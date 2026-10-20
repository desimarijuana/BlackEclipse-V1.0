"""Record an RSL experiment with the same identity the evaluator uses.

A code/tests experiment has no evaluation task set, so its dataset checksum is
the digest of the exact target + operations. The benchmark is explicitly
UNMEASURED; the record never invents a delta.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from ..evaluation.config import GRADER_API_VERSION
from ..evaluation.provenance import AGENT_VERSION, repository_commit
from ..persistence import now_iso


def _ensure_experiment_run(
    run_store: Any,
    run_id: str,
    candidate: dict[str, Any],
) -> None:
    """Create the HarnessRun row a completion event must reference.

    `HarnessEvent.runId` has a foreign key to `HarnessRun`. An evaluation
    experiment has its own `EvaluationRun` id, which is not a HarnessRun; the
    runtime event therefore needs one explicit record container. If a real run
    with the id already exists, it is never overwritten.
    """
    if run_store is None or not run_id:
        return
    try:
        if run_store.get_run(run_id) is not None:
            return
    except Exception:  # noqa: BLE001 - a lookup failure must not block recording
        pass
    try:
        run_store.create_run(run_id, "rsl", {
            "query": f"RSL experiment {candidate.get('id') or ''}".strip(),
            "kind": "rsl-experiment",
            "proposalId": candidate.get("id"),
            "subjectType": candidate.get("subjectType") or "code",
        })
        run_store.update_run(run_id, status="completed", finishedAt=now_iso())
    except Exception:  # noqa: BLE001 - the record is best-effort
        pass


def _payload_digest(candidate: dict[str, Any]) -> str:
    raw = json.dumps({
        "targetPath": candidate.get("targetPath"),
        "proposedOps": candidate.get("proposedOps") or [],
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def record_code_experiment(
    eval_store: Any,
    run_store: Any,
    *,
    run_id: str,
    candidate: dict[str, Any],
    verification: dict[str, Any],
    decision: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a tests-only code experiment and emit its completion event."""
    candidate_id = str(candidate.get("id") or "")
    config = {
        "kind": "rsl",
        "proposalId": candidate_id,
        "split": "validation",
        "trials": 0,
        "tier": 0,
        "graderVersion": GRADER_API_VERSION,
        "benchmark": "UNMEASURED",
        "mode": "tests_only",
    }
    metadata = {
        "kind": "rsl",
        "proposalId": candidate_id,
        "split": "validation",
        "graderVersion": GRADER_API_VERSION,
        "benchmark": "UNMEASURED",
        "decision": decision or ("tests_passed" if verification.get("passed") else "tests_failed"),
        "targetPath": candidate.get("targetPath"),
        "sourceCategory": candidate.get("sourceCategory"),
        "testsPassed": bool(verification.get("passed")),
        "checks": (verification.get("report") or {}).get("checks") or [],
        "measuredTrials": 0,
    }
    try:
        existing = eval_store.get_run(run_id)
        if existing is None:
            eval_store.create_run(
                id=run_id, suite="rsl-code", datasetName="owning-tests",
                datasetVersion="1", datasetChecksum=_payload_digest(candidate),
                tier=0, invoker="worktree-tests",
                agentVersion=AGENT_VERSION, gitCommit=repository_commit(),
                config=config, metadata=metadata, status="completed",
            )
        else:
            eval_store.update_run(
                run_id, status="completed", finishedAt=now_iso(),
                metadata=metadata,
            )
    except Exception:  # noqa: BLE001 - recording must not undo the verification
        pass
    _ensure_experiment_run(run_store, run_id, candidate)
    try:
        events = run_store.list_events(run_id)
        seq = max((int(event.get("seq") or 0) for event in events), default=0) + 1
        run_store.append_event(
            run_id, "self_improvement.experiment_completed", seq, {
                "candidateId": candidate_id,
                "benchmark": "UNMEASURED",
                "decision": metadata["decision"],
                "proposalId": candidate_id,
                "testsPassed": metadata["testsPassed"],
            },
        )
    except Exception:  # noqa: BLE001 - the event store is best-effort
        pass
    return {"runId": run_id, "config": config, "metadata": metadata}


def record_surface_experiment(
    run_store: Any,
    evolution: Any,
    *,
    candidate: dict[str, Any],
    verification: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    """Record a surface run's attempt + completion event.

    `verify_surface` already persisted the measured `EvaluationRun` (identity,
    metrics, decision). This function only adds the ONE `EvolutionAttempt` that
    counts the run against the daily budget, and the completion event. It never
    rewrites the evaluator's run.
    """
    candidate_id = str(candidate.get("id") or "")
    run_id = str(verification.get("runId") or "")
    record = verification.get("decisionRecord") or {}
    payload = {
        "candidateId": candidate_id,
        "proposalId": candidate_id,
        "runId": run_id,
        "benchmark": str(verification.get("benchmark") or "MEASURED").upper(),
        "decision": decision,
        "accepted": bool(record.get("accepted")) if record else False,
        "measured": record.get("measured"),
        "targetDimension": verification.get("targetDimension"),
    }
    attempt_id: Optional[str] = None
    if evolution is not None:
        try:
            surface = dict(candidate.get("surfaceConfig") or {})
            base = dict(surface.get("base") or {})
            attempt = evolution.save_attempt({
                "candidateId": candidate_id,
                "targetPath": f"surface:{surface.get('dataset') or 'benchmark_v1'}",
                "baseDigest": str(base.get("sourceDigest") or ""),
                "diffDigest": run_id or "surface-unmeasured",
                "proposedOps": [],
                "evaluation": payload,
                "outcome": "success" if payload["accepted"] else "failure",
                "outcomeReason": decision,
                "finishedAt": now_iso(),
            })
            attempt_id = str(attempt.get("id")) if attempt else None
        except Exception:  # noqa: BLE001 - the ledger must not undo the experiment
            attempt_id = None
    _ensure_experiment_run(run_store, run_id, candidate)
    if run_store is not None and run_id:
        try:
            events = run_store.list_events(run_id)
            seq = max((int(event.get("seq") or 0) for event in events), default=0) + 1
            run_store.append_event(
                run_id, "self_improvement.experiment_completed", seq, payload,
            )
        except Exception:  # noqa: BLE001 - the event store is best-effort
            pass
    return {**payload, "attemptId": attempt_id}


__all__ = ["record_code_experiment", "record_surface_experiment"]
