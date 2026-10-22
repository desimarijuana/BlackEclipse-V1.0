"""RSL R2 — comparable runs: identity, fingerprints, splits and measured-only acceptance."""

from __future__ import annotations

import copy

import pytest

from harness.evaluation.baseline import get_baseline, save_baseline
from harness.evaluation.config import GRADER_API_VERSION
from harness.evaluation.improvement import ImprovementProposal, evaluate_candidate
from harness.evaluation.provenance import (
    AGENT_VERSION,
    ProvenanceError,
    require_provenance,
)
from harness.evaluation.runner import EvaluationRunner, ScriptedAgentInvoker
from harness.evaluation.scoring import score_trial
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import (
    Dataset,
    EvaluationTask,
    TaskValidationError,
    load_all_builtin,
    load_builtin_dataset,
    select_tasks,
)
from harness.evaluation.trajectory import Trajectory, TrajectoryEvent
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


@pytest.fixture()
def runner(store):
    return EvaluationRunner(
        store,
        invoker=ScriptedAgentInvoker(store),
        eval_store=EvaluationStore(store),
    )


def _task(task_id: str, *, split: str | None = None) -> EvaluationTask:
    metadata = {"agent_script": [{"type": "final", "content": "READY"}]}
    if split:
        metadata["split"] = split
    return EvaluationTask.from_dict({
        "id": task_id,
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "say READY"},
        "expected_output": {"equals": "READY"},
        "metadata": metadata,
    })


def _dataset(tasks: list[EvaluationTask], *, split: str | None = None) -> Dataset:
    metadata = {"split": split} if split else {}
    return Dataset(name="rsl-provenance", version="1", tasks=tasks, metadata=metadata)


@pytest.mark.asyncio
async def test_persisted_suite_records_complete_provenance(runner):
    task = _task("rsl.1")
    dataset = _dataset([task])
    suite = await runner.run_suite(
        [task],
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        dataset_checksum=dataset.checksum,
        trials=1,
        tier=0,
        persist=True,
        split="validation",
        seed=7,
        temperature=0.0,
        metadata={"kind": "rsl", "proposalId": "evo_1"},
    )

    run = runner.eval_store.get_run(suite.run_id)
    assert run is not None
    assert run["agentVersion"] == AGENT_VERSION
    assert run["gitCommit"] or run["metadata"]["gitCommitUnavailable"] is True
    assert run["datasetChecksum"] == dataset.checksum
    assert run["config"]["trials"] == 1
    assert run["config"]["tier"] == 0
    assert run["config"]["split"] == "validation"
    assert run["config"]["seed"] == 7
    assert run["config"]["temperature"] == 0.0
    assert run["config"]["graderVersion"] == GRADER_API_VERSION
    assert run["metadata"]["kind"] == "rsl"
    assert run["metadata"]["proposalId"] == "evo_1"
    assert run["metadata"]["graderVersion"] == GRADER_API_VERSION
    assert run["metadata"]["taskCount"] == 1
    assert run["metadata"]["taskFingerprintDigest"]
    assert run["metadata"]["measuredTrials"] == 1
    assert run["provider"] == "ollama"
    assert run["model"]
    require_provenance(run)

    stored = runner.eval_store.list_tasks()
    assert any(
        row["id"] == task.id and row["fingerprint"] == task.fingerprint()
        for row in stored
    )
    trials = runner.eval_store.list_trials(suite.run_id)
    assert trials
    assert trials[0]["score"]["graderVersion"] == GRADER_API_VERSION


@pytest.mark.asyncio
async def test_baseline_carries_run_identity(runner):
    task = _task("rsl.baseline")
    dataset = _dataset([task])
    suite = await runner.run_suite(
        [task], dataset_name=dataset.name, dataset_version=dataset.version,
        dataset_checksum=dataset.checksum, trials=1, persist=True, seed=3,
    )
    baseline_id = save_baseline(runner.eval_store, "main", suite)
    baseline = get_baseline(runner.eval_store, "main")
    assert baseline["id"] == baseline_id
    assert baseline["runId"] == suite.run_id
    assert baseline["datasetChecksum"] == dataset.checksum
    assert baseline["agentVersion"] == AGENT_VERSION
    assert baseline["gitCommit"] or baseline["config"]["gitCommitUnavailable"] is True
    assert baseline["config"]["graderVersion"] == GRADER_API_VERSION
    assert baseline["config"]["taskFingerprintDigest"]
    assert baseline["metrics"]["passRate"] == 1.0


