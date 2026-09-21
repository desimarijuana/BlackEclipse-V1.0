"""LangGraph runtime: tool loop, max steps, provider failure, persistence.

The chat model is patched with a scripted fake so the graph is exercised end to
end without a network call. The real ToolRegistry, DataBridge, store and event
emitter are used.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.service import _HttpDataBridge
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools


class ScriptedModel:
    """Mimics a LangChain chat model: invoke/ainvoke, bind_tools."""

    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="(exhausted)")
        return self._responses.pop(0)


def _usage(message: AIMessage, prompt: int, completion: int) -> AIMessage:
    """Attach a usage_metadata block the way LangChain providers do."""
    message.usage_metadata = {
        "input_tokens": prompt,
        "output_tokens": completion,
        "total_tokens": prompt + completion,
    }
    return message


class FakeBridge(DataBridge):
    def __init__(self, payload):
        self.payload = payload

    async def fetch(self, capability, params):
        return self.payload


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-graph-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def request(agent=None):
    """Build a run request. Default: send only an agent id, so the assertions
    exercise Python's own agent resolution (the front-door path)."""
    kwargs: dict = {}
    if agent is not None:
        kwargs["agent"] = agent
    else:
        kwargs["agentId"] = "eclipse-agent"
    return RunRequest(
        runId="run_test",
        input=RunInput(query="price of AAPL", ticker="AAPL"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        **kwargs,
    )


def narrow_agent() -> AgentConfig:
    """An agent whose allowlist excludes get_fundamentals (for the forbidden test)."""
    return AgentConfig(
        id="narrow",
        name="Narrow",
        systemPrompt="sys",
        tools=["get_market_snapshot"],
        maxSteps=3,
    )


def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    return reg


def registry_with_retrieval() -> ToolRegistry:
    from harness.retrieval_tools import register_retrieval_tools

    reg = ToolRegistry()
    register_finance_tools(reg)
    register_retrieval_tools(reg)
    return reg


def test_agent_id_resolves_python_side_prompt():
    # Python is authoritative: an agentId alone must yield the full Eclipse
    # prompt, not a caller-supplied copy.
    req = RunRequest(
        runId="r",
        input=RunInput(query="hi"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    agent = graph_module.resolve_agent(req)
    assert agent.id == "eclipse-agent"
    assert agent.systemPrompt.startswith("You are Eclipse Agent")
    assert "Black Orbit Technologies" in agent.systemPrompt


@pytest.mark.asyncio
async def test_conversation_history_reaches_the_model(store, monkeypatch):
    # A follow-up must see prior turns so the chat keeps its thread.
    captured = {}

    class Capturing(ScriptedModel):
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return await super().ainvoke(messages)

    model = Capturing([AIMessage(content="Earlier I said AAPL.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    req = RunRequest(
        runId="run_hist",
        input=RunInput(
            query="what did you say?",
            history=[
                {"role": "user", "content": "price of AAPL?"},
                {"role": "assistant", "content": "AAPL is 338.55."},
            ],
        ),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    result = await graph_module.execute_run(req, registry(), FakeBridge({"status": "UNAVAILABLE"}), store)
    assert result.status == "completed"

    msgs = captured["messages"]
    # system, prior user, prior assistant, current user
    assert msgs[0].type == "system"
    assert msgs[1].type == "human" and msgs[1].content == "price of AAPL?"
    assert msgs[2].type == "ai" and "338.55" in msgs[2].content
    assert msgs[3].type == "human" and msgs[3].content == "what did you say?"


def test_history_is_bounded():
    # A very long chat must not blow the context window.
    history = [{"role": "user", "content": "x" * 5000} for _ in range(50)]
    req = RunRequest(
        runId="r",
        input=RunInput(query="hi", history=history),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    msgs = graph_module._history_messages(req)
    assert len(msgs) <= graph_module.MAX_HISTORY_TURNS
    assert sum(len(m.content) for m in msgs) <= graph_module.MAX_HISTORY_CHARS + 5000


def test_attached_documents_are_injected_into_the_user_message():
    req = RunRequest(
        runId="r",
        input=RunInput(
            query="summarize",
            documents=[{"name": "report.md", "text": "Revenue rose 4%."}],
        ),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    text = graph_module._user_message(req)
    assert "summarize" in text
    assert "report.md" in text
    assert "Revenue rose 4%." in text


def test_no_documents_leaves_the_user_message_clean():
    req = RunRequest(
        runId="r",
        input=RunInput(query="hi"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    assert graph_module._user_message(req) == "hi"


def test_default_agent_used_when_no_id_given():
    req = RunRequest(
        runId="r",
        input=RunInput(query="hi"),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    assert graph_module.resolve_agent(req).id == "eclipse-agent"


@pytest.mark.asyncio
async def test_completes_with_plain_answer(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="AAPL trades at 237.42.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.output == "AAPL trades at 237.42."
    events = [e["type"] for e in store.list_events("run_test")]
    assert events == ["run.created", "run.started", "model.requested", "model.completed", "run.completed"]


@pytest.mark.asyncio
async def test_token_usage_is_captured_and_persisted(store, monkeypatch):
    # A provider that reports usage must have its tokens summed across steps and
    # stored on the run; a provider that omits usage must stay at 0 (honest).
    model = ScriptedModel([_usage(AIMessage(content="AAPL is 237."), 1200, 40)])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.promptTokens == 1200
    assert result.completionTokens == 40
    assert result.totalTokens == 1240
    run = store.get_run("run_test")
    assert run["totalTokens"] == 1240
    completed = [e["data"] for e in store.list_events("run_test") if e["type"] == "model.completed"]
    assert completed[0]["totalTokens"] == 1240


@pytest.mark.asyncio
async def test_token_usage_sums_across_tool_steps(store, monkeypatch):
    tool_call = _usage(
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}]),
        500,
        15,
    )
    model = ScriptedModel([tool_call, _usage(AIMessage(content="AAPL is 237."), 700, 25)])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.promptTokens == 1200
    assert result.completionTokens == 40
    assert store.get_run("run_test")["totalTokens"] == 1240


@pytest.mark.asyncio
async def test_token_usage_absent_reports_zero(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="No usage metadata here.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.totalTokens == 0
    assert store.get_run("run_test")["totalTokens"] == 0


def test_extract_usage_reads_openai_compatible_metadata():
    msg = AIMessage(content="x")
    msg.response_metadata = {"token_usage": {"prompt_tokens": 30, "completion_tokens": 7}}
    assert graph_module._extract_usage(msg) == (30, 7)


@pytest.mark.asyncio
async def test_tool_loop_grounds_answer_and_persists(store, monkeypatch):
    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}],
    )
    model = ScriptedModel([tool_call, AIMessage(content="AAPL is at 237.42 per JDdS.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    bridge = FakeBridge(
        {
            "status": "OK",
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "US",
            "priceSource": "scraper",
            "price": {"price": 237.42, "changePct": 1.2},
        }
    )
    result = await graph_module.execute_run(request(), registry(), bridge, store)
    assert result.status == "completed"
    assert result.toolCalls == 1
    assert result.toolErrors == 0
    events = [e["type"] for e in store.list_events("run_test")]
    assert "tool.requested" in events and "tool.completed" in events
    tools = store.list_tool_executions("run_test")
    assert tools[0]["name"] == "get_market_snapshot"
    assert tools[0]["ok"] is True


@pytest.mark.asyncio
async def test_retrieval_tool_runs_through_the_graph(store, monkeypatch):
    """Phase-2: a retrieval tool is bound, executed and routed through the layer.

    The tool calls the Financial Retrieval Layer, which calls the (fake) bridge.
    Proves the harness executes the provider-agnostic tools end to end.
    """
    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "market_get_quote", "args": {"symbol": "AAPL"}}],
    )
    model = ScriptedModel([tool_call, AIMessage(content="AAPL is at 240.10 (retrieval layer).")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    bridge = FakeBridge(
        {
            "status": "OK",
            "symbol": "AAPL",
            "updatedAt": "2026-09-21T14:00:00.000Z",
            "priceSource": "scraper",
            "price": {"price": 240.10, "changePct": 1.1, "volume": 1000, "marketCap": None, "peRatio": None},
        }
    )
    result = await graph_module.execute_run(request(), registry_with_retrieval(), bridge, store)
    assert result.status == "completed"
    assert result.toolCalls == 1 and result.toolErrors == 0
    tools = store.list_tool_executions("run_test")
    assert tools[0]["name"] == "market_get_quote"
    assert tools[0]["ok"] is True
    assert "Retrieval status: OK" in tools[0]["text"]


@pytest.mark.asyncio
async def test_max_steps_exceeded(store, monkeypatch):
    def looping():
        return AIMessage(
            content="",
            tool_calls=[{"id": f"c{id(object())}", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}],
        )

    model = ScriptedModel([looping(), looping(), looping(), looping()])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    # maxSteps=3 so the fourth looping response is never reached.
    three_step = AgentConfig(
        id="three-step",
        name="Three Step",
        systemPrompt="sys",
        tools=["get_market_snapshot"],
        maxSteps=3,
    )
    result = await graph_module.execute_run(
        request(agent=three_step), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "failed"
    assert result.error.code == "MAX_STEPS_EXCEEDED"
    assert store.get_run("run_test")["status"] == "failed"


@pytest.mark.asyncio
async def test_provider_failure_is_persisted(store, monkeypatch):
    class Broken:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("provider down")

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: Broken())
    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "failed"
    assert result.error.code == "PROVIDER_ERROR"


@pytest.mark.asyncio
async def test_forbidden_tool_is_recorded_as_error_but_run_completes(store, monkeypatch):
    # A narrow agent allowlists only get_market_snapshot; calling
    # get_fundamentals must be refused AND counted as a tool error, yet the run
    # still completes because the model recovers with a final answer.
    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "get_fundamentals", "args": {"symbol": "ZZZZ"}}],
    )
    model = ScriptedModel([tool_call, AIMessage(content="That tool is not available.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=narrow_agent()), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.toolErrors == 1
    failures = [e["data"] for e in store.list_events("run_test") if e["type"] == "tool.failed"]
    assert failures[0]["name"] == "get_fundamentals"
    assert failures[0]["code"] == "TOOL_FORBIDDEN"


@pytest.mark.asyncio
async def test_unavailable_data_yields_honest_tool_ok(store, monkeypatch):
    # An UNAVAILABLE bridge response is an HONEST tool result (ok), not an error:
    # the tool deliberately reports "no data" instead of inventing a price.
    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "ZZZZ"}}],
    )
    model = ScriptedModel([tool_call, AIMessage(content="No stored snapshot for ZZZZ.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.toolErrors == 0
    tools = store.list_tool_executions("run_test")
    assert tools[0]["ok"] is True
    assert "UNAVAILABLE" in tools[0]["text"]
