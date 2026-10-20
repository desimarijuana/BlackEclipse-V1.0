"""RSL verification paths.

The approved R4 scope is deliberately honest:

* **Code patches** are verified by their owning tests in a disposable worktree.
  They are recorded with `benchmark="UNMEASURED"` and can never claim a
  benchmark delta — a worktree code patch is invisible to the snapshot-based
  candidate invoker.
* **Surface/skill candidates** are verified with the real evaluator through
  `CandidateAgentInvoker`; only these can claim a measured benchmark delta.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from ..code.evolution_service import evaluate as evaluate_code_candidate
from ..evaluation.candidate_invoker import (
    CandidateAgentInvoker,
    SnapshotError,
    validate_snapshot,
)
from ..evaluation.improvement import ImprovementProposal, evaluate_candidate
from ..evaluation.provenance import task_fingerprint_digest
from ..evaluation.runner import EvaluationRunner
from ..evaluation.store import EvaluationStore
from ..evaluation.tasks import (
    SPLITS,
    TaskValidationError,
    dataset_checksum,
    load_builtin_dataset,
    select_tasks,
)
from .models import HarnessSnapshot


class SurfaceConfigError(ValueError):
    """A stored surface candidate cannot be verified as configured."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


def verify_code(
    store: Any,
    candidate_id: str,
    *,
    ctx: Any,
    actor: Any,
) -> dict[str, Any]:
    """Run the owning tests in a worktree. No benchmark claim is made."""
    result = evaluate_code_candidate(store, candidate_id, ctx=ctx, actor=actor)
    passed = bool(result.get("passed"))
    return {
        "ok": bool(result.get("ok")),
        "passed": passed,
        "refused": bool(result.get("refused")),
        "code": result.get("code"),
        "detail": result.get("detail"),
        "report": result.get("report") or {},
        "benchmark": "UNMEASURED",
        "decision": "tests_only",
    }


def verify_code_benchmark(
    store: Any,
    candidate: dict[str, Any],
    *,
    config: Any,
    eval_store: Optional[Any] = None,
) -> dict[str, Any]:
    """Measure a code candidate in a patched worktree, if explicitly enabled.

    This is the only code path that can return a measured benchmark delta. It is
    opt-in (`HARNESS_RSL_CODE_BENCHMARK`) because it executes the patched harness
    in a child process. The candidate never lands here; the decision is returned
    to the conductor and the existing operator promotion remains the write path.
    """
    if not bool(getattr(config, "code_benchmark", False)):
        return {
            "ok": True,
            "passed": True,
            "benchmark": "UNMEASURED",
            "decision": "code_benchmark_disabled",
        }
    from ..evaluation.worktree_invoker import (  # noqa: PLC0415
        BenchmarkConfig,
        run_candidate_benchmark,
    )

    settings = BenchmarkConfig(
        dataset="benchmark_v1",
        split="validation",
        trials=max(1, int(getattr(config, "trials", 1) or 1)),
        target_dimension="task_success",
        min_improvement=0.0,
    )
    result = run_candidate_benchmark(
        candidate, config=settings, eval_store=eval_store,
    )
    return {
        **result,
        "decisionRecord": result.get("decisionRecord"),
    }


def verify_skill(
    *,
    registry: Any,
    skill_id: str,
    version: str,
    actor: Any,
) -> dict[str, Any]:
    """Run the existing skill evaluation. No benchmark claim is made here."""
    from ..skills.versioning import evaluate_version  # noqa: PLC0415

    result = evaluate_version(registry, skill_id, version, actor=actor)
    record = result.get("record") or {}
    return {
        "ok": bool(result.get("ok")),
        "passed": record.get("decision") == "eligible_for_activation",
        "benchmark": "UNMEASURED",
        "decision": "skill_evaluation",
        "result": result,
    }


def _surface_tasks(payload: dict[str, Any]) -> tuple[Any, list[Any], str]:
    """Resolve the exact validation tasks a stored surface candidate named."""
    dataset_name = str(payload.get("dataset") or "benchmark_v1")
    try:
        dataset = load_builtin_dataset(dataset_name)
    except TaskValidationError as exc:
        raise SurfaceConfigError("SURFACE_DATASET_UNKNOWN", str(exc)) from exc
    split = str(payload.get("split") or "validation").strip().lower()
    if split not in SPLITS:
        raise SurfaceConfigError(
            "SURFACE_SPLIT_INVALID",
            f"unknown split {split!r} (expected one of {', '.join(SPLITS)})",
        )
    tasks = select_tasks(dataset, split=split)
    wanted = [str(task_id) for task_id in (payload.get("taskIds") or []) if str(task_id)]
    if wanted:
        wanted_set = set(wanted)
        tasks = [task for task in tasks if task.id in wanted_set]
        missing = sorted(wanted_set - {task.id for task in tasks})
        if missing:
            raise SurfaceConfigError(
                "SURFACE_TASK_UNKNOWN",
                "tasks are not in the selected split: " + ", ".join(missing),
            )
    if not tasks:
        raise SurfaceConfigError("SURFACE_NO_TASKS", "the surface experiment selected no tasks")
    return dataset, tasks, split


