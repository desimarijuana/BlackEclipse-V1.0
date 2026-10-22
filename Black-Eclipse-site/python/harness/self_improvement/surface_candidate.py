"""Creating a SURFACE experiment candidate - ONE path for every caller.

The operator route (`POST /evolution/surface-experiments`) and the surface lab
must produce the SAME kind of row, with the SAME identity, so a lab winner and
an operator experiment are the same thing to the rest of the system. This module
owns that identity and the creation; the router and the lab both call it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


def surface_signature(
    *,
    base_digest: str,
    snapshot_digest: str,
    dataset: str,
    split: str,
    task_ids: list[str],
    target_dimension: str,
    trials: int,
    seed: Optional[int],
    baseline_run_id: Optional[str],
    scope: str = "global",
) -> str:
    """Deterministic identity: a changed snapshot/config/scope is a new experiment."""
    raw = json.dumps({
        "baseDigest": base_digest,
        "snapshotDigest": snapshot_digest,
        "scope": scope,
        "dataset": dataset,
        "split": split,
        "taskIds": sorted(task_ids),
        "targetDimension": target_dimension,
        "trials": int(trials),
        "seed": seed,
        "baselineRunId": baseline_run_id,
    }, sort_keys=True, separators=(",", ":"))
    return "rsl-surface:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_surface_config(
    *,
    base: Any,
    snapshot: Any,
    scope: str = "global",
    dataset: str = "benchmark_v1",
    dataset_name: str = "",
    dataset_version: str = "",
    task_ids: list[str],
    split: str = "validation",
    target_dimension: str = "task_success",
    trials: int = 3,
    seed: Optional[int] = None,
    baseline_run_id: Optional[str] = None,
) -> dict[str, Any]:
    """The typed surface configuration the verifier reads back."""
    return {
        "snapshot": snapshot.to_dict(),
        "base": base.to_dict(),
        "scope": scope,
        "dataset": dataset,
        "datasetName": dataset_name,
        "datasetVersion": dataset_version,
        "taskIds": list(task_ids),
        "split": split,
        "targetDimension": target_dimension,
        "trials": int(trials),
        "seed": seed,
        "baselineRunId": baseline_run_id,
    }


def save_surface_candidate(
    store: Any,
    *,
    base: Any,
    snapshot: Any,
    scope: str = "global",
    dataset: str = "benchmark_v1",
    dataset_name: str = "",
    dataset_version: str = "",
    task_ids: list[str],
    split: str = "validation",
    target_dimension: str = "task_success",
    trials: int = 3,
    seed: Optional[int] = None,
    baseline_run_id: Optional[str] = None,
    status: str = "proposed",
    source_category: str = "operator",
    problem_statement: str = "",
) -> dict[str, Any]:
    """Create (or reuse) ONE surface experiment candidate.

    The identity is the same the operator route uses, so re-running the same
    experiment never creates a second row. `status` is `proposed` for the
    operator route (the loop verifies it) and `inert` for the lab (the lab's
    measurement is EVIDENCE; the operator queues it).
    """
    from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

    surface_config = build_surface_config(
        base=base,
        snapshot=snapshot,
        scope=scope,
        dataset=dataset,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        task_ids=task_ids,
        split=split,
        target_dimension=target_dimension,
        trials=trials,
        seed=seed,
        baseline_run_id=baseline_run_id,
    )
    signature = surface_signature(
        base_digest=base.sourceDigest,
        snapshot_digest=snapshot.sourceDigest,
        dataset=dataset,
        split=split,
        task_ids=list(task_ids),
        target_dimension=target_dimension,
        trials=trials,
        seed=seed,
        baseline_run_id=baseline_run_id,
        scope=scope,
    )
    evolution = EvolutionStore(store)
    existing = evolution.get_by_signature(signature)
    if existing is not None:
        return {"candidate": existing, "created": False, "signature": signature}
    row = evolution.save_candidate({
        "signature": signature,
        "sourceCategory": source_category,
        "observedCount": 1,
        "problemStatement": problem_statement or (
            f"Surface harness experiment on {dataset} ({split})"
        ),
        "targetPath": None,
        "proposedOps": None,
        "subjectType": "surface",
        "surfaceConfig": surface_config,
        "status": status,
    })
    return {"candidate": row, "created": True, "signature": signature}


__all__ = [
    "build_surface_config",
    "save_surface_candidate",
    "surface_signature",
]
