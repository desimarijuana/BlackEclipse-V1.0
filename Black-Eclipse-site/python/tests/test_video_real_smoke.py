"""Opt-in real end-to-end: the actual fframes worker binary and FFmpeg DLLs.

Enable with ``HARNESS_VIDEO_IT=1`` (and ``FFMPEG_DIR`` set). Everything here is
skipped otherwise. This is the Phase 2 acceptance proof: a real draft render,
a real final render registered into the Artifact Center, and a real frame
inspection — all through the Execution Fabric job layer.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from harness.artifacts.service import ArtifactService
from harness.artifacts.storage import LocalArtifactStorage
from harness.artifacts.store import ArtifactStore
from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry
from harness.video.config import VideoConfig
from harness.video.fabric import build_video_worker
from harness.video.projects import VideoProjectStore
from harness.video.runner import VideoRunner
from harness.video.service import VideoService, set_video_service
from harness.video.tools import register_video_tools

from fabric_helpers import make_manager, wait_terminal

pytestmark = pytest.mark.skipif(
    os.environ.get("HARNESS_VIDEO_IT") != "1",
    reason="opt-in: set HARNESS_VIDEO_IT=1 (needs the built rust worker + FFmpeg)",
)


def _make(tmp_path: Path, *, with_artifacts: bool):
    config = VideoConfig(
        video_root=str(tmp_path / "video"),
        ffmpeg_dir=os.environ.get("FFMPEG_DIR", ""),
    )
    if not config.resolve_worker_bin().is_file():
        pytest.skip("the fframes worker binary is not built")
    aml = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    manager = make_manager(aml)
    manager.register_worker(build_video_worker(None, config))
    artifacts = None
    provider = None
    if with_artifacts:
        artifacts = ArtifactService(
            ArtifactStore(aml), LocalArtifactStorage(root=tmp_path / "artifacts")
        )
        provider = lambda: artifacts  # noqa: E731
    service = VideoService(
        config=config,
        runner=VideoRunner(config),
        projects=VideoProjectStore(config.resolve_video_root() / "projects"),
        artifact_provider=provider,
        manager_provider=lambda: manager,
    )
    set_video_service(service)
    return service, manager, artifacts


def test_real_draft_render_through_the_fabric(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    service, manager, _ = _make(tmp_path, with_artifacts=False)
    try:
        project = service.create_project(name="Phase 2 Smoke")
        assert service.validate_project(project["id"])["valid"] is True

        async def scenario():
            await manager.start()
            submitted = await service.render_draft(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=180)
            await manager.stop()
            return job

        job = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        output = job["output"]
        assert output["inspection"]["ok"] is True
        assert output["width"] == 960 and output["height"] == 540  # draft half-res
        assert output["sizeBytes"] > 10_000
        assert Path(output["outputPath"]).is_file()
    finally:
        set_video_service(None)


def test_real_final_render_registers_an_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    service, manager, artifacts = _make(tmp_path, with_artifacts=True)
    try:
        project = service.create_project(name="Phase 2 Final")

        async def scenario():
            await manager.start()
            submitted = await service.render_final(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=300)
            inspect = await service.inspect_video(job_id=job["id"])
            inspected = await wait_terminal(manager, inspect["jobId"], timeout=180)
            await manager.stop()
            return job, inspected

        job, inspected = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        output = job["output"]
        assert output["width"] == 1920 and output["height"] == 1080
        assert output["inspection"]["ok"] is True
        artifact = artifacts.get(output["artifact"]["id"])
        assert artifact.category.value == "video"
        assert artifact.metadata["mode"] == "final"
        assert inspected["status"] == "SUCCEEDED"
        assert inspected["output"]["ok"] is True
    finally:
        set_video_service(None)


def test_real_tool_workflow(tmp_path, monkeypatch):
    """The Phase 3 acceptance: the whole workflow through the registered tools."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    service, manager, _ = _make(tmp_path, with_artifacts=False)
    registry = ToolRegistry()
    register_video_tools(registry)
    try:
        _text, caps = asyncio.run(registry.get("video_capabilities").handler({}, None))
        assert caps["ready"] is True
        _text, created = asyncio.run(
            registry.get("video_create_project").handler({"name": "Tool Workflow"}, None)
        )
        project_id = created["project"]["id"]

        async def scenario():
            await manager.start()
            _text, draft = await registry.get("video_render_draft").handler(
                {"projectId": project_id}, None
            )
            job_id = draft["job"]["jobId"]
            job = await wait_terminal(manager, job_id, timeout=180)
            status_text, _status = await registry.get("video_job_status").handler(
                {"jobId": job_id}, None
            )
            _text, inspection = await registry.get("video_inspect").handler(
                {"jobId": job_id}, None
            )
            checked = await wait_terminal(manager, inspection["job"]["jobId"], timeout=120)
            await manager.stop()
            return job, status_text, checked

        job, status_text, checked = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        assert "SUCCEEDED" in status_text
        assert checked["status"] == "SUCCEEDED" and checked["output"]["ok"] is True
    finally:
        set_video_service(None)
