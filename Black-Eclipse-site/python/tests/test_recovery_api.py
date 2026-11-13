"""The recovery API routes: operator-gated reads over the real engine."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "ECLIPSE_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-recovery-api-em-"), "eclipse-memory.db"),
)
os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-recovery-api-am-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
os.environ.setdefault("HARNESS_SEARCH_WARM_INDEX", "0")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_health_reports_engine(client):
    res = client.get("/recovery/health")
    assert res.status_code == 200
    assert res.json()["status"] in ("ok", "disabled")


def test_boot_subscribed_to_the_event_bus(client):
    from harness.deps import service

    system = getattr(service, "events", None) or getattr(service, "_event_system", None)
    assert system is not None
    consumers = {s["consumerId"] for s in system.subscriptions()}
    assert "recovery.incidents" in consumers


def test_incidents_round_trip(client):
    from harness.deps import service

    engine = service.recovery
    assert engine is not None
    recorded = engine.record_failure(
        code="TOOL_TIMEOUT", message="timed out", subsystem="tools", source="tool", task_id="api-t1"
    )
    incident_id = recorded["incidentId"]

    listing = client.get("/recovery/incidents").json()
    assert any(i["id"] == incident_id for i in listing["incidents"])

    detail = client.get(f"/recovery/incidents/{incident_id}").json()
    assert detail["incident"]["kind"] == "timeout"
    assert "attempts" in detail


def test_missing_incident_is_404(client):
    assert client.get("/recovery/incidents/nope").status_code == 404


def test_discover_route(client):
    res = client.get("/recovery/discover", params={"query": "financial metrics"})
    assert res.status_code == 200
    body = res.json()
    assert "matches" in body and "plan" in body


def test_diagnose_route_reports_a_diagnosis(client):
    from harness.deps import service

    recorded = service.recovery.record_failure(
        code="ModuleNotFoundError", message="no module named 'x'", source="tool", task_id="diag-t1"
    )
    res = client.post(
        f"/recovery/incidents/{recorded['incidentId']}/diagnose",
        json={"dependency_missing": True},
    )
    assert res.status_code == 200
    assert res.json()["diagnosis"]["kind"] == "dependency"


def test_new_mutations_are_operator_gated(client):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.post("/recovery/promote", json={}).status_code == 403
        assert remote.post("/recovery/incidents/x/diagnose", json={}).status_code == 403
        assert remote.put("/recovery/envelope", json={}).status_code == 403


def test_envelope_round_trip(client):
    res = client.get("/recovery/envelope")
    assert res.status_code == 200
    body = res.json()["envelope"]
    assert "actionClasses" in body and "riskCeiling" in body

    updated = client.put("/recovery/envelope", json={
        "enabled": True,
        "actionClasses": ["retry", "fix_dependency"],
        "riskCeiling": "medium",
    })
    assert updated.status_code == 200
    classes = updated.json()["envelope"]["actionClasses"]
    assert "fix_dependency" in classes


def test_operations_route(client):
    res = client.get("/recovery/operations")
    assert res.status_code == 200
    assert "operations" in res.json()


def test_health_reports_autonomy(client):
    body = client.get("/recovery/health").json()
    assert "autonomy" in body


def test_approve_route(client):
    import uuid

    from harness.deps import service

    recorded = service.recovery.record_failure(
        code="provider_unavailable", message="down", source="provider",
        task_id=f"appr-{uuid.uuid4()}",
    )
    incident_id = recorded["incidentId"]
    assert client.get(f"/recovery/incidents/{incident_id}/approvals").json()["approvals"] == []
    res = client.post(
        f"/recovery/incidents/{incident_id}/approve",
        json={"strategy": "substitute_provider", "approvedBy": "alice"},
    )
    assert res.status_code == 200
    approvals = client.get(f"/recovery/incidents/{incident_id}/approvals").json()["approvals"]
    assert approvals and approvals[0]["strategy"] == "substitute_provider"
    # A missing strategy is a 400.
    assert client.post(f"/recovery/incidents/{incident_id}/approve", json={}).status_code == 400


def test_approve_is_operator_gated(client):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.post("/recovery/incidents/x/approve", json={"strategy": "retry"}).status_code == 403


def test_reproduce_route(client):
    from harness.recovery.taxonomy import FailureKind

    from harness.deps import service

    recorded = service.recovery.record_failure(
        code="TOOL_TIMEOUT", message="timed out", source="tool", task_id="repro-t1"
    )
    incident_id = recorded["incidentId"]
    service.recovery.register_reproducer(FailureKind.TIMEOUT, "re-run", lambda _f: True)
    res = client.post(f"/recovery/incidents/{incident_id}/reproduce")
    assert res.status_code == 200
    assert res.json()["reproduction"]["reproduced"] is True


def test_live_event_is_captured_end_to_end(client):
    from harness.deps import service

    system = getattr(service, "events", None) or getattr(service, "_event_system", None)
    assert system is not None
    assert getattr(client, "portal", None) is not None
    client.portal.call(
        system.publish,
        "tool.failed",
        {"code": "NETWORK_ERROR", "tool": "search", "message": "connection reset"},
    )
    listing = client.get("/recovery/incidents").json()["incidents"]
    assert any(i["kind"] == "network" and i["source"] == "event" for i in listing)


def test_outcome_mutation_is_operator_gated(client):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        res = remote.post("/recovery/incidents/whatever/outcome", json={"outcome": "succeeded"})
        assert res.status_code == 403


def test_guardrail_reset_route_exists_and_requires_a_known_run(client):
    res = client.post("/runs/not-a-real-run/guardrail-reset")
    assert res.status_code in (401, 403, 404)
