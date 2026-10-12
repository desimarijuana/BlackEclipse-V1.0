"""LLM-facing tools for the Bot / Automation workspace.

These register on the SAME tool registry as every other subsystem, so
validation, permission and effect authorization apply unchanged. They are thin
wrappers over the ONE `AutomationService`, so the chat agent and the Bots UI can
never disagree about what a bot is or what it is doing.

A "bot" is an automation whose action is `run_agent`: a durable, scheduled agent
that keeps running in the background. Creation persists through the same
validated service the UI uses; nothing is claimed until the store confirms it.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry

TOOL_NAMES = (
    "bot_create",
    "bot_list",
    "bot_get",
    "bot_update",
    "bot_run",
    "bot_pause",
    "bot_resume",
    "bot_enable",
    "bot_disable",
    "bot_delete",
    "bot_status",
    "bot_history",
    "bot_inspect_run",
)

_service: Any = None


def set_automation_service(service: Any) -> None:
    global _service
    _service = service


def get_automation_service() -> Any:
    return _service


def _require_service() -> Any:
    if _service is None:
        raise RuntimeError("the automation service is unavailable")
    return _service


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _build_trigger(args: dict[str, Any]) -> dict[str, Any]:
    kind = str(args.get("triggerType") or "manual")
    timezone = str(args.get("timezone") or "UTC")
    trigger: dict[str, Any] = {"type": kind, "timezone": timezone}
    if kind == "cron":
        trigger["cron"] = str(args.get("cron") or "")
    elif kind == "interval":
        trigger["intervalSeconds"] = int(args.get("intervalSeconds") or 0)
    elif kind == "one_time":
        trigger["runAt"] = args.get("runAt")
    return trigger


async def _create(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    objective = str(args.get("objective") or "").strip()
    name = str(args.get("name") or "").strip()
    if not objective:
        return "A bot needs an objective.", {"created": False, "reason": "objective required"}
    if not name:
        name = objective[:60]
    payload: dict[str, Any] = {
        "name": name,
        "description": args.get("description") or objective,
        "state": str(args.get("state") or "active"),
        "trigger": _build_trigger(args),
        "action": {
            "type": "run_agent",
            "objective": objective,
            "agentId": str(args.get("agentId") or "eclipse-agent"),
        },
        "tags": ["bot"],
    }
    try:
        definition = service.create(payload, created_by="agent")
    except Exception as exc:  # noqa: BLE001 - a domain error is reported, not raised
        return f"Could not create the bot: {exc}", {"created": False, "error": str(exc)}
    view = definition.public()
    return _dumps({"created": True, "bot": view}), {"created": True, "bot": view}


async def _list(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bots = service.list(
        limit=int(args.get("limit") or 100),
        scope_id=args.get("scopeId"),
        state=args.get("state"),
    )
    views = [b.public() for b in bots]
    return _dumps({"count": len(views), "bots": views}), {"bots": views}


async def _get(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    definition = service.get(bot_id)
    if definition is None:
        return f"No bot {bot_id!r}.", {"found": False, "botId": bot_id}
    view = definition.public()
    return _dumps(view), view


async def _update(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    definition = service.get(bot_id)
    if definition is None:
        return f"No bot {bot_id!r}.", {"updated": False, "botId": bot_id}
    patch: dict[str, Any] = {}
    if args.get("name") is not None:
        patch["name"] = str(args["name"])
    if args.get("objective") is not None:
        # Update the typed Action model (not a raw dict) so the service's re-type
        # step never sees an unvalidated field.
        patch["description"] = str(args["objective"])
        patch["action"] = definition.action.model_copy(update={"objective": str(args["objective"])})
    if args.get("triggerType") is not None:
        patch["trigger"] = _build_trigger(args)
    if not patch:
        return "Nothing to update.", {"updated": False, "reason": "no fields"}
    try:
        saved = service.update(bot_id, patch, updated_by="agent")
    except Exception as exc:  # noqa: BLE001
        return f"Could not update the bot: {exc}", {"updated": False, "error": str(exc)}
    view = saved.public()
    return _dumps({"updated": True, "bot": view}), {"updated": True, "bot": view}


async def _run(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    definition = service.get(bot_id)
    if definition is None:
        return f"No bot {bot_id!r}.", {"started": False, "botId": bot_id}
    if definition.state != "active":
        return f"Bot {bot_id!r} is {definition.state}; enable it before running.", {"started": False, "state": definition.state}
    execution_id = await service.run_now(bot_id)
    if execution_id is None:
        return f"Could not start bot {bot_id!r}.", {"started": False}
    return _dumps({"started": True, "executionId": execution_id}), {"started": True, "executionId": execution_id}


async def _delete(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    ok = service.delete(bot_id)
    if not ok:
        return f"No bot {bot_id!r}.", {"deleted": False}
    return _dumps({"deleted": True, "botId": bot_id}), {"deleted": True, "botId": bot_id}


async def _status(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    result = service.status(bot_id)
    if result is None:
        return f"No bot {bot_id!r}.", {"found": False}
    return _dumps(result), result


async def _history(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    bot_id = str(args.get("botId") or "")
    if service.get(bot_id) is None:
        return f"No bot {bot_id!r}.", {"found": False}
    runs = service.history(bot_id, limit=int(args.get("limit") or 20))
    return _dumps({"count": len(runs), "runs": runs}), {"runs": runs}


async def _inspect_run(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    service = _require_service()
    execution_id = str(args.get("executionId") or "")
    execution = service.get_execution(execution_id)
    if execution is None:
        return f"No run {execution_id!r}.", {"found": False}
    return _dumps(execution), execution


def register_automation_tools(registry: ToolRegistry) -> list[str]:
    """Register the bot tools. Idempotent per name (returns the ones added)."""
    definitions = [
        ToolDefinition(
            name="bot_create",
            description="Create a persistent autonomous bot (a scheduled agent) that runs in the "
            "background even after the browser closes. Set triggerType to manual, one_time, "
            "interval or cron; provide objective; optionally name, agentId, description, state.",
            input_schema=_obj({
                "name": {"type": "string"},
                "objective": {"type": "string"},
                "description": {"type": "string"},
                "agentId": {"type": "string", "enum": ["eclipse-agent", "code-navigator", "code-agent"]},
                "state": {"type": "string", "enum": ["draft", "active", "paused", "disabled"]},
                "triggerType": {"type": "string", "enum": ["manual", "one_time", "interval", "cron"]},
                "cron": {"type": "string"}, "intervalSeconds": {"type": "integer"},
                "runAt": {"type": "string"}, "timezone": {"type": "string"},
            }, ["objective"]),
            handler=_create, permission="read", risk="medium", timeout_ms=30_000,
        ),
        ToolDefinition(
            name="bot_list",
            description="List the user's bots (persistent scheduled agents).",
            input_schema=_obj({"state": {"type": "string"}, "scopeId": {"type": "string"}, "limit": {"type": "integer"}}),
            handler=_list, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_get",
            description="Get one bot's full configuration by id.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_get, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_update",
            description="Update a bot's name, objective/instructions, or schedule.",
            input_schema=_obj({
                "botId": {"type": "string"}, "name": {"type": "string"}, "objective": {"type": "string"},
                "triggerType": {"type": "string", "enum": ["manual", "one_time", "interval", "cron"]},
                "cron": {"type": "string"}, "intervalSeconds": {"type": "integer"},
                "runAt": {"type": "string"}, "timezone": {"type": "string"},
            }, ["botId"]),
            handler=_update, permission="read", risk="medium", timeout_ms=30_000,
        ),
        ToolDefinition(
            name="bot_run",
            description="Run a bot immediately without changing its schedule.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_run, permission="read", risk="low", timeout_ms=30_000,
        ),
        ToolDefinition(
            name="bot_pause", description="Pause a bot so it stops triggering (a running execution is not killed).",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_lifecycle_handler("pause"), permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_resume", description="Resume a paused bot.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_lifecycle_handler("resume"), permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_enable", description="Enable a draft/disabled bot so it becomes active.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_lifecycle_handler("enable"), permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_disable", description="Disable an active bot.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_lifecycle_handler("disable"), permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_delete", description="Delete a bot. Its run history is retained for auditing.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_delete, permission="read", risk="medium", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_status", description="Get a bot's health: next run, last run, success rate, breaker.",
            input_schema=_obj({"botId": {"type": "string"}}, ["botId"]),
            handler=_status, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_history", description="List a bot's recent runs (executions) with outcomes.",
            input_schema=_obj({"botId": {"type": "string"}, "limit": {"type": "integer"}}, ["botId"]),
            handler=_history, permission="read", risk="none", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="bot_inspect_run", description="Inspect one run: state, outcome, activity timeline and deliveries.",
            input_schema=_obj({"executionId": {"type": "string"}}, ["executionId"]),
            handler=_inspect_run, permission="read", risk="none", timeout_ms=15_000,
        ),
    ]
    added: list[str] = []
    for definition in definitions:
        if registry.get(definition.name) is None:
            registry.register(definition)
            added.append(definition.name)
    return added


def _lifecycle_handler(action: str):
    """Return a lifecycle handler. Kept sync-friendly for the definition table."""
    async def handler(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
        service = _require_service()
        bot_id = str(args.get("botId") or "")
        try:
            definition = getattr(service, action)(bot_id, actor="agent")
        except Exception as exc:  # noqa: BLE001
            return f"Could not {action} bot {bot_id!r}: {exc}", {"ok": False, "error": str(exc)}
        view = definition.public()
        data = {"ok": True, "state": view["state"], "bot": view}
        return _dumps(data), data
    return handler


__all__ = [
    "TOOL_NAMES",
    "get_automation_service",
    "register_automation_tools",
    "set_automation_service",
]
