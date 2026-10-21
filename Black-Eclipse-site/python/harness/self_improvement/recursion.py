"""One bounded recursive RSL experiment: k typed candidates from one observation.

This is the R7 conductor, not a second loop. It proposes typed variants from
operator/agent-supplied ops, verifies each independently through the caller's
existing verifier, records an anonymous selection, attempts a conservative
composition, and persists ONE `EvaluationRun` with the evidence. It never
activates a change and never consumes an approval.

`k=1` remains the trivial path. `k` counts against the caller's daily budget;
the existing `RSLLoop` budget and lease semantics are unchanged for single
experiments.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from ..evaluation.config import GRADER_API_VERSION
from ..evaluation.contrast import render_evidence_bundle
from ..evaluation.provenance import AGENT_VERSION, repository_commit
from ..persistence import now_iso
from . import composition, proposer, selection

VerifyFn = Callable[[proposer.CandidateProposal], Any]


def budgeted_k(
    k: int,
    *,
    started_today: int = 0,
    max_per_day: Optional[int] = None,
) -> dict[str, Any]:
    """How many candidate experiments the daily budget allows right now.

    `k` is a cost cap, not a promise: a recursive experiment stops at the
    remaining daily allowance. A budget of zero refuses the experiment rather
    than silently running a different one.
    """
    requested = max(1, int(k))
    if max_per_day is None:
        return {
            "requested": requested, "allowed": requested,
            "remaining": None, "refused": False,
        }
    remaining = max(0, int(max_per_day) - max(0, int(started_today)))
    allowed = min(requested, remaining)
    return {
        "requested": requested,
        "allowed": allowed,
        "remaining": remaining,
        "refused": allowed < 1,
    }


async def _resolve(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _number(value: Any, *, integer: bool = False) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if integer else float(value)


def _usage(result: Mapping[str, Any], key: str) -> Any:
    """Read an optional usage number from a verifier result.

    A verifier may report the cost directly (`costUsd` / `cost`) or inside the
    measured aggregates of a suite (`metrics.aggregates.cost`). Absent stays
    None (UNKNOWN) - never a fabricated zero.
    """
    for name in ("costUsd", "cost") if key == "cost" else ("totalTokens", "tokens"):
        value = result.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    metrics = result.get("metrics")
    if isinstance(metrics, Mapping):
        aggregates = metrics.get("aggregates")
        if isinstance(aggregates, Mapping):
            value = aggregates.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
    return None


def _normalised_result(result: Any) -> dict[str, Any]:
    result = dict(result) if isinstance(result, Mapping) else {}
    answered = result.get("answered") is not False and result.get("passed") is not None
    return {
        "answered": answered,
        "passed": bool(result.get("passed")) if answered else False,
        "score": selection.result_score(result),
        "benchmark": str(result.get("benchmark") or "UNMEASURED").upper(),
        "runId": result.get("runId"),
        "cause": str(result.get("cause") or ("no_answer" if not answered else "")) or None,
        # Optional real usage from the verifier; absent stays None (UNKNOWN),
        # never a fabricated zero.
        "costUsd": _number(_usage(result, "cost")),
        "totalTokens": _number(_usage(result, "totalTokens"), integer=True),
    }


def _checksum(candidate: Mapping[str, Any], proposals: Sequence[proposer.CandidateProposal]) -> str:
    raw = json.dumps(
        {
            "proposalId": candidate.get("id"),
            "signature": candidate.get("signature"),
            "variants": [proposal.to_dict() for proposal in proposals],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _append_event(
    run_store: Any,
    source_run_id: Optional[str],
    *,
    payload: Mapping[str, Any],
) -> None:
    if run_store is None or not source_run_id:
        return
    try:
        events = run_store.list_events(source_run_id)
        seq = max((int(event.get("seq") or 0) for event in events), default=0) + 1
        run_store.append_event(
            source_run_id, "self_improvement.experiment_completed", seq, dict(payload),
        )
    except Exception:  # noqa: BLE001 - recording must not undo the experiment
        pass


async def run_recursive(
    candidate: Mapping[str, Any],
    *,
    verify_fn: VerifyFn,
    k: int = 1,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    seed: int = 0,
    max_parallel: int = 1,
    actor: Any = None,
    measure: Optional[composition.Measurement] = None,
    trajectories: Optional[Mapping[str, Any]] = None,
    evidence_dir: Optional[Path | str] = None,
    started_today: int = 0,
    max_per_day: Optional[int] = None,
    eval_store: Any = None,
    run_store: Any = None,
    record: bool = True,
    record_attempts: bool = True,
) -> dict[str, Any]:
    """Run one recursive experiment and return its bounded record.

    The caller owns verification (the existing tests-only code verifier or the
    measured surface verifier). A verification exception is recorded as a
    non-answer with its cause, never as a pass. A verdict leak in a contrast
    bundle raises `VerdictLeakError` — a hard error, not a warning.
    """
    budget = budgeted_k(k, started_today=started_today, max_per_day=max_per_day)
    if budget["refused"]:
        return {
            "refused": True,
            "reason": "daily_budget",
            "budget": budget,
            "selection": None,
            "composition": None,
        }

    try:
        proposals = proposer.propose_many(
            candidate, int(budget["allowed"]), variants=variants, actor=actor,
        )
    except proposer.ProposalRefused as exc:
        return {
            "refused": True,
            "reason": "proposal_refused",
            "code": exc.code,
            "detail": exc.detail,
            "budget": budget,
            "selection": None,
            "composition": None,
        }

    labels = selection.anonymous_labels(
        [proposal.id for proposal in proposals], seed=seed,
    )
    limit = max(1, min(8, int(max_parallel or 1)))
    semaphore = asyncio.Semaphore(limit)

    async def _verify_one(proposal: Any) -> Any:
        async with semaphore:
            try:
                return await _resolve(verify_fn(proposal))
            except Exception as exc:  # noqa: BLE001 - a failed verification is a non-answer
                return {
                    "answered": False,
                    "cause": f"verification_error:{type(exc).__name__}",
                }

    raw_results = await asyncio.gather(
        *(_verify_one(proposal) for proposal in proposals),
    )
    candidates: list[dict[str, Any]] = []
    for proposal, raw in zip(proposals, raw_results):
        normalised = _normalised_result(raw)
        candidates.append({
            "id": proposal.id,
            "label": labels.get(proposal.id),
            "kind": proposal.kind,
            "targetPath": proposal.targetPath,
            "ops": list(proposal.ops),
            **normalised,
        })

    costs = [
        item["costUsd"] for item in candidates
        if item.get("costUsd") is not None
    ]
    tokens = [
        item["totalTokens"] for item in candidates
        if item.get("totalTokens") is not None
    ]
    total_cost = round(sum(costs), 6) if costs else None
    total_tokens = sum(tokens) if tokens else None

    selected = selection.build_selection(candidates, seed=seed)
    composed = await composition.compose_verified(candidates, measure=measure)

    bundle_path: Optional[str] = None
    if trajectories:
        directory = Path(evidence_dir) if evidence_dir else Path(
            tempfile.mkdtemp(prefix="rsl-recursion-")
        )
        render_evidence_bundle(
            directory,
            task_text=str(candidate.get("problemStatement") or candidate.get("title") or ""),
            mission_job=(
                "Compare the independently verified candidates against the "
                "baseline. Cite the trajectory moment behind every claim."
            ),
            trajectories=trajectories,
            baseline_label="base",
            produced={
                item["label"]: json.dumps(
                    {"kind": item.get("kind"), "ops": item.get("ops")}, default=str,
                )
                for item in candidates if item.get("label")
            },
        )
        bundle_path = str(directory)

    run_id = f"rsl-recursive-{uuid.uuid4().hex[:16]}"
    attempt_ids: list[str] = []
    if record and record_attempts and run_store is not None and eval_store is not None and candidate.get("id"):
        from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

        try:
            evolution = EvolutionStore(run_store)
            for proposal, item in zip(proposals, candidates):
                attempt = evolution.save_attempt({
                    "candidateId": candidate.get("id"),
                    "targetPath": proposal.targetPath,
                    "baseDigest": "",
                    "diffDigest": f"{run_id}:{proposal.id}",
                    "proposedOps": list(proposal.ops),
                    "evaluation": {
                        "benchmark": item.get("benchmark"),
                        "answered": item.get("answered"),
                        "passed": item.get("passed"),
                        "score": item.get("score"),
                        "runId": item.get("runId"),
                    },
                    "outcome": "success" if item.get("passed") else "failure",
                    "outcomeReason": item.get("cause") or (
                        "verified" if item.get("passed") else "not_verified"
                    ),
                    "finishedAt": now_iso(),
                })
                attempt_ids.append(str(attempt.get("id")))
        except Exception:  # noqa: BLE001 - the ledger must not undo the experiment
            attempt_ids = []

    payload = {
        "runId": run_id,
        "k": len(proposals),
        "requestedK": int(budget["requested"]),
        "maxParallel": limit,
        "budget": budget,
        "costUsd": total_cost,
        "totalTokens": total_tokens,
        "selection": selected,
        "composition": composed,
        "attemptIds": attempt_ids,
        "variants": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "kind": item.get("kind"),
                "benchmark": item.get("benchmark"),
                "runId": item.get("runId"),
                "answered": item.get("answered"),
            }
            for item in candidates
        ],
        "evidenceBundle": bundle_path,
        "benchmark": composed.get("benchmark", "UNMEASURED"),
    }

    if record and eval_store is not None:
        config = {
            "kind": "rsl-recursion",
            "proposalId": candidate.get("id"),
            "k": len(proposals),
            "requestedK": int(budget["requested"]),
            "maxParallel": limit,
            "seed": int(seed),
            "graderVersion": GRADER_API_VERSION,
            "benchmark": payload["benchmark"],
            "costUsd": total_cost,
            "totalTokens": total_tokens,
        }
        metadata = {
            "kind": "rsl-recursion",
            "proposalId": candidate.get("id"),
            "selection": selected,
            "selectionDigest": selection.selection_digest(selected),
            "composition": composed,
            "attemptIds": attempt_ids,
            "variants": payload["variants"],
            "evidenceBundle": bundle_path,
            "benchmark": payload["benchmark"],
            "costUsd": total_cost,
            "totalTokens": total_tokens,
        }
        eval_store.create_run(
            id=run_id,
            suite="rsl-recursion",
            datasetName="rsl-recursion",
            datasetVersion="1",
            datasetChecksum=_checksum(candidate, proposals),
            tier=0,
            invoker="rsl-recursion",
            agentVersion=AGENT_VERSION,
            gitCommit=repository_commit(),
            config=config,
            metadata=metadata,
            status="completed",
        )
        _append_event(
            run_store,
            str(candidate.get("createdByRunId") or "") or None,
            payload={
                "candidateId": candidate.get("id"),
                "recursiveRunId": run_id,
                "k": len(proposals),
                "decision": composed.get("decision"),
                "benchmark": payload["benchmark"],
            },
        )

    return {**payload, "refused": False}


__all__ = ["VerifyFn", "budgeted_k", "run_recursive"]
