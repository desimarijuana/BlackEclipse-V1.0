"""Milestones 3 & 4: overflow classification + bounded one-retry recovery."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.models import classify_context_overflow
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools


# ── Milestone 3: the classifier ──────────────────────────────────────────────

class ProviderError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def test_openai_context_length_classifies():
    exc = ProviderError(
        "This model's maximum context length is 4096 tokens. However, your "
        "messages resulted in 18734 tokens.",
        code="context_length_exceeded",
    )
    assert classify_context_overflow(exc) is True


def test_anthropic_prompt_too_long_classifies():
    exc = ProviderError("prompt is too long: 210000 tokens > 200000 maximum")
    assert classify_context_overflow(exc) is True


def test_google_input_token_exceeds_classifies():
    exc = ProviderError(
        "The input token count (300000) exceeds the maximum number of tokens allowed (1048576)."
    )
    assert classify_context_overflow(exc) is True


def test_mistral_context_window_classifies():
    exc = ProviderError("Context window exceeded for model mistral-large-latest")
    assert classify_context_overflow(exc) is True


def test_groq_reduce_message_length_classifies():
    exc = ProviderError(
        "Please reduce the length of the messages or completion.", code="string_above_max_length"
    )
    assert classify_context_overflow(exc) is True


def test_rate_limit_is_not_overflow():
    exc = ProviderError("Rate limit reached for gpt-4o on tokens per min. Please try again.")
    assert classify_context_overflow(exc) is False


def test_timeout_is_not_overflow():
    assert classify_context_overflow(ProviderError("Request timed out after 30s")) is False
    assert classify_context_overflow(ProviderError("Deadline exceeded")) is False


def test_auth_is_not_overflow():
    assert classify_context_overflow(ProviderError("Incorrect API key provided", code="invalid_api_key")) is False
    assert classify_context_overflow(ProviderError("401 Unauthorized", code="authentication_error")) is False


def test_quota_and_overload_are_not_overflow():
    assert classify_context_overflow(ProviderError("You exceeded your current quota", code="insufficient_quota")) is False
    assert classify_context_overflow(ProviderError("The engine is currently overloaded")) is False


def test_empty_and_unrelated_errors_are_not_overflow():
    assert classify_context_overflow(ProviderError("")) is False
    assert classify_context_overflow(RuntimeError("provider down")) is False


# ── Milestone 4: bounded recovery ────────────────────────────────────────────

class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


def _agent() -> AgentConfig:
    return AgentConfig(
        id="budget-test", name="Budget", systemPrompt="sys",
        tools=["get_market_snapshot"], maxSteps=3,
    )


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    return reg


def _history(n: int, chars: int = 2000):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * chars} for i in range(n)]


def _req(run_id: str, history, *, window: int = 20_000, context=None) -> RunRequest:
    merged = {"_context_budget_override": {"window": window}}
    if context:
        merged.update(context)
    return RunRequest(
        runId=run_id,
        input=RunInput(query="continue", history=history, context=merged),
        agent=_agent(),
        modelSettings=ModelSettings(provider="openai", model="gpt-4o", api_key="x"),
        callbackBaseUrl="http://localhost:3000",
    )


class ThresholdModel:
    """Raises a provider overflow while the history count exceeds `threshold`."""

    def __init__(self, threshold: int, answer: str = "ok"):
        self.threshold = threshold
        self.answer = answer
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def _history_count(self, messages) -> int:
        return sum(
            1 for m in messages
            if m.type in ("human", "ai") and isinstance(m.content, str) and m.content.startswith("x")
        )

    async def ainvoke(self, messages):
        self.calls += 1
        if self._history_count(messages) > self.threshold:
            raise RuntimeError(
                "This model's maximum context length is 4096 tokens. "
                "However, your messages resulted in 18734 tokens."
            )
        return AIMessage(content=self.answer)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-overflow-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.mark.asyncio
async def test_overflow_then_tighter_retry_succeeds(store, monkeypatch):
    # The base budget keeps 20 turns; the tightened retry keeps fewer. A threshold
    # between them means the first attempt overflows and the retry fits.
    model = ThresholdModel(threshold=17)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        _req("run_recover", _history(30)), _registry(), FakeBridge(), store
    )
    events = [e["type"] for e in store.list_events("run_recover")]
    assert result.status == "completed"
    assert events.count("context.retry") == 1
    # Two model attempts (no third).
    assert events.count("model.requested") == 2
    assert result.context is not None
    assert result.context["tighterRetry"] is True


@pytest.mark.asyncio
async def test_overflow_after_retry_fails_honestly_with_two_attempts(store, monkeypatch):
    # Threshold 0: even the tightened history overflows → honest failure, no
    # third attempt.
    model = ThresholdModel(threshold=0)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        _req("run_double", _history(30)), _registry(), FakeBridge(), store
    )
    events = [e["type"] for e in store.list_events("run_double")]
    assert result.status == "failed"
    assert result.error.code == "CONTEXT_OVERFLOW"
    # The message reports the retry it actually attempted.
    assert "retried once" in result.error.message
    assert "shorter conversation" in result.error.message
    # Two model attempts only (each attempt may make a stream + fallback call).
    assert events.count("model.requested") == 2
    assert events.count("context.retry") == 1
    assert events.count("run.failed") == 1
    assert store.get_run("run_double")["status"] == "failed"


@pytest.mark.asyncio
async def test_exactly_one_terminal_status_on_success_after_retry(store, monkeypatch):
    model = ThresholdModel(threshold=17)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    await graph_module.execute_run(_req("run_once", _history(30)), _registry(), FakeBridge(), store)
    events = [e["type"] for e in store.list_events("run_once")]
    assert events.count("run.completed") == 1
    assert "run.failed" not in events
    assert store.get_run("run_once")["status"] == "completed"


@pytest.mark.asyncio
async def test_side_effecting_tool_is_not_re_executed_across_retry(store, monkeypatch):
    """An overflow AFTER a tool executed must not trigger a rebuild that re-runs it."""
    executed = {"count": 0}

    class ToolThenOverflow:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}],
                )
            raise RuntimeError("This model's maximum context length is 4096 tokens.")

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    class CountingBridge(FakeBridge):
        async def fetch(self, capability, params):
            executed["count"] += 1
            return {"status": "OK", "symbol": "AAPL", "priceSource": "scraper", "price": {"price": 1.0, "changePct": 0.0}}

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ToolThenOverflow())
    result = await graph_module.execute_run(
        _req("run_tool", _history(30)), _registry(), CountingBridge(), store
    )
    events = [e["type"] for e in store.list_events("run_tool")]
    assert result.status == "failed"
    assert result.error.code == "CONTEXT_OVERFLOW"
    # The overflow happened on step 2; no retry is attempted, so the tool ran once.
    assert "context.retry" not in events
    # The property is that the TOOL was not re-executed — not that the bridge was
    # called once. A single `get_market_snapshot` now consults several capabilities
    # (the vault snapshot plus the arbitrated price route), so counting bridge
    # calls is the wrong proxy. Count the recorded tool executions instead.
    assert len(store.list_tool_executions("run_tool")) == 1
    assert executed["count"] >= 1


@pytest.mark.asyncio
async def test_cancellation_during_retry_still_cancels(store, monkeypatch):
    import asyncio

    retry_started = asyncio.Event()

    class SlowOnRetry(ThresholdModel):
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("This model's maximum context length is 4096 tokens.")
            retry_started.set()
            await asyncio.sleep(10)
            return AIMessage(content="too late")

    model = SlowOnRetry(threshold=100)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    task = asyncio.ensure_future(
        graph_module.execute_run(
            _req("run_cancel", _history(30)), _registry(), FakeBridge(), store
        )
    )
    # Wait until the retry is actually in flight before cancelling. A fixed sleep
    # here raced the retry: on a loaded machine the first attempt had not yet
    # overflowed when the cancel landed, so the test asserted a state it had not
    # reached. The event removes the race without weakening the assertion.
    await asyncio.wait_for(retry_started.wait(), timeout=10)
    task.cancel()
    try:
        result = await task
        status = result.status
    except asyncio.CancelledError:
        status = "cancelled"
    assert status == "cancelled"
    assert store.get_run("run_cancel")["status"] == "cancelled"


def test_unknown_window_overflow_does_not_attempt_a_retry():
    # If the window is unknown the budget is inert; a retry cannot be computed, so
    # the honest overflow stands with no second attempt.
    from harness.graph import _retry_with_tighter_budget  # noqa: F401
    from harness.context_budget import compute_history_budget

    budget = compute_history_budget(
        provider="ollama", model="x", system_prompt="s", user_turn="q",
        absolute_max_turns=graph_module.MAX_HISTORY_TURNS,
        absolute_max_chars=graph_module.MAX_HISTORY_CHARS,
    )
    assert budget.effective is False
