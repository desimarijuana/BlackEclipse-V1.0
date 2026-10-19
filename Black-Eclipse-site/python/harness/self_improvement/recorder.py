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


__all__ = ["record_code_experiment"]
