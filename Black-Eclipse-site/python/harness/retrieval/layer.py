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

import datetime as dt
import time
from typing import Any, Optional

from ..tools import DataBridge
from .aggregate import aggregate, outcome_to_evidence
from .authority import authority_for, decide_source, effective_authority
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
from .crypto import CryptoSource
from .health import apply_breaker, build_health_index, rank_sources
from .parallel import run_parallel
from .policies import cadence_for, max_age_seconds
from .planner import (
    SEC_FILINGS,
    STRUCTURED_LIVE,
    STRUCTURED_VAULT,
    WEB,
    plan_retrieval,
)
from .ratelimit import RateLimitManager
from .registry import ProviderRegistry
from .retry import retrieve_with_retry, DEFAULT_MAX_RETRIES
from .routing import classify_outcome, classify_skip
from .sources import RetrievalSource, SourceOutcome, outcome_diagnostics
from .structured import JddsSource, LiveStructuredSource, SecFilingsSource
from .validate import detect_incomplete, validate_objects, validate_observations
from .web import WebResearchSource

# The crypto source id. Kept beside the other source names so the layer and the
# planner agree; `authority.CRYPTO` is the canonical name.
from .authority import CRYPTO  # noqa: E402

# Data types whose payload is a legitimate TIME SERIES: an old row inside it is
# the point of history, not a defect, so the per-observation check is skipped.
_SERIES_TYPES = {"historical_prices", "macro_series"}


