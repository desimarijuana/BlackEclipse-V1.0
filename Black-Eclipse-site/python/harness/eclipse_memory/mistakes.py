"""Mistake analysis — deterministic detection of mistakes from a run trace.

This is not a model call. It inspects a persisted run (events + tool executions
+ the final output) and applies explicit heuristics for the mistake categories
the brief names. Every detection carries evidence; nothing is invented.

Categories detected deterministically:
  tool_failure            — a tool call failed
  incorrect_tool_arguments— a validation failure (bad args)
  missing_source          — a financial claim with no retrieval evidence
  unsupported_claim       — an answer states a precise figure with no tool call
  missing_data_undisclosed— data was UNAVAILABLE but the answer omits it
  invalid_output_schema   — a skill output failed schema validation
  repeated_failure        — the same tool failed repeatedly in one run
  unresolved_contradiction— retrieval reported conflicts and the answer ignored them
  timeout                 — a tool or the run timed out

Categories that need semantic judgement (hallucinated metric, currency/unit
mismatch) are recorded only when a deterministic signal exists (e.g. the
retrieval layer flagged a currency mismatch), never guessed. A mistake is a
*recorded observation*; it becomes a reusable improvement only through the
existing gated learning pipeline.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso
from .store import EclipseMemoryStore

# Categories with a deterministic signal.
CATEGORIES = (
    "tool_failure",
    "incorrect_tool_arguments",
    "missing_source",
    "unsupported_claim",
    "missing_data_undisclosed",
    "invalid_output_schema",
    "repeated_failure",
    "unresolved_contradiction",
    "timeout",
    "currency_mismatch",
    "unit_mismatch",
    # Phase 4 (code): deterministic code-loop mistakes. Each carries evidence.
    "check_claimed_not_run",        # the answer asserts a pass with no execution
    "check_run_failed_ignored",     # a check FAILED and the answer asserts a pass
    "scope_violation",              # a write/execute denied by code.policy
    "unbounded_retry",              # repair attempts exceeded the configured bound
    "protected_path_write_attempt", # a write to a PROTECTED_PATHS entry was refused
    "sandbox_unavailable",          # a check could not run (honest refusal)
)

_SEVERITY = {
    "tool_failure": "medium",
    "incorrect_tool_arguments": "medium",
    "missing_source": "high",
    "unsupported_claim": "high",
    "missing_data_undisclosed": "high",
    "invalid_output_schema": "medium",
    "repeated_failure": "high",
    "unresolved_contradiction": "medium",
    "timeout": "medium",
    "currency_mismatch": "high",
    "unit_mismatch": "medium",
    "check_claimed_not_run": "high",
    "check_run_failed_ignored": "high",
    "scope_violation": "high",
    "protected_path_write_attempt": "high",
    "unbounded_retry": "medium",
    "sandbox_unavailable": "medium",
}

_PRECISE_NUMBER = __import__("re").compile(r"\b\d[\d,]*(\.\d+)?\s?(%|billion|million|bn|mn|cr|b|m)?\b")


def analyze_run_for_mistakes(run_id: str, run_store: Any) -> list[dict[str, Any]]:
    """Return candidate mistake records for a run (does not persist)."""
    run = run_store.get_run(run_id)
    if run is None:
        return []

    events = run_store.list_events(run_id)
    tools = run_store.list_tool_executions(run_id)
    output = run.get("output") or ""
    status = run.get("status")

    failed_tools = [t for t in tools if not t.get("ok")]
    ok_tools = [t for t in tools if t.get("ok")]
    event_types = [e["type"] for e in events]

    mistakes: list[dict[str, Any]] = []

    def add(category: str, **fields: Any) -> None:
        mistakes.append({
            "category": category,
            "severity": _SEVERITY.get(category, "medium"),
            "runId": run_id,
            **fields,
        })

    # 1. Tool failures (one record per distinct failing tool).
    for tool in failed_tools:
        error = tool.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else None
        add(
            "tool_failure",
            toolName=tool.get("name"),
            expected="the tool would return data",
            actual=f"{code or 'error'}: {tool.get('text', '')[:200]}",
            evidence={"toolCallId": tool.get("toolCallId"), "code": code},
            reusable=False,
            correctionWorked=None,
        )
        if code in ("TOOL_VALIDATION_FAILED",):
            add(
                "incorrect_tool_arguments",
                toolName=tool.get("name"),
                expected="valid arguments per the tool schema",
                actual=tool.get("text", "")[:200],
                evidence={"toolCallId": tool.get("toolCallId")},
                reusable=True,
            )
        if code == "TOOL_TIMEOUT":
            add("timeout", toolName=tool.get("name"),
                expected="completion within the timeout", actual="timed out",
                evidence={"toolCallId": tool.get("toolCallId")}, reusable=False)

    # 2. Repeated failure of the same tool in one run.
    fail_counts: dict[str, int] = {}
    for tool in failed_tools:
        name = tool.get("name") or "?"
        fail_counts[name] = fail_counts.get(name, 0) + 1
    for name, count in fail_counts.items():
        if count > 1:
            add("repeated_failure", toolName=name,
                expected="the tool retried with a different approach",
                actual=f"{name} failed {count} times in one run",
                evidence={"count": count}, reusable=True)

    # 3. Invalid skill output schema (a skill run recorded it).
    if "skill.validation_failed" in event_types:
        add("invalid_output_schema",
            expected="output matches the skill's declared schema",
            actual="a skill output/schema validation failed",
            evidence={"events": [e["id"] for e in events if e["type"] == "skill.validation_failed"][:3]},
            reusable=True)

    # 4. A financial retrieval returned UNAVAILABLE but the answer does not say so.
    unavailable_markers = ("UNAVAILABLE", "AMBIGUOUS", "SOURCE FAILURE", "NOT COVERED")
    retrieval_text = "\n".join(t.get("text", "") for t in tools)
    saw_unavailable = any(marker in retrieval_text for marker in unavailable_markers)
    if saw_unavailable and output:
        disclosed = any(word in output.lower() for word in
                        ("unavailable", "could not", "no data", "not available", "cannot verify", "unable to retrieve"))
        if not disclosed:
            add("missing_data_undisclosed",
                expected="the answer discloses that requested data was unavailable",
                actual="the answer omitted the unavailability",
                evidence={"tools": [t.get("name") for t in tools if not t.get("ok")]},
                reusable=True)

    # 5. A precise numeric claim with no successful tool call at all.
    if output and not ok_tools and _PRECISE_NUMBER.search(output):
        add("unsupported_claim",
            expected="precise figures backed by a successful tool call",
            actual="a precise figure appears with no successful data retrieval",
            evidence={"toolCalls": len(tools)},
            reusable=True)

    # 6. An answer with a factual financial claim but zero retrieval evidence.
    if output and not tools and status == "completed":
        claim_words = ("revenue", "earnings", "price", "p/e", "margin", "yield", "gdp", "inflation")
        if any(word in output.lower() for word in claim_words):
            add("missing_source",
                expected="financial claims grounded in a retrieved source",
                actual="a financial claim with no retrieval in the run",
                evidence={}, reusable=True)

    # 7. Retrieval conflicts ignored in the answer.
    conflict_events = [e for e in events if e["type"] in ("retrieval.conflicts", "retrieval.conflict")]
    if conflict_events and output:
        acknowledged = any(word in output.lower() for word in ("conflict", "disagree", "discrepan"))
        if not acknowledged:
            add("unresolved_contradiction",
                expected="the answer surfaces conflicting sources",
                actual="retrieval reported a conflict the answer ignored",
                evidence={"events": [e["id"] for e in conflict_events[:3]]},
                reusable=True)

    # 8. Currency / unit mismatch explicitly flagged by the retrieval layer.
    if "currency_mismatch" in retrieval_text.lower():
        add("currency_mismatch",
            expected="values in the expected currency",
            actual="a retrieved value carried a different currency",
            evidence={}, reusable=True)
    if "unit mismatch" in retrieval_text.lower() or "unit_mismatch" in retrieval_text.lower():
        add("unit_mismatch",
            expected="values in a consistent unit",
            actual="a retrieved value carried an inconsistent unit",
            evidence={}, reusable=True)

    # 9. Phase 4 (code): deterministic code-loop mistakes from the verification
    #    blob + command events. A mistake is a recorded observation, never a guess.
    _code_mistakes(add, run, events, tools, output)

    return mistakes


# Error codes that prove a write/execute was denied by code.policy (Phase 0–3).
_DENIED_CODES = {"OUTSIDE_WORKSPACE", "COMMAND_NOT_ALLOWLISTED", "PROFILE_DENIED"}


def _code_mistakes(add, run, events, tools, output) -> None:  # noqa: ANN001 - local helper
    """Deterministic code-domain categories, each with its evidence."""
    blob = run.get("codeVerification") or {}
    records = blob.get("records") if isinstance(blob, dict) else None
    claims = blob.get("claims") if isinstance(blob, dict) else None
    records = records if isinstance(records, list) else []
    claims = claims if isinstance(claims, list) else []
    event_types = [e["type"] for e in events]

    # check_claimed_not_run: an unbacked pass-claim exists AND no record at all
    # matched its class (nothing ran). Distinguish from failed_ignored below.
    if blob:
        unverified = [c for c in claims if isinstance(c, dict) and not c.get("supported")]
        if unverified and not records:
            add(
                "check_claimed_not_run",
                expected="a check claim backed by an execution in this run",
                actual="the answer asserted a passing check with no recorded execution",
                evidence={"claims": [c.get("kind") for c in unverified][:5]},
                reusable=True,
            )

    # check_run_failed_ignored: a NON-ZERO-exit record exists for class C AND the
    # answer carries an (unsupported) claim whose matchedClasses include C.
    failing_classes = {
        str(r.get("commandClass")) for r in records
        if isinstance(r, dict) and isinstance(r.get("exitCode"), int) and r.get("exitCode") != 0
    }
    if failing_classes:
        ignored = [
            c for c in claims
            if isinstance(c, dict) and not c.get("supported")
            and failing_classes.intersection(c.get("matchedClasses") or [])
        ]
        if ignored:
            add(
                "check_run_failed_ignored",
                expected="the answer states that a check failed",
                actual="a check ran and failed, but the answer asserted a pass",
                evidence={"failedClasses": sorted(failing_classes)},
                reusable=True,
            )

    # scope_violation: a command/patch tool execution was denied by policy.
    for tool in tools:
        if tool.get("ok"):
            continue
        error = tool.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else None
        if code in _DENIED_CODES:
            add(
                "scope_violation",
                toolName=tool.get("name"),
                expected="the action stays within the granted scope",
                actual=f"a code action was denied: {code}",
                evidence={"toolCallId": tool.get("toolCallId"), "code": code},
                reusable=True,
            )
            break

    # unbounded_retry: repair attempts EXCEEDED the recorded maximum (proof the
    # loop crossed its bound, not merely used it).
    repair_events = [e for e in events if e["type"] == "code.repair.attempt"]
    if blob:
        repair = blob.get("repair") or {}
        max_attempts = int(repair.get("maxAttempts") or 0)
        if max_attempts and len(repair_events) > max_attempts:
            add(
                "unbounded_retry",
                expected="repair stops at the configured attempt bound",
                actual=f"{len(repair_events)} repair attempts exceeded the bound of {max_attempts}",
                evidence={"attempts": len(repair_events), "maxAttempts": max_attempts},
                reusable=False,
            )

    # protected_path_write_attempt: a policy denial on a protected path for a write.
    protected_denied = [
        e for e in events if e["type"] == "code.policy.denied"
        and isinstance(e.get("data"), dict)
        and e["data"].get("code") == "PROTECTED_PATH"
        and e["data"].get("decision") == "write"
    ]
    if protected_denied:
        add(
            "protected_path_write_attempt",
            expected="a write never targets a protected path",
            actual="a write to a protected path was refused",
            evidence={"events": [e["id"] for e in protected_denied[:3]]},
            reusable=False,
        )

    # sandbox_unavailable: a check could not run — an honest refusal, still a
    # recorded observation.
    sandbox_events = [
        e for e in events if isinstance(e.get("data"), dict)
        and e["data"].get("code") == "SANDBOX_UNAVAILABLE"
    ]
    tool_sandbox = [
        t for t in tools if not t.get("ok")
        and isinstance(t.get("error"), dict) and t["error"].get("code") == "SANDBOX_UNAVAILABLE"
    ]
    if sandbox_events or tool_sandbox or (isinstance(blob, dict) and blob.get("repair", {}).get("status") == "refused"):
        add(
            "sandbox_unavailable",
            expected="a check runs and reports its result",
            actual="a check could not be run safely and was refused",
            evidence={"events": [e["id"] for e in sandbox_events[:3]]},
            reusable=False,
        )


def capture_mistakes(run_id: str, run_store: Any, skill_store: EclipseMemoryStore) -> list[dict[str, Any]]:
    """Detect and persist mistakes for a run (deduplicated by category+tool).

    Idempotent per run: an already-recorded (category, toolName, run) is not
    repeated.
    """
    existing = skill_store.list_mistakes(run_id, limit=500)
    seen = {(m["category"], m.get("toolName")) for m in existing}
    created: list[dict[str, Any]] = []
    for mistake in analyze_run_for_mistakes(run_id, run_store):
        key = (mistake["category"], mistake.get("toolName"))
        if key in seen:
            continue
        seen.add(key)
        mistake.setdefault("createdAt", now_iso())
        mistake_id = skill_store.save_mistake(mistake)
        created.append({**mistake, "id": mistake_id})
    if created:
        skill_store.append_event("skill.mistakes_captured", run_id=run_id,
                                 data={"count": len(created), "categories": sorted({m["category"] for m in created})})
    return created


__all__ = ["CATEGORIES", "analyze_run_for_mistakes", "capture_mistakes"]
