"""Preference-learning API: read model + operator-gated learning pass.

A body boolean from a remote caller must never authorize the pass, and the read
model must report real evidence (not fabricated activity).
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-pref-api-run-"), "agent-memory.db"))
os.environ.setdefault("ECLIPSE_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-pref-api-em-"), "eclipse-memory.db"))

REMOTE = ("203.0.113.9", 5555)
SECRET = "runtime-operator-secret-pref-abc123"


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _observe(owner: str) -> None:
    from harness import main as main_module

    for index in range(3):
        main_module.service.memory.observe_turn_preferences(
            "Please show the results as a table",
            user_id=owner,
            run_id=f"api-pref-{owner}-{index}",
            learn_now=False,
        )


def test_preferences_read_model(client):
    owner = f"pref-api-{uuid.uuid4()}"
    _observe(owner)
    res = client.get(f"/eclipse-memory/preferences?scopeId={owner}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["mode"] == "ask"
    assert body["observationCount"] == 3
    assert len(body["observations"]) == 1
    assert body["observations"][0]["dimension"] == "answer_format"
    assert body["thresholds"]["minDistinctRuns"] == 3


def test_preferences_learn_is_operator_gated(client, monkeypatch):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    remote = TC(main_module.app, client=REMOTE)
    res = remote.post("/eclipse-memory/preferences/learn", json={"operator": True})
    assert res.status_code == 403, res.text

    monkeypatch.setenv("CRON_SECRET", SECRET)
    remote_with_secret = TC(main_module.app, client=REMOTE)
    res = remote_with_secret.post(
        "/eclipse-memory/preferences/learn",
        json={"operator": True},
        headers={"X-Harness-Operator": SECRET},
    )
    assert res.status_code == 200, res.text


def test_preferences_learn_creates_an_inert_suggestion(client):
    owner = f"pref-api-{uuid.uuid4()}"
    _observe(owner)
    res = client.post("/eclipse-memory/preferences/learn", json={"userId": owner})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert len(body["created"]) == 1
    pending = client.get(f"/eclipse-memory/preferences?scopeId={owner}").json()
    assert len(pending["suggestions"]) == 1
    assert pending["suggestions"][0]["provenance"] == "preference_learning"
