"""Persona API seam — status mapping, optimistic concurrency, limits."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.personas import PersonaStore, set_persona_store
from harness.routers.personas import router


class _Store:
    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    set_persona_store(PersonaStore(_Store()))
    try:
        yield TestClient(app)
    finally:
        set_persona_store(None)


def _create(client: TestClient, **overrides) -> dict:
    payload = {"name": "Terse desk", "description": "", "instructions": "Be terse."}
    payload.update(overrides)
    response = client.post("/personas", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["persona"]


def test_create_activate_draft_and_reset(client):
    persona = _create(client)
    assert persona["status"] == "draft"

    activated = client.post(f"/personas/{persona['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["persona"]["activeVersion"] == 1

    drafted = client.patch(
        f"/personas/{persona['id']}",
        json={"instructions": "Be very terse.", "expectedRevision": activated.json()["persona"]["revision"]},
    )
    assert drafted.status_code == 200
    assert drafted.json()["persona"]["hasDraft"] is True

    active = client.get("/personas/active").json()
    assert active["persona"]["instructions"] == "Be terse."

    reset = client.post("/personas/reset")
    assert reset.status_code == 200
    assert reset.json()["isDefault"] is True

    listed = client.get("/personas")
    assert listed.status_code == 200
    assert len(listed.json()["personas"]) == 1


def test_a_stale_revision_is_a_409(client):
    persona = _create(client)
    stale = persona["revision"]

    first = client.patch(
        f"/personas/{persona['id']}",
        json={"instructions": "One.", "expectedRevision": stale},
    )
    assert first.status_code == 200

    second = client.patch(
        f"/personas/{persona['id']}",
        json={"instructions": "Two.", "expectedRevision": stale},
    )
    assert second.status_code == 409
    assert "another window" in second.json()["detail"]


def test_overlong_instructions_are_a_400(client):
    response = client.post("/personas", json={"name": "Too long", "instructions": "x" * 2001})
    assert response.status_code == 400
    assert "at most" in response.json()["detail"]


def test_preview_reports_the_effective_prompt(client):
    _create(client)
    response = client.get("/personas/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["isDefault"] is True
    assert body["personaBlock"] == ""
    assert len(body["basePrompt"]) > 1000
    assert body["maxChars"] == 2000


def test_unknown_persona_is_a_404(client):
    assert client.get("/personas/per_missing").status_code == 404
