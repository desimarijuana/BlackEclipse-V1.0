"""Production hardening: credential-aware recovery, scheduler batching, engine-scope dedup."""

from __future__ import annotations

import asyncio
import time

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.orchestration import ExecutionGraph, ExecutionStatus, NodeKind
from harness.orchestration.models import ExecutionNode, TaskStatus
from harness.orchestration.primitives import parallel_execute, task_batch
from harness.schemas import ModelSettings
from harness.tools import DataBridge

from orchestration_helpers import make_engine, make_store


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="done")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


async def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


# ── credential-aware recovery ────────────────────────────────────────────────


async def test_recovery_parks_agent_execution_until_credentials(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    engine = make_engine(store)  # boot engine: no model settings
    graph = ExecutionGraph(id="exec_agent_recover")
    node = ExecutionNode(id="a", execution_id=graph.id, kind=NodeKind.AGENT,
                         input={"query": "analyze NVDA"}, status=TaskStatus.RUNNING)
    graph.nodes = {"a": node}
    graph.status = ExecutionStatus.RUNNING
    engine.store.save_execution(graph)
    engine.store.save_nodes(graph)
    engine.store.acquire_lease(graph.id, "a", "worker-x", 60_000)

    recovered = await engine.recover()
    assert "exec_agent_recover" in recovered
    parked = engine.store.get_execution("exec_agent_recover")
    assert parked.status is ExecutionStatus.PAUSED
    assert parked.metadata.get("awaitingRuntime") is True
    # The lease from the dead process was released.
    assert engine.store.active_leases("exec_agent_recover") == []
    # No work was lost or run without credentials.
    assert parked.nodes["a"].status is TaskStatus.PENDING

    # Resume with credentials completes the agent node through execute_run.
    monkeypatch.setattr(graph_module, "build_chat_model",
                        lambda settings: ScriptedModel([AIMessage(content="NVDA looks fine")]))
    runtime = engine.runtime.extend(
        model_settings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        data_bridge=FakeBridge(),
    )
    result = await engine.resume_execution("exec_agent_recover", runtime=runtime)
    assert result.status is ExecutionStatus.COMPLETED
    assert result.successful_tasks == 1
    assert engine.store.get_execution("exec_agent_recover").metadata.get("awaitingRuntime") is None


async def test_recovery_runs_tool_only_execution_without_credentials(tmp_path):
    store = make_store(tmp_path)
    engine = make_engine(store, callables={"mark": lambda args, node: {"ok": node.id}})
    graph = ExecutionGraph(id="exec_tool_recover")
    node = ExecutionNode(id="a", execution_id=graph.id, kind=NodeKind.FUNCTION,
                         input={"function": "mark"}, status=TaskStatus.RUNNING)
    graph.nodes = {"a": node}
    graph.status = ExecutionStatus.RUNNING
    engine.store.save_execution(graph)
    engine.store.save_nodes(graph)
    recovered = await engine.recover()
    assert "exec_tool_recover" in recovered
    assert engine.get_result("exec_tool_recover").status is ExecutionStatus.COMPLETED


# ── scheduler batching ───────────────────────────────────────────────────────


async def test_scheduler_coalesces_compatible_ready_nodes(tmp_path):
    store = make_store(tmp_path)
    calls: list[list] = []

    async def fetch(args, node):
        items = list(args.get("items") or [])
        calls.append(items)
        return [{"quote": value} for value in items]

    engine = make_engine(store, callables={"fetch": fetch}, max_concurrency=8)
    tasks = [{
        "id": f"q{i}", "kind": "function",
        "input": {
            "function": "fetch", "args": {"item": i},
            "batch": {"key": "quotes", "maxSize": 100, "argField": "items", "itemField": "item"},
        },
    } for i in range(5)]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert calls == [[0, 1, 2, 3, 4]], "the five nodes should coalesce into one call"
    outputs = sorted(n["output"]["quote"] for n in result.nodes)
    assert outputs == [0, 1, 2, 3, 4]


async def test_scheduler_batching_respects_max_size(tmp_path):
    store = make_store(tmp_path)
    calls: list[int] = []

    async def fetch(args, node):
        # A lone leftover node runs with its own scalar item; a group gets `items`.
        items = list(args["items"]) if args.get("items") is not None else [args.get("item")]
        calls.append(len(items))
        return [v for v in items]

    engine = make_engine(store, callables={"fetch": fetch}, max_concurrency=8)
    tasks = [{
        "id": f"q{i}", "kind": "function",
        "input": {"function": "fetch", "args": {"item": i},
                  "batch": {"key": "quotes", "maxSize": 2, "argField": "items", "itemField": "item"}},
    } for i in range(5)]
    await parallel_execute(engine, tasks)
    assert sorted(calls) == [1, 2, 2], "maxSize=2 -> groups of two"


async def test_task_batch_primitive(tmp_path):
    store = make_store(tmp_path)
    calls: list[list] = []

    async def quote(args, node):
        items = list(args.get("items") or [])
        calls.append(items)
        return [{"symbol": s} for s in items]

    engine = make_engine(store, callables={"quote": quote}, max_concurrency=8)
    result = await task_batch(
        engine, [{"item": "AAPL"}, {"item": "MSFT"}, {"item": "NVDA"}],
        template={"kind": "function", "function": "quote"}, batch_key="quotes",
    )
    assert result.status is ExecutionStatus.COMPLETED
    assert calls == [["AAPL", "MSFT", "NVDA"]]


# ── engine-scope deduplication ───────────────────────────────────────────────


async def test_engine_scope_dedup_shares_across_executions(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}
    gate = asyncio.Event()

    async def work(args, node):
        calls["n"] += 1
        await gate.wait()
        return {"v": args.get("item")}

    engine = make_engine(store, callables={"work": work}, max_concurrency=8)
    for execution_id, node_id in (("e1", "a"), ("e2", "b")):
        graph = engine.create_execution(execution_id=execution_id)
        engine.create_task(
            graph.id, kind=NodeKind.FUNCTION, node_id=node_id,
            input={"function": "work", "args": {"item": 7}, "dedupScope": "engine"},
        )
    t1 = engine.schedule("e1")
    t2 = engine.schedule("e2")
    assert await _wait_until(lambda: engine._executions["e2"].running or engine._executions["e2"].done.is_set())
    gate.set()
    await asyncio.gather(t1, t2)
    assert calls["n"] == 1, "engine-scope dedup should share one run across executions"
    assert engine.get_result("e1").successful_tasks == 1
    assert engine.get_result("e2").successful_tasks == 1
