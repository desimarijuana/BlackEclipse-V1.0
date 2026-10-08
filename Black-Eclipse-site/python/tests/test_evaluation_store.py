"""Persistence: datasets, runs, trials, scores, baselines, regressions, failures."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import load_builtin_dataset


@pytest.fixture()
def eval_store():
    directory = tempfile.mkdtemp(prefix="be-eval-store-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield EvaluationStore(store)
    store.close()


def test_dataset_task_and_run_roundtrip(eval_store):
    dataset = load_builtin_dataset("benchmark_v1")
    eval_store.save_dataset(dataset)
    for task in dataset.tasks:
        eval_store.upsert_task(task)
    assert eval_store.list_tasks(category="finance")

    run_id = eval_store.create_run(suite="finance", datasetName=dataset.name,
                                   datasetVersion=dataset.version,
                                   datasetChecksum=dataset.checksum, tier=0)
    eval_store.update_run(run_id, status="running")
    run = eval_store.get_run(run_id)
    assert run["status"] == "running" and run["suite"] == "finance"
    assert any(r["id"] == run_id for r in eval_store.list_runs())


def test_trial_score_metric_and_failure_persist(eval_store):
    run_id = eval_store.create_run(suite="x")
    eval_store.add_trial(runId=run_id, taskId="t.001", taskVersion=1, trialIndex=0,
                         passed=False, status="completed", score={"dimensions": {}},
                         trajectory={"runId": "r"})
    eval_store.add_score(runId=run_id, trialId="trial", taskId="t.001", taskVersion=1,
                         category="tools", dimension="tool_accuracy", value=0.5)
    eval_store.add_metric(runId=run_id, dimension="tool_accuracy", value=0.5, sampleSize=1)
    eval_store.record_failure(runId=run_id, taskId="t.001", labels=["tool_selection"],
                              detail={"x": 1})
    trials = eval_store.list_trials(run_id)
    assert len(trials) == 1 and trials[0]["passed"] == 0
    failures = eval_store.list_failures(run_id=run_id)
    assert failures and failures[0]["labels"] == ["tool_selection"]


def test_baseline_and_regression_persist(eval_store):
    baseline_id = eval_store.save_baseline(
        name="main", runId="run1", datasetChecksum="abc",
        metrics={"aggregates": {"task_success": 0.9}},
    )
    found = eval_store.get_baseline("main")
    assert found["id"] == baseline_id
    assert found["metrics"]["aggregates"]["task_success"] == 0.9
    eval_store.record_regression(baselineId=baseline_id, runId="run2", dimension="tool_accuracy",
                                 baseline=0.9, current=0.8, delta=-0.1, threshold=0.03)
    regressions = eval_store.list_regressions(run_id="run2")
    assert regressions and regressions[0]["dimension"] == "tool_accuracy"


def test_candidate_dedupe_and_status(eval_store):
    assert eval_store.candidate_exists("sig") is False
    cid = eval_store.save_candidate(signature="sig", category="tools",
                                    labels=["tool_selection"], task={"id": "c"})
    assert eval_store.candidate_exists("sig") is True
    assert eval_store.list_candidates()[0]["id"] == cid
    eval_store.update_candidate_status(cid, "validated")
    assert eval_store.list_candidates(status="validated")[0]["signature"] == "sig"


def test_model_results_persist(eval_store):
    eval_store.save_model_result(runId="run1", model="m1", provider="p1",
                                 metrics={"task_success": 0.5})
    results = eval_store.list_model_results(run_id="run1")
    assert results[0]["model"] == "m1"
    assert results[0]["metrics"]["task_success"] == 0.5
