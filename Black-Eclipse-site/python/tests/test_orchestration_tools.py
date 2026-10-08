"""The orchestration tool surface: registration, handlers and least privilege."""

from __future__ import annotations

import pytest

from harness.orchestration.runner import narrow_allowed
from harness.orchestration.tools import (
    TOOL_NAMES,
    dependency_graph_handler,
    engine_for,
    execution_cancel_handler,
    execution_status_handler,
    forget_engine,
    parallel_execute_handler,
    register_orchestration_tools,
    task_batch_handler,
    task_fork_handler,
)
from harness.tools import ToolContext, ToolDefinition, ToolRegistry

from orchestration_helpers import make_store


def _registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def echo(args, ctx):
        return f"echo:{args.get('value')}", {"value": args.get("value")}

    async def slow(args, ctx):
        import asyncio

        await asyncio.sleep(0.05)
        return "slow", {"ok": True}

    async def fetch_many(args, ctx):
        items = list(args.get("items") or [])
        return f"fetched {len(items)}", [{"quote": value} for value in items]

    for name, handler in (("echo", echo), ("slow", slow), ("fetch_many", fetch_many)):
        registry.register(ToolDefinition(
            name=name, description=name,
            input_schema={"type": "object",
                          "properties": {"value": {"type": "string"},
                                         "items": {"type": "array"}}},
            handler=handler, permission="read", risk="low",
        ))
    return registry


def _ctx(store, registry, allowed):
    return ToolContext(
        run_id="orch-tool-run", log=lambda *a, **k: None,
        memory_store=store, tool_registry=registry, allowed=allowed,
    )


def test_tools_are_registered():
    registry = ToolRegistry()
    register_orchestration_tools(registry)
    assert set(TOOL_NAMES) <= set(registry.names())


async def test_parallel_execute_handler_runs_tool_nodes(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", "slow", *TOOL_NAMES})
    text, data = await parallel_execute_handler({
        "tasks": [
            {"id": "a", "kind": "tool", "tool": "echo", "args": {"value": "x"}},
            {"id": "b", "kind": "tool", "tool": "slow"},
        ],
    }, ctx)
    assert data["status"] == "COMPLETED"
    assert data["successfulTasks"] == 2
    assert "Ran 2 task" in text


async def test_parallel_execute_runs_through_registry_execute(tmp_path):
    # The model calls tools via registry.execute, which builds a pydantic args
    # model from the JSON schema. This proves the schema is executable.
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", *TOOL_NAMES})
    result = await registry.execute("parallel_execute", "c1", {
        "tasks": [
            {"id": "a", "kind": "tool", "tool": "echo", "args": {"value": "x"}},
            {"id": "b", "kind": "tool", "tool": "echo", "args": {"value": "x"},
             "dependsOn": ["a"], "priority": "HIGH"},
        ],
    }, ctx)
    assert result.ok
    assert result.data["status"] == "COMPLETED"
    assert result.data["successfulTasks"] == 2


async def test_task_fork_returns_an_id(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", *TOOL_NAMES})
    _, data = await task_fork_handler({
        "tasks": [{"id": "a", "kind": "tool", "tool": "echo", "args": {"value": "x"}}],
    }, ctx)
    assert data["forkId"].startswith("exec_")


async def test_task_batch_handler_coalesces(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", "slow", "fetch_many", *TOOL_NAMES})
    text, data = await task_batch_handler({
        "items": [{"item": "AAPL"}, {"item": "MSFT"}, {"item": "NVDA"}],
        "template": {"kind": "tool", "tool": "fetch_many"},
        "batchKey": "quotes",
    }, ctx)
    assert data["status"] == "COMPLETED"
    assert data["successfulTasks"] == 3
    quotes = sorted(int(n["output"]["quote"] is not None) for n in data["nodes"])
    assert quotes == [1, 1, 1]


async def test_dependency_graph_and_status_handlers(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", *TOOL_NAMES})
    _, data = await parallel_execute_handler({
        "tasks": [
            {"id": "a", "kind": "tool", "tool": "echo", "args": {"value": "x"}},
            {"id": "b", "kind": "tool", "tool": "echo", "args": {"value": "x"},
             "dependsOn": ["a"]},
        ],
    }, ctx)
    execution_id = data["executionId"]
    _, graph = dependency_graph_handler({"executionId": execution_id}, ctx)
    assert graph["total"] == 2
    assert len(graph["edges"]) == 1
    assert graph["criticalPath"]
    _, status = execution_status_handler({"executionId": execution_id}, ctx)
    assert status["status"] == "COMPLETED"
    # Unknown execution is refused, not silently empty.
    text, _ = execution_status_handler({"executionId": "nope"}, ctx)
    assert "REFUSED" in text


async def test_engine_is_cached_per_run(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", *TOOL_NAMES})
    first = engine_for(ctx)
    second = engine_for(ctx)
    assert first is second
    forget_engine(ctx.run_id)
    assert engine_for(ctx) is not first


async def test_execution_cancel_handler_on_unknown_is_false(tmp_path):
    store = make_store(tmp_path)
    registry = _registry()
    register_orchestration_tools(registry)
    ctx = _ctx(store, registry, {"echo", *TOOL_NAMES})
    _, data = await execution_cancel_handler({"executionId": "missing"}, ctx)
    assert data["cancelled"] is False


def test_least_privilege_tool_narrowing():
    parent = {"echo", "slow", "other"}
    assert narrow_allowed(parent, ["echo"]) == {"echo"}
    # A requested tool the parent does not hold is dropped, never granted.
    assert narrow_allowed(parent, ["echo", "secret"]) == {"echo"}
    # No request inherits the parent's own allowlist.
    assert narrow_allowed(parent, None) == parent
    # No parent allowlist, but a request restricts.
    assert narrow_allowed(None, ["echo"]) == {"echo"}
    assert narrow_allowed(None, None) is None
