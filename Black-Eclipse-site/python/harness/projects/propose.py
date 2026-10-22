"""What should this project do next? — proposals grounded in its own evidence.

The curated view says where a project stands. This module says what to do
about it, and it may only say it from **evidence the project actually holds**:
a strategy with no result, a result with too few trades, a strategy whose
trades only ever happened in two market regimes, a result whose tail is
unsafe, a strategy that does or does not survive a prop firm's drawdown rule.

Every proposal carries:

- the **evidence** it came from (an experiment id, a flag, a metric, a
  regime), so it can be checked;
- the **action** it proposes, as a concrete tool call with arguments, so it can
  be run without being re-invented.

A proposal that cannot cite its evidence is not made. There is no generic
advice here: if the project is complete, the honest answer is that there is
nothing to propose, and that is what comes back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .curate import curate_project

#: A result with fewer trades than this cannot tell an edge from luck.
THIN_SAMPLE_TRADES = 30

#: A Monte-Carlo whose probability of loss is above this has an unsafe tail.
HIGH_PROBABILITY_OF_LOSS = 35.0

#: A trade log whose regimes cover fewer than this share of the regimes the
#: classifier knows about has been tested in a narrow world.
MIN_REGIME_COVERAGE = 0.5


@dataclass
class Proposal:
    """One proposed next step."""

    id: str
    title: str
    rationale: str
    evidence: list[str] = field(default_factory=list)
    action: dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "action": dict(self.action),
            "priority": self.priority,
        }


def _strategy_spec(quant_store: Any, strategy_id: str) -> Optional[dict[str, Any]]:
    try:
        record = quant_store.get_strategy(strategy_id)
    except Exception:  # noqa: BLE001 - an unknown strategy is simply not evidence
        return None
    spec = (record or {}).get("spec") or {}
    universe = spec.get("universe") or {}
    return {
        "id": strategy_id,
        "symbols": list(universe.get("symbols") or []),
        "version": (record or {}).get("version"),
    }


def _experiment_artifact(quant_store: Any, experiment_id: str) -> Optional[dict[str, Any]]:
    try:
        return quant_store.read_artifact(experiment_id)
    except Exception:  # noqa: BLE001 - a missing artifact is simply not evidence
        return None


def _strategy_of(entry: dict[str, Any]) -> str:
    """The strategy an experiment belongs to, from its own metadata."""
    metadata = (entry.get("artifact") or {}).get("metadata") or {}
    return str(metadata.get("strategyId") or "")


def _symbols_of(entry: dict[str, Any]) -> list[str]:
    metadata = (entry.get("artifact") or {}).get("metadata") or {}
    return list(metadata.get("symbols") or [])


def _all_regimes() -> set[str]:
    """Every regime label the classifier can produce."""
    from ..quant.regime import TREND_LABELS, VOL_LABELS

    return {f"{trend}_{vol}" for trend in TREND_LABELS for vol in VOL_LABELS}


def _propose_missing_result(
    strategy: dict[str, Any], symbols: list[str],
) -> Optional[Proposal]:
    return Proposal(
        id=f"result:{strategy['id']}",
        title=f"Test {strategy['id']} - it has never been run",
        rationale=("the project holds this strategy but no result for it, so its "
                   "behaviour is unknown"),
        evidence=[f"strategy:{strategy['id']}"],
        action={
            "tool": "run_backtest",
            "args": {
                "strategyId": strategy["id"],
                **({"symbols": symbols} if symbols else {}),
                "save": True,
            },
        },
        priority=90,
    )


def _propose_thin_sample(experiment_id: str, metrics: dict[str, Any],
                         strategy_id: str = "", symbols: Optional[list[str]] = None
                         ) -> Optional[Proposal]:
    trades = metrics.get("trade_count")
    try:
        count = int(trades or 0)
    except (TypeError, ValueError):
        return None
    if count >= THIN_SAMPLE_TRADES:
        return None
    return Proposal(
        id=f"sample:{experiment_id}",
        title=f"Widen the sample for {experiment_id} - {count} trade(s) cannot "
              f"tell an edge from luck",
        rationale=(f"the result rests on {count} closed trade(s); below "
                   f"{THIN_SAMPLE_TRADES} the difference between an edge and luck is "
                   f"not measurable"),
        evidence=[f"experiment:{experiment_id}", f"trade_count={count}"],
        action={
            "tool": "run_backtest",
            "args": {
                "strategyId": strategy_id or experiment_id,
                **({"symbols": symbols} if symbols else {}),
                "save": True,
            },
        },
        priority=80,
    )


def _propose_regime_blind_spot(
    experiment_id: str, attribution: dict[str, Any],
    strategy_id: str = "", symbols: Optional[list[str]] = None,
) -> Optional[Proposal]:
    regimes = (attribution or {}).get("regimes") or {}
    if not regimes:
        return None
    known = _all_regimes()
    covered = set(regimes.keys())
    share = len(covered & known) / max(1, len(known))
    if share >= MIN_REGIME_COVERAGE:
        return None
    missing = sorted(known - covered)
    return Proposal(
        id=f"regimes:{experiment_id}",
        title=f"{experiment_id} only ever traded in {len(covered)} of the "
              f"{len(known)} market regimes",
        rationale=(f"the tested trades only ever happened in "
                   f"{', '.join(sorted(covered))}; the strategy has never been "
                   f"observed in {', '.join(missing)}, so its behaviour there is "
                   f"unknown"),
        evidence=[f"experiment:{experiment_id}"] + [f"regime:{r}" for r in sorted(covered)],
        action={
            "tool": "run_backtest",
            "args": {
                "strategyId": strategy_id or experiment_id,
                **({"symbols": symbols} if symbols else {}),
                "save": True,
            },
        },
        priority=70,
    )


def _propose_unsafe_tail(experiment_id: str, monte_carlo: dict[str, Any],
                          strategy_id: str = "") -> Optional[Proposal]:
    probability = monte_carlo.get("probabilityOfLoss")
    percentiles = monte_carlo.get("returnPercentiles") or {}
    p5 = percentiles.get("p5")
    risky = (probability is not None and float(probability) > HIGH_PROBABILITY_OF_LOSS) or \
            (p5 is not None and float(p5) <= 0)
    if not risky:
        return None
    detail = (f"{float(probability):.1f}% of resampled paths finish below zero"
              if probability is not None else "the 5th-percentile return is not positive")
    return Proposal(
        id=f"tail:{experiment_id}",
        title=f"The tail of {experiment_id} is the problem, not the average",
        rationale=(f"{detail}; the expected return can look fine while the "
                   f"outcomes a trader would actually live through are not"),
        evidence=[f"experiment:{experiment_id}", f"probabilityOfLoss={probability}",
                   f"p5={p5}"],
        action={
            "tool": "run_robustness_analysis",
            "args": {
                "strategyId": strategy_id or experiment_id,
                "costMultipliers": [1.0, 2.0, 5.0],
                "save": True,
            },
        },
        priority=75,
    )


def _propose_firm_fit(
    experiment_id: str, trades: list[dict[str, Any]], firm: str = "topstep",
    size: str = "50k",
) -> Optional[Proposal]:
    """Does this strategy survive a prop firm's rules?"""
    if not trades:
        return None
    try:
        from ..quant.propfirm import get_spec
        from ..quant.propfirm_mc import PropFirmMonteCarloConfig, run_prop_firm_monte_carlo

        spec = get_spec(firm)
        account = spec.size(size)
        # The firm's OWN account size is the capital its rules apply to.
        report = run_prop_firm_monte_carlo(
            trades, spec, account,
            PropFirmMonteCarloConfig(simulations=200, seed=42))
    except Exception:  # noqa: BLE001 - a firm we cannot evaluate is not evidence
        return None
    if not report.get("available"):
        return None
    probability = report["monteCarlo"]["passProbability"]
    verdict = (f"passes {spec.name} {account.label} in {probability:.0f}% of "
               f"resampled paths" if probability >= 50 else
               f"does NOT survive {spec.name} {account.label} - it passes in only "
               f"{probability:.0f}% of resampled paths")
    return Proposal(
        id=f"firm:{experiment_id}:{firm}:{size}",
        title=f"{experiment_id} {verdict}",
        rationale=("the evaluation rules were applied to this strategy's own trade "
                   "sequence, resampled by trading day"),
        evidence=[f"experiment:{experiment_id}", f"firm={firm}", f"size={size}",
                  f"passProbability={probability}"],
        action={
            "tool": "run_prop_firm_simulation",
            "args": {"firm": firm, "size": size, "experimentId": experiment_id},
        },
        priority=60 if probability >= 50 else 85,
    )


