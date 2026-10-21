"""A bounded, deterministic hill climb over harness states.

The engine is deliberately free of I/O: the caller supplies neighbor generation
and evaluation, and may persist accepted states through `on_accept`. This keeps
the search testable and prevents the climb from inventing a patch, calling a
model or activating anything by itself.

Acceptance is strict (measured validation, no critical regression, a utility
gain) and replay-gated (no forgetting of retained competence). A rejected
neighbor is recorded with its reason, never silently dropped. A plateau stops
the climb instead of accepting a worse state.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

from .replay import best_known, replay_gate, task_rates
from .utility import UtilityWeights, acceptance

ProposeFn = Callable[[Mapping[str, Any], int, int, tuple[str, ...]], Any]
EvaluateFn = Callable[[Mapping[str, Any], str], Any]
AcceptFn = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class HillClimbConfig:
    generations: int = 1
    k: int = 2
    max_plateau: int = 2
    max_forgetting: float = 0.02
    require_replay: bool = True
    max_evaluations: Optional[int] = None
    objective: str = "single"
    weights: UtilityWeights = field(default_factory=UtilityWeights)


async def _await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _digest(candidate: Mapping[str, Any]) -> str:
    payload = {
        "snapshotDigest": candidate.get("snapshotDigest"),
        "ops": candidate.get("ops") or candidate.get("proposedOps"),
        "targetPath": candidate.get("targetPath"),
        "kind": candidate.get("kind"),
    }
    if any(value for value in payload.values()):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return str(candidate.get("id") or "")


def _state_metrics(state: Mapping[str, Any]) -> Any:
    if "metrics" in state:
        return state.get("metrics") or {}
    if "aggregates" in state:
        return state.get("aggregates") or {}
    return {}


def _pareto_accepts(
    current_metrics: Any,
    candidate_metrics: Any,
    decision: Mapping[str, Any],
    *,
    weights: UtilityWeights,
) -> bool:
    """v2 trade-off acceptance: candidate is measured, no critical veto, not dominated."""
    from .pareto import dominates, vector  # noqa: PLC0415

    if decision.get("accepted"):
        return True
    if any(str(reason).startswith("critical regression") for reason in decision.get("reasons") or []):
        return False
    if decision.get("candidate", {}).get("measuredTrials", 0) <= 0:
        return False
    current = vector(current_metrics, weights=weights)
    candidate = vector(candidate_metrics, weights=weights)
    if sum(value is not None for value in current.values()) < 2:
        return False
    if sum(value is not None for value in candidate.values()) < 2:
        return False
    return not dominates(current, candidate)


def _candidate_id(candidate: Mapping[str, Any]) -> Optional[str]:
    value = candidate.get("candidateId") or candidate.get("id")
    return str(value) if value else None


def _state_record(
    candidate: Mapping[str, Any],
    *,
    parent: Mapping[str, Any],
    metrics: Any,
    score: Mapping[str, Any],
    scope: str,
) -> dict[str, Any]:
    digest = str(candidate.get("snapshotDigest") or "") or _digest(candidate)
    return {
        "parentStateId": parent.get("id"),
        "scope": str(candidate.get("scope") or scope or "global"),
        "snapshotDigest": digest,
        "candidateId": _candidate_id(candidate),
        "acceptedRunId": candidate.get("acceptedRunId") or candidate.get("runId"),
        "utility": score.get("utility"),
        "metrics": metrics,
        "status": "candidate",
    }


async def run_hillclimb(
    current: Mapping[str, Any],
    *,
    propose: ProposeFn,
    evaluate: EvaluateFn,
    replay_baseline: Optional[Mapping[str, float]] = None,
    critical_tasks: Iterable[str] = (),
    config: Optional[HillClimbConfig] = None,
    scope: Optional[str] = None,
    on_accept: Optional[AcceptFn] = None,
) -> dict[str, Any]:
    """Climb from `current`, returning every rejected neighbor with its reason.

    `propose(current, k, generation, rejectedDigests)` returns candidate dicts.
    `evaluate(candidate, split)` returns a `SuiteResult`, a metrics dict, or an
    object with `aggregates`/`measured_trials`. `on_accept(state)` is called for
    an accepted candidate; persistence is the caller's decision.
    """
    settings = config or HillClimbConfig()
    state = dict(current)
    state_scope = str(scope or state.get("scope") or "global")
    retained = dict(replay_baseline or {})
    critical = tuple(critical_tasks)
    rejected_digests: set[str] = set()
    accepted: list[dict[str, Any]] = []
    generations: list[dict[str, Any]] = []
    plateau = 0
    evaluated = 0
    stop_reason = "generations"

    if not state.get("id") and state.get("snapshotDigest"):
        state["id"] = "current"

    for generation in range(max(0, int(settings.generations))):
        raw_neighbors = await _await(
            propose(state, max(1, int(settings.k)), generation, tuple(sorted(rejected_digests)))
        )
        neighbors = [dict(item) for item in (raw_neighbors or []) if isinstance(item, Mapping)]
        records: list[dict[str, Any]] = []
        improving: list[dict[str, Any]] = []
        budget_reached = False

        for candidate in neighbors:
            if (
                settings.max_evaluations is not None
                and evaluated >= max(0, int(settings.max_evaluations))
            ):
                budget_reached = True
                break
            digest = _digest(candidate)
            if digest and digest in rejected_digests:
                records.append({
                    **candidate,
                    "decision": "rejected",
                    "reasons": ["tabu: duplicate neighbor"],
                })
                continue
            evaluated += 1
            try:
                validation = await _await(evaluate(candidate, "validation"))
                decision = acceptance(
                    _state_metrics(state), validation, weights=settings.weights,
                )
                if (
                    settings.objective == "pareto"
                    and not decision["accepted"]
                    and _pareto_accepts(
                        _state_metrics(state), validation, decision,
                        weights=settings.weights,
                    )
                ):
                    decision = {
                        **decision,
                        "accepted": True,
                        "reasons": [
                            "pareto trade-off (not dominated by the current state)"
                        ],
                    }
            except Exception as exc:  # noqa: BLE001 - a failed evaluation is a rejection
                records.append({
                    **candidate, "decision": "rejected",
                    "reasons": [f"evaluation_error:{type(exc).__name__}"],
                })
                rejected_digests.add(digest)
                continue

            record = {
                **candidate,
                "digest": digest,
                "decision": "rejected",
                "reasons": list(decision["reasons"]),
                "utility": decision["candidate"]["utility"],
                "improvement": decision["improvement"],
                "validation": validation,
                "replay": None,
            }
            if not decision["accepted"]:
                records.append(record)
                rejected_digests.add(digest)
                continue

            try:
                replay_result = await _await(evaluate(candidate, "replay"))
                gate = replay_gate(
                    retained,
                    task_rates(replay_result),
                    critical_tasks=critical,
                    max_forgetting=settings.max_forgetting,
                    require_baseline=settings.require_replay,
                )
            except Exception as exc:  # noqa: BLE001 - a failed replay is a rejection
                gate = {
                    "passed": False, "status": "error",
                    "reason": f"replay_error:{type(exc).__name__}",
                    "forgetting": {"mean": None, "drops": {}, "criticalDrops": {}},
                }
                replay_result = None

            record["replay"] = replay_result
            if not gate["passed"]:
                record["reasons"].append(gate["reason"])
                records.append(record)
                rejected_digests.add(digest)
                continue

            record["decision"] = "accepted"
            record["replayGate"] = gate
            records.append(record)
            improving.append(record)

        if improving:
            best = max(
                improving,
                key=lambda item: (float(item.get("utility") or 0.0), str(item.get("id") or "")),
            )
            state_record = _state_record(
                best, parent=state, metrics=best["validation"],
                score={"utility": best["utility"]}, scope=state_scope,
            )
            saved: Any = None
            if on_accept is not None:
                saved = await _await(on_accept(state_record))
            persisted = saved if isinstance(saved, Mapping) else {}
            state = {
                **best,
                "id": persisted.get("id") or state_record.get("id") or best.get("id"),
                "scope": persisted.get("scope") or state_record["scope"],
                "snapshotDigest": persisted.get("snapshotDigest") or state_record["snapshotDigest"],
                "metrics": persisted.get("metrics") or best["validation"],
                "utility": (
                    persisted.get("utility")
                    if persisted.get("utility") is not None
                    else best["utility"]
                ),
                "parentStateId": (
                    persisted.get("parentStateId") or state_record["parentStateId"]
                ),
                "acceptedRunId": (
                    persisted.get("acceptedRunId") or state_record["acceptedRunId"]
                ),
            }
            retained = best_known(retained, task_rates(best.get("replay")))
            accepted.append(state_record)
            plateau = 0
        else:
            plateau += 1

        generations.append({
            "generation": generation,
            "neighbors": len(neighbors),
            "evaluated": evaluated,
            "accepted": len(improving),
            "records": records,
        })
        if budget_reached:
            stop_reason = "budget"
            break
        if plateau >= max(1, int(settings.max_plateau)):
            stop_reason = "plateau"
            break

    pareto = None
    if settings.objective == "pareto":
        from .pareto import frontier  # noqa: PLC0415

        pareto = frontier([*accepted, state])
    return {
        "current": state,
        "accepted": accepted,
        "generations": generations,
        "evaluations": evaluated,
        "stopReason": stop_reason,
        "replayBaseline": retained,
        "scope": state_scope,
        "objective": settings.objective,
        "pareto": pareto,
    }


__all__ = [
    "AcceptFn",
    "EvaluateFn",
    "HillClimbConfig",
    "ProposeFn",
    "run_hillclimb",
]
