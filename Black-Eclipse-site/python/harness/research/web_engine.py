"""The Evidence-Driven Web Research Engine.

This is the orchestrator that ties the web-research contracts together into one
first-class capability, without duplicating any existing subsystem:

    question → intent → mandate → plan → (provider registry, with fallback)
      → search → extract (bridge) → escalate (existing browser) → normalize
      → entity resolution → evidence store → freshness / point-in-time
      → source ranking → source comparison → conflict detection
      → claim verification → deterministic calculations
      → citation generation → citation validation → coverage → synthesis
      → status / snapshot / persistence

It reuses the existing Phase-4 pieces (budget, periods, calculations, coverage)
where they apply, and the existing transport (TS `web_fetch`/`web_search` via the
DataBridge), browser runtime, SSRF guard and memory primitives. It never builds a
second agent loop, tool registry, data plane, browser or memory.

Supports synchronous and asynchronous execution, cancellation, bounded retries,
partial results, resumability and incremental updates.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .web_contracts import (
    Claim,
    Evidence,
    ResearchDepth,
    ResearchPlan,
    ResearchRequest,
    ResearchState,
    ResearchStatus,
    SourceConflict,
    WebResearchMandate,
    evidence_id,
    source_id,
)
from .web_extract import FetchResult, enrich_structured, fetch, fetch_to_evidence, structured_extract
from .web_browser import browser_extract
from .web_freshness import filter_admissible
from .web_intent import classify_intent
from .web_planner import PlanInput, plan_research
from .web_providers import SearchProviderRegistry, build_default_registry
from .web_quality import compute_quality
from .web_pricing import CostLedger
from .web_graph import build_graph
from .web_coverage import answered_questions as _answered_questions
from .web_sources import (
    SourceFamily,
    dedupe_news,
    make_source,
    rank_source,
    resolve_entity,
)
from .web_store import EvidenceStore
from .web_verify import (
    build_citations,
    detect_conflicts,
    validate_citations,
    verify_claim,
)

# Bounds so a single run can never run away.
MAX_CONCURRENT_FETCHES = 4
MAX_CONCURRENT_SEARCHES = 4
TOP_SOURCES_PER_QUERY = 3

# Process-wide control/status maps so a run started by one tool call can be
# observed, cancelled or continued by another (the engine itself is per-run).
# Bounded so a long-lived process cannot grow them without limit.
_RUN_CANCELS: dict[str, asyncio.Event] = {}
_RUN_STATUS: dict[str, ResearchStatus] = {}
_MAX_TRACKED_RUNS = 256

# In-flight background research tasks, keyed by research id, so a run started in
# one turn can be polled/cancelled from another without blocking the tool call.
_RUN_TASKS: dict[str, asyncio.Task[Any]] = {}


def schedule_background_research(
    request: ResearchRequest,
    *,
    bridge: Any = None,
    store: Any = None,
    registry: Optional[SearchProviderRegistry] = None,
    emitter: Any = None,
) -> str:
    """Create+persist a research mandate on the running loop, then execute it in
    the BACKGROUND. Returns the stable research id immediately.

    The mandate is persisted BEFORE the task starts, so `research_status` can see
    the run at once; the state is re-persisted on every transition. A finished
    task removes itself from the map (its result lives in the store). This is how
    a long research run stops blocking a single chat turn — poll it with
    `research_status`, resume with `research_continue`.
    """
    engine = ResearchEngine(bridge=bridge, store=store, registry=registry, emitter=emitter)
    # Persist + plan synchronously BEFORE scheduling, so the id is observable at
    # once and a cancel issued before the task starts is honoured.
    mandate, plan = engine.create_research_sync(request)
    research_id = mandate.researchId

    async def _prepare_then_run() -> None:
        try:
            await engine.execute_research(mandate, plan)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            raise
        except Exception:  # noqa: BLE001 - a background failure is state, never a crash
            pass
        finally:
            _RUN_TASKS.pop(research_id, None)

    task = asyncio.create_task(_prepare_then_run())
    _RUN_TASKS[research_id] = task
    _prune_runs()
    return research_id


def background_research_active(research_id: str) -> bool:
    task = _RUN_TASKS.get(research_id)
    return task is not None and not task.done()


def _diagnostic_category(result: FetchResult) -> Optional[str]:
    """The transport's failure category for a fetch, when one was reported.

    The bridge returns a structured diagnostic whose `category` names WHY a page
    could not be read. Falls back to keyword-matching the error string so an older
    bridge payload still routes to the right escalation decision.
    """
    for diagnostic in getattr(result, "diagnostics", None) or []:
        if isinstance(diagnostic, dict):
            category = str(diagnostic.get("category") or "").strip()
            if category:
                return category
    error = (getattr(result, "error", None) or "").lower()
    if "javascript" in error or "js-only" in error or "js_only" in error:
        return "javascript_only"
    if "paywall" in error or "subscription" in error or "login" in error or "denied access" in error:
        return "paywalled"
    if "unsupported" in error:
        return "unsupported_document"
    if "parse" in error:
        return "parse_failure"
    return None


def _prune_runs() -> None:
    """Keep the status/cancel maps bounded: drop the oldest TERMINAL runs first.

    In-flight (non-terminal) runs are never dropped, so a live run can always be
    observed or cancelled; only finished runs age out once the cap is reached.
    """
    if len(_RUN_STATUS) <= _MAX_TRACKED_RUNS:
        return
    terminal = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}
    for research_id in list(_RUN_STATUS.keys()):
        if len(_RUN_STATUS) <= _MAX_TRACKED_RUNS:
            break
        if _RUN_STATUS.get(research_id) is not None and _RUN_STATUS[research_id].state in terminal:
            _RUN_STATUS.pop(research_id, None)
            _RUN_CANCELS.pop(research_id, None)


def request_cancel(research_id: str) -> bool:
    """Signal a running research id to stop at the next safe checkpoint."""
    event = _RUN_CANCELS.get(research_id)
    if event is None:
        return False
    event.set()
    return True


def run_status(research_id: str) -> Optional[ResearchStatus]:
    return _RUN_STATUS.get(research_id)


@dataclass
class EngineResult:
    researchId: str
    status: ResearchStatus
    mandate: WebResearchMandate
    plan: ResearchPlan
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[SourceConflict] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    families: list[SourceFamily] = field(default_factory=list)
    calculations: list[Any] = field(default_factory=list)
    answer: str = ""
    snapshotId: Optional[str] = None
    # General entity/knowledge graph extracted from the evidence (evidence-anchored).
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    # Incremental research: what changed relative to the previous snapshot.
    delta: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "researchId": self.researchId,
            "status": self.status.model_dump(),
            "mandate": self.mandate.model_dump(),
            "plan": self.plan.model_dump(),
            "evidence": [_evidence_public(e) for e in self.evidence],
            "sources": self.sources,
            "claims": [c.model_dump() for c in self.claims],
            "citations": self.citations,
            "conflicts": [c.model_dump() for c in self.conflicts],
            "coverage": self.coverage,
            "rejections": self.rejections,
            "families": [f.__dict__ for f in self.families],
            "calculations": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.calculations],
            "answer": self.answer,
            "snapshotId": self.snapshotId,
            "entities": self.entities,
            "relations": self.relations,
            "delta": self.delta,
        }


class ResearchEngine:
    """One process-wide-capable research engine bound to the run's dependencies.

    The engine is constructed per run from the `ToolContext`/service: it carries
    the data bridge (transport), the `EvidenceStore` (persistence) and the provider
    registry. It holds no global mutable state except an in-memory cancel/status
    map keyed by research id, so a long run can be observed, cancelled and resumed.
    """

    def __init__(
        self,
        *,
        bridge: Any = None,
        store: Any = None,
        registry: Optional[SearchProviderRegistry] = None,
        emitter: Any = None,
    ) -> None:
        self._bridge = bridge
        self._store = store
        self._registry = registry or build_default_registry(bridge)
        self._emitter = emitter
        # Control/status live in process-wide maps (shared across runs); the
        # engine itself is constructed per run from the tool context.
        self._status = _RUN_STATUS
        self._cancel = _RUN_CANCELS

    # ── public API ──────────────────────────────────────────────────────────────

    def status(self, research_id: str) -> Optional[ResearchStatus]:
        if research_id in self._status:
            return self._status[research_id]
        if self._store is not None:
            row = self._store.get_run(research_id)
            if row:
                return ResearchStatus(researchId=research_id, state=row.get("state", "PLANNING"), stopReason=row.get("status"))
        return None

    def cancel(self, research_id: str) -> bool:
        event = self._cancel.get(research_id)
        if event is None:
            return False
        event.set()
        return True

    async def create_research(self, request: ResearchRequest) -> tuple[WebResearchMandate, ResearchPlan]:
        """Classify + plan + persist a research mandate (no retrieval yet)."""
        return self.create_research_sync(request)

    def create_research_sync(self, request: ResearchRequest) -> tuple[WebResearchMandate, ResearchPlan]:
        """Synchronous classify + plan + persist. No await points, so a background
        caller can persist the mandate BEFORE scheduling the run — guaranteeing the
        research id is observable (via `research_status`) the moment it is returned."""
        research_id = _research_id(request.question)
        intent = classify_intent(
            request.question,
            explicit_intent=request.intent,
            point_in_time=request.pointInTime,
        )
        depth = request.depth or intent.depth
        entity = resolve_entity(request.question)
        plan = plan_research(
            PlanInput(
                researchId=research_id,
                question=request.question,
                intent=intent.intent,
                depth=depth,
                entityHints=[entity.name] if entity else None,
            )
        )
        mandate = WebResearchMandate(
            researchId=research_id,
            question=request.question,
            objective=request.question,
            intent=intent.intent,
            depth=depth,
            subQuestions=plan.subQuestions,
            sourceTypes=(request.sourceTypes or intent.sourceTypes),
            freshness=request.freshness or intent.freshness,
            pointInTime=request.pointInTime,
            minSources=request.minSources,
            maxSources=request.maxSources,
            primarySourcesRequired=request.primarySourcesRequired or intent.primaryRequired,
            crossValidationRequired=request.crossValidationRequired or intent.crossValidationRequired,
            citationsRequired=request.citationsRequired,
            budget=_budget_dict(request),
            stoppingCriteria=_stopping_criteria(request),
        )
        if self._store is not None:
            self._store.save_run(
                {
                    "researchId": research_id,
                    "question": request.question,
                    "objective": mandate.objective,
                    "intent": mandate.intent.value,
                    "depth": mandate.depth.value,
                    "state": "PLANNING",
                    "pointInTime": mandate.pointInTime,
                    "freshness": mandate.freshness,
                    "mandate": mandate.model_dump(),
                    "plan": plan.model_dump(),
                }
            )
        self._cancel[research_id] = asyncio.Event()
        self._status[research_id] = ResearchStatus(
            researchId=research_id,
            state="PLANNING",
            questionsTotal=len(plan.subQuestions),
        )
        _prune_runs()
        return mandate, plan

    async def execute_research(self, mandate: WebResearchMandate, plan: ResearchPlan) -> EngineResult:
        """Run the full pipeline for a mandate. Bounded, cancellable, resumable."""
        research_id = mandate.researchId
        # Honor a cancellation requested before this execution (create → cancel →
        # execute). `continue_research`/`update_research` explicitly CLEAR the event
        # first so a resume after a cancel is not instantly cancelled again.
        cancel = self._cancel.setdefault(research_id, asyncio.Event())
        status = self._status.setdefault(research_id, ResearchStatus(researchId=research_id))
        # Reset the observable state for this (re)execution.
        status.state = "SEARCHING"
        status.errors = []
        started = time.monotonic()
        errors: list[str] = []

        await self._set_state(status, "SEARCHING")

        # ── Search (concurrent, bounded, budget-aware) ────────────────────────────
        # Independent sub-question queries run in PARALLEL (bounded), not one after
        # another: the planner already produced non-overlapping queries, and each
        # is an independent provider call. Results are merged deterministically in
        # query order, so the evidence set does not depend on completion order.
        raw_results: list[dict[str, Any]] = []
        search_diagnostics: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        queries = plan.queries[: max(1, mandate.budget.get("maxQueries", 12))]
        search_sem = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
        cost = CostLedger()
        max_cost = float(mandate.budget.get("maxCost", 1.0) or 0.0)

        async def _search_one(query: str) -> list[dict[str, Any]]:
            if cancel.is_set() or time.monotonic() - started > mandate.budget.get("maxSeconds", 120.0):
                return []
            async with search_sem:
                try:
                    response = await self._registry.search(
                        query,
                        kind="web",
                        limit=8,
                        preference=mandate.budget.get("preferredProvider"),
                    )
                except Exception as exc:  # noqa: BLE001 - a provider failure is data
                    errors.append(f"search {query!r} failed: {exc}")
                    return []
                # Record an HONEST estimated cost per provider (unknown ≠ 0).
                cost.record(response.provider or "", kind="query")
                search_diagnostics.extend(response.diagnostics or [])
                await self._emit("webresearch.web_search", {"query": query, "results": len(response.results), "provider": response.provider, "status": response.status})
                return [r.model_dump() for r in response.results]

        batches = await asyncio.gather(*[_search_one(q) for q in queries], return_exceptions=True)
        for batch in batches:
            if isinstance(batch, Exception):
                errors.append(f"search batch failed: {batch}")
                continue
            for item in batch:
                url = item.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                raw_results.append(item)

        status.sourceCount = len(raw_results)

        # A cancel observed before or during search stops the run here, honestly.
        if cancel.is_set():
            return await self._finish_cancelled(mandate, plan, status, raw_results)

        # ── Extract (concurrent, bounded) ──────────────────────────────────────────
        await self._set_state(status, "EXTRACTING")
        evidence: list[Evidence] = []
        fetch_budget = mandate.budget.get("maxFetches", 12)
        # Enforce the cost budget: stop before extraction when the estimated spend
        # (only when EVERY used provider was priced) has reached maxCost. An
        # unpriced provider cannot be enforced — we disclose it, never block on a
        # number we do not actually know.
        if max_cost > 0 and cost.exact and cost.total >= max_cost:
            await self._emit("webresearch.budget_stop", {"reason": "maxCost", "estimatedCost": cost.total})
            errors.append(f"stopped: estimated cost {cost.total:.4f} reached budget {max_cost:.4f}")
            candidates: list[dict[str, Any]] = []
        else:
            candidates = raw_results[: max(0, min(fetch_budget, mandate.maxSources * 2))]
        fetches = 0
        sem = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

        async def _one(item: dict[str, Any]) -> Optional[Evidence]:
            nonlocal fetches
            async with sem:
                if cancel.is_set():
                    return None
                fetches += 1
                result = await fetch(item["url"], bridge=self._bridge)
                # A JavaScript-only shell, a parse/unsupported document or a
                # paywall/login wall is not a dead end: escalate to the existing
                # browser runtime (credentialed when configured) and re-extract.
                # A missing browser/credentials is an honest failure, never a
                # fabrication.
                category = _diagnostic_category(result)
                if not result.ok and category in {"javascript_only", "parse_failure", "unsupported_document", "paywalled"}:
                    outcome = await browser_extract(item["url"])
                    await self._emit(
                        "webresearch.escalation",
                        {"url": item["url"], "category": category, "ok": outcome.ok, "reason": outcome.reason},
                    )
                    if outcome.ok and outcome.text.strip():
                        result = FetchResult(
                            ok=True,
                            url=outcome.url or item["url"],
                            text=outcome.text,
                            title=outcome.title,
                            status="OK",
                            extraction="browser",
                        )
                if not result.ok:
                    await self._emit("webresearch.page_fetch_failed", {"url": item["url"], "error": result.error})
                    return None
                ev = fetch_to_evidence(
                    result,
                    entity_hint=mandate.question,
                    published_at=item.get("publishedAt"),
                )
                if ev is not None and isinstance(ev.provenance, dict):
                    ev.provenance["metric"] = None
                return ev

        fetched = await asyncio.gather(*[_one(item) for item in candidates], return_exceptions=True)
        for item in fetched:
            if isinstance(item, Evidence):
                evidence.append(item)

        status.evidenceCount = len(evidence)
        await self._emit("webresearch.extracted", {"count": len(evidence), "attempted": fetches})

        # ── Normalize + freshness / point-in-time ───────────────────────────────────
        await self._set_state(status, "NORMALIZING")
        # Deterministic structured enrichment: the first unambiguous financial
        # metric on a page becomes a structured value + period, so the comparison,
        # conflict and claim layers have real numbers to work on. Never guessed.
        for ev in evidence:
            enrichment = enrich_structured(ev.rawText)
            if enrichment:
                ev.structuredValue = enrichment["value"]
                ev.unit = enrichment.get("unit")
                ev.period = enrichment.get("period")
                if isinstance(ev.provenance, dict):
                    ev.provenance["metric"] = enrichment["metric"]
                    ev.provenance["sourceSpan"] = enrichment.get("span")
                    ev.claimText = enrichment["metric"]

        admissible, rejections = filter_admissible(
            evidence,
            as_of=mandate.pointInTime,
            freshness=mandate.freshness,
        )

        # ── News dedup (source families) ─────────────────────────────────────────────
        news_rows = [
            {"url": e.sourceUrl, "title": e.provenance.get("title") if isinstance(e.provenance, dict) else None, "text": e.rawText}
            for e in admissible
        ]
        deduped_rows, families = dedupe_news(news_rows)
        syndicated_urls = {r["url"] for r in deduped_rows if r.get("syndicated")}

        # ── Source ranking ───────────────────────────────────────────────────────────
        await self._set_state(status, "VALIDATING")
        sources: list[dict[str, Any]] = []
        entity = resolve_entity(mandate.question)
        entity_id = entity.entityId if entity else None
        for ev in admissible:
            if entity_id and not ev.entityId:
                ev.entityId = entity_id
            source = make_source(ev.sourceUrl, title=(ev.provenance.get("title") if isinstance(ev.provenance, dict) else None), published_at=ev.publishedAt, content_hash_value=ev.contentHash)
            ranking = rank_source(
                source,
                research_type=_research_type(mandate),
                relevance=1.0,
                published_at=ev.publishedAt,
                as_of=mandate.pointInTime,
            )
            row = {
                **source.model_dump(),
                "ranking": ranking["score"],
                "components": ranking["components"],
                "syndicated": ev.sourceUrl in syndicated_urls,
            }
            sources.append(row)
            if self._store is not None:
                self._store.save_source(row, research_id=research_id, ranking=ranking["score"])
                self._store.save_evidence(ev.model_dump(), research_id=research_id)

        # Independent source count excludes syndicated copies.
        independent_count = sum(1 for s in sources if not s["syndicated"])
        status.sourceCount = independent_count

        # ── Conflicts ────────────────────────────────────────────────────────────────
        await self._set_state(status, "COMPARING")
        # Build per-metric evidence: structured facts are produced by the tool layer,
        # so here we only compare evidence that already carries a structured value.
        conflicts = detect_conflicts(admissible, research_id=research_id)
        for c in conflicts:
            if self._store is not None:
                self._store.save_conflict(research_id, {**c.model_dump(), "id": f"{research_id}_conf_{len(self._store.list_conflicts(research_id)) + 1}"})
        status.conflictCount = len(conflicts)
        status.unresolvedConflicts = sum(1 for c in conflicts if c.status == "UNRESOLVED")

        # ── Deterministic calculations ──────────────────────────────────────────────────
        # A model is never the authority on a metric. Where two reported periods for
        # the same metric are available, the engine computes the change in pure
        # Python (reusing `research.calculations`) and records a CALCULATION claim.
        calculations = _calculations_for(admissible)

        # ── Claim verification + citations ─────────────────────────────────────────────
        await self._set_state(status, "VERIFYING")
        evidence_by_id = {e.evidenceId: e for e in admissible}
        claims = self._build_claims(admissible, conflicts, mandate, evidence_by_id)
        claims.extend(_calculation_claims(calculations))
        for idx, claim in enumerate(claims):
            claim.id = claim.id or f"{research_id}_claim_{idx}"
            claim_dict = {
                "id": claim.id,
                "text": claim.text,
                "kind": claim.kind,
                "status": claim.status,
                "confidence": claim.confidence,
                "issues": claim.issues,
            }
            if self._store is not None:
                self._store.save_claim(research_id, claim_dict)
                for eid in claim.evidenceIds:
                    self._store.link_claim_evidence(claim.id, eid)
                self._store.save_validation(research_id, claim.id, claim.status, claim.issues)
        status.claimCount = len(claims)

        citations = build_citations(claims, evidence_by_id, research_id=research_id)
        citation_dicts = [c.model_dump() for c in citations]
        for c in citations:
            if self._store is not None:
                self._store.save_citation(research_id, c.model_dump())
        status.citationCount = len(citations)

        citation_report = validate_citations(
            claims,
            citations,
            evidence_by_id,
            as_of=mandate.pointInTime,
            freshness=mandate.freshness,
            require_citations=mandate.citationsRequired,
        )

        # ── Coverage + stopping ─────────────────────────────────────────────────────────
        coverage = _build_coverage(mandate, admissible, conflicts, independent_count, citation_report)

        # ── Research-quality score (internal; explainable, never user-facing truth) ─────
        quality = compute_quality(
            coverage=coverage,
            sources=sources,
            evidence=admissible,
            claims=claims,
            conflicts=conflicts,
            citation_report=citation_report,
            freshness=mandate.freshness,
        )
        coverage["quality"] = quality
        # Honest cost accounting for this run (unknown prices ⇒ a floor, flagged).
        coverage["cost"] = cost.snapshot()

        # ── Synthesis (deterministic; model optional at the tool layer) ─────────────────
        await self._set_state(status, "SYNTHESIZING")
        answer = _synthesize(mandate, sources, claims, conflicts, coverage, rejections, citation_report)

        stop_reason = _stop_reason(coverage, mandate)
        final_state: ResearchState = "COMPLETED" if coverage["status"] == "COMPLETE" else ("PARTIAL" if admissible else "FAILED")
        status.state = final_state
        status.progress = 1.0
        status.stopReason = stop_reason
        status.errors = errors
        status.questionsAnswered = coverage.get("answeredQuestions", 0)

        # ── Entity / knowledge graph (deterministic, evidence-anchored) ─────────────
        graph_entities, graph_relations = build_graph(admissible)
        entity_dicts = [e.to_dict() for e in graph_entities]
        relation_dicts = [r.to_dict() for r in graph_relations]

        snapshot_id = None
        if self._store is not None:
            self._store.save_run(
                {
                    "researchId": research_id,
                    "question": mandate.question,
                    "state": final_state,
                    "status": stop_reason,
                    "mandate": mandate.model_dump(),
                    "plan": plan.model_dump(),
                }
            )
            for ent in entity_dicts:
                self._store.save_entity(ent, research_id=research_id)
            for rel in relation_dicts:
                self._store.save_relation(rel, research_id=research_id)
            snapshot_id = self._store.create_snapshot(
                research_id,
                {
                    "mandate": mandate.model_dump(),
                    "plan": plan.model_dump(),
                    "sources": sources,
                    "evidence": [e.model_dump() for e in admissible],
                    "claims": [c.model_dump() for c in claims],
                    "citations": citation_dicts,
                    "conflicts": [c.model_dump() for c in conflicts],
                    "coverage": coverage,
                    "rejections": rejections,
                    "entities": entity_dicts,
                    "relations": relation_dicts,
                },
            )
        await self._emit("webresearch.completed", {"researchId": research_id, "state": final_state, "coverage": coverage["status"]})

        return EngineResult(
            researchId=research_id,
            status=status,
            mandate=mandate,
            plan=plan,
            evidence=admissible,
            sources=sources,
            claims=claims,
            citations=citation_dicts,
            conflicts=conflicts,
            coverage=coverage,
            rejections=rejections,
            families=families,
            calculations=calculations,
            answer=answer,
            snapshotId=snapshot_id,
            entities=entity_dicts,
            relations=relation_dicts,
        )

    async def run(self, request: ResearchRequest) -> EngineResult:
        """Convenience: create + execute in one call (synchronous research)."""
        mandate, plan = await self.create_research(request)
        return await self.execute_research(mandate, plan)

    async def continue_research(self, research_id: str) -> Optional[EngineResult]:
        """Resume a run that was partial or cancelled, using its persisted state."""
        if self._store is None:
            return None
        row = self._store.get_run(research_id)
        if row is None:
            return None
        mandate = WebResearchMandate(**(row.get("mandate") or {}))
        plan = ResearchPlan(**(row.get("plan") or {}))
        # Starting a resume supersedes a prior cancellation.
        event = self._cancel.get(research_id)
        if event is not None:
            event.clear()
        return await self.execute_research(mandate, plan)

    async def update_research(self, research_id: str, *, refresh: bool = True) -> Optional[EngineResult]:
        """Incremental research: re-run and keep history via a new snapshot.

        NON-DESTRUCTIVE. A prior snapshot (the previous version of the question)
        is preserved verbatim; the new run appends a NEW snapshot. Evidence that a
        changed source SUPERSEDS is recorded in the EvidenceStore (idempotent
        upsert by content-derived id), and the delta between the last snapshot and
        the new one is computed and returned so a caller can report what changed.

        We deliberately do NOT delete prior evidence: the snapshot chain is the
        audit trail, and deleting rows would destroy the ability to reconstruct
        what Eclipse knew at an earlier time.
        """
        if self._store is None:
            return None
        row = self._store.get_run(research_id)
        if row is None:
            return None
        mandate = WebResearchMandate(**(row.get("mandate") or {}))
        plan = ResearchPlan(**(row.get("plan") or {}))
        previous = self._store.get_snapshot(research_id)
        # Starting an update supersedes a prior cancellation.
        event = self._cancel.get(research_id)
        if event is not None:
            event.clear()
        result = await self.execute_research(mandate, plan)
        if previous is not None:
            result.delta = _snapshot_delta(previous.get("payload") or {}, result)
        return result

    # ── internals ────────────────────────────────────────────────────────────────

    def _build_claims(
        self,
        evidence: list[Evidence],
        conflicts: list[SourceConflict],
        mandate: WebResearchMandate,
        evidence_by_id: dict[str, Evidence],
    ) -> list[Claim]:
        """Deterministic claims from retrieved evidence, then verified.

        A web page that has been fetched and segmented yields one FACT claim per
        material paragraph (bounded); a page carrying a structured value yields a
        FACT claim with that value. Every claim is then verified deterministically.
        """
        claims: list[Claim] = []
        for ev in evidence[:20]:
            snippet = _first_material_sentence(ev.rawText)
            if not snippet:
                continue
            # Untrusted pages that try to instruct the agent do not get laundered
            # into a "finding". The content is still preserved as evidence, but it
            # does not become a claim the answer presents.
            if _has_injection(snippet) or _has_injection(ev.rawText):
                claims.append(
                    Claim(
                        id=None,
                        text="",
                        kind="UNCERTAINTY",
                        evidenceIds=[ev.evidenceId],
                        status="UNSUPPORTED",
                        confidence=0.0,
                        issues=["page content contained instruction-like text and was treated as untrusted data, not a finding"],
                    )
                )
                continue
            claim = Claim(
                text=snippet,
                kind="FACT",
                evidenceIds=[ev.evidenceId],
            )
            claims.append(verify_claim(claim, evidence_by_id, conflicts=conflicts, as_of=mandate.pointInTime, freshness=mandate.freshness))
        return [c for c in claims if c.text or c.issues]

    async def _set_state(self, status: ResearchStatus, state: ResearchState) -> None:
        status.state = state
        if self._store is not None:
            # Persist the observable state on every transition so a background run
            # started in one turn can be polled (research_status) from another.
            try:
                row = self._store.get_run(status.researchId)
                if row is not None:
                    self._store.save_run({**row, "state": state})
            except Exception:  # noqa: BLE001 - persistence must not break research
                pass
        await self._emit("webresearch.state", {"researchId": status.researchId, "state": state})

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._emitter is None:
            return
        try:
            await self._emitter.emit(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry must never break research
            pass

    async def _finish_cancelled(
        self,
        mandate: WebResearchMandate,
        plan: ResearchPlan,
        status: ResearchStatus,
        raw_results: list[dict[str, Any]],
    ) -> EngineResult:
        status.state = "CANCELLED"
        status.stopReason = "cancelled_by_operator"
        if self._store is not None:
            self._store.save_run(
                {"researchId": mandate.researchId, "question": mandate.question, "state": "CANCELLED", "status": "cancelled_by_operator", "mandate": mandate.model_dump(), "plan": plan.model_dump()}
            )
        await self._emit("webresearch.cancelled", {"researchId": mandate.researchId})
        return EngineResult(researchId=mandate.researchId, status=status, mandate=mandate, plan=plan)


# ── pure helpers ────────────────────────────────────────────────────────────────

# Bound the raw text returned to the model and to the HTTP surface. The
# EvidenceStore keeps the FULL text; only the tool/router payload is trimmed.
_PUBLIC_RAW_CHARS = 8_000


def _research_id(question: str) -> str:
    import hashlib
    import re
    import time as _t

    slug = re.sub(r"[^a-z0-9]+", "_", (question or "research").lower())[:40].strip("_")
    return f"wr_{slug}_{hashlib.sha256((question + str(_t.time())).encode()).hexdigest()[:8]}"


def _evidence_public(ev: Evidence) -> dict[str, Any]:
    """A model/UI-safe evidence view: full provenance, bounded raw text.

    The stored record keeps the complete `rawText`; this view trims it so a deep
    run cannot blow the tool-result bound or an API response.
    """
    data = ev.model_dump()
    raw = data.get("rawText") or ""
    if len(raw) > _PUBLIC_RAW_CHARS:
        data["rawText"] = raw[:_PUBLIC_RAW_CHARS]
        data["rawTextTruncated"] = True
        data["rawTextChars"] = len(raw)
    return data


def _snapshot_delta(previous: dict[str, Any], result: EngineResult) -> dict[str, Any]:
    """What changed between the previous snapshot and the new run.

    Compares source URLs and their content hashes so a caller can report new,
    changed and dropped sources plus newly-added evidence ids — without deleting
    any prior record.
    """
    prev_sources = {s.get("canonicalUrl"): s.get("contentHash") for s in previous.get("sources") or []}
    new_sources = {s.get("canonicalUrl"): s.get("contentHash") for s in result.sources}
    added = [url for url in new_sources if url not in prev_sources]
    dropped = [url for url in prev_sources if url not in new_sources]
    changed = [
        url for url in new_sources
        if url in prev_sources and new_sources[url] != prev_sources[url]
    ]
    prev_evidence = {e.get("evidenceId") for e in previous.get("evidence") or []}
    new_evidence = {e.evidenceId for e in result.evidence}
    return {
        "sourcesAdded": added,
        "sourcesDropped": dropped,
        "sourcesChanged": changed,
        "evidenceAdded": sorted(new_evidence - prev_evidence),
        "evidenceRemoved": sorted(prev_evidence - new_evidence),
        "snapshotId": result.snapshotId,
    }


def _budget_dict(request: ResearchRequest) -> dict[str, Any]:
    return {
        "maxQueries": request.maxQueries,
        "maxFetches": request.maxSources * 2,
        "maxSources": request.maxSources,
        "maxSeconds": request.maxTimeSeconds,
        "maxCost": request.maxCost,
    }


def _stopping_criteria(request: ResearchRequest) -> list[str]:
    criteria = [
        f"minimum {request.minSources} independent sources",
        "all required sub-questions answered",
        "material claims supported by cited evidence",
        "major conflicts resolved or documented",
    ]
    if request.primarySourcesRequired:
        criteria.append("primary sources checked where required")
    if request.pointInTime:
        criteria.append("no evidence known after the point-in-time cutoff")
    criteria.append("budget respected")
    return criteria


def _research_type(mandate: WebResearchMandate) -> str:
    intent = mandate.intent.value
    if intent in ("financial_research", "market_research"):
        return "financial"
    if intent in ("news", "current_event"):
        return "news"
    if intent == "academic_research":
        return "academic"
    return "default"


def _first_material_sentence(text: str, *, min_chars: int = 40, max_chars: int = 240) -> str:
    import re

    if not text:
        return ""
    # Skip markdown headings and short boilerplate.
    for chunk in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        cleaned = chunk.strip()
        if len(cleaned) >= min_chars:
            return cleaned[:max_chars]
    return ""


def _has_injection(text: str) -> bool:
    """True when text carries instruction-like content that must not become a claim."""
    try:
        from .web_security import get_boundary

        return get_boundary().assess(text).suspicious
    except Exception:  # noqa: BLE001
        return False


def _calculations_for(evidence: list[Evidence]) -> list[Any]:
    """Deterministic derived metrics from structured evidence, reusing Phase-4 calcs.

    Only ever computes from values the engine extracted with provenance. A
    calculation that cannot be performed honestly is dropped (never fabricated).
    """
    import re

    # Group structured observations by metric; a metric needs two distinct periods.
    by_metric: dict[str, list[Evidence]] = {}
    for ev in evidence:
        if ev.structuredValue is None or not isinstance(ev.provenance, dict):
            continue
        metric = str(ev.provenance.get("metric") or "").strip()
        if metric:
            by_metric.setdefault(metric, []).append(ev)

    calculations: list[Any] = []
    for metric, items in by_metric.items():
        ordered = sorted(
            (e for e in items if e.period),
            key=lambda e: _year_of(e.period),
        )
        distinct_periods = {e.period for e in ordered}
        if len(ordered) < 2 or len(distinct_periods) < 2:
            continue
        first, last = ordered[0], ordered[-1]
        try:
            from .calculations import period_change

            observations = [
                {"date": e.period, "value": _as_float(e.structuredValue)}
                for e in (first, last)
            ]
            result = period_change(
                _as_float(first.structuredValue),
                _as_float(last.structuredValue),
                observations=observations,
            )
            result.inputEvidenceIds = [first.evidenceId, last.evidenceId]
            result.identity = last.entityId
            calculations.append(result)
        except Exception:  # noqa: BLE001 - an impossible calculation is dropped
            continue
    return calculations


def _calculation_claims(calculations: list[Any]) -> list[Claim]:
    claims: list[Claim] = []
    for calc in calculations:
        value = getattr(calc, "value", None)
        claims.append(
            Claim(
                text=f"{getattr(calc, 'metric', 'change')} changed by {value:.2f}% (computed deterministically)".strip()
                if value is not None
                else f"{getattr(calc, 'metric', 'change')} could not be computed",
                kind="CALCULATION",
                evidenceIds=list(getattr(calc, "inputEvidenceIds", []) or []),
                calculationId=getattr(calc, "calculationId", None),
                status="CALCULATED",
                confidence=0.95,
            )
        )
    return claims


def _as_float(value: Any) -> float:
    return float(str(value).replace(",", "").replace("$", "").strip())


def _year_of(period: Optional[str]) -> int:
    import re

    match = re.search(r"((?:19|20)\d{2})", period or "")
    return int(match.group(1)) if match else 0


def _build_coverage(
    mandate: WebResearchMandate,
    evidence: list[Evidence],
    conflicts: list[SourceConflict],
    independent_sources: int,
    citation_report: dict[str, Any],
) -> dict[str, Any]:
    primary = sum(
        1 for e in evidence
        if getattr(e.sourceType, "value", e.sourceType) in (
            "official_filing", "government", "regulator", "investor_relations"
        )
    )
    material_conflicts = [c for c in conflicts if c.material and c.status == "UNRESOLVED"]
    answered, coverage_method, question_scores = _answered_questions(mandate, evidence)
    unmet: list[str] = []
    if independent_sources < mandate.minSources:
        unmet.append(f"only {independent_sources} independent sources (need {mandate.minSources})")
    if mandate.primarySourcesRequired and primary == 0:
        unmet.append("primary sources were required but none were retrieved")
    if mandate.crossValidationRequired and independent_sources < 2:
        unmet.append("cross-validation was required but only one independent source was retrieved")
    if material_conflicts:
        unmet.append(f"{len(material_conflicts)} unresolved material conflict(s)")
    if mandate.citationsRequired and not citation_report["ok"]:
        unmet.append("citation validation failed")
    coverage_ratio = min(1.0, independent_sources / max(1, mandate.minSources))
    if not unmet:
        status = "COMPLETE"
    elif evidence:
        status = "SUFFICIENT" if independent_sources >= mandate.minSources else "NEEDS_MORE_RESEARCH"
    else:
        status = "NEEDS_MORE_RESEARCH"
    return {
        "status": status,
        "independentSources": independent_sources,
        "primarySources": primary,
        "evidenceCount": len(evidence),
        "answeredQuestions": answered,
        "questionsTotal": len(mandate.subQuestions),
        "coverageMethod": coverage_method,
        "questionScores": question_scores,
        "coverage": round(coverage_ratio, 4),
        "sourceCoverage": round(coverage_ratio, 4),
        "unmet": unmet,
        "citationCoverage": citation_report["coverage"],
        "conflicts": len(conflicts),
        "unresolvedConflicts": len(material_conflicts),
        "isCompletionClaimHonest": bool(not unmet),
    }


# ── Coverage: which sub-questions have corroborating evidence ────────────────
# The layered scorer (semantic → idf → keyword) lives in `web_coverage`; it is a
# COVERAGE signal, never a correctness claim. `coverageMethod` discloses the layer.




def _stop_reason(coverage: dict[str, Any], mandate: WebResearchMandate) -> str:
    if coverage["status"] == "COMPLETE":
        return "stopping_criteria_met"
    if coverage["independentSources"] == 0:
        return "provider_routes_unavailable"
    return "unresolved_requirements_remain"


def _synthesize(
    mandate: WebResearchMandate,
    sources: list[dict[str, Any]],
    claims: list[Claim],
    conflicts: list[SourceConflict],
    coverage: dict[str, Any],
    rejections: list[dict[str, Any]],
    citation_report: dict[str, Any],
) -> str:
    """Deterministic answer. Distinguishes FACT, CALCULATION, INFERENCE, UNCERTAINTY.

    The model is never the source of truth: this text is assembled from verified
    claims, disclosed conflicts and explicit gaps. It never claims completeness the
    coverage gate did not establish.
    """
    lines: list[str] = []
    supported = [c for c in claims if c.status in ("SUPPORTED", "CALCULATED")]
    partial = [c for c in claims if c.status in ("PARTIALLY_SUPPORTED", "AMBIGUOUS")]
    contradicted = [c for c in claims if c.status in ("CONTRADICTED", "OUTDATED", "UNSUPPORTED")]

    lines.append(f"Research: {mandate.objective}")
    lines.append(
        f"Coverage: {coverage['status']} — {coverage['independentSources']} independent source(s), "
        f"{coverage['evidenceCount']} evidence item(s), {coverage['primarySources']} primary."
    )
    if supported:
        lines.append("")
        lines.append("Findings (evidence-backed):")
        lines.extend(f"- {c.text}" for c in supported[:12])
    if partial:
        lines.append("")
        lines.append("Partially supported (verify before relying on):")
        lines.extend(f"- {c.text}" for c in partial[:8])
    if contradicted:
        lines.append("")
        lines.append("Not established / conflicting (removed from findings):")
        for c in contradicted[:8]:
            reason = "; ".join(c.issues[:2]) if c.issues else c.status.lower()
            lines.append(f"- [{c.status}] {reason}")
    if conflicts:
        lines.append("")
        lines.append("Conflicts:")
        for conflict in conflicts[:6]:
            detail = conflict.explanation or "unresolved — sources disagree"
            lines.append(f"- {conflict.metric} {conflict.period or ''}: {conflict.status} ({detail})")
    if coverage["unmet"]:
        lines.append("")
        lines.append("Gaps (research incomplete):")
        lines.extend(f"- {item}" for item in coverage["unmet"])
    if rejections:
        lines.append("")
        lines.append(f"Excluded {len(rejections)} item(s) (point-in-time/freshness):")
        lines.extend(f"- {r['reason']}" for r in rejections[:5])
    if not citation_report["ok"] and citation_report["issues"]:
        lines.append("")
        lines.append("Citation issues:")
        lines.extend(f"- {issue}" for issue in citation_report["issues"][:5])
    if not lines:
        lines.append("No usable evidence was retrieved, so no factual answer can be established.")
    return "\n".join(lines)


async def run_web_research(
    request: ResearchRequest,
    *,
    bridge: Any,
    store: Any = None,
    emitter: Any = None,
) -> EngineResult:
    """Module-level convenience entry point used by tools and routes."""
    engine = ResearchEngine(bridge=bridge, store=store, emitter=emitter)
    return await engine.run(request)


__all__ = [
    "ResearchEngine",
    "EngineResult",
    "run_web_research",
    "MAX_CONCURRENT_FETCHES",
    "MAX_CONCURRENT_SEARCHES",
    "request_cancel",
    "run_status",
]
