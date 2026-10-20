"""The run-scoped read surface (`/runs/{id}/…`).

The run's records — its events, why it knew what it knew, and the ONE outcome
envelope that names how it was routed (W1.3) — live here rather than in
`main.py`, which sits at the hard ceiling. The paths are unchanged, so the
front door is untouched: these are read-only, derived views over records the
runtime already wrote.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..deps import service

router = APIRouter()


@router.get("/runs/{run_id}/events")
def get_events(run_id: str) -> dict[str, Any]:
    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "success": True,
        "runId": run_id,
        "events": service.list_events(run_id),
        "toolExecutions": service.list_tool_executions(run_id),
    }


@router.get("/runs/{run_id}/explain")
def explain_run_endpoint(run_id: str) -> dict[str, Any]:
    """Why did the agent know/use (or not use) this? Derived, read-only, redacted.

    Combines the run's retrieval event (injected + excluded-with-reason + budget)
    with its prompt plan/profile/bundle events. Changes nothing at runtime.
    """
    from ..run_observability import explain_run  # noqa: PLC0415

    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    retrievals = service.memory_store.list_retrievals(limit=1, run_id=run_id)
    return {
        "success": True,
        **explain_run(
            run_id=run_id,
            retrieval_event=retrievals[0] if retrievals else None,
            events=service.list_events(run_id),
            run=service.get_run(run_id),
            lineage=service.run_lineage().lineage(run_id),
        ),
    }


@router.get("/runs/{run_id}/outcome")
def run_outcome_endpoint(run_id: str) -> dict[str, Any]:
    """The ONE record naming how this run was routed (W1.3).

    Intent verdict, resolved surface + allowlist, refusal code and the
    capability gap — derived from the run's canonical records. A fact that was
    never recorded is `null`, never guessed. Read-only; changes nothing.
    """
    from ..run_outcome import build_outcome_envelope, read_intent  # noqa: PLC0415

    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "success": True,
        **build_outcome_envelope(
            run_id=run_id,
            run=service.get_run(run_id),
            events=service.list_events(run_id),
            tool_executions=service.list_tool_executions(run_id),
            intent=read_intent(service.memory_store, run_id),
        ),
    }


__all__ = ["router"]
