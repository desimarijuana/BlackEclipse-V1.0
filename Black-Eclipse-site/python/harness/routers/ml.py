"""ML Research Lab HTTP routes (operator-gated).

A thin surface over the SAME store, pipeline and market gateway the agent tools
use. Data-building endpoints fetch through the run gateway; compute endpoints run
the deterministic pipeline. Reaches shared runtime state only through
`harness.deps`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..ml import service as S
from ..stats.base import StatsError

router = APIRouter(prefix="/ml/v1", tags=["ml"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, StatsError):
        return HTTPException(status_code=exc.http_status,
                             detail={"code": exc.code, "message": exc.message})
    return HTTPException(status_code=500, detail={"code": "ML_ERROR", "message": str(exc)})


def _market_gateway() -> Any:
    from ..market.gateway import MarketDataGateway  # noqa: PLC0415

    return MarketDataGateway(service.server_bridge(), cache=getattr(service, "market_cache", None),
                             router=getattr(service, "market_router", None))


def _feature_registry() -> Any:
    try:
        from ..stats.feature_registry import FeatureRegistry  # noqa: PLC0415
        from ..stats.service import get_stats_store  # noqa: PLC0415

        store = get_stats_store()
        return FeatureRegistry(store) if store is not None else None
    except Exception:  # noqa: BLE001
        return None


class TargetBody(BaseModel):
    kind: str = "direction_binary"
    horizon: int = 5
    threshold: float = 0.0
    neutralBand: float = 0.0
    nClasses: int = 3
    column: str = "target"
    # Only for kind="column" (records datasets): regression | classification.
    task: Optional[str] = None


class DatasetBody(BaseModel):
    name: str = "dataset"
    description: Optional[str] = None
    owner: Optional[str] = None
    datasetId: Optional[str] = None
    version: Optional[str] = None
    # "market" (symbols via the gateway) or "records" (operator-supplied rows).
    source: str = "market"
    symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    featureNames: list[str] = Field(default_factory=list)
    target: TargetBody = Field(default_factory=TargetBody)
    missingPolicy: str = "drop"
    minCoverage: float = 0.5
    assetClass: str = "equity"
    # records only: the rows, and optional time/id columns for provenance.
    records: Optional[list[dict[str, Any]]] = None
    timeColumn: Optional[str] = None
    idColumn: Optional[str] = None


class SplitBody(BaseModel):
    method: str = "walk_forward"
    nSplits: int = 5
    testSize: int = 0
    window: int = 0
    windowMode: str = "expanding"
    embargo: int = 0
    purge: bool = True
    minTrainSize: int = 0


class ExperimentBody(BaseModel):
    datasetId: str
    datasetVersion: str
    title: str = "experiment"
    modelFamily: str = "logistic"
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    selection: dict[str, Any] = Field(default_factory=lambda: {"method": "none"})
    split: SplitBody = Field(default_factory=SplitBody)
    seed: int = 42
    # "none" | "platt" | "isotonic" — fitted on out-of-fold predictions only.
    calibration: str = "none"
    registerModel: bool = False
    background: bool = False
    name: Optional[str] = None
    owner: Optional[str] = None


class TransitionBody(BaseModel):
    version: str
    action: str
    actor: Optional[str] = None
    reason: Optional[str] = None


class PredictBody(BaseModel):
    features: list[list[float]]
    version: Optional[str] = None


@router.get("/capabilities")
async def ml_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return S.engine_capabilities()


class PlanBody(BaseModel):
    datasetId: Optional[str] = None
    datasetVersion: Optional[str] = None
    rows: Optional[int] = None
    features: Optional[int] = None
    task: Optional[str] = None
    classCount: Optional[int] = None
    preference: str = "balanced"
    seed: int = 42


@router.get("/datasets")
async def ml_datasets(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"datasets": S.list_datasets(limit=limit)}


@router.post("/datasets")
async def ml_build_dataset(body: DatasetBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        result = await S.build_dataset_version(
            _market_gateway(), payload, name=body.name, description=body.description,
            owner=body.owner, registry=_feature_registry())
        return {
            "datasetId": result["datasetId"], "version": result["version"],
            "artifactId": result["artifactId"], "dataHash": result["dataHash"],
            "quality": result.get("quality"), "manifest": result.get("manifest"),
            "durationMs": result.get("durationMs"),
        }
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/datasets/{dataset_id}/versions")
async def ml_dataset_versions(dataset_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"versions": S.list_dataset_versions(dataset_id)}


@router.get("/datasets/{dataset_id}/versions/{version}")
async def ml_dataset_version(dataset_id: str, version: str,
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = S.get_dataset_version(dataset_id, version)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown dataset version"})
    manifest = result.get("manifest") or {}
    return {"datasetId": dataset_id, "version": version, "dataHash": result.get("dataHash"),
            "manifest": manifest}


@router.get("/datasets/{dataset_id}/versions/{version}/export")
async def ml_export_dataset(dataset_id: str, version: str, format: str = "csv",
                            limit: int = 10_000,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    """The dataset version as portable CSV/JSONL text (bounded, truncation stated)."""
    try:
        return S.export_dataset(dataset_id, version, fmt=format, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/experiments")
async def ml_experiments(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"experiments": S.list_experiments(limit=limit)}


@router.post("/plan")
async def ml_plan(body: PlanBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Plan a model recipe — no training, no metric claim."""
    try:
        return S.plan_model(body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class CompareBody(BaseModel):
    datasetId: str
    datasetVersion: str
    families: list[str] = Field(default_factory=list)
    hyperparameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    selection: dict[str, Any] = Field(default_factory=lambda: {"method": "none"})
    split: SplitBody = Field(default_factory=SplitBody)
    seed: int = 42
    scale: bool = True
    owner: Optional[str] = None
    # Run on the Execution Fabric worker instead of inside the request.
    background: bool = False


@router.post("/experiments")
async def ml_run_experiment(body: ExperimentBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        if body.background:
            job = await S.submit_experiment_background(body.model_dump(), owner=body.owner)
            return {"background": True, "job": job}
        result = await S.execute_experiment(body.model_dump(), owner=body.owner)
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class SearchBody(BaseModel):
    datasetId: str
    datasetVersion: str
    modelFamily: str
    grid: dict[str, list[Any]] = Field(default_factory=dict)
    maxTrials: int = 8
    maxSeconds: float = 300.0
    selection: dict[str, Any] = Field(default_factory=lambda: {"method": "none"})
    split: SplitBody = Field(default_factory=SplitBody)
    seed: int = 42
    scale: bool = True
    calibration: str = "none"
    owner: Optional[str] = None
    background: bool = False


@router.post("/compare")
async def ml_compare(body: CompareBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Train several families on one dataset with one validation design, then compare."""
    try:
        if body.background:
            job = await S.submit_compare_background(body.model_dump(), owner=body.owner)
            return {"background": True, "job": job}
        return await S.compare_models(body.model_dump(), owner=body.owner)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/search")
async def ml_search(body: SearchBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Grid/random hyperparameter search over one family, on the same folds."""
    try:
        if body.background:
            job = await S.submit_search_background(body.model_dump(), owner=body.owner)
            return {"background": True, "job": job}
        return await S.search_hyperparameters(body.model_dump(), owner=body.owner)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/jobs")
async def ml_jobs(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"jobs": S.list_jobs(limit=limit)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/jobs/{job_id}")
async def ml_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        job = S.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown job"})
    return {"job": job}


@router.post("/jobs/{job_id}/cancel")
async def ml_job_cancel(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"cancellation": await S.cancel_job(job_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/experiments/{experiment_id}/runs")
async def ml_experiment_runs(experiment_id: str, limit: int = 50,
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"runs": S.list_runs(experiment_id, limit=limit)}


@router.get("/runs/{run_id}")
async def ml_run(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    run = S.get_run_result(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown run"})
    return {"run": run}


@router.post("/runs/{run_id}/reproduce")
async def ml_reproduce(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return S.reproduce_run(run_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/models")
async def ml_models(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"models": S.list_models(limit=limit)}


@router.post("/models/register")
async def ml_register(body: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return S.register_from_run(str(body.get("runId") or ""),
                                   name=str(body.get("name") or "model"), owner=body.get("owner"))
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/models/{model_id}")
async def ml_model(model_id: str, version: Optional[str] = None,
                   _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = S.get_model_version(model_id, version)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown model"})
    return result


@router.post("/models/{model_id}/transition")
async def ml_transition(model_id: str, body: TransitionBody,
                        _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return S.transition_model(model_id, version=body.version, action=body.action,
                                  actor=body.actor, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class DriftBody(BaseModel):
    version: Optional[str] = None
    datasetId: str
    datasetVersion: str


@router.get("/models/{model_id}/verify")
async def ml_verify(model_id: str, version: Optional[str] = None,
                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return S.verify_model_artifact(model_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class EnsembleBody(BaseModel):
    name: str = "ensemble"
    members: list[dict[str, Any]] = Field(default_factory=list)
    owner: Optional[str] = None


@router.post("/ensembles")
async def ml_create_ensemble(body: EnsembleBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Register an ensemble of already-trained models (mean of their predictions)."""
    try:
        return S.create_ensemble(body.model_dump(), owner=body.owner)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/models/{model_id}/drift")
async def ml_model_drift(model_id: str, body: DriftBody,
                         _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Compare the model's training data with a later dataset version (PSI/KS)."""
    try:
        return S.model_drift(model_id, dataset_id=body.datasetId,
                             dataset_version=body.datasetVersion, version=body.version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/models/{model_id}/predict")
async def ml_predict_route(model_id: str, body: PredictBody,
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        import numpy as np  # noqa: PLC0415

        X = np.asarray(body.features, dtype=float)
        return S.predict_with_model(model_id, X, body.version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
