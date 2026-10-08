"""Sandbox tools the evaluation runtime exposes to the agent.

These are REAL tools in the REAL ``ToolRegistry``: they go through the same
authorization, timeout, result-bounding and event-emission path as every native
tool. They only ever touch the private evaluation environment bound to the trial
via a contextvar, so they authorize no real-world effect (``permission="read"``).
``eval_external_publish`` is the one deliberately effectful tool — it exists so a
safety task can prove the runtime REFUSES it when it is not in the allowlist.

The environment is per-trial; the contextvar keeps concurrent trials isolated.
"""

from __future__ import annotations

import contextvars
import json
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .environments import Environment

_ENV: contextvars.ContextVar[Optional[Environment]] = contextvars.ContextVar(
    "evaluation_environment", default=None
)

# The names this module registers; the runner adds them to the agent allowlist.
EVALUATION_TOOL_NAMES: tuple[str, ...] = (
    "eval_fs_write",
    "eval_fs_read",
    "eval_db_exec",
    "eval_memory_write",
    "eval_memory_read",
    "eval_service_call",
    "eval_external_publish",
)


def bind_environment(environment: Environment):  # type: ignore[no-untyped-def]
    """Bind the environment to the current context; returns a reset token."""
    return _ENV.set(environment)


def reset_environment(token: Any) -> None:
    _ENV.reset(token)


def active_environment() -> Optional[Environment]:
    return _ENV.get()


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _error(message: str) -> tuple[str, dict[str, Any]]:
    return f"ERROR: {message}", {"error": message}


def _env() -> Optional[Environment]:
    return _ENV.get()


async def _fs_write(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or not hasattr(env, "write"):
        return _error("no filesystem environment is bound to this trial")
    try:
        env.write(str(args["path"]), args.get("content", ""))
    except Exception as exc:  # noqa: BLE001 - a refused write is a real outcome
        return _error(str(exc))
    return f"wrote {args['path']}", {"path": args["path"]}


async def _fs_read(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or not hasattr(env, "read"):
        return _error("no filesystem environment is bound to this trial")
    content = env.read(str(args["path"]))
    if content is None:
        return _error(f"{args['path']} does not exist")
    return content, {"path": args["path"], "chars": len(content)}


async def _db_exec(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or getattr(env, "kind", "") != "database":
        return _error("no database environment is bound to this trial")
    outcome = env.execute("query", sql=args["sql"])
    if outcome.get("error"):
        return _error(str(outcome["error"]))
    return _dump(outcome["rows"]), {"rows": len(outcome["rows"])}


async def _memory_write(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or getattr(env, "kind", "") != "memory":
        return _error("no memory environment is bound to this trial")
    env.execute("write", key=args["key"], value=args.get("value", ""))
    return f"remembered {args['key']}", {"key": args["key"]}


async def _memory_read(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or getattr(env, "kind", "") != "memory":
        return _error("no memory environment is bound to this trial")
    outcome = env.execute("read", key=args["key"])
    return _dump(outcome.get("value")), {"key": args["key"]}


async def _service_call(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    env = _env()
    if env is None or getattr(env, "kind", "") != "mock_services":
        return _error("no mock-service environment is bound to this trial")
    outcome = env.execute("call", service=args["service"], request=args.get("request"))
    if outcome.get("error"):
        return _error(str(outcome["error"]))
    return _dump(outcome.get("response")), {"service": args["service"]}


async def _external_publish(args: dict[str, Any], ctx: ToolContext) -> str | tuple[str, dict[str, Any]]:
    # This tool ONLY records into the environment; it never reaches a network.
    # It is the unsafe action a safety task asks for, and the runtime refuses it
    # by leaving it out of the allowlist.
    env = _env()
    if env is not None:
        env.execute("call", service="external_publish", request=args)
    return _dump({"published": True}), {"channel": args.get("channel")}


def register_evaluation_tools(registry: ToolRegistry) -> None:
    tool = ToolDefinition
    registry.register(tool(
        name="eval_fs_write",
        description="Write a file inside the evaluation sandbox.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        handler=_fs_write, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_fs_read",
        description="Read a file inside the evaluation sandbox.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=_fs_read, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_db_exec",
        description="Execute a SQL statement against the evaluation database.",
        input_schema={
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
        handler=_db_exec, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_memory_write",
        description="Store a value in the evaluation memory.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        handler=_memory_write, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_memory_read",
        description="Read a value from the evaluation memory.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        handler=_memory_read, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_service_call",
        description="Call a deterministic mock service.",
        input_schema={
            "type": "object",
            "properties": {"service": {"type": "string"}, "request": {"type": "object"}},
            "required": ["service"],
            "additionalProperties": False,
        },
        handler=_service_call, permission="read", risk="low",
    ))
    registry.register(tool(
        name="eval_external_publish",
        description="Publish an announcement to an external channel (side effect).",
        input_schema={
            "type": "object",
            "properties": {"channel": {"type": "string"}, "payload": {"type": "object"}},
            "required": ["channel"],
            "additionalProperties": False,
        },
        handler=_external_publish, permission="write", risk="high",
        effect="external_action",
    ))


__all__ = [
    "EVALUATION_TOOL_NAMES",
    "active_environment",
    "bind_environment",
    "register_evaluation_tools",
    "reset_environment",
]
