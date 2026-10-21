"""Replay dataset builder: dedupe, redaction, live-only regression tasks."""

from __future__ import annotations

import json

import pytest

from harness.evaluation.replay_builder import build_replay_tasks, write_dataset
from harness.evaluation.tasks import load_dataset
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _run(store, run_id: str, query: str, status: str = "completed") -> None:
    store.create_run(run_id, "eclipse-agent", {"query": query})
    store.append_event(run_id, "tool.requested", 1, {
        "name": "get_quote", "toolCallId": "c1",
        "args": {"symbol": "ACME"},
    })
    store.append_event(run_id, "tool.completed", 2, {
        "name": "get_quote", "toolCallId": "c1",
    })
    store.update_run(run_id, status=status)


def test_completed_run_becomes_a_live_only_regression_task(store):
    _run(store, "r1", "Get ACME quote")
    result = build_replay_tasks(store)

    assert len(result.tasks) == 1
    task = result.tasks[0]
    assert task["category"] == "regression"
    assert task["expected_tools"] == ["get_quote"]
    assert task["metadata"]["live_only"] is True
    assert task["metadata"]["sourceRunId"] == "r1"
    assert task["metadata"]["expectedBehavior"].startswith("recorded tool sequence")
    assert "expected_output" not in task


def test_duplicate_runs_collapse(store):
    _run(store, "r1", "Get ACME quote")
    _run(store, "r2", "Get ACME quote")
    result = build_replay_tasks(store)
    assert len(result.tasks) == 1
    assert result.duplicates == 1


def test_failed_runs_are_excluded_by_default(store):
    _run(store, "r1", "Get ACME quote", status="failed")
    assert build_replay_tasks(store).tasks == []
    assert len(build_replay_tasks(store, include_failed=True).tasks) == 1


def test_prompt_is_redacted_and_dataset_round_trips(store, tmp_path):
    _run(store, "r1", "Use api_key=supersecret to get ACME")
    result = build_replay_tasks(store)
    prompt = result.tasks[0]["input"]["prompt"]
    assert "supersecret" not in prompt
    assert "[REDACTED]" in prompt

    path = write_dataset(result, str(tmp_path / "replay_v1.json"))
    dataset = load_dataset(path)
    assert dataset.name == "eclipse-replay"
    assert dataset.reviewed is False
    assert len(dataset.tasks) == 1
    assert dataset.tasks[0].metadata["live_only"] is True

    raw = json.loads((tmp_path / "replay_v1.json").read_text(encoding="utf-8"))
    assert raw["metadata"]["sources"] == ["r1"]
