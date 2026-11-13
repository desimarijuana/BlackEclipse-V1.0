"""Recovery routes — the operator surface for the failure-intelligence engine.

Read-only inspection of the recorded failure incidents, their classification, the
recovery decision taken and the attempt history; plus one operator-gated action
to record an attempt's outcome. Every mutation is gated by `require_operator`
(transport/token, never a body flag).

No route exposes a secret: incidents carry only the already-sanitized code,
message and metadata the emitting subsystem supplied.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_operator, service

router = APIRouter(tags=["recovery"])


def _engine():
    engine = getattr(service, "recovery", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="recovery engine unavailable")
    return engine


@router.get("/recovery/health")
def recovery_health() -> dict[str, Any]:
    return _engine().health()


@router.get("/recovery/summary")
def recovery_summary() -> dict[str, Any]:
    return _engine().summary()


@router.get("/recovery/metrics")
def recovery_metrics() -> dict[str, Any]:
    """The self-evolution metric block (round 4, W7), from the REAL records.

    Store-backed dimensions (time_to_repair, self_repair_precision,
    requirement_completeness) are measured from this runtime's incidents and
    goal tasks; a dimension with no samples stays None. Read-only.
    """
    from ..evaluation.repair_metrics import collect_self_evolution_metrics

    engine = _engine()
    incidents: list[dict[str, Any]] = []
    attempts_by_incident: dict[str, list[dict[str, Any]]] = {}
    try:
        incidents = engine.store.list_incidents(limit=500)
        # The outcome is an `action="outcome"` attempt; read it for resolved
        # incidents only (bounded), so the metric is real, never inferred.
        for incident in incidents[:200]:
            if str(incident.get("status")) != "resolved":
                continue
            attempts_by_incident[str(incident.get("id"))] = engine.store.list_attempts(
                incident["id"], limit=50,
            )
    except Exception:  # noqa: BLE001 - an unreadable ledger reports unmeasured, never a guess
        incidents, attempts_by_incident = [], {}
    tasks: list[dict[str, Any]] = []
    manager = getattr(service, "tasks", None)
    if manager is not None:
        try:
            for plan in manager.list_plans(limit=200):
                for task in manager.list_tasks(plan_id=plan.id, limit=500):
                    tasks.append({
                        "goalContract": (
                            task.goal_contract.model_dump() if task.goal_contract else None
                        ),
                        "criteria": [
                            {"required": criterion.required, "state": criterion.state.value}
                            for criterion in manager.list_criteria(task.id)
                        ],
                    })
        except Exception:  # noqa: BLE001
            tasks = []
    return collect_self_evolution_metrics(
        incidents=incidents, attempts_by_incident=attempts_by_incident,
        tasks=tasks, store=getattr(service, "store", None),
    )


@router.get("/recovery/incidents")
def list_incidents(
    status: Optional[str] = Query(default=None),
    task_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    incidents = _engine().list_incidents(status=status, task_id=task_id, limit=limit)
    return {"incidents": incidents, "count": len(incidents)}


@router.get("/recovery/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict[str, Any]:
    engine = _engine()
    incident = engine.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident": incident, "attempts": engine.incident_attempts(incident_id)}


@router.get("/recovery/discover")
def discover(query: str = Query(..., min_length=1), limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
    engine = _engine()
    matches = engine.discover(query, limit=limit)
    return {"query": query, "matches": matches, "plan": engine.plan_acquisition(query)}


@router.get("/recovery/envelope")
def get_envelope() -> dict[str, Any]:
    return {"envelope": _engine().envelope_view()}


@router.put("/recovery/envelope")
def set_envelope(
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    from ..recovery.envelope import from_dict  # noqa: PLC0415

    envelope = from_dict(payload or {}, source="operator")
    return {"envelope": _engine().set_envelope(envelope)}


@router.get("/recovery/operations")
def list_operations(
    incident_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    ledger = _engine().operations
    if incident_id:
        operations = ledger.list_by_incident(incident_id, limit=limit)
    else:
        operations = ledger.pending_compensations(limit=limit)
    return {"operations": operations, "count": len(operations)}


@router.get("/recovery/incidents/{incident_id}/approvals")
def list_approvals(incident_id: str) -> dict[str, Any]:
    return {"approvals": _engine().approvals(incident_id)}


@router.post("/recovery/incidents/{incident_id}/approve")
def approve(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    strategy = str(payload.get("strategy") or "").strip()
    if not strategy:
        raise HTTPException(status_code=400, detail="strategy is required")
    approval = _engine().approve(
        incident_id, strategy, approved_by=payload.get("approvedBy") or "operator"
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"approval": approval}


@router.post("/recovery/incidents/{incident_id}/diagnose")
def diagnose(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    diagnosis = _engine().diagnose_incident(incident_id, evidence=payload or {})
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"diagnosis": diagnosis}


@router.post("/recovery/incidents/{incident_id}/routing-repair")
def prepare_routing_repair(
    incident_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """Prepare a verified routing repair in a disposable copy.

    Returns the proposal, the promotion preview and the self-host landing verdict;
    the existing `/code/tasks/{runId}/promote` card performs the actual landing.
    This route never writes the real checkout.
    """
    from ..recovery import routing_landing  # noqa: PLC0415

    try:
        result = routing_landing.prepare(service, incident_id)
    except routing_landing.RoutingLandingError as exc:
        status = 404 if exc.code == "ROUTING_INCIDENT_NOT_FOUND" else 409
        raise HTTPException(status_code=status, detail=exc.code) from exc
    return {"success": True, **result}


@router.post("/recovery/incidents/{incident_id}/acquisition")
def plan_incident_acquisition(
    incident_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """The ordered acquisition lifecycle for a stored capability incident."""
    plan = _engine().plan_incident_acquisition(incident_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="incident not found or it carries no capability request",
        )
    return {"acquisition": plan}


@router.post("/recovery/incidents/{incident_id}/acquisition/execute")
def execute_incident_acquisition(
    incident_id: str,
    payload: Optional[dict[str, Any]] = None,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """Execute ONE acquisition step through its surface, operator-gated.

    `approved: true` is the operator's explicit decision that authorizes a
    mutation step (`install`/`enable`); without it the step is handed back with
    its exact approval requirement. Nothing self-grants: the handler still runs
    through the named existing gate.
    """
    from ..recovery.acquire_handlers import (
        build_acquisition_handlers, park_for_acquisition, proposal_from_dict,
    )
    from ..recovery.acquisition import execute_step

    engine = _engine()
    body = payload or {}
    facts = body.get("facts") if isinstance(body.get("facts"), dict) else None
    plan = engine.plan_incident_acquisition(incident_id, facts=facts)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="incident not found or it carries no capability request",
        )
    proposal = proposal_from_dict(plan)
    index = int(body.get("stepIndex") or 0)
    approved = bool(body.get("approved"))
    manager = getattr(service, "tasks", None)
    task = None
    incident = engine.store.get_incident(incident_id) or {}
    if manager is not None and incident.get("taskId"):
        try:
            task = manager.get_task(str(incident["taskId"]))
        except Exception:  # noqa: BLE001 - a missing task is reported, not invented
            task = None
    handlers = (
        build_acquisition_handlers(service, manager, task, facts=facts)
        if manager is not None and task is not None else {}
    )
    outcome = execute_step(proposal, index, handlers=handlers, approved=approved)
    result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
    result_status = str(result.get("status") or "")
    # A `build` step routed through the production surfaces parks the original
    # task (dependency or operator wait); the DAG or the resume route wakes it.
    # Parking NEVER re-executes the step. A handler-level `approval_required`
    # (e.g. a skill install whose single-use approval is not granted yet) parks
    # the task for the operator the same way.
    parked = None
    if outcome.get("status") == "executed" and manager is not None and task is not None:
        if result_status == "approval_required":
            try:
                manager.wait_task(task.id, reason="APPROVAL")
            except Exception:  # noqa: BLE001 - parking is best-effort
                pass
            parked = {"resume": "operator"}
        else:
            parked = park_for_acquisition(manager, task, outcome.get("result"))
    elif (outcome.get("status") == "approval_required"
          and manager is not None and task is not None):
        try:
            manager.wait_task(task.id, reason="APPROVAL")
        except Exception:  # noqa: BLE001 - parking is best-effort
            pass
        parked = {"resume": "operator"}
    return {
        "success": outcome.get("status") == "executed"
        and result_status not in ("approval_required", "failed"),
        "outcome": outcome, "parked": parked,
    }


@router.post("/recovery/incidents/{incident_id}/acquisition/resume")
def resume_incident_task(
    incident_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """Resume the incident's original task from its latest durable checkpoint."""
    from ..recovery.acquire_handlers import resume_callback

    engine = _engine()
    incident = engine.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    task_id = incident.get("taskId")
    manager = getattr(service, "tasks", None)
    if not task_id or manager is None:
        raise HTTPException(
            status_code=409,
            detail="the incident names no task to resume, or the task runtime is unavailable",
        )
    result = resume_callback(manager, str(task_id))()
    return {"success": True, "resume": result}


