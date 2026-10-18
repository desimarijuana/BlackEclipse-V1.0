"""The bounded repair loop (Phase 6): transient failures retried in-job (capped),
content failures repaired by revision (capped per failure line, explicit
terminal refusal), and the final render's review provenance (fake worker)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness.video.models import VideoError
from harness.video.repair import MAX_REPAIR_ATTEMPTS, is_transient, repair_attempts
from harness.video.service import set_video_service

from fabric_helpers import wait_terminal
from video_fakes import FakeMarketProvider, make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    yield make_video_env(tmp_path, monkeypatch)
    set_video_service(None)


def _job_report(env, job_id: str) -> dict:
    path = env["config"].resolve_video_root() / "jobs" / job_id / "report.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _spec(title: str = "Fix me") -> dict:
    return {
        "schemaVersion": 2,
        "format": "landscape",
        "scenes": [
            {"type": "intro", "durationSeconds": 2, "title": title},
            {"type": "outro", "durationSeconds": 2, "transition": "fade", "title": "End"},
        ],
    }


def _bound_spec() -> dict:
    return {
        "schemaVersion": 3,
        "format": "landscape",
        "scenes": [{
            "type": "metric", "durationSeconds": 3, "title": "Live",
            "metrics": [{"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}}],
        }],
    }


def _run_render(env, project_id, *, mode="draft"):
    service, manager = env["service"], env["manager"]
    submit = service.render_final if mode == "final" else service.render_draft

    async def scenario():
        await manager.start()
        submitted = await submit(project_id)
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    return asyncio.run(scenario())


def _run_repair(env, project_id, of_job_id, **kwargs):
    service, manager = env["service"], env["manager"]

    async def scenario():
        await manager.start()
        submitted = await service.render_repair(project_id, of_job_id=of_job_id, **kwargs)
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    return asyncio.run(scenario())


def test_repair_policy_helpers_are_pure():
    assert is_transient("DATA_UNAVAILABLE") and is_transient("worker_unavailable")
    assert not is_transient("INSPECTION_FAILED") and not is_transient(None)
    jobs = [
        {"id": "a", "input": {"action": "render"}},
        {"id": "b", "input": {"action": "render", "repairOf": "a"}},
        {"id": "c", "input": {"action": "render", "repairOf": "b"}},
        {"id": "d", "input": {"action": "render", "repairOf": "a"}},
    ]
    assert repair_attempts(jobs, "c") == 3  # b and c in the chain, plus d
    assert repair_attempts(jobs, "a") == 3  # counting per failure line, not parent
    assert repair_attempts([], "a") == 0


def test_transient_provider_failure_is_retried_inside_the_job(tmp_path, monkeypatch):
    provider = FakeMarketProvider(fail_times=1)
    env = make_video_env(tmp_path, monkeypatch, data_provider=provider)
    try:
        project = env["service"].create_project(name="Transient", kind="storyboard", spec=_bound_spec())
        _submitted, job = _run_render(env, project["id"])
        assert job["status"] == "SUCCEEDED", job
        retries = job["output"]["retries"]
        assert [entry["errorClass"] for entry in retries] == ["DATA_UNAVAILABLE"]
        assert len(provider.calls) == 2
    finally:
        set_video_service(None)


def test_transient_retry_is_bounded_and_still_fails(tmp_path, monkeypatch):
    provider = FakeMarketProvider(fail=True)
    env = make_video_env(tmp_path, monkeypatch, data_provider=provider)
    try:
        project = env["service"].create_project(name="Down", kind="storyboard", spec=_bound_spec())
        _submitted, job = _run_render(env, project["id"])
        assert job["status"] == "FAILED"
        assert job["errorClass"] == "DATA_UNAVAILABLE"
        report = _job_report(env, job["id"])
        assert len(report["result"]["retries"]) == 1
        assert len(provider.calls) == 2  # one initial + one bounded retry, then stop
    finally:
        set_video_service(None)


def test_transient_retries_can_be_disabled(tmp_path, monkeypatch):
    provider = FakeMarketProvider(fail_times=1)
    env = make_video_env(
        tmp_path, monkeypatch, data_provider=provider, transient_retries=0
    )
    try:
        project = env["service"].create_project(name="No retry", kind="storyboard", spec=_bound_spec())
        _submitted, job = _run_render(env, project["id"])
        assert job["status"] == "FAILED"
        assert job["errorClass"] == "DATA_UNAVAILABLE"
        report = _job_report(env, job["id"])
        assert "retries" not in report["result"]
        assert len(provider.calls) == 1
    finally:
        set_video_service(None)


def test_repair_requires_a_change_for_content_failures(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    service = env["service"]
    project = service.create_project(name="Clipped", kind="storyboard", spec=_spec())
    _submitted, failed = _run_render(env, project["id"])
    assert failed["status"] == "FAILED" and failed["errorClass"] == "INSPECTION_FAILED"

    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_repair(project["id"], of_job_id=failed["id"]))
    assert exc.value.code == "REPAIR_REQUIRES_CHANGE"
    assert service.get_project(project["id"])["revision"] == 1  # no silent revision bump


def test_repair_updates_the_spec_and_links_the_failure(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    service = env["service"]
    project = service.create_project(name="Clipped", kind="storyboard", spec=_spec())
    _submitted, failed = _run_render(env, project["id"])
    monkeypatch.delenv("FAKE_VIDEO_INSPECT")

    submitted, repaired = _run_repair(
        env, project["id"], failed["id"], spec=_spec("Fixed"), name="Clipped v2"
    )
    assert submitted["repair"] == {
        "ofJobId": failed["id"], "attempt": 1, "maxAttempts": MAX_REPAIR_ATTEMPTS,
    }
    assert repaired["status"] == "SUCCEEDED", repaired
    output = repaired["output"]
    assert output["repair"]["ofJobId"] == failed["id"]
    assert output["repair"]["attempt"] == 1
    diagnostics = output["repair"]["diagnostics"]
    assert diagnostics["errorClass"] == "INSPECTION_FAILED"
    assert any("clipped" in (finding.get("message") or "") for finding in diagnostics["findings"])
    assert repaired["input"]["repairOf"] == failed["id"]
    project = service.get_project(project["id"])
    assert project["revision"] == 2 and project["name"] == "Clipped v2"
    spec_path = Path(output["outputPath"]).parent / "spec.json"
    assert "Fixed" in spec_path.read_text(encoding="utf-8")


def test_repair_loop_is_capped_with_an_explicit_refusal(env, monkeypatch):
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    service = env["service"]
    project = service.create_project(name="Hopeless", kind="storyboard", spec=_spec())
    _submitted, failed = _run_render(env, project["id"])

    first = None
    latest = failed
    for _ in range(MAX_REPAIR_ATTEMPTS):
        submitted, first = _run_repair(env, project["id"], latest["id"], spec=_spec("Still bad"))
        assert first["status"] == "FAILED" and first["errorClass"] == "INSPECTION_FAILED"
        latest = first

    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_repair(project["id"], of_job_id=latest["id"], spec=_spec("One more")))
    assert exc.value.code == "REPAIR_LIMIT_REACHED"
    assert str(MAX_REPAIR_ATTEMPTS) in exc.value.message

    # The cap is per FAILURE LINE: re-referencing the original failure is refused too.
    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_repair(project["id"], of_job_id=failed["id"], spec=_spec("Again")))
    assert exc.value.code == "REPAIR_LIMIT_REACHED"


def test_repair_of_a_successful_or_cancelled_job_is_refused(env):
    service = env["service"]
    project = service.create_project(name="Fine", kind="storyboard", spec=_spec())
    _submitted, succeeded = _run_render(env, project["id"])
    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_repair(project["id"], of_job_id=succeeded["id"]))
    assert exc.value.code == "INVALID_STATE" and "succeeded" in exc.value.message
    with pytest.raises(VideoError) as exc:
        asyncio.run(service.render_repair(project["id"], of_job_id="job_missing"))
    assert exc.value.code == "JOB_NOT_FOUND"


def test_final_records_the_review_cut(env):
    service = env["service"]
    project = service.create_project(name="Reviewed", kind="storyboard", spec=_spec())
    _submitted, preview_job = _run_preview_helper(env, project["id"])
    _submitted, final = _run_render(env, project["id"], mode="final")
    assert final["status"] == "SUCCEEDED", final
    review = final["output"]["review"]
    assert review["kind"] == "preview" and review["jobId"] == preview_job["id"]

    plain = service.create_project(name="Unreviewed", kind="storyboard", spec=_spec())
    _submitted, final = _run_render(env, plain["id"], mode="final")
    assert final["status"] == "SUCCEEDED", final
    assert final["output"]["review"] is None


def _run_preview_helper(env, project_id):
    service, manager = env["service"], env["manager"]

    async def scenario():
        await manager.start()
        submitted = await service.preview_project(project_id)
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    return asyncio.run(scenario())
