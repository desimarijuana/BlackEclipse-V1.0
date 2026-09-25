"""The Financial Retrieval Layer — the orchestrator tools call (Milestone 2M/N).

Flow:

    request
      → planner (task-aware source selection, explainable)
      → cache check (freshness policy)
      → parallel / sequential retrieval across selected sources
      → normalization (each source already normalizes)
      → data-quality validation
      → conflict resolution across structured sources
      → evidence aggregation (provenance preserved)
      → FinancialRetrievalResult

The layer is provider-agnostic: it knows source *names* from the planner, not
yfinance or JDdS. It never fabricates data: when a precise dataset is required
and unavailable, it returns UNAVAILABLE rather than searching the web for a
number.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..tools import DataBridge
from .aggregate import aggregate, outcome_to_evidence
from .cache import RetrievalCache
from .conflicts import detect_conflicts
from .contract import (
    EvidenceItem,
    FinancialRetrievalRequest,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    QualityStatus,
    SourceReference,
    RetrievalStatus,
)
from .parallel import run_parallel
from .policies import cadence_for
from .planner import (
    SEC_FILINGS,
    STRUCTURED_LIVE,
    STRUCTURED_VAULT,
    WEB,
    plan_retrieval,
)
from .retry import retrieve_with_retry, DEFAULT_MAX_RETRIES
from .routing import classify_outcome, classify_skip
from .sources import RetrievalSource, SourceOutcome, outcome_diagnostics
from .structured import JddsSource, LiveStructuredSource, SecFilingsSource
from .validate import detect_incomplete, validate_objects
from .web import WebResearchSource

# Data types where a single best source is expected (not multi-source synthesis).
_SINGLE_BEST = {
    "current_quote",
    "historical_prices",
    "macro_series",
    "company_profile",
    "financial_statements",
}
# Data types where multiple sources are intentionally combined.
_MULTI_SOURCE = {"earnings", "news", "web_research", "world_events", "derived_metric"}


class FinancialRetrievalLayer:
    def __init__(
        self,
        bridge: Optional[DataBridge],
        cache: Optional[RetrievalCache] = None,
        on_event: Optional[Any] = None,
        store: Optional[Any] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._sources: dict[str, RetrievalSource] = {
            STRUCTURED_VAULT: JddsSource(bridge),
            STRUCTURED_LIVE: LiveStructuredSource(bridge),
            SEC_FILINGS: SecFilingsSource(bridge),
            WEB: WebResearchSource(bridge),
        }
        self.cache = cache or RetrievalCache()
        self._on_event = on_event
        self._max_retries = max(0, int(max_retries))
        # D1: a durable retrieval store (agent-memory.db). A parsed result is
        # persisted and replayed for an identical request, so the same query
        # yields the same figures and citations instead of re-scraping.
        self._store = store
        # Performance counters (reported, never fabricated).
        self.metrics: dict[str, int] = {
            "requests": 0,
            "cacheHits": 0,
            "durableHits": 0,
            "cacheMisses": 0,
            "deduplicated": 0,
            "sourceCalls": 0,
            "failures": 0,
            "conflicts": 0,
        }

    def available_sources(self, request: FinancialRetrievalRequest) -> set[str]:
        return {name for name, source in self._sources.items() if source.available(request)}

    async def retrieve(self, request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
        started = time.monotonic()
        self.metrics["requests"] += 1

        plan = plan_retrieval(request, available_sources=self.available_sources(request))
        await self._emit("retrieval.planned", {"dataType": request.dataType, "strategy": plan.sources, "rationale": plan.rationale})

        # ── Durable replay (D1): an identical request returns the stored result.
        # Deterministic by construction — no read-time re-scrape to drift.
        durable = self._recall_durable(request)
        if durable is not None:
            self.metrics["durableHits"] += 1
            durable.strategy = plan.sources
            durable.latencyMs = int((time.monotonic() - started) * 1000)
            await self._emit("retrieval.durable_hit", {"dataType": request.dataType})
            return durable

        # ── Cache (freshness policy) with in-flight deduplication ──
        async def _do_retrieve() -> FinancialRetrievalResult:
            return await self._execute(request, plan)

        result, cache_hit, deduped = await self.cache.get_or_retrieve(request, _do_retrieve)
        if cache_hit:
            self.metrics["cacheHits"] += 1
            # Mark the returned copy as cached so callers/evidence can label it.
            result = result.model_copy(update={"cached": True})
            await self._emit("retrieval.cache_hit", {"dataType": request.dataType})
        elif deduped:
            self.metrics["deduplicated"] += 1
            await self._emit("retrieval.deduplicated", {"dataType": request.dataType})
        else:
            self.metrics["cacheMisses"] += 1
            # Persist a successful parse for deterministic replay.
            self._persist_durable(request, result)

        result.strategy = plan.sources
        result.latencyMs = int((time.monotonic() - started) * 1000)
        if plan.warnings:
            for warning in plan.warnings:
                if warning not in result.warnings:
                    result.warnings.append(warning)
        return result

    # ── Durable store helpers (D1) ────────────────────────────────────────────

    def _recall_durable(self, request: FinancialRetrievalRequest) -> Optional[FinancialRetrievalResult]:
        """Return a persisted result for an identical request, if one exists.

        Only replayed when the stored data still satisfies the request's
        freshness policy — a stale stored result is not silently served.
        """
        if self._store is None:
            return None
        try:
            record = self._store.get_retrieval(self.cache.key_for(request))
        except Exception:  # noqa: BLE001 - a store read failure must not break retrieval
            return None
        if not record:
            return None
        try:
            result = FinancialRetrievalResult(**record["result"])
        except Exception:  # noqa: BLE001
            return None
        # Honor freshness: a slow/frozen series is fine; a realtime one is not.
        if request.dataType in ("current_quote", "historical_prices"):
            return None
        return result.model_copy(update={"cached": True})

    def _persist_durable(self, request: FinancialRetrievalRequest, result: FinancialRetrievalResult) -> None:
        """Persist a successful, non-empty result for replay (D1).

        Only OK/PARTIAL results with data are stored — never an empty answer,
        which could otherwise be replayed as if it were data.
        """
        if self._store is None:
            return
        if result.status not in ("OK", "PARTIAL") or (result.data is None and not result.evidence):
            return
        try:
            provenance = {
                "sources": [r.source for r in result.sourceReferences],
                "strategy": result.strategy,
                "retrievedAt": result.retrievedAt,
                "dataTimestamp": result.dataTimestamp if hasattr(result, "dataTimestamp") else None,
            }
            self._store.save_retrieval(
                self.cache.key_for(request),
                request.dataType,
                request.instrument,
                request.market,
                result.model_dump(mode="json"),
                provenance,
            )
        except Exception:  # noqa: BLE001 - persistence is best-effort, never fatal
            pass

    # ── Execution ──────────────────────────────────────────────────────────────

    async def _execute(self, request: FinancialRetrievalRequest, plan: Any) -> FinancialRetrievalResult:
        if not plan.sources:
            return FinancialRetrievalResult(
                status="UNAVAILABLE",
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                freshness=request.freshnessRequirement,
                quality="unknown",
                warnings=plan.warnings or ["no available source"],
                strategy=plan.sources,
            )

        if request.dataType in _SINGLE_BEST:
            return await self._execute_single(request, plan)
        return await self._execute_multi(request, plan)

    async def _execute_single(self, request: FinancialRetrievalRequest, plan: Any) -> FinancialRetrievalResult:
        """Try planned sources in order; first OK result wins (then validate)."""
        attempts: list[SourceOutcome] = []
        warnings: list[str] = []
        diagnostics: list[dict[str, Any]] = []
        # Fallback misses are recorded separately and are NOT carried into a
        # successful answer: a live source answering after a vault miss is not a
        # degradation of the result, and warning about it makes a fresh quote
        # look suspect (e.g. "EURUSD is not in the instrument universe" beside a
        # valid FX quote).
        fallback_notes: list[str] = []
        for name in plan.sources:
            source = self._sources.get(name)
            # Preserve the EXACT reason a route was skipped (ineligible /
            # not_implemented / unconfigured). A skipped route is never recorded
            # as a provider failure, and is auditable in the receipt (WS4).
            skip = classify_skip(name, source, request) if source is not None else ("not_implemented", f"{name} is not registered")
            if skip is not None:
                category, reason = skip
                diagnostics.append(
                    {
                        "provider": name,
                        "category": category,
                        "routeCategory": category,
                        "normalizedStatus": "skipped",
                        "retryable": False,
                        "detail": reason,
                    }
                )
                await self._emit("retrieval.source_skipped", {"source": name, "category": category, "reason": reason})
                continue
            self.metrics["sourceCalls"] += 1
            await self._emit("retrieval.source_start", {"source": name, "dataType": request.dataType})
            outcome = await self._retrieve_one(source, request)
            attempts.append(outcome)
            for d in outcome_diagnostics(outcome):
                # Tag each ran-outcome with its route category so "no data" is
                # distinguishable from "provider failure" downstream.
                diagnostics.append({**d, "routeCategory": classify_outcome(outcome)})
            # AMBIGUOUS is terminal: the ticker does not name one instrument, and
            # no other source can change that. Return it rather than trying a
            # different provider that might guess.
            if outcome.status == "AMBIGUOUS":
                await self._emit("retrieval.source_unavailable", {"source": name, "error": outcome.error})
                return FinancialRetrievalResult(
                    status="AMBIGUOUS",
                    objective=request.objective,
                    dataType=request.dataType,
                    instrument=request.instrument,
                    freshness=request.freshnessRequirement,
                    quality="unknown",
                    warnings=warnings + [outcome.error or "instrument identity is ambiguous"],
                    strategy=plan.sources,
                    diagnostics=diagnostics,
                )
            if outcome.status == "OK" and (outcome.objects or outcome.evidence):
                await self._emit("retrieval.source_ok", {"source": name, "objects": len(outcome.objects)})
                # Only the answering source's own warnings apply to the result.
                return self._finalize_single(
                    request, outcome, list(outcome.warnings), plan, fallback_notes,
                    diagnostics=diagnostics,
                )
            self.metrics["failures"] += 1
            if outcome.error:
                fallback_notes.append(f"{name}: {outcome.error}")
            await self._emit("retrieval.source_unavailable", {"source": name, "error": outcome.error})

        # Nothing succeeded.
        return FinancialRetrievalResult(
            status="UNAVAILABLE",
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            freshness=request.freshnessRequirement,
            quality="unknown",
            warnings=fallback_notes + warnings + plan.warnings,
            strategy=plan.sources,
            # Every attempt is auditable: "the web had nothing" vs "the route is
            # broken / timed out / was blocked" is now distinguishable.
            diagnostics=diagnostics,
        )

    async def _execute_multi(self, request: FinancialRetrievalRequest, plan: Any) -> FinancialRetrievalResult:
        """Run independent sources concurrently; aggregate all evidence."""
        tasks: list[tuple[str, Any]] = []
        for name in plan.sources:
            source = self._sources.get(name)
            if source is None or not source.available(request):
                continue
            tasks.append((name, self._bind(source, request)))

        if not tasks:
            return FinancialRetrievalResult(
                status="UNAVAILABLE",
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                freshness=request.freshnessRequirement,
                warnings=plan.warnings + ["no available source"],
                strategy=plan.sources,
            )

        self.metrics["sourceCalls"] += len(tasks)
        task_results = await run_parallel(
            tasks,
            on_start=lambda n: None,
            on_done=None,
        )

        items: list[EvidenceItem] = []
        references: list[SourceReference] = []
        warnings: list[str] = []
        ok = 0
        for tr in task_results:
            if tr.ok and tr.outcome is not None:
                ok += 1
                items.extend(tr.outcome.evidence)
                references.extend(tr.outcome.references)
            else:
                self.metrics["failures"] += 1
                if tr.error:
                    warnings.append(tr.error)

        if not items:
            return FinancialRetrievalResult(
                status="UNAVAILABLE",
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                freshness=request.freshnessRequirement,
                warnings=warnings + plan.warnings,
                strategy=plan.sources,
            )

        status: RetrievalStatus = "OK" if ok == len(task_results) else "PARTIAL"
        quality: QualityStatus = "valid"
        return FinancialRetrievalResult(
            status=status,
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            data={"evidenceCount": len(items)},
            evidence=items,
            sourceReferences=references,
            freshness=request.freshnessRequirement,
            quality=quality,
            warnings=warnings + plan.warnings,
            strategy=plan.sources,
        )

    # ── Single-result post-processing ─────────────────────────────────────────

    def _finalize_single(
        self,
        request: FinancialRetrievalRequest,
        outcome: SourceOutcome,
        warnings: list[str],
        plan: Any,
        fallback_notes: Optional[list[str]] = None,
        diagnostics: Optional[list[dict[str, Any]]] = None,
    ) -> FinancialRetrievalResult:
        objects = outcome.objects
        _ = fallback_notes  # fallback misses are not degradations of the answer
        # Structured providers may include a duplicate value under two sources;
        # resolve conflicts across the objects of THIS outcome.
        chosen, conflict_warnings, unresolved = self._resolve(objects)
        warnings.extend(conflict_warnings)
        if unresolved:
            self.metrics["conflicts"] += 1

        # A source may declare how often it publishes (`cadenceSeconds` in its
        # raw payload); a slow-cadence source is DELAYED, not stale. When it does
        # not, fall back to the data type's natural cadence (Issue 4) so a
        # currently-valid annual filing is not flagged stale by a 7-day window —
        # prices/quotes have no cadence and keep their strict windows.
        cadence = None
        if isinstance(outcome.raw, dict):
            cadence = outcome.raw.get("cadenceSeconds")
            if not isinstance(cadence, (int, float)):
                cadence = None
        if cadence is None:
            cadence = cadence_for(request.dataType)
        objects, quality_warnings = validate_objects(
            chosen, request.freshnessRequirement, source_cadence_seconds=cadence
        )
        warnings.extend(quality_warnings)

        # D2: detect truncated/partial parses. A partial numeric is never emitted
        # as a figure — it is marked invalid and the result is flagged incomplete.
        incomplete_warnings = detect_incomplete(objects)
        warnings.extend(incomplete_warnings)
        incomplete = any(o.quality == "invalid" for o in objects) and bool(incomplete_warnings)

        quality: QualityStatus = "valid"
        if unresolved:
            quality = "warning"
        elif any(o.quality == "invalid" for o in objects):
            quality = "invalid"
        elif any(o.quality == "warning" for o in objects) or warnings:
            quality = "warning"

        refs = outcome.references or [SourceReference(source=outcome.source)]
        evidence = list(outcome.evidence)
        if not evidence:
            item = outcome_to_evidence(outcome)
            if item is not None:
                evidence = [item]

        status: RetrievalStatus = "OK"
        if unresolved:
            status = "CONFLICTING"
        # A precise-data request that only got a web snippet must not claim OK.
        if request.dataType in ("historical_prices", "macro_series", "derived_metric") and outcome.source == WEB:
            status = "UNAVAILABLE"
        # D2: an incomplete parse is never a successful value.
        if incomplete:
            status = "UNAVAILABLE"

        # Separate invalid (withheld) objects from the payload entirely.
        usable = [o for o in objects if o.quality != "invalid"]
        data = _data_payload(request, usable)
        # The canonical identity, when the source supplied one, rides on the
        # result so every consumer can verify which instrument the answer is for.
        identity = next((o.identity for o in usable if o.identity is not None), None)

        # C4: conflicting sources produce a structured flag carrying ALL
        # candidates with provenance — the agent must surface it, not pick one.
        conflicts = _conflicts_payload(objects) if unresolved else []

        # D3: a value is only presentable when its identity + provenance are
        # verified. `degraded` is TOP-LEVEL, never nested metadata.
        provenance_verified = len(refs) > 0 and not incomplete
        degraded, degradation = _degradation(
            quality=quality,
            unresolved=unresolved,
            incomplete=incomplete,
            identity_required=request.dataType in ("current_quote", "historical_prices", "company_profile", "financial_statements"),
            identity=identity,
            provenance_verified=provenance_verified,
        )

        result = FinancialRetrievalResult(
            status=status,
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            identity=identity,
            data=data,
            evidence=evidence,
            sourceReferences=refs,
            freshness=request.freshnessRequirement,
            quality=quality,
            warnings=_dedupe(warnings + plan.warnings),
            strategy=plan.sources,
            degraded=degraded,
            degradation=degradation,
            incomplete=incomplete,
            conflicts=conflicts,
            provenanceVerified=provenance_verified,
            diagnostics=diagnostics or [],
        )
        # Cache only successful/partial results.
        if status in ("OK", "PARTIAL"):
            self.cache.put(
                request,
                result,
                source=outcome.source,
                data_timestamp=usable[0].dataTimestamp if usable else None,
            )
        return result

    @staticmethod
    def _resolve(objects: list[NormalizedFinancialObject]) -> tuple[list[NormalizedFinancialObject], list[str], bool]:
        """Detect conflicts only between observations OF THE SAME FACT.

        A conflict means two sources disagree about one measurement. Time-series
        bars (same metric name, different date/period) are separate observations
        and must never be collapsed — that was a real bug the scenario tests
        caught (a 20-bar series resolved to a single bar).
        """
        groups: dict[str, list[NormalizedFinancialObject]] = {}
        passthrough: list[NormalizedFinancialObject] = []
        for obj in objects:
            # Non-numeric facts (sector, industry, description, exchange…) can
            # never "disagree" numerically. Passing them through untouched is
            # what was missing when company_profile returned five valid objects
            # as an empty body.
            if isinstance(obj.value, (int, float)) and not isinstance(obj.value, bool):
                key = f"{obj.name}@{obj.dataTimestamp or ''}@{obj.period or ''}"
                groups.setdefault(key, []).append(obj)
            else:
                passthrough.append(obj)
        chosen, warnings, unresolved = detect_conflicts(groups)
        return [*passthrough, *chosen.values()], warnings, unresolved

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _bind(self, source: RetrievalSource, request: FinancialRetrievalRequest):
        async def _call() -> SourceOutcome:
            return await source.retrieve(request)

        return _call

    async def _retrieve_one(self, source: RetrievalSource, request: FinancialRetrievalRequest) -> SourceOutcome:
        async def _attempt() -> SourceOutcome:
            try:
                return await source.retrieve(request)
            except Exception as exc:  # noqa: BLE001 - isolate source failures
                return SourceOutcome(source=source.name, status="ERROR", error=str(exc))

        # A transient failure (timeout / 5xx / socket) gets a bounded retry with
        # backoff before the layer moves on to the next independent provider. A
        # permanent failure (blocked, unsupported content type) is never retried.
        return await retrieve_with_retry(_attempt, max_retries=self._max_retries)

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry must never break retrieval
            pass


def _conflicts_payload(objects: list[NormalizedFinancialObject]) -> list[dict[str, Any]]:
    """C4: group conflicting observations, carrying every candidate + provenance.

    One entry per (metric, period) with more than one distinct value across
    sources, listing each value with its source so the agent can surface the
    disagreement rather than silently choosing.
    """
    buckets: dict[tuple[str, Optional[str]], list[NormalizedFinancialObject]] = {}
    for o in objects:
        buckets.setdefault((o.name, o.period), []).append(o)
    out: list[dict[str, Any]] = []
    for (name, period), group in buckets.items():
        distinct = {_hashable(o.value) for o in group}
        if len(distinct) <= 1:
            continue
        if len({o.source.source for o in group}) <= 1:
            continue  # a single source repeating itself is not a conflict
        out.append(
            {
                "metric": name,
                "period": period,
                "candidates": [
                    {
                        "value": o.value,
                        "unit": o.unit,
                        "source": o.source.source,
                        "sourceType": o.source.sourceType,
                        "dataTimestamp": o.dataTimestamp,
                    }
                    for o in group
                ],
            }
        )
    return out


def _hashable(value: Any) -> Any:
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


def _dedupe(items: list[str]) -> list[str]:
    """De-duplicate warnings while preserving order (identical text once)."""
    seen: set[str] = set()
    out: list[str] = []
    for w in items:
        key = w.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(w)
    return out


def _degradation(
    *,
    quality: str,
    unresolved: bool,
    incomplete: bool,
    identity_required: bool,
    identity: Any,
    provenance_verified: bool,
) -> tuple[bool, Optional[str]]:
    """D3: compute the TOP-LEVEL degradation flag + reason.

    Degraded when quality is not `valid`, identity could not be verified for a
    data type that requires one, or the provenance chain is incomplete. The
    reason is user-safe and lives beside the value, never nested.
    """
    reasons: list[str] = []
    if incomplete:
        reasons.append("data parse incomplete")
    if unresolved:
        reasons.append("sources disagree")
    if quality == "warning":
        reasons.append("quality warnings present")
    if quality == "invalid":
        reasons.append("value failed validation")
    if identity_required and identity is None:
        reasons.append("instrument identity not verified")
    if not provenance_verified:
        reasons.append("provenance incomplete")
    if reasons:
        return True, "; ".join(reasons)
    return False, None


def _data_payload(request: FinancialRetrievalRequest, objects: list[NormalizedFinancialObject]) -> Any:
    """Shape the `data` field for the agent, keyed by metric name."""
    if request.dataType == "historical_prices":
        bars: dict[str, dict[str, Any]] = {}
        for obj in objects:
            date = obj.dataTimestamp or ""
            bars.setdefault(date, {"date": date})[obj.name] = obj.value
        return sorted(bars.values(), key=lambda b: b.get("date") or "")
    if request.dataType in ("current_quote", "company_profile"):
        return {obj.name: obj.value for obj in objects}
    return [obj.model_dump() for obj in objects]


__all__ = ["FinancialRetrievalLayer"]
