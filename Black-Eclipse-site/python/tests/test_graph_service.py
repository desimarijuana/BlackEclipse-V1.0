"""Graph runtime — the service: persistence, background runs, cancel, and the
compile gate."""

from __future__ import annotations

import time

import pytest

from harness.graph_runtime.compiler import RunGrants
from harness.graph_runtime.model import PortDef, PortType, RunStatus
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef
from harness.graph_runtime.service import GraphCompileError, GraphService
from harness.graph_runtime.store import GraphRunStore
from harness.persistence import AgentMemoryStore


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _payload(nodes, edges):
    return {
        "irVersion": 1, "id": "wf_service", "name": "Service",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    }


def _pure_graph():
    return _payload(
        [
            _node("trig", "trigger.manual", {"seed": "3"}),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("f", "transform.formula", {"expression": "x + 1"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "f", "x"),
            _edge("e3", "f", "result", "out", "value"),
        ],
    )


def _ir(payload):
    from harness.graph_runtime.model import WorkflowIR

    return WorkflowIR.model_validate(payload)


@pytest.fixture()
def service(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    graph_service = GraphService(GraphRunStore(store))
    yield graph_service
    store.close()


def test_run_sync_persists_an_inspectable_run(service):
    run = service.run_sync(_ir(_pure_graph()), workflow_version=4)
    assert run.status == RunStatus.SUCCEEDED
    assert run.workflow_version == 4

    record = service.get_run(run.id)
    assert record is not None
    assert record["status"] == "succeeded"
    assert record["workflowVersion"] == 4
    assert any(n["nodeId"] == "out" for n in record["nodeRuns"])
    assert record["plan"]["executable"] is True

    listed = service.list_runs("wf_service")
    assert [r["id"] for r in listed] == [run.id]
    assert service.list_runs("other-workflow") == []


def test_compile_gate_refuses_a_broken_graph(service):
    broken = _payload([_node("trig", "trigger.manual")], [])  # no terminal
    with pytest.raises(GraphCompileError) as excinfo:
        service.run_sync(_ir(broken))
    assert excinfo.value.plan.executable is False
    assert "missing_terminal" in [d.code for d in excinfo.value.plan.diagnostics]


def test_start_run_completes_on_a_background_thread(service):
    started = service.start_run(_ir(_pure_graph()))
    assert started["status"] in ("running", "succeeded")
    run_id = started["id"]

    deadline = time.time() + 10
    record = started
    while time.time() < deadline:
        record = service.get_run(run_id) or record
        if record["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.02)
    assert record["status"] == "succeeded", record.get("error")
    assert service.get_run(run_id)["status"] == "succeeded"


def test_cancel_stops_a_running_graph(tmp_path):
    import threading

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        registry = build_default_registry()
        release = threading.Event()

        def blocking(_ctx):
            release.wait(timeout=5)
            return {"out": 1}

        registry.register(NodeDef(
            type="test.blocking", version="1.0.0", label="Blocking", category="transform",
            inputs=(PortDef(id="in", name="In", type=PortType.ANY),),
            outputs=(PortDef(id="out", name="Out", type=PortType.ANY),),
            timeout_ms=5_000, executor=blocking,
        ))
        graph_service = GraphService(GraphRunStore(store), registry)
        payload = _payload(
            [_node("trig", "trigger.manual"), _node("b", "test.blocking"), _node("out", "output.result")],
            [_edge("e1", "trig", "start", "b", "in"), _edge("e2", "b", "out", "out", "value")],
        )
        started = graph_service.start_run(_ir(payload))
        time.sleep(0.05)
        graph_service.cancel(started["id"])
        release.set()

        deadline = time.time() + 10
        record = graph_service.get_run(started["id"]) or {}
        while time.time() < deadline and record.get("status") == "running":
            time.sleep(0.02)
            record = graph_service.get_run(started["id"]) or {}
        assert record.get("status") == "cancelled", record
    finally:
        release.set()
        store.close()


def test_store_roundtrip_and_delete(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        run_store = GraphRunStore(store)
        graph_service = GraphService(run_store)
        run = graph_service.run_sync(_ir(_pure_graph()))
        assert run_store.get_run(run.id)["id"] == run.id
        assert run_store.delete_run(run.id) == 1
        assert run_store.get_run(run.id) is None
    finally:
        store.close()


def test_run_ids_are_unique(service):
    first = service.run_sync(_ir(_pure_graph()))
    second = service.run_sync(_ir(_pure_graph()))
    assert first.id != second.id
    assert len(service.list_runs("wf_service")) == 2


def test_orphaned_running_runs_are_reconciled(tmp_path):
    """A run left `running` by a previous process must not stay phantom."""
    from harness.graph_runtime.model import GraphRun, RunStatus
    from harness.persistence import now_iso

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        run_store = GraphRunStore(store)
        run_store.create_run(GraphRun(
            id="grun_orphan", workflowId="wf_service", irVersion=1, mode="research",
            testRun=True, status=RunStatus.RUNNING, startedAt=now_iso(),
        ))
        assert run_store.get_run("grun_orphan")["status"] == "running"
        assert run_store.reconcile_orphans() == 1
        record = run_store.get_run("grun_orphan")
        assert record["status"] == "failed"
        assert "interrupted" in (record["error"] or "")
        # Idempotent: nothing left to reconcile.
        assert run_store.reconcile_orphans() == 0
    finally:
        store.close()


def test_grants_are_recorded_on_the_run(service):
    run = service.run_sync(_ir(_pure_graph()), grants=RunGrants(test_run=False))
    assert run.test_run is False
    assert service.get_run(run.id)["testRun"] is False
