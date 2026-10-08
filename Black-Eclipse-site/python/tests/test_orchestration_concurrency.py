"""Concurrency and race-condition tests for the orchestration engine.

Deterministic: coordination uses asyncio events/barriers, not sleeps-as-oracles.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from harness.orchestration import ExecutionStatus, FailurePolicy, NodeKind
from harness.orchestration.graph import GraphValidationError
from harness.orchestration.models import ExecutionNode, TaskStatus
from harness.orchestration.primitives import parallel_execute

from orchestration_helpers import make_engine, make_store


async def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


async def test_two_tasks_completing_simultaneously_is_consistent(tmp_path):
    store = make_store(tmp_path)
    gate = asyncio.Event()
    finished: list[str] = []

    async def synced(args, node):
        await gate.wait()
        finished.append(node.id)
        return {"id": node.id}

    engine = make_engine(store, callables={"synced": synced}, max_concurrency=4)
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.FUNCTION,
                       input={"function": "synced", "args": {"tag": "a"}}, node_id="a", dedup=False)
    engine.create_task(graph.id, kind=NodeKind.FUNCTION,
                       input={"function": "synced", "args": {"tag": "b"}}, node_id="b", dedup=False)
    task = engine.schedule(graph.id)
    await _wait_until(lambda: len(engine._executions[graph.id].running) == 2)
    gate.set()
    await task
    result = engine.get_result(graph.id)
    assert result.status is ExecutionStatus.COMPLETED
    assert sorted(finished) == ["a", "b"]
    assert result.successful_tasks == 2


async def test_cancel_immediately_after_start_leaves_nothing_running(tmp_path):
    store = make_store(tmp_path)

    async def long(args, node):
        await asyncio.sleep(5)
        return {"ok": True}

    engine = make_engine(store, callables={"long": long})
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.FUNCTION,
                       input={"function": "long", "args": {"tag": "x"}}, node_id="a", dedup=False)
    task = engine.schedule(graph.id)
    await engine.cancel(graph.id)
    await task
    assert engine._executions[graph.id].running == {}
    assert engine.get_result(graph.id).status is ExecutionStatus.CANCELLED


async def test_runner_crash_releases_resources_and_lease(tmp_path):
    store = make_store(tmp_path)

    async def crash(args, node):
        raise RuntimeError("worker died")

    engine = make_engine(store, callables={"crash": crash})
    graph = engine.create_execution()
    node = engine.create_task(graph.id, kind=NodeKind.FUNCTION,
                              input={"function": "crash", "args": {"tag": "x"}},
                              node_id="a", dedup=False)
    await engine.execute(graph.id)
    result = engine.get_result(graph.id)
    assert result.nodes[0]["status"] == "FAILED"
    # No leaked resource slots and no un-released lease.
    assert engine._resources._used == {}
    assert engine.store.active_leases(graph.id) == []


async def test_duplicate_node_id_is_rejected(tmp_path):
    store = make_store(tmp_path)
    engine = make_engine(store)
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.NOOP, input={"value": 1}, node_id="a")
    with pytest.raises(GraphValidationError):
        engine.create_task(graph.id, kind=NodeKind.NOOP, input={"value": 2}, node_id="a")


async def test_cancel_beats_a_pending_retry(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}
    started = asyncio.Event()

    class Flaky(RuntimeError):
        def __init__(self):
            super().__init__("TEMP")
            self.code = "TEMPORARY_FAILURE"

    async def flaky(args, node):
        calls["n"] += 1
        started.set()
        raise Flaky()

    engine = make_engine(store, callables={"flaky": flaky})
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.FUNCTION,
                       input={"function": "flaky", "args": {"tag": "x"}}, node_id="a",
                       retry={"max_attempts": 5, "backoff_ms": 1000}, dedup=False)
    task = engine.schedule(graph.id)
    await _wait_until(started.is_set)
    await engine.cancel(graph.id)
    await task
    result = engine.get_result(graph.id)
    assert result.status is ExecutionStatus.CANCELLED
    assert result.nodes[0]["status"] == "CANCELLED"
    assert calls["n"] == 1


async def test_edge_can_be_added_to_a_completed_graph_without_a_cycle(tmp_path):
    store = make_store(tmp_path)
    engine = make_engine(store)
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.NOOP, input={"value": 1}, node_id="a")
    engine.create_task(graph.id, kind=NodeKind.NOOP, input={"value": 2}, node_id="b")
    engine.add_dependency(graph.id, "b", "a")
    with pytest.raises(GraphValidationError):
        engine.add_dependency(graph.id, "a", "b")  # would create a cycle
