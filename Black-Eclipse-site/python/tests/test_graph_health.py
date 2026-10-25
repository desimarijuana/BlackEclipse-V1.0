"""Bounded graph telemetry: counts, percentiles, failure codes and caps."""

from __future__ import annotations

import datetime as dt

import pytest

from harness.graph_runtime.model import ExecutionMode, GraphRun, NodeRun, NodeStatus, RunStatus
from harness.graph_runtime.store import GraphRunStore
from harness.persistence import AgentMemoryStore, now_iso


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        yield GraphRunStore(memory)
    finally:
        memory.close()


def _run(store: GraphRunStore, run_id: str, status: RunStatus, duration: int | None = None) -> None:
    run = GraphRun(
        id=run_id, workflowId="wf", irVersion=1, mode=ExecutionMode.RESEARCH,
        testRun=True, status=status, startedAt=now_iso(), durationMs=duration,
        finishedAt=now_iso() if status != RunStatus.RUNNING else None,
    )
    store.create_run(run)
    if status != RunStatus.RUNNING:
        store.finish_run(run)


def _node(
    store: GraphRunStore,
    run_id: str,
    node_id: str,
    node_type: str,
    status: NodeStatus,
    duration: int | None = None,
    error_code: str | None = None,
) -> None:
    store.save_node_run(run_id, NodeRun(
        nodeId=node_id, nodeType=node_type, label=node_id, status=status,
        durationMs=duration, errorCode=error_code,
        outputs={"value": 1} if status == NodeStatus.SUCCEEDED else {},
    ))


def test_health_reports_counts_percentiles_and_failures(store):
    _run(store, "r1", RunStatus.SUCCEEDED, 100)
    _run(store, "r2", RunStatus.FAILED, 300)
    _run(store, "r3", RunStatus.RUNNING)
    _node(store, "r1", "calc", "transform.formula", NodeStatus.SUCCEEDED, 40)
    _node(store, "r1", "out", "output.result", NodeStatus.SUCCEEDED, 5)
    _node(store, "r2", "calc", "transform.formula", NodeStatus.FAILED, 200, "E_BAD")
    _node(store, "r2", "out", "output.result", NodeStatus.SKIPPED)

    health = store.health(window_hours=24)

    assert health["runs"]["total"] == 3
    assert health["runs"]["terminal"] == 2
    assert health["runs"]["successRate"] == 0.5
    assert health["runs"]["failureRate"] == 0.5
    assert health["durationMs"]["p95"] == 300
    assert health["failures"] == [{"code": "E_BAD", "count": 1}]
    assert health["nodeRuns"]["failed"] == 1
    assert health["nodeRuns"]["skipped"] == 1
    assert health["nodeRuns"]["checkpointRate"] == pytest.approx(0.5)
    assert health["slowestNodes"][0]["nodeType"] == "transform.formula"
    assert health["slowestNodes"][0]["avgMs"] == 120
    assert health["truncated"] == {"runs": False, "nodeRuns": False}


def test_health_window_excludes_old_runs(store):
    _run(store, "new", RunStatus.SUCCEEDED, 10)
    _run(store, "old", RunStatus.SUCCEEDED, 10)
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    store._db.execute("UPDATE HarnessGraphRun SET startedAt=? WHERE id='old'", (old,))
    store._db.commit()

    assert store.health(window_hours=24)["runs"]["total"] == 1
    assert store.health(window_hours=72)["runs"]["total"] == 2


def test_health_measures_queue_wait(store):
    _run(store, "r1", RunStatus.SUCCEEDED, 10)
    started = dt.datetime.now(dt.timezone.utc)
    created = started - dt.timedelta(milliseconds=500)
    def iso(value: dt.datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    store._db.execute(
        "UPDATE HarnessGraphRun SET startedAt=?, createdAt=? WHERE id='r1'",
        (iso(started), iso(created)),
    )
    store._db.commit()
    assert store.health()["queueWaitMs"]["avg"] == pytest.approx(500, abs=50)


def test_health_is_bounded_and_says_so(store):
    for index in range(3):
        _run(store, f"r{index}", RunStatus.SUCCEEDED, 10)
    health = store.health(window_hours=24, run_limit=1)
    assert health["runs"]["total"] == 1
    assert health["truncated"]["runs"] is True
