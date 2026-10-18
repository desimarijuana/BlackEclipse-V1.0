"""The video job layer through the Execution Fabric: queue -> track -> cancel ->
recover, draft/final renders, the inspection gate and Artifact Center
registration (fake worker; no Rust, no FFmpeg)."""

from __future__ import annotations

import asyncio
import json
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


# ── Phase 4: storyboard projects ──────────────────────────────────────────────


def _storyboard_spec(title: str = "Hello") -> dict:
    return {
        "schemaVersion": 2,
        "format": "landscape",
        "scenes": [
            {"type": "intro", "durationSeconds": 2, "title": title},
            {
                "type": "metric", "durationSeconds": 3, "transition": "fade", "title": "Metrics",
                "metrics": [{"label": "Price", "value": "42"}],
            },
            {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "Bye"},
        ],
    }


def test_storyboard_create_update_and_render(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Recap", kind="storyboard", spec=_storyboard_spec())
    assert project["kind"] == "storyboard" and project.get("revision") == 1
    assert service.validate_project(project["id"])["valid"] is True

    updated = service.update_project(project["id"], spec=_storyboard_spec("Revised"))
    assert updated["revision"] == 2
    assert updated["spec"]["scenes"][0]["title"] == "Revised"

    async def scenario():
        await manager.start()
        submitted = await service.render_draft(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    output = job["output"]
    assert Path(output["outputPath"]).is_file()
    spec_path = Path(output["outputPath"]).parent / "spec.json"
    assert spec_path.is_file()
    assert json.loads(spec_path.read_text(encoding="utf-8"))["scenes"][0]["title"] == "Revised"
    argv = json.loads(Path(str(output["outputPath"]) + ".argv.json").read_text(encoding="utf-8"))
    assert "--project" in argv
    assert argv[argv.index("--project") + 1].endswith("spec.json")


def test_storyboard_spec_validation_on_create_and_update(env):
    service = env["service"]
    with pytest.raises(VideoError) as exc:
        service.create_project(
            name="Bad", kind="storyboard",
            spec={"schemaVersion": 2, "format": "landscape", "scenes": []},
        )
    assert exc.value.code == "INVALID_SPEC" and "1-12 scenes" in exc.value.message
    with pytest.raises(VideoError) as exc:
        service.create_project(name="Title", kind="title_card", spec={"scenes": []})
    assert exc.value.code == "INVALID_INPUT"
    project = service.create_project(name="Ok", kind="storyboard", spec=_storyboard_spec())
    with pytest.raises(VideoError) as exc:
        service.update_project(project["id"], spec={"schemaVersion": 2})
    assert exc.value.code == "INVALID_SPEC"


def test_storyboard_inspect_carries_the_project_spec(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Inspectable", kind="storyboard", spec=_storyboard_spec())

    async def scenario():
        await manager.start()
        rendered = await service.render_draft(project["id"])
        await wait_terminal(manager, rendered["jobId"], timeout=30)
        inspected_handle = await service.inspect_video(job_id=rendered["jobId"])
        inspected = await wait_terminal(manager, inspected_handle["jobId"], timeout=30)
        await manager.stop()
        return inspected

    inspected = asyncio.run(scenario())
    assert inspected["status"] == "SUCCEEDED", inspected
    assert (inspected["input"].get("projectPath") or "").endswith("spec.json")
    assert inspected["output"]["ok"] is True


# ── Phase 5: evidence-bound data bindings ────────────────────────────────────


def _bound_spec() -> dict:
    return {
        "schemaVersion": 3,
        "format": "landscape",
        "scenes": [
            {"type": "intro", "durationSeconds": 2, "title": "Bound"},
            {
                "type": "metric", "durationSeconds": 4, "transition": "fade", "title": "Live",
                "metrics": [{"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}}],
            },
            {
                "type": "candlestick", "durationSeconds": 4, "transition": "fade",
                "title": "Candles", "symbol": "BTC-USD",
                "data": {"symbol": "BTC-USD", "interval": "1d", "count": 8},
            },
            {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "End"},
        ],
    }


def _run_bound_render(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Bound", kind="storyboard", spec=_bound_spec())

    async def scenario():
        await manager.start()
        submitted = await service.render_draft(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return project, job

    return asyncio.run(scenario())


def test_bound_storyboard_resolves_inside_the_render_job(tmp_path, monkeypatch):
    from video_fakes import FakeMarketProvider

    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider())
    try:
        project, job = _run_bound_render(env)
        assert job["status"] == "SUCCEEDED", job
        output = job["output"]
        evidence = output["evidence"]
        assert evidence["providers"] == ["yahoo", "yfinance"]
        assert evidence["stale"] is False and len(evidence["bindings"]) == 2
        assert output["inspection"]["ok"] is True
        resolved = json.loads(
            (Path(output["outputPath"]).parent / "spec.json").read_text(encoding="utf-8")
        )
        metric = resolved["scenes"][1]["metrics"][0]
        assert metric["value"] == "$68,240" and "source" not in metric
        assert resolved["scenes"][1]["evidence"]["stale"] is False
        assert len(resolved["scenes"][2]["candles"]) == 8
        assert resolved["scenes"][2]["evidence"]["sourceLine"].startswith("yfinance")
    finally:
        set_video_service(None)


def test_bound_without_provider_fails_the_job(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch)
    try:
        _project, job = _run_bound_render(env)
        assert job["status"] == "FAILED"
        assert job["errorClass"] == "DATA_UNAVAILABLE"
        assert "market data layer" in (job["error"] or "")
    finally:
        set_video_service(None)


def test_bound_provider_failure_fails_the_job(tmp_path, monkeypatch):
    from video_fakes import FakeMarketProvider

    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider(fail=True))
    try:
        _project, job = _run_bound_render(env)
        assert job["status"] == "FAILED"
        assert job["errorClass"] == "DATA_UNAVAILABLE"
        assert "fetch failed" in (job["error"] or "")
    finally:
        set_video_service(None)


def test_stale_binding_is_flagged_everywhere(tmp_path, monkeypatch):
    from video_fakes import FakeMarketProvider

    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider(stale=True))
    try:
        _project, job = _run_bound_render(env)
        assert job["status"] == "SUCCEEDED", job
        assert job["output"]["evidence"]["stale"] is True
        resolved = json.loads(
            (Path(job["output"]["outputPath"]).parent / "spec.json").read_text(encoding="utf-8")
        )
        assert resolved["scenes"][2]["evidence"]["stale"] is True
    finally:
        set_video_service(None)


def test_resolve_project_data_previews_without_rendering(tmp_path, monkeypatch):
    from video_fakes import FakeMarketProvider

    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider())
    try:
        service, manager = env["service"], env["manager"]
        project = service.create_project(name="Preview", kind="storyboard", spec=_bound_spec())
        manifest = asyncio.run(service.resolve_project_data(project["id"]))
        assert manifest["bindings"][0]["display"] == "$68,240"
        assert manifest["providers"] == ["yahoo", "yfinance"]
        assert service.list_jobs(project_id=project["id"]) == []

        plain = service.create_project(name="Plain", kind="storyboard", spec=_storyboard_spec())
        with pytest.raises(VideoError) as exc:
            asyncio.run(service.resolve_project_data(plain["id"]))
        assert exc.value.code == "NO_BINDINGS"
        title = service.create_project(name="Title")
        with pytest.raises(VideoError) as exc:
            asyncio.run(service.resolve_project_data(title["id"]))
        assert exc.value.code == "NO_BINDINGS"
    finally:
        set_video_service(None)
