"""Durable graph execution: normalized node/event rows, checkpoints/resume,
Fabric dispatch and the graph worker bridge."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from harness.graph_runtime.compiler import RunGrants
from harness.graph_runtime.model import (
    GraphRun,
    NodeRun,
    NodeStatus,
    PortDef,
    PortType,
    RunStatus,
    WorkflowIR,
)
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeRegistry
from harness.graph_runtime.service import GraphService
from harness.graph_runtime.store import GraphRunStore
from harness.graph_runtime.worker import GraphWorker
from harness.fabric.config import FabricConfig
from harness.fabric.manager import ExecutionManager
from harness.fabric.models import Job, WorkerOutcome
from harness.fabric.store import FabricStore
from harness.fabric.workers import WorkerContext
from harness.persistence import AgentMemoryStore, now_iso


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges, workflow_id="wf_durable"):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": workflow_id, "name": workflow_id,
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


def _simple():
    return _ir([
        _node("trig", "trigger.manual", {"seed": "3"}),
        _node("v", "data.value", {"dataType": "number", "value": "0"}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "v", "in"),
        _edge("e2", "v", "value", "out", "value"),
    ])


def _counter_graph(calls: list[str]):
    registry = NodeRegistry()
    for definition in build_default_registry().definitions():
        registry.register(definition)

    def exec_counter(_ctx):
        calls.append(_ctx.node_id)
        return {"value": 1}

    registry.register(NodeDef(
        type="test.counter", version="1.0.0", label="Counter", category="data",
        inputs=(PortDef(id="in", name="In", type=PortType.ANY, optional=True),),
        outputs=(PortDef(id="value", name="Value", type=PortType.NUMBER),),
        executor=exec_counter,
    ))
    ir = _ir([
        _node("trig", "trigger.manual"),
        _node("counter", "test.counter"),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "counter", "in"),
        _edge("e2", "counter", "value", "out", "value"),
    ])
    return registry, ir


@pytest.fixture()
def service(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    graph_service = GraphService(GraphRunStore(memory))
    yield graph_service
    memory.close()


def test_run_sync_writes_normalized_rows_and_terminal_output(service):
    run = service.run_sync(_simple())
    assert run.status == RunStatus.SUCCEEDED
    assert run.output == 3.0

    stored = service._store
    nodes = stored.list_node_runs(run.id)
    assert {node["nodeId"] for node in nodes} == {"trig", "v", "out"}
    assert all(node["status"] == "succeeded" for node in nodes)
    assert all("resumable" in node for node in nodes)
    assert any(node["resumable"] for node in nodes)
    events = stored.list_events(run.id)
    assert any(event["kind"] == "run.started" for event in events)
    assert any(event["kind"] == "node.succeeded" for event in events)

    record = service.get_run(run.id)
    assert record["nodeRuns"]
    assert record["nodeStatus"]["out"] == "succeeded"


def test_checkpoint_limit_is_operator_configurable_and_bounded(monkeypatch):
    from harness.graph_runtime.store import HARD_CHECKPOINT_BYTES, MAX_CHECKPOINT_BYTES, _checkpoint_limit

    monkeypatch.delenv("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES", raising=False)
    assert _checkpoint_limit() == MAX_CHECKPOINT_BYTES
    monkeypatch.setenv("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES", "5000000")
    assert _checkpoint_limit() == 5_000_000
    monkeypatch.setenv("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES", "999999999")
    assert _checkpoint_limit() == HARD_CHECKPOINT_BYTES
    monkeypatch.setenv("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES", "not-a-number")
    assert _checkpoint_limit() == MAX_CHECKPOINT_BYTES


def test_oversized_checkpoints_spill_to_a_confined_file(monkeypatch, tmp_path):
    from harness.graph_runtime.model import ExecutionMode

    monkeypatch.setenv("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES", "1000")
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    store = GraphRunStore(memory)
    run_id = "grun_spill"
    try:
        store.create_run(GraphRun(
            id=run_id, workflowId="wf_spill", irVersion=1,
            mode=ExecutionMode.RESEARCH, testRun=True,
            status=RunStatus.RUNNING, startedAt=now_iso(),
        ))
        large = {"blob": "x" * 5_000}
        terminal = {"blob": "y" * 5_000}
        store.save_node_run(
            run_id,
            NodeRun(
                nodeId="big", nodeType="test.big", label="Big",
                status=NodeStatus.SUCCEEDED, layer=0, attempt=1,
                startedAt=now_iso(), finishedAt=now_iso(), durationMs=1,
                inputs={}, outputs={},
            ),
            outputs=large, fired=[], terminal_done=True, terminal_value=terminal,
        )
        resume = store.load_resume(run_id)
        assert resume["complete"] is True
        assert resume["outputs"]["big"] == large
        assert resume["terminal"]["big"] == terminal
        root = store._checkpoint_root()
        assert list(root.rglob("*.checkpoint.json"))
        assert list(root.rglob("*.terminal.json"))
        assert store.delete_run(run_id) == 1
        assert not (root / run_id).exists()
    finally:
        memory.close()


def test_execute_job_resumes_completed_nodes(service):
    calls: list[str] = []
    registry, ir = _counter_graph(calls)
    service = GraphService(service._store, registry=registry)
    plan = service.compile(ir)
    run_id = "grun_resume"
    service._store.create_run(GraphRun(
        id=run_id, workflowId=ir.id, workflowVersion=1, irVersion=1,
        mode=plan.mode, testRun=True, status=RunStatus.RUNNING,
        startedAt=now_iso(), plan=plan,
    ))
    service._store.save_node_run(
        run_id,
        NodeRun(
            nodeId="counter", nodeType="test.counter", label="Counter",
            status=NodeStatus.SUCCEEDED, layer=1, attempt=1,
            startedAt=now_iso(), finishedAt=now_iso(), durationMs=1,
            inputs={}, outputs={"value": 1},
        ),
        outputs={"value": 1}, fired=[], terminal_done=False,
    )

    payload = {
        "ir": ir.model_dump(by_alias=True),
        "subworkflows": {},
        "runId": run_id,
        "workflowVersion": 1,
        "ownerId": "local",
        "runInput": None,
        "grants": {"testRun": True, "grantedCapabilities": [], "allowNetwork": False, "allowTrading": False},
    }
    run = service.execute_job(payload, cancel_event=threading.Event())
    assert run is not None and run.status == RunStatus.SUCCEEDED
    assert run.output == 1
    assert calls == []  # the resumed counter node was not re-executed
    assert service._store.get_run(run_id)["nodeStatus"]["counter"] == "succeeded"


def test_durable_wait_defers_then_resumes_from_the_checkpoint(service):
    from harness.graph_runtime.model import RunDeferred

    payload_ir = {
        "irVersion": 1, "id": "wf_wait_durable", "name": "Wait",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "wait", "type": "logic.wait", "version": "1.0.0", "config": {"ms": 120_000}, "layout": {"x": 0, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
        ],
        "edges": [
            {"id": "e2", "source": "wait", "sourceHandle": "waitedMs", "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    }
    ir = WorkflowIR.model_validate(payload_ir)
    service = GraphService(service._store, registry=build_default_registry())
    grants = RunGrants(test_run=False)
    plan = service.compile(ir, grants)
    assert plan.executable, [d.message for d in plan.diagnostics]
    run_id = "grun_wait_durable"
    service._store.create_run(GraphRun(
        id=run_id, workflowId=ir.id, workflowVersion=1, irVersion=1,
        mode=plan.mode, testRun=False, status=RunStatus.RUNNING,
        startedAt=now_iso(), plan=plan,
    ))
    payload = {
        "ir": ir.model_dump(by_alias=True),
        "subworkflows": {},
        "runId": run_id,
        "workflowVersion": 1,
        "ownerId": "local",
        "runInput": None,
        "grants": {"testRun": False, "grantedCapabilities": [], "allowNetwork": False, "allowTrading": False},
    }

    started = time.monotonic()
    first = service.execute_job(payload, cancel_event=threading.Event())
    assert isinstance(first, RunDeferred)
    assert time.monotonic() - started < 5  # it did not sleep 120 s
    assert first.run.status == RunStatus.QUEUED
    stored = service._store.get_run(run_id)
    assert stored["status"] == "queued"
    assert stored["nodeStatus"]["wait"] == "succeeded"
    assert "out" not in stored["nodeStatus"]  # it has not settled yet

    second = service.execute_job(payload, cancel_event=threading.Event())
    assert isinstance(second, GraphRun)
    assert second.status == RunStatus.SUCCEEDED
    assert second.output == 120_000


class _FakeFabric:
    def __init__(self):
        self.payload = None
        self.cancelled = None

    async def submit(self, job_type, payload, **kwargs):
        self.payload = payload
        return {"jobId": "job_graph_1", "status": "QUEUED", "mode": "DURABLE"}

    async def cancel(self, job_id):
        self.cancelled = job_id
        return {"cancelled": True}


def test_start_run_dispatches_a_durable_job_and_worker_completes_it(service):
    fabric = _FakeFabric()
    service.set_fabric(fabric)
    started = service.start_run(_simple())
    assert started["status"] == "queued"
    assert started["jobId"] == "job_graph_1"
    assert fabric.payload["runId"] == started["id"]

    run = service.execute_job(fabric.payload, cancel_event=threading.Event())
    assert run is not None and run.status == RunStatus.SUCCEEDED
    record = service.get_run(started["id"])
    assert record["status"] == "succeeded"
    assert record["nodeRuns"]


def test_worker_bridges_a_payload_and_returns_success(service):
    class _LogStore:
        def append_event(self, *_args, **_kwargs):
            return 1

    class _Graphs:
        def execute_job(self, payload, *, cancel_event, job_id=None):
            return service.run_sync(_simple())

    class _Service:
        graphs = _Graphs()

    worker = GraphWorker(_Service())
    ctx = WorkerContext(
        job=Job(type="graph", queue="graph", input={"runId": "grun_worker"}),
        worker_id="wrk_1", attempt=1, store=_LogStore(),
    )
    outcome = asyncio.run(worker.handle(ctx))
    assert isinstance(outcome, WorkerOutcome)
    assert outcome.status == "succeeded"
    assert outcome.output["status"] == "succeeded"


def test_cancel_marks_queued_run_and_calls_fabric(service):
    fabric = _FakeFabric()
    service.set_fabric(fabric)
    started = service.start_run(_simple())
    cancelled = service.cancel(started["id"])
    assert fabric.cancelled == "job_graph_1"
    assert cancelled["status"] == "cancelled"


async def test_real_fabric_worker_runs_and_persists_a_graph_job(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "fabric-agent-memory.db"))
    graph_service = GraphService(GraphRunStore(memory))
    config = FabricConfig(poll_seconds=0.05, lease_seconds=5, job_timeout_ms=30_000)

    class _Service:
        graphs = graph_service
        store = memory
        bus = None

    manager = ExecutionManager(FabricStore(memory), config=config, service=_Service())
    manager.register_worker(GraphWorker(_Service()))
    graph_service.set_fabric(manager)
    await manager.start()
    try:
        ir = _simple()
        run_id = "grun_real_fabric"
        payload = graph_service._job_payload(
            ir, run_id=run_id, workflow_version=1, owner_id="local",
            grants=RunGrants(test_run=True), subworkflows=None, run_input=None,
        )
        result = await manager.submit(
            "graph", payload, mode="DURABLE", queue="graph", worker_kind="graph",
            timeout_ms=30_000, max_attempts=1,
        )
        assert result["jobId"]

        deadline = time.time() + 10
        record = None
        while time.time() < deadline:
            record = graph_service.get_run(run_id)
            if record and record["status"] in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(0.05)
        assert record is not None
        assert record["status"] == "succeeded", record.get("error")
        assert record["nodeRuns"]
        assert record["jobId"] == result["jobId"]
    finally:
        await manager.stop()
        memory.close()


def test_orphan_reconcile_leaves_durable_runs_for_the_fabric(service):
    store = service._store
    durable = GraphRun(
        id="grun_durable", workflowId="wf", irVersion=1, mode="research",
        testRun=True, status=RunStatus.RUNNING, startedAt=now_iso(),
    )
    store.create_run(durable)
    store.set_job_id(durable.id, "job_1")
    legacy = GraphRun(
        id="grun_legacy", workflowId="wf", irVersion=1, mode="research",
        testRun=True, status=RunStatus.RUNNING, startedAt=now_iso(),
    )
    store.create_run(legacy)
    assert store.reconcile_orphans() == 1
    assert store.get_run(durable.id)["status"] == "running"
    assert store.get_run(legacy.id)["status"] == "failed"
