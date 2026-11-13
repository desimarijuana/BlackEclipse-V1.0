"""W2.5: safe checkpoint recovery for a step>1 context overflow.

The guards are the point of these tests: a completed-work checkpoint is
recoverable, but an unconfirmed effect (started, or reconciled to unknown) is
not - the external side effect may have happened, and neither replaying nor
skipping it silently is safe.
"""

from __future__ import annotations

import os
import tempfile

from langchain_core.messages import AIMessage, HumanMessage

from harness.persistence import AgentMemoryStore
from harness.run_effects import RunEffects
from harness.run_lineage import RunLineage
from harness.run_recovery import recoverable_state


def _store() -> AgentMemoryStore:
    directory = tempfile.mkdtemp(prefix="be-w2-recovery-")
    return AgentMemoryStore(os.path.join(directory, "agent-memory.db"))


def _checkpoint(store: AgentMemoryStore, run_id: str, *, kind: str = "tool_results") -> None:
    store.create_run(run_id, "eclipse-agent", {"query": "q"})
    store.update_run(run_id, status="running")
    lineage = RunLineage(store)
    lineage.save_messages(run_id, [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "read_file", "args": {}}]),
    ])
    lineage.save_checkpoint(run_id, kind, {
        "step": 1, "toolCalls": 1, "toolErrors": 0, "messages": [],
        "messageSeq": lineage.message_cursor(run_id),
    })


def test_completed_work_checkpoint_is_recoverable():
    store = _store()
    try:
        _checkpoint(store, "r_ok")
        state = recoverable_state(store, "r_ok")
        assert state is not None
        assert state["step"] == 1
        assert state["tool_calls"] == 1
        assert len(state["messages"]) == 2
    finally:
        store.close()


def test_agent_step_checkpoint_is_not_a_completed_work_boundary():
    store = _store()
    try:
        _checkpoint(store, "r_agent_step", kind="agent_step")
        assert recoverable_state(store, "r_agent_step") is None
    finally:
        store.close()


def test_started_effect_blocks_recovery():
    store = _store()
    try:
        _checkpoint(store, "r_started")
        effects = RunEffects(store)
        effects.begin("r_started", 1, "c1", "send_email", "irreversible")
        assert recoverable_state(store, "r_started") is None
        effects.finish("r_started", 1, "c1", ok=True)
        assert recoverable_state(store, "r_started") is not None
    finally:
        store.close()


def test_unknown_effect_still_blocks_recovery():
    store = _store()
    try:
        _checkpoint(store, "r_unknown")
        effects = RunEffects(store)
        effects.begin("r_unknown", 1, "c1", "send_email", "irreversible")
        effects.mark_unknown("r_unknown", 1, "c1")
        assert recoverable_state(store, "r_unknown") is None
    finally:
        store.close()


def test_trim_to_chars_preserves_head_and_last_user_turn():
    from langchain_core.messages import SystemMessage, ToolMessage

    from harness.run_recovery import _trim_to_chars

    messages = [SystemMessage(content="policy")]
    for i in range(20):
        messages.append(HumanMessage(content=f"question {i} " + "x" * 200))
        messages.append(AIMessage(content="", tool_calls=[{"id": f"c{i}", "name": "t", "args": {}}]))
        messages.append(ToolMessage(content="y" * 400, tool_call_id=f"c{i}", name="t"))
        messages.append(AIMessage(content="answer " + "z" * 200))
    trimmed = _trim_to_chars(messages, 4_000)
    assert trimmed[0].type == "system"
    assert trimmed[-4].type == "human"  # the last user turn survives
    assert len(trimmed) < len(messages)
    assert sum(len(str(m.content)) for m in trimmed) <= 4_000
    # No half pair: a tool message is never the first tail message.
    assert not any(
        m.type == "tool" and (i == 0 or trimmed[i - 1].type != "ai")
        for i, m in enumerate(trimmed)
    )

