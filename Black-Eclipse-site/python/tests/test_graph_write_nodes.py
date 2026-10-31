"""Scoped file writes (Phase 5): confinement, caps, compiler envelope."""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.write_nodes import exec_file_write

REGISTRY = build_default_registry()


def _exec(tmp_path, monkeypatch, *, path: str, content="hello", scope="workspace", append=False):
    monkeypatch.setenv("HARNESS_GRAPH_WRITE_ROOTS", json.dumps({"workspace": str(tmp_path)}))
    return exec_file_write(NodeExecContext(
        node_id="write", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"content": content}, config={"scope": scope, "path": path, "append": append},
    ))


def test_writes_a_relative_path_inside_the_scope(tmp_path, monkeypatch):
    result = _exec(tmp_path, monkeypatch, path="reports/aapl.txt", content="close=100")
    assert result["path"] == "reports/aapl.txt"
    assert result["bytes"] == len("close=100")
    assert (tmp_path / "reports" / "aapl.txt").read_text() == "close=100"


def test_append_adds_to_the_existing_file(tmp_path, monkeypatch):
    _exec(tmp_path, monkeypatch, path="log.txt", content="one\n")
    _exec(tmp_path, monkeypatch, path="log.txt", content="two\n", append=True)
    assert (tmp_path / "log.txt").read_text() == "one\ntwo\n"


def test_objects_are_json_encoded(tmp_path, monkeypatch):
    _exec(tmp_path, monkeypatch, path="data.json", content={"a": 1})
    assert json.loads((tmp_path / "data.json").read_text()) == {"a": 1}


@pytest.mark.parametrize("path", ["../escape.txt", "../../etc/passwd", "/etc/passwd"])
def test_paths_outside_the_scope_are_refused(tmp_path, monkeypatch, path):
    with pytest.raises(ValueError, match="relative|escapes|absolute|cannot contain"):
        _exec(tmp_path, monkeypatch, path=path)


def test_an_unknown_scope_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="unknown write scope"):
        _exec(tmp_path, monkeypatch, path="a.txt", scope="not-configured")


def test_a_symlink_escape_is_refused(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating a symlink requires a Windows privilege")
    with pytest.raises(ValueError, match="escapes"):
        _exec(tmp_path, monkeypatch, path="link/secret.txt")


def _ir(scope: str = "workspace") -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_write", "name": "Write",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0",
             "config": {"seed": "x"}, "layout": {"x": 0, "y": 0}},
            {"id": "write", "type": "file.write", "version": "1.0.0",
             "config": {"scope": scope, "path": "out.txt"}, "layout": {"x": 200, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0",
             "config": {}, "layout": {"x": 400, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "write", "targetHandle": "content"},
            {"id": "e2", "source": "write", "sourceHandle": "path", "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["file.write"],
    })


def test_a_test_run_never_writes():
    plan = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert plan.executable is False
    assert any(d.code == "permission_denied" for d in plan.diagnostics)


def test_an_operator_run_needs_the_exact_scope():
    missing = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(test_run=False, granted_capabilities=frozenset({"file.write"})),
    )
    assert missing.executable is False
    assert any(d.code == "write_scope_denied" for d in missing.diagnostics)

    allowed = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(
            test_run=False,
            granted_capabilities=frozenset({"file.write"}),
            allowed_write_scopes=frozenset({"workspace"}),
        ),
    )
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]