def propose_next(
    project_store: Any,
    project_id: str,
    *,
    quant_store: Any = None,
    firm: str = "topstep",
    firm_size: str = "50k",
    max_proposals: int = 6,
) -> dict[str, Any]:
    """Propose the next steps for a project, from its own evidence."""
    from .policy import get_auto_run_store

    digest = curate_project(project_store, project_id,
                            auto_run_store=get_auto_run_store())
    if digest is None:
        return {"available": False, "reason": f"no project {project_id!r}",
                "proposals": []}

    proposals: list[Proposal] = []
    strategies: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    monte_carlos: list[dict[str, Any]] = []
    # A rule that could not be evaluated is REPORTED, not silently skipped: a
    # broken rule must never look like a project with nothing to propose.
    skipped: list[dict[str, str]] = []

    def attempt(rule: Any, *args: Any, **kwargs: Any) -> Optional[Proposal]:
        try:
            return rule(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a broken rule is reported
            skipped.append({"rule": getattr(rule, "__name__", "rule"),
                            "error": str(exc)[:200]})
            return None

    for member in digest.members:
        if member.kind == "strategy":
            spec = _strategy_spec(quant_store, member.ref) if quant_store else None
            strategies.append(spec or {"id": member.ref, "symbols": []})
        elif member.kind == "experiment":
            artifact = (_experiment_artifact(quant_store, member.ref)
                        if quant_store else None)
            if artifact:
                results.append({"id": member.ref, "artifact": artifact})
                if (artifact.get("regimeAttribution") is not None
                        or artifact.get("probabilityOfLoss") is not None
                        or artifact.get("returnPercentiles") is not None):
                    monte_carlos.append({"id": member.ref, "artifact": artifact})

    project_symbols = list(getattr(project_store.get(project_id), "symbols", []) or [])

    # 1. a strategy with no result at all
    for strategy in strategies:
        has_result = any(
            result["artifact"].get("metadata", {}).get("strategyId") == strategy["id"]
            for result in results
        )
        if not has_result:
            symbols = strategy["symbols"] or project_symbols
            proposal = attempt(_propose_missing_result, strategy, symbols)
            if proposal:
                proposals.append(proposal)

    # 2. a result with too few trades
    for result in results:
        metrics = result["artifact"].get("metrics") or {}
        proposal = attempt(_propose_thin_sample, result["id"], metrics,
                           _strategy_of(result), _symbols_of(result))
        if proposal:
            proposals.append(proposal)

    # 3. a strategy that only ever traded in a few regimes
    for entry in monte_carlos:
        attribution = entry["artifact"].get("regimeAttribution") or {}
        proposal = attempt(_propose_regime_blind_spot, entry["id"], attribution,
                           _strategy_of(entry), _symbols_of(entry))
        if proposal:
            proposals.append(proposal)

    # 4. a result whose tail is unsafe
    for entry in monte_carlos:
        proposal = attempt(_propose_unsafe_tail, entry["id"], entry["artifact"],
                           _strategy_of(entry))
        if proposal:
            proposals.append(proposal)

    # 5. does the strategy survive a firm's rules?
    for result in results:
        trades = result["artifact"].get("trades") or []
        if not trades:
            continue
        proposal = attempt(_propose_firm_fit, result["id"], trades, firm, firm_size)
        if proposal:
            proposals.append(proposal)

    proposals.sort(key=lambda p: (-p.priority, p.id))
    trimmed = proposals[:max_proposals]

    if skipped:
        summary = (f"{len(trimmed)} proposal(s) from the project's own evidence"
                   + (", most important first" if trimmed else "")
                   + f"; {len(skipped)} check(s) could not be evaluated and are "
                     f"named in `skipped`.")
    elif not trimmed:
        summary = ("nothing to propose: the project holds what it needs. The next "
                   "step is a decision, not a measurement.")
    else:
        summary = (f"{len(trimmed)} proposal(s) from the project's own evidence, "
                   f"most important first.")

    return {
        "available": True,
        "projectId": project_id,
        "summary": summary,
        "proposals": [p.to_dict() for p in trimmed],
        "proposalCount": len(trimmed),
        "skipped": skipped,
        "digest": digest.to_dict(),
    }


__all__ = [
    "HIGH_PROBABILITY_OF_LOSS",
    "MIN_REGIME_COVERAGE",
    "Proposal",
    "THIN_SAMPLE_TRADES",
    "propose_next",
]
