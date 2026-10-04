"""Phase 11 — bounded replanning on the ONE execution graph.

The chat model is scripted (no network). The real ToolRegistry, store and event
emitter run end to end, so the tests prove the `replan` node, its trigger, its
bound and its observability, not just the pure helpers.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.replan import (
    ReplanBudget,
    build_replan_instruction,
    replan_enabled,
    should_replan,
)
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.service import _HttpDataBridge
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class ScriptedModel:
    """Mimics a LangChain chat model: ainvoke/astream/bind_tools."""

    def __init__(self, responses, capture: list | None = None) -> None:
        self._responses = list(responses)
        self.bound_tools = None
        self._capture = capture

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        if self._capture is not None:
            self._capture.append(list(messages))
        if not self._responses:
            return AIMessage(content="(exhausted)")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    def __init__(self, payload=None):
        self.payload = payload or {"status": "UNAVAILABLE"}

    async def fetch(self, capability, params):
        return self.payload


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-replan-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def request(run_id: str = "run_replan", agent: AgentConfig | None = None) -> RunRequest:
    kwargs: dict = {}
    if agent is not None:
        kwargs["agent"] = agent
    else:
        kwargs["agentId"] = "eclipse-agent"
    return RunRequest(
        runId=run_id,
        input=RunInput(query="what is the price of AAPL?"),
        modelSettings=ModelSettings(
            provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"
        ),
        callbackBaseUrl="http://localhost:3000",
        **kwargs,
    )


def _failing_registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def boom(args, ctx):
        raise RuntimeError("kaboom")

    reg.register(
        ToolDefinition(
            name="boom",
            description="Always raises.",
            input_schema={"type": "object", "properties": {}},
            handler=boom,
        )
    )
    return reg


def _counting_registry(counter: dict[str, int]) -> ToolRegistry:
    reg = ToolRegistry()

    async def handler(args, ctx):
        counter["n"] += 1
        return f"ok result #{counter['n']}"

    reg.register(
        ToolDefinition(
            name="counting",
            description="Succeeds and counts.",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=handler,
        )
    )
    return reg


def _agent(tool: str, max_steps: int = 6) -> AgentConfig:
    return AgentConfig(id="rp", name="RP", systemPrompt="sys", tools=[tool], maxSteps=max_steps)


def _call(name: str, args: dict, cid: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": cid, "name": name, "args": args}])


# ── pure module ──────────────────────────────────────────────────────────────


def test_should_replan_prefers_stall_and_respects_budget():
    budget = ReplanBudget(max_replans=1)
    assert should_replan(replans=0, budget=None, step_failures=3, stalled=False) is None
    assert should_replan(replans=0, budget=budget, step_failures=0, stalled=False) is None
    assert should_replan(replans=0, budget=budget, step_failures=1, stalled=False) == "tool_failures"
    assert should_replan(replans=0, budget=budget, step_failures=1, stalled=True) == "stall"
    # Budget spent: no replan, whatever the signal.
    assert should_replan(replans=1, budget=budget, step_failures=5, stalled=True) is None


def test_build_replan_instruction_names_failures():
    text = build_replan_instruction(
        "tool_failures", failures=[{"name": "boom", "code": "TOOL_ERROR"}], stalled_calls=[]
    )
    assert "Revised approach" in text
    assert "boom" in text and "TOOL_ERROR" in text
    stall = build_replan_instruction("stall", failures=[], stalled_calls=["counting:{x: 1}"])
    assert "repeated" in stall.lower()


def test_replan_enabled_reads_the_flag(monkeypatch):
    monkeypatch.delenv("HARNESS_REPLAN_ENABLED", raising=False)
    assert replan_enabled() is False
    monkeypatch.setenv("HARNESS_REPLAN_ENABLED", "1")
    assert replan_enabled() is True


# ── integration on the real graph ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failed_tool_triggers_one_replan_then_answer(store, monkeypatch):
    monkeypatch.setenv("HARNESS_REPLAN_ENABLED", "1")
    captured: list = []
    model = ScriptedModel([_call("boom", {}), AIMessage(content="Recovered answer.")], captured)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_agent("boom")), _failing_registry(), FakeBridge(), store
    )
    assert result.status == "completed", result.error
    assert result.output == "Recovered answer."
    events = store.list_events("run_replan")
    replanned = [e for e in events if e["type"] == "run.replanned"]
    assert len(replanned) == 1
    assert replanned[0]["data"]["reason"] == "tool_failures"
    assert replanned[0]["data"]["replan"] == 1
    # The agent's second turn saw the inert revised-approach directive.
    assert any(
        "Revised approach" in m.content
        for m in captured[1]
        if getattr(m, "type", "") == "human"
    )


@pytest.mark.asyncio
async def test_replan_is_off_by_default(store, monkeypatch):
    monkeypatch.delenv("HARNESS_REPLAN_ENABLED", raising=False)
    model = ScriptedModel([_call("boom", {}), AIMessage(content="Recovered answer.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_agent("boom")), _failing_registry(), FakeBridge(), store
    )
    assert result.status == "completed", result.error
    events = [e["type"] for e in store.list_events("run_replan")]
    assert "run.replanned" not in events


@pytest.mark.asyncio
async def test_replans_are_bounded(store, monkeypatch):
    monkeypatch.setenv("HARNESS_REPLAN_ENABLED", "1")
    # Three failing turns, then an answer. Only two replans are allowed.
    model = ScriptedModel(
        [
            _call("boom", {}, "c1"),
            _call("boom", {}, "c2"),
            _call("boom", {}, "c3"),
            AIMessage(content="Answer after the bound."),
        ]
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_agent("boom", max_steps=6)), _failing_registry(), FakeBridge(), store
    )
    assert result.status == "completed", result.error
    replanned = [e for e in store.list_events("run_replan") if e["type"] == "run.replanned"]
    assert len(replanned) == 2
    assert [e["data"]["replan"] for e in replanned] == [1, 2]


@pytest.mark.asyncio
async def test_repeated_successful_call_triggers_stall_replan(store, monkeypatch):
    monkeypatch.setenv("HARNESS_REPLAN_ENABLED", "1")
    counter = {"n": 0}
    # The same successful call twice is a stall, not a failure.
    model = ScriptedModel(
        [
            _call("counting", {"x": 1}, "c1"),
            _call("counting", {"x": 1}, "c2"),
            AIMessage(content="Took a different step."),
        ]
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_agent("counting")), _counting_registry(counter), FakeBridge(), store
    )
    assert result.status == "completed", result.error
    replanned = [e for e in store.list_events("run_replan") if e["type"] == "run.replanned"]
    assert len(replanned) == 1
    assert replanned[0]["data"]["reason"] == "stall"
    # The first call executed; the repeated one was refused as an intra-turn
    # duplicate is NOT what triggered this — it is the next TURN's repeat.
    assert counter["n"] >= 1
