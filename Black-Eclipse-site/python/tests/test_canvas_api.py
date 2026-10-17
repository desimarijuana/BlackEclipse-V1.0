"""Canvas API tests — create, save (revision guard), restore, honest AI failure."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-canvas-api-"), "agent-memory.db"),
)
os.environ.setdefault(
    "HARNESS_ARTIFACT_ROOT",
    os.path.join(tempfile.mkdtemp(prefix="be-canvas-files-"), "artifacts"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def test_canvas_create_save_conflict_restore():
    created = client.post("/canvas/artifacts", json={
        "name": "Implementation Report",
        "kind": "document",
        "content": "# Introduction\n\nBody.\n",
    })
    assert created.status_code == 201, created.text
    snap = created.json()
    artifact_id = snap["artifactId"]
    assert snap["version"] == 1
    assert snap["name"].endswith(".md")

    fetched = client.get(f"/canvas/artifacts/{artifact_id}")
    assert fetched.status_code == 200
    assert fetched.json()["content"].startswith("# Introduction")

    saved = client.put(f"/canvas/artifacts/{artifact_id}", json={
        "baseVersion": 1,
        "content": "# Introduction\n\nBody, edited.\n",
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2

    stale = client.put(f"/canvas/artifacts/{artifact_id}", json={
        "baseVersion": 1, "content": "should not win",
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "CANVAS_CONFLICT"
    assert stale.json()["detail"]["currentVersion"] == 2

    restored = client.post(f"/canvas/artifacts/{artifact_id}/restore", json={
        "baseVersion": 2, "version": 1,
    })
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 3
    assert restored.json()["content"] == "# Introduction\n\nBody.\n"


def test_canvas_edits_requires_model_configuration():
    created = client.post("/canvas/artifacts", json={"name": "Note", "kind": "document", "content": "# N"})
    artifact_id = created.json()["artifactId"]
    response = client.post(f"/canvas/artifacts/{artifact_id}/edits", json={
        "baseVersion": 1, "instruction": "improve it", "mode": "edit",
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CANVAS_MODEL_UNAVAILABLE"


def test_canvas_missing_artifact_404():
    assert client.get("/canvas/artifacts/does-not-exist").status_code == 404
