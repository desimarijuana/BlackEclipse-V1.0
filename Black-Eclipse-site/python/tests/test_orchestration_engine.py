"""Orchestration engine: scheduling, concurrency, retries, failure and policies.

Offline and deterministic: nodes are FUNCTION nodes backed by test callables, so
no model, network or registry is needed to exercise the scheduler. Every timing
assertion compares measured intervals, never a bare sleep.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from harness.orchestration import (
    ExecutionGraph,
    ExecutionStatus,
    FailurePolicy,
    JoinPolicy,
    NodeKind,
    Priority,
    TaskStatus,
)
from harness.orchestration.graph import GraphValidationError
from harness.orchestration.primitives import parallel_execute, task_join, task_map, task_race, task_reduce
from harness.tools import ToolDefinition, ToolRegistry

from orchestration_helpers import make_engine, make_store, tool_ctx


class Boom(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _timing_callable(intervals: dict, events: list):
    async def run(args, node):
        start = time.monotonic()
        events.append(("start", node.id, start))
        await asyncio.sleep(float(args.get("seconds", 0.1)))
        end = time.monotonic()
        intervals[node.id] = (start, end)
        events.append(("end", node.id, end))
        return {"id": node.id}
    return run


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# ── genuine parallelism ──────────────────────────────────────────────────────


async def test_independent_tasks_run_concurrently(tmp_path):
    store = make_store(tmp_path)
    intervals: dict = {}
    events: list = []
    engine = make_engine(store, callables={"mark": _timing_callable(intervals, events)},
                         max_concurrency=4, limits={"global": 4})
    tasks = [{"id": f"t{i}", "kind": "function", "function": "mark",
              "args": {"seconds": 0.2}, "dedup": False} for i in range(4)]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert result.successful_tasks == 4
    wall = max(e[2] for e in events) - min(e[2] for e in events)
    # 4 x 0.2s sequential would be ~0.8s; genuine overlap is ~0.2s.
    assert wall < 0.5, f"tasks did not overlap (wall={wall:.2f}s)"
    ids = list(intervals)
    assert _overlap(intervals[ids[0]], intervals[ids[1]])


async def test_dependencies_are_respected(tmp_path):
    store = make_store(tmp_path)
    events: list = []
    engine = make_engine(store, callables={"mark": _timing_callable({}, events)})
    tasks = [
        {"id": "a", "kind": "function", "function": "mark", "args": {"seconds": 0.05}, "dedup": False},
        {"id": "b", "kind": "function", "function": "mark", "args": {"seconds": 0.05}, "dedup": False, "dependsOn": ["a"]},
        {"id": "c", "kind": "function", "function": "mark", "args": {"seconds": 0.05}, "dedup": False, "dependsOn": ["b"]},
    ]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    order = [e[1] for e in events if e[0] == "start"]
    assert order == ["a", "b", "c"]


async def test_automatic_parallelism_diamond(tmp_path):
    store = make_store(tmp_path)
    intervals: dict = {}
    engine = make_engine(store, callables={"mark": _timing_callable(intervals, [])},
                         max_concurrency=4, limits={"global": 4})
    tasks = [
        {"id": "a", "kind": "function", "function": "mark", "args": {"seconds": 0.05}, "dedup": False},
        {"id": "b", "kind": "function", "function": "mark", "args": {"seconds": 0.2}, "dedup": False, "dependsOn": ["a"]},
        {"id": "c", "kind": "function", "function": "mark", "args": {"seconds": 0.2}, "dedup": False, "dependsOn": ["a"]},
        {"id": "d", "kind": "function", "function": "mark", "args": {"seconds": 0.05}, "dedup": False, "dependsOn": ["b", "c"]},
    ]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert _overlap(intervals["b"], intervals["c"])
    assert intervals["a"][1] <= intervals["b"][0] + 1e-3
    assert intervals["d"][0] >= max(intervals["b"][1], intervals["c"][1]) - 1e-3


async def test_concurrency_limit_bounds_parallelism(tmp_path):
    store = make_store(tmp_path)
    intervals: dict = {}
    engine = make_engine(store, callables={"mark": _timing_callable(intervals, [])},
                         max_concurrency=2, limits={"global": 2})
    tasks = [{"id": f"t{i}", "kind": "function", "function": "mark",
              "args": {"seconds": 0.15}, "dedup": False} for i in range(4)]
    await parallel_execute(engine, tasks)
    starts = sorted(intervals[i][0] for i in intervals)
    # With a global limit of 2, the third start cannot precede the first end.
    first_end = min(v[1] for v in intervals.values())
    assert starts[2] >= first_end - 0.02


async def test_priority_order_within_capacity(tmp_path):
    store = make_store(tmp_path)
    events: list = []
    engine = make_engine(store, callables={"mark": _timing_callable({}, events)},
                         max_concurrency=1, limits={"global": 1})
    tasks = [
        {"id": "low", "kind": "function", "function": "mark", "args": {"seconds": 0.05},
         "dedup": False, "priority": "LOW"},
        {"id": "high", "kind": "function", "function": "mark", "args": {"seconds": 0.05},
         "dedup": False, "priority": "HIGH"},
        {"id": "normal", "kind": "function", "function": "mark", "args": {"seconds": 0.05},
         "dedup": False, "priority": "NORMAL"},
    ]
    await parallel_execute(engine, tasks)
    order = [e[1] for e in events if e[0] == "start"]
    assert order == ["high", "normal", "low"]


# ── retries / timeouts ───────────────────────────────────────────────────────


async def test_retry_succeeds_after_transient_failure(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def flaky(args, node):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Boom("TEMPORARY_FAILURE")
        return {"ok": True}

    engine = make_engine(store, callables={"flaky": flaky})
    tasks = [{"id": "a", "kind": "function", "function": "flaky",
              "retry": {"max_attempts": 3, "backoff_ms": 10}}]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert calls["n"] == 2
    assert result.nodes[0]["attemptCount"] == 2


async def test_non_retryable_failure_is_not_retried(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def bad(args, node):
        calls["n"] += 1
        raise Boom("TOOL_VALIDATION_FAILED")

    engine = make_engine(store, callables={"bad": bad})
    tasks = [{"id": "a", "kind": "function", "function": "bad",
              "retry": {"max_attempts": 3, "backoff_ms": 10}}]
    result = await parallel_execute(engine, tasks)
    assert calls["n"] == 1
    assert result.nodes[0]["status"] == "FAILED"
    assert result.nodes[0]["error"]["code"] == "TOOL_VALIDATION_FAILED"


async def test_timeout_marks_node_timed_out(tmp_path):
    store = make_store(tmp_path)

    async def slow(args, node):
        await asyncio.sleep(2)
        return {"ok": True}

    engine = make_engine(store, callables={"slow": slow})
    tasks = [{"id": "a", "kind": "function", "function": "slow", "timeoutMs": 100}]
    result = await parallel_execute(engine, tasks)
    assert result.nodes[0]["status"] == "TIMED_OUT"
    assert result.nodes[0]["error"]["code"] == "TASK_TIMEOUT"


# ── failure policies ─────────────────────────────────────────────────────────


async def test_fail_fast_cancels_the_execution(tmp_path):
    store = make_store(tmp_path)

    async def boom(args, node):
        raise Boom("DETERMINISTIC_ERROR")

    async def long(args, node):
        await asyncio.sleep(5)
        return {"ok": True}

    engine = make_engine(store, callables={"boom": boom, "long": long}, max_concurrency=4)
    tasks = [
        {"id": "bad", "kind": "function", "function": "boom"},
        {"id": "slow", "kind": "function", "function": "long"},
    ]
    result = await parallel_execute(engine, tasks, failure_policy=FailurePolicy.FAIL_FAST)
    assert result.status is ExecutionStatus.FAILED
    statuses = {n["id"]: n["status"] for n in result.nodes}
    assert statuses["bad"] == "FAILED"
    assert statuses["slow"] == "CANCELLED"


async def test_continue_policy_reports_partial_success(tmp_path):
    store = make_store(tmp_path)

    async def boom(args, node):
        raise Boom("DETERMINISTIC_ERROR")

    async def ok(args, node):
        return {"ok": True}

    engine = make_engine(store, callables={"boom": boom, "ok": ok})
    tasks = [
        {"id": "bad", "kind": "function", "function": "boom"},
        {"id": "good", "kind": "function", "function": "ok"},
    ]
    result = await parallel_execute(engine, tasks, failure_policy=FailurePolicy.CONTINUE)
    assert result.status is ExecutionStatus.PARTIAL_SUCCESS
    assert result.failed_tasks == 1 and result.successful_tasks == 1
    assert result.coverage == pytest.approx(0.5)


async def test_dependent_of_failed_node_is_skipped_not_run(tmp_path):
    store = make_store(tmp_path)
    ran = {"dependent": False}

    async def boom(args, node):
        raise Boom("DETERMINISTIC_ERROR")

    async def dep(args, node):
        ran["dependent"] = True
        return {"ok": True}

    engine = make_engine(store, callables={"boom": boom, "dep": dep})
    tasks = [
        {"id": "a", "kind": "function", "function": "boom"},
        {"id": "b", "kind": "function", "function": "dep", "dependsOn": ["a"]},
    ]
    result = await parallel_execute(engine, tasks)
    assert ran["dependent"] is False
    statuses = {n["id"]: n["status"] for n in result.nodes}
    assert statuses["b"] == "SKIPPED"


async def test_retry_failed_policy_reruns_failed_nodes(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def once(args, node):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Boom("DETERMINISTIC_ERROR")
        return {"ok": True}

    engine = make_engine(store, callables={"once": once})
    tasks = [{"id": "a", "kind": "function", "function": "once", "retry": {"max_attempts": 1}}]
    result = await parallel_execute(engine, tasks, failure_policy=FailurePolicy.RETRY_FAILED)
    assert result.status is ExecutionStatus.COMPLETED
    assert calls["n"] >= 2


async def test_require_quorum(tmp_path):
    store = make_store(tmp_path)

    async def boom(args, node):
        raise Boom("DETERMINISTIC_ERROR")

    async def ok(args, node):
        return {"ok": True}

    engine = make_engine(store, callables={"boom": boom, "ok": ok})
    tasks = [
        {"id": "a", "kind": "function", "function": "ok"},
        {"id": "b", "kind": "function", "function": "boom"},
        {"id": "c", "kind": "function", "function": "boom"},
    ]
    failed = await parallel_execute(engine, tasks, failure_policy=FailurePolicy.REQUIRE_QUORUM, quorum=2)
    assert failed.status is ExecutionStatus.FAILED
    passed = await parallel_execute(engine, tasks, failure_policy=FailurePolicy.REQUIRE_QUORUM, quorum=1)
    assert passed.status is ExecutionStatus.COMPLETED


# ── joins / race / quorum ────────────────────────────────────────────────────


async def test_first_success_join_cancels_losers(tmp_path):
    store = make_store(tmp_path)

    async def quick(args, node):
        await asyncio.sleep(0.02)
        return {"winner": node.id}

    async def slow(args, node):
        await asyncio.sleep(5)
        return {"winner": node.id}

    engine = make_engine(store, callables={"quick": quick, "slow": slow}, max_concurrency=4)
    children = [
        {"id": "fast", "kind": "function", "function": "quick"},
        {"id": "slow", "kind": "function", "function": "slow"},
    ]
    result = await task_join(engine, children, policy=JoinPolicy.FIRST_SUCCESS)
    statuses = {n["id"]: n["status"] for n in result.nodes}
    assert statuses["join"] == "COMPLETED"
    assert statuses["slow"] == "CANCELLED"
    # The join's structured input records the winner and the failure honestly.
    join_output = next(n["output"] for n in result.nodes if n["id"] == "join")
    assert "fast" in join_output["outputs"]


async def test_race_completes_with_the_first_result(tmp_path):
    store = make_store(tmp_path)

    async def racer(args, node):
        await asyncio.sleep(float(args["delay"]))
        return {"by": node.id}

    engine = make_engine(store, callables={"racer": racer}, max_concurrency=4)
    result = await task_race(engine, [
        {"id": "slow", "kind": "function", "function": "racer", "args": {"delay": 1.0}},
        {"id": "fast", "kind": "function", "function": "racer", "args": {"delay": 0.02}},
    ])
    assert result.status is ExecutionStatus.COMPLETED
    assert {n["id"]: n["status"] for n in result.nodes}["slow"] == "CANCELLED"


async def test_map_reduce_over_items(tmp_path):
    store = make_store(tmp_path)

    async def analyze(args, node):
        return {"symbol": args.get("item"), "score": len(str(args.get("item")))}

    async def reduce_rank(args, node):
        items = [i for i in (args.get("item") or []) if i is not None]
        return {"ranked": sorted(items, key=lambda d: d.get("score", 0), reverse=True)}

    engine = make_engine(store, callables={"analyze": analyze})
    result = await task_map(
        engine, ["AAPL", "MSFT", "NVDA"],
        template={"kind": "function", "function": "analyze"},
        reduce_mode="list",
    )
    assert result.successful_tasks == 4  # 3 mapped nodes + the aggregate
    agg = next(n for n in result.nodes if n["id"] == "aggregate")
    assert agg["status"] == "COMPLETED"
    assert len(agg["output"]["items"]) == 3


async def test_task_reduce_uses_a_function_reducer(tmp_path):
    store = make_store(tmp_path)

    async def analyze(args, node):
        return {"symbol": args.get("item")}

    def reduce_all(args, node):
        return {"items": [a.get("item") for a in (args.get("item") or [])]}

    engine = make_engine(store, callables={"analyze": analyze, "reduce_all": reduce_all})
    result = await task_reduce(
        engine, [{"value": 1}, {"value": 2}],
        template={"kind": "function", "function": "analyze"},
        reduce={"function": "reduce_all"},
    )
    assert result.successful_tasks == 3
    reducer = next(n for n in result.nodes if n["id"] == "reduce")
    assert reducer["status"] == "COMPLETED"


# ── dedup / cache ────────────────────────────────────────────────────────────


async def test_identical_tool_work_is_deduplicated(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def analyze(args, node):
        calls["n"] += 1
        await asyncio.sleep(0.1)
        return {"symbol": args.get("item")}

    engine = make_engine(store, callables={"analyze": analyze}, max_concurrency=4)
    tasks = [
        {"id": "a", "kind": "function", "function": "analyze", "args": {"item": "AAPL"}},
        {"id": "b", "kind": "function", "function": "analyze", "args": {"item": "AAPL"}},
        {"id": "c", "kind": "function", "function": "analyze", "args": {"item": "AAPL"}},
    ]
    result = await parallel_execute(engine, tasks)
    assert result.status is ExecutionStatus.COMPLETED
    assert calls["n"] == 1, "identical work should share one execution"
    outputs = {n["id"]: n["output"] for n in result.nodes}
    assert outputs["a"] == outputs["b"] == outputs["c"]


async def test_cache_reuses_a_result_across_executions(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def price(args, node):
        calls["n"] += 1
        return {"price": 42}

    engine = make_engine(store, callables={"price": price})
    spec = [{"id": "p", "kind": "function", "function": "price", "args": {"item": "AAPL"},
             "cacheable": True, "cacheTtlMs": 60_000}]
    await parallel_execute(engine, spec)
    await parallel_execute(engine, spec)
    assert calls["n"] == 1


# ── cancellation / pause / dynamic / persistence / recovery ──────────────────


async def test_cancellation_stops_running_work(tmp_path):
    store = make_store(tmp_path)
    started = asyncio.Event()

    async def long(args, node):
        started.set()
        await asyncio.sleep(5)
        return {"ok": True}

    engine = make_engine(store, callables={"long": long})
    graph = engine.create_execution(failure_policy=FailurePolicy.CONTINUE)
    engine.create_task(graph.id, kind=NodeKind.FUNCTION, input={"function": "long"}, node_id="a")
    task = engine.schedule(graph.id)
    await _wait_until(started.is_set)
    assert await engine.cancel(graph.id) is True
    await task
    result = engine.get_result(graph.id)
    assert result.status is ExecutionStatus.CANCELLED
    assert result.nodes[0]["status"] == "CANCELLED"
    assert engine._executions[graph.id].running == {}


async def test_pause_and_resume(tmp_path):
    store = make_store(tmp_path)
    order: list[str] = []

    async def step(args, node):
        order.append(f"start:{node.id}")
        await asyncio.sleep(0.1)
        order.append(f"end:{node.id}")
        return {"ok": True}

    engine = make_engine(store, callables={"step": step})
    graph = engine.create_execution()
    a = engine.create_task(graph.id, kind=NodeKind.FUNCTION, input={"function": "step"},
                           node_id="a", dedup=False)
    engine.create_task(graph.id, kind=NodeKind.FUNCTION, input={"function": "step"},
                       node_id="b", dependencies=[a.id], dedup=False)
    task = engine.schedule(graph.id)
    assert await _wait_until(lambda: "start:a" in order)
    # Pause while the first node is running; the second must not start.
    await engine.pause(graph.id)
    assert await _wait_until(lambda: "end:a" in order)
    await asyncio.sleep(0.05)
    assert "start:b" not in order  # paused before b
    await engine.resume(graph.id)
    await task
    assert order == ["start:a", "end:a", "start:b", "end:b"]


async def test_dynamic_node_insertion_while_running(tmp_path):
    store = make_store(tmp_path)
    gate = asyncio.Event()
    order: list[str] = []

    async def gate_fn(args, node):
        order.append("gate:start")
        await gate.wait()
        order.append("gate:end")
        return {"ok": True}

    async def extra(args, node):
        order.append("extra")
        return {"ok": True}

    engine = make_engine(store, callables={"gate_fn": gate_fn, "extra": extra})
    graph = engine.create_execution()
    engine.create_task(graph.id, kind=NodeKind.FUNCTION, input={"function": "gate_fn"}, node_id="gate")
    task = engine.schedule(graph.id)
    await _wait_until(lambda: "gate:start" in order)
    # Insert a new independent node while the execution is running.
    from harness.orchestration.models import ExecutionNode
    engine.add_node_runtime(graph.id, ExecutionNode(id="late", kind=NodeKind.FUNCTION,
                                                    input={"function": "extra"}))
    gate.set()
    await task
    result = engine.get_result(graph.id)
    assert result.status is ExecutionStatus.COMPLETED
    assert "extra" in order


async def test_persistence_and_crash_recovery(tmp_path):
    store = make_store(tmp_path)
    engine = make_engine(store, callables={"mark": lambda args, node: {"ok": node.id}})
    graph = ExecutionGraph(id="exec_recover")
    from harness.orchestration.models import ExecutionNode as N

    done = N(id="done", execution_id=graph.id, kind=NodeKind.FUNCTION,
             input={"function": "mark"}, status=TaskStatus.COMPLETED, output={"prev": 1})
    pending = N(id="pending", execution_id=graph.id, kind=NodeKind.FUNCTION,
                input={"function": "mark"})
    abandoned = N(id="abandoned", execution_id=graph.id, kind=NodeKind.FUNCTION,
                  input={"function": "mark"}, dependencies=["done"], status=TaskStatus.RUNNING)
    pending.dependencies = ["done"]
    done.dependents = ["pending", "abandoned"]
    graph.nodes = {"done": done, "pending": pending, "abandoned": abandoned}
    graph.status = ExecutionStatus.RUNNING
    engine.store.save_execution(graph)
    engine.store.save_nodes(graph)

    recovered = await engine.recover()
    assert "exec_recover" in recovered
    result = engine.get_result("exec_recover")
    assert result.status is ExecutionStatus.COMPLETED
    assert result.total_tasks == 3
    assert result.successful_tasks == 3
    # Idempotent: a second recovery is a no-op.
    assert await engine.recover() == []


# ── tool nodes & allowlist ───────────────────────────────────────────────────


async def test_tool_node_runs_through_the_registry(tmp_path):
    store = make_store(tmp_path)

    async def echo(args, ctx):
        return f"echo:{args.get('value')}", {"value": args.get("value")}

    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="echo", description="echo",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        handler=echo, permission="read", risk="low",
    ))
    ctx = tool_ctx(store, allowed={"echo"}, registry=registry)
    engine = make_engine(store, registry=registry, tool_context=ctx, allowed={"echo"})
    result = await parallel_execute(engine, [
        {"id": "t", "kind": "tool", "tool": "echo", "args": {"value": "hi"}},
    ])
    assert result.status is ExecutionStatus.COMPLETED
    assert result.nodes[0]["output"] == {"value": "hi"}


async def test_tool_node_outside_the_allowlist_is_forbidden(tmp_path):
    store = make_store(tmp_path)

    async def echo(args, ctx):
        return "x", None

    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="echo", description="echo", input_schema={"type": "object", "properties": {}},
        handler=echo, permission="read", risk="low",
    ))
    ctx = tool_ctx(store, allowed=set(), registry=registry)  # empty allowlist
    engine = make_engine(store, registry=registry, tool_context=ctx, allowed=set())
    result = await parallel_execute(engine, [{"id": "t", "kind": "tool", "tool": "echo"}])
    assert result.status is ExecutionStatus.FAILED
    assert result.nodes[0]["error"]["code"] == "TOOL_FORBIDDEN"


async def test_rate_limit_feeds_retry_and_fails_honestly(tmp_path):
    store = make_store(tmp_path)
    calls = {"n": 0}

    async def work(args, node):
        calls["n"] += 1
        return {"ok": True}

    engine = make_engine(store, callables={"work": work})
    # A bucket with one token and no refill; pre-consume the token so the node is
    # immediately rate-limited.
    engine.rate_limiter.configure("prov", requests_per_second=0, burst=1)
    assert await engine.rate_limiter.try_acquire("prov") is True
    result = await parallel_execute(engine, [{
        "id": "a", "kind": "function", "function": "work", "rateKey": "prov",
        "retry": {"max_attempts": 2}, "dedup": False,
    }])
    assert calls["n"] == 0  # the runner was never reached
    assert result.status is ExecutionStatus.FAILED
    assert result.nodes[0]["error"]["code"] == "RATE_LIMITED"
    assert result.nodes[0]["attemptCount"] == 2


async def test_task_map_batches_items(tmp_path):
    store = make_store(tmp_path)
    seen: list[int] = []

    async def batch(args, node):
        items = args.get("items") if args.get("items") is not None else [args.get("item")]
        seen.append(len(items))
        return {"count": len(items)}

    engine = make_engine(store, callables={"batch": batch})
    result = await task_map(
        engine, list(range(10)),
        template={"kind": "function", "function": "batch"},
        batch_size=4,
    )
    # 10 items in batches of 4 -> 4, 4, 2.
    assert sorted(seen) == [2, 4, 4]
    assert result.successful_tasks == 4  # 3 batched nodes + the aggregate


async def test_invalid_graph_is_not_executed(tmp_path):
    store = make_store(tmp_path)
    engine = make_engine(store)
    graph = ExecutionGraph(id="bad")
    from harness.orchestration.models import ExecutionNode as N

    graph.nodes = {"x": N(id="x", kind=NodeKind.FUNCTION, dependencies=["missing"])}
    with pytest.raises(GraphValidationError):
        await engine.run_graph(graph)
