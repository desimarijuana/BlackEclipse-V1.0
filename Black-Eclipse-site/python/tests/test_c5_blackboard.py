"""C5: shared blackboard, scoped to the root run."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage
from harness.spawn import BoardStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-board-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("root", "eclipse-agent", {"query": "root"})
    s.create_run("child", "eclipse-agent", {"query": "child"})
    s.create_run("other", "eclipse-agent", {"query": "other"})
    RunLineage(s).set_run_parent("child", "root")
    yield s
    s.close()


def test_a_child_reaches_the_root_board_and_an_unrelated_run_does_not(store):
    board = BoardStore(store)
    board.write(run_id="child", kind="fact", text="drawdown is 12.4%")
    assert board.root_of("child") == "root"
    assert [e["text"] for e in board.read("root")] == ["drawdown is 12.4%"]
    assert board.read("other") == []


def test_entries_are_searchable_and_kind_filtered(store):
    board = BoardStore(store)
    board.write(run_id="root", kind="fact", text="AAPL price is 190")
    board.write(run_id="child", kind="decision", text="use the 2y window")
    assert board.search("root", "190")[0]["kind"] == "fact"
    assert [e["kind"] for e in board.read("root", kind="decision")] == ["decision"]


def test_the_board_refuses_a_write_past_its_entry_cap(store):
    board = BoardStore(store)
    board.ensure_board("root")
    store._db.execute("UPDATE Board SET maxEntries=1 WHERE rootRunId='root'")
    board.write(run_id="root", kind="note", text="one")
    with pytest.raises(ValueError):
        board.write(run_id="root", kind="note", text="two")


def test_an_unknown_kind_is_rejected(store):
    with pytest.raises(ValueError):
        BoardStore(store).write(run_id="root", kind="made-up", text="x")
