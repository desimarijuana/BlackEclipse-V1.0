"""The agent-facing video tools: typed schemas, honest failures, and the full
tool workflow (create -> validate -> draft -> inspect -> final) over the fake
worker through the Execution Fabric."""

from __future__ import annotations

import asyncio

import pytest

from harness.tools import ToolContext, ToolRegistry
from harness.video.service import set_video_service
from harness.video.tools import VIDEO_TOOLS, register_video_tools

from fabric_helpers import wait_terminal
from video_fakes import make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch)
    registry = ToolRegistry()
    register_video_tools(registry)
    env["registry"] = registry
    yield env
    set_video_service(None)


def _ctx() -> ToolContext:
    return ToolContext(run_id="run_test", log=lambda *a, **k: None)


def _handler(registry: ToolRegistry, name: str):
    tool = registry.get(name)
    assert tool is not None
    return tool.handler


def test_tools_register_as_read_with_object_schemas(env):
    registry = env["registry"]
    for name in VIDEO_TOOLS:
        tool = registry.get(name)
        assert tool is not None, name
        assert tool.permission == "read"
        assert tool.risk == "low"
        assert tool.input_schema.get("type") == "object"
        assert callable(tool.handler)


def test_capabilities_reports_readiness(env):
    text, data = asyncio.run(_handler(env["registry"], "video_capabilities")({}, _ctx()))
    assert data["status"] == "ok" and data["ready"] is True
    assert data["projectKinds"] == ["title_card"]
    assert "ready" in text.lower()


def test_create_validate_and_render_draft_through_tools(env):
    registry, manager = env["registry"], env["manager"]

    text, data = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Chat Title Card"}, _ctx()))
    assert data["status"] == "ok"
    project_id = data["project"]["id"]
    assert "created video project" in text

    text, data = asyncio.run(_handler(registry, "video_validate_project")(
        {"projectId": project_id}, _ctx()))
    assert data["valid"] is True and data["problems"] == []

    async def scenario():
        await manager.start()
        _text, handle = await _handler(registry, "video_render_draft")(
            {"projectId": project_id}, _ctx())
        job_id = handle["job"]["jobId"]
        job = await wait_terminal(manager, job_id, timeout=30)
        status_text, status = await _handler(registry, "video_job_status")({"jobId": job_id}, _ctx())
        await manager.stop()
        return job, status_text, status

    job, status_text, status = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    assert status["status"] == "ok"
    assert status["job"]["output"]["inspection"]["ok"] is True
    assert "SUCCEEDED" in status_text


def test_final_render_surfaces_the_artifact(env):
    registry, manager = env["registry"], env["manager"]
    _text, data = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Deliverable"}, _ctx()))
    project_id = data["project"]["id"]

    async def scenario():
        await manager.start()
        _text, handle = await _handler(registry, "video_render_final")(
            {"projectId": project_id}, _ctx())
        job_id = handle["job"]["jobId"]
        job = await wait_terminal(manager, job_id, timeout=30)
        text, status = await _handler(registry, "video_job_status")({"jobId": job_id}, _ctx())
        await manager.stop()
        return job, text, status

    job, text, status = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    artifact_id = job["output"]["artifact"]["id"]
    assert f"artifact {artifact_id}" in text
    assert status["job"]["output"]["artifact"]["id"] == artifact_id


def test_inspect_and_cancel_through_tools(env, monkeypatch):
    registry, manager = env["registry"], env["manager"]
    _text, data = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Inspectable"}, _ctx()))
    project_id = data["project"]["id"]

    async def scenario():
        await manager.start()
        _text, handle = await _handler(registry, "video_render_draft")(
            {"projectId": project_id}, _ctx())
        await wait_terminal(manager, handle["job"]["jobId"], timeout=30)
        _text, inspection = await _handler(registry, "video_inspect")(
            {"jobId": handle["job"]["jobId"]}, _ctx())
        inspected = await wait_terminal(manager, inspection["job"]["jobId"], timeout=30)
        monkeypatch.setenv("FAKE_VIDEO_SCENARIO", "sleep")
        _text, slow = await _handler(registry, "video_render_draft")(
            {"projectId": project_id}, _ctx())
        slow_id = slow["job"]["jobId"]
        for _ in range(500):
            current = manager.get(slow_id)
            if current and current["status"] == "RUNNING":
                break
            await asyncio.sleep(0.02)
        _text, cancellation = await _handler(registry, "video_cancel_job")(
            {"jobId": slow_id}, _ctx())
        cancelled = await wait_terminal(manager, slow_id, timeout=30)
        await manager.stop()
        return inspected, cancellation, cancelled

    inspected, cancellation, cancelled = asyncio.run(scenario())
    assert inspected["status"] == "SUCCEEDED"
    assert inspected["output"]["ok"] is True
    assert cancellation["cancellation"]["cancelled"] is True
    assert cancelled["status"] == "CANCELLED"


def test_unknown_job_and_unavailable_service_are_structured(env):
    registry = env["registry"]
    text, data = asyncio.run(_handler(registry, "video_job_status")(
        {"jobId": "job_missing"}, _ctx()))
    assert data["status"] == "error" and data["error"]["code"] == "JOB_NOT_FOUND"
    assert "JOB_NOT_FOUND" in text

    set_video_service(None)
    text, data = asyncio.run(_handler(registry, "video_capabilities")({}, _ctx()))
    assert data["status"] == "error" and data["error"]["code"] == "RUNTIME_UNAVAILABLE"
    assert "RUNTIME_UNAVAILABLE" in text


def _status_text(status: dict) -> str:
    job = status["job"]
    return f"job {job.get('jobId')}: {job.get('status')}"
