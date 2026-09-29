"""Milestone 0 fixture — the reproduced overflow, asserted post-fix.

BEFORE the fix (recorded verbatim in `docs/harness/context-budget-progress.md`):

    status: failed
    error.code: PROVIDER_ERROR
    error.message: Error code: 400 - {'error': {'message': "This model's maximum
      context length is 4096 tokens. However, your messages resulted in 18734
      tokens.", 'type': 'invalid_request_error', 'code': 'context_length_exceeded'}}
    events: ['run.created', 'run.started', 'prompt.plan',
             'memory.dropped_context_extracted', 'model.requested', 'run.failed']
    history_bounded event: False

AFTER the fix the same fixture must:
  * classify the rejection as CONTEXT_OVERFLOW (not the generic PROVIDER_ERROR);
  * state the honest reason + remedy;
  * still fail (the request genuinely cannot fit) — never a fake answer.

Deterministic. A scripted model raises the SAME provider-native context-length
error an OpenAI-compatible endpoint raises when the assembled request exceeds
the window. A long transcript is driven past the history bound.

Run (from `Black-Eclipse-site/`):
    python/python.exe -m pytest python/tests/test_context_budget_repro.py -q -s
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools


OVERSIZE = (
    "Error code: 400 - {'error': {'message': \"This model's maximum context "
    "length is 4096 tokens. However, your messages resulted in 18734 tokens.\", "
    "'type': 'invalid_request_error', 'code': 'context_length_exceeded'}}"
)


class OverflowModel:
    """Simulates a provider that rejects a request that exceeds its window.

    The 'window' is enforced by the model itself, matching real provider
    behaviour. `window_override` on the run lets the runtime KNOW the window so
    it derives a real budget; without it the window is unknown (conservative).
    """

    def __init__(self, window_tokens: int):
        self.window_tokens = window_tokens

    def bind_tools(self, tools):
        return self

    def _cost(self, messages) -> int:
        total = 0
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            total += (len(content) + 3) // 4
        return total

    async def ainvoke(self, messages):
        if self._cost(messages) > self.window_tokens:
            raise RuntimeError(OVERSIZE)
        return AIMessage(content="small-window answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-repro-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _long_history(turns: int, chars_each: int):
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * chars_each}
        for i in range(turns)
    ]


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    return reg


@pytest.mark.asyncio
async def test_repro_small_window_overflow_is_classified_specifically(store, monkeypatch):
    # 40 turns x 2000 chars = 80_000 chars, enough to overflow a 4096-token
    # window. An explicit unknown provider (ollama) means the runtime cannot derive
    # a real budget, so this is the honest "cannot trim enough" terminal path.
    model = OverflowModel(window_tokens=4096)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    req = RunRequest(
        runId="run_repro_small",
        input=RunInput(query="continue", history=_long_history(40, 2000)),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(
            provider="ollama", model="tiny-context",
            base_url="http://localhost:11434/v1",
        ),
        callbackBaseUrl="http://localhost:3000",
    )
    result = await graph_module.execute_run(
        req, _registry(), FakeBridge(), store
    )

    events = [e["type"] for e in store.list_events("run_repro_small")]
    print("\n=== FIXED small window (unknown) ===")
    print("status:", result.status)
    print("error.code:", result.error.code if result.error else None)
    print("error.message:", result.error.message if result.error else None)
    print("events:", events)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "CONTEXT_OVERFLOW"       # specific, not generic
    assert "context window" in result.error.message.lower()
    assert "shorter conversation" in result.error.message.lower()
    assert "context.overflow" in events
    assert "run.failed" in events


@pytest.mark.asyncio
async def test_repro_known_window_trims_and_succeeds(store, monkeypatch):
    # BEFORE the fix a 80_000-char history was sent whole (bounded only by the
    # 40_000-char constant) and overflowed. WITH the fix, once the window is
    # known the runtime derives a real budget, trims the history, the request
    # fits, and the trim is surfaced.
    model = OverflowModel(window_tokens=20_000)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    req = RunRequest(
        runId="run_repro_known",
        input=RunInput(
            query="continue",
            history=_long_history(40, 2000),
            context={"_context_budget_override": {"window": 20_000}},
        ),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="openai", model="gpt-4o", api_key="x"),
        callbackBaseUrl="http://localhost:3000",
    )
    result = await graph_module.execute_run(req, _registry(), FakeBridge(), store)
    events = [e["type"] for e in store.list_events("run_repro_known")]
    print("\n=== FIXED known window ===")
    print("status:", result.status)
    print("events:", events)

    assert result.status == "completed"
    assert "memory.history_bounded" in events
    assert store.get_run("run_repro_known")["status"] == "completed"
    assert result.context is not None
    assert result.context["window"] == 20_000
    assert result.context["droppedTurns"] > 0


def test_repro_large_window_keeps_usable_turns():
    # A large-context model: the measured budget keeps all 40 turns the hardcoded
    # bound would have discarded.
    from harness.context_budget import compute_history_budget

    history = _long_history(40, 100)
    req = RunRequest(
        runId="run_repro_large",
        input=RunInput(query="continue", history=history),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="openai", model="gpt-4o", api_key="x"),
        callbackBaseUrl="http://localhost:3000",
    )
    budget = compute_history_budget(
        provider="openai", model="gpt-4o",
        system_prompt="sys", user_turn="continue",
        absolute_max_turns=graph_module.MAX_HISTORY_TURNS,
        absolute_max_chars=graph_module.MAX_HISTORY_CHARS,
    )
    kept, dropped = graph_module._bounded_history(req, budget)
    print("\n=== FIXED large window ===")
    print("kept turns:", len(kept), "dropped turns:", len(dropped))
    assert len(kept) == 40
    assert dropped == []


def test_repro_unknown_window_uses_the_hardcoded_bound():
    # Unknown stays safe: the bound is exactly today's conservative ceiling.
    history = _long_history(30, 100)
    req = RunRequest(
        runId="run_repro_unknown",
        input=RunInput(query="continue", history=history),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="whatever", base_url="http://x"),
        callbackBaseUrl="http://localhost:3000",
    )
    kept, dropped = graph_module._bounded_history(req)
    assert len(kept) == graph_module.MAX_HISTORY_TURNS
    assert len(dropped) == 10
