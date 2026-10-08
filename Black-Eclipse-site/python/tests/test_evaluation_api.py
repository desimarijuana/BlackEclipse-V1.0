"""The evaluation API routes: operator-gated, reading the real store."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-eval-api-"), "agent-memory.db"),
)

from fastapi.testclient import TestClient  # noqa: E402


def _client() -> TestClient:
    from harness import main as main_module

    # A loopback client satisfies `require_operator` without a token.
    return TestClient(main_module.app, client=("127.0.0.1", 5555))


def test_list_tasks_and_runs():
    client = _client()
    tasks = client.get("/evaluation/tasks")
    assert tasks.status_code == 200
    assert "tasks" in tasks.json()
    runs = client.get("/evaluation/runs")
    assert runs.status_code == 200


def test_missing_run_is_404():
    client = _client()
    assert client.get("/evaluation/runs/does-not-exist").status_code == 404


def test_remote_client_is_refused():
    from harness import main as main_module

    remote = TestClient(main_module.app, client=("203.0.113.9", 5555))
    assert remote.get("/evaluation/runs").status_code == 403


def test_start_offline_run_for_one_task():
    client = _client()
    response = client.post("/evaluation/runs", json={"taskId": "finance.pe.001", "trials": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["aggregates"]["task_success"] == 1.0
