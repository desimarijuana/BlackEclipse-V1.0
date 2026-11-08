"""The recursive climb over the playbook.

This is the trade-domain analogue of RSL's hill climb, with its two hard rules
kept intact:

1. **Where to explore and what to accept are different decisions.** A proposal
   may be mutated from any previously *measured* state (the archive), including
   one that lost. Acceptance always compares against the current champion.
2. **Nothing is accepted on the data it was fitted to.** The climb reads the
   holdout window only; the fit window is reported for honesty, not reward.

It is bounded (`k` proposals per generation, a small number of generations),
seeded, and pure: it proposes snapshots, it does not persist them.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from .model import Playbook, stable_hash
from .playbook import candidate_limits, mutable_knobs
from .replay import walk_forward


def _evidence_additions(findings: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The offending identities named by the findings, per list knob.

    Data, not inference: a symbol is added only because a finding recorded it.
    """
    symbols: list[str] = []
    strategies: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        symbol = str(finding.get("symbol") or "").strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        strategy = str(finding.get("strategyId") or "").strip()
        if strategy and strategy not in strategies:
            strategies.append(strategy)
    return {
        "symbolBlocklist": symbols[:50],
        "suspendedStrategies": strategies[:20],
    }


def _expectancy(metrics: dict[str, Any]) -> Optional[float]:
    value = metrics.get("expectancyR")
    return float(value) if value is not None else None


def _rank(entry: dict[str, Any]) -> tuple[float, float, int, str]:
    holdout = entry["holdout"]
    expectancy = _expectancy(holdout)
    net = holdout.get("netR") or 0.0
    blocked = holdout.get("blocked") or 0
    # Higher expectancy wins; ties break on net R, then fewer blocked trades, then
    # the snapshot hash so two runs of the same inputs rank identically.
    return (
        expectancy if expectancy is not None else float("-inf"),
        float(net),
        -int(blocked),
        stable_hash(entry["playbook"].to_dict()),
    )


def _measure(playbook: Playbook, trades: list[Any], split_pct: float, equity: float) -> dict[str, Any]:
    return walk_forward(playbook, trades, split_pct=split_pct, equity=equity)


def climb(
    trades: list[Any],
    *,
    current: Playbook,
    findings: Optional[list[dict[str, Any]]] = None,
    k: int = 3,
    generations: int = 2,
    split_pct: float = 0.7,
    min_validation_trades: int = 10,
    min_lift_r: float = 0.02,
    seed: int = 7,
    equity: float = 0.0,
) -> dict[str, Any]:
    """Propose, measure, archive and select. Never applies anything."""
    k = max(1, min(int(k), 5))
    generations = max(1, min(int(generations), 3))
    additions = _evidence_additions(findings or [])
    rng = random.Random(int(seed))

    baseline = _measure(current, trades, split_pct, equity)
    archive: list[dict[str, Any]] = [{
        "id": "current",
        "playbook": current,
        "parentId": None,
        "generation": 0,
        "fit": baseline["fit"],
        "holdout": baseline["holdout"],
        "accepted": False,
        "reason": "baseline",
    }]
    seen = {current.hash}
    candidates: list[dict[str, Any]] = []
    best = archive[0]
    best_expectancy = _expectancy(best["holdout"])

    knobs = mutable_knobs(current)
    if not knobs:
        return {
            "candidates": [],
            "best": current.to_dict(),
            "accepted": False,
            "reason": "no_mutable_knobs",
            "baseline": {"fit": baseline["fit"], "holdout": baseline["holdout"]},
            "k": k,
            "generations": generations,
            "seed": seed,
            "sample": "simulated over recorded trades",
        }
    if len(trades) < min_validation_trades + 2:
        return {
            "candidates": [],
            "best": current.to_dict(),
            "accepted": False,
            "reason": "insufficient_sample",
            "baseline": {"fit": baseline["fit"], "holdout": baseline["holdout"]},
            "k": k,
            "generations": generations,
            "seed": seed,
            "sample": "simulated over recorded trades",
        }

    for generation in range(1, generations + 1):
        proposals: list[dict[str, Any]] = []
        # Explore from measured states only — including stepping stones that
        # did not beat the champion. Sampling and acceptance stay separate.
        pool = list(archive)
        weights = []
        for entry in pool:
            expectancy = _expectancy(entry["holdout"])
            weights.append(1.0 + max(0.0, expectancy or 0.0))
        picks = rng.choices(pool, weights=weights, k=k * 2)
        for parent in picks:
            if len(proposals) >= k:
                break
            shuffled = list(mutable_knobs(parent["playbook"]))
            rng.shuffle(shuffled)
            for knob in shuffled:
                options = candidate_limits(
                    parent["playbook"], knob, additions=additions.get(knob, []),
                )
                if not options:
                    continue
                limits = options[0]
                candidate = Playbook(
                    limits=limits,
                    bounds=parent["playbook"].bounds,
                    version=parent["playbook"].version,
                )
                if candidate.hash in seen:
                    continue
                seen.add(candidate.hash)
                measured = _measure(candidate, trades, split_pct, equity)
                record = {
                    "id": stable_hash({"parent": parent["id"], "limits": limits})[:16],
                    "playbook": candidate,
                    "parentId": parent["id"],
                    "generation": generation,
                    "fit": measured["fit"],
                    "holdout": measured["holdout"],
                    "accepted": False,
                    "reason": "measured",
                }
                proposals.append(record)
                archive.append(record)
                break

        if not proposals:
            break
        top = max(proposals, key=_rank)
        top_expectancy = _expectancy(top["holdout"])
        valid_sample = int(top["holdout"].get("rAvailable") or 0) >= min_validation_trades
        if (
            valid_sample
            and top_expectancy is not None
            and (best_expectancy is None or top_expectancy - best_expectancy >= min_lift_r)
        ):
            top["accepted"] = True
            top["reason"] = "improved_holdout"
            best = top
            best_expectancy = top_expectancy
        else:
            top["reason"] = "insufficient_sample" if not valid_sample else "no_improvement"
        candidates.extend(proposals)

    accepted = best["id"] != "current"
    reason = "improved" if accepted else "no_improvement"
    if not accepted and not candidates:
        reason = "no_mutable_candidates"
    return {
        "candidates": [
            {
                "id": entry["id"],
                "playbook": entry["playbook"].to_dict(),
                "parentId": entry["parentId"],
                "generation": entry["generation"],
                "fit": entry["fit"],
                "holdout": entry["holdout"],
                "accepted": entry["accepted"],
                "reason": entry["reason"],
            }
            for entry in candidates
        ],
        "best": best["playbook"].to_dict(),
        "accepted": accepted,
        "reason": reason,
        "baseline": {"fit": baseline["fit"], "holdout": baseline["holdout"]},
        "archiveSize": len(archive),
        "k": k,
        "generations": generations,
        "seed": seed,
        "sample": "simulated over recorded trades",
        "labels": {
            "holdout": "out-of-sample; used for acceptance",
            "fit": "in-sample; reported for honesty, never rewarded",
        },
    }


__all__ = ["climb"]
