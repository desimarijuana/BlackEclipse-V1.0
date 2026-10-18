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
from video_fakes import FakeMarketProvider, make_video_env


@pytest.fixture()
def env(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch, data_provider=FakeMarketProvider())
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
    assert data["projectKinds"] == ["title_card", "storyboard"]
    assert data["storyboardSchemaVersion"] == 3
    assert data["dataBindings"]["providerAvailable"] is True
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


def test_storyboard_create_and_update_through_tools(env):
    registry = env["registry"]
    spec = {
        "schemaVersion": 2,
        "format": "landscape",
        "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Story"}],
    }
    text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Story", "kind": "storyboard", "spec": spec}, _ctx()))
    assert created["status"] == "ok"
    project = created["project"]
    assert project["kind"] == "storyboard" and project.get("revision") == 1

    text, updated = asyncio.run(_handler(registry, "video_update_project")(
        {"projectId": project["id"], "name": "Story v2"}, _ctx()))
    assert updated["project"]["revision"] == 2 and "revision 2" in text

    text, bad = asyncio.run(_handler(registry, "video_update_project")(
        {"projectId": project["id"], "spec": {"schemaVersion": 2}}, _ctx()))
    assert bad["status"] == "error" and bad["error"]["code"] == "INVALID_SPEC"


def test_resolve_data_tool_returns_the_manifest(env):
    registry = env["registry"]
    spec = {
        "schemaVersion": 3,
        "format": "landscape",
        "scenes": [{
            "type": "metric", "durationSeconds": 4, "title": "Live",
            "metrics": [{"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}}],
        }],
    }
    _text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Bound", "kind": "storyboard", "spec": spec}, _ctx()))
    project_id = created["project"]["id"]

    text, data = asyncio.run(_handler(registry, "video_resolve_data")(
        {"projectId": project_id}, _ctx()))
    assert data["status"] == "ok"
    assert data["evidence"]["bindings"][0]["display"] == "$68,240"
    assert "resolved 1 binding" in text and "$68,240" in text

    _text, plain = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Plain"}, _ctx()))
    text, data = asyncio.run(_handler(registry, "video_resolve_data")(
        {"projectId": plain["project"]["id"]}, _ctx()))
    assert data["status"] == "error" and data["error"]["code"] == "NO_BINDINGS"


def _status_text(status: dict) -> str:
    job = status["job"]
    return f"job {job.get('jobId')}: {job.get('status')}"


def test_preview_and_repair_are_advertised(env):
    _text, caps = asyncio.run(_handler(env["registry"], "video_capabilities")({}, _ctx()))
    assert caps["preview"]["contactSheet"] is True
    assert caps["preview"]["frames"] is True
    assert caps["repair"]["maxAttempts"] >= 1
    assert caps["limits"]["previewTimeoutMs"] >= 1000


def test_preview_tool_queues_pngs_without_a_video(env):
    registry, manager = env["registry"], env["manager"]
    _text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Preview me", "kind": "storyboard", "spec": {
            "schemaVersion": 2, "format": "landscape",
            "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Hi"}],
        }}, _ctx()))
    project_id = created["project"]["id"]

    async def scenario():
        await manager.start()
        text, handle = await _handler(registry, "video_preview")(
            {"projectId": project_id}, _ctx())
        job = await wait_terminal(manager, handle["job"]["jobId"], timeout=30)
        await manager.stop()
        return text, job

    text, job = asyncio.run(scenario())
    assert "preview submitted" in text
    assert job["status"] == "SUCCEEDED", job
    assert job["output"]["action"] == "preview"
    assert "artifact" not in job["output"]  # a preview is never a video
    assert job["output"]["previews"][0]["registered"] is True


def test_repair_tool_refuses_a_content_failure_without_a_change(env, monkeypatch):
    registry, manager = env["registry"], env["manager"]
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    _text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Broken", "kind": "storyboard", "spec": {
            "schemaVersion": 2, "format": "landscape",
            "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Hi"}],
        }}, _ctx()))
    project_id = created["project"]["id"]

    async def scenario():
        await manager.start()
        _text, handle = await _handler(registry, "video_render_draft")(
            {"projectId": project_id}, _ctx())
        failed = await wait_terminal(manager, handle["job"]["jobId"], timeout=30)
        text, refused = await _handler(registry, "video_render_repair")(
            {"projectId": project_id, "ofJobId": failed["id"]}, _ctx())
        await manager.stop()
        return failed, text, refused

    failed, text, refused = asyncio.run(scenario())
    assert failed["status"] == "FAILED"
    assert refused["status"] == "error"
    assert refused["error"]["code"] == "REPAIR_REQUIRES_CHANGE"
    assert "REPAIR_REQUIRES_CHANGE" in text


def test_repair_tool_revises_and_queues_the_retry(env, monkeypatch):
    registry, manager = env["registry"], env["manager"]
    monkeypatch.setenv("FAKE_VIDEO_INSPECT", "bad")
    _text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Repairable", "kind": "storyboard", "spec": {
            "schemaVersion": 2, "format": "landscape",
            "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Bad"}],
        }}, _ctx()))
    project_id = created["project"]["id"]

    async def scenario():
        await manager.start()
        _text, handle = await _handler(registry, "video_render_draft")(
            {"projectId": project_id}, _ctx())
        failed = await wait_terminal(manager, handle["job"]["jobId"], timeout=30)
        await manager.stop()
        return failed

    failed = asyncio.run(scenario())
    monkeypatch.delenv("FAKE_VIDEO_INSPECT")

    async def scenario2():
        await manager.start()
        text, handle = await _handler(registry, "video_render_repair")({
            "projectId": project_id, "ofJobId": failed["id"],
            "spec": {
                "schemaVersion": 2, "format": "landscape",
                "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Fixed"}],
            },
        }, _ctx())
        job = await wait_terminal(manager, handle["job"]["jobId"], timeout=30)
        await manager.stop()
        return text, job

    text, job = asyncio.run(scenario2())
    assert "repair attempt 1 of" in text
    assert job["status"] == "SUCCEEDED", job
    assert job["output"]["repair"]["ofJobId"] == failed["id"]


def test_queued_jobs_reach_the_run_collector_and_carry_the_session(env):
    """Phase 7: a `video_*` tool hands the queued job to the run's collector
    (the chat's job card), and the job payload carries the conversation
    (session) + run id so a produced artifact is associated with them."""
    registry, manager = env["registry"], env["manager"]
    collected: list[dict] = []
    ctx = ToolContext(
        run_id="run_chat", log=lambda *a, **k: None,
        session_id="chat_42", agent_id="eclipse-agent",
        video_sink=collected.append,
    )

    _text, created = asyncio.run(_handler(registry, "video_create_project")(
        {"name": "Collected", "kind": "storyboard", "spec": {
            "schemaVersion": 2, "format": "landscape",
            "scenes": [{"type": "intro", "durationSeconds": 2, "title": "Hi"}],
        }}, ctx))
    project_id = created["project"]["id"]

    _text, handle = asyncio.run(_handler(registry, "video_render_final")(
        {"projectId": project_id}, ctx))
    job_id = handle["job"]["jobId"]

    assert collected and collected[-1]["kind"] == "render"
    assert collected[-1]["jobId"] == job_id
    assert collected[-1]["projectId"] == project_id
    assert collected[-1]["mode"] == "final"
    assert collected[-1]["projectName"] == "Collected"

    job = manager.get(job_id)
    context = (job.get("input") or {}).get("context") or {}
    assert context.get("conversationId") == "chat_42"
    assert context.get("runId") == "run_chat"
    assert context.get("agentId") == "eclipse-agent"
