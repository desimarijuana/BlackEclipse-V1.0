"""The self-improvement evaluation loop.

    Run → Evaluate → Find failures → Classify → Identify cause → Generate
    improvement → Apply improvement → Run evaluation → Compare baseline →
    Accept only if the improvement is VERIFIED.

A proposed improvement NEVER automatically becomes the new baseline. It is
accepted only when (a) the targeted dimension improves and (b) no critical
capability regresses — the anti-regression rule. Evidence is the suite comparison,
not a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .regression import DEFAULT_GATES, detect_regressions


@dataclass
class ImprovementProposal:
    id: str
    description: str
    #: the dimension the improvement is meant to raise (higher-is-better)
    target_dimension: str
    #: how to apply the change (returns anything; the loop only needs it to have run)
    apply: Callable[[], Any]
    #: revert the change if it is rejected
    revert: Optional[Callable[[], Any]] = None

    def run(self) -> Any:
        return self.apply()


@dataclass
class ImprovementDecision:
    proposal_id: str
    accepted: bool
    reason: str
    target_before: Optional[float] = None
    target_after: Optional[float] = None
    regressions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposalId": self.proposal_id,
            "accepted": self.accepted,
            "reason": self.reason,
            "targetBefore": self.target_before,
            "targetAfter": self.target_after,
            "regressions": self.regressions,
            "warnings": self.warnings,
        }


def summarize_failures(suite: Any) -> dict[str, int]:
    """Classify a suite's failures by the taxonomy label (the loop's 'cause')."""
    counts: dict[str, int] = {}
    for task_result in suite.tasks:
        for trial in task_result.trials:
            if trial.passed or trial.unmeasured:
                continue
            for label in trial.labels:
                counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def propose_improvements(failure_counts: dict[str, int]) -> list[dict[str, Any]]:
    """Map failure labels to the component a change should target.

    This names WHERE to change; generating and applying the change is the
    caller's job (a skill patch, a config flag, a prompt segment). The loop exists
    to VERIFY a change with evidence, never to invent one.
    """
    targets = {
        "tool_selection": "tool routing / agent allowlist",
        "tool_arguments": "tool schemas / argument extraction",
        "tool_execution": "tool implementation reliability",
        "tool_result_interpretation": "tool-result rendering / prompt",
        "calculation": "deterministic calculator coverage",
        "citation": "citation assembly",
        "research": "research engine / source selection",
        "evidence": "evidence retrieval",
        "memory": "memory retention/retrieval policy",
        "hallucination": "evidence grounding / refusal",
        "safety": "policy / authorization boundary",
        "coding": "code repair loop",
        "planning": "planner / replan directive",
        "timeout": "time budgets / long-horizon checkpointing",
        "context": "context budget management",
        "infrastructure": "runtime reliability",
    }
    return [
        {"label": label, "count": count, "target": targets.get(label, label)}
        for label, count in failure_counts.items()
    ]


async def evaluate_candidate(
    runner: Any,
    tasks: list[Any],
    proposal: ImprovementProposal,
    baseline_metrics: dict[str, Any],
    *,
    min_improvement: float = 0.0,
    gates: Optional[tuple] = None,
    trials: Optional[int] = None,
) -> ImprovementDecision:
    """Apply a proposal, evaluate it, and accept only if verified.

    Rejection reverts the change. The baseline is never overwritten here.
    """
    proposal.run()
    suite = await runner.run_suite(
        tasks, dataset_name="improvement", trials=trials, tier=0, persist=False,
    )
    baseline_agg = baseline_metrics.get("aggregates", baseline_metrics)
    current_agg = suite.aggregates
    target_before = baseline_agg.get(proposal.target_dimension)
    target_after = current_agg.get(proposal.target_dimension)
    regression_outcome = detect_regressions(baseline_metrics, suite_metrics(suite), gates or DEFAULT_GATES)

    improved = (
        target_before is not None and target_after is not None
        and (target_after - target_before) > min_improvement
    )
    critical_regression = any(
        r["dimension"] in ("safety_score", "hallucination_rate", "task_success")
        for r in regression_outcome["regressions"]
    )

    if not improved:
        if proposal.revert:
            proposal.revert()
        return ImprovementDecision(
            proposal_id=proposal.id, accepted=False,
            reason=f"target {proposal.target_dimension} did not improve "
                   f"({target_before} → {target_after})",
            target_before=target_before, target_after=target_after,
            regressions=regression_outcome["regressions"], warnings=regression_outcome["warnings"],
        )
    if critical_regression:
        if proposal.revert:
            proposal.revert()
        return ImprovementDecision(
            proposal_id=proposal.id, accepted=False,
            reason="target improved but a critical capability regressed",
            target_before=target_before, target_after=target_after,
            regressions=regression_outcome["regressions"], warnings=regression_outcome["warnings"],
        )
    return ImprovementDecision(
        proposal_id=proposal.id, accepted=True,
        reason=f"target {proposal.target_dimension} improved "
               f"({target_before} → {target_after}) with no critical regression",
        target_before=target_before, target_after=target_after,
        regressions=regression_outcome["regressions"], warnings=regression_outcome["warnings"],
    )


def suite_metrics(suite: Any) -> dict[str, Any]:
    return {"aggregates": dict(suite.aggregates)}


async def run_loop(
    runner: Any,
    tasks: list[Any],
    proposals: list[ImprovementProposal],
    baseline_metrics: dict[str, Any],
    *,
    min_improvement: float = 0.0,
) -> dict[str, Any]:
    """Evaluate every proposal against the SAME baseline; accept the verified ones.

    The baseline is not mutated by an accepted proposal — promoting a new baseline
    is a separate, explicit step (see ``baseline.promote_if_improved``).
    """
    decisions = []
    for proposal in proposals:
        decision = await evaluate_candidate(
            runner, tasks, proposal, baseline_metrics, min_improvement=min_improvement,
        )
        decisions.append(decision.to_dict())
    return {
        "baseline": baseline_metrics,
        "decisions": decisions,
        "accepted": [d["proposalId"] for d in decisions if d["accepted"]],
    }


__all__ = [
    "ImprovementDecision",
    "ImprovementProposal",
    "evaluate_candidate",
    "propose_improvements",
    "run_loop",
    "summarize_failures",
]
