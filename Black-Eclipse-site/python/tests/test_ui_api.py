"""UI Engineering API tests — the FastAPI route group over the service."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-ui-api-"), "agent-memory.db"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def test_application_map_and_components():
    app_map = client.get("/ui/application-map")
    assert app_map.status_code == 200, app_map.text
    assert "capabilities" in app_map.json()

    caps = client.get("/ui/capabilities")
    assert caps.status_code == 200
    assert caps.json()["componentCount"] >= 1

    components = client.get("/ui/components", params={"text": "table"})
    assert components.status_code == 200
    assert any(c["id"] == "data-table" for c in components.json()["components"])

    single = client.get("/ui/components/metric-card")
    assert single.status_code == 200
    assert single.json()["component"]["category"] == "metrics"


def test_create_page_add_widget_and_read_back():
    created = client.post("/ui/blueprints", json={"title": "API Desk"})
    assert created.status_code == 200, created.text
    blueprint_id = created.json()["blueprint"]["id"]

    added = client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={
        "componentId": "metric-card", "instanceId": "m1",
    })
    assert added.status_code == 200, added.text
    assert added.json()["blueprint"]["revision"] == 2

    current = client.get(f"/ui/blueprints/{blueprint_id}/current")
    assert current.status_code == 200
    assert current.json()["instances"][0]["componentId"] == "metric-card"

    layout = client.get(f"/ui/blueprints/{blueprint_id}/layout")
    assert layout.status_code == 200
    assert layout.json()["revision"] == 2


def test_unknown_component_is_rejected():
    blueprint_id = client.post("/ui/blueprints", json={"title": "Reject"}).json()["blueprint"]["id"]
    resp = client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={"componentId": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "UI_OPERATION_INVALID"


def test_missing_blueprint_404():
    assert client.get("/ui/blueprints/does-not-exist").status_code == 404
    assert client.post("/ui/blueprints/missing/widgets", json={"componentId": "metric-card"}).status_code == 404


def test_preview_and_history():
    blueprint_id = client.post("/ui/blueprints", json={"title": "Preview"}).json()["blueprint"]["id"]
    client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={"componentId": "metric-card", "instanceId": "m1"})

    preview = client.post(f"/ui/blueprints/{blueprint_id}/preview", json={
        "ops": [{"op": "add_widget", "componentId": "data-table", "instanceId": "d1"}],
    })
    assert preview.status_code == 200
    assert preview.json()["nextRevision"] == preview.json()["currentRevision"] + 1

    history = client.get(f"/ui/blueprints/{blueprint_id}/history")
    assert history.status_code == 200
    assert len(history.json()["revisions"]) >= 2


def test_reorder_and_classify():
    blueprint_id = client.post("/ui/blueprints", json={"title": "Order"}).json()["blueprint"]["id"]
    client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={"componentId": "metric-card", "instanceId": "a"})
    client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={"componentId": "data-table", "instanceId": "b"})
    reorder = client.post(f"/ui/blueprints/{blueprint_id}/widgets/b/reorder", json={"toIndex": 0})
    assert reorder.status_code == 200
    assert reorder.json()["blueprint"]["revision"] == 4

    compose = client.post("/ui/classify", json={"text": "move the latency chart below the timeline"})
    assert compose.status_code == 200
    assert compose.json()["mode"] == "compose"

    engineer = client.post("/ui/classify", json={"text": "build a new backend API endpoint"})
    assert engineer.json()["mode"] == "engineer"


def test_engineering_workflow():
    started = client.post("/ui/engineering", json={"text": "build a new plugin with a backend API endpoint"})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["created"] is True and body["mode"] == "engineer"
    task_id = body["taskId"]
    plan_id = body["planId"]

    status = client.get(f"/ui/engineering/{plan_id}")
    assert status.status_code == 200
    assert status.json()["plan"]["plan"]["id"] == plan_id

    reg = client.post(f"/ui/engineering/{task_id}/components", json={
        "spec": {"id": "eng-widget", "displayName": "Eng Widget", "category": "custom"},
    })
    assert reg.status_code == 200, reg.text
    assert reg.json()["componentId"] == "eng-widget"

    compose = client.post("/ui/engineering", json={"text": "add a widget"})
    assert compose.status_code == 200
    assert compose.json()["created"] is False


def test_export_import_roundtrip():
    blueprint_id = client.post("/ui/blueprints", json={"title": "Portable"}).json()["blueprint"]["id"]
    client.post(f"/ui/blueprints/{blueprint_id}/widgets", json={"componentId": "metric-card", "instanceId": "m1"})

    exported = client.get(f"/ui/blueprints/{blueprint_id}/export")
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    assert payload["kind"] == "eclipse.ui.blueprint"

    imported = client.post("/ui/blueprints/import", json={"blueprint": payload["blueprint"]})
    assert imported.status_code == 200, imported.text
    new_id = imported.json()["blueprint"]["id"]
    assert new_id != blueprint_id

    current = client.get(f"/ui/blueprints/{new_id}/current")
    assert current.status_code == 200
    assert current.json()["instances"][0]["componentId"] == "metric-card"
