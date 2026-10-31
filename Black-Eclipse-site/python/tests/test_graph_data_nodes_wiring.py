"""Wiring proof for the six basic data/write nodes shown in Graph Studio.

Each node is placed in a minimal workflow and executed through the real
compiler + executor (not just its executor function), because "the node exists
in the palette" is not the same as "the node is usable in a graph":

    data.value          Constant / input
    data.set_variables  Set variables
    data.json.parse     Parse JSON
    data.dataset.save   Save dataset
    data.dataset.load   Load dataset
    file.write          Write file (registry-write.ts)

The last test chains all six in one operator run, which is the shape a user
builds by dragging them onto the canvas. `file.write` is a WRITE effect, so it
cannot run in a test run by design; it is exercised with an operator grant for
the `workspace` scope backed by a temp directory.
"""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.datasets import GraphDatasetStore, set_dataset_store
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import NodeStatus, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.persistence import AgentMemoryStore

ALL_DATA_CAPABILITIES = frozenset({"dataset.read", "dataset.write", "file.write"})


@pytest.fixture()
def dataset_store(tmp_path):
    store = GraphDatasetStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))
    set_dataset_store(store)
    try:
        yield store
    finally:
        set_dataset_store(None)


@pytest.fixture()
def write_scope(tmp_path, monkeypatch):
    """Point the `workspace` scope at a temp dir so tests never touch the repo."""
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("HARNESS_GRAPH_WRITE_ROOTS", json.dumps({"workspace": str(root)}))
    return root


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "version": "1.0.0",
        "config": config or {},
        "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }


def _ir(
    nodes: list[dict],
    edges: list[dict],
    capabilities: list[str] | None = None,
) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1,
        "id": "wf_data_nodes",
        "name": "Data nodes",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "executionMode": "research",
            "failFast": False,
            "maxConcurrency": 1,
            "timeoutMs": 0,
        },
        "requiredCapabilities": capabilities or [],
    })


def _run(ir: WorkflowIR, grants: RunGrants | None = None):
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, grants or RunGrants(test_run=True))
    assert plan.executable, [d.message for d in plan.diagnostics]
    run = GraphExecutor(ir, plan, registry, run_id="grun_data_nodes").execute()
    by_id = {record.node_id: record for record in run.node_runs}
    return run, by_id


def _assert_succeeded(run, by_id, *node_ids: str) -> None:
    assert run.status == RunStatus.SUCCEEDED
    for node_id in node_ids:
        record = by_id[node_id]
        assert record.status == NodeStatus.SUCCEEDED, (node_id, record.error)


# ── One node at a time ───────────────────────────────────────────────────────


def test_data_value_emits_literal_and_coerces_its_type():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": "42", "dataType": "number"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "out", "value"),
        ],
    )
    run, by_id = _run(ir, RunGrants(test_run=False, granted_capabilities=ALL_DATA_CAPABILITIES))
    _assert_succeeded(run, by_id, "v", "out")
    assert by_id["v"].outputs["value"] == 42.0
    assert by_id["out"].inputs["value"] == 42.0


def test_data_value_wired_input_overrides_the_configured_literal():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": "configured", "dataType": "string"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "out", "value"),
        ],
    )
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, RunGrants())
    run = GraphExecutor(
        ir, plan, registry, run_id="grun_value_override", run_input="from-trigger",
    ).execute()
    _assert_succeeded(run, {r.node_id: r for r in run.node_runs}, "v")
    assert {r.node_id: r for r in run.node_runs}["v"].outputs["value"] == "from-trigger"


def test_set_variables_merges_config_over_input_object():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("src", "data.value", {"value": '{"env": "dev", "symbol": "AAPL"}', "dataType": "object"}),
            _node("vars", "data.set_variables", {"variables": {"env": "prod"}}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "src", "in"),
            _edge("e2", "src", "value", "vars", "in"),
            _edge("e3", "vars", "variables", "out", "value"),
        ],
    )
    run, by_id = _run(ir)
    _assert_succeeded(run, by_id, "vars", "out")
    assert by_id["vars"].outputs["variables"] == {"env": "prod", "symbol": "AAPL"}
    assert by_id["out"].inputs["value"] == {"env": "prod", "symbol": "AAPL"}


def test_json_parse_returns_structured_values():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("text", "data.value", {"value": '{"rows": [1, 2], "ok": true}', "dataType": "string"}),
            _node("parse", "data.json.parse", {"strict": True}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "text", "in"),
            _edge("e2", "text", "value", "parse", "text"),
            _edge("e3", "parse", "value", "out", "value"),
        ],
    )
    run, by_id = _run(ir)
    _assert_succeeded(run, by_id, "parse", "out")
    assert by_id["parse"].outputs["value"] == {"rows": [1, 2], "ok": True}
    assert by_id["out"].inputs["value"] == {"rows": [1, 2], "ok": True}


