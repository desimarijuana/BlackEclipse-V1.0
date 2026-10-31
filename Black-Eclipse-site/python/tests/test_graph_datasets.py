"""Graph runtime datasets: bounded local refs, not a second market-data store.

The save node is a LOCAL write: a test run may use it, while external write,
network and trading effects remain denied. A missing/expired ref fails
explicitly and a too-large/non-JSON payload is refused.
"""

from __future__ import annotations

import pytest

from harness.graph_runtime import datasets as datasets_module
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.datasets import (
    DatasetExpired,
    DatasetNotFound,
    DatasetSerializationError,
    DatasetTooLarge,
    GraphDatasetStore,
    set_dataset_store,
)
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import ExecutionMode, NodeStatus, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def dataset_store(tmp_path):
    store = GraphDatasetStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))
    set_dataset_store(store)
    try:
        yield store
    finally:
        set_dataset_store(None)


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {
        "id": edge_id, "source": source, "sourceHandle": source_handle,
        "target": target, "targetHandle": target_handle,
    }


def _ir() -> WorkflowIR:
    nodes = [
        _node("trig", "trigger.manual", {"seed": ""}),
        _node("value", "data.value", {"dataType": "object", "value": '{"rows": [1, 2]}'}),
        _node("save", "data.dataset.save", {"name": "bars", "ttlHours": 0}),
        _node("load", "data.dataset.load", {}),
        _node("out", "output.result", {"label": "Loaded"}),
    ]
    edges = [
        _edge("e1", "trig", "start", "value", "in"),
        _edge("e2", "value", "value", "save", "value"),
        _edge("e3", "save", "ref", "load", "ref"),
        _edge("e4", "load", "value", "out", "value"),
    ]
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_datasets", "name": "Datasets",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 2, "timeoutMs": 0},
        "requiredCapabilities": ["dataset.read", "dataset.write"],
    })


def test_save_load_roundtrip_and_metadata(dataset_store):
    meta = dataset_store.save("bars", [{"close": 1.0}, {"close": 2.0}], ttl_seconds=3600)
    assert meta["ref"].startswith("gds:")
    assert meta["rows"] == 2
    assert meta["valueType"] == "array"
    assert dataset_store.load(meta["ref"]) == [{"close": 1.0}, {"close": 2.0}]
    assert dataset_store.meta(meta["ref"])["contentHash"] == meta["contentHash"]


def test_missing_and_expired_refs_fail_explicitly(dataset_store):
    with pytest.raises(DatasetNotFound):
        dataset_store.load("gds:missing")
    meta = dataset_store.save("old", {"a": 1})
    dataset_store._db.execute(
        "UPDATE HarnessGraphDataset SET expiresAt='2000-01-01T00:00:00.000Z' WHERE id=?",
        (meta["ref"][4:],),
    )
    dataset_store._db.commit()
    with pytest.raises(DatasetExpired):
        dataset_store.load(meta["ref"])
    with pytest.raises(DatasetNotFound):
        dataset_store.load(meta["ref"])  # the expired row was removed


def test_datasets_are_owner_scoped(dataset_store):
    meta = dataset_store.save("mine", {"a": 1}, owner="alice")
    assert dataset_store.load(meta["ref"], owner="alice") == {"a": 1}
    with pytest.raises(DatasetNotFound):
        dataset_store.load(meta["ref"], owner="bob")
    with pytest.raises(DatasetNotFound):
        dataset_store.meta(meta["ref"], owner="bob")
    assert dataset_store.list(owner="bob") == []
    assert len(dataset_store.list(owner="alice")) == 1


def test_size_and_serialization_limits(dataset_store, monkeypatch):
    monkeypatch.setattr(datasets_module, "MAX_DATASET_BYTES", 8)
    with pytest.raises(DatasetTooLarge):
        dataset_store.save("big", {"x": "abcdef"})
    with pytest.raises(DatasetSerializationError):
        dataset_store.save("bad", {1, 2})


def test_json_parse_reads_its_config_when_the_port_is_unwired():
    registry = build_default_registry()
    parse = registry.get("data.json.parse")
    assert parse is not None and parse.executor is not None
    out = parse.executor(NodeExecContext(
        node_id="parse", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={"text": '{"a": 1}', "strict": True},
    ))
    assert out == {"value": {"a": 1}}


def test_save_and_load_use_their_config_fallbacks(dataset_store):
    registry = build_default_registry()
    save = registry.get("data.dataset.save")
    load = registry.get("data.dataset.load")
    assert save is not None and save.executor is not None
    assert load is not None and load.executor is not None

    saved = save.executor(NodeExecContext(
        node_id="save", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={"name": "inline", "ttlHours": 0, "valueJson": '{"rows": [1, 2]}'},
    ))
    loaded = load.executor(NodeExecContext(
        node_id="load", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={"ref": saved["ref"]},
    ))
    assert loaded["value"] == {"rows": [1, 2]}
    assert loaded["meta"]["ref"] == saved["ref"]


def test_executors_roundtrip_through_the_registry(dataset_store):
    registry = build_default_registry()
    save = registry.get("data.dataset.save")
    load = registry.get("data.dataset.load")
    assert save is not None and save.executor is not None
    assert load is not None and load.executor is not None

    saved = save.executor(NodeExecContext(
        node_id="save", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"value": {"rows": [1, 2]}}, config={"name": "bars", "ttlHours": 0},
    ))
    loaded = load.executor(NodeExecContext(
        node_id="load", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"ref": saved["ref"]}, config={},
    ))
    assert loaded["value"] == {"rows": [1, 2]}
    assert loaded["meta"]["ref"] == saved["ref"]


def test_test_run_may_use_local_datasets_and_executes(dataset_store):
    registry = build_default_registry()
    ir = _ir()
    plan = compile_workflow(ir, registry, RunGrants(test_run=True))
    assert plan.executable, [d.message for d in plan.diagnostics]

    run = GraphExecutor(ir, plan, registry, run_id="grun_datasets").execute()
    assert run.status == RunStatus.SUCCEEDED
    by_id = {record.node_id: record for record in run.node_runs}
    assert by_id["save"].status == NodeStatus.SUCCEEDED
    assert by_id["load"].status == NodeStatus.SUCCEEDED
    assert by_id["out"].status == NodeStatus.SUCCEEDED


def test_non_test_run_needs_dataset_capabilities(dataset_store):
    plan = compile_workflow(_ir(), build_default_registry(), RunGrants(test_run=False))
    assert plan.executable is False
    assert "capability_denied" in [diagnostic.code for diagnostic in plan.diagnostics]
