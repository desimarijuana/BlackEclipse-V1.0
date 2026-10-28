"""Learning engine — capture reusable lessons from execution traces.

This module inspects a persisted run and MAY create an inert `LearningCandidate`.
It never creates a skill, never enables anything, and never lets a model
artifact become active. A candidate is a *reviewable observation*, not a
capability.

Candidate creation is criteria-driven and conservative:

CREATE a candidate when:
  * a failure was recovered through a reusable fallback (failure_recovery);
  * a user correction reveals a generalizable validation rule (user_correction);
  * a multi-step procedure succeeded AND was observed more than once
    (successful_procedure — recurrence is required; a single run is not proof);
  * a missing-data condition was resolved by a verified method
    (validation_improvement / source_selection_improvement).

DO NOT create a general skill from:
  * a single instrument-specific event;
  * a single successful run (one-off workflow — no recurrence evidence);
  * an unverified factual claim;
  * a temporary data anomaly with no reusable solution;
  * a user-specific preference (that belongs in memory);
  * a model explanation with no supporting evidence.

An eligible run is NOT itself permission to create a skill: recurrence (the same
successful workflow seen across runs) or an explicit user request is required.

Duplicate suppression uses a deterministic `signature` (type + normalized
problem) so the same experience never yields repeated candidates.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

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


# How many recent completed runs are scanned as a FALLBACK when the persisted
# recurrence ledger is unavailable. The ledger (agent-memory.db
# `LearningRecurrence`) is the primary, indexed, restart-surviving source; this
# only bounds the legacy scan path.
_RECURRENCE_SCAN_LIMIT = 40


def _candidate_recurrence_key(candidate_type: str, tools: list[dict[str, Any]]) -> Optional[str]:
    """A deterministic signature for "the same experience" so recurrence can be
    counted across runs without storing raw prose. Two runs share a key when
    their tool evidence for that candidate type is the same."""
    if candidate_type == "failure_recovery":
        # Order + tool name + failure class. Args vary legitimately; the
        # failure signature must not.
        names = [
            f"{t.get('name')}:{_error_code(t)}"
            for t in tools if not t.get("ok")
        ]
    elif candidate_type == "successful_procedure":
        # Canonical ordered sequence (names + success pattern).
        names = [str(t.get("name")) for t in tools if t.get("ok")]
    elif candidate_type in ("validation_improvement",
                             "source_selection_improvement",
                             "provider_eligibility_improvement"):
        names = sorted({str(t.get("name")) for t in tools if not t.get("ok")})
    else:
        return None
    if not names:
        return None
    digest = hashlib.sha256(
        f"{candidate_type}|{'->'.join(names)}".encode("utf-8")
    ).hexdigest()
    return digest[:32]


def _record_recurrence(store: Any, run_id: str, tools: list[dict[str, Any]]) -> None:
    """Record this run's evidence signatures so a later identical workflow counts
    as recurring. Uses the persisted ledger when available; never raises.

    Only completed runs with tool evidence contribute, so a failed or empty run
    cannot manufacture recurrence.
    """
    signatures = {
        key for key in (
            _candidate_recurrence_key("successful_procedure", tools),
            _candidate_recurrence_key("failure_recovery", tools),
        ) if key
    }
    record = getattr(store, "record_learning_recurrence", None)
    if record is None or not signatures:
        return
    for signature in signatures:
        try:
            record(signature, run_id)
        except Exception:  # noqa: BLE001 - ledger is best-effort
            return


def _recurrence_count(
    store: Any, run_id: str, candidate_type: str, tools: list[dict[str, Any]]
) -> int:
    """How many PRIOR completed runs carried the same evidence key.

    Primary source: the persisted, indexed `LearningRecurrence` ledger (survives
    restarts and is not bounded by a scan window). Secondary: a bounded scan of
    recent runs, for runs recorded before the ledger existed or when the ledger
    API is unavailable. The two are combined with `max` (never summed) so the
    same prior run is not double-counted. Never raises.
    """
    key = _candidate_recurrence_key(candidate_type, tools)
    if not key:
        return 0

    ledger_prior = 0
    counter = getattr(store, "learning_recurrence", None)
    if counter is not None:
        try:
            seen = int(counter(key))
            # The current run is recorded before this is called, so subtract it.
            ledger_prior = max(0, seen - 1)
        except Exception:  # noqa: BLE001
            ledger_prior = 0

    scan_prior = 0
    try:
        runs = store.list_runs(limit=_RECURRENCE_SCAN_LIMIT)
    except Exception:  # noqa: BLE001
        runs = []
    for prior in runs:
        if prior.get("id") == run_id or prior.get("status") != "completed":
            continue
        if _candidate_recurrence_key(candidate_type, _run_tools(store, prior["id"])) == key:
            scan_prior += 1

    return max(ledger_prior, scan_prior)


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
    "get_quote": "live_quote",
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


def _error_code(execution: dict[str, Any]) -> str:
    error = execution.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("message")
    else:
        code = getattr(error, "code", None) or getattr(error, "message", None)
    text = str(execution.get("text") or "")
    import re  # noqa: PLC0415

    generic = (not code) or str(code).lower() in (
        "tool_error", "error", "none", "tool_failure",
    )
    if generic or "TOOL_" in text:
        match = re.search(r"\b(TOOL_[A-Z_]+)\b", text)
        if match:
            code = match.group(1)
        elif "timed out" in text.lower():
            code = "TOOL_TIMEOUT"
        elif "unavailable" in text.lower():
            code = "UNAVAILABLE"
    return str(code or "tool_error").strip()[:120]


def _call_label(execution: dict[str, Any]) -> str:
    name = str(execution.get("name") or "tool")
    args = execution.get("args") or {}
    if isinstance(args, dict) and args:
        try:
            rendered = ", ".join(f"{key}={value!r}" for key, value in list(args.items())[:4])
        except Exception:  # noqa: BLE001 - a label never breaks analysis
            rendered = ""
        if rendered:
            return f"{name}({rendered})"[:240]
    return name


_FAILURE_TEXT_MARKERS = (
    "unavailable", "timeouterror", "timed out", "tool error", "forbidden",
    "not approved", "failed to", "app api unavailable", "app api error",
    "http 4", "http 5", "status code 4", "status code 5", "404", "500",
)

# The app-API proxy is a front-door reachability check, not a reusable recovery
# method: a retry cannot fix a down app. Never learn a recovery that routes
# through it.
_NON_RECOVERY_TOOLS = frozenset({"app_api_get"})


def _execution_succeeded(execution: dict[str, Any]) -> bool:
    """A tool call that reports an unavailable/error body is NOT a recovery."""
    if not execution.get("ok"):
        return False
    text = str(execution.get("text") or "").lower()
    return not any(marker in text for marker in _FAILURE_TEXT_MARKERS)


def _first_recovery_pair(
    tools: list[dict[str, Any]],
) -> Optional[tuple[dict[str, Any], dict[str, Any], str]]:
    """The first failure followed by a genuine same-capability recovery.

    A different tool that merely happens to succeed later is not evidence that
    it recovered the failed objective. The recovery must be the same tool (a
    retry) or the same recorded capability, and its body must not itself report
    unavailability/error.
    """
    for index, execution in enumerate(tools):
        if _execution_succeeded(execution):
            continue
        failed_name = str(execution.get("name") or "")
        if failed_name in _NON_RECOVERY_TOOLS:
            continue
        failed_capability = _TOOL_CAPABILITY.get(failed_name)
        for later in tools[index + 1 :]:
            if not _execution_succeeded(later):
                continue
            later_name = str(later.get("name") or "")
            if later_name in _NON_RECOVERY_TOOLS:
                continue
            same_capability = (
                failed_capability is not None
                and _TOOL_CAPABILITY.get(later_name) == failed_capability
            )
            if later_name == failed_name or same_capability:
                return execution, later, _error_code(execution)
    return None


def _failure_confidence(evidence_count: int, occurrence_count: int) -> float:
    from ..self_improvement.lesson_contract import derive_confidence  # noqa: PLC0415

    return derive_confidence(
        evidence_count=evidence_count,
        occurrence_count=occurrence_count,
        has_replay=True,
    )


def analyze_run(run_id: str, store: Any) -> list[dict[str, Any]]:
    """Analyze one run and return candidate drafts (not yet persisted).

    Does not create a candidate itself: `capture_from_run` persists the drafts.
    It DOES record this completed run's recurrence evidence (a bounded,
    signature-only ledger) so the next identical workflow counts as recurring;
    that is a bookkeeping side effect, not a candidate.
    """
    run = store.get_run(run_id)
    if run is None:
        return []
    events = _run_events(store, run_id)
    tools = _run_tools(store, run_id)

    if run.get("status") == "completed" and tools:
        _record_recurrence(store, run_id, tools)

    tool_failures = [t for t in tools if not t.get("ok")]
    tool_successes = [t for t in tools if t.get("ok")]
    validation_failures = [e for e in events if e["type"] in ("skill.validation_failed", "error")]
    event_types = {e["type"] for e in events}

    drafts: list[dict[str, Any]] = []

    # ── 0. Explicit user correction: a recorded correction is strong evidence
    #         that a prior answer was wrong. The candidate preserves the corrected
    #         fact as a scoped lesson; it never generalizes beyond it.
    memory_blob = run.get("memory") if isinstance(run.get("memory"), dict) else {}
    correction = str((memory_blob or {}).get("contentPreview") or "").strip()
    if str((memory_blob or {}).get("action") or "") in ("correct", "corrected") and correction:
        from ..self_improvement.lesson_contract import derive_confidence  # noqa: PLC0415

        drafts.append({
            "candidateType": "user_correction",
            "title": "Apply the user's recorded correction",
            "problem": "The user corrected a previous answer.",
            "observedBehavior": f"The correction recorded in the run was: {correction[:400]}",
            "condition": "a prior answer conflicts with the user's explicit correction",
            "action": f"apply the user's correction and state {correction[:200]}",
            "proposedLesson": (
                "When a user corrects a prior answer, apply the corrected statement "
                "and do not repeat the superseded claim."
            ),
            "proposedProcedure": [
                {"step": 1, "action": "detect",
                 "detail": "recognize that the user is correcting a prior answer"},
                {"step": 2, "action": "apply",
                 "detail": f"use the corrected statement: {correction[:200]}"},
                {"step": 3, "action": "verify",
                 "detail": "check the final answer reflects the correction"},
            ],
            "evidenceReferences": [
                {"kind": "memory", "id": run_id, "action": "correction"},
            ],
            "replayTest": (
                f"Replay run {run_id}: present the corrected statement and assert the "
                "answer reflects it rather than the superseded claim."
            ),
            "occurrenceCount": 1,
            "confidence": derive_confidence(
                evidence_count=1, occurrence_count=1, has_replay=True,
            ),
            "generalizationNotes": (
                "This lesson is scoped to the corrected fact; do not generalize it "
                "to unrelated claims."
            ),
            "knownLimitations": (
                "A single correction is weak evidence for a reusable procedure; "
                "recurrence is required before it can become a skill."
            ),
        })

    # ── 1. Failure recovery: a failure occurred, then the run still completed
    #         through a different, observable call. The candidate carries the
    #         failed call, the recovered call, the precondition and a replay test;
    #         without those it is not falsifiable and is not created.
    recovered = bool(tool_failures) and run.get("status") == "completed"
    if recovered:
        pairing = _first_recovery_pair(tools)
        if pairing is not None:
            failed_exec, recovered_exec, precondition = pairing
            failed_name = str(failed_exec.get("name"))
            recovered_name = str(recovered_exec.get("name"))
            same_tool = failed_name == recovered_name
            recurrence = _recurrence_count(store, run_id, "failure_recovery", tools)
            evidence = [
                {"kind": "tool", "name": failed_name, "phase": "failed",
                 "error": precondition, "at": failed_exec.get("createdAt")},
                {"kind": "tool", "name": recovered_name, "phase": "recovered",
                 "at": recovered_exec.get("createdAt")},
            ]
            title = (
                f"Retry {failed_name} after a transient {precondition}"
                if same_tool
                else f"Recover from {precondition} by calling {recovered_name}"
            )
            action = (
                f"retry {failed_name} once after a transient {precondition}, then "
                "verify the result is OK"
                if same_tool
                else (
                    f"call {recovered_name} after {failed_name} fails with "
                    f"{precondition}, then verify the original objective is satisfied"
                )
            )
            draft = {
                "candidateType": "failure_recovery",
                "title": title,
                "problem": (
                    f"{failed_name} failed with {precondition}; the run recovered "
                    f"through {recovered_name}."
                ),
                "observedBehavior": (
                    f"{failed_name} failed, then {recovered_name} succeeded and the "
                    "run completed."
                ),
                "condition": (
                    f"{failed_name} returns {precondition}"
                ),
                "action": action,
                "failedCall": _call_label(failed_exec),
                "recoveredCall": _call_label(recovered_exec),
                "precondition": precondition,
                "proposedLesson": (
                    f"When {failed_name} fails with {precondition}, "
                    + (
                        f"retry it once (transient {precondition}) and verify the "
                        "result is OK."
                        if same_tool
                        else f"call {recovered_name} instead and verify the objective."
                    )
                ),
                "proposedProcedure": [
                    {"step": 1, "action": "classify",
                     "detail": f"recognize {failed_name} returning {precondition}"},
                    {"step": 2, "action": "recover",
                     "detail": (
                         f"retry {failed_name} once"
                         if same_tool
                         else f"call {recovered_name} with the same objective"
                     )},
                    {"step": 3, "action": "verify",
                     "detail": "confirm the result is OK before using it"},
                ],
                "replayTest": (
                    f"Replay run {run_id}: force {failed_name} to return "
                    f"{precondition}; assert {recovered_name} is called and the run "
                    "completes."
                ),
                "evidenceReferences": evidence,
                "occurrenceCount": recurrence + 1,
                "confidence": _failure_confidence(len(evidence), recurrence + 1),
                "generalizationNotes": (
                    f"Observed in {recurrence + 1} run(s) with the same failure "
                    "signature; scope is the recorded precondition."
                ),
                "knownLimitations": (
                    "Applies only while the precondition matches; re-verify if the "
                    "provider error or tool contract changes."
                ),
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

    # ── 3. Successful procedure. Round 4 (W6): a successful CONSTRUCTION
    #         sequence (engineer → register a UI capability) is encoded with its
    #         actual steps and constraints on the FIRST occurrence — the
    #         registration ran, which is strong observable evidence — and the
    #         generic tool-sequence candidate is suppressed for that run. The
    #         generic path keeps its existing recurrence requirement.
    construction_draft: Optional[dict[str, Any]] = None
    if run.get("status") == "completed":
        try:
            from .procedures import (  # noqa: PLC0415 - keep the module import-light
                construction_candidate_draft,
                record_construction_recurrence,
            )

            construction_draft = construction_candidate_draft(run_id, store)
            if construction_draft is not None:
                record_construction_recurrence(store, run_id)
        except Exception:  # noqa: BLE001 - detection must never break a run
            construction_draft = None
    if construction_draft is not None:
        drafts.append(construction_draft)
    elif (
        run.get("status") == "completed"
        and run.get("modelSteps", 0) >= _REUSABLE_MIN_STEPS
        and tool_successes
        and "tool.failed" not in event_types
    ):
        ordered_tools: list[str] = []
        for execution in tool_successes:
            name = str(execution.get("name") or "")
            if name and name not in ordered_tools:
                ordered_tools.append(name)
        successful_tools = ordered_tools
        sequence = " -> ".join(successful_tools)
        capability = _infer_capability(tool_successes) or "general"
        recurrence = _recurrence_count(store, run_id, "successful_procedure", tool_successes)
        if recurrence >= 1:
            draft = {
                "candidateType": "successful_procedure",
                "title": f"Reusable procedure: {sequence}",
                "problem": f"Multi-step {capability} procedure completed: {sequence}.",
                "observedBehavior": f"{run.get('modelSteps')} model steps; tools: {sequence}.",
                "proposedLesson": (
                    f"Reuse the observed {capability} sequence: {sequence}."
                ),
                "condition": f"successful {capability} procedure with sequence {sequence}",
                "action": f"reuse the observed sequence: {sequence}",
                "proposedProcedure": [
                    {"step": i + 1, "action": f"call {name}"} for i, name in enumerate(successful_tools)
                ],
                "evidenceReferences": [
                    {"kind": "tool", "name": t["name"], "at": t.get("createdAt")} for t in tool_successes
                ],
                "occurrenceCount": recurrence + 1,
                "confidence": min(0.8, 0.5 + 0.1 * recurrence),
                "generalizationNotes": (
                    f"Observed in {recurrence + 1} runs with the same tool evidence; "
                    "still requires evaluation before promotion."
                ),
                "knownLimitations": "Confirm the procedure still holds across the supported markets/capabilities.",
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
    from ..self_improvement.lesson_contract import candidate_problems  # noqa: PLC0415

    created: list[dict[str, Any]] = []
    duplicates: list[str] = []
    rejected: list[dict[str, Any]] = []
    for draft in drafts:
        problems = candidate_problems(draft)
        if problems and not (
            user_intent and draft.get("candidateType") == "successful_procedure"
        ):
            rejected.append({
                "candidateType": draft.get("candidateType"),
                "title": str(draft.get("title") or "")[:120],
                "problems": problems,
            })
            continue
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
    return {
        "ok": True, "created": created, "duplicates": duplicates,
        "rejected": rejected,
    }


__all__ = ["analyze_run", "capture_from_run"]
