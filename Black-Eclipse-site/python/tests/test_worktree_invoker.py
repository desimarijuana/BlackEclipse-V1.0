"""Measured code benchmark: isolation, decision, and baseline/candidate order."""

from __future__ import annotations

from pathlib import Path

from harness.evaluation.worktree_invoker import (
    BenchmarkConfig,
    PreparedWorktree,
    _app_root,
    _safe_env,
    benchmark_decision,
    run_candidate_benchmark,
    run_suite_in_worktree,
)


def _suite(success=0.8, *, measured=10, safety=1.0):
    return {
        "ok": True,
        "aggregates": {"task_success": success, "safety_score": safety},
        "measuredTrials": measured,
        "taskResults": [
            {"taskId": "a", "n": 1, "successes": 1, "passRate": 1.0},
            {"taskId": "b", "n": 1, "successes": 0, "passRate": 0.0},
        ],
    }


def test_benchmark_decision_accepts_a_measured_improvement():
    decision = benchmark_decision(_suite(0.7), _suite(0.8))
    assert decision["accepted"] is True
    assert decision["targetBefore"] == 0.7
    assert decision["targetAfter"] == 0.8


def test_benchmark_decision_rejects_unmeasured_and_non_improving():
    assert benchmark_decision(_suite(0.7), _suite(0.8, measured=0))["accepted"] is False
    assert benchmark_decision(_suite(0.8), _suite(0.8))["accepted"] is False


def test_benchmark_decision_vetoes_a_critical_task_drop():
    baseline = _suite(0.7)
    candidate = _suite(0.9)
    baseline["taskResults"].append({
        "taskId": "safety.forbidden_tool.001", "n": 1, "successes": 1,
        "passRate": 1.0,
    })
    candidate["taskResults"].append({
        "taskId": "safety.forbidden_tool.001", "n": 1, "successes": 0,
        "passRate": 0.0,
    })

    decision = benchmark_decision(
        baseline, candidate, critical_tasks=["safety.forbidden_tool.001"],
    )

    assert decision["accepted"] is False
    assert any("critical task regressed" in reason for reason in decision["reasons"])
    assert decision["criticalDeltas"][0]["delta"] == -1.0


def test_benchmark_decision_vetoes_a_critical_regression():
    decision = benchmark_decision(_suite(0.7, safety=1.0), _suite(0.9, safety=0.5))
    assert decision["accepted"] is False
    assert any("critical regression" in reason for reason in decision["reasons"])


def test_app_root_finds_a_nested_application(tmp_path):
    root = tmp_path / "repo"
    nested = root / "Black-Eclipse-site"
    (nested / "python" / "harness").mkdir(parents=True)

    assert _app_root(root) == nested
    assert _app_root(nested) == nested


def test_safe_env_excludes_provider_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("HARNESS_JOB_API_KEY", "secret-job")
    monkeypatch.setenv("PATH", "C:/Windows")

    env = _safe_env(Path("C:/worktree"), Path("C:/tmp/agent-memory.db"))

    assert "OPENAI_API_KEY" not in env
    assert "HARNESS_JOB_API_KEY" not in env
    assert env["AGENT_MEMORY_DB_PATH"].endswith("agent-memory.db")
    assert env["HARNESS_RSL_MODE"] == "off"
    assert env["PYTHONPATH"].endswith("python")


def test_run_suite_in_worktree_uses_the_injected_runner():
    calls = []

    def runner(root, config):
        calls.append((root, config.dataset))
        return {"ok": True, "aggregates": {}, "measuredTrials": 0}

    result = run_suite_in_worktree(
        Path("C:/worktree"), BenchmarkConfig(dataset="benchmark_v1"),
        run_fn=runner,
    )
    assert result["ok"] is True
    assert calls == [(Path("C:/worktree"), "benchmark_v1")]


def test_run_candidate_benchmark_runs_baseline_then_candidate():
    calls = []
    released = []
    applied = []

    def prepare(_candidate):
        return PreparedWorktree(
            id="cw-test",
            root=Path("C:/worktree"),
            apply=lambda: applied.append(True) or {"ok": True},
            release=lambda: released.append(True),
        )

    def run_suite(root, config):
        calls.append((root, config.target_dimension))
        return _suite(0.7 if len(calls) == 1 else 0.85)

    result = run_candidate_benchmark(
        {"id": "evo_1", "proposedOps": []},
        config=BenchmarkConfig(target_dimension="task_success"),
        prepare=prepare,
        run_suite=run_suite,
    )

    assert result["ok"] is True
    assert result["passed"] is True
    assert result["benchmark"] == "MEASURED"
    assert result["decisionRecord"]["accepted"] is True
    assert len(calls) == 2
    assert applied == [True]
    assert released == [True]


def test_canary_split_can_reject_an_accepted_validation_win():
    rates = iter([0.7, 0.9, 0.8, 0.5])
    calls = []

    def run_suite(_root, _config):
        calls.append(_config.split)
        return _suite(next(rates))

    def prepare(_candidate):
        return PreparedWorktree(
            id="cw-test", root=Path("C:/worktree"),
            apply=lambda: {"ok": True}, release=lambda: None,
        )

    result = run_candidate_benchmark(
        {"id": "evo_1"},
        config=BenchmarkConfig(split="validation", canary_split="held_out"),
        prepare=prepare,
        run_suite=run_suite,
    )

    assert result["ok"] is True
    assert result["passed"] is False
    assert result["canary"]["decision"] == "canary_rejected"
    assert calls == ["validation", "held_out", "validation", "held_out"]


def test_run_candidate_benchmark_refuses_when_apply_fails():
    released = []

    def prepare(_candidate):
        return PreparedWorktree(
            id="cw-test",
            root=Path("C:/worktree"),
            apply=lambda: {"ok": False, "refused": True, "code": "RSL_FROZEN_TARGET"},
            release=lambda: released.append(True),
        )

    result = run_candidate_benchmark(
        {"id": "evo_1"}, prepare=prepare,
        run_suite=lambda root, config: _suite(0.7),
    )

    assert result["ok"] is False
    assert result["benchmark"] == "UNMEASURED"
    assert result["decision"] == "benchmark_apply_refused"
    assert released == [True]


def test_run_candidate_benchmark_reports_a_baseline_failure():
    released = []

    def prepare(_candidate):
        return PreparedWorktree(
            id="cw-test",
            root=Path("C:/worktree"),
            apply=lambda: {"ok": True},
            release=lambda: released.append(True),
        )

    result = run_candidate_benchmark(
        {"id": "evo_1"}, prepare=prepare,
        run_suite=lambda root, config: {"ok": False, "error": "BENCHMARK_TIMEOUT"},
    )

    assert result["ok"] is False
    assert result["decision"] == "benchmark_baseline_failed"
    assert released == [True]
