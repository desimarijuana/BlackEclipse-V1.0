"""Bounded recovery inside the run's tool loop (R3-03).

The graph calls `run_tool_with_recovery` for every tool call. This is NOT a
second execution loop: `ToolRegistry.execute` still runs the tool, and the
recovery ENGINE only classifies the failure and returns a bounded decision. The
loop then either retries the SAME call once — only a read-only tool, only a
retryable failure, only inside the recovery budget — or attaches the decision to
the failed result so the model's next attempt is a justified, DIFFERENT route
instead of a blind repeat.

Fail-open by construction: no engine, no store or any unexpected error returns
the original result unchanged. Recovery can never break a run or hide a failure.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import recovery_enabled
from .taxonomy import normalize_failure
from .tools import get_recovery_service

# A retry is only ever automatic for these strategies, on a READ-ONLY tool.
_RETRY_STRATEGIES = ("retry", "rate_limit_backoff")
# The in-loop wait is capped so backoff can never eat the run's wall clock.
_MAX_INLINE_BACKOFF_MS = 1500

# One plain sentence per strategy: what the NEXT attempt must do differently.
_STEP_GUIDANCE = {
    "retry": "retry this call once with the same arguments after a short pause",
    "rate_limit_backoff": "wait briefly, then retry this call once",
    "substitute_tool": "use a different available tool or route for the same objective",
    "substitute_provider": "use a different configured source or provider for the same fact",
    "alternative_implementation": "construct a different way to get the same result",
    "repair_input": "fix the missing or invalid input, then call again",
    "replan": "revise the approach — the current route cannot proceed as-is",
    "re_execute_node": "re-run this step once the surrounding state is fixed",
    "restore_checkpoint": "restore the last good state before continuing",
    "delegate_investigation": "split off an independent part of the problem and investigate that",
    "fix_dependency": "a required dependency is missing; report it rather than retrying",
    "suspend": "stop and report — this needs a decision outside the run",
    "stop_and_report": "stop retrying; report exactly what failed and what is missing",
}


def _state_for(ctx: Any) -> dict[str, Any]:
    """Per-run recovery counters, kept on the run context (never durable)."""
    state = getattr(ctx, "_recovery_hotpath", None)
    if state is None:
        state = {"attempts": 0, "signatures": {}, "started": time.monotonic()}
        try:
            ctx._recovery_hotpath = state
        except Exception:  # noqa: BLE001 - a read-only ctx must not break the call
            pass
    return state


def _is_read_only(registry: Any, name: str) -> bool:
    try:
        tool = registry.get(name)
    except Exception:  # noqa: BLE001
        return False
    if tool is None:
        return False
    return str(getattr(tool, "permission", "")) == "read"


def _hint(failure: dict[str, Any], decision: dict[str, Any], incident_id: str, retried: bool) -> str:
    strategy = str(decision.get("strategy") or "stop_and_report")
    guidance = _STEP_GUIDANCE.get(strategy, "change the approach before calling again")
    lead = (
        "A retry was attempted and did not succeed."
        if retried else "This call failed."
    )
    return (
        f"\n\n[recovery] {lead} Failure kind: {failure.get('kind')} "
        f"({failure.get('retryability')}). Next step: {guidance}. Do NOT repeat the "
        f"same call with the same arguments. Reason: {str(decision.get('reason') or '')} "
        f"(incident {incident_id})"
    )


async def _emit(ctx: Any, record: dict[str, Any]) -> None:
    emitter = getattr(ctx, "emitter", None)
    if emitter is None:
        return
    try:
        await emitter.emit("recovery.decided", {
            "incidentId": record.get("incidentId"),
            "decision": record.get("decision"),
            "failed": record.get("failure"),
        })
    except Exception:  # noqa: BLE001 - the event stream must never break a call
        pass


async def run_tool_with_recovery(
    registry: Any,
    name: str,
    call_id: str,
    args: Any,
    ctx: Any,
    allowed: Any,
    timeout_ms: Any,
    request: Any,
) -> Any:
    """Execute one tool call; on failure, apply bounded recovery.

    Returns the result of the (possibly retried) call. Never raises for recovery
    reasons — a failure in the recovery path returns the original result.
    """
    result = await registry.execute(
        name, call_id, args, ctx, allowed=allowed, timeout_ms=timeout_ms
    )
    if result.ok:
        return result
    try:
        return await _recover(registry, name, call_id, args, ctx, allowed, timeout_ms, request, result)
    except Exception:  # noqa: BLE001 - recovery must never break the tool loop
        return result


async def _recover(
    registry: Any,
    name: str,
    call_id: str,
    args: Any,
    ctx: Any,
    allowed: Any,
    timeout_ms: Any,
    request: Any,
    result: Any,
) -> Any:
    service = get_recovery_service()
    if service is None or not recovery_enabled():
        return result

    code = result.error.code if getattr(result, "error", None) else "TOOL_ERROR"
    message = str(getattr(result, "text", "") or "")
    failure = normalize_failure(
        code=code, message=message, subsystem=name, source="hotpath", location=name,
    )
    state = _state_for(ctx)
    signature = failure.signature
    signature_attempts = int(state["signatures"].get(signature, 0))
    record = service.record_failure(
        code=code,
        message=message,
        subsystem=name,
        source="hotpath",
        location=name,
        run_id=getattr(request, "runId", None),
        details={"tool": name, "hotPath": True},
        recovery_state={
            "attempts": int(state["attempts"]),
            "signature_attempts": signature_attempts,
            "recurrent": signature_attempts >= 1,
            "delegations": 0,
            "elapsed_ms": int((time.monotonic() - state["started"]) * 1000),
        },
    )
    state["signatures"][signature] = signature_attempts + 1
    decision = record.get("decision") or {}
    incident_id = str(record.get("incidentId") or "")

    retried = False
    can_retry = (
        str(decision.get("action")) == "recover"
        and str(decision.get("strategy")) in _RETRY_STRATEGIES
        and _is_read_only(registry, name)
    )
    if can_retry:
        state["attempts"] = int(state["attempts"]) + 1
        backoff = min(int(decision.get("backoffMs") or 0), _MAX_INLINE_BACKOFF_MS)
        if backoff:
            await asyncio.sleep(backoff / 1000.0)
        result = await registry.execute(
            name, call_id, args, ctx, allowed=allowed, timeout_ms=timeout_ms
        )
        retried = True
        try:
            service.record_outcome(
                incident_id,
                outcome="succeeded" if result.ok else "failed",
                detail={"strategy": decision.get("strategy"), "hotPath": True, "retried": True},
            )
        except Exception:  # noqa: BLE001
            pass
        if result.ok:
            result.text = (
                f"{result.text}\n\n[recovery] The first attempt failed; a retry succeeded "
                f"(incident {incident_id})."
            )
            await _emit(ctx, record)
            return result

    result.text = f"{result.text}{_hint(failure.to_dict(), decision, incident_id, retried)}"
    await _emit(ctx, record)
    return result


__all__ = ["run_tool_with_recovery"]
