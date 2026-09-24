"""Live-chat integration for the research flow (Phase 4, Workstream 2).

`maybe_run_research` is called by `execute_run` BEFORE the ordinary agent graph.
For a supported, unambiguous `financial_comparison` it:

  1. classifies the objective into a mandate,
  2. retrieves every required leg through the existing retrieval layer,
  3. computes deterministic coverage,
  4. asks the configured model (same `ModelSettings`, no new adapter) to
     synthesize claims from the bounded evidence packet only,
  5. deterministically validates them with at most one bounded repair round,
  6. renders only validated/qualified claims + explicit gaps,
  7. persists a receipt and returns additive `research` metadata.

For anything that is not an unambiguous supported comparison it returns None, and
the caller runs the existing Phase 1–3 path unchanged. A gated run is never
silently downgraded to an ungated model answer: if synthesis fails the run
returns an honest partial/unavailable result.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..retrieval.contract import FinancialRetrievalRequest, FinancialRetrievalResult
from .budget import ResearchBudget
from .engine import run_research
from .mandate import parse_mandate
from .synthesis import ModelSynthesizer
from .web_facts import WebFactExtractor

log = logging.getLogger("harness.research.run")


async def maybe_run_research(
    *,
    run_id: str,
    query: str,
    ticker: Optional[str],
    market: Optional[str],
    model: Any,
    retrieve: Any,
    store: Any,
    emitter: Any,
    model_settings: Any = None,
    provider: Optional[str] = None,
    bridge: Any = None,
) -> Optional[dict[str, Any]]:
    """Run the gated research flow when the request is a supported comparison.

    Returns a dict with `output`, `status`, `metadata`, `receipt`, and token usage
    when the request was routed into the gate; returns None to fall back to the
    ordinary agent graph.
    """
    mandate = parse_mandate(query, ticker=ticker, market=market)
    if not mandate.supported:
        return None

    await emitter.emit(
        "research.mandate",
        {
            "taskType": mandate.taskType,
            "legs": len(mandate.factLegs),
            "entities": [e.symbol for e in mandate.entities],
            "asOf": mandate.asOf,
        },
    )

    synthesizer = ModelSynthesizer(model)
    # The web-fact extractor is model-assisted; deterministic validation gates it.
    extractor = WebFactExtractor(model) if bridge is not None else None
    budget = ResearchBudget()
    try:
        await emitter.emit("research.started", {"legs": len(mandate.factLegs)})

        async def _retrieve(request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
            try:
                return await retrieve(request)
            except Exception as exc:  # noqa: BLE001 - a leg failure is unavailable, not fatal
                return FinancialRetrievalResult(
                    status="UNAVAILABLE",
                    objective=request.objective,
                    dataType=request.dataType,
                    instrument=request.instrument,
                    warnings=[f"retrieval failed: {exc}"],
                )

        async def _on_event(event_type: str, data: dict[str, Any]) -> None:
            await emitter.emit(event_type, data)

        outcome = await run_research(
            mandate,
            _retrieve,
            synthesize=synthesizer,
            run_id=run_id,
            provider=provider,
            model=getattr(model_settings, "model", None),
            bridge=bridge,
            extractor=extractor,
            budget=budget,
            on_event=_on_event,
        )
    except Exception as exc:  # noqa: BLE001 - a gate failure is an honest error, not a crash
        log.exception("research flow failed")
        await emitter.emit("research.failed", {"error": str(exc)})
        return {
            "output": (
                "The evidence-grounded research flow could not complete honestly. "
                f"No answer was fabricated. ({exc})"
            ),
            "status": "rejected",
            "metadata": None,
            "receipt": None,
            "persistenceError": None,
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "prose": None,
            "coverage": None,
            "validation": None,
        }

    for coverage_leg in outcome.coverage.legs:
        await emitter.emit(
            "research.coverage",
            {"legId": coverage_leg.legId, "status": coverage_leg.status, "metric": coverage_leg.metric},
        )
    if outcome.validation is not None:
        await emitter.emit(
            "research.validation",
            {
                "status": outcome.validation.status,
                "claims": len(outcome.validation.claims),
                "repaired": outcome.validation.repaired,
            },
        )

    # Persist the receipt. Persistence failure is exposed, never hidden.
    persistence_error: Optional[str] = None
    if outcome.receipt is not None:
        try:
            store.save_receipt(outcome.receipt.model_dump())
        except Exception as exc:  # noqa: BLE001
            log.exception("research receipt persistence failed")
            persistence_error = str(exc)
            await emitter.emit("research.receipt_failed", {"error": str(exc)})

    # User-facing answer: only validated/qualified claims plus explicit gaps.
    output = _render_answer(outcome)
    await emitter.emit("research.completed", {"status": outcome.status})

    usage = {
        "promptTokens": synthesizer.usage["promptTokens"],
        "completionTokens": synthesizer.usage["completionTokens"],
    }
    return {
        "output": output,
        "status": outcome.status,
        "metadata": outcome.metadata.model_dump() if outcome.metadata else None,
        "receipt": outcome.receipt.model_dump() if outcome.receipt else None,
        "persistenceError": persistence_error,
        "usage": usage,
        "prose": outcome.prose,
        "coverage": outcome.coverage.model_dump(),
        "validation": outcome.validation.model_dump() if outcome.validation else None,
        "escalation": outcome.escalation,
        "budget": outcome.budget,
        "legStatus": outcome.legStatus,
        "stopReason": outcome.stopReason,
        # Structured provenance for the chat UI's separate Sources/Limitations
        # area. Kept out of the prose so the answer stays clean and no long URL
        # or raw source label sits inside a sentence.
        "failedRoutes": _failed_routes(outcome),
        "stopReasonText": _stop_reason_text(outcome.stopReason),
        # WS6/WS7: comparisons the deterministic gate blocked, with the exact
        # reason. The answer presents each verified fact and names the blocked
        # change rather than emitting a misleading percentage.
        "blockedComparisons": (outcome.comparability.to_dict().get("blocked") if outcome.comparability else None),
    }


# Human-readable label per stop reason, so the answer explains why it ended.
_STOP_REASON_TEXT = {
    "all_required_legs_resolved": "every required fact was resolved from verified evidence",
    "budget_exhausted": "the research budget was exhausted before every fact was resolved",
    "provider_routes_unavailable": "every available source route failed or was unavailable",
    "unresolved_facts_remain": "some required facts remain unresolved",
}


def _stop_reason_text(stop_reason: Optional[str]) -> Optional[str]:
    """Human-readable stop reason (None when the run did not record one)."""
    if not stop_reason:
        return None
    return _STOP_REASON_TEXT.get(stop_reason, stop_reason)


def _render_answer(outcome: Any) -> str:
    """Render the answer PROSE — validated claims PLUS useful verified partials.

    The validated answer text is the base. When a run is partial, every fact the
    coverage gate marked `covered`/`qualified` is still presented (WS7) so a
    single missing optional step never hides verified facts. Blocked comparisons
    are named with their exact reason. Citations/limitations/failed routes stay in
    STRUCTURED fields for the chat UI's Sources area.
    """
    prose = (outcome.prose or "").strip()

    parts: list[str] = []
    if prose:
        parts.append(prose)

    # WS7: present every independently verified covered/qualified leg. This is
    # deterministic — it copies values already established by the coverage gate,
    # and never invents one.
    verified_lines = _verified_fact_lines(outcome)
    if verified_lines and not _prose_mentions_verified(outcome):
        parts.append("Verified facts established from evidence:")
        parts.extend(verified_lines)

    # WS6/WS7: name each blocked comparison so the absence of a change is
    # explained, not silently omitted.
    blocked_lines = _blocked_comparison_lines(outcome)
    if blocked_lines:
        parts.append("Comparison not computed (inputs are not comparable):")
        parts.extend(blocked_lines)

    if parts:
        return "\n".join(parts).strip()
    if outcome.coverage.status == "rejected":
        return "No usable evidence was retrieved, so no factual answer can be established."
    return ""


def _verified_fact_lines(outcome: Any) -> list[str]:
    """One deterministic line per covered/qualified leg, from its evidence objects."""
    evidence = getattr(outcome, "evidence", []) or []
    by_id = {getattr(item, "id", ""): item for item in evidence}
    lines: list[str] = []
    for leg in getattr(getattr(outcome, "coverage", None), "legs", []) or []:
        if leg.status not in ("covered", "qualified"):
            continue
        rendered = False
        for evidence_id in leg.evidenceIds:
            item = by_id.get(evidence_id)
            if item is None:
                continue
            for obj in getattr(item, "objects", []) or []:
                if str(getattr(obj, "name", "")).lower() != str(leg.metric).lower():
                    continue
                value = getattr(obj, "value", None)
                if value is None:
                    continue
                currency = getattr(obj, "currency", None) or ""
                unit = getattr(obj, "unit", None) or ""
                period = getattr(obj, "period", None) or leg.period or ""
                source = getattr(getattr(item, "source", None), "source", "source")
                qualifier = " (qualified)" if leg.status == "qualified" else ""
                lines.append(
                    f"- {leg.metric} {period}: {value} {currency}{unit} — source: {source}{qualifier}"
                )
                rendered = True
                break
            if rendered:
                break
        if not rendered:
            source_hint = ", ".join(sorted(set(leg.sourceTiers))) or "verified evidence"
            lines.append(f"- {leg.metric} {leg.period or ''}: established ({source_hint})")
    return lines


def _prose_mentions_verified(outcome: Any) -> bool:
    """True when the validated prose already lists supported claims.

    Avoids duplicating the fact list when synthesis already rendered them.
    """
    validation = getattr(outcome, "validation", None)
    if validation is None:
        return False
    return any(getattr(c, "supportStatus", "") == "supported" for c in getattr(validation, "claims", []) or [])


def _blocked_comparison_lines(outcome: Any) -> list[str]:
    comparability = getattr(outcome, "comparability", None)
    if comparability is None:
        return []
    out: list[str] = []
    for blocked in comparability.blocked:
        legs = blocked.legs
        out.append(f"- {legs[0]} vs {legs[1]}: {blocked.reason}")
    return out


def _failed_routes(outcome: Any) -> list[str]:
    """Concise 'route — reason' lines for every provider attempt that failed."""
    rows: list[str] = []
    for leg in getattr(outcome, "legStatus", []) or []:
        for diagnostic in leg.get("diagnostics") or []:
            if diagnostic.get("normalizedStatus") != "failed":
                continue
            provider = diagnostic.get("provider") or "source"
            category = diagnostic.get("category") or "failure"
            detail = diagnostic.get("detail") or ""
            rows.append(f"{provider} — {category}{f': {detail}' if detail else ''}")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        if row not in seen:
            seen.add(row)
            out.append(row)
    return out


__all__ = ["maybe_run_research"]
