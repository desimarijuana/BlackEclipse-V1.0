"""The structured fframes worker interface: result shaping, progress forwarding,
timeout, cancellation and the "no false success" output check (fake worker)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from harness.video.config import VideoConfig
from harness.video.runner import VideoRunner

from video_fakes import write_fake_worker


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    script = write_fake_worker(tmp_path)
    config = VideoConfig(video_root=str(tmp_path / "video"), worker_bin=str(script))
    instance = VideoRunner(config)
    monkeypatch.setattr(instance, "worker_argv", lambda: [sys.executable, str(script)])
    return instance, tmp_path


def test_render_parses_json_and_reports_progress(runner):
    instance, tmp_path = runner
    seen: list = []
    result = asyncio.run(
        instance.render(
            out_path=tmp_path / "out" / "draft.mp4", draft=True, timeout_ms=30_000,
            progress=lambda fraction, message=None: seen.append((fraction, message)),
        )
    )
    assert result["ok"] is True
    assert result["width"] == 1920 and result["height"] == 1080
    assert Path(result["outputPath"]).stat().st_size == result["sizeBytes"] > 0
    assert seen and seen[-1][0] == pytest.approx(1.0)


def test_render_failure_is_structured(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "fail")
    result = asyncio.run(
        instance.render(out_path=tmp_path / "d.mp4", draft=True, timeout_ms=30_000)
    )
    assert result["ok"] is False
    assert result["status"] == "failed" and result["errorClass"] == "RENDER_FAILED"
    assert any("boom" in line for line in result["logTail"])


def test_render_success_without_output_is_not_success(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "nooutput")
    result = asyncio.run(
        instance.render(out_path=tmp_path / "d.mp4", draft=True, timeout_ms=30_000)
    )
    assert result["ok"] is False and result["errorClass"] == "RENDER_OUTPUT_MISSING"


def test_render_timeout_kills_the_process(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "sleep")
    result = asyncio.run(
        instance.render(out_path=tmp_path / "d.mp4", draft=True, timeout_ms=1_500)
    )
    assert result["ok"] is False
    assert result["status"] == "timed_out" and result["errorClass"] == "TIMEOUT"


def test_render_cancellation_kills_the_process(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "sleep")

    async def scenario():
        event = asyncio.Event()
        task = asyncio.create_task(
            instance.render(
                out_path=tmp_path / "d.mp4", draft=True, timeout_ms=60_000,
                cancel_event=event,
            )
        )
        await asyncio.sleep(0.6)
        event.set()
        return await asyncio.wait_for(task, timeout=20)

    result = asyncio.run(scenario())
    assert result["ok"] is False and result["status"] == "cancelled"


def test_inspect_clean_and_with_findings(runner, monkeypatch):
    instance, tmp_path = runner
    clean = asyncio.run(instance.inspect(timeout_ms=30_000, cwd=tmp_path))
    assert clean["ok"] is True
    assert clean["status"] == "inspected" and clean["checkedFrames"] == 39
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    bad = asyncio.run(instance.inspect(timeout_ms=30_000, cwd=tmp_path))
    assert bad["ok"] is False and bad["status"] == "inspection_failed"
    assert bad["findings"] and bad["workerExitCode"] == 2


def test_strip_renders_a_contact_sheet(runner):
    instance, tmp_path = runner
    result = asyncio.run(
        instance.strip(
            out_path=tmp_path / "previews" / "strip.png", count=6, columns=3, width=400,
            timeout_ms=30_000, cwd=tmp_path,
        )
    )
    assert result["ok"] is True and result["status"] == "rendered"
    assert Path(result["outputPath"]).is_file()
    assert result["frames"] == [0, 12, 25, 37, 50]
    assert result["diagnostics"] == []


def test_strip_carries_frame_diagnostics(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_PREVIEW", "findings")
    result = asyncio.run(
        instance.strip(
            out_path=tmp_path / "strip.png", timeout_ms=30_000, cwd=tmp_path,
        )
    )
    assert result["ok"] is True
    diagnostics = result["diagnostics"][0]["diagnostics"]
    assert diagnostics[0]["key"].startswith("text_clipped")
    assert diagnostics[0]["kind"] == "text_clipped"
    assert diagnostics[0]["severity"] == "warning"


def test_frames_render_one_png_per_spec(runner):
    instance, tmp_path = runner
    result = asyncio.run(
        instance.frames(
            at_specs=["#0@50%", "#1@50%"], out_dir=tmp_path / "previews" / "frames",
            timeout_ms=30_000, cwd=tmp_path,
        )
    )
    assert result["ok"] is True and len(result["frames"]) == 2
    for frame in result["frames"]:
        assert frame["spec"].endswith("@50%")
        assert Path(frame["path"]).is_file()
        assert frame["sizeBytes"] > 0


def test_preview_failures_are_structured(runner, monkeypatch):
    instance, tmp_path = runner
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "fail")
    strip = asyncio.run(
        instance.strip(out_path=tmp_path / "s.png", timeout_ms=30_000, cwd=tmp_path)
    )
    assert strip["ok"] is False and strip["errorClass"] == "PREVIEW_FAILED"
    assert any("boom" in line for line in strip["logTail"])
    frames = asyncio.run(
        instance.frames(at_specs=["#0@50%"], out_dir=tmp_path / "f", timeout_ms=30_000, cwd=tmp_path)
    )
    assert frames["ok"] is False and frames["errorClass"] == "PREVIEW_FAILED"

    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "nooutput")
    missing = asyncio.run(
        instance.strip(out_path=tmp_path / "s.png", timeout_ms=30_000, cwd=tmp_path)
    )
    assert missing["ok"] is False and missing["errorClass"] == "PREVIEW_OUTPUT_MISSING"


def test_frames_needs_at_least_one_spec(runner):
    instance, tmp_path = runner
    result = asyncio.run(
        instance.frames(at_specs=[], out_dir=tmp_path / "f", timeout_ms=30_000, cwd=tmp_path)
    )
    assert result["ok"] is False and result["errorClass"] == "INVALID_INPUT"