def test_baseline_refuses_incomplete_provenance(runner):
    from types import SimpleNamespace

    incomplete = SimpleNamespace(
        run_id="run-bad", dataset_checksum="", agent_version=AGENT_VERSION,
        git_commit=None, config={}, metadata={}, tasks=[],
        aggregates={}, categories={}, tier=0,
    )
    with pytest.raises(ProvenanceError):
        save_baseline(runner.eval_store, "bad", incomplete)


@pytest.mark.asyncio
async def test_two_runs_share_the_task_set_and_differ_only_on_the_experiment_axis(runner):
    task = _task("rsl.compare")
    checksum = _dataset([task]).checksum

    async def run(axis: str):
        return await runner.run_suite(
            [task], dataset_name="rsl-provenance", dataset_version="1",
            dataset_checksum=checksum, trials=1, persist=True, seed=5,
            extra_config={"snapshotDigest": axis},
        )

    first = await run("a")
    second = await run("b")
    first_run = runner.eval_store.get_run(first.run_id)
    second_run = runner.eval_store.get_run(second.run_id)
    assert first_run is not None and second_run is not None
    assert first_run["datasetChecksum"] == second_run["datasetChecksum"] == checksum
    assert (
        first_run["metadata"]["taskFingerprintDigest"]
        == second_run["metadata"]["taskFingerprintDigest"]
    )
    differing = {
        key for key in first_run["config"]
        if first_run["config"].get(key) != second_run["config"].get(key)
    }
    assert differing == {"snapshotDigest"}


@pytest.mark.asyncio
async def test_require_provenance_refuses_each_missing_piece(runner):
    task = _task("rsl.2")
    suite = await runner.run_suite(
        [task], dataset_name="rsl-provenance", dataset_version="1",
        dataset_checksum=_dataset([task]).checksum, trials=1, persist=True,
    )
    run = runner.eval_store.get_run(suite.run_id)
    assert run is not None

    for field in ("datasetChecksum", "agentVersion"):
        broken = copy.deepcopy(run)
        broken[field] = None
        with pytest.raises(ProvenanceError):
            require_provenance(broken)

    broken = copy.deepcopy(run)
    broken["gitCommit"] = None
    broken["metadata"].pop("gitCommitUnavailable", None)
    with pytest.raises(ProvenanceError):
        require_provenance(broken)

    broken = copy.deepcopy(run)
    broken["config"] = {}
    with pytest.raises(ProvenanceError):
        require_provenance(broken)

    broken = copy.deepcopy(run)
    broken["config"]["split"] = ""
    with pytest.raises(ProvenanceError):
        require_provenance(broken)

    broken = copy.deepcopy(run)
    broken["metadata"] = {}
    with pytest.raises(ProvenanceError):
        require_provenance(broken)


def test_split_selection_and_built_in_splits():
    default = _task("t.default")
    optimization = _task("t.opt", split="optimization")
    held_out = _task("t.held", split="held_out")
    dataset = _dataset([default, optimization, held_out])

    assert [t.id for t in select_tasks(dataset, split="validation")] == ["t.default"]
    assert [t.id for t in select_tasks(dataset, split="optimization")] == ["t.opt"]
    assert [t.id for t in select_tasks(dataset, split="held_out")] == ["t.held"]
    with pytest.raises(TaskValidationError):
        select_tasks(dataset, split="not-a-split")

    release_task = _task("t.release")
    release_dataset = _dataset([release_task], split="release")
    assert [t.id for t in select_tasks(release_dataset, split="release")] == ["t.release"]

    assert len(select_tasks(load_builtin_dataset("benchmark_v1"), split="validation")) == 31
    assert len(select_tasks(load_builtin_dataset("routing_e2e_v1"), split="optimization")) == 4
    assert len(select_tasks(load_builtin_dataset("team_v1"), split="held_out")) == 2

    merged = load_all_builtin()
    # The built-in corpus is 68 tasks: benchmark_v1 (31) + construction_v1 (16)
    # + adversarial_v1 (4) + finance_v1 (5) = validation (56), routing_e2e_v1
    # (4) + replay_v1 (6) = optimization (10), team_v1 (2) = held_out.
    assert len(select_tasks(merged, split="validation")) == 56
    assert len(select_tasks(merged, split="optimization")) == 10
    assert len(select_tasks(merged, split="held_out")) == 2
    # No filter keeps every task for the release gate.
    assert len(select_tasks(merged)) == 68


