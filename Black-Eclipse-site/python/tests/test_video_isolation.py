"""Phase 8 isolation pins.

The worker executes only its own compiled code and every input/output stays in
the job's confined workspace. These tests pin that contract:

1. storyboard specs have NO way to name a media/asset path (unknown keys are
   refused with their precise path), so a spec cannot point the renderer at a
   file outside the video;
2. the invoked worker's argv (`--project`, `-o`) is inside the job workspace;
3. a worker that REPORTS an output outside the workspace is refused before
   inspection or Artifact Center registration.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness.artifacts.model import ListArtifactsQuery
from harness.video.service import set_video_service
from harness.video.spec import validate_storyboard

from fabric_helpers import wait_terminal
from video_fakes import make_video_env

_SPEC = {
    "schemaVersion": 2,
    "format": "landscape",
    "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Confined"}],
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    yield make_video_env(tmp_path, monkeypatch)
    set_video_service(None)


def test_storyboard_specs_cannot_name_media_paths():
    """No scene, item or top-level key may smuggle a filesystem path in: the
    schema is closed, so every path-ish field is an unknown-key refusal."""
    path_value = r"C:\Windows\System32\drivers\etc\hosts"
    cases = [
        # scene-level media keys
        {"type": "intro", "durationSeconds": 2, "title": "x", "image": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "video": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "audio": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "asset": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "src": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "file": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "path": path_value},
        {"type": "intro", "durationSeconds": 2, "title": "x", "media": path_value},
        # nested item key
        {
            "type": "metric", "durationSeconds": 2, "title": "x",
            "metrics": [{"label": "L", "value": "1", "image": path_value}],
        },
    ]
    for scene in cases:
        problems = validate_storyboard(
            {"schemaVersion": 2, "format": "landscape", "scenes": [scene]}
        )
        assert problems, f"a path-bearing unknown key was accepted: {sorted(scene)}"
        assert any("unknown field" in problem for problem in problems), problems

    top_level = validate_storyboard({
        "schemaVersion": 2, "format": "landscape",
        "mediaRoot": path_value,
        "scenes": [_SPEC["scenes"][0]],
    })
    assert any("unknown field" in problem for problem in top_level), top_level


def _argv_for(path: Path) -> list[str]:
    return json.loads(Path(str(path) + ".argv.json").read_text(encoding="utf-8"))


def _workspace(env, job_id: str) -> Path:
    return env["config"].resolve_video_root() / "jobs" / job_id


def test_worker_argv_is_confined_to_the_job_workspace(env):
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Confined", kind="storyboard", spec=_SPEC)

    async def scenario():
        await manager.start()
        rendered = await service.render_draft(project["id"])
        render_job = await wait_terminal(manager, rendered["jobId"], timeout=30)
        previewed = await service.preview_project(project["id"])
        preview_job = await wait_terminal(manager, previewed["jobId"], timeout=30)
        await manager.stop()
        return render_job, preview_job

    render_job, preview_job = asyncio.run(scenario())
    assert render_job["status"] == "SUCCEEDED", render_job
    assert preview_job["status"] == "SUCCEEDED", preview_job

    render_ws = _workspace(env, render_job["id"])
    render_argv = _argv_for(Path(render_job["output"]["outputPath"]))
    project_path = Path(render_argv[render_argv.index("--project") + 1]).resolve()
    output_path = Path(render_argv[render_argv.index("-o") + 1]).resolve()
    assert str(project_path).startswith(str(render_ws.resolve()))
    assert str(output_path).startswith(str(render_ws.resolve()))

    preview_ws = _workspace(env, preview_job["id"])
    previews = preview_job["output"]["previews"]
    strip_path = next(Path(p["path"]) for p in previews if p["kind"] == "strip")
    strip_argv = _argv_for(strip_path)
    assert str(Path(strip_argv[strip_argv.index("--project") + 1]).resolve()).startswith(
        str(preview_ws.resolve())
    )
    assert str(Path(strip_argv[strip_argv.index("-o") + 1]).resolve()).startswith(
        str(preview_ws.resolve())
    )
    frames_dir = next(Path(p["path"]).parent for p in previews if p["kind"] == "frame")
    frames_argv = json.loads((frames_dir / "argv.json").read_text(encoding="utf-8"))
    assert str(Path(frames_argv[frames_argv.index("-o") + 1]).resolve()).startswith(
        str(preview_ws.resolve())
    )


def test_preview_refuses_an_output_outside_the_workspace(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "escape_strip")
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Escaping preview", kind="storyboard", spec=_SPEC)

    async def scenario():
        await manager.start()
        submitted = await service.preview_project(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "FAILED", job
    assert job["errorClass"] == "INVALID_INPUT"
    assert "outside the video workspace" in (job["error"] or "")
    # Nothing was registered from the refused output.
    assert env["artifacts"].list(ListArtifactsQuery()).artifacts == []


def test_render_refuses_an_output_outside_the_workspace(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "escape_render")
    service, manager = env["service"], env["manager"]
    project = service.create_project(name="Escaping render", kind="storyboard", spec=_SPEC)

    async def scenario():
        await manager.start()
        submitted = await service.render_final(project["id"])
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "FAILED", job
    assert job["errorClass"] == "INVALID_STATE"
    assert "outside the confined workspace" in (job["error"] or "")
    assert env["artifacts"].list(ListArtifactsQuery()).artifacts == []
