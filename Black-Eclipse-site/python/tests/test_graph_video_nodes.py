"""Graph Studio's video node declaration (Phase 8).

The node is deliberately executor-less: the graph runtime cannot yet execute an
async queued Fabric render, and its UI/schedule envelope refuses effectful
nodes. These tests pin the declaration, its honest compile diagnostic, and the
TS↔Python registry lockstep.
"""

from __future__ import annotations

from pathlib import Path

from harness.graph_runtime.compiler import compile_workflow
from harness.graph_runtime.model import SideEffect, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry


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
        "requiredCapabilities": [],
    })


def test_video_node_is_registered_and_declared_only():
    definition = build_default_registry().get("video.render")
    assert definition is not None
    assert definition.executor is None and definition.available is False
    assert definition.capabilities == ("video.render",)
    assert definition.side_effects == SideEffect.WRITE
    assert definition.since_phase  # the diagnostic names what it waits for
    assert [port.id for port in definition.inputs] == ["symbols"]
    assert {port.id for port in definition.outputs} == {"project", "job"}


def test_compile_refuses_the_node_with_an_actionable_diagnostic():
    plan = compile_workflow(_ir([_node("v1", "video.render")]), build_default_registry())
    assert plan.executable is False
    unavailable = [d for d in plan.diagnostics if d.code == "executor_unavailable"]
    assert unavailable, [d.message for d in plan.diagnostics]
    assert "async graph execution" in unavailable[0].message


def test_ts_registry_mirrors_the_video_node():
    """The two registries are hand-maintained mirrors; a new Python node that is
    missing from the TS palette would fail validation in the editor."""
    registry_ts = (
        Path(__file__).resolve().parents[2]
        / "src" / "lib" / "graph-studio" / "registry.ts"
    )
    text = registry_ts.read_text(encoding="utf-8")
    assert "type: 'video.render'" in text
    assert "capabilities: ['video.render']" in text
