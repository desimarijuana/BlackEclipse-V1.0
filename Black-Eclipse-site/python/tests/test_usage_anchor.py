"""W2: usage anchor and compression cooldown primitives."""

from __future__ import annotations

import os
import tempfile

from harness.context.compression_state import CompressionStateStore
from harness.context.usage_anchor import UsageAnchorStore
from harness.persistence import AgentMemoryStore


def _store():
    directory = tempfile.mkdtemp(prefix="be-w2-anchor-")
    return AgentMemoryStore(os.path.join(directory, "agent-memory.db"))


def test_anchor_records_usage_and_estimates_only_appended_history():
    store = _store()
    try:
        anchors = UsageAnchorStore(store)
        anchor = anchors.record(
            "s1", model_key="openai/gpt-4o", prompt_tokens=10_000,
            completion_tokens=200, messages=[], history_chars=4_000,
            context_length=128_000,
        )
        assert anchor is not None
        assert anchor.anchored is True
        assert anchor.estimated_used(history_chars=6_000) == 10_500
        assert anchors.get("s1").prompt_tokens == 10_000
    finally:
        store.close()


def test_anchor_clear_and_model_switch_are_explicit():
    store = _store()
    try:
        anchors = UsageAnchorStore(store)
        anchors.record("s1", model_key="openai/gpt-4o", prompt_tokens=1,
                       completion_tokens=1, messages=[], history_chars=0,
                       context_length=1000)
        assert anchors.get("s1") is not None
        anchors.clear("s1")
        assert anchors.get("s1") is None

        anchors.record("s2", model_key="openai/gpt-4o", prompt_tokens=1,
                       completion_tokens=1, messages=[], history_chars=0,
                       context_length=1000)
        anchors.record("s2", model_key="ollama/llama", prompt_tokens=2,
                       completion_tokens=1, messages=[], history_chars=0,
                       context_length=1000)
        assert anchors.get("s2").model_key == "ollama/llama"
    finally:
        store.close()


def test_compression_cooldown_ladder_and_clear():
    store = _store()
    try:
        state = CompressionStateStore(store)
        now = [100.0]
        assert state.allow("s1", now=now[0])
        state.record_failure("s1", "timeout", now=now[0])
        assert not state.allow("s1", now=now[0] + 1)
        assert state.allow("s1", now=now[0] + 61)
        state.record_failure("s1", "timeout", now=now[0] + 61)
        assert not state.allow("s1", now=now[0] + 100)
        state.clear("s1")
        assert state.allow("s1", now=now[0] + 100)
    finally:
        store.close()


def test_usage_anchor_kill_switch_disables_store_and_anchor():
    from types import SimpleNamespace

    from harness.context.usage_anchor import prepare_anchor

    store = _store()
    try:
        request = SimpleNamespace(
            sessionId="s1", runId="r1",
            input=SimpleNamespace(history=[SimpleNamespace(content="hello")]),
        )
        anchors, anchor_id, anchor, chars = prepare_anchor(store, request, enabled=False)
        assert anchors is None
        assert anchor_id == "s1"
        assert anchor is None
        assert chars == 5
    finally:
        store.close()
