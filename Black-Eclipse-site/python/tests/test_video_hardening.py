"""Phase 8 hardening: workspace GC, per-project queue caps, worker concurrency.

The video workspace grows by design; these tests pin that growth is bounded
(old job dirs pruned, `projects/` untouched), that a runaway submit loop is
refused honestly (`TOO_MANY_PENDING`), and that the dedicated worker serializes
renders at its configured concurrency.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from harness.video.config import VideoConfig
from harness.video.fabric import build_video_worker
from harness.video.gc import prune_video_workspace
from harness.video.models import VideoError
from harness.video.service import set_video_service

from fabric_helpers import wait_terminal
from video_fakes import make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    yield make_video_env(tmp_path, monkeypatch)
    set_video_service(None)


def _spec(title: str = "Bounded") -> dict:
    return {
        "schemaVersion": 2,
        "format": "landscape",
        "scenes": [{"type": "intro", "durationSeconds": 2, "title": title}],
    }


def _job_dir(root: Path, name: str, *, size: int = 1024, mtime: float) -> Path:
    path = root / "jobs" / name
    path.mkdir(parents=True)
    (path / "report.json").write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


# ── workspace GC ─────────────────────────────────────────────────────────────


def test_prune_keeps_the_newest_and_removes_the_oldest(tmp_path):
    config = VideoConfig(
        video_root=str(tmp_path / "video"), gc_keep_jobs=2, gc_max_total_mb=64
    )
    root = config.resolve_video_root()
    for index in range(5):
        _job_dir(root, f"job_{index}", mtime=1000 + index)
    (root / "projects").mkdir(parents=True)
    (root / "projects" / "vprj_x.json").write_text("{}", encoding="utf-8")

    result = prune_video_workspace(config)

    assert sorted(result["removed"]) == ["job_0", "job_1", "job_2"]
    assert result["kept"] == 2
    assert (root / "jobs" / "job_3").is_dir() and (root / "jobs" / "job_4").is_dir()
    # Durable user-facing data is never touched.
    assert (root / "projects" / "vprj_x.json").is_file()


def test_prune_enforces_the_byte_budget_but_keeps_the_newest(tmp_path):
    config = VideoConfig(
        video_root=str(tmp_path / "video"), gc_keep_jobs=10, gc_max_total_mb=1
    )
    root = config.resolve_video_root()
    for index in range(3):
        _job_dir(root, f"job_{index}", size=600 * 1024, mtime=1000 + index)

    result = prune_video_workspace(config)

    assert result["removed"] and result["totalBytes"] <= 1024 * 1024
    assert (root / "jobs" / "job_2").is_dir()  # the newest render is never pruned


def test_prune_is_a_noop_without_a_workspace(tmp_path):
    result = prune_video_workspace(VideoConfig(video_root=str(tmp_path / "video")))
    assert result["removed"] == [] and result["kept"] == 0


def test_prune_can_be_disabled(tmp_path):
    config = VideoConfig(video_root=str(tmp_path / "video"), gc_enabled=False)
    root = config.resolve_video_root()
    (root / "jobs" / "job_1").mkdir(parents=True)
    result = prune_video_workspace(config)
    assert result["skipped"] == "disabled"
    assert (root / "jobs" / "job_1").is_dir()


# ── queue depth (per project) ────────────────────────────────────────────────


def test_queue_depth_cap_refuses_the_next_submit(env):
    service = env["service"]
    project = service.create_project(name="Capped", kind="storyboard", spec=_spec())
    cap = service._config.max_pending_per_project

    for _ in range(cap):
        asyncio.run(service.render_draft(project["id"]))

    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_draft(project["id"]))
    assert exc.value.code == "TOO_MANY_PENDING"
    assert str(cap) in exc.value.message

    # Previews share the same per-project budget.
    with pytest.raises(VideoError) as exc:
        asyncio.run(service.preview_project(project["id"]))
    assert exc.value.code == "TOO_MANY_PENDING"


def test_queue_depth_is_per_project(env):
    service = env["service"]
    busy = service.create_project(name="Busy", kind="storyboard", spec=_spec("Busy"))
    free = service.create_project(name="Free", kind="storyboard", spec=_spec("Free"))
    for _ in range(service._config.max_pending_per_project):
        asyncio.run(service.render_draft(busy["id"]))
    handle = asyncio.run(service.render_draft(free["id"]))
    assert handle["projectId"] == free["id"]


def test_terminal_jobs_free_their_slots(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Drained", kind="storyboard", spec=_spec())
    cap = service._config.max_pending_per_project

    async def scenario():
        await manager.start()
        submitted = [await service.render_draft(project["id"]) for _ in range(cap)]
        for handle in submitted:
            job = await wait_terminal(manager, handle["jobId"], timeout=30)
            assert job["status"] == "SUCCEEDED", job
        # Every job is terminal, so the budget is free again.
        handle = await service.render_draft(project["id"])
        await manager.stop()
        return handle

    handle = asyncio.run(scenario())
    assert handle["projectId"] == project["id"]


# ── concurrency + advertised limits ──────────────────────────────────────────


def test_renders_serialize_at_concurrency_one(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "slow")
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Serial", kind="storyboard", spec=_spec())

    async def scenario():
        await manager.start()
        submitted = [await service.render_draft(project["id"]) for _ in range(3)]
        jobs = [await wait_terminal(manager, h["jobId"], timeout=30) for h in submitted]
        await manager.stop()
        return jobs

    jobs = asyncio.run(scenario())
    assert all(job["status"] == "SUCCEEDED" for job in jobs)
    ordered = sorted(jobs, key=lambda job: job["startedAt"])
    for previous, following in zip(ordered, ordered[1:]):
        # One worker slot: the next render starts only after the previous ends.
        assert following["startedAt"] >= previous["completedAt"] - 0.05


def test_worker_honours_the_configured_concurrency():
    worker = build_video_worker(None, VideoConfig(max_concurrent=2))
    assert worker is not None and worker.concurrency == 2


def test_capabilities_advertise_the_resource_limits(env):
    limits = env["service"].capabilities()["limits"]
    assert limits["maxPendingPerProject"] >= 1
    assert limits["gcKeepJobs"] >= 1
    assert limits["gcMaxTotalMb"] >= 1
