"""Bounded answer recovery: a bare refusal does not end the run while a route remains."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.answer_guard import (
    MAX_ANSWER_RECOVERIES,
    build_recovery_instruction,
    is_bare_refusal,
    recovery_reason,
    render_fallback_block,
    sources_restricted,
)
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.service import _HttpDataBridge
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class ScriptedModel:
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
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-answer-guard-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _request(query: str, tool_names: list[str], *, agent_id: str = "ag") -> RunRequest:
    agent = AgentConfig(
        id=agent_id, name="AG", systemPrompt="sys",
        tools=list(tool_names), maxSteps=6,
    )
    return RunRequest(
        runId="run_answer_guard",
        input=RunInput(query=query),
        modelSettings=ModelSettings(
            provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"
        ),
        callbackBaseUrl="http://localhost:3000",
        agent=agent,
    )


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def missing(_args, _ctx):
        return "UNAVAILABLE — no stored row for TEST.", {"status": "UNAVAILABLE"}

    async def found(_args, _ctx):
        return "Source page found and extracted.", {"status": "OK", "url": "https://example.test/TEST"}

    reg.register(ToolDefinition(
        name="fetch_thing", description="Read the stored TEST row.",
        input_schema={"type": "object", "properties": {}}, handler=missing,
    ))
    reg.register(ToolDefinition(
        name="web_search", description="Search the web.",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        handler=found,
    ))
    return reg


def _call(name: str, args: dict, cid: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": cid, "name": name, "args": args}])


# ── pure classifier ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", [
    "UNAVAILABLE — no stored row for TEST.",
    "I could not retrieve the price; no data was returned.",
    "The source did not return a value.",
    "I don't have access to that series.",
])
def test_short_route_specific_refusals_are_recognised(text):
    assert is_bare_refusal(text) is True


@pytest.mark.parametrize("text", [
    "I can't provide investment advice for this holding.",
    "Here is the valuation: P/E 18.4 with revenue growth of 12%.",
    "AAPL traded at 211.20 as of 2026-11-14 (source: exchange, live). "
    "Fundamentals were unavailable, so the margin comparison is withheld.",
    "",
])
def test_substantive_or_policy_answers_are_not_refusals(text):
    assert is_bare_refusal(text) is False


def test_source_restriction_blocks_recovery():
    assert sources_restricted("only use the attached filing") is True
    assert sources_restricted("no web search; use the stored data") is True
    assert sources_restricted("what is AAPL trading at?") is False

    reason = recovery_reason(
        query="only use the attached filing",
        answer="UNAVAILABLE — not in the attachment.",
        tools_used=["fetch_thing"],
        available={"web_search", "fetch_thing"},
        recoveries=0, step=1, max_steps=6,
    )
    assert reason is None


def test_recovery_names_only_untried_permitted_routes():
    text = build_recovery_instruction(
        query="what is TEST trading at?",
        answer="UNAVAILABLE — no data.",
        tools_used=["fetch_thing", "web_search"],
        available={"fetch_thing", "web_search", "web_extract", "analysis_run"},
        unavailable_tools=["fetch_thing"],
    )
    assert text is not None
    assert "`web_extract`" in text
    assert "`analysis_run`" in text
    assert "`fetch_thing`" not in text
    assert "`web_search`" not in text


def test_fallback_block_names_only_bound_routes():
    block = render_fallback_block(
        {"web_search", "scraper_run", "analysis_run", "not_a_route"},
        "what is TEST trading at?",
    )
    assert "`web_search`" in block
    assert "`scraper_run`" in block
    assert "`analysis_run`" in block
    assert "`browser_launch`" not in block
    assert "`not_a_route`" not in block

    restricted = render_fallback_block(
        {"web_search", "scraper_run"}, "only use the attached document",
    )
    assert "Source restriction" in restricted
    assert "`web_search`" not in restricted


def test_recovery_is_bounded_and_stops_when_no_route_remains():
    assert MAX_ANSWER_RECOVERIES >= 1
    # A refusal with NO tool attempted is a capability/policy shape.
    assert recovery_reason(
        query="q", answer="UNAVAILABLE — no data.", tools_used=[],
        available={"web_search"}, recoveries=0, step=1, max_steps=6,
    ) is None
    assert recovery_reason(
        query="q", answer="UNAVAILABLE", tools_used=[],
        available={"web_search"}, recoveries=MAX_ANSWER_RECOVERIES,
        step=1, max_steps=6,
    ) is None
    assert recovery_reason(
        query="q", answer="UNAVAILABLE", tools_used=["web_search"],
        available={"web_search"}, recoveries=0, step=1, max_steps=6,
    ) is None


def test_outcome_envelope_records_the_recovery():
    from harness.run_outcome import build_outcome_envelope

    envelope = build_outcome_envelope(
        run_id="run_r",
        run={"agentId": "eclipse-agent"},
        events=[
            {"type": "answer.recovery_started",
             "data": {"attempt": 1, "nextRoutes": ["web_search", "scraper_run"]}},
            {"type": "answer.recovered", "data": {"attempts": 1}},
        ],
    )
    assert envelope["answerRecovery"] == {
        "attempts": 1, "recovered": True, "exhausted": False,
        "nextRoutes": ["web_search", "scraper_run"],
    }
    plain = build_outcome_envelope(
        run_id="run_plain", run={"agentId": "eclipse-agent"}, events=[],
    )
    assert plain["answerRecovery"] is None


# ── graph integration ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_bare_refusal_is_sent_back_to_an_untried_route(store, monkeypatch):
    captured: list = []
    model = ScriptedModel(
        [
            _call("fetch_thing", {}),
            AIMessage(content="UNAVAILABLE — no stored row for TEST."),
            _call("web_search", {"q": "TEST price"}),
            AIMessage(content="TEST last traded at USD 42.10 (source: retrieved page, 2026-11-14)."),
        ],
        captured,
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        _request("what is TEST trading at?", ["fetch_thing", "web_search"]),
        _registry(), FakeBridge(), store,
    )

    assert result.status == "completed", result.error
    assert "USD 42.10" in (result.output or "")
    events = store.list_events("run_answer_guard")
    types = [event["type"] for event in events]
    assert "answer.recovery_started" in types
    assert "answer.recovered" in types
    started = next(e for e in events if e["type"] == "answer.recovery_started")
    assert "web_search" in started["data"]["nextRoutes"]
    assert any(
        "Do not end on a blocked route" in message.content
        for turn in captured
        for message in turn
        if getattr(message, "type", "") == "human"
    )


@pytest.mark.asyncio
async def test_a_source_restriction_is_respected(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="UNAVAILABLE — not in the attachment.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        _request("only use the attached filing — what is TEST revenue?", ["fetch_thing", "web_search"]),
        _registry(), FakeBridge(), store,
    )

    assert result.status == "completed", result.error
    assert "UNAVAILABLE" in (result.output or "")
    types = [event["type"] for event in store.list_events("run_answer_guard")]
    assert "answer.recovery_started" not in types
