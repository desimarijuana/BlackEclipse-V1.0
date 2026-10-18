"""Preview jobs (Phase 6): the contact sheet + per-scene frame PNGs, image
artifact registration, diagnostics reported without failing, and evidence
resolution for bound storyboards (fake worker; no Rust, no FFmpeg)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness.video.models import VideoError
from harness.video.service import set_video_service

from fabric_helpers import wait_terminal
from video_fakes import FakeMarketProvider, make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    yield make_video_env(tmp_path, monkeypatch)
    set_video_service(None)


def _spec() -> dict:
    return {
        "schemaVersion": 2,
        "format": "landscape",
        "scenes": [
            {"type": "intro", "durationSeconds": 2, "title": "Look"},
            {"type": "metric", "durationSeconds": 3, "transition": "fade", "title": "Values",
             "metrics": [{"label": "Price", "value": "42"}]},
        ],
    }


def _run_preview(env, project_id, **kwargs):
    service, manager = env["service"], env["manager"]

    async def scenario():
        await manager.start()
        submitted = await service.preview_project(project_id, **kwargs)
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    return asyncio.run(scenario())


def test_preview_renders_contact_sheet_and_frames_with_artifacts(env):
    service, artifacts = env["service"], env["artifacts"]
    project = service.create_project(name="Look", kind="storyboard", spec=_spec())
    submitted, job = _run_preview(env, project["id"])

    assert submitted["kind"] == "preview"
    assert job["status"] == "SUCCEEDED", job
    output = job["output"]
    assert output["status"] == "completed" and output["action"] == "preview"
    assert [preview["kind"] for preview in output["previews"]] == ["strip", "frame", "frame"]
    assert output["findingsTotal"] == 0
    assert job["input"]["projectRevision"] == 1

    for preview in output["previews"]:
        assert Path(preview["path"]).is_file()
        assert preview["registered"] is True
        artifact = artifacts.get(preview["artifactId"])
        assert artifact.category.value == "image"
        assert artifact.mime_type == "image/png"
        assert artifact.metadata["videoJobId"] == job["id"]
        assert artifact.metadata["projectId"] == project["id"]
        assert artifact.metadata["kind"] == preview["kind"]
        assert "preview" in artifact.tags


def test_preview_reports_findings_without_failing(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_PREVIEW", "findings")
    service = env["service"]
    project = service.create_project(name="Findings", kind="storyboard", spec=_spec())
    _submitted, job = _run_preview(env, project["id"])

    assert job["status"] == "SUCCEEDED", job
    output = job["output"]
    assert output["findingsTotal"] == 1
    assert output["findingsErrors"] == 0 and output["findingsWarnings"] == 1
    finding = output["findings"][0]
    assert finding["severity"] == "warning"
    assert finding["key"].startswith("text_clipped")
    assert finding["kind"] == "text_clipped"


def test_preview_of_bound_storyboard_resolves_evidence(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider(stale=True))
    try:
        service = env["service"]
        spec = {
            "schemaVersion": 3,
            "format": "landscape",
            "scenes": [{
                "type": "metric", "durationSeconds": 3, "title": "Live",
                "metrics": [{"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}}],
            }],
        }
        project = service.create_project(name="Bound preview", kind="storyboard", spec=spec)
        _submitted, job = _run_preview(env, project["id"])

        assert job["status"] == "SUCCEEDED", job
        assert job["output"]["evidence"]["stale"] is True
        resolved = json.loads(
            (Path(job["output"]["previews"][0]["path"]).parent.parent / "spec.json").read_text(
                encoding="utf-8"
            )
        )
        assert resolved["scenes"][0]["metrics"][0]["value"] == "$68,240"
        assert "source" not in resolved["scenes"][0]["metrics"][0]
    finally:
        set_video_service(None)


def test_preview_title_card_has_no_frames(env):
    service = env["service"]
    project = service.create_project(name="Title")
    _submitted, job = _run_preview(env, project["id"])
    assert job["status"] == "SUCCEEDED", job
    assert [preview["kind"] for preview in job["output"]["previews"]] == ["strip"]


def test_preview_without_artifacts_reports_paths_honestly(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch)
    env["service"]._artifact_provider = lambda: None
    try:
        project = env["service"].create_project(name="No catalog", kind="storyboard", spec=_spec())
        _submitted, job = _run_preview(env, project["id"])
        assert job["status"] == "SUCCEEDED", job
        for preview in job["output"]["previews"]:
            assert preview["registered"] is False
            assert preview["artifactId"] is None
            assert "Artifact Center" in preview["registrationError"]
            assert Path(preview["path"]).is_file()
    finally:
        set_video_service(None)


def test_preview_of_a_missing_project_is_refused(env):
    with pytest.raises(VideoError) as exc:
        asyncio.run(env["service"].preview_project("vprj_0000000000000000"))
    assert exc.value.code == "PROJECT_NOT_FOUND"
