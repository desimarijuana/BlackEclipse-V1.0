"""Graph assistant: the tools only ever produce validated operations.

These tests exercise the deterministic session directly and the agent loop with
a scripted runtime — no provider, no network.
"""

from __future__ import annotations

import asyncio
import json

from harness.graph_runtime.assistant import (
    GraphAssistantSession,
    _run_tool,
    assist_graph,
    stream_assist,
)
from harness.graph_runtime.model import WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.model_runtime.types import ModelResponse, ToolCall

REGISTRY = build_default_registry()


def _ir() -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 2,
        "id": "wf_assistant",
        "name": "Assistant test",
        "description": "",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0", "config": {}, "layout": {"x": 300, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 4, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


def test_search_and_schema_come_from_the_real_registry():
    session = GraphAssistantSession(_ir(), REGISTRY)
    found = session.search_nodes("filter", 5)
    assert found["ok"] is True
    assert any(item["type"] == "logic.filter" for item in found["nodes"])

    schema = session.get_node_schema("logic.filter")
    assert schema["ok"] is True
    assert any(port["id"] == "items" for port in schema["node"]["inputs"])
    assert any(field["name"] == "expression" for field in schema["node"]["config"])


def test_add_node_records_an_operation_and_can_auto_wire():
    session = GraphAssistantSession(_ir(), REGISTRY)
    result = session.add_node("logic.filter", after_node_id="trig")
    assert result["ok"] is True
    node_id = result["nodeId"]
    assert result.get("edge", {}).get("target") == node_id
    assert any(item["op"] == "add_node" and item["node"]["id"] == node_id for item in session.ops)
    assert any(item["op"] == "add_edge" for item in session.ops)
    assert session.ir.node(node_id) is not None


def test_unknown_types_and_invalid_config_are_refused():
    session = GraphAssistantSession(_ir(), REGISTRY)
    assert session.add_node("does.not.exist")["ok"] is False

    added = session.add_node("logic.filter")
    assert added["ok"] is True
    result = session.update_node_config(added["nodeId"], {"expression": 42})
    assert result["ok"] is False
    assert "invalid config" in result["error"]


def test_connecting_rejects_incompatible_ports_and_cycles():
    session = GraphAssistantSession(_ir(), REGISTRY)
    filter_id = session.add_node("logic.filter")["nodeId"]
    map_id = session.add_node("logic.map")["nodeId"]

    assert session.connect_nodes(filter_id, "items", map_id, "items")["ok"] is True
    # map -> filter would close a loop.
    cycle = session.connect_nodes(map_id, "items", filter_id, "items")
    assert cycle["ok"] is False
    assert "cycle" in cycle["error"]


def test_remove_node_drops_its_edges():
    session = GraphAssistantSession(_ir(), REGISTRY)
    filter_id = session.add_node("logic.filter", after_node_id="trig")["nodeId"]
    assert any(edge.target == filter_id for edge in session.ir.edges)
    assert session.remove_node(filter_id)["ok"] is True
    assert session.ir.node(filter_id) is None
    assert all(edge.source != filter_id and edge.target != filter_id for edge in session.ir.edges)


def test_ask_mode_refuses_mutating_tools():
    session = GraphAssistantSession(_ir(), REGISTRY)
    refused = asyncio.run(_run_tool(session, "add_node", {"type": "logic.filter"}, edit=False))
    assert refused["ok"] is False
    assert "ask mode" in refused["error"]
    assert session.ops == []


def test_ask_user_stops_the_turn():
    session = GraphAssistantSession(_ir(), REGISTRY)
    result = session.ask_user("Which form should trigger this?")
    assert result["ok"] is True
    assert result["stop"] is True
    assert "Which form" in session.question


