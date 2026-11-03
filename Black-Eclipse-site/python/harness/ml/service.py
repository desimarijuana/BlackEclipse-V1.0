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
from .models import (
    DatasetSpec, ExperimentConfig, MODEL_UNAVAILABLE, MLError, SplitSpec, TargetSpec,
)
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
        task=target_raw.get("task"),
    )
    source = str(payload.get("source") or "market")
    return DatasetSpec(
        source=source,
        symbols=list(payload.get("symbols") or []),
        interval=payload.get("interval", "1d"),
        start=payload.get("start"),
        end=payload.get("end"),
        feature_names=list(payload.get("featureNames") or []),
        target=target,
        missing_policy=payload.get("missingPolicy", "drop"),
        min_coverage=float(payload.get("minCoverage", 0.5)),
        # A records dataset is not an equity panel; label it honestly unless the
        # caller declares something specific.
        asset_class=payload.get("assetClass") or ("table" if source == "records" else "equity"),
        time_column=payload.get("timeColumn"),
        id_column=payload.get("idColumn"),
    )


def _payload_records(payload: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    records = payload.get("records")
    if records is None:
        return None
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise MLError(INVALID_INPUT, "records must be a list of row objects", 422)
    return records


def plan_model(payload: dict[str, Any]) -> dict[str, Any]:
    """Plan (never train) a model recipe for a dataset version or an inline profile.

    A plan carries no metric: it is a proposal until `execute_experiment` runs it.
    """
    from .recipes import (  # noqa: PLC0415
        DataProfile, plan_recipe, profile_from_manifest, to_experiment_payload,
    )

    dataset_id = str(payload.get("datasetId") or "")
    version = str(payload.get("datasetVersion") or "")
    if dataset_id:
        record = get_dataset_version(dataset_id, version) if version else None
        if record is None:
            versions = list_dataset_versions(dataset_id)
            record = get_dataset_version(dataset_id, versions[0]["version"]) if versions else None
        if record is None:
            raise MLError(INVALID_INPUT, f"dataset {dataset_id!r} was not found", 404)
        profile = profile_from_manifest(record.get("manifest") or {})
        version = str(record.get("version") or version)
    else:
        profile = DataProfile(rows=int(payload.get("rows") or 0),
                              features=int(payload.get("features") or 0),
                              task=str(payload.get("task") or "classification"),
                              class_count=payload.get("classCount"))

    plan = plan_recipe(profile, preference=str(payload.get("preference") or "balanced"))
    return {
        "plan": plan.to_dict(),
        "profile": profile.to_dict(),
        "experiment": (to_experiment_payload(plan, dataset_id=dataset_id,
                                             dataset_version=version,
                                             seed=int(payload.get("seed", 42)))
                       if dataset_id else None),
    }


async def build_dataset_version(
    gateway: Any, payload: dict[str, Any], *, name: str, description: Optional[str] = None,
    owner: Optional[str] = None, registry: Any = None,
) -> dict[str, Any]:
    """Build AND persist one immutable dataset version."""
    store = _require_store()
    spec = _dataset_spec(payload)
    records = _payload_records(payload)
    cfg = get_ml_config()
    if records is not None and len(records) > cfg.max_rows:
        raise MLError("TOO_MANY_ROWS",
                      f"dataset has {len(records)} rows; the limit is {cfg.max_rows} "
                      f"(raise HARNESS_ML_MAX_ROWS)", 413)
    started = time.time()
    built = await build_dataset(gateway, spec, registry=registry, records=records)
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
        calibration=str(payload.get("calibration") or "none"),
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


async def compare_models(payload: dict[str, Any], *, owner: Optional[str] = None,
                          cancel_event: Any = None,
                          progress: Any = None) -> dict[str, Any]:
    """Train several families on ONE dataset version with the SAME folds, then compare.

    Every family sees the caller's exact split spec, seed and selection config, so
    a comparison can never be won by an easier validation design. Each family is a
    normal persisted run (same store rows, artifacts and audit), and the verdict is
    computed by `ml.compare.build_comparison`, which refuses to rank an unmeasured
    metric or a task with no ground truth.
    """
    from .compare import MAX_FAMILIES, build_comparison  # noqa: PLC0415

    families = [str(f) for f in (payload.get("families") or [])]
    if not families:
        raise MLError(INVALID_INPUT, "families is required (a list of model families)", 422)
    if len(families) > MAX_FAMILIES:
        raise MLError(INVALID_INPUT,
                      f"a comparison takes at most {MAX_FAMILIES} families "
                      f"(got {len(families)}); use several runs for a larger grid", 422)

    dataset_id = str(payload.get("datasetId") or "")
    version = str(payload.get("datasetVersion") or "")
    record = get_dataset_version(dataset_id, version)
    if record is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    manifest = record.get("manifest") or {}
    task = str(manifest.get("target", {}).get("task") or payload.get("task") or "")
    if not task:
        raise MLError(INVALID_INPUT, "the dataset does not declare a task", 422)

    base = {key: payload.get(key) for key in
            ("datasetId", "datasetVersion", "selection", "split", "seed", "scale",
             "featureNames")}
    runs: list[dict[str, Any]] = []
    total = len(families)
    for position, family in enumerate(families):
        if cancel_event is not None and cancel_event.is_set():
            raise MLError("CANCELLED", "the comparison was cancelled", 409)
        if progress is not None:
            progress(position / max(1, total), f"{family} ({position + 1}/{total})")
        body = {
            **base,
            "modelFamily": family,
            "title": f"arena: {family}",
            "task": task,
            "hyperparameters": (((payload.get("hyperparameters") or {}).get(family, {})
                                 if isinstance(payload.get("hyperparameters"), dict) else {})),
        }
        runs.append(await run_experiment_job(body, owner=owner,
                                             cancel_event=cancel_event,
                                             progress=None))

    comparison = build_comparison(runs, task)
    return {
        "comparison": comparison,
        "runs": [{"modelFamily": (r.get("result") or {}).get("modelFamily"),
                  "runId": r.get("runId"), "experimentId": r.get("experimentId"),
                  "status": r.get("status"), "error": r.get("error")} for r in runs],
    }


def export_dataset(dataset_id: str, version: str, *, fmt: str = "csv",
                   limit: int = 10_000) -> dict[str, Any]:
    """The dataset version as portable text (CSV or JSONL), bounded by ``limit``.

    Why a text export: a model is only as portable as its data. The rows come from
    the stored artifact (features), the label array and the recorded timestamps —
    no re-fetch, no re-derivation — and a truncation is stated, never silent. A
    column target also carries its human labels, so an exported row is readable
    without the manifest.
    """
    import csv as _csv  # noqa: PLC0415
    import io  # noqa: PLC0415
    import json  # noqa: PLC0415

    if fmt not in ("csv", "jsonl"):
        raise MLError(INVALID_INPUT, f"unknown export format {fmt!r} (csv | jsonl)", 422)
    store = _require_store()
    record = store.get_dataset_version(dataset_id, version)
    if record is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    arrays = deserialize_arrays(record["artifact"]["content"]["arrays"])
    manifest = record.get("manifest") or {}
    names = list(arrays.get("featureNames") or [])
    X = np.asarray(arrays["X"], dtype=float)
    y = np.asarray(arrays["y"], dtype=float)
    timestamps = list(arrays.get("timestamps") or [])
    labels = (manifest.get("target") or {}).get("classLabels") or []

    total = int(X.shape[0])
    take = max(0, min(total, int(limit)))
    target_name = str((manifest.get("target") or {}).get("column") or "target")

    def _label(code: float) -> Optional[str]:
        if labels and np.isfinite(code) and 0 <= int(code) < len(labels):
            return str(labels[int(code)])
        return None

    if fmt == "csv":
        buffer = io.StringIO()
        writer = _csv.writer(buffer)
        header = [*names, target_name]
        if labels:
            header.append(f"{target_name}Label")
        header.append("timestamp")
        writer.writerow(header)
        for i in range(take):
            row: list[Any] = [("" if not np.isfinite(v) else repr(float(v))) for v in X[i]]
            row.append("" if not np.isfinite(y[i]) else repr(float(y[i])))
            if labels:
                row.append(_label(y[i]) or "")
            row.append(timestamps[i] if i < len(timestamps) else "")
            writer.writerow(row)
        content = buffer.getvalue()
        content_type = "text/csv; charset=utf-8"
    else:
        lines = []
        for i in range(take):
            item: dict[str, Any] = {name: (None if not np.isfinite(X[i, j]) else float(X[i, j]))
                                    for j, name in enumerate(names)}
            item[target_name] = None if not np.isfinite(y[i]) else float(y[i])
            if labels:
                item[f"{target_name}Label"] = _label(y[i])
            item["timestamp"] = timestamps[i] if i < len(timestamps) else None
            lines.append(json.dumps(item, sort_keys=False))
        content = "\n".join(lines)
        content_type = "application/x-ndjson; charset=utf-8"

    return {"datasetId": dataset_id, "version": version, "format": fmt,
            "contentType": content_type,
            "filename": f"{dataset_id}@{version}.{fmt}",
            "rows": take, "totalRows": total, "truncated": take < total,
            "content": content}


async def search_hyperparameters(payload: dict[str, Any], *,
                                  owner: Optional[str] = None,
                                  cancel_event: Any = None,
                                  progress: Any = None) -> dict[str, Any]:
    """Run N configurations of ONE family over a declared space, on the same folds.

    Every trial is a normal persisted run. The ranking reuses the arena's rule, so
    an unmeasured trial cannot win and a margin inside the fold noise is reported
    as no clear winner. The note always states that the winner was SELECTED on the
    folds it is scored on, which makes its score optimistic — a fresh-period
    confirmation run is the honest next step.
    """
    from .compare import build_comparison  # noqa: PLC0415
    from .search import MAX_TRIALS, plan_trials  # noqa: PLC0415

    family = str(payload.get("modelFamily") or "")
    if not family:
        raise MLError(INVALID_INPUT, "modelFamily is required", 422)
    dataset_id = str(payload.get("datasetId") or "")
    version = str(payload.get("datasetVersion") or "")
    record = get_dataset_version(dataset_id, version)
    if record is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    manifest = record.get("manifest") or {}
    task = str(manifest.get("target", {}).get("task") or payload.get("task") or "")

    max_trials = int(payload.get("maxTrials") or 8)
    if max_trials < 1 or max_trials > MAX_TRIALS:
        raise MLError(INVALID_INPUT,
                      f"maxTrials must be between 1 and {MAX_TRIALS}", 422)
    max_seconds = float(payload.get("maxSeconds") or 300.0)
    seed = int(payload.get("seed", 42))

    configs, sampled = plan_trials(
        family, grid=payload.get("grid"), n_trials=max_trials, seed=seed)
    configs = configs[:max_trials]

    base = {key: payload.get(key) for key in
            ("datasetId", "datasetVersion", "selection", "split", "scale",
             "featureNames", "calibration")}
    started = time.monotonic()
    outcomes: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    stopped_reason = "exhausted"
    for index, hyperparameters in enumerate(configs):
        if cancel_event is not None and cancel_event.is_set():
            raise MLError("CANCELLED", "the search was cancelled", 409)
        if time.monotonic() - started > max_seconds:
            stopped_reason = "maxSeconds"
            break
        if progress is not None:
            progress(index / max(1, len(configs)), f"trial {index + 1}/{len(configs)}")
        body = {**base, "modelFamily": family, "hyperparameters": hyperparameters,
                "title": f"search {family} #{index + 1}", "task": task}
        outcome = await run_experiment_job(body, owner=owner,
                                           cancel_event=cancel_event, progress=None)
        outcomes.append(outcome)
        trials.append({
            "index": index, "hyperparameters": hyperparameters,
            "runId": outcome.get("runId"), "status": outcome.get("status"),
            "error": outcome.get("error"),
        })
        if index + 1 >= max_trials:
            stopped_reason = "maxTrials"
            break

    comparison = build_comparison(outcomes, task)
    best = None
    ranking = comparison.get("ranking") or []
    if ranking:
        top = ranking[0]
        match = next((t for t in trials if t["runId"] == top["runId"]), None)
        if match is not None:
            # The empirical best is always reported; whether it is statistically
            # separable from the runner-up is a separate, honest field.
            best = {**match, "value": top["value"],
                    "metric": comparison["primaryMetric"]["key"],
                    "withinNoise": comparison.get("winner") is None}

    caveat = ("the winner was selected on the same folds it is scored on, so its score is "
              "optimistic — confirm it with the final holdout or a fresh period")
    note = comparison.get("note") or ""
    if best is not None and best["withinNoise"]:
        note = (note + " " if note else "") + (
            f"the top-ranked config {best['hyperparameters']} is reported as the "
            "empirical best, but it is not clearly ahead of the runner-up")
    note = (note + " " if note else "") + caveat

    return {"family": family, "task": task, "sampled": sampled,
            "trials": trials, "comparison": comparison, "best": best,
            "stoppedReason": stopped_reason,
            "elapsedMs": int((time.monotonic() - started) * 1000),
            "note": note}


async def submit_compare_background(payload: dict[str, Any], *, owner: Optional[str] = None) -> dict[str, Any]:
    """Submit an arena comparison as a durable Fabric job (poll with get_job)."""
    from .fabric import submit_ml_composite  # noqa: PLC0415

    return await submit_ml_composite(payload, kind="compare", owner=owner)


async def submit_search_background(payload: dict[str, Any], *, owner: Optional[str] = None) -> dict[str, Any]:
    """Submit a hyperparameter search as a durable Fabric job (poll with get_job)."""
    from .fabric import submit_ml_composite  # noqa: PLC0415

    return await submit_ml_composite(payload, kind="search", owner=owner)


def build_training_corpus(dataset_id: str, version: str, *,
                           limit: int = 2000) -> dict[str, Any]:
    """A distillation corpus (chat JSONL) from one dataset version.

    Behaviour distillation of the decision the dataset encodes — not general
    instruction data, and the note says so. Incomplete rows are skipped, never
    filled.
    """
    from .distill import MAX_EXAMPLES, build_examples, corpus_hash, to_jsonl  # noqa: PLC0415

    store = _require_store()
    record = store.get_dataset_version(dataset_id, version)
    if record is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    arrays = deserialize_arrays(record["artifact"]["content"]["arrays"])
    manifest = record.get("manifest") or {}
    cap = max(1, min(int(limit), MAX_EXAMPLES))
    examples = build_examples(arrays, manifest, limit=cap)
    if not examples:
        raise MLError("INSUFFICIENT_DATA",
                      "no complete rows to distil (features or labels are missing)", 422)
    return {
        "datasetId": dataset_id, "version": version,
        "format": "jsonl", "rows": len(examples),
        "rowsConsidered": int(min(cap, len(arrays["X"]))),
        "hash": corpus_hash(examples), "content": to_jsonl(examples),
        "note": ("a behaviour-distillation corpus (features -> the dataset's own label), "
                 "not general instruction data; evaluate any fine-tune on held-out data"),
    }


def fine_tune_adapter(payload: dict[str, Any]) -> dict[str, Any]:
    """Materialise the corpus + recipe, and train only if the optional stack exists."""
    import os  # noqa: PLC0415

    from .distill import build_examples, to_jsonl  # noqa: PLC0415
    from .llm import adapter_support, train_adapter, write_recipe  # noqa: PLC0415

    dataset_id = str(payload.get("datasetId") or "")
    version = str(payload.get("datasetVersion") or "")
    name = str(payload.get("name") or "adapter")
    base_model = str(payload.get("baseModel") or "Qwen/Qwen2.5-0.5B-Instruct")
    store = _require_store()
    record = store.get_dataset_version(dataset_id, version)
    if record is None:
        raise MLError(INVALID_INPUT, f"dataset {dataset_id}@{version} was not found", 404)
    arrays = deserialize_arrays(record["artifact"]["content"]["arrays"])
    manifest = record.get("manifest") or {}
    examples = build_examples(arrays, manifest, limit=int(payload.get("limit", 2000)))
    if not examples:
        raise MLError("INSUFFICIENT_DATA", "no complete rows to distil", 422)

    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.lower())[:40] or "adapter"
    out_dir = os.path.join(os.getcwd(), ".black-eclipse", "ml", "adapters", slug)
    os.makedirs(out_dir, exist_ok=True)
    corpus_path = os.path.join(out_dir, "corpus.jsonl")
    with open(corpus_path, "w", encoding="utf-8") as handle:
        handle.write(to_jsonl(examples))

    from .distill import corpus_hash  # noqa: PLC0415

    recipe = write_recipe(corpus_path, out_dir, base_model=base_model, manifest={
        "dataset": f"{dataset_id}@{version}", "rows": len(examples),
        "corpusHash": corpus_hash(examples), "name": name,
    })
    available, reason = adapter_support()
    trained = None
    if payload.get("train"):
        if not available:
            raise MLError(
                MODEL_UNAVAILABLE,
                f"fine-tuning needs the optional stack ({reason}); the corpus and recipe "
                f"are written at {out_dir} — install the deps or run train_lora.py there",
                503,
            )
        trained = train_adapter(corpus_path, out_dir, base_model=base_model,
                                epochs=int(payload.get("epochs", 1)))
    return {
        "name": name, "baseModel": base_model, "rows": len(examples),
        "corpus": corpus_path, "recipe": recipe,
        "depsAvailable": available, "depsReason": reason,
        "trained": trained,
        "serveHint": ("serve the adapter with vLLM or Ollama (an OpenAI-compatible "
                      "endpoint) and select it in Settings > AI / LLM"),
    }


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
        "classLabels": result.get("classLabels"),
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
    # A registered model becomes a first-class chat capability immediately.
    try:
        from .tools import register_model_tool  # noqa: PLC0415

        register_model_tool(reg["modelId"], name, result.get("task"))
    except Exception:  # noqa: BLE001 - never fail a registration over a tool name
        pass
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


