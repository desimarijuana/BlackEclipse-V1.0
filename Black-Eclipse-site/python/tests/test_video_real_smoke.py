"""Opt-in real end-to-end: the actual fframes worker binary and FFmpeg DLLs.

Enable with ``HARNESS_VIDEO_IT=1`` (and ``FFMPEG_DIR`` set). Everything here is
skipped otherwise. This is the Phase 2 acceptance proof: a real draft render,
a real final render registered into the Artifact Center, and a real frame
inspection — all through the Execution Fabric job layer.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

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


def _make(tmp_path: Path, *, with_artifacts: bool, data_provider: Any = None):
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
        data_provider=(lambda: data_provider) if data_provider is not None else None,
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


def test_real_storyboard_render_and_inspect(tmp_path, monkeypatch):
    """Phase 4 acceptance: a real multi-scene storyboard renders and inspects."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    service, manager, _ = _make(tmp_path, with_artifacts=False)
    try:
        spec = {
            "schemaVersion": 2,
            "format": "landscape",
            "scenes": [
                {"type": "intro", "durationSeconds": 2, "title": "SMOKE TEST"},
                {
                    "type": "metric", "durationSeconds": 3, "transition": "fade",
                    "title": "Live Values",
                    "metrics": [{"label": "Value", "value": "42", "delta": "+1.0%"}],
                },
                {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "DONE"},
            ],
        }
        project = service.create_project(name="Storyboard Smoke", kind="storyboard", spec=spec)
        assert service.validate_project(project["id"])["valid"] is True

        async def scenario():
            await manager.start()
            submitted = await service.render_draft(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=180)
            inspected_handle = await service.inspect_video(job_id=job["id"])
            inspected = await wait_terminal(manager, inspected_handle["jobId"], timeout=180)
            await manager.stop()
            return job, inspected

        job, inspected = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        output = job["output"]
        assert output["durationSeconds"] == 7.0
        assert output["inspection"]["ok"] is True
        assert Path(output["outputPath"]).is_file()
        assert inspected["status"] == "SUCCEEDED", inspected
        assert inspected["output"]["ok"] is True
    finally:
        set_video_service(None)


def test_real_bound_storyboard_render(tmp_path, monkeypatch):
    """Phase 5 acceptance: a bound storyboard renders with resolved data,
    the evidence manifest, and the STALE flag carried end-to-end."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from video_fakes import FakeMarketProvider

    service, manager, _ = _make(
        tmp_path, with_artifacts=False, data_provider=FakeMarketProvider(stale=True)
    )
    try:
        spec = {
            "schemaVersion": 3,
            "format": "landscape",
            "scenes": [
                {"type": "intro", "durationSeconds": 2, "title": "BOUND SMOKE"},
                {
                    "type": "metric", "durationSeconds": 3, "transition": "fade",
                    "title": "Live Values",
                    "metrics": [
                        {"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}},
                    ],
                },
                {
                    "type": "candlestick", "durationSeconds": 3, "transition": "fade",
                    "title": "Candles", "symbol": "BTC-USD",
                    "data": {"symbol": "BTC-USD", "interval": "1d", "count": 8},
                },
                {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "END"},
            ],
        }
        project = service.create_project(name="Bound Smoke", kind="storyboard", spec=spec)
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
        evidence = output["evidence"]
        assert evidence["stale"] is True
        assert {entry["kind"] for entry in evidence["bindings"]} == {"value", "candles"}
        resolved = json.loads(
            (Path(output["outputPath"]).parent / "spec.json").read_text(encoding="utf-8")
        )
        assert resolved["scenes"][1]["metrics"][0]["value"] == "$68,240"
        assert resolved["scenes"][2]["evidence"]["stale"] is True
    finally:
        set_video_service(None)


def test_real_preview_catches_a_clipped_title(tmp_path, monkeypatch):
    """Phase 6 acceptance: a preview job renders a real contact sheet + one
    frame per scene, registers them as image artifacts, and DETECTS the known
    layout failure (a long title clipped by the canvas edge) before any
    render — without producing a video."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    service, manager, artifacts = _make(tmp_path, with_artifacts=True)
    try:
        spec = {
            "schemaVersion": 2,
            "format": "landscape",
            "scenes": [
                {"type": "intro", "durationSeconds": 3, "title": "W" * 80,
                 "subtitle": "A deliberately long title to provoke clipping"},
                {
                    "type": "metric", "durationSeconds": 3, "transition": "fade",
                    "title": "Values",
                    "metrics": [{"label": "Price", "value": "68,240", "delta": "+2.41%"}],
                },
                {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "END"},
            ],
        }
        project = service.create_project(name="Preview Smoke", kind="storyboard", spec=spec)

        async def scenario():
            await manager.start()
            submitted = await service.preview_project(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=300)
            await manager.stop()
            return job

        job = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        output = job["output"]
        assert output["action"] == "preview" and "artifact" not in output
        assert [preview["kind"] for preview in output["previews"]] == ["strip", "frame", "frame", "frame"]
        for preview in output["previews"]:
            assert Path(preview["path"]).is_file()
            assert preview["registered"] is True
            artifact = artifacts.get(preview["artifactId"])
            assert artifact.category.value == "image"
            assert artifact.mime_type == "image/png"
            assert artifact.metadata["videoJobId"] == job["id"]
        assert output["findingsErrors"] == 0 and output["findingsWarnings"] >= 1
        assert any(
            finding["kind"] == "text_clipped" for finding in output["findings"]
        ), output["findings"]
    finally:
        set_video_service(None)


