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

from typing import Any, Optional

from ..code.evolution_service import evaluate as evaluate_code_candidate
from ..evaluation.candidate_invoker import CandidateAgentInvoker
from ..evaluation.improvement import ImprovementProposal, evaluate_candidate
from ..evaluation.runner import EvaluationRunner
from ..evaluation.store import EvaluationStore


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
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Benchmark a validated snapshot through the real evaluator.

    This is the ONLY R4 path that can return a measured benchmark delta. The
    candidate runs in the isolated invoker; the comparison is recorded on an
    `EvaluationRun` with the RSL experiment metadata.
    """
    invoker = CandidateAgentInvoker(store, snapshot, base=base)
    runner = EvaluationRunner(
        store, invoker=invoker, eval_store=eval_store or EvaluationStore(store),
    )
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
    return {
        "ok": decision.accepted,
        "passed": decision.accepted,
        "benchmark": "MEASURED",
        "decision": "benchmark",
        "runId": decision.run_id,
        "measured": decision.measured,
        "decisionRecord": decision.to_dict(),
    }


__all__ = ["verify_code", "verify_skill", "verify_surface"]
