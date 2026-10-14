"""Private per-conversation memory — scope, isolation, read-through, forget.

A conversation-scoped run (a bot chat or a group-room member turn) owns a PRIVATE
durable-memory bucket keyed by its conversation id. It reads only its own bucket,
the signed-in user's own rows and truly-global `general` knowledge — never another
conversation's. These tests pin that contract.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.decision import resolve_owner_scope


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-convmem-")
    path = os.path.join(directory, "eclipse-memory.db")
    svc = EclipseMemoryService(EclipseMemoryStore(path))
    yield svc
    svc.close()


# ── Owner resolution ─────────────────────────────────────────────────────────


def test_resolve_owner_routes_personal_fact_to_conversation():
    assert resolve_owner_scope("user", None, user_id=None, conversation_id="bot-1") == (
        "conversation", "bot-1",
    )


def test_resolve_owner_keeps_user_when_signed_in():
    assert resolve_owner_scope("user", "u1", user_id="u1", conversation_id="bot-1") == (
        "user", "u1",
    )


def test_resolve_owner_conversation_without_id_degrades():
    assert resolve_owner_scope("conversation", None, user_id=None, conversation_id=None) == (
        "general", None,
    )
    assert resolve_owner_scope("conversation", None, user_id="u1", conversation_id=None) == (
        "user", "u1",
    )


# ── Write path ──────────────────────────────────────────────────────────────


def test_decide_turn_saves_preference_into_conversation(service):
    decision = service.decide_turn("I prefer concise answers", conversation_id="bot-1")
    assert decision.scope == "conversation"
    outcome = service.commit_decision(decision, conversation_id="bot-1")
    assert outcome["ok"] is True
    memory = outcome["memory"]
    assert memory["scope"] == "conversation"
    assert memory["scopeId"] == "bot-1"


def test_memory_tool_defaults_to_conversation(service):
    # write_memory with an explicit conversation scope is the persistence path the
    # memory tool uses for a bot.
    memory = service.write_memory(
        memory_type="semantic", content="The desk's research cadence is weekly",
        source="explicit_user", scope="conversation", scope_id="bot-7", created_by="bot-7",
    )
    assert memory["scope"] == "conversation"
    assert memory["scopeId"] == "bot-7"


# ── Isolation + read-through ─────────────────────────────────────────────────


def test_conversations_are_isolated_but_share_general(service):
    service.write_memory(
        memory_type="preference", content="User prefers concise answers always",
        source="explicit_user", scope="conversation", scope_id="bot-1", created_by="bot-1",
    )
    service.write_memory(
        memory_type="preference", content="User prefers detailed answers always",
        source="explicit_user", scope="conversation", scope_id="bot-2", created_by="bot-2",
    )
    service.write_memory(
        memory_type="semantic", content="Market hours are 9:30 to 16:00 ET",
        source="explicit_user", scope="general",
    )

    # A standing preference is always recalled; an unrelated conversation's
    # preference is never even a candidate.
    a = service.retrieve(query="concise answers", conversation_id="bot-1")
    contents = " ".join(m["content"] for m in a.memories)
    assert "concise answers" in contents
    assert "detailed answers" not in contents

    # A truly-global `general` memory is readable from a conversation when it is
    # relevant to the query.
    g = service.retrieve(query="market hours", conversation_id="bot-1")
    gcontents = " ".join(m["content"] for m in g.memories)
    assert "Market hours" in gcontents

    # The other conversation never sees bot-1's private fact.
    b = service.retrieve(query="concise answers", conversation_id="bot-2")
    bcontents = " ".join(m["content"] for m in b.memories)
    assert "concise answers" not in bcontents


def test_conversation_reads_user_rows_when_signed_in(service):
    service.write_memory(
        memory_type="preference", content="User prefers blue charts always",
        source="explicit_user", scope="user", scope_id="u1", created_by="u1",
    )
    result = service.retrieve(
        query="blue charts", conversation_id="bot-1", scope_id="u1",
        actor_scope="user",
    )
    assert any("blue charts" in m["content"] for m in result.memories)


def test_scope_authorization_rejects_another_conversation():
    from harness.eclipse_memory.retrieval import _scope_authorized

    row = {"scope": "conversation", "scopeId": "bot-2"}
    ok, reason = _scope_authorized(
        row, actor_scope=None, scope_id=None, conversation_id="bot-1",
    )
    assert ok is False
    assert reason == "another conversation's scope"
    ok, _ = _scope_authorized(
        row, actor_scope=None, scope_id=None, conversation_id="bot-2",
    )
    assert ok is True


# ── Forget ───────────────────────────────────────────────────────────────────


def test_forget_conversation_archives_without_deleting(service):
    memory = service.write_memory(
        memory_type="semantic", content="A private conversation note here",
        source="explicit_user", scope="conversation", scope_id="bot-9", created_by="bot-9",
    )
    result = service.forget_conversation("bot-9")
    assert result["ok"] is True
    assert memory["id"] in result["archived"]
    # Archived, not deleted: still present, inert.
    assert service.store.get_memory(memory["id"]) is not None
    after = service.retrieve(query="private conversation note", conversation_id="bot-9")
    assert not after.memories
