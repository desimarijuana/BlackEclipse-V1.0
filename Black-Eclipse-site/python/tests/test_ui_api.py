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


def test_current_page_route_resolves_without_path_segment():
    created = client.post("/ui/blueprints", json={"title": "Main", "path": "/main"}).json()["blueprint"]["id"]
    by_id = client.get(f"/ui/blueprints/{created}/current")
    assert by_id.status_code == 200
    assert by_id.json()["blueprint"]["id"] == created

    by_path = client.get("/ui/current-page", params={"path": "/main"})
    assert by_path.status_code == 200, by_path.text
    body = by_path.json()
    assert body["resolution"] == "path"
    assert body["blueprint"]["id"] == created

    default = client.get("/ui/current-page")
    assert default.status_code == 200
    assert default.json()["blueprint"]["id"] == created


def test_page_icon_create_and_read_back():
    created = client.post("/ui/blueprints", json={"title": "Iconic", "icon": "wallet"}).json()["blueprint"]
    assert created["icon"] == "wallet"
    listed = client.get("/ui/blueprints", params={"q": "Iconic"}).json()["blueprints"]
    assert any(b["id"] == created["id"] and b["icon"] == "wallet" for b in listed)


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

    # Engineer -> Compose closure, end to end: the newly registered component is
    # discoverable, addable to a page, and the page verifies as renderable.
    catalog = client.get("/ui/components", params={"text": "eng"}).json()["components"]
    assert any(c["id"] == "eng-widget" for c in catalog)

    page_id = client.post("/ui/blueprints", json={"title": "Engineered"}).json()["blueprint"]["id"]
    added = client.post(f"/ui/blueprints/{page_id}/widgets", json={"componentId": "eng-widget", "instanceId": "e1"})
    assert added.status_code == 200, added.text

    verified = client.get(f"/ui/blueprints/{page_id}/verify")
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["renderable"] is True
    assert body["instances"][0]["componentId"] == "eng-widget"


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


def test_register_surfaces_and_map_them_separately_from_pages():
    payload = {
        "surfaces": [
            {
                "id": "memory",
                "label": "Eclipse Memory",
                "deepLink": "/?tab=memory",
                "tabs": [
                    {
                        "id": "memory.reviews",
                        "label": "Learning Reviews",
                        "deepLink": "/?tab=memory&sub=memory.reviews",
                    },
                ],
            },
        ],
    }
    registered = client.post("/ui/surfaces", json=payload)
    assert registered.status_code == 200, registered.text
    assert registered.json()["registered"] == 1

    app_map = client.get("/ui/application-map").json()
    assert any(s["id"] == "memory" for s in app_map["screens"])
    memory = next(s for s in app_map["screens"] if s["id"] == "memory")
    assert memory["tabs"][0]["deepLink"] == "/?tab=memory&sub=memory.reviews"
    # Saved pages remain their own list — never conflated with the screens.
    assert isinstance(app_map["pages"], list)

    # An empty batch must not wipe the inventory.
    empty = client.post("/ui/surfaces", json={"surfaces": []})
    assert empty.status_code == 200
    assert empty.json()["registered"] == 0
    assert any(s["id"] == "memory" for s in client.get("/ui/application-map").json()["screens"])
