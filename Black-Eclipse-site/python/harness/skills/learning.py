"""Learning engine — capture reusable lessons from execution traces.

This module inspects a persisted run and MAY create an inert `LearningCandidate`.
It never creates a skill, never enables anything, and never lets a model
artifact become active. A candidate is a *reviewable observation*, not a
capability.

Candidate creation is criteria-driven and conservative:

CREATE a candidate when:
  * a failure was recovered through a reusable fallback (failure_recovery);
  * a user correction reveals a generalizable validation rule (user_correction);
  * a multi-step procedure succeeded and is plausibly reusable
    (successful_procedure);
  * a missing-data condition was resolved by a verified method
    (validation_improvement / source_selection_improvement).

DO NOT create a general skill from:
  * a single instrument-specific event;
  * an unverified factual claim;
  * a temporary data anomaly with no reusable solution;
  * a user-specific preference (that belongs in memory);
  * a model explanation with no supporting evidence.

Duplicate suppression uses a deterministic `signature` (type + normalized
problem) so the same experience never yields repeated candidates.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from ..persistence import now_iso

CandidateType = str  # failure_recovery | user_correction | successful_procedure |
#                       validation_improvement | source_selection_improvement |
#                       provider_eligibility_improvement |
#                       workflow_pattern | terminology_or_preference

_REUSABLE_MIN_STEPS = 2


def _signature(candidate_type: str, problem: str) -> str:
    normalized = re.sub(r"\s+", " ", (problem or "").strip().lower())[:400]
    digest = hashlib.sha256(f"{candidate_type}|{normalized}".encode("utf-8")).hexdigest()
    return digest[:24]


def _run_events(store: Any, run_id: str) -> list[dict[str, Any]]:
    try:
        return store.list_events(run_id)
    except Exception:  # noqa: BLE001
        return []


def _run_tools(store: Any, run_id: str) -> list[dict[str, Any]]:
    try:
        return store.list_tool_executions(run_id)
    except Exception:  # noqa: BLE001
        return []


# Markets the run touched, so a lesson NEVER generalizes one country/provider to
# all countries. Extracted from retrieval/tool text; bounded and de-duplicated.
_MARKET_TOKENS = (
    "US", "TW", "KR", "BR", "JP", "UK", "DE", "FR", "NL", "CA", "IN", "CN",
    "HK", "SG", "MY", "AU", "PK", "SA", "AE", "ZA", "MX", "TR", "ID", "TH", "VN",
)


def _infer_scope(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """The regional/provider/capability scope a lesson is supported by.

    Never "all countries". The capability and a suggested regression case are
    folded here (JSON, no schema change) so a candidate states exactly which data
    type it is about and offers a narrowly-scoped test to add on review.
    """
    markets = _markets_in(tools)
    return {
        "markets": markets,
        "capability": _infer_capability(tools),
        "regressionCase": _regression_case(tools),
        "scopeClaim": "observed markets only" if markets else "unspecified",
    }


def _diagnostic_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Structured failure diagnostics a run recorded (category + provider)."""
    out: list[dict[str, Any]] = []
    for e in events:
        if e["type"] not in ("retrieval.source_unavailable", "retrieval.source_failed", "retrieval.source_skipped", "research.page_fetch_failed", "research.web_search_failed"):
            continue
        data = e.get("data") or {}
        out.append({
            "event": e["type"],
            "provider": data.get("source") or data.get("provider"),
            "category": data.get("error") or data.get("category") or data.get("reason"),
        })
        if len(out) >= 8:
            break
    return out


# Tool name → capability, so a candidate names the data type a lesson is about
# (a lesson about quote routing must not be applied to filings, etc.).
_TOOL_CAPABILITY: dict[str, str] = {
    "market_get_quote": "live_quote",
    "market_get_ohlcv": "price_history",
    "fundamentals_get_company_profile": "fundamentals",
    "fundamentals_get_financials": "financial_statements",
    "get_capability_matrix": "capability",
    "get_coverage": "capability",
    "get_source_health": "health",
    "get_research_health": "health",
    "research_search": "web_search",
    "research_search_news": "news",
    "research_retrieve_source": "web_fetch",
    "macro_get_series": "macro_series",
}