class _ScriptedRuntime:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                provider_id="scripted",
                model_id="scripted",
                tool_calls=[ToolCall(id="c1", name="search_nodes", arguments={"query": "filter"})],
            )
        if self.calls == 2:
            return ModelResponse(
                provider_id="scripted",
                model_id="scripted",
                tool_calls=[ToolCall(
                    id="c2",
                    name="add_node",
                    arguments={"type": "logic.filter", "after_node_id": "trig"},
                )],
            )
        return ModelResponse(
            provider_id="scripted",
            model_id="scripted",
            text="Added a filter after the trigger.",
        )


def test_assist_loop_applies_tool_calls_and_returns_ops(monkeypatch):
    runtime = _ScriptedRuntime()
    monkeypatch.setattr("harness.model_runtime.get_runtime", lambda: runtime)

    result = asyncio.run(assist_graph(
        "Add a filter after the trigger",
        ir_payload=_ir().model_dump(by_alias=True),
        model_settings={"provider": "scripted", "model": "scripted"},
        registry=REGISTRY,
        mode="edit",
    ))

    assert result["ok"] is True, result["errors"]
    assert runtime.calls >= 3
    assert any(item["op"] == "add_node" and item["node"]["type"] == "logic.filter" for item in result["ops"])
    assert result["ir"]["nodes"]
    assert result["model"]["provider"] == "scripted"
    assert "filter" in result["answer"].lower()


class _BuildWorkflowRuntime:
    """Builds a complete trigger → output workflow from an empty document."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                provider_id="scripted",
                model_id="scripted",
                tool_calls=[ToolCall(id="c1", name="add_node", arguments={"type": "trigger.manual"})],
            )
        if self.calls == 2:
            return ModelResponse(
                provider_id="scripted",
                model_id="scripted",
                tool_calls=[ToolCall(
                    id="c2",
                    name="add_node",
                    arguments={"type": "output.result", "after_node_id": "n_trigger_manual_1"},
                )],
            )
        if self.calls == 3:
            return ModelResponse(
                provider_id="scripted",
                model_id="scripted",
                tool_calls=[ToolCall(id="c3", name="validate_graph", arguments={})],
            )
        return ModelResponse(
            provider_id="scripted",
            model_id="scripted",
            text="Built a manual trigger and a result output.",
        )


def test_assistant_can_build_a_whole_workflow_from_an_empty_graph(monkeypatch):
    runtime = _BuildWorkflowRuntime()
    monkeypatch.setattr("harness.model_runtime.get_runtime", lambda: runtime)
    empty = _ir()
    empty.nodes = []
    empty.edges = []

    result = asyncio.run(assist_graph(
        "Build a manual workflow that outputs its input",
        ir_payload=empty.model_dump(by_alias=True),
        model_settings={"provider": "scripted", "model": "scripted"},
        registry=REGISTRY,
        mode="edit",
    ))

    assert result["ok"] is True, result["errors"]
    assert [item["op"] for item in result["ops"]].count("add_node") == 2
    assert any(item["op"] == "add_edge" for item in result["ops"])
    nodes = {node["type"] for node in result["ir"]["nodes"]}
    assert nodes == {"trigger.manual", "output.result"}
    assert result["ir"]["edges"]


class _CaptureRuntime:
    def __init__(self) -> None:
        self.messages = []

    async def generate(self, **kwargs):
        self.messages = kwargs.get("messages") or []
        return ModelResponse(provider_id="scripted", model_id="scripted", text="ok")


def test_credentials_are_redacted_before_the_model_sees_the_graph(monkeypatch):
    ir = _ir()
    ir.nodes[0].config = {
        "apiKey": "sk-test-placeholder",
        "headersJson": "Authorization: Bearer test-token",
        "note": "keep me",
    }
    runtime = _CaptureRuntime()
    monkeypatch.setattr("harness.model_runtime.get_runtime", lambda: runtime)

    asyncio.run(assist_graph(
        "What does this workflow do?",
        ir_payload=ir.model_dump(by_alias=True),
        model_settings={"provider": "scripted", "model": "scripted"},
        registry=REGISTRY,
        mode="ask",
    ))

    payload = runtime.messages[1].content
    assert "sk-test-placeholder" not in payload
    assert "Bearer test-token" not in payload
    assert "keep me" in payload


class _FixRunRuntime:
    """Run → see the failure → fix the config → run again."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                provider_id="scripted", model_id="scripted",
                tool_calls=[ToolCall(id="r1", name="run_workflow", arguments={})],
            )
        if self.calls == 2:
            return ModelResponse(
                provider_id="scripted", model_id="scripted",
                tool_calls=[ToolCall(
                    id="r2",
                    name="update_node_config",
                    arguments={"node_id": "out", "config": {"label": "Fixed"}},
                )],
            )
        if self.calls == 3:
            return ModelResponse(
                provider_id="scripted", model_id="scripted",
                tool_calls=[ToolCall(id="r3", name="run_workflow", arguments={})],
            )
        return ModelResponse(
            provider_id="scripted", model_id="scripted",
            text="Fixed the output label and the second run succeeded.",
        )


