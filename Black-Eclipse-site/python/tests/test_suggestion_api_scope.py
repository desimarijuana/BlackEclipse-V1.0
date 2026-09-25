"""Suggestion ownership at the API level.

A suggestion carrying a `scopeId` may only be accepted/dismissed by that same
user; listing can be narrowed to a scope. These exercise the REAL FastAPI routes
(not just the service unit), and prove a caller guessing another user's
suggestion id is refused.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-sugg-run-"), "agent-memory.db"))
os.environ.setdefault("ECLIPSE_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-sugg-em-"), "eclipse-memory.db"))


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _make_suggestion(client, scope_id: str, content: str) -> str:
    """Create a pending suggestion through the service the app already holds."""
    from harness import main as main_module

    service = main_module.service
    service.memory.policy.set("memory_mode", "ask_before_saving")
    from harness.eclipse_memory.decision import decide_turn

    decision = decide_turn(content, user_id=scope_id)
    suggestion = service.memory.create_suggestion(decision, scope_id=scope_id)
    return suggestion["id"]


def test_suggestion_list_can_be_narrowed_by_scope(client):
    sid = _make_suggestion(client, "ownerA", "I prefer weekly summaries please")
    listed = client.get("/eclipse-memory/suggestions?scopeId=ownerA").json()["suggestions"]
    assert any(s["id"] == sid for s in listed)
    # A different scope does not include it.
    listed_b = client.get("/eclipse-memory/suggestions?scopeId=ownerB").json()["suggestions"]
    assert all(s["id"] != sid for s in listed_b)


def test_accept_refuses_another_users_suggestion(client):
    sid = _make_suggestion(client, "ownerA", "I prefer dark mode interfaces")
    res = client.post(
        f"/eclipse-memory/suggestions/{sid}/accept",
        json={"operator": True, "userId": "ownerB"},
    )
    assert res.status_code == 403, res.text
    # It remains pending — no mutation happened.
    pending = client.get("/eclipse-memory/suggestions?status=pending&scopeId=ownerA").json()["suggestions"]
    assert any(s["id"] == sid and s["status"] == "pending" for s in pending)


def test_dismiss_refuses_another_users_suggestion(client):
    sid = _make_suggestion(client, "ownerA", "I prefer quarterly reports only")
    res = client.post(
        f"/eclipse-memory/suggestions/{sid}/dismiss",
        json={"operator": True, "userId": "ownerB"},
    )
    assert res.status_code == 403, res.text
    pending = client.get("/eclipse-memory/suggestions?status=pending&scopeId=ownerA").json()["suggestions"]
    assert any(s["id"] == sid and s["status"] == "pending" for s in pending)


def test_owner_can_accept_their_own_suggestion(client):
    sid = _make_suggestion(client, "ownerA", "I prefer tables over charts")
    res = client.post(
        f"/eclipse-memory/suggestions/{sid}/accept",
        json={"operator": True, "userId": "ownerA"},
    )
    assert res.status_code == 200, res.text
    accepted = client.get("/eclipse-memory/suggestions?status=accepted&scopeId=ownerA").json()["suggestions"]
    assert any(s["id"] == sid for s in accepted)
