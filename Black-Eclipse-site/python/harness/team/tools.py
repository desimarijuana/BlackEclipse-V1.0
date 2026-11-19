"""The model-facing bot-team tools, on the ONE tool registry.

They resolve a per-run `TeamService` from the `ToolContext` (rebuilt from
`ctx.memory_store` and the A2A layer, exactly like the task/A2A/orchestration
tools — no new ToolContext fields, no change to `execute_run`). A `team_run`
creates durable tasks; the process `TaskScheduler` dispatches them. Permission is
`read`: a team run is agent-local orchestration state, not an external mutation.
"""

from __future__ import annotations

import logging
from typing import Any

from ..a2a.tools import a2a_for
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .model import TeamDefinition, TeamRun
from .service import TeamError, TeamService

log = logging.getLogger("harness.team.tools")

TEAM_TOOLS: tuple[str, ...] = (
    "team_run",
    "team_status",
    "team_result",
    "team_review",
    "team_cancel",
)


class _ContextHost:
    """The minimal host a `TeamService` needs, built from a live ToolContext."""

    def __init__(self, ctx: ToolContext) -> None:
        self.store = ctx.memory_store
        self.bus = getattr(ctx, "bus", None)
        self.evidence_store = getattr(ctx, "evidence_store", None)
        self.registry = getattr(ctx, "tool_registry", None)
        self.tasks = None

    def run(self, *_args: Any, **_kwargs: Any):  # pragma: no cover - not executed here
        raise RuntimeError("the per-run team host does not execute runs")


_CACHE: dict[tuple[str, int], TeamService] = {}
_MAX_CACHED = 64


def team_for(ctx: ToolContext) -> TeamService:
    """The per-run TeamService, cached by (runId, store identity)."""
    key = (ctx.run_id or "anonymous", id(ctx.memory_store))
    service = _CACHE.get(key)
    if service is None:
        if len(_CACHE) >= _MAX_CACHED:
            _CACHE.pop(next(iter(_CACHE)))
        service = TeamService(_ContextHost(ctx), a2a=a2a_for(ctx))
        _CACHE[key] = service
    return service


def forget_team(run_id: str) -> None:
    for key in [k for k in _CACHE if k[0] == run_id]:
        _CACHE.pop(key, None)


def _ok(text: str, data: dict[str, Any]) -> tuple[str, Any]:
    return text, {"status": "ok", **data}


def _refused(exc: TeamError) -> tuple[str, Any]:
    return f"Couldn't run that team: {exc.reason}", {
        "status": "refused", "code": exc.code, "reason": exc.reason, "detail": exc.detail,
    }


# ── handlers ───────────────────────────────────────────────────────────────────


async def team_run_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = team_for(ctx)
    raw = args.get("team")
    if not isinstance(raw, dict):
        return "Provide a team object with members and subtasks.", {
            "status": "refused", "code": "TEAM_INVALID", "reason": "missing team object",
        }
    try:
        team = TeamDefinition(**raw)
    except Exception as exc:  # noqa: BLE001 - a malformed team is refused, never guessed
        return f"That team is not valid: {exc}", {
            "status": "refused", "code": "TEAM_INVALID", "reason": str(exc),
        }
    model_settings = args.get("modelSettings") if isinstance(args.get("modelSettings"), dict) else None
    try:
        run: TeamRun = await service.run(team, model_settings=model_settings)
    except TeamError as exc:
        return _refused(exc)
    return (
        f"Started team {team.name!r}: {len(run.subtask_task_ids)} subtasks "
        f"(team run {run.id}).",
        {"teamRun": run.model_dump(by_alias=True)},
    )


def team_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = team_for(ctx)
    try:
        status = service.status(str(args.get("runId") or ""))
    except TeamError as exc:
        return _refused(exc)
    team = status["team"]
    working = [s["subtaskId"] for s in status["subtasks"] if s["status"] in ("IN_PROGRESS", "VERIFYING")]
    return (
        f"Team run {team['id']} is {team['status']}; "
        f"{len(status['subtasks'])} subtasks, {len(working)} running.",
        {"teamStatus": status},
    )