def _infer_capability(tools: list[dict[str, Any]]) -> Optional[str]:
    """The dominant capability a run exercised, when determinable (else None)."""
    counts: dict[str, int] = {}
    for t in tools:
        cap = _TOOL_CAPABILITY.get(str(t.get("name") or ""))
        if cap:
            counts[cap] = counts.get(cap, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _markets_in(tools: list[dict[str, Any]]) -> list[str]:
    """Markets named in the run's tool text (bounded, de-duplicated)."""
    text = " ".join(str(t.get("text") or "") for t in tools).upper()
    return sorted({m for m in _MARKET_TOKENS if re.search(rf"\b{m}\b", text)})


def _regression_case(tools: list[dict[str, Any]]) -> Optional[str]:
    """A short, deterministic regression label from the observed run.

    Suggests a narrowly scoped case (e.g. a fixture for the market+capability),
    so the operator can add a targeted test rather than a broad claim. It never
    invents a fixture name beyond the markets/capability the run actually touched.
    """
    markets = _markets_in(tools)
    capability = _infer_capability(tools)
    if not markets and not capability:
        return None
    parts = []
    if markets:
        parts.append("+".join(markets[:3]))
    if capability:
        parts.append(capability)
    return f"fixture: {'_'.join(parts)} — assert route category + no fabricated value"


def analyze_run(run_id: str, store: Any) -> list[dict[str, Any]]:
    """Analyze one run and return candidate drafts (not yet persisted).

    Pure analysis: no side effects. `capture_from_run` persists the drafts.
    """
    run = store.get_run(run_id)
    if run is None:
        return []
    events = _run_events(store, run_id)
    tools = _run_tools(store, run_id)

    tool_failures = [t for t in tools if not t.get("ok")]
    tool_successes = [t for t in tools if t.get("ok")]
    validation_failures = [e for e in events if e["type"] in ("skill.validation_failed", "error")]
    event_types = {e["type"] for e in events}

    drafts: list[dict[str, Any]] = []

    # ── 1. Failure recovery: a failure occurred, then the run still completed
    #         (or a later identical tool succeeded) through a different path.
    recovered = bool(tool_failures) and run.get("status") == "completed"
    if recovered:
        failed_tools = sorted({t["name"] for t in tool_failures})
        later_success = sorted({t["name"] for t in tool_successes})
        draft = {
            "candidateType": "failure_recovery",
            "title": f"Recovery after {', '.join(failed_tools)} failure",
            "problem": f"Tool(s) {', '.join(failed_tools)} failed during the run.",
            "observedBehavior": (
                f"The run still completed using {', '.join(later_success) or 'alternative steps'}."
            ),
            "proposedLesson": "When these tools fail, prefer the alternative that worked before giving up.",
            "evidenceReferences": [
                {"kind": "tool", "name": t["name"], "error": (t.get("error") or {}).get("code")}
                for t in tool_failures
            ],
            "confidence": 0.55,
            "generalizationNotes": "Generalize only if the fallback is data-source-independent.",
            "knownLimitations": "A single recovery is not proof the fallback always works; verify before reuse.",
        }
        drafts.append(draft)

    # ── 2. Repeated failure with no recovery: a reusable validation improvement
    #         only when a validation rule is implicated (not a transient outage).
    if validation_failures and not recovered:
        draft = {
            "candidateType": "validation_improvement",
            "title": "Add a pre-flight validation guard",
            "problem": "A validation failure occurred during execution.",
            "observedBehavior": validation_failures[0]["data"].get("reason")
            or "validation failed before completion",
            "proposedLesson": "Validate the failing condition before execution to fail fast with a clear message.",
            "evidenceReferences": [{"kind": "event", "id": e["id"], "type": e["type"]} for e in validation_failures[:5]],
            "confidence": 0.4,
            "generalizationNotes": "Only generalizable if the rule is not instrument-specific.",
            "knownLimitations": "A validation failure may be a one-off bad input; do not over-generalize.",
        }
        drafts.append(draft)

    # ── 3. Successful procedure: a multi-step run completed with verified
    #         evidence and enough steps to be a reusable procedure.
    if (
        run.get("status") == "completed"
        and run.get("modelSteps", 0) >= _REUSABLE_MIN_STEPS
        and tool_successes
        and "tool.failed" not in event_types
    ):
        successful_tools = sorted({t["name"] for t in tool_successes})
        draft = {
            "candidateType": "successful_procedure",
            "title": f"Reusable procedure: {', '.join(successful_tools[:3])}",
            "problem": "A multi-step research procedure completed with no tool failures.",
            "observedBehavior": f"{run.get('modelSteps')} model steps; tools: {', '.join(successful_tools)}.",
            "proposedLesson": "This tool sequence is a candidate reusable procedure for similar objectives.",
            "proposedProcedure": [
                {"step": i + 1, "action": f"call {name}"} for i, name in enumerate(successful_tools)
            ],
            "evidenceReferences": [
                {"kind": "tool", "name": t["name"], "at": t.get("createdAt")} for t in tool_successes
            ],
            "confidence": 0.45,
            "generalizationNotes": "Reusability must be confirmed across more than one run.",
            "knownLimitations": "One successful run is weak evidence for a general skill.",
        }
        drafts.append(draft)

    # ── 4. Source-selection improvement: a source failed and another provided
    #         the data (only when the run recorded retrieval source events).
    retrieval_events = [e for e in events if e["type"].startswith("retrieval.")]
    source_failures = [e for e in retrieval_events if e["type"] in ("retrieval.source_unavailable", "retrieval.source_failed")]
    if source_failures and tool_successes:
        scope = _infer_scope(tools)
        draft = {
            "candidateType": "source_selection_improvement",
            "title": "Prefer a working source for this data type",
            "problem": "A retrieval source was unavailable.",
            "observedBehavior": "Another source satisfied the request.",
            "proposedLesson": "Record the working source preference for this data type/coverage.",
            "evidenceReferences": [{"kind": "event", "id": e["id"], "type": e["type"]} for e in source_failures[:5]],
            "diagnostics": _diagnostic_summary(events),
            "scope": scope,
            "capability": _infer_capability(tools),
            "regressionCase": _regression_case(tools),
            "confidence": 0.4,
            "generalizationNotes": (
                "A source outage is often transient; only generalize if it recurs. "
                f"Scope is limited to {scope.get('scopeClaim')}: do NOT generalize one "
                "country/provider to all countries."
            ),
            "knownLimitations": "Do not turn a temporary outage into a permanent source rule.",
        }
        drafts.append(draft)

    # ── 5. Provider-eligibility improvement: a provider was attempted for a
    #         request it is not eligible for (e.g. SEC for a non-US issuer) and
    #         the run still answered through another route. The lesson is a
    #         routing rule for ONE provider/market, never a global rule.
    ineligible = [
        e for e in retrieval_events
        if e["type"] == "retrieval.source_unavailable"
        and "not_covered" in str(e.get("data") or "").lower()
    ]
    if ineligible and tool_successes and source_failures:
        scope = _infer_scope(tools)
        draft = {
            "candidateType": "provider_eligibility_improvement",
            "title": "Skip a provider that is not eligible for the issuer's market",
            "problem": "A provider was attempted for a request it does not cover.",
            "observedBehavior": "Another eligible route answered the request.",
            "proposedLesson": (
                "Record a provider-eligibility rule (provider × market/issuer type) so an "
                "ineligible provider is skipped rather than attempted and reported as an outage."
            ),
            "evidenceReferences": [{"kind": "event", "id": e["id"], "type": e["type"]} for e in ineligible[:5]],
            "diagnostics": _diagnostic_summary(events),
            "scope": scope,
            "capability": _infer_capability(tools),
            "regressionCase": _regression_case(tools),
            "confidence": 0.5,
            "generalizationNotes": (
                "A provider's eligibility is issuer/market-specific; apply it only to the "
                f"observed scope ({scope.get('scopeClaim')}) and never to all markets."
            ),
            "knownLimitations": "Do not infer eligibility from a single failure; confirm the provider's stated coverage.",
        }
        drafts.append(draft)

    return drafts


def explicit_skill_candidate(
    run_id: str, run_store: Any, *, user_intent: str = ""
) -> dict[str, Any]:
    """A candidate synthesized from an explicit "turn this into a skill" request.

    Ordinary informational runs do not qualify for automatic candidate detection
    (they carry no reusable procedure). When the USER explicitly asks to turn a
    run into a skill, we still may not have evidence of a real procedure — so the
    candidate records the evidence that exists (tools used, steps taken) and,
    when there is no tool trace, explicitly states that manual authoring is
    required rather than fabricating a procedure. Always inert.
    """
    run = run_store.get_run(run_id) or {}
    tools = _run_tools(run_store, run_id)
    successes = sorted({t["name"] for t in tools if t.get("ok")})
    successful_procedure = [
        {"step": i + 1, "action": f"call {name}"} for i, name in enumerate(successes)
    ]
    objective = ((run.get("input") or {}).get("query") or "").strip()
    lesson = (
        (user_intent or "").strip()
        or (
            f"Reusable procedure observed for the objective: {objective[:300]}"
            if objective else "User-requested reusable procedure."
        )
    )
    no_evidence = not successes
    draft = {
        "candidateType": "successful_procedure",
        "title": (objective[:120] or "User-requested skill")[:200],
        "problem": "The user explicitly asked to turn this run into a reusable skill.",
        "observedBehavior": (
            f"Run {run_id}: {run.get('modelSteps', 0)} model steps; tools: "
            f"{', '.join(successes) if successes else 'none observed'}."
        ),
        "proposedLesson": lesson,
        "proposedProcedure": successful_procedure,
        "evidenceReferences": [
            {"kind": "tool", "name": t["name"], "at": t.get("createdAt")}
            for t in tools if t.get("ok")
        ],
        "confidence": 0.5 if successes else 0.25,
        "generalizationNotes": (
            "Requested by the user; reusability must be confirmed before this becomes a skill."
        ),
        "knownLimitations": (
            "No tool trace was observed in the source run; a human must author the "
            "procedure before this candidate can become a usable skill."
            if no_evidence
            else "A single run is weak evidence for a general procedure."
        ),
    }
    return draft


def capture_from_run(
    run_id: str,
    run_store: Any,
    skill_store: Any,
    *,
    actor_is_operator: bool = False,
    user_intent: str = "",
) -> dict[str, Any]:
    """Analyze a run and persist any qualifying candidates (deduplicated).

    `run_store` is the harness `AgentMemoryStore` (traces); `skill_store` is the
    `SkillStore` (candidates). They are the same database but different
    responsibilities. Requires operator authorization for the capture action
    itself (creating learning records is controlled). Returns the created
    candidates and any duplicates suppressed.

    `user_intent` is an explicit "turn this into a skill" request: when present,
    a candidate is created even if automatic detection would not qualify, so the
    explicit request is honored — still inert and operator-reviewed.
    """
    if not actor_is_operator:
        return {"ok": False, "error": "skill.create requires an authorized operator", "created": [], "duplicates": []}

    drafts = analyze_run(run_id, run_store)
    if user_intent:
        explicit = explicit_skill_candidate(run_id, run_store, user_intent=user_intent)
        if not any(d["candidateType"] == "successful_procedure" for d in drafts):
            drafts.append(explicit)
    created: list[dict[str, Any]] = []
    duplicates: list[str] = []
    for draft in drafts:
        signature = _signature(draft["candidateType"], draft["problem"])
        existing = skill_store.find_candidate_by_signature(signature)
        if existing:
            duplicates.append(existing["id"])
            continue
        candidate = {
            **draft,
            "id": None,
            "sourceRunId": run_id,
            "signature": signature,
            "status": "detected",
            "createdAt": now_iso(),
        }
        candidate_id = skill_store.save_candidate(candidate)
        skill_store.append_event("skill.learning_candidate_created", run_id=run_id,
                                 data={"candidateId": candidate_id, "candidateType": draft["candidateType"]})
        # A failure-recovery candidate is also a captured mistake/recovery in
        # Eclipse-Memory, so the mistake is inspectable even if no skill is made.
        if draft["candidateType"] == "failure_recovery":
            try:
                skill_store.save_mistake({
                    "category": "tool_failure",
                    "severity": "medium",
                    "runId": run_id,
                    "expected": "the failing tool would succeed",
                    "actual": draft.get("observedBehavior"),
                    "evidence": draft.get("evidenceReferences"),
                    "correctiveAction": draft.get("proposedLesson"),
                    "correctionWorked": True,
                    "reusable": True,
                    "candidateId": candidate_id,
                })
            except Exception:  # noqa: BLE001 - mistake capture is best-effort
                pass
        created.append(skill_store.get_candidate(candidate_id) or {"id": candidate_id})
    return {"ok": True, "created": created, "duplicates": duplicates}


__all__ = ["analyze_run", "capture_from_run"]
