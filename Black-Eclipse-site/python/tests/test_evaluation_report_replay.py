"""Reporting formats and trajectory replay/inspection."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.evaluation.report import to_html, to_json, to_jsonl, to_markdown, write_report
from harness.evaluation.replay import compare_trajectories, inspect, replay
from harness.evaluation.runner import EvaluationRunner, ScriptedAgentInvoker
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import EvaluationTask


@pytest.fixture()
def env():
    directory = tempfile.mkdtemp(prefix="be-eval-rep-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    runner = EvaluationRunner(store, invoker=ScriptedAgentInvoker(store),
                              eval_store=EvaluationStore(store))
    yield runner, directory
    store.close()


def _task(**overrides):
    data = {"id": "t.001", "category": "core", "difficulty": "easy",
            "input": {"prompt": "say OK"}, "expected_output": {"equals": "OK"},
            "metadata": {"agent_script": [{"type": "final", "content": "OK"}]}}
    data.update(overrides)
    return EvaluationTask.from_dict(data)


def test_report_formats_render_and_keep_metrics_separate(env):
    runner, _ = env
    suite = asyncio.run(runner.run_suite([_task()], dataset_name="d", trials=1, tier=0, persist=False))
    as_json = json.loads(to_json(suite))
    assert "aggregates" in as_json and "categories" in as_json
    assert "UNKNOWN" in to_markdown(suite)  # latency cannot be measured
    assert "<html" in to_html(suite)
    lines = to_jsonl(suite).splitlines()
    assert lines and json.loads(lines[0])["taskId"] == "t.001"


def test_write_report_creates_files(env):
    runner, directory = env
    suite = asyncio.run(runner.run_suite([_task()], dataset_name="d", trials=1, tier=0, persist=False))
    paths = write_report(suite, directory, formats=("json", "jsonl", "md", "html"), name="r1")
    assert all(os.path.isfile(p) for p in paths)
    with pytest.raises(ValueError):
        write_report(suite, directory, formats=("pdf",))


def test_inspect_and_compare_trajectories(env):
    runner, _ = env
    task = _task()
    result = asyncio.run(runner.run_task(task, trials=1, persist=False))
    trajectory = result.trials[0].trajectory
    summary = inspect(trajectory)
    assert summary["taskId"] == "t.001"
    assert summary["eventCount"] > 0
    assert compare_trajectories(trajectory, trajectory)["identical"] is True


def test_replay_reruns_through_the_real_runtime(env):
    runner, _ = env
    task = _task()
    result = asyncio.run(runner.run_task(task, trials=1, persist=False))
    replayed = asyncio.run(replay(result.trials[0].trajectory, runner.invoker, task))
    assert replayed.replayed["taskId"] == "t.001"
    assert replayed.replayed["outcome"]["status"] == "completed"