def resolve_model_id(model_id_or_name: str) -> str:
    """An exact model id, or the id of the model with that NAME (newest first).

    Chat says "predict with my momentum model", not an id; the resolution is exact
    (case-sensitive, first match in the newest-first list) so a typo fails instead
    of silently picking something else.
    """
    if not model_id_or_name:
        raise MLError(INVALID_INPUT, "a model id or name is required", 422)
    store = _require_store()
    if store.get_model_version(model_id_or_name) is not None:
        return model_id_or_name
    for record in store.list_models(limit=200):
        if record.get("name") == model_id_or_name:
            return str(record["id"])
    raise MLError(INVALID_INPUT, f"model {model_id_or_name!r} was not found", 404)


def model_drift(model_id: str, *, dataset_id: str, dataset_version: str,
                version: Optional[str] = None) -> dict[str, Any]:
    """Drift between the dataset a model was trained on and a later version.

    Reads the two stored feature matrices and compares them per feature (PSI/KS).
    It never calls a model and never imputes: a feature that only one side has is
    reported as a schema change.
    """
    from .drift import compare_features  # noqa: PLC0415

    store = _require_store()
    mv = store.get_model_version(model_id, version)
    if mv is None:
        raise MLError(INVALID_INPUT, f"model {model_id} was not found", 404)
    reference_id = str(mv.get("datasetId") or "")
    reference_version = str(mv.get("datasetVersion") or "")
    ref_ds = store.get_dataset_version(reference_id, reference_version)
    cur_ds = store.get_dataset_version(dataset_id, dataset_version)
    if ref_ds is None or cur_ds is None:
        raise MLError(INVALID_INPUT, "the reference or comparison dataset version was not found", 404)

    def _columns(ds: dict[str, Any]) -> dict[str, np.ndarray]:
        arrays = deserialize_arrays(ds["artifact"]["content"]["arrays"])
        names = list(ds["manifest"].get("featureNames") or arrays.get("featureNames") or [])
        X = np.asarray(arrays["X"], dtype=float)
        return {name: X[:, index] for index, name in enumerate(names) if index < X.shape[1]}

    feature_names = list((mv.get("signature") or {}).get("features") or [])
    report = compare_features(_columns(ref_ds), _columns(cur_ds),
                              feature_names=feature_names or None)
    store.audit(action="model.drift", subject_type="model", subject_id=model_id,
                actor=None, detail={"version": mv["version"],
                                    "against": f"{dataset_id}@{dataset_version}",
                                    "verdict": report["verdict"]})
    return {"modelId": model_id, "version": mv["version"], "task": mv["task"],
            "reference": {"datasetId": reference_id, "datasetVersion": reference_version},
            "current": {"datasetId": dataset_id, "datasetVersion": dataset_version},
            "report": report}


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
    if state.get("family") == "ensemble":
        # An ensemble carries references, not weights: each member is loaded and
        # predicted with its own preprocessing at inference time.
        return {"modelId": model_id, "version": mv["version"], "family": "ensemble",
                "task": mv["task"], "model": None,
                "members": state.get("members") or [],
                "signature": mv["signature"],
                "featureNames": state.get("featureNames") or [],
                "selected": [], "calibration": None, "preprocessing": None}
    model = load_model(state)
    return {"modelId": model_id, "version": mv["version"], "family": mv["family"],
            "task": mv["task"], "model": model, "signature": mv["signature"],
            "featureNames": state.get("featureNames") or [],
            "selected": state.get("selected") or [],
            "calibration": state.get("calibration"),
            "preprocessing": state.get("preprocessing")}