def _json_parse_ir(strict: bool) -> WorkflowIR:
    return _ir(
        [
            _node("trig", "trigger.manual"),
            _node("text", "data.value", {"value": "not json", "dataType": "string"}),
            _node("parse", "data.json.parse", {"strict": strict}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "text", "in"),
            _edge("e2", "text", "value", "parse", "text"),
            _edge("e3", "parse", "value", "out", "value"),
        ],
    )


def test_json_parse_strict_false_passes_text_through_and_strict_fails_loudly():
    run, by_id = _run(_json_parse_ir(strict=False))
    _assert_succeeded(run, by_id, "parse", "out")
    assert by_id["parse"].outputs["value"] == "not json"

    strict = _json_parse_ir(strict=True)
    registry = build_default_registry()
    plan = compile_workflow(strict, registry, RunGrants())
    failed = GraphExecutor(strict, plan, registry, run_id="grun_strict").execute()
    failed_by_id = {r.node_id: r for r in failed.node_runs}
    assert failed.status == RunStatus.FAILED
    assert failed_by_id["parse"].status == NodeStatus.FAILED
    assert "not valid JSON" in (failed_by_id["parse"].error or "")
    assert failed_by_id["out"].status == NodeStatus.SKIPPED


def test_dataset_save_and_load_roundtrip_through_a_graph(dataset_store):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": '{"rows": [{"close": 1}, {"close": 2}]}', "dataType": "object"}),
            _node("save", "data.dataset.save", {"name": "bars", "ttlHours": 1}),
            _node("load", "data.dataset.load"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "save", "value"),
            _edge("e3", "save", "ref", "load", "ref"),
            _edge("e4", "load", "value", "out", "value"),
        ],
        capabilities=["dataset.read", "dataset.write"],
    )
    run, by_id = _run(ir, RunGrants(test_run=False, granted_capabilities=ALL_DATA_CAPABILITIES))
    _assert_succeeded(run, by_id, "save", "load", "out")
    assert by_id["save"].outputs["ref"].startswith("gds:")
    assert by_id["save"].outputs["meta"]["name"] == "bars"
    assert by_id["load"].outputs["value"] == {"rows": [{"close": 1}, {"close": 2}]}
    assert by_id["out"].inputs["value"] == {"rows": [{"close": 1}, {"close": 2}]}


def test_dataset_load_missing_ref_fails_explicitly(dataset_store):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("ref", "data.value", {"value": "gds:does-not-exist", "dataType": "string"}),
            _node("load", "data.dataset.load"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "ref", "in"),
            _edge("e2", "ref", "value", "load", "ref"),
            _edge("e3", "load", "value", "out", "value"),
        ],
    )
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, RunGrants())
    run = GraphExecutor(ir, plan, registry, run_id="grun_missing_ref").execute()
    by_id = {r.node_id: r for r in run.node_runs}
    assert run.status == RunStatus.FAILED
    assert by_id["load"].status == NodeStatus.FAILED
    assert "does not exist" in (by_id["load"].error or "").lower()


def test_file_write_writes_inside_the_granted_workspace_scope(dataset_store, write_scope):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("content", "data.value", {"value": "hello eclipse", "dataType": "string"}),
            _node("path", "data.value", {"value": "reports/note.txt", "dataType": "string"}),
            _node("write", "file.write", {"scope": "workspace", "append": False}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "content", "in"),
            _edge("e2", "content", "value", "write", "content"),
            _edge("e3", "path", "value", "write", "path"),
            _edge("e4", "write", "path", "out", "value"),
        ],
        capabilities=["file.write"],
    )
    grants = RunGrants(
        test_run=False,
        granted_capabilities=ALL_DATA_CAPABILITIES,
        allowed_write_scopes=frozenset({"workspace"}),
    )
    run, by_id = _run(ir, grants)
    _assert_succeeded(run, by_id, "write", "out")
    assert by_id["write"].outputs == {
        "path": "reports/note.txt",
        "bytes": len(b"hello eclipse"),
        "scope": "workspace",
    }
    assert (write_scope / "reports" / "note.txt").read_text(encoding="utf-8") == "hello eclipse"


def test_file_write_is_refused_in_a_test_run_and_by_an_ungranted_scope(write_scope):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": "x", "dataType": "string"}),
            _node("write", "file.write", {"scope": "workspace", "path": "a.txt"}),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "write", "content"),
        ],
    )
    test_plan = compile_workflow(ir, build_default_registry(), RunGrants(test_run=True))
    assert test_plan.executable is False
    assert "permission_denied" in {d.code for d in test_plan.diagnostics}

    denied_scope = compile_workflow(
        ir,
        build_default_registry(),
        RunGrants(test_run=False, granted_capabilities=ALL_DATA_CAPABILITIES),
    )
    assert denied_scope.executable is False
    assert "write_scope_denied" in {d.code for d in denied_scope.diagnostics}


