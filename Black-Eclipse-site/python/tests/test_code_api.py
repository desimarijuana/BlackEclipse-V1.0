"""Phase 5/14 — the `/code/*` route seam.

The `/code/tasks` create route had NO API test, which is exactly why a
FOREIGN KEY ordering bug shipped: the route recorded a `task.created`
checkpoint (whose `RunCheckpoint.runId` FKs `HarnessRun(id)`) BEFORE the run row
existed, so every create returned HTTP 500. These tests drive the REAL route
against a REAL store and a stubbed run executor, so the ordering contract is
locked independently of `execute_run`'s model loop.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-code-api-"), "agent-memory.db"),
)


class _StubTaskStore:
    """A real-ish TaskStore over a temp DB, so FK behavior is exercised."""

    def __init__(self) -> None:
        from harness.code.tasks import TaskStore
        from harness.persistence import AgentMemoryStore

        self._store = AgentMemoryStore(
            os.path.join(tempfile.mkdtemp(prefix="be-code-api-store-"), "agent-memory.db")
        )
        self._tasks = TaskStore(self._store)

    def store(self):
        return self._store

    def record_created(self, run_id, **kwargs):
        # Mirror the route: the row MUST already exist or this raises the FK
        # IntegrityError the regression guards against.
        return self._tasks.record_created(run_id, **kwargs)

    def view(self, run_id):
        return self._tasks.view(run_id)


class _StubService:
    """Only the attributes the `/code/tasks` route touches."""

    def __init__(self) -> None:
        self._task_store = _StubTaskStore()
        self.store = self._task_store.store()

    def code_tasks(self):
        return self._task_store

    async def run(self, request):
        # The route pre-creates the row and records the boundary; the executor
        # must NOT re-create it. Assert the row is present here.
        assert self.store.get_run(request.runId) is not None

        class _Result:
            def model_dump(self_inner):
                return {"runId": request.runId, "status": "completed", "output": "ok"}

        return _Result()


@pytest.fixture()
def code_app(monkeypatch):
    from harness.routers import code as code_router

    stub = _StubService()
    monkeypatch.setattr(code_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(code_router.router)
    return TestClient(app), stub


def _payload():
    return {
        "query": "create hello.py and run it",
        "autonomy": "edit_verify",
        "callbackBaseUrl": "http://127.0.0.1:3000",
        "modelSettings": {
            "provider": "ollama",
            "baseUrl": "http://localhost:11434/v1",
            "apiKey": "ollama",
            "model": "test-model",
        },
    }


def test_create_task_does_not_fk_fail(code_app):
    """The run row exists before the FK-bound `task.created` checkpoint."""
    client, _stub = code_app
    resp = client.post("/code/tasks", json=_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["task"]["id"]


def test_create_task_records_created_boundary(code_app):
    """`task.created` is persisted with the run's autonomy after a create."""
    client, stub = code_app
    resp = client.post("/code/tasks", json=_payload())
    run_id = resp.json()["task"]["id"]
    created = stub.code_tasks()._tasks._lineage.latest_checkpoint(run_id)
    assert created is not None
    kinds = [c["kind"] for c in stub.code_tasks()._tasks._lineage.list_checkpoints(run_id)]
    assert "task.created" in kinds


def test_create_task_rejects_unknown_autonomy(code_app):
    client, _stub = code_app
    payload = _payload()
    payload["autonomy"] = "yolo"
    resp = client.post("/code/tasks", json=payload)
    assert resp.status_code == 400
