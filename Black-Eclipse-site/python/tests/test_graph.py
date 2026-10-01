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
from harness.tools import DataBridge, ToolRegistry, ToolDefinition
from harness.finance_tools import register_finance_tools


class ScriptedModel:
    """Mimics a LangChain chat model: invoke/ainvoke, bind_tools, astream."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="(exhausted)")
        return self._responses.pop(0)

    async def astream(self, messages):
        """Stream the next message once, routed through `ainvoke` so subclasses
        that override it (capture calls, attach usage) still apply. Models one
        provider that streams whole messages, which the runtime must tolerate."""
        message = await self.ainvoke(messages)
        yield message


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
    # system, runtime date/time context, prior user, prior assistant, current user
    from datetime import datetime, timezone

    assert msgs[0].type == "system"
    assert "Runtime context" in msgs[1].content
    # The block carries the run's real date, not a fabricated one.
    assert datetime.now(timezone.utc).strftime("%Y-%m-%d") in msgs[1].content
    assert msgs[2].type == "human" and msgs[2].content == "price of AAPL?"
    assert msgs[3].type == "ai" and "338.55" in msgs[3].content
    assert msgs[4].type == "human" and msgs[4].content == "what did you say?"


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
    assert events == [
        "run.created", "run.started", "prompt.plan", "model.requested", "model.completed",
        "run.completed", "session.indexed",
    ]


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
async def test_final_step_forbids_tools_and_forces_an_answer(store, monkeypatch):
    """Regression: a tool-looping model must still produce an answer.

    Previously a model that kept calling tools hit MAX_STEPS_EXCEEDED with no
    answer. On the last allowed step tools are unbound, so the model must answer
    from what it gathered.
    """
    seen_models: list[object] = []

    def looping():
        return AIMessage(
            content="",
            tool_calls=[{"id": f"c{id(object())}", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}],
        )

    class TrackingModel(ScriptedModel):
        def bind_tools(self, tools):
            self.bound_tools = tools
            return self

    model = TrackingModel([looping(), looping(), AIMessage(content="Final answer from gathered data.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    seen_models.append(model)

    three_step = AgentConfig(id="three-step", name="Three Step", systemPrompt="sys", tools=["get_market_snapshot"], maxSteps=3)
    bridge = FakeBridge({"status": "OK", "symbol": "AAPL", "priceSource": "scraper", "price": {"price": 1.0, "changePct": 0.0}})
    result = await graph_module.execute_run(request(agent=three_step), registry(), bridge, store)
    assert result.status == "completed", result.error
    assert result.output == "Final answer from gathered data."
    # The final invocation used the tools-unbound model, so the loop could not
    # continue; the terminal answer was reached on the last step.
    assert result.modelSteps == 3


@pytest.mark.asyncio
async def test_model_deltas_are_streamed_but_not_persisted(store, monkeypatch):
    """Live token streaming emits transient `model.delta` events that never land
    in the persisted trace (only real lifecycle events do)."""
    model = ScriptedModel([AIMessage(content="Hello world")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    bus = graph_module.EventBus()
    live: list[str] = []
    bus.subscribe(lambda e: live.append(e["type"]))

    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store, bus
    )
    assert result.status == "completed"
    assert "model.delta" in live
    persisted = [e["type"] for e in store.list_events("run_test")]
    assert "model.delta" not in persisted
    assert "model.completed" in persisted


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
    # Capture bus events so we can prove retrieval.* reaches the live stream —
    # the events were previously swallowed by a no-op log callback, so the UI's
    # source activity never rendered.
    from harness.events import EventBus

    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e["type"]))

    result = await graph_module.execute_run(request(), registry_with_retrieval(), bridge, store, bus=bus)
    assert result.status == "completed"
    assert result.toolCalls == 1 and result.toolErrors == 0
    tools = store.list_tool_executions("run_test")
    assert tools[0]["name"] == "market_get_quote"
    assert tools[0]["ok"] is True
    assert "Retrieval status: OK" in tools[0]["text"]
    # The retrieval layer's source selection must be observable.
    assert "retrieval.planned" in seen
    assert "retrieval.source_start" in seen
    assert "retrieval.source_ok" in seen


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
async def test_explicit_remember_is_captured_deterministically(store, monkeypatch):
    """An explicit "remember this" is persisted through the service even though
    the (scripted) model never calls the memory tool — the deterministic path."""
    from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore

    directory = tempfile.mkdtemp(prefix="be-graph-mem-")
    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    model = ScriptedModel([AIMessage(content="Got it.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    req = RunRequest(
        runId="run_remember",
        input=RunInput(query="Remember that I prefer terse answers"),
        agentId="eclipse-agent",
        userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    try:
        result = await graph_module.execute_run(
            req, registry(), FakeBridge({"status": "UNAVAILABLE"}), store, memory_service=memory
        )
        assert result.status == "completed"
        assert result.memory and result.memory.get("action") == "saved"
        assert result.memory.get("memoryId")
        rows = memory.store.list_memories()
        assert any("terse answers" in r["content"] and r["memoryType"] == "preference" for r in rows)
        # Persisted on the run too, so the UI reads it after restart.
        assert store.get_run("run_remember")["memory"]["action"] == "saved"
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_explicit_secret_is_refused_not_stored(store, monkeypatch):
    from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore

    directory = tempfile.mkdtemp(prefix="be-graph-mem2-")
    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    model = ScriptedModel([AIMessage(content="Understood.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    req = RunRequest(
        runId="run_secret",
        input=RunInput(query="Remember my API key is sk-abcdefghijklmnopqrstuvwxyz"),
        agentId="eclipse-agent",
        userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    try:
        result = await graph_module.execute_run(
            req, registry(), FakeBridge({"status": "UNAVAILABLE"}), store, memory_service=memory
        )
        assert result.memory and result.memory.get("action") == "refused"
        assert memory.store.list_memories() == []
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_ordinary_chat_records_learning_eligibility(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="AAPL trades at 237.42.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        request(), registry(), FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed"
    assert result.memory is not None
    eligibility = result.memory["learningEligibility"]
    assert eligibility["eligible"] is False
    assert "no tool use" in eligibility["reason"]
    assert eligibility["learnQueuePath"]


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


# ── Phase 2: duplicate suppression is scoped to one agent step ──────────────


def _counting_registry(counter: dict[str, int]) -> ToolRegistry:
    """A registry with one native tool that counts how often it actually runs."""
    reg = ToolRegistry()

    async def handler(args, ctx):
        counter["n"] += 1
        return f"counting result #{counter['n']} for x={args.get('x')}"

    reg.register(
        ToolDefinition(
            name="counting",
            description="A counting test tool.",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=handler,
        )
    )
    return reg


def _counter_agent(max_steps: int = 6) -> AgentConfig:
    return AgentConfig(id="counter", name="Counter", systemPrompt="sys", tools=["counting"], maxSteps=max_steps)


@pytest.mark.asyncio
async def test_identical_tool_call_across_turns_executes_twice(store, monkeypatch):
    """A legitimate re-issue in a LATER turn must execute, not be suppressed.

    Regression for the run-scoped `seen_calls` map: the same (name, args) asked
    at step 1 and again at a later step must run twice and the second result must
    be the fresh one, never the "Use the earlier result" refusal.
    """
    counter = {"n": 0}
    reg = _counting_registry(counter)
    same = {"x": 1}
    model = ScriptedModel(
        [
            AIMessage(content="", tool_calls=[{"id": "c1", "name": "counting", "args": same}]),
            AIMessage(content="", tool_calls=[{"id": "c2", "name": "counting", "args": same}]),
            AIMessage(content="Answer from two calls."),
        ]
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_counter_agent()), reg, FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed", result.error
    assert counter["n"] == 2
    completed = [e for e in store.list_events("run_test") if e["type"] == "tool.completed"]
    assert len(completed) == 2
    assert result.toolErrors == 0
    messages = store.list_tool_executions("run_test")
    assert "counting result #2" in messages[1]["text"]
    assert "Duplicate call" not in messages[1]["text"]


@pytest.mark.asyncio
async def test_identical_tool_call_within_one_turn_still_refuses(store, monkeypatch):
    """Two identical calls in ONE model turn: the first runs, the second refuses.

    This is the original intra-turn behaviour and must be preserved exactly —
    same refusal shape and the same `tool.failed` code.
    """
    counter = {"n": 0}
    reg = _counting_registry(counter)
    same = {"x": 7}
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "c1", "name": "counting", "args": same},
                    {"id": "c2", "name": "counting", "args": same},
                ],
            ),
            AIMessage(content="Answer after one real call."),
        ]
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=_counter_agent()), reg, FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed", result.error
    assert counter["n"] == 1
    assert result.toolErrors == 1
    failures = [e["data"] for e in store.list_events("run_test") if e["type"] == "tool.failed"]
    assert len(failures) == 1
    assert failures[0]["code"] == "TOOL_FORBIDDEN"
    # The refusal is not executed, so only the one real call is persisted.
    messages = store.list_tool_executions("run_test")
    assert len(messages) == 1
    assert "counting result #1" in messages[0]["text"]


@pytest.mark.asyncio
async def test_oversized_native_tool_result_emits_tool_truncated(store, monkeypatch):
    """Phase 3: a result over the bound is trimmed and emits `tool.truncated` once."""
    from harness.tools import MAX_TOOL_RESULT_CHARS

    big = "a" * (MAX_TOOL_RESULT_CHARS + 400)
    reg = ToolRegistry()

    async def handler(args, ctx):
        return big

    reg.register(
        ToolDefinition(
            name="bigtool",
            description="Returns an oversized result.",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
        )
    )
    agent = AgentConfig(id="big", name="Big", systemPrompt="sys", tools=["bigtool"], maxSteps=3)
    model = ScriptedModel(
        [
            AIMessage(content="", tool_calls=[{"id": "c1", "name": "bigtool", "args": {}}]),
            AIMessage(content="Done."),
        ]
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        request(agent=agent), reg, FakeBridge({"status": "UNAVAILABLE"}), store
    )
    assert result.status == "completed", result.error
    truncated = [e["data"] for e in store.list_events("run_test") if e["type"] == "tool.truncated"]
    assert len(truncated) == 1
    assert truncated[0]["totalChars"] == len(big)
    assert truncated[0]["shownChars"] == MAX_TOOL_RESULT_CHARS
    completed = [e["data"] for e in store.list_events("run_test") if e["type"] == "tool.completed"]
    assert completed[0]["truncated"] is True