def test_assistant_runs_inspects_and_fixes(monkeypatch):
    runtime = _FixRunRuntime()
    monkeypatch.setattr("harness.model_runtime.get_runtime", lambda: runtime)
    calls = {"n": 0}

    async def runner(_ir):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "ok": False,
                "status": "failed",
                "failed": [{"nodeId": "out", "label": "Result", "error": "bad label"}],
                "nodes": [],
            }
        return {"ok": True, "status": "succeeded", "failed": [], "nodes": [], "output": {"value": 1}}

    result = asyncio.run(assist_graph(
        "Run it and fix whatever fails",
        ir_payload=_ir().model_dump(by_alias=True),
        model_settings={"provider": "scripted", "model": "scripted"},
        registry=REGISTRY,
        mode="edit",
        runner=runner,
    ))

    assert result["ok"] is True
    assert len(result["runs"]) == 2
    assert result["runs"][0]["ok"] is False
    assert result["runs"][1]["ok"] is True
    assert any(op["op"] == "update_node_config" for op in result["ops"])
    assert "fixed" in result["answer"].lower()


def test_assistant_run_tool_is_bounded(monkeypatch):
    session = GraphAssistantSession(_ir(), REGISTRY, runner=None)
    missing = asyncio.run(session.run_workflow())
    assert missing["ok"] is False
    assert "not available" in missing["error"]

    async def runner(_ir):
        return {"ok": True, "status": "succeeded"}

    session = GraphAssistantSession(_ir(), REGISTRY, runner=runner)
    for _ in range(3):
        result = asyncio.run(session.run_workflow())
    assert result["ok"] is False
    assert "run limit" in result["error"]
    assert len(session.run_log) == 2


def test_stream_assist_emits_progress_and_a_final_result(monkeypatch):
    runtime = _ScriptedRuntime()
    monkeypatch.setattr("harness.model_runtime.get_runtime", lambda: runtime)

    async def collect():
        events = []
        async for chunk in stream_assist(
            "Add a filter after the trigger",
            ir_payload=_ir().model_dump(by_alias=True),
            model_settings={"provider": "scripted", "model": "scripted"},
            registry=REGISTRY,
            mode="edit",
        ):
            assert chunk.startswith("data: ")
            events.append(json.loads(chunk[len("data: "):].strip()))
        return events

    events = asyncio.run(collect())
    assert any(event["type"] == "tool_start" for event in events)
    assert any(event["type"] == "tool_end" and event["ok"] for event in events)
    assert events[-1]["type"] == "result"
    assert any(op["op"] == "add_node" for op in events[-1]["result"]["ops"])


def test_assist_requires_an_instruction_and_a_model():
    for kwargs in (
        {"instruction": "", "model_settings": {"provider": "x", "model": "y"}},
        {"instruction": "add a node", "model_settings": None},
    ):
        try:
            asyncio.run(assist_graph(
                kwargs["instruction"],
                ir_payload=_ir().model_dump(by_alias=True),
                model_settings=kwargs["model_settings"],
                registry=REGISTRY,
            ))
        except ValueError:
            continue
        raise AssertionError("expected a ValueError")
