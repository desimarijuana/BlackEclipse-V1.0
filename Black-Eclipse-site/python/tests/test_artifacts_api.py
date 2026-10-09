"""Artifact Center API tests — the FastAPI route group over the service."""

from __future__ import annotations

import base64
import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-artifacts-api-"), "agent-memory.db"),
)
os.environ.setdefault(
    "HARNESS_ARTIFACT_ROOT",
    os.path.join(tempfile.mkdtemp(prefix="be-artifacts-files-"), "artifacts"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def test_register_list_get_download():
    register = client.post("/artifacts", json={
        "name": "api-report.csv",
        "contentBase64": base64.b64encode(b"col1,col2\n1,2\n").decode(),
        "tags": ["api"],
    })
    assert register.status_code == 200, register.text
    artifact = register.json()["artifact"]
    artifact_id = artifact["id"]
    assert artifact["category"] == "dataset"

    listing = client.get("/artifacts", params={"q": "api-report"})
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1

    detail = client.get(f"/artifacts/{artifact_id}")
    assert detail.status_code == 200
    assert detail.json()["artifact"]["name"] == "api-report.csv"

    download = client.get(f"/artifacts/{artifact_id}/download")
    assert download.status_code == 200
    assert download.content == b"col1,col2\n1,2\n"
    assert "attachment" in download.headers["content-disposition"]

    preview = client.get(f"/artifacts/{artifact_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["preview"]["kind"] == "table"


def test_stats_and_tags():
    stats = client.get("/artifacts/stats")
    assert stats.status_code == 200
    assert "total" in stats.json()["stats"]
    tags = client.get("/artifacts/tags")
    assert tags.status_code == 200
    assert "api" in tags.json()["tags"]


def test_missing_artifact_404():
    assert client.get("/artifacts/does-not-exist").status_code == 404


def test_source_traversal_403():
    response = client.post("/artifacts", json={
        "name": "hosts", "sourcePath": "../../../../etc/hosts",
    })
    assert response.status_code == 403


def test_lifecycle_endpoints():
    created = client.post("/artifacts", json={"name": "life.txt", "contentBase64": "eA=="}).json()
    artifact_id = created["artifact"]["id"]
    assert client.post(f"/artifacts/{artifact_id}/archive").status_code == 200
    assert client.get("/artifacts", params={"includeArchived": "true"}).json()["total"] >= 1
    assert client.post(f"/artifacts/{artifact_id}/restore").status_code == 200
    assert client.delete(f"/artifacts/{artifact_id}").status_code == 200
    assert client.post(f"/artifacts/{artifact_id}/purge").status_code == 200
