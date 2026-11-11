"""Round 5 / C2: the durable message cursor behind a checkpoint."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-cursor-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_cursor", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


def test_the_full_conversation_survives_beyond_the_legacy_tail(store):
    lineage = RunLineage(store)
    long_text = "evidence-" * 6_000  # 54k chars, well over the 12k legacy cap
    messages = [
        HumanMessage(content="first"),
        AIMessage(content=long_text),
        HumanMessage(content="last"),
    ]

    cursor = lineage.save_messages("run_cursor", messages)
    assert cursor == 2
    assert lineage.message_cursor("run_cursor") == 2

    restored = lineage.load_messages("run_cursor")
    assert len(restored) == 3
    assert restored[1].content == long_text
    assert len(restored[1].content) == len(long_text)


def test_a_shorter_rewrite_deletes_the_stale_tail(store):
    lineage = RunLineage(store)
    lineage.save_messages("run_cursor", [HumanMessage(content=str(i)) for i in range(5)])
    lineage.save_messages("run_cursor", [HumanMessage(content=str(i)) for i in range(3)])

    restored = lineage.load_messages("run_cursor")
    assert [message.content for message in restored] == ["0", "1", "2"]
    assert lineage.message_cursor("run_cursor") == 2


def test_an_absent_cursor_is_empty_not_an_error(store):
    lineage = RunLineage(store)
    assert lineage.load_messages("run_none") == []
    assert lineage.message_cursor("run_none") is None


def test_the_migration_ledger_records_the_cursor_schema(store):
    lineage = RunLineage(store)
    applied = lineage._db.execute(
        "SELECT id FROM HarnessMigration WHERE namespace='agent-memory'"
    ).fetchall()
    assert "2026-11-11-001-run-message-cursor" in {row["id"] for row in applied}
