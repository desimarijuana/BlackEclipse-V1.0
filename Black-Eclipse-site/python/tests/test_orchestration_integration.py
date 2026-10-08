"""Integration: orchestration drives real agent runs and beats sequential time."""

from __future__ import annotations

import asyncio
import time

from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.orchestration import ExecutionStatus, NodeKind
from harness.orchestration.primitives import parallel_execute
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


async def test_agent_nodes_run_through_execute_run(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    monkeypatch.setattr(
        graph_module, "build_chat_model",
        lambda settings: ScriptedModel([AIMessage(content="answer one"), AIMessage(content="answer two")]),
    )
    engine = make_engine(
        store,
        model_settings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
    )
    engine.runtime = engine.runtime.extend(data_bridge=FakeBridge())

    result = await parallel_execute(engine, [
        {"id": "a", "kind": "agent", "query": "analyze AAPL"},
        {"id": "b", "kind": "agent", "query": "analyze MSFT"},
    ])
    assert result.status is ExecutionStatus.COMPLETED
    assert result.successful_tasks == 2
    outputs = {n["id"]: n["output"] for n in result.nodes}
    assert all(v for v in outputs.values())
    # The child runs were persisted as real HarnessRuns linked to this execution's run.
    assert store.get_run("test_run_a") is not None
    assert store.get_run("test_run_a")["parentRunId"] == "test_run"


async def test_parallel_is_faster_than_sequential(tmp_path):
    store = make_store(tmp_path)
    seconds = 0.2

    async def work(args, node):
        await asyncio.sleep(seconds)
        return {"id": node.id}

    engine = make_engine(store, callables={"work": work}, max_concurrency=8,
                         limits={"global": 8})
    tasks = [{"id": f"t{i}", "kind": "function", "function": "work",
              "args": {"seconds": seconds, "tag": i}, "dedup": False} for i in range(4)]

    started = time.monotonic()
    result = await parallel_execute(engine, tasks)
    parallel = time.monotonic() - started

    # Sequential baseline: run the same callable four times in a row.
    seq_started = time.monotonic()
    for _ in range(4):
        await asyncio.sleep(seconds)
    sequential = time.monotonic() - seq_started

    assert result.status is ExecutionStatus.COMPLETED
    assert parallel < sequential * 0.6, f"parallel={parallel:.2f}s sequential={sequential:.2f}s"
    # And close to one task's duration, not four.
    assert parallel < seconds * 3


async def test_throughput_of_many_independent_tasks(tmp_path):
    store = make_store(tmp_path)

    async def noop(args, node):
        return {"id": node.id}

    engine = make_engine(store, callables={"noop": noop}, max_concurrency=16,
                         limits={"global": 16})
    tasks = [{"id": f"n{i}", "kind": "function", "function": "noop",
              "args": {"tag": i}, "dedup": False} for i in range(100)]
    started = time.monotonic()
    result = await parallel_execute(engine, tasks)
    elapsed = time.monotonic() - started
    assert result.successful_tasks == 100
    assert elapsed < 5.0


async def test_dependency_chain_across_many_layers(tmp_path):
    store = make_store(tmp_path)

    async def step(args, node):
        return {"id": node.id}

    engine = make_engine(store, callables={"step": step}, max_concurrency=8)
    tasks = []
    for i in range(10):
        spec = {"id": f"s{i}", "kind": "function", "function": "step",
                "args": {"tag": i}, "dedup": False}
        if i > 0:
            spec["dependsOn"] = [f"s{i - 1}"]
        tasks.append(spec)
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert result.successful_tasks == 10