def team_result_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = team_for(ctx)
    try:
        text = service.synthesize(str(args.get("runId") or ""))
    except TeamError as exc:
        return _refused(exc)
    return text, {"teamResult": text}


async def team_review_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = team_for(ctx)
    try:
        result = await service.finalize(
            str(args.get("runId") or ""),
            reviewer_agent_id=str(args.get("reviewerAgentId") or "qa-agent"),
        )
    except TeamError as exc:
        return _refused(exc)
    return f"Team review: {result.get('reviewOutcome') or result.get('status')}.", {"teamReview": result}


async def team_cancel_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = team_for(ctx)
    try:
        result = await service.cancel(str(args.get("runId") or ""))
    except TeamError as exc:
        return _refused(exc)
    return f"Cancelled {len(result['cancelledTaskIds'])} task(s).", {"teamCancel": result}


# ── schemas / registration ─────────────────────────────────────────────────────


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [],
            "additionalProperties": False}


def _str(desc: str = "") -> dict[str, Any]:
    return {"type": "string", "description": desc} if desc else {"type": "string"}


_TEAM_SCHEMA = _obj({
    "id": _str("A stable id for this team."),
    "name": _str("A human name for the team."),
    "objective": _str("The shared objective."),
    "agentId": _str("The lead/delegator agent id (default eclipse-orchestrator)."),
    "members": {
        "type": "array",
        "items": _obj({
            "agentId": _str("The runtime agent id of the member bot."),
            "role": _str("specialist | lead | reviewer"),
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "maxConcurrency": {"type": "integer"},
            "tools": {"type": "array", "items": {"type": "string"}},
            "instructions": _str("Extra system instructions (narrowing only)."),
            "label": _str("Optional display label."),
        }, ["agentId"]),
    },
    "subtasks": {
        "type": "array",
        "items": _obj({
            "id": _str("A stable subtask id."),
            "objective": _str("The one objective for this subtask."),
            "capability": _str("A capability noun used to route to a member."),
            "assignedAgentId": _str("An explicit member agent id."),
            "dependsOn": {"type": "array", "items": {"type": "string"}},
            "required": {"type": "boolean"},
            "expectedOutput": {"type": "object"},
            "inputRefs": {"type": "array", "items": {"type": "string"}},
            "review": {"type": "boolean"},
            "priority": _str("LOW | NORMAL | HIGH | URGENT | CRITICAL"),
        }, ["id", "objective"]),
    },
    "policy": {
        "type": "object",
        "properties": {
            "delegationEnabled": {"type": "boolean"},
            "maxDepth": {"type": "integer"},
            "maxChildren": {"type": "integer"},
            "maxConcurrency": {"type": "integer"},
            "perAgentConcurrency": {"type": "integer"},
            "maxTasks": {"type": "integer"},
            "maxCost": {"type": "number"},
            "maxRuntimeMs": {"type": "integer"},
            "requireReview": {"type": "boolean"},
            "reviewStrictness": _str("NONE | LENIENT | STANDARD | STRICT"),
            "optionalFailurePolicy": _str("ALLOW_PARTIAL | REQUIRE_ALL"),
            "requireApproval": {"type": "boolean"},
        },
    },
}, ["id", "name", "members", "subtasks"])