async def _run_baseline(
    store: Any,
    eval_store: EvaluationStore,
    base: HarnessSnapshot,
    tasks: list[Any],
    *,
    dataset: Any,
    split: str,
    trials: int,
    seed: Optional[int],
    temperature: Optional[float],
    proposal_id: str,
) -> dict[str, Any]:
    """Run the base snapshot on the same tasks; this is the comparison floor."""
    invoker = CandidateAgentInvoker(store, base, base=base)
    runner = EvaluationRunner(store, invoker=invoker, eval_store=eval_store)
    run_id = f"rsl-baseline-{proposal_id}-{uuid.uuid4().hex[:8]}"
    suite = await runner.run_suite(
        tasks,
        dataset_name=str(getattr(dataset, "name", "") or ""),
        dataset_version=str(getattr(dataset, "version", "") or ""),
        dataset_checksum=dataset_checksum(tasks),
        suite="surface-baseline",
        trials=trials,
        tier=0,
        persist=True,
        run_id=run_id,
        split=split,
        seed=seed,
        temperature=temperature,
        metadata={
            "kind": "rsl-baseline",
            "proposalId": proposal_id,
            "baseDigest": base.sourceDigest,
            "benchmark": "BASELINE",
        },
        extra_config={
            "kind": "rsl-baseline",
            "proposalId": proposal_id,
            "snapshotDigest": base.sourceDigest,
        },
    )
    return {
        "runId": run_id,
        "metrics": {
            "aggregates": dict(suite.aggregates),
            "categories": dict(suite.categories),
        },
        "measuredTrials": suite.measured_trials,
    }


def _baseline_from_run(
    eval_store: EvaluationStore,
    run_id: str,
    *,
    base: HarnessSnapshot,
    tasks: list[Any],
    split: str,
) -> dict[str, Any]:
    """Reuse a recorded baseline only when its identity still matches."""
    run = eval_store.get_run(run_id)
    if run is None:
        raise SurfaceConfigError("SURFACE_BASELINE_NOT_FOUND", "the baseline run does not exist")
    metadata = run.get("metadata") or {}
    if metadata.get("kind") != "rsl-baseline":
        raise SurfaceConfigError(
            "SURFACE_BASELINE_INVALID", "the referenced run is not a surface baseline",
        )
    if metadata.get("baseDigest") != base.sourceDigest:
        raise SurfaceConfigError(
            "SURFACE_BASELINE_MISMATCH", "the baseline was measured on a different base snapshot",
        )
    if metadata.get("taskFingerprintDigest") != task_fingerprint_digest(tasks):
        raise SurfaceConfigError(
            "SURFACE_BASELINE_MISMATCH", "the baseline was measured on different tasks",
        )
    if metadata.get("split") != split:
        raise SurfaceConfigError(
            "SURFACE_BASELINE_MISMATCH", "the baseline was measured on a different split",
        )
    aggregates = {
        str(row.get("dimension")): row.get("value")
        for row in eval_store.list_metrics(run_id, scope="overall")
        if row.get("dimension") and row.get("value") is not None
    }
    if "task_success" not in aggregates:
        raise SurfaceConfigError(
            "SURFACE_BASELINE_UNMEASURED", "the baseline has no measured task_success",
        )
    return {"runId": run_id, "metrics": {"aggregates": aggregates}}


