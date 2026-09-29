"""Milestone 2: measured, model-aware history budgeting."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.context_budget import compute_history_budget, tool_schema_text
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools


def _budget(window, **overrides):
    kwargs = dict(
        provider="test", model="test",
        system_prompt="sys", tool_schemas="",
        user_turn="q",
        absolute_max_turns=graph_module.MAX_HISTORY_TURNS,
        absolute_max_chars=graph_module.MAX_HISTORY_CHARS,
    )
    kwargs.update(overrides)
    return compute_history_budget(window_override=window, **kwargs)


def _request(history):
    return RunRequest(
        runId="r",
        input=RunInput(query="continue", history=history),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="test", model="test"),
        callbackBaseUrl="http://localhost:3000",
    )


def _turns(n, chars):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * chars} for i in range(n)]


def test_large_window_keeps_more_history_than_today():
    req = _request(_turns(40, 100))
    baseline, _ = graph_module._bounded_history(req)          # no budget
    assert len(baseline) == graph_module.MAX_HISTORY_TURNS
    bounded, dropped = graph_module._bounded_history(req, _budget(32_000))
    assert len(bounded) == 40
    assert dropped == []


def test_small_window_keeps_less_history():
    req = _request(_turns(40, 100))
    # A large measured overhead against a small window leaves no room for history.
    budget = _budget(6_000, system_prompt="s" * 20_000)
    bounded, dropped = graph_module._bounded_history(req, budget)
    assert len(bounded) < graph_module.MAX_HISTORY_TURNS
    assert len(dropped) > 20


def test_unknown_window_reproduces_todays_bound_exactly():
    req = _request(_turns(30, 100))
    baseline = graph_module._bounded_history(req)
    unknown = _budget(None)
    assert unknown.effective is False
    assert unknown.window_known is False
    assert unknown.max_history_turns == graph_module.MAX_HISTORY_TURNS
    assert unknown.max_history_chars == graph_module.MAX_HISTORY_CHARS
    assert graph_module._bounded_history(req, unknown) == baseline


def test_overhead_measurement_includes_real_per_run_blocks():
    base = _budget(32_000)
    with_blocks = _budget(
        32_000,
        profile_block="p" * 400,
        skill_manifest="s" * 400,
        memory_block="m" * 400,
        dropped_block="d" * 400,
    )
    assert with_blocks.measured_overhead_tokens > base.measured_overhead_tokens
    # The allowance correspondingly shrinks.
    assert with_blocks.history_allowance_chars < base.history_allowance_chars


def test_absolute_char_ceiling_holds_on_a_huge_window():
    req = _request(_turns(100, 1000))   # 100_000 chars
    budget = _budget(1_000_000)
    assert budget.max_history_chars == graph_module.MAX_HISTORY_CHARS
    kept, dropped = graph_module._bounded_history(req, budget)
    assert sum(len(t.content) for t in kept) <= graph_module.MAX_HISTORY_CHARS
    assert dropped


def test_under_bound_history_is_byte_identical():
    req = _request([
        {"role": "user", "content": "price of AAPL?"},
        {"role": "assistant", "content": "AAPL is 338.55."},
    ])
    baseline = graph_module._history_messages(req)
    bounded = graph_module._history_messages(req, _budget(32_000))
    assert [m.content for m in baseline] == [m.content for m in bounded]


def test_tool_schema_text_is_deterministic():
    schemas = [
        {"name": "b", "description": "z", "parameters": {}},
        {"name": "a", "description": "y", "parameters": {}},
    ]
    assert tool_schema_text(schemas) == tool_schema_text(list(reversed(schemas)))


@pytest.mark.asyncio
async def test_run_keeps_more_history_on_a_large_declared_window(monkeypatch):
    captured = {}

    class Capturing:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="ok")

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: Capturing())

    directory = tempfile.mkdtemp(prefix="be-budget-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    reg = ToolRegistry()
    register_finance_tools(reg)

    class FakeBridge(DataBridge):
        async def fetch(self, capability, params):
            return {}

    # 40 turns fit easily in a 32k window; the hardcoded bound would keep 20.
    req = _request(_turns(40, 100))
    req.input.context = {"_context_budget_override": {"window": 32_000}}
    try:
        result = await graph_module.execute_run(req, reg, FakeBridge(), store)
    finally:
        store.close()
    assert result.status == "completed"
    history = [m for m in captured["messages"] if m.type in ("human", "ai") and m.content.startswith("x")]
    assert len(history) == 40
    # The additive result blob reports the budget honestly. The 40 x 100 chars
    # (4000 chars) fit the 32k window, so nothing was dropped and the blob is
    # correctly ABSENT (old clients unaffected).
    assert result.context is None
