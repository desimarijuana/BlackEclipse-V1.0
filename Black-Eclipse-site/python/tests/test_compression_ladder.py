"""W2: the unified compression ladder (prune -> summary -> skeleton).

The properties under test are the ones the plan promises: prune is free, the
tail and the assistant/tool pairs are never split, a model failure commits the
deterministic skeleton (never a lossy claim), the cooldown is persisted, and
`/compact` can force one attempt.
"""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from harness.context.compression_ladder import (
    LadderResult,
    compact_turns,
    compress,
    protect_tail,
)
from harness.context.compression_state import CompressionStateStore
from harness.persistence import AgentMemoryStore


def _store():
    directory = tempfile.mkdtemp(prefix="be-w2-ladder-")
    return AgentMemoryStore(os.path.join(directory, "agent-memory.db"))


def _budget(gate: str, *, window: int = 10_000, effective: bool = True):
    return SimpleNamespace(
        gate=gate, window=window if effective else None, effective=effective,
    )


def _tool_history(n: int = 8, chars: int = 400) -> list:
    messages: list = [SystemMessage(content="system policy")]
    for i in range(n):
        messages.append(HumanMessage(content=f"question {i}"))
        messages.append(AIMessage(
            content="", tool_calls=[{"id": f"c{i}", "name": "terminal", "args": {}}],
        ))
        messages.append(ToolMessage(
            content="output " * (chars // 7) + str(i), tool_call_id=f"c{i}", name="terminal",
        ))
        messages.append(AIMessage(content=f"answer {i}"))
    return messages


def test_protect_tail_keeps_recent_turns_and_never_splits_a_pair():
    messages = _tool_history(6)
    cut = protect_tail(messages, turns=2, tool_results=1)
    assert cut > 0
    assert not isinstance(messages[cut], ToolMessage)
    # The protected tail contains the last user turn.
    assert any(isinstance(m, HumanMessage) for m in messages[cut:])


def test_prune_is_free_and_keeps_handles(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")
    messages = [
        SystemMessage(content="system policy"),
        ToolMessage(content="old output " * 100, tool_call_id="c1", name="terminal"),
        ToolMessage(content='{"handles":["a"]} ' * 100, tool_call_id="c2", name="quote"),
        ToolMessage(content="recent " * 100, tool_call_id="c3", name="patch"),
        AIMessage(content="answer"),
        HumanMessage(content="next"),
    ]
    result = _run(compress, messages, budget=_budget("soft"), protect_tool_results=1)
    assert result.stage == "prune"
    assert result.used_model is False
    assert result.pruned_tool_results == 1
    assert "pruned tool result" in result.messages[1].content
    assert "handles" in result.messages[2].content


def test_short_run_is_a_noop(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")
    messages = [SystemMessage(content="s"), HumanMessage(content="q"), AIMessage(content="a")]
    result = _run(compress, messages, budget=_budget("continue"))
    assert result.stage == "none"
    assert result.ok is False
    assert result.messages == messages


def test_summary_failure_commits_the_skeleton(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")

    async def _boom(*args, **kwargs):
        raise TimeoutError("summary timed out")

    monkeypatch.setattr("harness.compaction._model_narrative", _boom)
    settings = {"history_compaction_model": True}
    result = _run(compress, _tool_history(8), budget=_budget("hard"), settings=settings,
                  request=object())
    assert result.stage == "skeleton"
    assert result.used_model is False
    assert result.ok is True
    assert result.dropped_turns > 0


def test_empty_summary_commits_the_skeleton(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")

    async def _empty(*args, **kwargs):
        return "", "the model returned nothing"

    monkeypatch.setattr("harness.compaction._model_narrative", _empty)
    result = _run(
        compress, _tool_history(8), budget=_budget("hard"),
        settings={"history_compaction_model": True}, request=object(),
    )
    assert result.stage == "skeleton"
    assert result.used_model is False


def test_successful_summary_uses_the_model_and_preserves_the_tail(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")

    async def _narrative(*args, **kwargs):
        return "Decisions: keep going.", ""

    monkeypatch.setattr("harness.compaction._model_narrative", _narrative)
    messages = _tool_history(8)
    result = _run(
        compress, messages, budget=_budget("hard"),
        settings={"history_compaction_model": True}, request=object(),
        protect_turns=2, protect_tool_results=1,
    )
    assert result.stage == "summary"
    assert result.used_model is True
    assert result.dropped_turns > 0
    assert result.summary_chars > 0
    # The current user turn survives verbatim.
    assert messages[-1].content in [m.content for m in result.messages]
    # The stable system head is kept ahead of the summary.
    assert result.messages[0].type == "system"


def test_failure_arms_the_cooldown_and_force_overrides(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "on")
    store = _store()
    try:
        state = CompressionStateStore(store)
        calls = {"n": 0}

        async def _boom(*args, **kwargs):
            calls["n"] += 1
            raise TimeoutError("timeout")

        monkeypatch.setattr("harness.compaction._model_narrative", _boom)
        settings = {"history_compaction_model": True}
        first = _run(
            compress, _tool_history(8), budget=_budget("hard"), settings=settings,
            state_store=state, session_id="s1", request=object(),
        )
        assert first.stage == "skeleton"
        assert calls["n"] == 1
        assert state.allow("s1") is False
        # Cooldown blocks a second model attempt; the skeleton still commits.
        second = _run(
            compress, _tool_history(8), budget=_budget("hard"), settings=settings,
            state_store=state, session_id="s1", request=object(),
        )
        assert second.stage == "skeleton"
        assert calls["n"] == 1
        # An explicit `/compact` force ignores the cooldown once.
        forced = _run(
            compress, _tool_history(8), budget=_budget("hard"), settings=settings,
            state_store=state, session_id="s1", force=True, request=object(),
        )
        assert forced.stage == "skeleton"
        assert calls["n"] == 2
    finally:
        store.close()


def test_off_kill_switch_does_nothing(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "off")
    messages = _tool_history(8)
    result = _run(compress, messages, budget=_budget("emergency"))
    assert result.stage == "none"
    assert result.ok is False
    assert result.messages == messages


def test_shadow_computes_but_does_not_apply(monkeypatch):
    monkeypatch.setenv("HARNESS_COMPRESSION_LADDER", "shadow")
    messages = _tool_history(8)
    result = _run(compress, messages, budget=_budget("soft"), protect_tool_results=1)
    assert result.pruned_tool_results > 0
    assert result.messages == messages


@pytest.mark.asyncio
async def test_compact_turns_returns_a_block_and_result():
    store = _store()
    try:
        from langchain_core.messages import HumanMessage as H

        block, result = await compact_turns(
            [H(content="what did we decide?"), H(content="x" * 100)],
            request=None, settings={}, state_store=CompressionStateStore(store),
            session_id="s1",
        )
        assert "compacted-conversation" in block
        assert result.dropped_turns == 2
        assert result.used_model is False
    finally:
        store.close()


def test_ladder_result_payload_is_bounded_and_content_free():
    result = LadderResult(stage="summary", dropped_turns=3, summary_chars=120)
    payload = result.to_dict()
    assert payload["stage"] == "summary"
    assert "messages" not in payload
    assert "content" not in payload


# ── helpers ─────────────────────────────────────────────────────────────────


def _run(fn, *args, **kwargs):
    """Run an async ladder call from a sync test."""
    import asyncio

    return asyncio.run(fn(*args, **kwargs))