def _predict_loaded(loaded: dict[str, Any], X: np.ndarray) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """Prediction (and probability) for one loaded member, with its own preprocessing."""
    from .features import apply_selection  # noqa: PLC0415

    model = loaded["model"]
    pre = loaded.get("preprocessing") or {}
    X = np.asarray(X, dtype=float)
    if pre.get("mean") is not None and pre.get("std") is not None:
        X = (X - np.asarray(pre["mean"])) / np.asarray(pre["std"])
    X = apply_selection(X, loaded.get("selected") or [])
    pred = model.predict(X)
    proba = model.predict_proba(X) if loaded.get("task") == "classification" else None
    calibration = loaded.get("calibration")
    if proba is not None and calibration:
        from .calibration import apply_calibration  # noqa: PLC0415

        arr = np.asarray(proba, dtype=float)
        if arr.ndim == 2 and arr.shape[1] == 2:
            p1 = apply_calibration(calibration, arr[:, 1])
            proba = np.column_stack([1.0 - p1, p1])
    return pred, proba


def create_ensemble(payload: dict[str, Any], *, owner: Optional[str] = None) -> dict[str, Any]:
    """Register an ensemble of already-trained models (mean of probabilities).

    Nothing is re-fitted: the members' OWN out-of-fold predictions are aligned by
    row index and blended, so the ensemble's score is measured on the same
    held-out rows the members were scored on. Members must share one dataset
    version and one task; different folds are refused rather than averaged.
    """
    from .ensemble import MAX_MEMBERS, align_out_of_fold, blend  # noqa: PLC0415
    from .metrics import evaluate_classification, evaluate_regression  # noqa: PLC0415

    members_in = payload.get("members") or []
    if len(members_in) < 2:
        raise MLError(INVALID_INPUT, "an ensemble needs at least two members", 422)
    if len(members_in) > MAX_MEMBERS:
        raise MLError(INVALID_INPUT, f"an ensemble takes at most {MAX_MEMBERS} members", 422)

    store = _require_store()
    resolved: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in members_in:
        model_id = resolve_model_id(str(entry.get("modelId") or entry.get("modelName") or ""))
        mv = store.get_model_version(model_id, entry.get("version"))
        if mv is None:
            raise MLError(INVALID_INPUT, f"model {model_id} was not found", 404)
        run = store.get_run_result(mv["runId"])
        if run is None or not run.get("result"):
            raise MLError(INVALID_INPUT,
                          f"model {model_id}@{mv['version']} has no stored run result", 422)
        resolved.append((mv, run))

    task = str(resolved[0][0]["task"])
    if any(mv["task"] != task for mv, _ in resolved):
        raise MLError(INVALID_INPUT, "members must all solve the same task", 422)
    datasets = {(mv["datasetId"], mv["datasetVersion"]) for mv, _ in resolved}
    if len(datasets) != 1:
        raise MLError(INVALID_INPUT,
                      "members must be trained on the SAME dataset version — otherwise "
                      "their out-of-fold rows are not comparable", 422)

    aligned = [{"rowIndex": run["result"]["oos"]["rowIndex"],
                "pred": run["result"]["oos"]["pred"],
                "proba": run["result"]["oos"].get("proba")} for _, run in resolved]
    rows, predictions, probabilities = align_out_of_fold(aligned)
    combined = blend(task, predictions, probabilities)

    first_oos = resolved[0][1]["result"]["oos"]
    y_by_row = {int(r): float(v) for r, v in zip(first_oos["rowIndex"], first_oos["y"])
                if v is not None}
    y = np.asarray([y_by_row[row] for row in rows], dtype=float)
    pred = np.asarray(combined["pred"], dtype=float)

    if task == "classification":
        proba = None if combined["proba"] is None else np.asarray(combined["proba"], dtype=float)
        n_classes = int(proba.shape[1]) if proba is not None else int(pred.max()) + 1
        metrics = evaluate_classification(y, pred, proba, n_classes)
    else:
        metrics = evaluate_regression(y, pred)

    feature_names = list((resolved[0][1]["result"].get("finalModel") or {}).get("featureNames") or [])
    class_labels = (resolved[0][0].get("signature") or {}).get("classLabels")
    member_refs = [{"modelId": mv["modelId"], "version": mv["version"],
                    "family": mv["family"]} for mv, _ in resolved]
    name = str(payload.get("name") or "ensemble")
    state = {"family": "ensemble", "task": task, "rule": "mean", "members": member_refs,
             "featureNames": feature_names, "classLabels": class_labels}
    reg = store.register_model(
        name=name, family="ensemble", task=task, run_id=str(resolved[0][0]["runId"]),
        dataset_id=str(resolved[0][0]["datasetId"]),
        dataset_version=str(resolved[0][0]["datasetVersion"]),
        model_state=state, metrics={"pooled": metrics, "members": member_refs},
        signature={"task": task, "features": feature_names, "classLabels": class_labels,
                   "members": len(member_refs)},
        deps={"ensemble": "mean"}, owner=owner)
    store.audit(action="ensemble.create", subject_type="model", subject_id=reg["modelId"],
                actor=owner, detail={"members": len(member_refs), "task": task})
    try:
        from .tools import register_model_tool  # noqa: PLC0415

        register_model_tool(reg["modelId"], name, task)
    except Exception:  # noqa: BLE001 - never fail a registration over a tool name
        pass
    return {"modelId": reg["modelId"], "version": reg["version"], "name": name,
            "task": task, "members": member_refs, "rows": len(rows),
            "metrics": metrics, "note": (
                "the ensemble is scored on the members' own out-of-fold rows; it is a "
                "mean of their predictions and adds no new information beyond them")}


