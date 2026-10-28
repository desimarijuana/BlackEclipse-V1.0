"""Evidence-gated tool-widening proposals.

This module assembles a ratification package for ADDING one read/compute tool to
an agent surface. It never grants, activates, persists or renews anything: the
only output is a deterministic, machine-checkable safety case whose default
answer is refusal. A human must still ratify the change through the existing
operator surfaces.

The module is pure so it can be tested without a store and cannot be reached by
the self-improvement loop as an activation path. The requirements it enforces
are specified in ``docs/self-improvement/tool-widening/safety-case-spec.md``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Sequence

MIN_OCCURRENCES = 3
MIN_DISTINCT_SESSIONS = 3
MIN_DISTINCT_TASKS = 2
MIN_REPLAY_RUNS = 5
MIN_VALIDATION_RUNS = 2
MIN_NEGATIVE_CONTROLS = 2
MAX_ADDED_TOOLS = 1
MAX_EVIDENCE_AGE_DAYS = 14
PROPOSED_TTL_DAYS = 14

ALLOWED_PERMISSIONS = frozenset({"read"})
ALLOWED_RISKS = frozenset({"none", "low"})
ALLOWED_EFFECTS = frozenset({"", "read"})

FINANCIAL_ACTION_MARKERS: tuple[str, ...] = (
    "place_order",
    "submit_order",
    "cancel_order",
    "modify_order",
    "execute_trade",
    "trade_execute",
    "send_payment",
    "fund_transfer",
    "transfer",
    "withdraw",
    "deposit",
)

MECHANISM_TOOL_MARKERS: tuple[str, ...] = (
    "capability_",
    "skill_",
    "grant_",
    "autonomy_",
    "rsl_",
    "mcp_",
    "plugin_install",
    "code_",
    "command_",
    "shell_",
    "terminal_",
    "execution_",
    "fabric_",
    "approval_",
    "policy_",
    "security_",
)

HUMAN_REVIEW_ITEMS: tuple[str, ...] = (
    "confirm the named failure and the replay failures are the same class",
    "confirm the added tool is the narrowest available tool",
    "confirm the deny-path input covers the realistic dangerous inputs",
    "confirm the blast radius is acceptable for this workspace",
    "confirm any expected conclusion change is acceptable and non-financial",
)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _as_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _out_of_scope_reason(name: str, metadata: Mapping[str, Any]) -> str:
    lowered = name.casefold()
    for marker in FINANCIAL_ACTION_MARKERS:
        if marker in lowered:
            return "financial_action"
    for marker in MECHANISM_TOOL_MARKERS:
        if lowered == marker or lowered.startswith(marker):
            return "mechanism"
    permission = str(metadata.get("permission") or "").strip().lower()
    if permission not in ALLOWED_PERMISSIONS:
        return "effectful"
    risk = str(metadata.get("risk") or "").strip().lower()
    if risk not in ALLOWED_RISKS:
        return "risky"
    effect = str(metadata.get("effect") or "").strip().lower()
    if effect not in ALLOWED_EFFECTS:
        return "effectful"
    return ""


def _case_id(payload: Mapping[str, Any]) -> str:
    raw = _canonical(payload).encode("utf-8")
    return "wcase_" + hashlib.sha256(raw).hexdigest()[:16]


def build_widening_case(
    *,
    added_tools: Sequence[str],
    base_tools: Sequence[str],
    registered_tools: Sequence[str],
    blocked_tools: Sequence[str],
    tool_metadata: Mapping[str, Mapping[str, Any]],
    need: Mapping[str, Any],
    replay: Mapping[str, Any],
    scope: str = "workspace",
    max_calls_per_day: int = 0,
    proposed_at: str = "",
    evidence_cutoff: str = "",
) -> dict[str, Any]:
    """Assemble a ratification package. Never grants anything.

    ``eligible`` means the safety case is complete enough to ask a human. Every
    return value has ``granted=False``, ``requiresOperator=True``,
    ``autoApply=False`` and ``selfRenewable=False``.
    """
    reasons: list[str] = []
    missing: list[str] = []

    added = _as_strings(added_tools)
    base = set(_as_strings(base_tools))
    registered = set(_as_strings(registered_tools))
    blocked = set(_as_strings(blocked_tools))

    if not added:
        reasons.append("WIDENING_NO_ADDED_TOOL")
        missing.append("addedTools")
    if len(added) > MAX_ADDED_TOOLS:
        reasons.append("WIDENING_TOO_MANY_TOOLS")
    if len(set(added)) != len(added):
        reasons.append("WIDENING_DUPLICATE_TOOL")

    for name in added:
        if name in base:
            reasons.append(f"WIDENING_TOOL_ALREADY_PRESENT:{name}")
        if name in blocked:
            reasons.append(f"WIDENING_TOOL_BLOCKED:{name}")
        if name not in registered:
            reasons.append(f"WIDENING_TOOL_UNKNOWN:{name}")
        metadata = tool_metadata.get(name)
        if not isinstance(metadata, Mapping):
            reasons.append(f"WIDENING_TOOL_METADATA_MISSING:{name}")
            missing.append(f"toolMetadata.{name}")
            continue
        excluded = _out_of_scope_reason(name, metadata)
        if excluded:
            reasons.append(f"WIDENING_TOOL_OUT_OF_SCOPE:{excluded}:{name}")

    failure_signature = str(
        need.get("failureSignature") or need.get("failure_signature") or ""
    ).strip()
    named_failure = str(
        need.get("namedFailure") or need.get("named_failure") or ""
    ).strip()
    existing_cannot = str(
        need.get("existingToolsCannotServe")
        or need.get("existing_tools_cannot_serve")
        or ""
    ).strip()
    occurrences = _as_int(need.get("occurrences"))
    distinct_sessions = _as_int(
        need.get("distinctSessions") or need.get("distinct_sessions")
    )
    distinct_tasks = _as_int(need.get("distinctTasks") or need.get("distinct_tasks"))

    if not failure_signature:
        reasons.append("WIDENING_NEED_UNNAMED")
        missing.append("need.failureSignature")
    if not named_failure:
        missing.append("need.namedFailure")
    if not existing_cannot:
        reasons.append("WIDENING_NEED_NOT_DEMONSTRATED")
        missing.append("need.existingToolsCannotServe")
    if occurrences < MIN_OCCURRENCES:
        reasons.append("WIDENING_NEED_TOO_FEW_OCCURRENCES")
    if distinct_sessions < MIN_DISTINCT_SESSIONS:
        reasons.append("WIDENING_NEED_TOO_FEW_SESSIONS")
    if distinct_tasks < MIN_DISTINCT_TASKS:
        reasons.append("WIDENING_NEED_TOO_FEW_TASKS")

    evidence_ids = _as_strings(need.get("evidenceRunIds") or need.get("evidence_run_ids"))
    derivation_ids = set(
        _as_strings(need.get("derivationRunIds") or need.get("derivation_run_ids"))
    )
    validation_ids = set(
        _as_strings(need.get("validationRunIds") or need.get("validation_run_ids"))
    )
    derivation_tasks = set(
        _as_strings(need.get("derivationTaskIds") or need.get("derivation_task_ids"))
    )
    validation_tasks = set(
        _as_strings(need.get("validationTaskIds") or need.get("validation_task_ids"))
    )
    excluded_ids = _as_strings(need.get("excludedRunIds") or need.get("excluded_run_ids"))
    evidence_completed = _as_strings(
        need.get("evidenceCompletedAt") or need.get("evidence_completed_at")
    )

    if not evidence_ids:
        reasons.append("WIDENING_EVIDENCE_IDS_MISSING")
        missing.append("need.evidenceRunIds")
    if len(set(evidence_ids)) != len(evidence_ids):
        reasons.append("WIDENING_DUPLICATE_EVIDENCE")
    if not validation_ids:
        reasons.append("WIDENING_TOO_FEW_VALIDATION_RUNS")
        missing.append("need.validationRunIds")
    elif len(validation_ids) < MIN_VALIDATION_RUNS:
        reasons.append("WIDENING_TOO_FEW_VALIDATION_RUNS")
    if derivation_ids & validation_ids:
        reasons.append("WIDENING_EVIDENCE_NOT_DISJOINT")
    if not derivation_tasks or not validation_tasks:
        reasons.append("WIDENING_TASK_EVIDENCE_MISSING")
        missing.append("need.derivationTaskIds/need.validationTaskIds")
    elif derivation_tasks & validation_tasks:
        reasons.append("WIDENING_TASKS_NOT_DISJOINT")
    if excluded_ids:
        reasons.append("WIDENING_CHERRY_PICK")

    if not proposed_at:
        reasons.append("WIDENING_PROPOSAL_TIME_MISSING")
        missing.append("proposedAt")
    if not evidence_cutoff:
        reasons.append("WIDENING_EVIDENCE_CUTOFF_MISSING")
        missing.append("evidenceCutoff")
    if not evidence_completed:
        reasons.append("WIDENING_EVIDENCE_TIMESTAMPS_MISSING")
        missing.append("need.evidenceCompletedAt")
    elif proposed_at and evidence_cutoff:
        if evidence_cutoff > proposed_at:
            reasons.append("WIDENING_EVIDENCE_POSTDATES_PROPOSAL")
        newest = max(evidence_completed)
        if newest > evidence_cutoff:
            reasons.append("WIDENING_EVIDENCE_POSTDATES_CUTOFF")

    replay_runs = _as_int(replay.get("runs"))
    fired = _as_int(replay.get("toolWouldHaveFired") or replay.get("tool_would_have_fired"))
    passed = _as_int(replay.get("passed"))
    critical = _as_int(
        replay.get("criticalRegressions") or replay.get("critical_regressions")
    )
    negative_controls = _as_int(
        replay.get("notNeededControlsPassed") or replay.get("not_needed_controls_passed")
    )
    deny_tested = bool(replay.get("denyPathTested") or replay.get("deny_path_tested"))
    deny_refused = bool(replay.get("denyPathRefused") or replay.get("deny_path_refused"))
    freshness = str(
        replay.get("evidenceFreshness") or replay.get("evidence_freshness") or ""
    ).strip().lower()
    age_days = _as_int(replay.get("evidenceAgeDays") or replay.get("evidence_age_days"))
    before = sorted(
        _as_strings(
            replay.get("conclusionDigestsBefore")
            or replay.get("conclusion_digests_before")
        )
    )
    after = sorted(
        _as_strings(
            replay.get("conclusionDigestsAfter")
            or replay.get("conclusion_digests_after")
        )
    )
    expected_changes = set(
        _as_strings(
            replay.get("expectedConclusionChanges")
            or replay.get("expected_conclusion_changes")
        )
    )

    if replay_runs < MIN_REPLAY_RUNS:
        reasons.append("WIDENING_REPLAY_TOO_FEW_RUNS")
    if fired < 1:
        reasons.append("WIDENING_REPLAY_TOOL_NEVER_FIRED")
    if passed < fired:
        reasons.append("WIDENING_REPLAY_FAILED")
    if critical > 0:
        reasons.append("WIDENING_CRITICAL_REGRESSION")
    if negative_controls < MIN_NEGATIVE_CONTROLS:
        reasons.append("WIDENING_NEGATIVE_CONTROL_FAILED")
    if not deny_tested:
        reasons.append("WIDENING_DENY_PATH_UNTESTED")
    if not deny_refused:
        reasons.append("WIDENING_DENY_PATH_FAILED")
    if freshness != "fresh" or age_days > MAX_EVIDENCE_AGE_DAYS:
        reasons.append("WIDENING_EVIDENCE_STALE")
    if not before or not after:
        reasons.append("WIDENING_CONCLUSION_EVIDENCE_MISSING")
    else:
        changed = (set(before) - set(after)) | (set(after) - set(before))
        if changed - expected_changes:
            reasons.append("WIDENING_CONCLUSIONS_CHANGED")

    if scope not in ("workspace", "global"):
        reasons.append("WIDENING_SCOPE_INVALID")
    elif scope == "global":
        reasons.append("WIDENING_SCOPE_NOT_NARROWEST")
    if _as_int(max_calls_per_day) < 1:
        reasons.append("WIDENING_NO_CALL_BUDGET")

    evidence = {
        "need": {
            "failureSignature": failure_signature,
            "namedFailure": named_failure,
            "existingToolsCannotServe": existing_cannot,
            "occurrences": occurrences,
            "distinctSessions": distinct_sessions,
            "distinctTasks": distinct_tasks,
            "evidenceRunIds": evidence_ids,
            "derivationRunIds": sorted(derivation_ids),
            "validationRunIds": sorted(validation_ids),
            "derivationTaskIds": sorted(derivation_tasks),
            "validationTaskIds": sorted(validation_tasks),
            "excludedRunIds": excluded_ids,
            "evidenceCompletedAt": evidence_completed,
        },
        "replay": {
            "runs": replay_runs,
            "toolWouldHaveFired": fired,
            "passed": passed,
            "criticalRegressions": critical,
            "notNeededControlsPassed": negative_controls,
            "denyPathTested": deny_tested,
            "denyPathRefused": deny_refused,
            "evidenceFreshness": freshness,
            "evidenceAgeDays": age_days,
            "conclusionDigestsBefore": before,
            "conclusionDigestsAfter": after,
            "expectedConclusionChanges": sorted(expected_changes),
        },
        "blastRadius": {
            "addedTools": added,
            "scope": scope,
            "maxCallsPerDay": _as_int(max_calls_per_day),
            "toolMetadata": {
                name: dict(tool_metadata.get(name) or {}) for name in added
            },
        },
        "timing": {
            "proposedAt": proposed_at,
            "evidenceCutoff": evidence_cutoff,
        },
    }
    eligible = not reasons
    case_id = _case_id({
        "addedTools": added,
        "scope": scope,
        "failureSignature": failure_signature,
        "proposedAt": proposed_at,
        "evidence": evidence,
    })
    return {
        "caseId": case_id,
        "status": "ready_for_operator" if eligible else "refused",
        "eligible": eligible,
        "granted": False,
        "requiresOperator": True,
        "autoApply": False,
        "selfRenewable": False,
        "renewalRequiresNewEvidence": True,
        "addedTools": added,
        "scope": scope,
        "proposedTtlDays": PROPOSED_TTL_DAYS,
        "expiresAt": None,
        "withdrawn": False,
        "withdrawnAt": None,
        "withdrawnReason": "",
        "reasons": reasons,
        "missing": missing,
        "humanReview": list(HUMAN_REVIEW_ITEMS),
        "evidence": evidence,
        "revocation": {
            "path": "remove the tool from the agent preset or deactivate the capability",
            "audited": True,
            "requiredBeforeRatification": True,
        },
    }


def withdraw_case(
    case: Mapping[str, Any],
    *,
    reason: str = "",
    at: str = "",
) -> dict[str, Any]:
    """Withdraw a staged case. Idempotent; never grants or revokes access."""
    updated = dict(case)
    updated["status"] = "withdrawn"
    updated["eligible"] = False
    updated["granted"] = False
    updated["withdrawn"] = True
    updated["withdrawnAt"] = str(at or "")
    updated["withdrawnReason"] = str(reason or "")
    return updated


def is_case_live(case: Mapping[str, Any], *, now: Optional[str] = None) -> bool:
    """Whether a staged case may still be shown to an operator.

    A withdrawn, expired or non-ready case is not live. An unparseable or absent
    live state fails closed.
    """
    if bool(case.get("withdrawn")):
        return False
    if str(case.get("status") or "") != "ready_for_operator":
        return False
    expires_at = str(case.get("expiresAt") or "").strip()
    if not expires_at:
        return True
    if not now:
        return False
    return str(now) < expires_at


__all__ = [
    "FINANCIAL_ACTION_MARKERS",
    "HUMAN_REVIEW_ITEMS",
    "MAX_ADDED_TOOLS",
    "MAX_EVIDENCE_AGE_DAYS",
    "MECHANISM_TOOL_MARKERS",
    "MIN_DISTINCT_SESSIONS",
    "MIN_DISTINCT_TASKS",
    "MIN_NEGATIVE_CONTROLS",
    "MIN_OCCURRENCES",
    "MIN_REPLAY_RUNS",
    "MIN_VALIDATION_RUNS",
    "PROPOSED_TTL_DAYS",
    "build_widening_case",
    "is_case_live",
    "withdraw_case",
]
