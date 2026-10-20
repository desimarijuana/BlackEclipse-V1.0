"""Round 4 (W7): the self-evolution metric block — measured or UNMEASURED.

Every metric is computed from real records or reported as None. The gate prints
`UNMEASURED` for a dimension with no samples; it never fabricates a number.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.evaluation.repair_metrics import (
    collect_self_evolution_metrics,
    metrics_from_recovery,
    metrics_from_suite,
    metrics_from_tasks,
)


def test_time_to_repair_is_the_median_over_resolved_incidents():
    incidents = [
        {"status": "resolved", "outcome": "succeeded",
         "createdAt": "2026-01-01T00:00:00+00:00", "resolvedAt": "2026-01-01T00:00:10+00:00"},
        {"status": "resolved", "outcome": "failed",
         "createdAt": "2026-01-01T00:00:00+00:00", "resolvedAt": "2026-01-01T00:00:30+00:00"},
        {"status": "open", "createdAt": "2026-01-01T00:00:00+00:00"},
    ]
    metrics = metrics_from_recovery(incidents)
    assert metrics["time_to_repair_ms"] == 20000.0
    assert metrics["self_repair_precision"] == 0.5


def test_recovery_metrics_are_unmeasured_without_records():
    metrics = metrics_from_recovery([])
    assert metrics["time_to_repair_ms"] is None
    assert metrics["self_repair_precision"] is None


def test_requirement_completeness_counts_goal_contract_criteria_only():
    tasks = [
        {"goalContract": {"deliverables": ["app"]}, "criteria": [
            {"required": True, "state": "PASSED"},
            {"required": True, "state": "PENDING"},
            {"required": False, "state": "PENDING"},
        ]},
        {"goalContract": None, "criteria": [{"required": True, "state": "PENDING"}]},
    ]
    assert metrics_from_tasks(tasks)["requirement_completeness"] == 0.5
    assert metrics_from_tasks([])["requirement_completeness"] is None


def test_suite_metrics_measure_cost_and_safety_honestly():
    def trial(passed, cost, safety_passed):
        return SimpleNamespace(
            unmeasured=False, passed=passed,
            score=SimpleNamespace(
                cost=cost,
                grader_results=[{"grader": "safety", "passed": safety_passed}],
            ),
        )

    suite = SimpleNamespace(tasks=[
        SimpleNamespace(trials=[trial(True, 0.4, True), trial(False, 0.6, True)]),
        SimpleNamespace(trials=[trial(True, 0.0, True)]),
    ])
    metrics = metrics_from_suite(suite)
    assert metrics["cost_per_success"] == 0.5
    assert metrics["unauthorized_action_rate"] == 0.0

    failing = SimpleNamespace(tasks=[
        SimpleNamespace(trials=[trial(False, 0.1, False)]),
    ])
    assert metrics_from_suite(failing)["unauthorized_action_rate"] == 1.0
    assert metrics_from_suite(failing)["cost_per_success"] is None  # no success


def test_the_block_reports_every_dimension_with_missing_sources_unmeasured():
    metrics = collect_self_evolution_metrics(suite=None, incidents=None, tasks=None)
    assert set(metrics) == {
        "time_to_repair_ms", "self_repair_precision", "requirement_completeness",
        "cost_per_success", "unauthorized_action_rate",
        "rsl_experiments", "rsl_accepted", "rsl_rejected", "rsl_unmeasured",
        "regression_rate",
    }
    assert all(value is None for value in metrics.values())


def test_rsl_metrics_split_measured_unmeasured_and_count_regressions():
    from harness.evaluation.repair_metrics import metrics_from_rsl_runs

    runs = [
        {
            "status": "completed",
            "suite": "rsl-recursion",
            "config": {"kind": "rsl-recursion", "benchmark": "MEASURED"},
            "metadata": {"composition": {"decision": "composed"}},
        },
        {
            "status": "completed",
            "suite": "rsl-code",
            "config": {"kind": "rsl", "benchmark": "UNMEASURED"},
            "metadata": {"decision": "tests_passed"},
        },
        {
            "status": "completed",
            "suite": "rsl-recursion",
            "config": {"kind": "rsl-recursion", "benchmark": "MEASURED"},
            "metadata": {
                "accepted": False,
                "composition": {"decision": "no_gain"},
                "regressions": [{"dimension": "task_success"}],
            },
        },
        {
            "status": "running",
            "suite": "rsl-code",
            "config": {"kind": "rsl"},
            "metadata": {},
        },
    ]
    metrics = metrics_from_rsl_runs(runs)
    assert metrics["rsl_experiments"] == 3
    assert metrics["rsl_accepted"] == 1
    assert metrics["rsl_rejected"] == 1
    assert metrics["rsl_unmeasured"] == 1
    assert metrics["regression_rate"] == 0.5

    assert metrics_from_rsl_runs([]) == {
        "rsl_experiments": 0,
        "rsl_accepted": 0,
        "rsl_rejected": 0,
        "rsl_unmeasured": 0,
        "regression_rate": None,
    }
    assert all(value is None for value in metrics_from_rsl_runs(None).values())


def test_rsl_run_metrics_read_real_evaluation_rows(tmp_path):
    from harness.evaluation.repair_metrics import rsl_runs_from_store
    from harness.evaluation.store import EvaluationStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        eval_store = EvaluationStore(store)
        eval_store.create_run(
            id="rsl-run", suite="rsl-code", datasetName="owning-tests",
            datasetVersion="1", datasetChecksum="x",
            config={"kind": "rsl", "benchmark": "UNMEASURED"},
            metadata={"decision": "tests_passed", "benchmark": "UNMEASURED"},
            status="completed",
        )
        runs = rsl_runs_from_store(store)
        assert [run["id"] for run in runs] == ["rsl-run"]
        metrics = collect_self_evolution_metrics(store=store)
        assert metrics["rsl_experiments"] == 1
        assert metrics["rsl_unmeasured"] == 1
        assert metrics["rsl_accepted"] == 0
    finally:
        store.close()


def test_the_gate_report_prints_the_block():
    from harness.evaluation.gate import format_gate_report

    suite = SimpleNamespace(
        passed=True, run_id="r1", tasks=[], categories={},
        aggregates={}, thresholds={},
        routing={"cases": 8, "misroute_rate": 0.0, "escalation_correct": 1.0},
        self_evolution={
            "time_to_repair_ms": None, "self_repair_precision": None,
            "requirement_completeness": None, "cost_per_success": 0.0,
            "unauthorized_action_rate": 0.0,
        },
    )
    lines = format_gate_report(suite)
    block = next(line for line in lines if line.strip().startswith("self-evolution:"))
    assert "time_to_repair_ms=UNMEASURED" in block
    assert "unauthorized_action_rate=0.0" in block


def test_the_recovery_route_measures_from_real_runtime_records(monkeypatch, tmp_path):
    """W7.3: the operator route reports the block from the REAL stores."""
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.persistence import AgentMemoryStore
    from harness.recovery.service import RecoveryService
    from harness.routers import recovery as recovery_router
    from harness.tasks.manager import TaskManager
    from harness.tasks.model import (
        CreatePlanInput, CreateTaskInput, GoalContract, TaskType,
    )
    from harness.tasks.store import TaskStore

    recovery = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    recorded = recovery.record_failure(
        code="TOOL_ERROR", message="a route refused", subsystem="web",
    )
    recovery.record_outcome(recorded["incidentId"], outcome="succeeded")

    manager = TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))
    plan = manager.create_plan(CreatePlanInput(name="goal"))
    task = manager.create_task(CreateTaskInput(
        title="goal", plan_id=plan.id, task_type=TaskType.CODE,
        goal_contract=GoalContract(acceptance=["tests pass"]),
    ))
    for criterion in manager.list_criteria(task.id):
        manager.set_criterion(criterion.id, "PASSED", evidence="run:r1")

    monkeypatch.setattr(
        recovery_router, "service",
        SimpleNamespace(recovery=recovery, tasks=manager),
    )
    metrics = recovery_router.recovery_metrics()
    assert metrics["self_repair_precision"] == 1.0
    assert metrics["time_to_repair_ms"] is not None
    assert metrics["requirement_completeness"] == 1.0
    assert metrics["cost_per_success"] is None  # no suite in this context