def test_real_transient_retry_recovers_a_bound_render(tmp_path, monkeypatch):
    """Phase 6 acceptance: a transient market-data fetch failure is retried
    inside the render job (bounded) and the render still succeeds."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from video_fakes import FakeMarketProvider

    provider = FakeMarketProvider(fail_times=1)
    service, manager, _ = _make(tmp_path, with_artifacts=False, data_provider=provider)
    try:
        spec = {
            "schemaVersion": 3,
            "format": "landscape",
            "scenes": [{
                "type": "metric", "durationSeconds": 3, "title": "Live",
                "metrics": [
                    {"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}},
                ],
            }],
        }
        project = service.create_project(name="Retry Smoke", kind="storyboard", spec=spec)

        async def scenario():
            await manager.start()
            submitted = await service.render_draft(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=180)
            await manager.stop()
            return job

        job = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        retries = job["output"]["retries"]
        assert [entry["errorClass"] for entry in retries] == ["DATA_UNAVAILABLE"]
        assert len(provider.calls) == 2
    finally:
        set_video_service(None)


def test_real_recap_draft_renders(tmp_path, monkeypatch):
    """Phase 8 acceptance: a data-bound market recap (built by `video.recaps`)
    renders through the REAL worker with every figure resolved — no authored
    numbers anywhere."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from harness.video.recaps import build_recap_spec
    from video_fakes import FakeMarketProvider

    provider = FakeMarketProvider(bars=30)
    service, manager, _ = _make(tmp_path, with_artifacts=False, data_provider=provider)
    try:
        spec = build_recap_spec(symbols=["BTC-USD", "ETH-USD"], title="RECAP SMOKE")
        project = service.create_project(name="Recap Smoke", kind="storyboard", spec=spec)
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
        assert {entry["kind"] for entry in output["evidence"]["bindings"]} == {"value", "candles"}
        assert len(provider.calls) >= 2  # both symbols' quotes resolved
    finally:
        set_video_service(None)


def test_real_final_render_gets_a_poster_thumbnail(tmp_path, monkeypatch):
    """Phase 7 acceptance: a real final render's MP4 gets a REAL frame as its
    Artifact Center thumbnail (via the registered FFmpeg poster extractor),
    and byte ranges are served for inline playback."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from harness.artifacts.preview import set_video_poster_extractor
    from harness.video import config as video_config
    from harness.video.config import VideoConfig
    from harness.video.poster import extract_video_poster

    # The poster extractor resolves the FFmpeg tree through the process-wide
    # video config; pin it to THIS machine's tree for the test.
    monkeypatch.setattr(
        video_config, "_default", VideoConfig(ffmpeg_dir=os.environ.get("FFMPEG_DIR", ""))
    )
    set_video_poster_extractor(extract_video_poster)
    service, manager, artifacts = _make(tmp_path, with_artifacts=True)
    try:
        assert service.capabilities()["ready"] is True
        project = service.create_project(name="Poster Smoke")

        async def scenario():
            await manager.start()
            submitted = await service.render_final(project["id"])
            job = await wait_terminal(manager, submitted["jobId"], timeout=300)
            await manager.stop()
            return job

        job = asyncio.run(scenario())
        assert job["status"] == "SUCCEEDED", job
        artifact = artifacts.get(job["output"]["artifact"]["id"])
        assert artifact.category.value == "video"
        assert artifact.preview_status.value == "READY", artifact.preview_status
        assert artifact.thumbnail_key and artifact.thumbnail_key.endswith(".thumb.png")
        found = artifacts.open_thumbnail(artifact.id)
        assert found is not None
        handle, _ = found
        poster = handle.read()
        assert poster[:8] == b"\x89PNG\r\n\x1a\n"  # a real PNG, not a placeholder
        assert len(poster) > 1000
    finally:
        set_video_service(None)
