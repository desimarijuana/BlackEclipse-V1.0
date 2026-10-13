"""Durable learning-path + progress persistence tests (eclipse-memory.db)."""

from __future__ import annotations

import os

from harness.eclipse_memory.db import EclipseMemoryDb
from harness.eclipse_memory.schema import SCHEMA_VERSION
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.research.learning_store import LearningStore


def _store(tmp_path) -> LearningStore:
    db = EclipseMemoryDb(os.path.join(str(tmp_path), "eclipse-memory.db"))
    return LearningStore(EclipseMemoryStore(db=db))


def test_schema_bumped_for_learning_tables(tmp_path):
    assert SCHEMA_VERSION >= 30
    ls = _store(tmp_path)
    # The tables exist after migration.
    names = {r["name"] for r in ls._db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"LearningPath", "LearningNodeProgress", "LearningPreference"} <= names


def test_path_save_get_update_and_resume(tmp_path):
    ls = _store(tmp_path)
    ls.save_path("p1", goal="quantitative trading", payload={"v": 1}, start_level="beginner")
    assert ls.get_path("p1")["goal"] == "quantitative trading"
    ls.update_path("p1", payload={"v": 2}, version=2)
    assert ls.get_path("p1")["payload"] == {"v": 2} and ls.get_path("p1")["version"] == 2
    # Resume finds the active path from a broader returning request.
    found = ls.find_active_by_goal("i want to keep learning quantitative trading")
    assert found is not None and found["id"] == "p1"
    assert len(ls.list_paths()) == 1


def test_node_progress_persists_and_upserts(tmp_path):
    ls = _store(tmp_path)
    ls.save_path("p1", goal="g", payload={"graph": {"nodes": [{"id": "a"}, {"id": "b"}]}})
    ls.set_node_status("p1", "a", "completed", "passed the quiz")
    ls.set_node_status("p1", "b", "in_progress")
    ls.set_node_status("p1", "a", "skipped")  # upsert, not duplicate
    progress = {p["nodeId"]: p for p in ls.list_node_progress("p1")}
    assert len(progress) == 2
    assert progress["a"]["status"] == "skipped"
    assert progress["b"]["status"] == "in_progress"
    # An unknown status is normalized to pending (never stored verbatim).
    ls.set_node_status("p1", "b", "bogus")
    assert {p["nodeId"]: p for p in ls.list_node_progress("p1")}["b"]["status"] == "pending"


def test_delete_path_cascades_progress(tmp_path):
    ls = _store(tmp_path)
    ls.save_path("p1", goal="g", payload={})
    ls.set_node_status("p1", "a", "completed")
    assert ls.delete_path("p1") is True
    assert ls.get_path("p1") is None
    assert ls.list_node_progress("p1") == []


def test_preferences_round_trip(tmp_path):
    ls = _store(tmp_path)
    ls.set_preference("pace", "2 hours/week")
    ls.set_preference("pace", "3 hours/week")
    assert ls.get_preference("pace")["value"] == "3 hours/week"
    assert ls.list_preferences() == [{"key": "pace", "value": "3 hours/week", "updatedAt": ls.get_preference("pace")["updatedAt"]}]
