"""A production smoke test: the real app, the real routes, a real request.

The other tests check units. This one starts the actual FastAPI application
(the same `harness.main:app` the runtime serves) and asks it the questions a
user's first minute would ask: is it alive, what does it hold, what can it
run, and does it refuse honestly when something is missing.

It is deliberately read-only. A smoke test that mutates production state is
not a smoke test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from harness.deps import require_operator
    from harness.main import app

    app.dependency_overrides[require_operator] = lambda: True
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(require_operator, None)


def test_the_runtime_is_alive(client):
    response = client.get("/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("status") in ("ok", "healthy", "degraded") or payload


def test_the_projects_surface_answers(client):
    response = client.get("/projects")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


def test_the_gallery_surface_answers(client):
    response = client.get("/gallery")
    assert response.status_code == 200, response.text
    assert "entries" in response.json()


def test_the_venue_surface_answers_and_names_the_gaps(client):
    response = client.get("/quant/venues")
    assert response.status_code == 200, response.text
    venues = response.json()["venues"]
    ids = [v["id"] for v in venues]
    assert ids == ["pine", "ninjascript", "powerlanguage", "easylanguage"]
    for venue in venues:
        if not venue["available"]:
            assert venue["reason"], venue["id"]


def test_the_history_catalog_answers(client):
    response = client.get("/market/history")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "available" in payload
    if payload["available"]:
        assert isinstance(payload["series"], list)


def test_the_market_providers_report_credential_presence_never_the_secret(client):
    response = client.get("/market/providers")
    assert response.status_code == 200, response.text
    payload = response.json()
    if not payload.get("available"):
        pytest.skip("the market layer is unavailable in this runtime")
    for provider in payload.get("providers", []):
        assert "credentialRef" in provider
        assert "apiKey" not in provider


def test_a_run_that_needs_a_provider_refuses_honestly(client):
    """A request with no strategy is a named refusal, not a fake success."""
    response = client.post("/quant/edge-report", json={"experimentId": "exp_nope"})
    assert response.status_code in (400, 404, 422, 503), response.text
    body = response.json()
    assert body.get("detail"), body


def test_the_pine_route_reports_whether_the_engine_is_installed(client):
    response = client.get("/quant/pine")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "available" in payload
    if not payload["available"]:
        assert payload.get("reason")