def _definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="team_run",
            description=(
                "Start a team of specialist bots on one objective. Provide members "
                "(runtime agent ids) and a dependency-aware list of subtasks; each "
                "subtask runs as that bot through the real runtime. Returns a durable "
                "team-run handle immediately (non-blocking)."
            ),
            input_schema=_obj({"team": _TEAM_SCHEMA, "modelSettings": {"type": "object"}},
                              ["team"]),
            handler=team_run_handler,
        ),
        ToolDefinition(
            name="team_status",
            description="Show which bots are working on a team run, each subtask's status, and what is blocking.",
            input_schema=_obj({"runId": _str("The team run id.")}, ["runId"]),
            handler=team_status_handler,
        ),
        ToolDefinition(
            name="team_result",
            description="Synthesize a team run's validated results, disclosing any unresolved conflicts.",
            input_schema=_obj({"runId": _str("The team run id.")}, ["runId"]),
            handler=team_result_handler,
        ),
        ToolDefinition(
            name="team_review",
            description=(
                "Run the independent quality review for a finished team run: reconcile "
                "conflicts, review the actual artifacts and, if required, queue bounded "
                "repairs for re-verification."
            ),
            input_schema=_obj({"runId": _str("The team run id."),
                               "reviewerAgentId": _str("The independent reviewer (default qa-agent).")},
                              ["runId"]),
            handler=team_review_handler,
        ),
        ToolDefinition(
            name="team_cancel",
            description="Cancel a team run and propagate cancellation to its subtasks.",
            input_schema=_obj({"runId": _str("The team run id.")}, ["runId"]),
            handler=team_cancel_handler,
        ),
    ]


def register_team_tools(registry: ToolRegistry) -> list[str]:
    """Register the team tools, skipping any name already taken. Returns names added."""
    names: list[str] = []
    for tool in _definitions():
        if registry.get(tool.name) is not None:
            continue
        registry.register(tool)
        names.append(tool.name)
    return names


# ── the prerequisite-memo hand-off (read-only) ─────────────────────────────────

_READ_OUTPUT_MAX_CHARS = 20_000
_READ_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "runId": {
            "type": "string",
            "description": "The run id of a completed prerequisite (listed in the task context).",
        },
    },
    "required": ["runId"],
}


async def read_run_output(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Read a completed prerequisite run's final output by its run id.

    A downstream stage does not inherit an upstream agent's prose: the task
    context names the prerequisite (`output: <runId>`) and this tool reads the ONE
    run store. No second transcript, no prompt-injected memory.
    """
    run_id = str(args.get("runId") or "").strip()
    if not run_id:
        return "Provide the prerequisite runId.", {
            "ok": False, "code": "INVALID_ARGUMENT", "message": "runId is required",
        }
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return "The run store is unavailable in this run.", {
            "ok": False, "code": "RUNTIME_UNAVAILABLE",
        }
    try:
        run = store.get_run(run_id)
    except Exception as exc:  # noqa: BLE001 - a missing run is an honest refusal
        return f"Could not read run {run_id}: {exc}", {
            "ok": False, "code": "RUN_READ_FAILED", "runId": run_id,
        }
    if not run:
        return f"No run {run_id!r} exists.", {
            "ok": False, "code": "RUN_NOT_FOUND", "runId": run_id,
        }
    status = str(run.get("status") or "")
    output = str(run.get("output") or "")
    if not output.strip():
        return (
            f"Run {run_id} is {status or 'unknown'} and produced no output.",
            {"ok": False, "code": "RUN_OUTPUT_EMPTY", "runId": run_id, "status": status},
        )
    bounded = output[:_READ_OUTPUT_MAX_CHARS]
    return (
        f"Run {run_id} ({status or 'unknown'}) output:\n\n{bounded}",
        {
            "ok": True,
            "runId": run_id,
            "status": status,
            "output": bounded,
            "truncated": len(output) > len(bounded),
        },
    )


def register_run_output_tool(registry: ToolRegistry) -> list[str]:
    """Register `read_run_output`. Idempotent like every other layer."""
    if registry.get("read_run_output") is not None:
        return []
    registry.register(ToolDefinition(
        name="read_run_output",
        description=(
            "Read a completed prerequisite run's final output by its run id. "
            "Use it to read the brief, debate record, proposal or verdict handed "
            "to your stage."
        ),
        input_schema=_READ_OUTPUT_SCHEMA,
        handler=read_run_output,
        permission="read",
        risk="low",
        timeout_ms=10_000,
    ))
    return ["read_run_output"]


__all__ = [
    "TEAM_TOOLS",
    "forget_team",
    "read_run_output",
    "register_run_output_tool",
    "register_team_tools",
    "team_for",
]
