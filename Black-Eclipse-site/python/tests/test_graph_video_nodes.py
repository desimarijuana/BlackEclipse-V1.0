"""Graph Studio's video render node: local write, operator-granted."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, SideEffect, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.video_nodes import set_video_runner

REGISTRY = build_default_registry()


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _ir(nodes: list[dict], edges: list[dict] | None = None) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_video", "name": "Video",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges or [],
        "settings": {
            "executionMode": "research", "failFast": False,
            "maxConcurrency": 1, "timeoutMs": 0,
        },
        "requiredCapabilities": ["video.render"],
    })


def _graph():
    return _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v1", "video.render", {"title": "Recap"}),
            _node("out", "output.result"),
        ],
        [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "v1", "targetHandle": "symbols"},
            {"id": "e2", "source": "v1", "sourceHandle": "job", "target": "out", "targetHandle": "value"},
        ],
    )


def test_video_node_is_registered_with_an_executor():
    definition = REGISTRY.get("video.render")
    assert definition is not None
    assert definition.executor is not None and definition.available is True
    assert definition.capabilities == ("video.render",)
    assert definition.side_effects == SideEffect.WRITE
    assert [port.id for port in definition.inputs] == ["symbols"]
    assert {port.id for port in definition.outputs} == {"project", "job"}


def test_test_runs_never_render_and_operator_runs_need_a_write_grant():
    denied = compile_workflow(_graph(), REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "permission_denied" for d in denied.diagnostics)

    ungranted = compile_workflow(_graph(), REGISTRY, RunGrants(
        test_run=False, granted_capabilities=frozenset({"video.render"}),
    ))
    assert ungranted.executable is False
    assert any("writes locally" in d.message for d in ungranted.diagnostics)

    allowed = compile_workflow(_graph(), REGISTRY, RunGrants(
        test_run=False, granted_capabilities=frozenset({"video.render"}),
        allow_write=True,
    ))
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]


def test_executor_builds_the_project_through_the_bound_pipeline():
    captured = {}

    def runner(context, symbols, title, mode):
        captured.update({"symbols": symbols, "title": title, "mode": mode})
        return {
            "project": {"id": "proj_1", "kind": "storyboard"},
            "job": {"status": "succeeded", "artifactId": "art_1"},
        }

    set_video_runner(runner)
    try:
        result = REGISTRY.get("video.render").executor(NodeExecContext(
            node_id="v1", run_id="run", mode=ExecutionMode.RESEARCH,
            inputs={"symbols": ["aapl", "MSFT"]},
            config={"title": "Daily", "mode": "draft"},
        ))
    finally:
        set_video_runner(None)
    assert result["project"]["id"] == "proj_1"
    assert result["job"]["status"] == "succeeded"
    assert captured == {"symbols": ["AAPL", "MSFT"], "title": "Daily", "mode": "draft"}


def test_executor_validates_symbols_and_the_bound_pipeline():
    set_video_runner(None)
    with pytest.raises(ValueError, match="video pipeline"):
        REGISTRY.get("video.render").executor(NodeExecContext(
            node_id="v1", run_id="run", mode=ExecutionMode.RESEARCH,
            inputs={"symbols": ["AAPL"]}, config={},
        ))
    with pytest.raises(ValueError, match="bounded"):
        REGISTRY.get("video.render").executor(NodeExecContext(
            node_id="v1", run_id="run", mode=ExecutionMode.RESEARCH,
            inputs={"symbols": ["A", "B", "C", "D", "E", "F"]}, config={},
        ))


def test_ts_registry_mirrors_the_video_node():
    registry_ts = (
        Path(__file__).resolve().parents[2]
        / "src" / "lib" / "graph-studio" / "registry.ts"
    )
    text = registry_ts.read_text(encoding="utf-8")
    assert "type: 'video.render'" in text
    assert "capabilities: ['video.render']" in text
