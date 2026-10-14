"""Agent-facing scheduling tools (Phase 17, repo-mapped onto the Automation engine).

`job_list` / `job_describe_template` are read-only. `job_create` writes a
DISABLED finance job from the fixed catalogue (`automation/catalogue.py`) — it
never enables anything and accepts no free-form objective. `job_run_now` runs an
already-enabled job once, visibly in this conversation (mirrors `bot_run`).

The operator's master switch (`agent_scheduling_enabled`, default OFF) is the
authority: `graph.surface_disabled_tools` removes all four tools from the bound
set when it is off, and every handler re-checks it fail-closed. Creating a job
needs no schedule approval because the job cannot run until the OPERATOR turns
it on under Scheduled Jobs — "discovery is not activation" holds at the top of
the chain.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..jobs.templates import get_template, instantiate
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .catalogue import catalogue_issues, get_shape, list_shapes, shape_public
from .legacy import job_definition_to_automation

TOOL_NAMES = (
    "job_list",
    "job_describe_template",
    "job_create",
    "job_run_now",
)

#: The tag every catalogue-created job carries, so `job_list` and the tools can
#: tell a scheduled FINANCE JOB apart from a bot or an operator-authored row.
JOB_TAG = "job"

_SWITCH_OFF_TEXT = (
    "Eclipse isn't set up to schedule work on its own right now. You can turn "
    "that on in Eclipse Memory → Policies."
)


def _require_service() -> Any:
    from .tools import get_automation_service  # noqa: PLC0415 - set at boot

    service = get_automation_service()
    if service is None:
        raise RuntimeError("the automation service is unavailable")
    return service


def _scheduling_enabled(ctx: ToolContext) -> bool:
    """The operator's master switch, read fail-closed.

    The surface gate (`graph.surface_disabled_tools`) is the primary control —
    when the switch is off the model never sees these tools. This second look
    exists so a direct call (a test, a script) cannot bypass it: an unreadable
    policy is treated as OFF.
    """
    memory = getattr(ctx, "memory_service", None)
    policy = getattr(memory, "policy", None) if memory is not None else None
    if policy is None:
        return False
    try:
        return bool(policy.get_all().get("agent_scheduling_enabled", False))
    except Exception:  # noqa: BLE001 - a policy read failure is a refusal
        return False


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _shape_views(definition: Any) -> list[str]:
    return [tag for tag in (definition.tags or []) if tag != JOB_TAG]


async def _list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _scheduling_enabled(ctx):
        return _SWITCH_OFF_TEXT, {"jobs": [], "code": "AGENT_SCHEDULING_OFF"}
    service = _require_service()
    limit = int(args.get("limit") or 100)
    definitions = service.list(limit=limit, scope_id=args.get("scopeId"))
    jobs: list[dict[str, Any]] = []
    for definition in definitions:
        if JOB_TAG not in (definition.tags or []):
            continue
        jobs.append({
            "id": definition.id,
            "name": definition.name,
            "state": definition.state,
            "shape": (_shape_views(definition) or [None])[0],
            "nextRunAt": definition.next_run_at,
            "lastRunAt": definition.last_run_at,
            "switchedOn": definition.state == "active",
        })
    return _dumps({"count": len(jobs), "jobs": jobs}), {"jobs": jobs}


async def _describe_template(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _scheduling_enabled(ctx):
        return _SWITCH_OFF_TEXT, {"shape": None, "code": "AGENT_SCHEDULING_OFF"}
    shape_id = str(args.get("shapeId") or "").strip()
    shape = get_shape(shape_id)
    if shape is None:
        views = list_shapes()
        names = ", ".join(view["id"] for view in views)
        return (
            f"There's no ready-made job called {shape_id!r}. The ones I can set up: {names}.",
            {"shape": None, "code": "UNKNOWN_SHAPE", "available": [v["id"] for v in views]},
        )
    view = shape_public(shape)
    return _dumps(view), view


async def _create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _scheduling_enabled(ctx):
        return _SWITCH_OFF_TEXT, {"created": False, "code": "AGENT_SCHEDULING_OFF"}
    shape_id = str(args.get("shapeId") or "").strip()
    shape = get_shape(shape_id)
    if shape is None:
        names = ", ".join(view["id"] for view in list_shapes())
        return (
            f"There's no ready-made job called {shape_id!r}. The ones I can set up: {names}.",
            {"created": False, "code": "UNKNOWN_SHAPE"},
        )
    params_raw = args.get("params") or {}
    if not isinstance(params_raw, dict):
        return "The job details must be a set of named answers.", {"created": False, "code": "INVALID_PARAMS"}
    allowed = set(shape.required_params) | set(shape.optional_params)
    unknown = sorted(key for key in params_raw if key not in allowed)
    if unknown:
        return (
            f"I don't know what to do with {', '.join(unknown)} for this job.",
            {"created": False, "code": "UNKNOWN_PARAM", "params": unknown},
        )
    params = {key: params_raw[key] for key in params_raw if str(params_raw[key] or "").strip()}
    missing = [key for key in shape.required_params if key not in params]
    if missing:
        return (
            f"I still need: {', '.join(missing)}.",
            {"created": False, "code": "MISSING_PARAM", "params": missing},
        )
    if get_template(shape.template_id) is None:
        return (
            "That job isn't available in this copy of Eclipse.",
            {"created": False, "code": "TEMPLATE_MISSING"},
        )
    try:
        job = instantiate(shape.template_id, params, name=args.get("name") or None)
    except Exception as exc:  # noqa: BLE001 - a template error is a refusal
        return f"I couldn't build that job: {exc}", {"created": False, "code": "SAVE_FAILED", "error": str(exc)[:300]}
    automation = job_definition_to_automation(job)
    automation = automation.model_copy(update={
        "state": "disabled",   # discovery is not activation — the operator turns it on
        "tags": [JOB_TAG, shape.id],
        "delivery": automation.delivery.model_copy(update={"adapter": shape.delivery}),
    })
    try:
        saved = _require_service().create_definition(automation, created_by="agent")
    except Exception as exc:  # noqa: BLE001 - a save error is reported, never raised
        return f"I couldn't save that job: {exc}", {"created": False, "code": "SAVE_FAILED", "error": str(exc)[:300]}
    view = saved.public()
    data = {
        "created": True, "jobId": saved.id, "name": saved.name,
        "switchedOn": False, "state": saved.state, "job": view,
    }
    return (
        f"Saved “{saved.name}” — it's switched off. Turn it on under Scheduled "
        f"Jobs when you want it to run.",
        data,
    )


async def _run_now(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _scheduling_enabled(ctx):
        return _SWITCH_OFF_TEXT, {"started": False, "code": "AGENT_SCHEDULING_OFF"}
    service = _require_service()
    job_id = str(args.get("jobId") or "").strip()
    definition = service.get(job_id)
    if definition is None:
        return f"No scheduled job {job_id!r}.", {"started": False, "code": "NOT_FOUND"}
    if JOB_TAG not in (definition.tags or []):
        return (
            f"{job_id!r} isn't a scheduled job — I didn't run it.",
            {"started": False, "code": "NOT_A_JOB"},
        )
    if definition.state != "active":
        return (
            f"“{definition.name}” is switched off, so I didn't run it. Turn it on "
            f"under Scheduled Jobs first.",
            {"started": False, "code": "NOT_ACTIVE", "state": definition.state},
        )
    execution_id = await service.run_now(job_id, trigger_ref="agent")
    if execution_id is None:
        return f"Couldn't start “{definition.name}”.", {"started": False, "code": "START_FAILED"}
    return (
        _dumps({"started": True, "jobId": job_id, "executionId": execution_id}),
        {"started": True, "jobId": job_id, "executionId": execution_id},
    )


def register_scheduling_tools(registry: ToolRegistry) -> list[str]:
    """Register the scheduling tools. Idempotent per name."""
    definitions = [
        ToolDefinition(
            name="job_list",
            description=(
                "List the user's scheduled finance jobs (name, whether it is on, "
                "and when it next runs). Read-only."
            ),
            input_schema=_obj({
                "scopeId": {"type": "string"},
                "limit": {"type": "integer"},
            }),
            handler=_list, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="job_describe_template",
            description=(
                "Describe one ready-made job shape from the scheduling catalogue: "
                "what it does and which answers it needs. Read-only."
            ),
            input_schema=_obj({"shapeId": {"type": "string"}}, ["shapeId"]),
            handler=_describe_template, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="job_create",
            description=(
                "Set up a recurring finance job from the fixed catalogue (a shape id "
                "plus its parameter answers). The job is ALWAYS saved switched off; "
                "only the user can turn it on under Scheduled Jobs. Never invent a "
                "shape id — call job_describe_template first when unsure."
            ),
            input_schema=_obj({
                "shapeId": {"type": "string"},
                "params": {"type": "object"},
                "name": {"type": "string"},
            }, ["shapeId", "params"]),
            handler=_create, permission="write", risk="low", timeout_ms=30_000,
            effect="write",
        ),
        ToolDefinition(
            name="job_run_now",
            description=(
                "Run an existing, switched-on scheduled job once, right now. Refuses "
                "when the job is switched off."
            ),
            input_schema=_obj({"jobId": {"type": "string"}}, ["jobId"]),
            handler=_run_now, permission="read", risk="low", timeout_ms=30_000,
        ),
    ]
    added: list[str] = []
    for definition in definitions:
        if registry.get(definition.name) is None:
            registry.register(definition)
            added.append(definition.name)
    return added


__all__ = [
    "JOB_TAG",
    "TOOL_NAMES",
    "catalogue_issues",
    "register_scheduling_tools",
]