async def verify_surface_candidate(
    store: Any,
    candidate: dict[str, Any],
    *,
    config: Any,
    eval_store: Optional[Any] = None,
    skill_store: Optional[Any] = None,
) -> dict[str, Any]:
    """Verify a stored surface candidate through the measured benchmark path.

    The base and candidate snapshots are read from the candidate row, the exact
    tasks/split are resolved, and the baseline is either the recorded run named
    in the config or a fresh run of the SAME base snapshot. The evaluator's
    acceptance decision is persisted, so metrics never infer it.
    """
    payload = dict(candidate.get("surfaceConfig") or {})
    if not payload:
        raise SurfaceConfigError(
            "SURFACE_CONFIG_MISSING", "the candidate carries no surface configuration",
        )
    try:
        base = HarnessSnapshot(**dict(payload.get("base") or {}))
        snapshot = HarnessSnapshot(**dict(payload.get("snapshot") or {}))
    except (TypeError, ValueError) as exc:
        raise SurfaceConfigError("SURFACE_SNAPSHOT_INVALID", str(exc)) from exc
    try:
        validate_snapshot(
            base, snapshot,
            known_skill_ids=set(snapshot.skillDraftIds) if skill_store is not None else None,
        )
    except SnapshotError as exc:
        raise SurfaceConfigError(exc.code, exc.detail) from exc

    dataset, tasks, split = _surface_tasks(payload)
    run_store = eval_store or EvaluationStore(store)
    proposal_id = str(candidate.get("id") or "")
    try:
        trials = max(1, min(int(payload.get("trials") or getattr(config, "trials", 3)), 10))
        seed_value = payload.get("seed")
        seed = int(seed_value) if seed_value not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise SurfaceConfigError(
            "SURFACE_CONFIG_INVALID", "trials/seed must be integers",
        ) from exc
    target_dimension = str(payload.get("targetDimension") or "task_success")

    baseline_run_id = str(payload.get("baselineRunId") or "").strip()
    if baseline_run_id:
        baseline = _baseline_from_run(
            run_store, baseline_run_id, base=base, tasks=tasks, split=split,
        )
    else:
        baseline = await _run_baseline(
            store, run_store, base, tasks,
            dataset=dataset, split=split, trials=trials, seed=seed,
            temperature=snapshot.temperature, proposal_id=proposal_id,
        )

    result = await verify_surface(
        store=store,
        snapshot=snapshot,
        base=base,
        tasks=tasks,
        baseline_metrics=baseline["metrics"],
        target_dimension=target_dimension,
        proposal_id=proposal_id,
        eval_store=run_store,
        split=split,
        trials=trials,
        seed=seed,
        temperature=snapshot.temperature,
        skill_store=skill_store,
        metadata={
            "kind": "rsl",
            "proposalId": proposal_id,
            "sourceCategory": candidate.get("sourceCategory"),
            "subjectType": str(candidate.get("subjectType") or "surface"),
            "scope": str(
                (candidate.get("surfaceConfig") or {}).get("scope") or "global"
            ),
            "targetDimension": target_dimension,
            "datasetName": getattr(dataset, "name", ""),
            "datasetVersion": getattr(dataset, "version", ""),
            "split": split,
            "taskIds": [task.id for task in tasks],
            "baselineRunId": baseline["runId"],
            "baseDigest": base.sourceDigest,
            "snapshotDigest": snapshot.sourceDigest,
            "surface": True,
        },
    )
    return {
        **result,
        "baselineRunId": baseline["runId"],
        "targetDimension": target_dimension,
    }


async def verify_surface(
    *,
    store: Any,
    snapshot: Any,
    base: Any,
    tasks: list[Any],
    baseline_metrics: dict[str, Any],
    target_dimension: str,
    proposal_id: str,
    eval_store: Optional[Any] = None,
    split: str = "validation",
    trials: int = 3,
    seed: Optional[int] = None,
    temperature: Optional[float] = None,
    skill_store: Optional[Any] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Benchmark a validated snapshot through the real evaluator.

    This is the ONLY R4 path that can return a measured benchmark delta. The
    candidate runs in the isolated invoker; the comparison is recorded on an
    `EvaluationRun` with the RSL experiment metadata.
    """
    invoker = CandidateAgentInvoker(store, snapshot, base=base, skill_store=skill_store)
    run_store = eval_store or EvaluationStore(store)
    runner = EvaluationRunner(store, invoker=invoker, eval_store=run_store)
    proposal = ImprovementProposal(
        id=proposal_id,
        description=f"RSL surface {snapshot.sourceDigest[:12]}",
        target_dimension=target_dimension,
        apply=lambda: None,
    )
    payload = {
        **(metadata or {}),
        "kind": "rsl",
        "proposalId": proposal_id,
        "benchmark": "MEASURED",
    }
    decision = await evaluate_candidate(
        runner, tasks, proposal, baseline_metrics,
        trials=trials, persist=True, metadata=payload, split=split,
        seed=seed, temperature=temperature,
        extra_config={"snapshotDigest": snapshot.sourceDigest},
    )
    # Measurement honesty: the persisted run must carry the decision the
    # evaluator actually reached (accepted/reason/regressions/measured), so R8
    # metrics never have to infer an outcome from a score it cannot see.
    if decision.run_id:
        try:
            run = run_store.get_run(decision.run_id) or {}
            run_store.update_run(
                decision.run_id,
                metadata={**(run.get("metadata") or {}), **decision.to_dict()},
            )
        except Exception:  # noqa: BLE001 - recording must not undo the verification
            pass
    return {
        "ok": decision.accepted,
        "passed": decision.accepted,
        "benchmark": "MEASURED",
        "decision": "benchmark",
        "runId": decision.run_id,
        "measured": decision.measured,
        "decisionRecord": decision.to_dict(),
    }


__all__ = [
    "SurfaceConfigError",
    "verify_code",
    "verify_code_benchmark",
    "verify_skill",
    "verify_surface",
    "verify_surface_candidate",
]