def test_self_evolution_cost_stays_unmeasured_when_any_trial_is_unknown():
    from types import SimpleNamespace

    from harness.evaluation.repair_metrics import metrics_from_suite

    unknown = SimpleNamespace(
        unmeasured=False, passed=True,
        score=SimpleNamespace(cost=None, grader_results=[]),
    )
    suite = SimpleNamespace(tasks=[SimpleNamespace(trials=[unknown])])
    assert metrics_from_suite(suite)["cost_per_success"] is None


def test_unknown_cost_and_latency_stay_none():
    trajectory = Trajectory(run_id="r", task_id="t", trial_id="t0")
    trajectory.events = [
        TrajectoryEvent(
            index=0, type="model.completed", at="",
            data={"promptTokens": 3, "completionTokens": 2, "totalTokens": 5},
        ),
    ]
    metrics = trajectory.derive_metrics()
    assert metrics["cost"] is None
    assert metrics["latencyMs"] is None

    score = score_trial(_task("t.cost"), trajectory, [])
    assert score.cost is None
    assert score.latency_ms is None
    assert score.to_dict()["costKnown"] is False
    assert score.to_dict()["latencyKnown"] is False


class _UnmeasuredSuite:
    aggregates = {"task_success": None, "safety_score": 1.0}
    measured_trials = 0
    run_id = "evalrun-unmeasured"


class _UnmeasuredRunner:
    async def run_suite(self, tasks, **kwargs):
        return _UnmeasuredSuite()


@pytest.mark.asyncio
async def test_unmeasured_candidate_is_rejected_and_reverted():
    calls = {"reverted": 0}
    proposal = ImprovementProposal(
        id="unmeasured", description="no measurement", target_dimension="task_success",
        apply=lambda: None,
        revert=lambda: calls.__setitem__("reverted", calls["reverted"] + 1),
    )
    decision = await evaluate_candidate(
        _UnmeasuredRunner(), [], proposal,
        {"aggregates": {"task_success": 0.5, "safety_score": 1.0}},
    )
    assert decision.accepted is False
    assert decision.measured == 0
    assert decision.run_id == "evalrun-unmeasured"
    assert "unmeasured" in decision.reason.lower()
    assert calls["reverted"] == 1


class _CapturingRunner:
    def __init__(self) -> None:
        self.kwargs = {}

    async def run_suite(self, tasks, **kwargs):
        self.kwargs = kwargs

        class Suite:
            aggregates = {"task_success": 0.9, "safety_score": 1.0}
            measured_trials = 3
            run_id = "evalrun-candidate"

        return Suite()


@pytest.mark.asyncio
async def test_improvement_passes_provenance_to_the_candidate_run():
    runner = _CapturingRunner()
    proposal = ImprovementProposal(
        id="persisted", description="raise success", target_dimension="task_success",
        apply=lambda: None,
    )
    decision = await evaluate_candidate(
        runner, [], proposal,
        {"aggregates": {"task_success": 0.5, "safety_score": 1.0}},
        persist=True, run_id="evalrun-candidate",
        metadata={"kind": "rsl", "proposalId": "evo_1"},
        split="validation", seed=11, temperature=0.2,
        extra_config={"snapshotDigest": "abc"},
    )
    assert decision.accepted is True
    assert decision.measured == 3
    assert decision.run_id == "evalrun-candidate"
    assert runner.kwargs["persist"] is True
    assert runner.kwargs["run_id"] == "evalrun-candidate"
    assert runner.kwargs["metadata"]["proposalId"] == "evo_1"
    assert runner.kwargs["split"] == "validation"
    assert runner.kwargs["seed"] == 11
    assert runner.kwargs["temperature"] == 0.2
    assert runner.kwargs["extra_config"]["snapshotDigest"] == "abc"
