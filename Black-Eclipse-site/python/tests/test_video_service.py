"""The video job layer through the Execution Fabric: queue -> track -> cancel ->
recover, draft/final renders, the inspection gate and Artifact Center
registration (fake worker; no Rust, no FFmpeg)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from harness.video.models import VideoError
from harness.video.service import set_video_service

from fabric_helpers import wait_terminal
from video_fakes import make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    yield make_video_env(tmp_path, monkeypatch)
    set_video_service(None)


def test_projects_create_get_and_validate(env):
    service = env["service"]
    project = service.create_project(name="Title Card")
    assert project["id"].startswith("vprj_") and project["kind"] == "title_card"
    assert service.get_project(project["id"])["name"] == "Title Card"
    assert [p["id"] for p in service.list_projects()] == [project["id"]]
    report = service.validate_project(project["id"])
    assert report["valid"] is True and report["problems"] == []
    with pytest.raises(VideoError) as exc:
        service.create_project(name="X", kind="unknown_kind")
    assert exc.value.code == "UNSUPPORTED_PROJECT_KIND"


def test_validate_reports_a_missing_binary(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch, worker_bin=str(tmp_path / "missing.exe"))
    set_video_service(None)
    service = env["service"]
    project = service.create_project(name="Broken")
    report = service.validate_project(project["id"])
    assert report["valid"] is False
    assert any("not built" in problem for problem in report["problems"])


def test_render_draft_end_to_end(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Title Card")

    async def scenario():
        await manager.start()
        submitted = await service.render_draft(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    submitted, job = asyncio.run(scenario())
    assert submitted["mode"] == "draft" and submitted["projectId"] == project["id"]
    assert job["status"] == "SUCCEEDED", job
    output = job["output"]
    assert output["status"] == "completed" and output["mode"] == "draft"
    assert output["artifact"] is None
    assert Path(output["outputPath"]).is_file()
    assert output["inspection"]["ok"] is True
    assert output["inspection"]["checkedFrames"] == 39
    assert Path(output["reportPath"]).is_file()
    assert job["progress"] == pytest.approx(1.0)
    assert service.get_job(job["id"])["status"] == "SUCCEEDED"
    assert [j["id"] for j in service.list_jobs(project_id=project["id"])] == [job["id"]]


def test_render_final_registers_an_artifact(env):
    service, manager, artifacts = env["service"], env["manager"], env["artifacts"]
    project = service.create_project(name="Title Card")

    async def scenario():
        await manager.start()
        submitted = await service.render_final(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    artifact_id = job["output"]["artifact"]["id"]
    artifact = artifacts.get(artifact_id)
    assert artifact.category.value == "video"
    assert artifact.name == "Title Card.mp4"
    assert artifact.size_bytes == Path(job["output"]["outputPath"]).stat().st_size
    assert artifact.metadata["videoJobId"] == job["id"]
    assert artifact.metadata["mode"] == "final"
    surfaced = service.get_artifact(artifact_id)
    assert surfaced.get("id") == artifact_id


def test_inspection_findings_fail_the_render(env, monkeypatch):
    service, manager = env["service"], env["manager"]
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    project = service.create_project(name="Clipped")

    async def scenario():
        await manager.start()
        submitted = await service.render_draft(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "FAILED"
    assert job["errorClass"] == "INSPECTION_FAILED"
    assert "clipped" in (job["error"] or "")


def test_inspect_video_by_job_and_by_project(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Title Card")

    async def scenario():
        await manager.start()
        rendered = await service.render_draft(project["id"])
        await wait_terminal(manager, rendered["jobId"], timeout=30)
        by_job = await service.inspect_video(job_id=rendered["jobId"])
        inspected = await wait_terminal(manager, by_job["jobId"], timeout=30)
        by_project = await service.inspect_video(project_id=project["id"])
        latest = await wait_terminal(manager, by_project["jobId"], timeout=30)
        await manager.stop()
        return inspected, latest

    inspected, latest = asyncio.run(scenario())
    for job in (inspected, latest):
        assert job["status"] == "SUCCEEDED", job
        assert job["output"]["ok"] is True
        assert job["output"]["checkedFrames"] == 39
    with pytest.raises(VideoError) as exc:
        asyncio.run(service.inspect_video())
    assert exc.value.code == "INVALID_INPUT"


def test_cancel_a_running_job(env, monkeypatch):
    service, manager = env["service"], env["manager"]
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "sleep")
    project = service.create_project(name="Long")

    async def scenario():
        await manager.start()
        submitted = await service.render_draft(project["id"])
        for _ in range(500):
            job = manager.get(submitted["jobId"])
            if job and job["status"] == "RUNNING":
                break
            await asyncio.sleep(0.02)
        started = time.monotonic()
        cancelled = await service.cancel_job(submitted["jobId"])
        assert cancelled["cancelled"] is True
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job, time.monotonic() - started

    job, elapsed = asyncio.run(scenario())
    assert job["status"] == "CANCELLED"
    assert elapsed < 15


def test_recovery_after_a_worker_restart(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Recover")

    async def scenario():
        submitted = await service.render_draft(project["id"])  # queued; no worker runs yet
        # Simulate a worker that claimed the job, then died (same recipe the
        # Fabric worker tests use): force the lease to lapse, then recover.
        manager._store.claim_job(
            ["video"], worker_id="dead", worker_kind="video", lease_seconds=5
        )
        manager._store.update_job(submitted["jobId"], leaseExpiresAt=time.time() - 1)
        recovered = await manager.recover()
        assert submitted["jobId"] in recovered
        await manager.start()  # a fresh boot consumes the requeued job
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    assert job["attempts"] >= 2
    assert Path(job["output"]["outputPath"]).is_file()
