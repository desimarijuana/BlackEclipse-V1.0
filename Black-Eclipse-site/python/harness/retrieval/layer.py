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
from .planner import (
    STRUCTURED_LIVE,
    STRUCTURED_VAULT,
    WEB,
    plan_retrieval,
)
from .sources import RetrievalSource, SourceOutcome
from .structured import JddsSource, LiveStructuredSource
from .validate import validate_objects
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
    ) -> None:
        self._sources: dict[str, RetrievalSource] = {
            STRUCTURED_VAULT: JddsSource(bridge),
            STRUCTURED_LIVE: LiveStructuredSource(bridge),
            WEB: WebResearchSource(bridge),
        }
        self.cache = cache or RetrievalCache()
        self._on_event = on_event
        # Performance counters (reported, never fabricated).
        self.metrics: dict[str, int] = {
            "requests": 0,
            "cacheHits": 0,
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

        result.strategy = plan.sources
        result.latencyMs = int((time.monotonic() - started) * 1000)
        if plan.warnings:
            for warning in plan.warnings:
                if warning not in result.warnings:
                    result.warnings.append(warning)
        return result

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
        for name in plan.sources:
            source = self._sources.get(name)
            if source is None or not source.available(request):
                continue
            self.metrics["sourceCalls"] += 1
            await self._emit("retrieval.source_start", {"source": name, "dataType": request.dataType})
            outcome = await self._retrieve_one(source, request)
            attempts.append(outcome)
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
                )
            if outcome.status == "OK" and (outcome.objects or outcome.evidence):
                await self._emit("retrieval.source_ok", {"source": name, "objects": len(outcome.objects)})
                return self._finalize_single(request, outcome, warnings, plan)
            self.metrics["failures"] += 1
            if outcome.error:
                warnings.append(f"{name}: {outcome.error}")
            await self._emit("retrieval.source_unavailable", {"source": name, "error": outcome.error})

        # Nothing succeeded.
        return FinancialRetrievalResult(
            status="UNAVAILABLE",
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            freshness=request.freshnessRequirement,
            quality="unknown",
            warnings=warnings + plan.warnings,
            strategy=plan.sources,
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
    ) -> FinancialRetrievalResult:
        objects = outcome.objects
        # Structured providers may include a duplicate value under two sources;
        # resolve conflicts across the objects of THIS outcome.
        chosen, conflict_warnings, unresolved = self._resolve(objects)
        warnings.extend(conflict_warnings)
        if unresolved:
            self.metrics["conflicts"] += 1

        objects, quality_warnings = validate_objects(chosen, request.freshnessRequirement)
        warnings.extend(quality_warnings)

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

        data = _data_payload(request, objects)
        # The canonical identity, when the source supplied one, rides on the
        # result so every consumer can verify which instrument the answer is for.
        identity = next((o.identity for o in objects if o.identity is not None), None)
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
            warnings=warnings + plan.warnings,
            strategy=plan.sources,
        )
        # Cache only successful/partial results.
        if status in ("OK", "PARTIAL"):
            self.cache.put(
                request,
                result,
                source=outcome.source,
                data_timestamp=objects[0].dataTimestamp if objects else None,
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
        try:
            return await source.retrieve(request)
        except Exception as exc:  # noqa: BLE001 - isolate source failures
            return SourceOutcome(source=source.name, status="ERROR", error=str(exc))

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry must never break retrieval
            pass


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
