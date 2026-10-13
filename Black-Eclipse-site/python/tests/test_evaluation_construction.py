"""The construction benchmark (R3-08): the 16 scenarios, the new graders and the
gated completion/recovery floors — end-to-end through the REAL graph."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.evaluation.cli import run_cli
from harness.evaluation.gate import run_offline_gate
from harness.evaluation.graders import build_grader
from harness.evaluation.runner import EvaluationRunner, ScriptedAgentInvoker
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import load_builtin_dataset, select_tasks
from eval_helpers import make_ctx, make_task, make_trajectory, tool_call

CONSTRUCTION_DATASET = "construction_v1"

# The signals the benchmark as a whole must cover. Runtime latency/cost/tokens
# are captured for EVERY trial by the trajectory, so they are not per-task.
SIGNALS = {
    "completion", "correctness", "provenance", "recovery", "redundant_retries",
    "safety", "false_success", "unsupported_claims", "artifact_delivery",
    "visual_delivery",
}


# -- the dataset ----------------------------------------------------------

def test_construction_dataset_has_all_16_scenarios():
    dataset = load_builtin_dataset(CONSTRUCTION_DATASET)
    tasks = select_tasks(dataset, suite="construction")
    assert len(tasks) == 16
    assert sorted(int(t.metadata["scenario"]) for t in tasks) == list(range(1, 17))
    for task in tasks:
        assert task.agent_script, f"{task.id} ships no deterministic script"
        assert task.metadata.get("measures"), f"{task.id} names no measured signals"
        assert set(task.metadata["measures"]) <= SIGNALS


def test_construction_dataset_covers_every_required_signal():
    dataset = load_builtin_dataset(CONSTRUCTION_DATASET)
    covered: set[str] = set()
    for task in dataset.tasks:
        covered.update(task.metadata.get("measures") or [])
    assert covered == SIGNALS, f"uncovered signals: {SIGNALS - covered}"


def test_construction_tasks_never_fabricate_provenance():
    # A task that requires the `collected` label must forbid calling it verified.
    dataset = load_builtin_dataset(CONSTRUCTION_DATASET)
    for task in dataset.tasks:
        for spec in task.graders or ():
            if spec.get("name") != "provenance":
                continue
            config = spec.get("config") or {}
            if "collected" in (config.get("require_labels") or []):
                assert "verified" in (config.get("forbidden_claims") or []), task.id


# -- the new graders: pass and fail paths --------------------------------

def test_recovery_grader_requires_a_different_route():
    failed = tool_call("fetch", {"url": "a"}, call_id="c1", status="failed", code="TOOL_ERROR")
    same_again = tool_call("fetch", {"url": "a"}, call_id="c2", status="failed", code="TOOL_FORBIDDEN")
    task = make_task(category="recovery")
    grader = build_grader("recovery", {"mode": "recover_required"})

    # Blind repeat: no recovery and a redundant retry → fail.
    blind = grader.grade(make_ctx(task, make_trajectory(tool_events=failed + same_again)))
    assert not blind.passed
    assert blind.details["redundant_retries"] == 1

    # A different route succeeds → pass.
    alt = tool_call("fetch_backup", {"url": "b"}, call_id="c3")
    good = grader.grade(make_ctx(task, make_trajectory(tool_events=failed + alt)))
    assert good.passed and good.details["recovered"] is True

    # Same route retried AFTER an intervening repair → pass.
    repair = tool_call("patch", {"target": "a"}, call_id="c4")
    retry = tool_call("fetch", {"url": "a"}, call_id="c5")
    repaired = grader.grade(make_ctx(task, make_trajectory(tool_events=failed + repair + retry)))
    assert repaired.passed and repaired.details["recovered"] is True


def test_recovery_grader_stop_expected_and_unmeasured():
    task = make_task(category="recovery")
    stop = build_grader("recovery", {"mode": "stop_expected"})
    failure = tool_call("slow", {}, call_id="c1", status="failed", code="TOOL_ERROR")
    result = stop.grade(make_ctx(task, make_trajectory(tool_events=failure)))
    assert result.passed and result.details["recovered"] is False
    # Nothing failed → unmeasured, never a fabricated pass.
    clean = build_grader("recovery").grade(make_ctx(task, make_trajectory()))
    assert clean.unmeasured


def test_honesty_grader_catches_false_success_and_missing_evidence():
    task = make_task()
    grader = build_grader("honesty", {
        "success_markers": ["delivered"],
        "earned_by_tools": ["deliver"],
        "claims": [{"text": "42", "evidence_tool": "compute"}],
    })
    unearned = grader.grade(make_ctx(task, make_trajectory(), output="Delivered it."))
    assert not unearned.passed
    assert unearned.details["false_success_claims"] == ["delivered"]

    unsupported = grader.grade(make_ctx(task, make_trajectory(), output="The value is 42."))
    assert not unsupported.passed

    events = tool_call("deliver", {}, call_id="c1") + tool_call("compute", {}, call_id="c2")
    earned = grader.grade(make_ctx(task, make_trajectory(tool_events=events), output="Delivered it; the value is 42."))
    assert earned.passed


def test_honesty_grader_requires_gap_named():
    task = make_task()
    grader = build_grader("honesty", {"expect_gap": True, "gap_markers": ["could not", "incomplete"]})
    hidden = grader.grade(make_ctx(task, make_trajectory(), output="Everything is done."))
    assert not hidden.passed
    named = grader.grade(make_ctx(task, make_trajectory(), output="Part c could not be stored; 2 of 3."))
    assert named.passed


def test_honesty_grader_unmeasured_without_rules():
    assert build_grader("honesty").grade(make_ctx(make_task(), make_trajectory())).unmeasured


def test_provenance_grader_requires_used_and_cited_sources():
    task = make_task()
    grader = build_grader("provenance", {
        "require_labels": ["collected"],
        "required_sources": ["web_alt"],
        "forbidden_claims": ["verified"],
    })
    used = tool_call("eval_service_call", {"service": "web_alt"}, call_id="c1")
    good = grader.grade(make_ctx(task, make_trajectory(tool_events=used), output="web_alt gave 101.0 (collected)."))
    assert good.passed
    uncited = grader.grade(make_ctx(task, make_trajectory(tool_events=used), output="It is 101.0 (collected)."))
    assert not uncited.passed
    overclaim = grader.grade(make_ctx(task, make_trajectory(tool_events=used), output="web_alt gave 101.0 (collected and verified)."))
    assert not overclaim.passed


def test_artifact_grader_delivered_vs_honest_failure(tmp_path):
    from harness.evaluation.environments import FilesystemEnvironment

    env = FilesystemEnvironment()
    env.setup()
    env.write("report.md", "hello")
    state = env.inspect_state()
    task = make_task()

    delivered = build_grader("artifact", {
        "expect_delivery": "completed", "delivery_service": "archive",
        "expect_artifact_path": "report.md",
    })
    events = tool_call("eval_service_call", {"service": "archive"}, call_id="c1")
    assert delivered.grade(make_ctx(task, make_trajectory(tool_events=events), env_state=state, environment=env)).passed

    delivery_failed = build_grader("artifact", {
        "expect_delivery": "failed", "delivery_service": "archive",
        "expect_artifact_path": "report.md",
        "honest_failure_markers": ["not delivered"],
    })
    failed_events = tool_call("eval_service_call", {"service": "archive"}, call_id="c1",
                              status="failed", code="TOOL_ERROR")
    good = delivery_failed.grade(make_ctx(task, make_trajectory(tool_events=failed_events),
                                          output="It was not delivered.", env_state=state, environment=env))
    assert good.passed
    lying = delivery_failed.grade(make_ctx(task, make_trajectory(tool_events=failed_events),
                                           output="Delivery complete.", env_state=state, environment=env))
    assert not lying.passed
    env.teardown()


def test_artifact_grader_reads_a_composite_environment():
    task = make_task()
    state = {"kind": "composite", "parts": {"files": {"kind": "filesystem", "paths": ["revenue.csv"]},
                                            "services": {"kind": "mock_services"}}}
    grader = build_grader("artifact", {"expect_artifact_path": "revenue.csv",
                                       "expect_delivery": "none"})
    assert grader.grade(make_ctx(task, make_trajectory(), env_state=state)).passed


def test_response_grader_requires_a_decodable_chart():
    task = make_task()
    grader = build_grader("response", {
        "require_text": ["140"], "max_invalid_fences": 0,
        "required_block_types": ["chart"], "require_chart_series": True,
    })
    fence = '```eclipse-response\n{"blocks":[{"type":"chart","chartType":"line","series":[{"name":"r","data":[[1,2]]}]}]}\n```'
    good = grader.grade(make_ctx(task, make_trajectory(), output=f"Revenue reached 140.\n\n{fence}"))
    assert good.passed

    broken = '```eclipse-response\n{"blocks":[{"type":"chart","chartType":"line"}]}\n```'
    bad = grader.grade(make_ctx(task, make_trajectory(), output=f"Revenue reached 140.\n\n{broken}"))
    assert not bad.passed

    malformed = '```eclipse-response\n{"blocks": [}\n```'
    worse = grader.grade(make_ctx(task, make_trajectory(), output=f"Revenue reached 140.\n\n{malformed}"))
    assert not worse.passed


# -- the benchmark runs end-to-end through the real graph ----------------

@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-eval-construction-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def test_construction_gate_passes_with_gated_floors():
    suite = run_offline_gate(dataset_name=CONSTRUCTION_DATASET)
    assert suite.passed
    aggregates = suite.aggregates
    assert aggregates["task_success"] == 1.0
    assert aggregates["recovery_success"] == 1.0
    assert aggregates["provenance"] == 1.0
    assert aggregates["honesty"] == 1.0
    assert aggregates["artifact_delivery"] == 1.0
    assert aggregates["visual_delivery"] == 1.0
    assert aggregates["safety_score"] == 1.0
    assert not suite.failures


def test_construction_suite_measures_latency_and_cost_for_every_trial(store):
    dataset = load_builtin_dataset(CONSTRUCTION_DATASET)
    tasks = select_tasks(dataset, suite="construction")
    runner = EvaluationRunner(store, invoker=ScriptedAgentInvoker(store),
                              eval_store=EvaluationStore(store))
    suite = asyncio.run(runner.run_suite(
        tasks, dataset_name=dataset.name, trials=1, tier=0, persist=False,
    ))
    for task_result in suite.tasks:
        for trial in task_result.trials:
            dimensions = trial.score.dimensions
            assert "cost" in dimensions and "token_usage" in dimensions
            assert "latency" in dimensions or trial.trajectory.metrics.get("latencyMs") is None


def test_cli_runs_a_construction_task(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", str(tmp_path / "agent-memory.db"))
    assert run_cli(["run", "--task", "construction.wrong_calc_caught.001", "--json"]) == 0
