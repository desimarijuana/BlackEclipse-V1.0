"""The nightly session: a planted regression must FAIL the gate.

A gate that cannot fail is decoration. This test plants a regression (a task
that does not pass) against a recorded baseline and asserts the session says
FAIL, names the regressed measure and reports it.
"""

from __future__ import annotations

import json
import os

import pytest

from harness.evaluation.nightly import run_nightly
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _task(task_id: str, *, answer: str) -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": task_id,
        "version": 1,
        "name": task_id,
        "description": "nightly fixture",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": f"Answer with {answer}."},
        "expected_output": {"equals": "READY"},
        "graders": [{"name": "exact"}],
        "metadata": {
            "tier": 0,
            "suites": ["core"],
            "agent_script": [{"type": "final", "content": answer}],
        },
    })


@pytest.mark.asyncio
async def test_a_planted_regression_fails_the_nightly_gate(store, tmp_path):
    reports = str(tmp_path / "reports")

    # 1. A clean run records the baseline.
    first = await run_nightly(
        store, tasks=[_task("nightly.good", answer="READY")],
        directory=reports, promote=True,
    )
    assert first["ok"] is True
    assert first["hasBaseline"] is False  # there was nothing to compare with yet
    assert first["baselineId"]

    # 2. The same corpus, but one task now fails: the gate must catch it.
    second = await run_nightly(
        store,
        tasks=[
            _task("nightly.good", answer="READY"),
            _task("nightly.broken", answer="MAYBE"),
        ],
        directory=reports,
    )
    assert second["ok"] is False
    assert second["regressions"]
    dimensions = {row["dimension"] for row in second["regressions"]}
    assert "task_success" in dimensions

    # 3. The report says so, on disk, in both formats.
    with open(second["report"]["json"], encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["ok"] is False
    with open(second["report"]["markdown"], encoding="utf-8") as handle:
        markdown = handle.read()
    assert "FAIL" in markdown
    assert "task_success" in markdown


@pytest.mark.asyncio
async def test_a_committed_baseline_file_is_the_gate(store, tmp_path):
    from harness.evaluation.nightly import read_baseline_file, write_baseline_file

    reports = str(tmp_path / "reports")
    baseline = str(tmp_path / "baseline.json")

    good = await run_nightly(
        store, tasks=[_task("nightly.good", answer="READY")],
        directory=reports, write_baseline=baseline,
    )
    assert good["ok"] is True
    body = read_baseline_file(baseline)
    assert body["metrics"]["aggregates"]["task_success"] == 1.0
    # The volatile measures are NOT in a committed baseline: they move every run.
    assert "cost" not in body["metrics"]["aggregates"]
    assert "latency" not in body["metrics"]["aggregates"]

    # A broken run against the COMMITTED baseline fails the session.
    broken = await run_nightly(
        store,
        tasks=[
            _task("nightly.good", answer="READY"),
            _task("nightly.broken", answer="MAYBE"),
        ],
        directory=reports,
        baseline_file=baseline,
    )
    assert broken["ok"] is False
    assert broken["hasBaseline"] is True
    assert any(row["dimension"] == "task_success" for row in broken["regressions"])


def test_a_broken_baseline_file_is_refused():
    from harness.evaluation.nightly import read_baseline_file

    with pytest.raises(ValueError):
        read_baseline_file("does-not-exist.json")


@pytest.mark.asyncio
async def test_a_clean_run_after_the_baseline_passes(store, tmp_path):
    reports = str(tmp_path / "reports")
    await run_nightly(
        store, tasks=[_task("nightly.good", answer="READY")],
        directory=reports, promote=True,
    )
    again = await run_nightly(
        store, tasks=[_task("nightly.good", answer="READY")],
        directory=reports,
    )
    assert again["ok"] is True
    assert again["hasBaseline"] is True
    assert again["regressions"] == []