def test_file_write_refuses_traversal(write_scope):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": "x", "dataType": "string"}),
            _node("write", "file.write", {"scope": "workspace", "path": "../escape.txt"}),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "write", "content"),
        ],
    )
    grants = RunGrants(
        test_run=False,
        granted_capabilities=ALL_DATA_CAPABILITIES,
        allowed_write_scopes=frozenset({"workspace"}),
    )
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, grants)
    run = GraphExecutor(ir, plan, registry, run_id="grun_traversal").execute()
    by_id = {r.node_id: r for r in run.node_runs}
    assert run.status == RunStatus.FAILED
    assert by_id["write"].status == NodeStatus.FAILED
    assert "cannot contain '..'" in (by_id["write"].error or "")
    assert not (write_scope.parent / "escape.txt").exists()


def test_file_write_uses_config_path_and_can_append(dataset_store, write_scope):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("a", "data.value", {"value": "first", "dataType": "string"}),
            _node("b", "data.value", {"value": "-second", "dataType": "string"}),
            _node("w1", "file.write", {"scope": "workspace", "path": "log.txt"}),
            _node("w2", "file.write", {"scope": "workspace", "path": "log.txt", "append": True}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "a", "in"),
            _edge("e2", "a", "value", "w1", "content"),
            _edge("e3", "b", "value", "w2", "content"),
            # Feeding w1's path back into w2's path keeps the two writes ordered
            # and makes w2 append to the same file.
            _edge("e4", "w1", "path", "w2", "path"),
            _edge("e5", "w2", "path", "out", "value"),
        ],
        capabilities=["file.write"],
    )
    grants = RunGrants(
        test_run=False,
        granted_capabilities=ALL_DATA_CAPABILITIES,
        allowed_write_scopes=frozenset({"workspace"}),
    )
    run, by_id = _run(ir, grants)
    _assert_succeeded(run, by_id, "w1", "w2", "out")
    assert (write_scope / "log.txt").read_text(encoding="utf-8") == "first-second"


def test_file_write_falls_back_to_its_configured_path(write_scope):
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"value": "configured path", "dataType": "string"}),
            _node("write", "file.write", {"scope": "workspace", "path": "from-config.txt"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "write", "content"),
            _edge("e3", "write", "path", "out", "value"),
        ],
        capabilities=["file.write"],
    )
    grants = RunGrants(
        test_run=False,
        granted_capabilities=ALL_DATA_CAPABILITIES,
        allowed_write_scopes=frozenset({"workspace"}),
    )
    run, by_id = _run(ir, grants)
    _assert_succeeded(run, by_id, "write")
    assert (write_scope / "from-config.txt").read_text(encoding="utf-8") == "configured path"


# ── All six nodes in one workflow ────────────────────────────────────────────


def test_all_six_nodes_chain_in_one_operator_run(dataset_store, write_scope):
    """The drag-and-drop shape: constant → set variables → parse JSON →
    save/load dataset → write file → result."""
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("const", "data.value", {"value": '{"symbol": "AAPL", "rows": [1, 2, 3]}', "dataType": "string"}),
            _node("parse", "data.json.parse", {"strict": True}),
            _node("vars", "data.set_variables", {"variables": {"env": "test"}}),
            _node("save", "data.dataset.save", {"name": "payload", "ttlHours": 0}),
            _node("load", "data.dataset.load"),
            _node("path", "data.value", {"value": "out/payload.json", "dataType": "string"}),
            _node("write", "file.write", {"scope": "workspace", "append": False}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "const", "in"),
            _edge("e2", "const", "value", "parse", "text"),
            _edge("e3", "parse", "value", "vars", "in"),
            _edge("e4", "vars", "variables", "save", "value"),
            _edge("e5", "save", "ref", "load", "ref"),
            _edge("e6", "load", "value", "write", "content"),
            _edge("e7", "path", "value", "write", "path"),
            _edge("e8", "load", "value", "out", "value"),
        ],
        capabilities=["dataset.read", "dataset.write", "file.write"],
    )
    grants = RunGrants(
        test_run=False,
        granted_capabilities=ALL_DATA_CAPABILITIES,
        allowed_write_scopes=frozenset({"workspace"}),
    )
    run, by_id = _run(ir, grants)
    _assert_succeeded(
        run, by_id, "const", "parse", "vars", "save", "load", "path", "write", "out",
    )

    expected = {"symbol": "AAPL", "rows": [1, 2, 3], "env": "test"}
    assert by_id["parse"].outputs["value"] == {"symbol": "AAPL", "rows": [1, 2, 3]}
    assert by_id["vars"].outputs["variables"] == expected
    assert by_id["save"].outputs["meta"]["valueType"] == "object"
    assert by_id["load"].outputs["value"] == expected
    assert by_id["out"].inputs["value"] == expected

    written = write_scope / "out" / "payload.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == expected
    assert by_id["write"].outputs["bytes"] == len(written.read_bytes())