@router.post("/recovery/incidents/{incident_id}/reproduce")
async def reproduce(
    incident_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = await _engine().reproduce_incident(incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return result


@router.post("/recovery/promote")
def promote(
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    engine = _engine()
    min_occurrences = int(payload.get("minOccurrences", 2))
    result = engine.promote_incidents(
        min_occurrences=max(2, min_occurrences),
        limit=int(payload.get("limit", 50)),
    )
    return result


@router.post("/recovery/incidents/{incident_id}/outcome")
def record_outcome(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    engine = _engine()
    outcome = str(payload.get("outcome") or "").strip()
    if outcome not in ("succeeded", "resolved", "failed", "exhausted"):
        raise HTTPException(status_code=400, detail="unknown outcome")
    attempt = engine.record_outcome(incident_id, outcome=outcome, detail=payload.get("detail"))
    if attempt is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"attempt": attempt}

@router.post("/runs/{run_id}/guardrail-reset")
def reset_tool_guardrail(
    run_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """Clear a run's tool-loop guardrail ledger before its next decision.

    Process-local by design: the ledger is per attempt, never durable. A resume
    already starts clean; this endpoint lets an operator unstick a live run
    without restarting the process. Nothing about a tool result is changed.
    """
    from ..tool_guardrails import request_reset

    if not service.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    request_reset(run_id)
    return {"success": True, "runId": run_id, "reset": True}
