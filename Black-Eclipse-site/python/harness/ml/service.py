"""Service layer for the ML Research Lab.

Owns the singleton `MLStore`, the dataset/experiment orchestration and the
array (de)serialisation used to persist a dataset version. The training pipeline
is CPU-bound, so it runs off the event loop via ``asyncio.to_thread`` — training
never blocks the interactive runtime.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import numpy as np

from .datasets import build_dataset
from .config import get_ml_config
from .models import DatasetSpec, ExperimentConfig, MLError, SplitSpec, TargetSpec
from .store import MLStore
from .training import run_experiment as _run_experiment
from ..stats.base import INVALID_INPUT

_store: Optional[MLStore] = None


def set_ml_store(store: Optional[MLStore]) -> None:
    global _store
    _store = store


def get_ml_store() -> Optional[MLStore]:
    return _store


def _require_store() -> MLStore:
    if _store is None:
        raise MLError("UNAVAILABLE", "the ML store is unavailable", 503)
    return _store


# ── array (de)serialisation ──────────────────────────────────────────────────


def serialize_arrays(arrays: dict[str, Any]) -> dict[str, Any]:
    return {
        "X": np.asarray(arrays["X"], dtype=float).tolist(),
        "y": [None if not np.isfinite(v) else float(v) for v in np.asarray(arrays["y"], dtype=float)],
        "labelStart": np.asarray(arrays["labelStart"], dtype=int).tolist(),
        "labelEnd": np.asarray(arrays["labelEnd"], dtype=int).tolist(),
        "timestamps": list(arrays["timestamps"]),
        "symbols": list(arrays["symbols"]),
        "featureNames": list(arrays["featureNames"]),
        "perSymbolRows": int(arrays.get("perSymbolRows") or 0),
        "targetTask": arrays.get("targetTask"),
        "targetClasses": arrays.get("targetClasses"),
    }


def deserialize_arrays(payload: dict[str, Any]) -> dict[str, Any]:
    y = np.asarray([np.nan if v is None else float(v) for v in payload["y"]], dtype=float)
    return {
        "X": np.asarray(payload["X"], dtype=float),
        "y": y,
        "labelStart": np.asarray(payload["labelStart"], dtype=int),
        "labelEnd": np.asarray(payload["labelEnd"], dtype=int),
        "timestamps": list(payload["timestamps"]),
        "symbols": list(payload["symbols"]),
        "featureNames": list(payload["featureNames"]),
        "perSymbolRows": int(payload.get("perSymbolRows") or 0),
        "targetTask": payload.get("targetTask"),
        "targetClasses": payload.get("targetClasses"),
    }


# ── dataset ──────────────────────────────────────────────────────────────────


def _dataset_spec(payload: dict[str, Any]) -> DatasetSpec:
    target_raw = payload.get("target") or {}
    target = TargetSpec(
        kind=target_raw.get("kind", "direction_binary"),
        horizon=int(target_raw.get("horizon", 5)),
        threshold=float(target_raw.get("threshold", 0.0)),
        neutral_band=float(target_raw.get("neutralBand", 0.0)),
        n_classes=int(target_raw.get("nClasses", 3)),
        column=target_raw.get("column", "target"),
    )
    return DatasetSpec(
        symbols=list(payload.get("symbols") or []),
        interval=payload.get("interval", "1d"),
        start=payload.get("start"),
        end=payload.get("end"),
        feature_names=list(payload.get("featureNames") or []),
        target=target,
        missing_policy=payload.get("missingPolicy", "drop"),
        min_coverage=float(payload.get("minCoverage", 0.5)),
        asset_class=payload.get("assetClass", "equity"),
    )


async def build_dataset_version(
    gateway: Any, payload: dict[str, Any], *, name: str, description: Optional[str] = None,
    owner: Optional[str] = None, registry: Any = None,
) -> dict[str, Any]:
    """Build AND persist one immutable dataset version."""
    store = _require_store()
    spec = _dataset_spec(payload)
    started = time.time()
    built = await build_dataset(gateway, spec, registry=registry)
    manifest = built["manifest"]
    manifest["datasetId"] = payload.get("datasetId") or f"mld_{int(time.time() * 1000):x}"
    manifest["version"] = payload.get("version") or "1.0.0"
    manifest["name"] = name
    result = store.save_dataset(
        name=name, description=description, owner=owner, asset_class=spec.asset_class,
        manifest=manifest, arrays=serialize_arrays(built["arrays"]))
    store.audit(action="dataset.build", subject_type="dataset",
                subject_id=result["datasetId"], actor=owner,
                detail={"version": result["version"], "rows": manifest["rows"]})
    result["quality"] = manifest.get("quality")
    result["manifest"] = manifest
    result["durationMs"] = int((time.time() - started) * 1000)
    return result


def list_datasets(limit: int = 100) -> list[dict[str, Any]]:
    return _require_store().list_datasets(limit=limit)


def get_dataset_version(dataset_id: str, version: str) -> Optional[dict[str, Any]]:
    return _require_store().get_dataset_version(dataset_id, version)


def list_dataset_versions(dataset_id: str) -> list[dict[str, Any]]:
    return _require_store().list_dataset_versions(dataset_id)


# ── experiment execution ─────────────────────────────────────────────────────


def _config_from_payload(payload: dict[str, Any]) -> ExperimentConfig:
    split_raw = payload.get("split") or payload.get("splitSpec") or {}
    split = SplitSpec(
        method=split_raw.get("method", "walk_forward"),
        n_splits=int(split_raw.get("nSplits", 5)),
        test_size=int(split_raw.get("testSize", 0)),
        window=int(split_raw.get("window", 0)),
        window_mode=split_raw.get("windowMode", "expanding"),
        embargo=int(split_raw.get("embargo", 0)),
        purge=bool(split_raw.get("purge", True)),
        min_train_size=int(split_raw.get("minTrainSize", 0)),
    )
    return ExperimentConfig(
        dataset_id=str(payload.get("datasetId") or ""),
        dataset_version=str(payload.get("datasetVersion") or ""),
        title=str(payload.get("title") or "experiment"),
        model_family=str(payload.get("modelFamily") or "logistic"),
        hyperparameters=dict(payload.get("hyperparameters") or {}),
        feature_names=list(payload.get("featureNames") or []),
        selection=dict(payload.get("selection") or {"method": "none"}),
        split=split,
        seed=int(payload.get("seed", 42)),
        scale=bool(payload.get("scale", True)),
        task=payload.get("task"),
    )


async def run_experiment_job(
    payload: dict[str, Any], *, owner: Optional[str] = None,
    cancel_event: Any = None, progress: Any = None,
) -> dict[str, Any]:
    """Run one training experiment with resource guardrails, progress and
    cancellation. Persists the experiment + run and returns a structured result.

    This NEVER raises for an ML operational failure — cancellation, a budget
    overrun and a training error are each recorded and returned as an honest
    status. Pre-flight validation errors (unknown dataset, over-limit rows) are
    raised before any run is created.
    """
    cfg = get_ml_config()
    if not cfg.enabled:
        raise MLError("UNAVAILABLE", "the ML engine is disabled (HARNESS_ML_ENABLED=0)", 503)
    store = _require_store()
    config = _config_from_payload(payload)
    dataset_id = config.dataset_id
    version = config.dataset_version
    ds = store.get_dataset_version(dataset_id, version)
    if ds is None or ds.get("artifact") is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    arrays = deserialize_arrays(ds["artifact"]["content"]["arrays"])
    manifest = ds["manifest"]

    n_rows = int(np.asarray(arrays["X"]).shape[0])
    if n_rows > cfg.max_rows:
        raise MLError(INVALID_INPUT,
                      f"dataset has {n_rows} rows; the limit is {cfg.max_rows} "
                      f"(raise HARNESS_ML_MAX_ROWS)", 413)

    experiment_id = store.create_experiment(
        title=config.title, dataset_id=dataset_id, dataset_version=version,
        target=manifest.get("target") or {}, feature_names=list(manifest.get("featureNames") or []),
        model_family=config.model_family, hyperparameters=config.hyperparameters,
        selection=config.selection, split_spec=config.split.to_dict(), seed=config.seed,
        task=manifest.get("target", {}).get("task"), owner=owner)
    run_id = store.create_run(experiment_id)
    started = time.time()

    def _should_cancel() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    def _on_progress(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)

    try:
        result = await asyncio.to_thread(
            _run_experiment, arrays, manifest, config,
            should_cancel=_should_cancel, on_progress=_on_progress,
            max_folds=cfg.max_folds, deadline=time.monotonic() + cfg.max_seconds)
    except asyncio.CancelledError:
        # A hard cancel (Fabric) must not leave a run stuck "running".
        store.finish_run(run_id, status="cancelled",
                         error={"code": "CANCELLED", "message": "training was cancelled"},
                         duration_ms=int((time.time() - started) * 1000), stage="cancelled")
        store.audit(action="experiment.run", subject_type="run", subject_id=run_id,
                    actor=owner, detail={"status": "cancelled"})
        raise
    except Exception as exc:  # noqa: BLE001 - failures are recorded, not hidden
        code = getattr(exc, "code", "ML_ERROR")
        duration_ms = int((time.time() - started) * 1000)
        status = "cancelled" if code == "CANCELLED" else (
            "timed_out" if code == "TIME_BUDGET_EXCEEDED" else "failed")
        store.finish_run(run_id, status=status,
                         error={"code": code, "message": str(exc)},
                         duration_ms=duration_ms, stage=status)
        store.audit(action="experiment.run", subject_type="run", subject_id=run_id,
                    actor=owner, detail={"status": status, "code": code})
        return {"status": status, "experimentId": experiment_id, "runId": run_id,
                "error": str(exc), "errorCode": code}

    duration_ms = int((time.time() - started) * 1000)
    result["experimentId"] = experiment_id
    result["runId"] = run_id
    artifact = store.save_artifact(result, kind="run-result")
    store.record_folds(run_id, result["folds"])
    store.finish_run(run_id, status="completed", metrics=result["pooledMetrics"],
                     artifact_id=artifact["id"], duration_ms=duration_ms)

    registered = None
    if config.model_family and (payload.get("registerModel") or payload.get("register")):
        registered = register_from_run(run_id, name=payload.get("name") or config.title, owner=owner)

    store.audit(action="experiment.run", subject_type="run", subject_id=run_id, actor=owner,
                detail={"status": "completed", "durationMs": duration_ms})
    return {"experimentId": experiment_id, "runId": run_id, "artifactId": artifact["id"],
            "status": "completed", "result": result, "registered": registered}


async def execute_experiment(payload: dict[str, Any], *, owner: Optional[str] = None) -> dict[str, Any]:
    """Inline execution: never reports a partial run as done, and raises on a
    non-completed status so a synchronous caller cannot mistake a failure for
    success."""
    outcome = await run_experiment_job(payload, owner=owner)
    if outcome.get("status") != "completed":
        raise MLError(outcome.get("errorCode") or "ML_ERROR",
                      outcome.get("error") or "the experiment did not complete",
                      409 if outcome.get("status") == "cancelled" else 500)
    return outcome


async def submit_experiment_background(payload: dict[str, Any], *, owner: Optional[str] = None) -> dict[str, Any]:
    """Submit a training experiment as a durable Execution Fabric job.

    Returns ``{jobId, status, mode}`` immediately; the job runs on the dedicated
    ML worker (isolated, timeout-bounded, cancellable, resource-limited). Poll
    with `get_job`."""
    from .fabric import submit_ml_experiment  # noqa: PLC0415

    return await submit_ml_experiment(payload, owner=owner)


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    """Fetch a Fabric ML job (status, progress, output)."""
    from .fabric import get_ml_job  # noqa: PLC0415

    return get_ml_job(job_id)


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    from .fabric import list_ml_jobs  # noqa: PLC0415

    return list_ml_jobs(limit=limit)


async def cancel_job(job_id: str) -> dict[str, Any]:
    from .fabric import cancel_ml_job  # noqa: PLC0415

    return await cancel_ml_job(job_id)


def get_run_result(run_id: str) -> Optional[dict[str, Any]]:
    return _require_store().get_run_result(run_id)


def list_experiments(limit: int = 50) -> list[dict[str, Any]]:
    return _require_store().list_experiments(limit=limit)


def list_runs(experiment_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return _require_store().list_runs(experiment_id, limit=limit)


# ── model registry ───────────────────────────────────────────────────────────


def register_from_run(run_id: str, *, name: str, owner: Optional[str] = None,
                      model_id: Optional[str] = None) -> dict[str, Any]:
    store = _require_store()
    run = store.get_run_result(run_id)
    if run is None or not run.get("result"):
        raise MLError(INVALID_INPUT, f"run {run_id} has no result to register", 404)
    result = run["result"]
    final_state = result.get("finalModel")
    if not final_state:
        raise MLError(INVALID_INPUT, "the run did not produce a final model", 422)
    experiment = store.get_experiment(run["experimentId"]) or {}
    signature = {
        "task": result.get("task"), "family": result.get("modelFamily"),
        "features": final_state.get("featureNames") or [],
        "selected": final_state.get("selected") or [],
        "nFeatures": len(final_state.get("featureNames") or []),
    }
    deps = result.get("dependencyVersions") or {}
    metrics = {"pooled": result.get("pooledMetrics"), "holdout": result.get("finalEvaluation")}
    reg = store.register_model(
        name=name, family=result.get("modelFamily"), task=result.get("task"), run_id=run_id,
        dataset_id=experiment.get("datasetId") or "", dataset_version=experiment.get("datasetVersion") or "",
        model_state=final_state, metrics=metrics, signature=signature, deps=deps,
        owner=owner, model_id=model_id)
    store.audit(action="model.register", subject_type="model", subject_id=reg["modelId"],
                actor=owner, detail={"version": reg["version"], "runId": run_id})
    return reg


def list_models(limit: int = 100) -> list[dict[str, Any]]:
    return _require_store().list_models(limit=limit)


def get_model_version(model_id: str, version: Optional[str] = None) -> Optional[dict[str, Any]]:
    return _require_store().get_model_version(model_id, version)


def transition_model(model_id: str, *, version: str, action: str, actor: Optional[str],
                     reason: Optional[str] = None) -> dict[str, Any]:
    """Controlled lifecycle transitions. Research approval is NOT trading auth."""
    store = _require_store()
    mapping = {
        "evaluate": "evaluated",
        "approve_research": "approved_research",
        "archive": "archived",
    }
    if action not in mapping:
        raise MLError(INVALID_INPUT, f"unknown lifecycle action {action!r}")
    result = store.transition_model(model_id, version=version, action=action, actor=actor,
                                    reason=reason, to_status=mapping[action])
    store.audit(action=f"model.{action}", subject_type="model", subject_id=model_id,
                actor=actor, detail={"version": version, "reason": reason})
    return result


def verify_model_artifact(model_id: str, version: Optional[str] = None) -> dict[str, Any]:
    store = _require_store()
    mv = store.get_model_version(model_id, version)
    if mv is None:
        raise MLError(INVALID_INPUT, f"model {model_id} was not found", 404)
    check = store.verify_artifact(mv["stateArtifactId"])
    return {"modelId": model_id, "version": mv["version"], **check}


def load_model_for_inference(model_id: str, version: Optional[str] = None) -> dict[str, Any]:
    """Load a registered model state and reconstruct the estimator.

    Returns the estimator + the selected feature indices and feature names needed
    to run inference. The artifact hash is verified before loading.
    """
    from .adapters import load_model  # noqa: PLC0415

    store = _require_store()
    mv = store.get_model_version(model_id, version)
    if mv is None:
        raise MLError(INVALID_INPUT, f"model {model_id} was not found", 404)
    check = store.verify_artifact(mv["stateArtifactId"])
    if not check["ok"]:
        raise MLError("REPRODUCIBILITY_MISMATCH",
                      f"model artifact hash mismatch for {model_id}@{mv['version']}", 409)
    artifact = store.get_artifact(mv["stateArtifactId"])
    state = artifact["content"]
    model = load_model(state)
    return {"modelId": model_id, "version": mv["version"], "family": mv["family"],
            "task": mv["task"], "model": model, "signature": mv["signature"],
            "featureNames": state.get("featureNames") or [],
            "selected": state.get("selected") or [],
            "preprocessing": state.get("preprocessing")}


def predict_with_model(model_id: str, X: np.ndarray, version: Optional[str] = None) -> dict[str, Any]:
    """Run inference with a registered model version (honest about the task)."""
    from .features import apply_selection  # noqa: PLC0415

    loaded = load_model_for_inference(model_id, version)
    model = loaded["model"]
    pre = loaded["preprocessing"] or {}
    X = np.asarray(X, dtype=float)
    if pre.get("mean") is not None and pre.get("std") is not None:
        X = (X - np.asarray(pre["mean"])) / np.asarray(pre["std"])
    X = apply_selection(X, loaded["selected"])
    pred = model.predict(X).tolist()
    proba = model.predict_proba(X) if loaded["task"] == "classification" else None
    return {"modelId": model_id, "version": loaded["version"], "task": loaded["task"],
            "pred": [None if not np.isfinite(v) else float(v) for v in pred],
            "proba": None if proba is None else np.asarray(proba, dtype=float).tolist()}


# ── reproducibility ──────────────────────────────────────────────────────────


def reproduce_run(run_id: str, *, tolerance: float = 1e-6) -> dict[str, Any]:
    """Re-run an experiment from its recorded configuration and compare metrics.

    Numeric agreement within ``tolerance`` is reported; a mismatch is surfaced,
    never hidden. Bitwise equality is not claimed.
    """
    store = _require_store()
    run = store.get_run_result(run_id)
    if run is None or not run.get("result"):
        raise MLError(INVALID_INPUT, f"run {run_id} has no stored result", 404)
    original = run["result"]
    experiment = store.get_experiment(run["experimentId"])
    if experiment is None:
        raise MLError(INVALID_INPUT, "the experiment record is missing", 404)
    ds = store.get_dataset_version(experiment["datasetId"], experiment["datasetVersion"])
    arrays = deserialize_arrays(ds["artifact"]["content"]["arrays"])
    manifest = ds["manifest"]
    config = _config_from_payload({**experiment, "datasetId": experiment["datasetId"],
                                   "datasetVersion": experiment["datasetVersion"]})
    result = _run_experiment(arrays, manifest, config)
    diffs = _compare_metrics(original.get("pooledMetrics", {}), result.get("pooledMetrics", {}),
                             tol=tolerance)
    within = all(d["within"] for d in diffs if d["delta"] is not None)
    return {"runId": run_id, "reproduced": True, "withinTolerance": within,
            "tolerance": tolerance, "metricDiffs": diffs,
            "original": original.get("pooledMetrics"), "reproducedMetrics": result.get("pooledMetrics")}


def _compare_metrics(a: dict[str, Any], b: dict[str, Any], tol: float = 1e-6) -> list[dict[str, Any]]:
    out = []
    for key in sorted(set(a) | set(b)):
        av, bv = a.get(key), b.get(key)
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            delta = abs(float(av) - float(bv))
            out.append({"metric": key, "original": av, "reproduced": bv, "delta": delta,
                        "within": delta <= max(tol, 1e-6 * max(abs(av), 1.0))})
        else:
            out.append({"metric": key, "original": av, "reproduced": bv, "delta": None,
                        "within": av == bv})
    return out


def engine_capabilities() -> dict[str, Any]:
    from . import adapters  # noqa: PLC0415

    return {"available": _store is not None, "config": get_ml_config().to_dict(),
            "models": adapters.model_capabilities()}


__all__ = [
    "set_ml_store",
    "get_ml_store",
    "serialize_arrays",
    "deserialize_arrays",
    "build_dataset_version",
    "list_datasets",
    "get_dataset_version",
    "list_dataset_versions",
    "run_experiment_job",
    "execute_experiment",
    "submit_experiment_background",
    "get_job",
    "list_jobs",
    "cancel_job",
    "get_run_result",
    "list_experiments",
    "list_runs",
    "register_from_run",
    "list_models",
    "get_model_version",
    "transition_model",
    "verify_model_artifact",
    "load_model_for_inference",
    "predict_with_model",
    "reproduce_run",
    "engine_capabilities",
]