def predict_with_model(model_id: str, X: np.ndarray, version: Optional[str] = None) -> dict[str, Any]:
    """Run inference with a registered model version (honest about the task)."""
    loaded = load_model_for_inference(model_id, version)
    if loaded.get("family") == "ensemble":
        from .ensemble import blend  # noqa: PLC0415

        member_preds: list[list[float]] = []
        member_probas: list[Optional[list[list[float]]]] = []
        for member in loaded.get("members") or []:
            inner = load_model_for_inference(member["modelId"], member.get("version"))
            inner_pred, inner_proba = _predict_loaded(inner, X)
            member_preds.append(np.asarray(inner_pred, dtype=float).tolist())
            member_probas.append(None if inner_proba is None
                                 else np.asarray(inner_proba, dtype=float).tolist())
        combined = blend(loaded["task"], member_preds, member_probas)
        return {"modelId": model_id, "version": loaded["version"], "task": loaded["task"],
                "ensemble": True, "members": len(member_preds),
                "pred": [None if v is None else float(v) for v in combined["pred"]],
                "classLabels": (loaded.get("signature") or {}).get("classLabels"),
                "calibration": None,
                "proba": combined["proba"]}

    pred, proba = _predict_loaded(loaded, X)
    return {"modelId": model_id, "version": loaded["version"], "task": loaded["task"],
            "pred": [None if not np.isfinite(v) else float(v) for v in pred],
            # A column target's labels are the operator's own vocabulary; echo the
            # code→label mapping so a prediction is decodable without a second call.
            "classLabels": (loaded.get("signature") or {}).get("classLabels"),
            "calibration": (loaded.get("calibration") or {}).get("method") or None,
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
    config = _config_from_payload({
        **experiment, "datasetId": experiment["datasetId"],
        "datasetVersion": experiment["datasetVersion"],
        # The experiment row predates the calibration field, but the run result
        # records the method that was actually used — reproduce with that, never
        # with a default that would silently change the pipeline.
        "calibration": (original.get("calibration") or {}).get("method", "none"),
    })
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
    from .models import DATASET_SOURCES, TARGET_KINDS  # noqa: PLC0415

    return {"available": _store is not None, "config": get_ml_config().to_dict(),
            "datasetSources": list(DATASET_SOURCES), "targetKinds": list(TARGET_KINDS),
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