class FinancialRetrievalLayer:
    def __init__(
        self,
        bridge: Optional[DataBridge],
        cache: Optional[RetrievalCache] = None,
        on_event: Optional[Any] = None,
        store: Optional[Any] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        mcp_sources: Optional[list[RetrievalSource]] = None,
        rate_limits: Optional[RateLimitManager] = None,
        registry: Optional[ProviderRegistry] = None,
    ) -> None:
        self._sources: dict[str, RetrievalSource] = {
            STRUCTURED_VAULT: JddsSource(bridge),
            STRUCTURED_LIVE: LiveStructuredSource(bridge),
            SEC_FILINGS: SecFilingsSource(bridge),
            WEB: WebResearchSource(bridge),
            CRYPTO: CryptoSource(bridge),
        }
        # Operator-declared MCP data tools (Milestone 6) join the SAME source
        # registry, so the planner can select/compare them side-by-side. A
        # generic MCP tool that does not implement the contract is not added
        # here — it stays directly callable by the model.
        for source in mcp_sources or []:
            self._sources[source.name] = source
        self._mcp_sources = list(mcp_sources or [])
        # Health-aware ordering (P0-2): the `source_health` index is fetched at
        # most once per layer lifetime and reused, so ordering is deterministic
        # within a run and adds no repeated bridge chatter. Fail-open — an
        # unavailable ledger leaves the static plan untouched.
        self._health_index: Optional[dict] = None
        self._health_loaded = False
        self.cache = cache or RetrievalCache()
        self._on_event = on_event
        self._max_retries = max(0, int(max_retries))
        # Centralized provider pacing (Financial Data Gateway). A layer built
        # without a manager keeps the previous behavior exactly — pacing is
        # additive. The registry carries each provider's declared limit spec.
        self.rate_limits = rate_limits or RateLimitManager()
        self.registry = registry or ProviderRegistry()
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

    async def _health(self) -> Optional[dict]:
        """The `source_health` index, fetched once and cached. Best-effort."""
        if self._health_loaded:
            return self._health_index
        self._health_loaded = True
        if self._sources[STRUCTURED_VAULT]._bridge is None:  # noqa: SLF001 - internal wiring
            return None
        try:
            payload = await self._sources[STRUCTURED_VAULT]._bridge.fetch("source_health", {})  # noqa: SLF001
            if isinstance(payload, dict) and payload.get("status") == "OK":
                self._health_index = build_health_index(payload.get("rows"))
        except Exception:  # noqa: BLE001 - health is best-effort, never load-bearing
            self._health_index = None
        return self._health_index

    def _declared_for(self, request: FinancialRetrievalRequest) -> list[str]:
        """Declared MCP source names whose data type matches this request."""
        out: list[str] = []
        for source in self._mcp_sources:
            try:
                if request.dataType in getattr(source, "dataTypes", ()) and source.available(request):
                    out.append(source.name)
            except Exception:  # noqa: BLE001 - a probing failure never selects a source
                continue
        return out

    async def retrieve(self, request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
        started = time.monotonic()
        self.metrics["requests"] += 1

        declared = self._declared_for(request)
        plan = plan_retrieval(
            request,
            available_sources=self.available_sources(request),
            additional_sources=declared,
        )

        # ── Durable replay (D1): an identical request returns the stored result.
        # Deterministic by construction — no read-time re-scrape to drift. It is
        # checked BEFORE the health read so a replay performs NO provider work at
        # all (not even reading the health ledger).
        durable = self._recall_durable(request)
        if durable is not None:
            self.metrics["durableHits"] += 1
            durable.strategy = plan.sources
            durable.latencyMs = int((time.monotonic() - started) * 1000)
            await self._emit("retrieval.planned", {
                "dataType": request.dataType, "strategy": plan.sources,
                "rationale": plan.rationale, "mcpSources": declared,
            })
            await self._emit("retrieval.durable_hit", {"dataType": request.dataType})
            return durable

        # P0-2: reorder so a healthy route outranks a degraded/failing one. Only
        # REORDERS among already-available sources; never adds or removes one.
        index = await self._health()
        if index:
            plan.sources, health_notes = rank_sources(
                plan.sources, index, request.market, request.dataType
            )
            plan.warnings.extend(health_notes)
            # D6: a route with zero recorded successes over N failures is
            # demoted and skipped, not retried on every request. Provenance names
            # it and why.
            plan.sources, plan.routes_skipped = apply_breaker(
                plan.sources, index, request.market, request.dataType
            )
        await self._emit("retrieval.planned", {
            "dataType": request.dataType, "strategy": plan.sources,
            "rationale": plan.rationale, "mcpSources": declared,
        })

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
                diagnostics=list(getattr(plan, "routes_skipped", [])),
            )

        authority = effective_authority(authority_for(request.dataType), request)
        if authority.policy == "arbitrated":
            return await self._execute_arbitrated(request, plan, authority)
        return await self._execute_single(request, plan, authority)
    async def _execute_single(self, request: FinancialRetrievalRequest, plan: Any, authority: Any = None) -> FinancialRetrievalResult:
        """Try planned sources in order; first OK result wins (then validate)."""
        attempts: list[SourceOutcome] = []
        warnings: list[str] = []
        diagnostics: list[dict[str, Any]] = [*getattr(plan, "routes_skipped", [])]
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
                    diagnostics=diagnostics, authority=authority,
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

    async def _execute_arbitrated(self, request: FinancialRetrievalRequest, plan: Any, authority: Any) -> FinancialRetrievalResult:
        """Run EVERY eligible candidate concurrently, then decide with provenance.

        This is the Phase-13 path for price/series/macro/profile types. It reuses
        the existing ``run_parallel`` + ``_resolve`` + ``detect_conflicts`` seam —
        there is no second conflict mechanism. Its whole point is that a fresh live
        reading is *consulted* alongside a saved snapshot, so a real disagreement
        can be preserved (which was unreachable when the first success won).
        """
        tasks: list[tuple[str, Any]] = []
        diagnostics: list[dict[str, Any]] = [*getattr(plan, "routes_skipped", [])]
        for name in plan.sources:
            source = self._sources.get(name)
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
            tasks.append((name, self._bind(source, request)))
            await self._emit("retrieval.source_start", {"source": name, "dataType": request.dataType})

        if not tasks:
            return FinancialRetrievalResult(
                status="UNAVAILABLE",
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                freshness=request.freshnessRequirement,
                warnings=plan.warnings + ["no available source"],
                strategy=plan.sources,
                diagnostics=diagnostics,
            )

        self.metrics["sourceCalls"] += len(tasks)
        task_results = await run_parallel(tasks, on_start=lambda n: None, on_done=None)

        outcomes: list[SourceOutcome] = []
        for tr in task_results:
            if tr.outcome is not None:
                outcomes.append(tr.outcome)
                for d in outcome_diagnostics(tr.outcome):
                    diagnostics.append({**d, "routeCategory": classify_outcome(tr.outcome)})
                if tr.outcome.status == "OK" and (tr.outcome.objects or tr.outcome.evidence):
                    await self._emit("retrieval.source_ok", {"source": tr.name, "objects": len(tr.outcome.objects)})
                else:
                    await self._emit("retrieval.source_unavailable", {"source": tr.name, "error": tr.outcome.error})
            elif tr.error:
                self.metrics["failures"] += 1
                diagnostics.append(
                    {
                        "provider": tr.name,
                        "category": "provider_failure",
                        "routeCategory": "provider_failure",
                        "normalizedStatus": "failed",
                        "retryable": not tr.timed_out,
                        "detail": tr.error,
                    }
                )

        decision = decide_source(authority, outcomes, request)
        if decision.chosen is None:
            status: RetrievalStatus = "CONFLICTING" if decision.reason.startswith("CONFLICTING") else "UNAVAILABLE"
            if status == "CONFLICTING":
                self.metrics["conflicts"] += 1
            # Preserve every candidate and its provenance when they disagree.
            candidate_objects = [o for outcome in outcomes if outcome.status == "OK" for o in outcome.objects]
            return FinancialRetrievalResult(
                status=status,
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                freshness=request.freshnessRequirement,
                warnings=_dedupe([decision.reason, *plan.warnings, *(w for _n, w in decision.rejected)]),
                strategy=plan.sources,
                conflicts=_conflicts_payload(candidate_objects) if status == "CONFLICTING" else [],
                diagnostics=diagnostics,
            )

        chosen_outcome = next((o for o in outcomes if o.source == decision.chosen), None)
        if chosen_outcome is None:  # pragma: no cover - decide_source only names members of `outcomes`
            return FinancialRetrievalResult(
                status="UNAVAILABLE", objective=request.objective, dataType=request.dataType,
                instrument=request.instrument, freshness=request.freshnessRequirement,
                strategy=plan.sources, diagnostics=diagnostics,
            )
        fallback_notes = [w for name, w in decision.rejected if name != decision.chosen and not w.startswith("skipped")]
        return self._finalize_single(
            request, chosen_outcome, list(chosen_outcome.warnings), plan, fallback_notes,
            diagnostics=diagnostics, authority=authority,
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
        authority: Any = None,
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

        # Phase 13: a payload of many rows can pass the dataset-level freshness
        # check while a few individual rows are stale. `validate_observations`
        # answers "is THIS value current?" for a non-series payload — the check
        # that stops one instrument's stale row riding a fresh batch. The
        # authority's window is the SAME ceiling arbitration used to gate the
        # source, so the age stated here and the eligibility agree.
        if request.dataType not in _SERIES_TYPES:
            window_s = None
            if authority is not None:
                request_window = max_age_seconds(request.freshnessRequirement)
                window_s = min(int(authority.request_window_s), request_window) or int(
                    authority.request_window_s
                )
            objects, observation_warnings = validate_observations(
                objects, request.freshnessRequirement, window_s=window_s
            )
            warnings.extend(observation_warnings)

        # D2: statements carry a per-statement maximum age. A cache hit whose
        # reported period ends years ago is not "the latest" - it is STALE, with
        # the real period end and age, and `stale=true` so a consumer can reject
        # it without parsing a warning string.
        statement_stale: Optional[str] = None
        if request.dataType == "financial_statements":
            statement_stale = _statement_staleness(request, objects)
            if statement_stale is not None:
                warnings.append(statement_stale)

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
        # An explicit `webFallback` request accepts it as PARTIAL (labelled): the
        # caller asked for a last-resort page route, not a verified series.
        if request.dataType in ("historical_prices", "macro_series", "derived_metric") and outcome.source == WEB:
            if request.webFallback and request.dataType in ("historical_prices", "macro_series"):
                status = "PARTIAL"
                warnings.append(
                    "WEB fallback: this series is page-sourced and labelled PARTIAL, "
                    "not a verified structured series"
                )
            else:
                status = "UNAVAILABLE"
        # A statement whose newest period is beyond its cadence is honest STALE,
        # never presented as "latest".
        if statement_stale is not None:
            status = "STALE"
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
            stale=statement_stale is not None,
            reasonCode=("DATA_STALE" if statement_stale is not None else None),
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
            return await self._retrieve_one(source, request)

        return _call

    async def _retrieve_one(self, source: RetrievalSource, request: FinancialRetrievalRequest) -> SourceOutcome:
        async def _attempt() -> SourceOutcome:
            try:
                return await source.retrieve(request)
            except Exception as exc:  # noqa: BLE001 - isolate source failures
                return SourceOutcome(source=source.name, status="ERROR", error=str(exc))

        # Centralized pacing: never stampede a provider. A denied acquire does not
        # call the provider at all — the outcome is an honest, categorized
        # rate-limit result, not a fabricated failure.
        spec = self._spec_for(source.name)
        decision = await self.rate_limits.acquire(source.name, spec)
        if not decision.allowed:
            await self._emit(
                "retrieval.rate_limited",
                {"source": source.name, "reason": decision.reason, "retryAfterS": decision.retry_after_s},
            )
            return SourceOutcome(
                source=source.name,
                status="UNAVAILABLE",
                error=f"rate limited: {decision.reason}",
                diagnostics=[
                    {
                        "provider": source.name,
                        "category": "rate_limited",
                        "normalizedStatus": "rate_limited",
                        "retryable": True,
                        "retryAfterS": decision.retry_after_s,
                        "detail": decision.reason,
                    }
                ],
            )
        try:
            # A transient failure (timeout / 5xx / socket) gets a bounded retry with
            # backoff before the layer moves on to the next independent provider. A
            # permanent failure (blocked, unsupported content type) is never retried.
            outcome = await retrieve_with_retry(_attempt, max_retries=self._max_retries)
        finally:
            await self.rate_limits.release(source.name)
        self._note_throttle(source.name, outcome)
        return outcome

    def _spec_for(self, provider: str):
        descriptor = self.registry.get(provider) if self.registry else None
        if descriptor is not None:
            return descriptor.rate_limit
        return None

    def _note_throttle(self, provider: str, outcome: SourceOutcome) -> None:
        """Open a cooldown when a provider reported 429 / an explicit Retry-After."""
        for diagnostic in outcome.diagnostics:
            if str(diagnostic.get("category")) in ("rate_limited", "http_error") and (
                diagnostic.get("httpStatus") == 429
                or diagnostic.get("rateLimited")
                or diagnostic.get("retryAfterS")
            ):
                hint = diagnostic.get("retryAfterS")
                try:
                    self.rate_limits.record_429(provider, float(hint) if hint else None)
                except Exception:  # noqa: BLE001 - pacing is best-effort
                    self.rate_limits.record_429(provider)
                return

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry must never break retrieval
            pass


ANNUAL_STATEMENT_MAX_AGE_DAYS = 548      # 18 months
QUARTERLY_STATEMENT_MAX_AGE_DAYS = 150


def _statement_staleness(
    request: FinancialRetrievalRequest, objects: list[NormalizedFinancialObject]
) -> Optional[str]:
    """A named STALE reason when the newest reported period is too old."""
    stamps = sorted({
        str(o.dataTimestamp) for o in objects
        if o.dataTimestamp and len(str(o.dataTimestamp)) >= 10
    })
    if not stamps:
        return None
    period_text = " ".join(str(o.period or "") for o in objects)
    quarterly = "Q" in period_text.upper() or any(
        o.period and str(o.period).upper().startswith("Q") for o in objects
    )
    # Infer quarterly cadence when consecutive period ends are ~3 months apart.
    if not quarterly and len(stamps) >= 2:
        first = _parse_date(stamps[0])
        last = _parse_date(stamps[-1])
        if first and last:
            span_days = (last - first).days
            if span_days and len(stamps) > 1 and span_days / (len(stamps) - 1) < 200:
                quarterly = True
    max_days = QUARTERLY_STATEMENT_MAX_AGE_DAYS if quarterly else ANNUAL_STATEMENT_MAX_AGE_DAYS
    newest = stamps[-1]
    parsed = _parse_date(newest)
    if parsed is None:
        return None
    age_days = (dt.datetime.now(dt.timezone.utc).date() - parsed).days
    if age_days <= max_days:
        return None
    return (
        f"STALE_STATEMENT: newest period ends {newest} ({age_days} days old); "
        f"{'quarterly' if quarterly else 'annual'} statements allow {max_days} days"
    )


def _parse_date(value: str) -> Optional[dt.date]:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None


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


