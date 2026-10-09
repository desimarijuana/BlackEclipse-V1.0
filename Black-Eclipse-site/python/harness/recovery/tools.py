"""Agent-facing read tools for the recovery engine.

These let the model (and the UI) inspect what Eclipse has learned about its own
failures: the recorded incidents, the recovery decision taken for each, and the
attempt history. They are READ-ONLY by construction — the model never decides
budgets or performs a recovery action through a tool; those are the controller's
job and the operator's. Resolution uses a process-wide singleton, the same
pattern the terminal subsystem uses, so a handler carries no store.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry

_SERVICE: Any = None


def set_recovery_service(service: Any) -> None:
    global _SERVICE
    _SERVICE = service


def get_recovery_service() -> Any:
    return _SERVICE


def _service() -> Any:
    if _SERVICE is None:
        raise RuntimeError("recovery engine is not installed")
    return _SERVICE


def _incident_view(incident: dict[str, Any]) -> dict[str, Any]:
    """A compact, non-secret projection for a tool result."""
    return {
        "id": incident["id"],
        "kind": incident["kind"],
        "retryability": incident["retryability"],
        "code": incident["code"],
        "subsystem": incident["subsystem"],
        "source": incident["source"],
        "status": incident["status"],
        "occurrences": incident["occurrenceCount"],
        "attempts": incident["attempts"],
        "taskId": incident["taskId"],
        "lastSeenAt": incident["lastSeenAt"],
        "decision": incident.get("decision"),
        "diagnosis": incident.get("diagnosis"),
    }


async def recovery_incidents_handler(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    svc = _service()
    status = args.get("status")
    task_id = args.get("task_id")
    limit = int(args.get("limit") or 20)
    incidents = svc.list_incidents(status=status, task_id=task_id, limit=limit)
    views = [_incident_view(i) for i in incidents]
    if not views:
        return ("No recovery incidents recorded.", {"incidents": []})
    lines = [f"{len(views)} recovery incident(s):"]
    for v in views:
        lines.append(
            f"- [{v['kind']}/{v['status']}] {v['code'] or 'error'} in {v['subsystem']} "
            f"x{v['occurrences']} -> {(v['decision'] or {}).get('strategy') or 'n/a'} ({v['id']})"
        )
    return ("\n".join(lines), {"incidents": views})


async def recovery_incident_handler(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    svc = _service()
    incident_id = str(args.get("incident_id") or "").strip()
    if not incident_id:
        return ("Provide an incident_id.", {"error": "missing incident_id"})
    incident = svc.get_incident(incident_id)
    if incident is None:
        return (f"No incident {incident_id}.", {"error": "not_found"})
    attempts = svc.incident_attempts(incident_id)
    detail = _incident_view(incident)
    detail["message"] = incident.get("message")
    detail["attemptHistory"] = attempts
    return (f"Incident {incident_id}: {incident['kind']} ({incident['occurrenceCount']}x).",
            {"incident": detail})


async def recovery_summary_handler(_args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    svc = _service()
    summary = svc.summary()
    return (
        f"{summary['incidents']} incident(s) across {len(summary['byKind'])} kind(s); "
        f"{summary['attempts']} attempt(s).",
        summary,
    )


async def recovery_diagnose_handler(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    svc = _service()
    incident_id = str(args.get("incident_id") or "").strip()
    if not incident_id:
        return ("Provide an incident_id.", {"error": "missing incident_id"})
    diagnosis = svc.diagnose_incident(incident_id)
    if diagnosis is None:
        return (f"No incident {incident_id}.", {"error": "not_found"})
    if diagnosis.get("decisive"):
        text = f"{incident_id}: root cause = {diagnosis['selected']} (confidence {diagnosis['confidence']})."
    else:
        text = f"{incident_id}: root cause undetermined; {len(diagnosis.get('missingInformation', []))} evidence gap(s)."
    return (text, {"diagnosis": diagnosis})


async def recovery_discover_handler(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    svc = _service()
    query = str(args.get("query") or "").strip()
    if not query:
        return ("Provide a query describing the capability you need.", {"error": "missing query"})
    matches = svc.discover(query, limit=int(args.get("limit") or 8))
    plan = svc.plan_acquisition(query)
    if not matches:
        return (f"No configured capability matches '{query}'.", {"matches": [], "plan": plan})
    lines = [f"Capabilities matching '{query}':"]
    for m in matches:
        cap = m["capability"]
        lines.append(f"- {cap['id']} ({cap['kind']}, {cap['provenance']}) available={cap['available']}")
    return ("\n".join(lines), {"matches": matches, "plan": plan})


def register_recovery_tools(registry: ToolRegistry) -> None:
    """Register the read tools, idempotently.

    The tool registry is process-wide and boot runs more than once in a test
    process (one lifespan per client), so a blind re-register would raise
    "already registered". Only names not already present are added.
    """
    existing = set(registry.names())
    definitions = [
        ToolDefinition(
            name="recovery_incidents",
            description="List recorded failure incidents and the recovery decision taken for each.",
            input_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "resolved", "failed"]},
                    "task_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            handler=recovery_incidents_handler,
            permission="read",
            risk="none",
        ),
        ToolDefinition(
            name="recovery_incident",
            description="Inspect one failure incident: classification, diagnosis, decision and attempt history.",
            input_schema={
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
            handler=recovery_incident_handler,
            permission="read",
            risk="none",
        ),
        ToolDefinition(
            name="recovery_summary",
            description="Roll-up of recorded failure incidents by status and kind.",
            input_schema={"type": "object", "properties": {}},
            handler=recovery_summary_handler,
            permission="read",
            risk="none",
        ),
        ToolDefinition(
            name="recovery_diagnose",
            description="Produce an evidence-ranked root-cause diagnosis for a recorded failure incident.",
            input_schema={
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
            handler=recovery_diagnose_handler,
            permission="read",
            risk="none",
        ),
        ToolDefinition(
            name="recovery_discover",
            description="Find configured capabilities (tools/providers/skills) that fit a described need, with an acquisition plan.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
            handler=recovery_discover_handler,
            permission="read",
            risk="none",
        ),
    ]
    for definition in definitions:
        if definition.name not in existing:
            registry.register(definition)


__all__ = [
    "get_recovery_service",
    "register_recovery_tools",
    "set_recovery_service",
]
