"""Operator route for trial-only model-identity experiments (RSL v2).

Kept beside `evolution.py` to respect the module size budget. The experiment is
an ordinary surface candidate whose snapshot differs only by provider/model/
temperature; the existing verifier measures it and the preview still refuses
model identity for live activation.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import require_operator

router = APIRouter(tags=["evolution"])


class ModelExperimentRequest(BaseModel):
    scope: str = "eclipse-agent"
    provider: str
    model: str
    temperature: Optional[float] = None
    dataset: str = "benchmark_v1"
    taskIds: Optional[list[str]] = None  # noqa: N815
    split: str = "validation"
    targetDimension: str = "task_success"  # noqa: N815
    trials: Optional[int] = None
    seed: Optional[int] = None
    problemStatement: str = ""  # noqa: N815


@router.post("/evolution/model-experiments")
def create_model_experiment(
    body: ModelExperimentRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Queue a measured model-identity comparison for ONE agent scope."""
    from ..agents import AGENT_PRESETS  # noqa: PLC0415
    from ..evaluation.candidate_invoker import base_snapshot_from_agent  # noqa: PLC0415
    from .evolution import (  # noqa: PLC0415 - local import avoids a cycle
        SurfaceExperimentRequest,
        SurfaceSnapshotInput,
        create_surface_experiment,
    )

    scope = str(body.scope or "").strip()
    agent = AGENT_PRESETS.get(scope)
    if agent is None:
        raise HTTPException(
            status_code=400,
            detail=f"model experiments target an agent scope, not {scope or 'global'!r}",
        )
    base = base_snapshot_from_agent(agent)
    candidate = base.to_dict(include_digest=False)
    candidate.update({
        "modelProvider": body.provider,
        "modelName": body.model,
        "temperature": body.temperature,
    })
    experiment = SurfaceExperimentRequest(
        base=SurfaceSnapshotInput(**base.to_dict(include_digest=False)),
        candidate=SurfaceSnapshotInput(**candidate),
        dataset=body.dataset,
        taskIds=body.taskIds,
        split=body.split,
        targetDimension=body.targetDimension,
        trials=body.trials,
        seed=body.seed,
        problemStatement=body.problemStatement or (
            f"Model identity experiment for {scope}: {body.provider}/{body.model}"
        ),
        scope=scope,
    )
    return create_surface_experiment(experiment)


__all__ = ["router"]
