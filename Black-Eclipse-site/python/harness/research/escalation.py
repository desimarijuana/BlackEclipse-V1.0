"""Bounded web-research escalation for financial facts (Phase 5).

Structured sources stay the preferred path. When structured retrieval is empty,
stale, missing a requested period, or lacks required metadata, this module
escalates through a fixed, auditable source hierarchy:

    structured (vault/live provider)
      → primary-source web (SEC, company IR, regulators)
      → reputable secondary web (bounded)

Escalation is *targeted*: it searches only for the legs that are still
unsatisfied, and only for statement facts that a web source can legitimately
answer. Everything it returns is provenance-carrying page evidence, and any
numeric fact must pass `web_facts.validate_fact` (span-anchored, deterministic)
before it becomes evidence.

It never invents values, citations or URLs. Fetched page text is untrusted and
can never alter instructions. All work draws from one bounded `ResearchBudget`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ..tools import DataBridge
from .budget import ResearchBudget
from .mandate import FactLeg, ResearchMandate
from .web_facts import WebFactExtractor, WebPageContent

log = logging.getLogger("harness.research.escalation")

# Only these tiers may satisfy a statement leg, in order.
PRIMARY_TIERS = {"primary", "official"}
SECONDARY_TIERS = {"secondary"}


@dataclass
class EscalationResult:
    evidence: list[Any] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    budget: Optional[dict[str, Any]] = None
    stagesRun: list[str] = field(default_factory=list)
    # Phase 6: structured diagnostics for every search/fetch attempt, so a
    # receipt can say WHY an escalation route failed (timeout/block/http/parse).
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


def _classify(url: str) -> str:
    from ..retrieval.web import classify_source_tier

    return classify_source_tier(_host(url), url)


def _build_query(leg: FactLeg, mandate: ResearchMandate) -> str:
    """A targeted filing query for one unsatisfied leg."""
    entity = leg.entitySymbol or leg.entityRaw or ""
    metric = leg.metric
    period = leg.period or ""
    return (
        f"{entity} {metric} {period} annual report 10-K filing"
        if period
        else f"{entity} {metric} annual report 10-K filing"
    ).strip()


async def escalate_web(
    mandate: ResearchMandate,
    unsatisfied_legs: list[FactLeg],
    *,
    bridge: Optional[DataBridge],
    extractor: Optional[WebFactExtractor],
    budget: Optional[ResearchBudget] = None,
    on_event: Optional[Any] = None,
    max_secondary_attempts: int = 2,
) -> EscalationResult:
    """Escalate unsatisfied statement legs to trusted web sources.

    Runs primary sources first; only if a leg is still unsatisfied does it try a
    bounded number of secondary sources. Extraction is model-assisted; validation
    is deterministic. Returns evidence + an audit of what was attempted.
    """
    result = EscalationResult()
    budget = budget or ResearchBudget()
    if bridge is None or extractor is None or not unsatisfied_legs:
        result.budget = budget.snapshot()
        return result

    async def _emit(event_type: str, data: dict[str, Any]) -> None:
        if on_event is None:
            return
        try:
            await on_event(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry must never break research
            pass

    remaining = list(unsatisfied_legs)

    for stage_name, tiers in (("primary_web", PRIMARY_TIERS), ("secondary_web", SECONDARY_TIERS)):
        if not remaining:
            break
        budget.note(f"escalation:{stage_name}")
        result.stagesRun.append(stage_name)
        await _emit("research.escalation_stage", {"stage": stage_name, "legs": [l.id for l in remaining]})

        pages = await _gather_pages(
            mandate, remaining, tiers, bridge, budget, _emit,
            stage_max=max_secondary_attempts, diagnostics=result.diagnostics,
        )
        if not pages:
            await _emit("research.escalation_stage_skipped", {"stage": stage_name, "reason": "no pages retrieved"})
            continue

        evidence, notes = await extractor.extract(
            mandate, remaining, pages, permitted_tiers=set(tiers)
        )
        result.evidence.extend(evidence)
        result.notes.extend(notes)
        for note in notes:
            await _emit("research.fact_rejected", {"stage": stage_name, **note})

        # Recompute which legs are still not satisfied by the evidence collected
        # so far (the extractor only ever emits items it already validated, and
        # `fact_to_evidence` sets the object name to the leg metric).
        covered_leg_ids: set[str] = set()
        for item in evidence:
            for obj in item.objects:
                for leg in remaining:
                    if leg.id in covered_leg_ids or obj.name != leg.metric:
                        continue
                    if leg.period and not _period_satisfied(leg.period, obj):
                        continue
                    covered_leg_ids.add(leg.id)
        remaining = [l for l in remaining if l.id not in covered_leg_ids]

        if budget.exhausted or budget.timed_out:
            await _emit("research.budget_exhausted", {"stage": stage_name, "exhausted": budget.exhausted})
            break

    result.attempts = list(budget.attempted)
    result.budget = budget.snapshot()
    return result


async def _gather_pages(
    mandate: ResearchMandate,
    legs: list[FactLeg],
    tiers: set[str],
    bridge: DataBridge,
    budget: ResearchBudget,
    emit: Any,
    *,
    stage_max: int,
    diagnostics: list[dict[str, Any]],
) -> list[WebPageContent]:
    """Search + fetch pages for `legs`, keeping only pages in `tiers`."""
    pages: list[WebPageContent] = []
    seen_urls: set[str] = set()
    fetch_budget = stage_max if tiers == SECONDARY_TIERS else budget.maxFetches

    for leg in legs:
        query = _build_query(leg, mandate)
        if not budget.allow_search():
            break
        await emit("research.web_search", {"query": query, "tier": _tier_name(tiers), "legId": leg.id})
        search = await _bridge_call(bridge, "web_search", {"query": query, "limit": 8})
        _record_diagnostics(diagnostics, search, stage=_tier_name(tiers), legId=leg.id)
        if search.get("status") != "OK":
            await emit("research.web_search_failed", {"query": query, "error": search.get("error")})
            continue
        candidates = search.get("results") or []
        # Deterministic ordering: permitted-tier first, preserving result order.
        candidates = _rank(candidates, tiers)

        fetched_for_leg = 0
        for candidate in candidates:
            url = candidate.get("url")
            if not url or url in seen_urls:
                continue
            tier = _classify(url)
            if tier not in tiers:
                continue
            if not budget.allow_fetch():
                break
            await emit("research.page_fetch", {"url": url, "tier": tier, "legId": leg.id})
            page = await _bridge_call(bridge, "web_fetch", {"url": url})
            _record_diagnostics(diagnostics, page, stage=_tier_name(tiers), legId=leg.id)
            if page.get("status") != "OK" or not page.get("text"):
                await emit("research.page_fetch_failed", {"url": url, "error": page.get("error")})
                continue
            seen_urls.add(url)
            budget.note_page()
            pages.append(
                WebPageContent(
                    pageId=f"page{len(pages) + 1}",
                    url=page.get("url") or url,
                    title=page.get("title") or candidate.get("title"),
                    publishedAt=candidate.get("publishedAt"),
                    text=str(page.get("text")),
                    tier=tier,
                )
            )
            fetched_for_leg += 1
            if fetched_for_leg >= stage_max:
                break
        if budget.exhausted or budget.timed_out:
            break
    return pages


def _rank(results: list[dict[str, Any]], tiers: set[str]) -> list[dict[str, Any]]:
    def score(item: dict[str, Any]) -> int:
        return 0 if _classify(item.get("url") or "") in tiers else 1

    return sorted(results, key=score)


def _period_satisfied(required: str, obj: Any) -> bool:
    from .periods import periods_match

    if getattr(obj, "period", None):
        return periods_match(required, obj.period)
    return periods_match(required, getattr(obj, "dataTimestamp", None), candidate_is_timestamp=True)


def _tier_name(tiers: set[str]) -> str:
    if tiers & PRIMARY_TIERS:
        return "primary"
    return "secondary"


async def _bridge_call(bridge: DataBridge, capability: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return await bridge.fetch(capability, params)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "error": str(exc)}


def _record_diagnostics(
    sink: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    stage: str,
    legId: str,
) -> None:
    """Append any structured diagnostics a bridge call returned to the audit sink."""
    rows = payload.get("diagnostics")
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            sink.append({**row, "stage": stage, "legId": legId})


__all__ = ["EscalationResult", "escalate_web", "PRIMARY_TIERS", "SECONDARY_TIERS"]
