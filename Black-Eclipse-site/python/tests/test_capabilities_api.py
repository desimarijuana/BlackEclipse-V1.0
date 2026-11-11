"""The generated-capability routes: read the durable record, operator actions."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "ECLIPSE_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-cap-api-em-"), "eclipse-memory.db"),
)
os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-cap-api-am-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
os.environ.setdefault("HARNESS_SEARCH_WARM_INDEX", "0")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _seed(version: str = "1.0.0", status: str = "active", *, root: Path, capability_id: str):
    from harness.capabilities.manifest import CapabilityManifest, CapabilityPort
    from harness.capabilities.store import CapabilityRecord, CapabilityStore
    from harness.deps import service

    manifest = CapabilityManifest(
        id=capability_id,
        version=version,
        kind="recipe",
        title="API test recipe",
        description="A recipe created by the capability API test.",
        inputs=[CapabilityPort(name="values", kind="series")],
        outputs=[CapabilityPort(name="sum", kind="scalar")],
        tests=["test_capability.py"],
        acceptance="The contract test passes.",
    )
    store = CapabilityStore(service.store)
    store.save_record(CapabilityRecord(
        capability_id=capability_id,
        version=version,
        kind="recipe",
        title=manifest.title,
        description=manifest.description,
        scope="workspace",
        status=status,
        manifest=manifest.to_dict(),
        source_digest="a" * 64,
        test_digest="b" * 64,
        test_status="verified",
        tests=["test_capability.py"],
        directory=str(root / ".black-eclipse" / "capabilities" / capability_id / version),
    ))
    return store


def test_builtins_route_is_a_read_only_catalogue(client):
    response = client.get("/capabilities/builtins")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["builtins"]}
    assert {"returns_series", "drawdown_profile", "correlation_matrix"} <= names
    assert body["count"] == len(body["builtins"])
    assert all(item["source"] == "builtin" for item in body["builtins"])
    assert all(item["kind"] == "recipe" for item in body["builtins"])
    assert all("inputs" in item for item in body["builtins"])


def test_read_list_detail_and_operator_actions(client, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    capability_id = "api_cap_" + uuid.uuid4().hex[:8]
    store = _seed(root=tmp_path, capability_id=capability_id)
    _seed("1.0.1", "disabled", root=tmp_path, capability_id=capability_id)

    listing = client.get("/capabilities")
    assert listing.status_code == 200
    rows = [row for row in listing.json()["capabilities"] if row["capabilityId"] == capability_id]
    assert len(rows) == 2
    assert all("usage" in row for row in rows)

    detail = client.get(f"/capabilities/{capability_id}")
    assert detail.status_code == 200
    assert len(detail.json()["versions"]) == 2

    deactivated = client.post(f"/capabilities/{capability_id}/deactivate", json={"version": "1.0.0"})
    assert deactivated.status_code == 200
    assert deactivated.json()["result"]["status"] == "disabled"

    activated = client.post(f"/capabilities/{capability_id}/activate", json={"version": "1.0.0"})
    assert activated.status_code == 200
    assert activated.json()["result"]["status"] == "active"

    rolled_back = client.post(f"/capabilities/{capability_id}/rollback", json={"version": "1.0.1"})
    assert rolled_back.status_code == 200
    assert rolled_back.json()["result"]["version"] == "1.0.1"

    retired = client.post(f"/capabilities/{capability_id}/remove")
    assert retired.status_code == 200
    assert retired.json()["result"]["status"] == "retired"
    assert store.get(capability_id, "1.0.1")["status"] == "retired"


def test_gap_offer_routes(client):
    from harness.deps import service
    from harness.gaps.service import GapService

    gaps = GapService(service.store)
    gap = gaps.record_tool_failure(
        "run_api_gap", tool="scaffold_kit", code="PROFILE_DENIED",
        need="turn this into a bot that runs every morning", reason="profile",
    )
    assert isinstance(gap, dict) and gap["state"] == "open"

    listing = client.get("/capabilities/gaps", params={"runId": "run_api_gap"})
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    assert body["gaps"][0]["offer"]["nextTool"] == "bot_create"

    summary = client.get("/capabilities/gaps/summary")
    assert summary.status_code == 200
    assert summary.json()["total"] >= 1

    accepted = client.post(f"/capabilities/gaps/{gap['gapId']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["result"]["state"] == "accepted"
    assert accepted.json()["result"]["actionPrompt"]
    # No durable task was attached to this gap, so the resume is reported
    # honestly rather than claimed.
    assert accepted.json()["result"]["resume"]["resumed"] is False


def test_unknown_capability_is_404(client):
    assert client.get("/capabilities/nope").status_code == 404
    assert client.post("/capabilities/nope/activate", json={}).status_code == 404
    assert client.post("/capabilities/nope/promote", json={}).status_code == 404
