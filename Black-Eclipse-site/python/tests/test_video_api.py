"""The native-video route group (Phase 7): the HTTP door the TS front door
proxies. Exercises the real FastAPI router over a stubbed `deps.service` whose
`.video` is the standard fake-worker environment, so every op goes through the
REAL VideoService + Execution Fabric (no Rust, no FFmpeg)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.video.models import VideoError
from harness.video.service import set_video_service

from fabric_helpers import wait_terminal
from video_fakes import make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch)

    from harness.routers import video as video_router

    class _Stub:
        pass

    stub = _Stub()
    stub.video = env["service"]
    monkeypatch.setattr(video_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(video_router.router)
    env["client"] = TestClient(app)
    env["stub"] = stub
    yield env
    set_video_service(None)


def _run_manager(env, job_id: str):
    manager = env["manager"]

    async def scenario():
        await manager.start()
        job = await wait_terminal(manager, job_id, timeout=30)
        await manager.stop()
        return job

    return asyncio.run(scenario())


_SPEC = {
    "schemaVersion": 2,
    "format": "landscape",
    "scenes": [
        {"type": "intro", "durationSeconds": 2, "title": "API"},
        {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "End"},
    ],
}


def test_capabilities(env):
    response = env["client"].get("/video/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["ready"] is True
    assert "storyboard" in body["projectKinds"]


def test_missing_layer_is_an_honest_503(env):
    del env["stub"].video
    response = env["client"].get("/video/capabilities")
    assert response.status_code == 503


def test_project_lifecycle_over_http(env):
    client = env["client"]
    created = client.post(
        "/video/projects", json={"name": "HTTP recap", "kind": "storyboard", "spec": _SPEC}
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    assert project["kind"] == "storyboard" and project["revision"] == 1

    listed = client.get("/video/projects")
    assert [p["id"] for p in listed.json()["projects"]] == [project["id"]]

    fetched = client.get(f"/video/projects/{project['id']}")
    assert fetched.json()["project"]["name"] == "HTTP recap"

    updated = client.put(f"/video/projects/{project['id']}", json={"name": "HTTP recap v2"})
    assert updated.json()["project"]["revision"] == 2

    validated = client.post(f"/video/projects/{project['id']}/validate")
    assert validated.status_code == 200 and validated.json()["valid"] is True


def test_invalid_spec_is_a_structured_400(env):
    response = env["client"].post(
        "/video/projects",
        json={"name": "Bad", "kind": "storyboard", "spec": {"schemaVersion": 2, "scenes": []}},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_SPEC" and "scenes" in detail["message"]


def test_render_and_job_reads_over_http(env):
    client = env["client"]
    project = client.post(
        "/video/projects", json={"name": "HTTP render", "kind": "storyboard", "spec": _SPEC}
    ).json()["project"]

    submitted = client.post(
        f"/video/projects/{project['id']}/render", json={"mode": "draft"}
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["job"]["jobId"]
    assert submitted.json()["job"]["projectName"] == "HTTP render"

    job = _run_manager(env, job_id)
    assert job["status"] == "SUCCEEDED", job

    fetched = client.get(f"/video/jobs/{job_id}")
    assert fetched.status_code == 200
    body = fetched.json()["job"]
    assert body["status"] == "SUCCEEDED"
    assert body["output"]["status"] == "completed"

    listed = client.get(f"/video/jobs?projectId={project['id']}")
    assert [j["jobId"] for j in listed.json()["jobs"]] == [job_id]


def test_preview_over_http(env):
    client = env["client"]
    project = client.post(
        "/video/projects", json={"name": "HTTP preview", "kind": "storyboard", "spec": _SPEC}
    ).json()["project"]

    submitted = client.post(f"/video/projects/{project['id']}/preview", json={"frames": True})
    assert submitted.status_code == 202
    job_id = submitted.json()["job"]["jobId"]
    job = _run_manager(env, job_id)
    assert job["status"] == "SUCCEEDED", job

    fetched = client.get(f"/video/jobs/{job_id}").json()["job"]
    assert fetched["output"]["action"] == "preview"
    assert [p["kind"] for p in fetched["output"]["previews"]] == ["strip", "frame", "frame"]


def test_final_render_associates_the_conversation_and_the_run(env):
    client, artifacts = env["client"], env["artifacts"]
    project = client.post(
        "/video/projects", json={"name": "Chat render", "kind": "storyboard", "spec": _SPEC}
    ).json()["project"]

    submitted = client.post(
        f"/video/projects/{project['id']}/render",
        json={"mode": "final", "conversationId": "chat_123"},
    )
    assert submitted.status_code == 202
    job = _run_manager(env, submitted.json()["job"]["jobId"])
    assert job["status"] == "SUCCEEDED", job
    artifact_id = job["output"]["artifact"]["id"]
    artifact = artifacts.get(artifact_id)
    assert artifact.conversation_id == "chat_123"
    assert artifact.category.value == "video"


def test_repair_refusals_are_structured_conflicts(env, monkeypatch):
    client = env["client"]
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    project = client.post(
        "/video/projects", json={"name": "Broken", "kind": "storyboard", "spec": _SPEC}
    ).json()["project"]

    submitted = client.post(f"/video/projects/{project['id']}/render", json={"mode": "draft"})
    failed = _run_manager(env, submitted.json()["job"]["jobId"])
    assert failed["status"] == "FAILED" and failed["errorClass"] == "INSPECTION_FAILED"

    refuse = client.post(
        f"/video/projects/{project['id']}/repair", json={"ofJobId": failed["id"]}
    )
    assert refuse.status_code == 409
    assert refuse.json()["detail"]["code"] == "REPAIR_REQUIRES_CHANGE"

    monkeypatch.delenv("FAKE_VIDEO_INSPECT")
    accepted = client.post(
        f"/video/projects/{project['id']}/repair",
        json={"ofJobId": failed["id"], "spec": _SPEC | {"scenes": [{"type": "intro", "durationSeconds": 2, "title": "Fixed"}]}},
    )
    assert accepted.status_code == 202, accepted.text
    repaired = _run_manager(env, accepted.json()["job"]["jobId"])
    assert repaired["status"] == "SUCCEEDED", repaired


def test_unknown_project_and_job_are_404(env):
    client = env["client"]
    missing = client.get("/video/projects/vprj_0000000000000000")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PROJECT_NOT_FOUND"

    job = client.get("/video/jobs/job_missing")
    assert job.status_code == 404
    assert job.json()["detail"]["code"] == "JOB_NOT_FOUND"


def test_cancel_unknown_job_reports_not_cancelled(env):
    """An unknown job id is refused HONESTLY: no cancellation happened."""
    response = env["client"].post("/video/jobs/job_missing/cancel")
    assert response.status_code == 200
    cancellation = response.json()["cancellation"]
    assert cancellation["cancelled"] is False
    assert cancellation["reason"] == "unknown job"


def test_inspect_over_http(env):
    client = env["client"]
    project = client.post(
        "/video/projects", json={"name": "Inspect me", "kind": "storyboard", "spec": _SPEC}
    ).json()["project"]
    submitted = client.post(f"/video/projects/{project['id']}/render", json={"mode": "draft"})
    rendered = _run_manager(env, submitted.json()["job"]["jobId"])

    inspected = client.post(f"/video/jobs/{rendered['id']}/inspect")
    assert inspected.status_code == 202
    job = _run_manager(env, inspected.json()["job"]["jobId"])
    assert job["status"] == "SUCCEEDED" and job["output"]["ok"] is True
