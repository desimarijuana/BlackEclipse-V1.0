"""Fabric integration: builtin workers -> runtime, event rules, HTTP router."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.events import EventBus
from harness.fabric import JobState
from harness.fabric.bootstrap import install_fabric_layer, start_fabric, stop_fabric
from harness.fabric.integrations import build_event_handler, rule_for
from harness.tools import ToolContext, ToolDefinition, ToolRegistry

from fabric_helpers import make_store, wait_terminal


class _RunResult:
    def __init__(self, status: str, output: str = "", code: str | None = None) -> None:
        self._data = {
            "status": status, "output": output, "runId": "run_x", "totalTokens": 5,
            "error": {"code": code, "message": output} if code else None,
        }

    def model_dump(self):
        return dict(self._data)


class StubService:
    """A minimal service: only the attributes the fabric workers touch."""

    def __init__(self, store) -> None:
        self.store = store
        self.registry = ToolRegistry()
        self.bus = EventBus()

        async def echo(args, ctx: ToolContext):
            return {"echo": args.get("value")}, {"ok": True}

        self.registry.register(ToolDefinition(
            name="echo", description="echo", handler=echo,
            input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        ))

    async def run(self, request):
        return _RunResult("completed", output=f"agent answered: {request.input.query}")


@pytest.fixture()
def store(tmp_path):
    s = make_store(tmp_path)
    yield s
    s.close()


async def test_agent_worker_delegates_to_service_run(store):
    service = StubService(store)
    manager = install_fabric_layer(service)
    await start_fabric(service)
    try:
        result = await manager.submit("agent", {"query": "hello"}, mode="CONCURRENT")
        assert result["status"] == JobState.SUCCEEDED.value
        assert "agent answered: hello" in result["output"]
    finally:
        await stop_fabric(service)


async def test_tool_worker_delegates_to_the_registry(store):
    service = StubService(store)
    manager = install_fabric_layer(service)
    await start_fabric(service)
    try:
        submitted = await manager.submit(
            "tool", {"tool": "echo", "args": {"value": "hi"}}, mode="BACKGROUND", queue="user")
        job = await wait_terminal(manager, submitted["jobId"])
        assert job["status"] == JobState.SUCCEEDED.value
        assert job["output"] == {"ok": True}
    finally:
        await stop_fabric(service)


async def test_python_worker_runs_isolated_code(store):
    try:
        from harness.code import sandbox

        sandbox.select_backend()
    except Exception as exc:  # noqa: BLE001 - a missing sandbox is a supported state
        pytest.skip(f"sandbox unavailable: {exc}")
    service = StubService(store)
    manager = install_fabric_layer(service)
    await start_fabric(service)
    try:
        result = await manager.submit("python", {"code": "print(6 * 7)"}, mode="CONCURRENT")
        assert result["status"] == JobState.SUCCEEDED.value
        assert "42" in str(result["output"])
    finally:
        await stop_fabric(service)


async def test_event_rule_creates_a_notification_job(store):
    service = StubService(store)
    manager = install_fabric_layer(service)
    handler = build_event_handler(manager)
    event = SimpleNamespace(
        type="market.alert.triggered",
        payload={"title": "AAPL", "message": "price crossed", "level": "warning"},
        correlation_id="corr_1", task_id=None, agent_id=None, session_id=None, id="evt_1",
    )
    await handler(event)
    jobs = manager.list_jobs(type="notification")
    assert len(jobs) == 1
    assert jobs[0]["input"]["title"] == "AAPL"
    assert jobs[0]["correlationId"] == "corr_1"
    assert rule_for("task.completed").job_type == "notification"
    assert rule_for("unknown.event") is None


# ── HTTP router seam ────────────────────────────────────────────────────────


@pytest.fixture()
def app(store, monkeypatch):
    stub = StubService(store)
    install_fabric_layer(stub)

    from harness.routers import fabric as fabric_router

    monkeypatch.setattr(fabric_router, "service", stub, raising=False)
    application = FastAPI()
    application.include_router(fabric_router.router)
    return application, stub


def test_router_round_trip(app):
    application, stub = app
    with TestClient(application) as client:
        created = client.post("/fabric/jobs", json={
            "type": "tool", "mode": "BACKGROUND", "queue": "user",
            "tool": "echo", "args": {"value": "x"},
        })
        assert created.status_code == 200, created.text
        job_id = created.json()["jobId"]
        detail = client.get(f"/fabric/jobs/{job_id}")
        assert detail.status_code == 200
        assert detail.json()["job"]["type"] == "tool"
        listed = client.get("/fabric/jobs").json()
        assert listed["success"] and listed["jobs"]
        assert client.get("/fabric/queues").json()["success"]
        assert client.get("/fabric/workers").json()["success"]
        assert client.get("/fabric/status").json()["success"]
        cancelled = client.post(f"/fabric/jobs/{job_id}/cancel").json()
        assert cancelled["success"] and cancelled["cancelled"]
        assert client.get(f"/fabric/jobs/{job_id}/events").json()["success"]
        assert client.get("/fabric/dlq").json()["success"]


def test_router_unknown_job_is_404(app):
    application, _ = app
    with TestClient(application) as client:
        assert client.get("/fabric/jobs/missing").status_code == 404
        assert client.post("/fabric/jobs/missing/retry").status_code == 404


def test_router_unavailable_is_503(monkeypatch):
    from harness.routers import fabric as fabric_router

    monkeypatch.setattr(fabric_router, "service", SimpleNamespace(fabric=None), raising=False)
    application = FastAPI()
    application.include_router(fabric_router.router)
    with TestClient(application) as client:
        assert client.get("/fabric/status").status_code == 503
