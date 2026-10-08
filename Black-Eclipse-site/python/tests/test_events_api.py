"""Event Console API tests — the `/events/*` operator-gated route group."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.event_system.envelope import EclipseEvent
from harness.event_system.service import EventSystem
from harness.persistence import AgentMemoryStore


class StubService:
    def __init__(self, store):
        self.store = store
        self.bus = None

    def event_system(self):
        from harness.event_system.bootstrap import event_system

        return event_system(self)


@pytest.fixture
def client(tmp_workspace, monkeypatch):
    from harness.routers import events as events_router

    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    stub = StubService(memory)
    system = stub.event_system()
    system.store.append(EclipseEvent.create(
        "task.completed", {"taskId": "t1"}, source="tasks", correlation_id="c1", task_id="t1",
    ))
    system.store.append(EclipseEvent.create(
        "market.price.updated", {"symbol": "BTCUSDT", "changePercent": 9}, source="market",
    ))
    monkeypatch.setattr(events_router, "service", stub)

    app = FastAPI()
    app.include_router(events_router.router)
    with TestClient(app) as test_client:
        yield test_client, system


def test_health_registry_and_types(client):
    http, _ = client
    assert http.get("/events/health").status_code == 200
    registry = http.get("/events/registry").json()
    assert any(spec["type"] == "task.completed" for spec in registry["events"])
    types = http.get("/events/types").json()["types"]
    assert any(t["type"] == "task.completed" for t in types)


def test_list_and_get_event(client):
    http, system = client
    listed = http.get("/events", params={"correlationId": "c1"}).json()
    assert listed["count"] == 1
    event_id = listed["events"][0]["id"]
    detail = http.get(f"/events/{event_id}").json()["event"]
    assert detail["type"] == "task.completed"
    assert http.get("/events/does-not-exist").status_code == 404


def test_filter_by_namespace_and_predicate_query(client):
    http, _ = client
    ns = http.get("/events", params={"namespace": "market"}).json()
    assert [e["type"] for e in ns["events"]] == ["market.price.updated"]


def test_subscription_declare_and_list(client):
    http, _ = client
    created = http.post("/events/subscriptions", json={
        "subscriberId": "agent.market", "subscriberType": "agent",
        "patterns": ["market.**", "filing.discovered"],
    }).json()
    assert created["subscription"]["subscriberId"] == "agent.market"
    listing = http.get("/events/subscriptions").json()
    assert any(s["subscriberId"] == "agent.market" for s in listing["declared"])
    assert http.delete("/events/subscriptions/agent.market").json()["removed"] == 1


def test_replay_endpoint_modes(client):
    http, _ = client
    observe = http.post("/events/replay", json={"mode": "observe", "correlationId": "c1"}).json()["replay"]
    assert observe["count"] == 1 and observe["dryRun"] is True

    unauthorized = http.post("/events/replay", json={"mode": "full", "correlationId": "c1"})
    assert unauthorized.status_code == 400
    assert unauthorized.json()["detail"]["code"] == "UNAUTHORIZED"


def test_dlq_endpoints_empty_and_missing(client):
    http, system = client
    assert http.get("/events/dlq").json()["deadLetters"] == []
    assert http.get("/events/dlq/nope").status_code == 404


def test_graph_endpoint(client):
    http, _ = client
    graph = http.get("/events/graph", params={"correlationId": "c1"}).json()
    assert len(graph["nodes"]) == 1


def test_create_rule_unknown_action_is_400(client):
    http, _ = client
    response = http.post("/events/rules", json={
        "name": "bad", "eventType": "task.completed", "action": "explode",
    })
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_ACTION"
