"""Milestone 3 (named sessions) + Milestone 4 (named profiles) tests.

These exercise the real store/service with a temp database and a temp profiles
root. They pin the isolation and lifecycle invariants.
"""

from __future__ import annotations

import os

import pytest

from harness.eclipse_memory.profiles import ProfileError, ProfileRegistry
from harness.eclipse_memory.service import EclipseMemoryService
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    run_store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db")))
    yield memory, run_store
    run_store.close()
    memory.close()


# ── M3 sessions ─────────────────────────────────────────────────────────────


def test_run_belongs_to_session(stores):
    _, run_store = stores
    run_store.create_run("run_1", "eclipse-agent", {"query": "hello"}, "u1", session_id="sess_1")
    run = run_store.get_run("run_1")
    assert run["sessionId"] == "sess_1"
    session = run_store.get_chat_session("sess_1")
    assert session is not None
    assert session["userId"] == "u1"
    assert run_store.session_runs("sess_1") == ["run_1"]


def test_session_lifecycle(stores):
    _, run_store = stores
    run_store.create_chat_session("sess_1", user_id="u1", title="Original")
    run_store.update_chat_session("sess_1", title="Renamed")
    assert run_store.get_chat_session("sess_1")["title"] == "Renamed"
    # Pause / archive.
    run_store.update_chat_session("sess_1", status="paused")
    assert run_store.get_chat_session("sess_1")["status"] == "paused"
    run_store.delete_chat_session("sess_1")
    assert run_store.get_chat_session("sess_1")["status"] == "archived"
    # Restore.
    run_store.update_chat_session("sess_1", status="active")
    assert run_store.get_chat_session("sess_1")["status"] == "active"


def test_session_fork_links_source(stores):
    _, run_store = stores
    run_store.create_chat_session("sess_1", user_id="u1", title="Research")
    fork = run_store.fork_chat_session("sess_1", "sess_2")
    assert fork["sourceSessionId"] == "sess_1"
    # Source is untouched.
    assert run_store.get_chat_session("sess_1")["title"] == "Research"


def test_session_hard_delete_clears_index_not_trace(stores):
    _, run_store = stores
    run_store.create_run("run_1", "eclipse-agent", {"query": "hello"}, session_id="sess_1")
    run_store.index_session_message(run_id="run_1", role="user", content="hello",
                                    session_id="sess_1")
    result = run_store.delete_chat_session("sess_1", hard=True)
    assert result["deleted"] is True
    assert run_store.get_chat_session("sess_1") is None
    assert run_store.session_message_count() == 0
    # The run trace survives.
    assert run_store.get_run("run_1") is not None


def test_session_search_filters(stores):
    _, run_store = stores
    run_store.create_run("r1", "a", {"query": "q"}, session_id="s1", profile_id="p1")
    run_store.create_run("r2", "a", {"query": "q"}, session_id="s2", profile_id="p2")
    run_store.index_session_message(run_id="r1", role="user", content="rebalance quarterly",
                                    session_id="s1", profile_id="p1")
    run_store.index_session_message(run_id="r2", role="user", content="rebalance monthly",
                                    session_id="s2", profile_id="p2")
    by_session = run_store.search_session_messages("rebalance", session_id="s1")
    assert {h["runId"] for h in by_session["results"]} == {"r1"}
    by_profile = run_store.search_session_messages("rebalance", profile_id="p2")
    assert {h["runId"] for h in by_profile["results"]} == {"r2"}
    by_role = run_store.search_session_messages("rebalance", role="assistant")
    assert by_role["results"] == []


def test_session_search_phrase_ranks_first(stores):
    _, run_store = stores
    run_store.create_run("r1", "a", {"query": "q"})
    run_store.create_run("r2", "a", {"query": "q"})
    run_store.index_session_message(run_id="r1", role="assistant",
                                    content="beta something alpha gamma unrelated prose")
    run_store.index_session_message(run_id="r2", role="assistant",
                                    content="the alpha beta phrase appears here")
    result = run_store.search_session_messages("alpha beta")
    assert result["results"]
    # The exact-phrase document ranks first.
    assert "phrase appears" in (result["results"][0]["snippet"] or "")


def test_session_summary_is_bounded_and_persisted(stores):
    _, run_store = stores
    run_store.create_run("r1", "a", {"query": "Compare AAPL and MSFT margins"}, session_id="s1")
    run_store.index_session_message(run_id="r1", role="user", content="Compare AAPL and MSFT margins", session_id="s1", ordinal=0)
    run_store.index_session_message(run_id="r1", role="assistant", content="AAPL wins. Next step: verify period.", session_id="s1", ordinal=1)
    from harness.session_index import build_summary

    result = build_summary(run_store, "s1")
    assert result["ok"] is True
    summary = result["summary"]
    assert summary["objective"]
    assert "AAPL" in summary["instruments"]
    # Persisted on the session (searchable/opt-in; never auto-injected).
    stored = run_store.get_chat_session("s1")
    assert stored["summary"]["objective"]


# ── M4 profiles ─────────────────────────────────────────────────────────────


def test_profile_create_list_and_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    registry = ProfileRegistry()
    registry.create("work", name="Work", retention_days=30)
    profiles = {p["id"]: p for p in registry.list()}
    assert "work" in profiles
    assert profiles["work"]["memoryNamespace"] == "profile:work"
    # Directory projection with the documented subfolders.
    directory = profiles["work"]["directory"]
    assert os.path.isfile(os.path.join(directory, "PROFILE.json"))
    for sub in ("sessions", "skills", "history", "exports"):
        assert os.path.isdir(os.path.join(directory, sub))


def test_profile_default_cannot_be_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    registry = ProfileRegistry()
    registry.ensure_default()
    with pytest.raises(ProfileError):
        registry.delete("default")


def test_profile_inheritance_readonly_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    registry = ProfileRegistry()
    registry.create("personal")
    registry.create("project-x", inherits="personal")
    assert registry.inherited_ids("project-x") == ["personal"]
    assert registry.readable_profile_ids("project-x") == ["project-x", "personal"]


def test_profile_inheritance_cycle_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    registry = ProfileRegistry()
    registry.create("a")
    registry.create("b", inherits="a")
    with pytest.raises(ProfileError):
        registry.update("a", inherits="b")


def test_profile_delete_blocked_by_child(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_PROFILES_ROOT", str(tmp_path / "profiles"))
    registry = ProfileRegistry()
    registry.create("personal")
    registry.create("project-x", inherits="personal")
    with pytest.raises(ProfileError):
        registry.delete("personal")


def test_cross_profile_memory_isolation(stores):
    """A memory scoped to one profile is not returned for another."""
    memory, _ = stores
    memory.profiles.create("work")
    work_scope = "profile:work"
    memory.write_memory(
        memory_type="preference", content="Work prefers formal tone.",
        source="explicit_user", scope="user", scope_id=work_scope,
    )
    work = memory.retrieve(query="formal tone", actor_scope="user", scope_id=work_scope)
    assert work.memories
    other = memory.retrieve(query="formal tone", actor_scope="user", scope_id="profile:personal")
    assert other.memories == []
