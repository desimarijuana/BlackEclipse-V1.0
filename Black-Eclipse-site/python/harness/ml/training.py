"""Training pipeline for the ML Research Lab.

The pipeline enforces the correctness order mandated by the brief:

  1. resolve dataset + label arrays,
  2. build chronological folds (purge/embargo),
  3. for EACH fold: fit preprocessing on the training rows only,
     fit feature selection on the training rows only, train the estimator,
     predict the test rows,
  4. pool the out-of-fold predictions for aggregate metrics,
  5. fit one FINAL model on the union of fold training rows and evaluate it on
     the held-out rows (never used for any earlier decision),
  6. return the model artifact state, fold results, metrics and lineage.

A failure anywhere raises; a partial run is never reported as completed.
"""

from __future__ import annotations

import platform
import time
from typing import Any, Callable, Optional

import numpy as np

from . import adapters
from . import metrics as M
from .features import apply_selection, fit_selection
from .models import ML_ENGINE_VERSION, ExperimentConfig, MLError
from .splits import assert_no_leakage, build_splits, coverage_summary, fold_assignments
from ..stats.base import INVALID_INPUT, INSUFFICIENT_DATA

CANCELLED = "CANCELLED"


class _Standardizer:
    """Fit-on-train standardisation; a missing/zero variance column is left as-is."""

    def __init__(self) -> None:
        self.mean: Optional[np.ndarray] = None
        self.std: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray) -> "_Standardizer":
        self.mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0, ddof=1)
        std = np.where((std > 0) & np.isfinite(std), std, 1.0)
        self.std = std
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.mean is None or self.std is None:
            raise MLError(INVALID_INPUT, "standardizer is not fitted")
        return (X - self.mean) / self.std


class _IdentityScaler:
    """Used when `config.scale` is false: an explicit, documented no-op."""

    def fit(self, X: np.ndarray) -> "_IdentityScaler":
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return X


def _finite_rows(X: np.ndarray, y: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Rows of ``idx`` with a finite label and finite features."""
    if idx.size == 0:
        return idx
    ok = np.isfinite(y[idx])
    if X.shape[1] > 0:
        ok &= np.isfinite(X[idx]).all(axis=1)
    return idx[ok]


def _concat_folds(folds: list[dict[str, Any]], key: str) -> np.ndarray:
    parts = [np.asarray(f[key], dtype=int) for f in folds if len(f[key])]
    return np.concatenate(parts) if parts else np.array([], dtype=int)


def run_experiment(
    arrays: dict[str, Any],
    manifest: dict[str, Any],
    config: ExperimentConfig,
    *,
    train_final_model: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
    max_folds: Optional[int] = None,
    deadline: Optional[float] = None,
) -> dict[str, Any]:
    """Execute one experiment. Returns a fully-populated, JSON-serialisable result.

    ``should_cancel`` is polled between folds (and before the final fit) so a
    long job stops promptly without corrupting state; a cancelled run raises
    ``MLError("CANCELLED")`` and is never reported as completed. ``on_progress``
    receives ``(fraction, message)``. ``deadline`` is a ``time.monotonic()``
    instant past which the run stops with a budget error.
    """
    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise MLError(CANCELLED, "the experiment was cancelled", 409)
        if deadline is not None and time.monotonic() > deadline:
            raise MLError("TIME_BUDGET_EXCEEDED",
                          "the experiment exceeded its wall-clock budget", 408)

    def _progress(fraction: float, message: str) -> None:
        if on_progress is not None:
            on_progress(fraction, message)

    X = np.asarray(arrays["X"], dtype=float)
    y = np.asarray(arrays["y"], dtype=float)
    label_start = np.asarray(arrays["labelStart"], dtype=int)
    label_end = np.asarray(arrays["labelEnd"], dtype=int)
    feature_names = list(manifest.get("featureNames") or arrays.get("featureNames") or [])
    task = manifest.get("target", {}).get("task") or arrays.get("targetTask")
    if task is None:
        raise MLError(INVALID_INPUT, "the dataset does not declare a task")
    if config.model_family not in adapters.NATIVE_MODEL_FAMILIES and \
            config.model_family not in adapters.OPTIONAL_MODEL_FAMILIES:
        raise MLError(INVALID_INPUT, f"unknown model family {config.model_family!r}")

    if task not in ("classification", "regression", "ranking"):
        return _run_unsupervised(
            X=X, feature_names=feature_names, config=config, task=task, manifest=manifest,
            label_start=label_start, label_end=label_end, train_final_model=train_final_model,
            should_cancel=should_cancel, on_progress=on_progress, max_folds=max_folds,
            deadline=deadline,
        )

    folds = build_splits(config.split, label_start, label_end)
    assert_no_leakage(folds, label_start, label_end)
    if max_folds is not None and len(folds) > max_folds:
        raise MLError(INVALID_INPUT,
                      f"the split design produced {len(folds)} folds (limit {max_folds})")

    fold_results: list[dict[str, Any]] = []
    pooled_y: list[float] = []
    pooled_pred: list[float] = []
    pooled_proba: list[Optional[list[float]]] = []
    pooled_row: list[int] = []
    is_classification = task == "classification"

    for fold in folds:
        _check_cancel()
        _progress((fold["index"] / max(1, len(folds))) * 0.9,
                  f"fold {fold['index'] + 1}/{len(folds)}")
        train = _finite_rows(X, y, np.asarray(fold["trainIdx"], dtype=int))
        test = _finite_rows(X, y, np.asarray(fold["testIdx"], dtype=int))
        if train.size < 4 or test.size < 1:
            fold_results.append({**{k: fold[k] for k in (
                "index", "nTrain", "nTest", "nPurged", "nEmbargoed", "trainStart",
                "trainEnd", "testStart", "testEnd")},
                "status": "skipped", "reason": "insufficient finite rows",
                "metrics": {}})
            continue

        scaler = _Standardizer().fit(X[train])
        Xtr = scaler.transform(X[train])
        Xte = scaler.transform(X[test])
        selection = fit_selection(Xtr, y[train], task, feature_names,
                                  method=config.selection.get("method", "none"),
                                  top_k=int(config.selection.get("topK", 0) or 0),
                                  threshold=float(config.selection.get("threshold", 0.0) or 0.0))
        sel = selection["selected"]
        Xtr_s = apply_selection(Xtr, sel)
        Xte_s = apply_selection(Xte, sel)

        model = adapters.build_model(config.model_family, task, config.hyperparameters, config.seed)
        model.fit(Xtr_s, y[train])
        pred = model.predict(Xte_s)
        proba = model.predict_proba(Xte_s) if is_classification else None

        if is_classification:
            n_classes = int(manifest.get("target", {}).get("nClasses")
                            or (max(int(np.max(y[train])), int(np.max(y[test]))) + 1))
            block = M.evaluate_classification(y[test], pred, proba, n_classes)
        else:
            block = M.evaluate_regression(y[test], pred)

        fold_results.append({
            "index": fold["index"], "status": "ok",
            "nTrain": int(train.size), "nTest": int(test.size),
            "nPurged": fold["nPurged"], "nEmbargoed": fold["nEmbargoed"],
            "trainStart": fold["trainStart"], "trainEnd": fold["trainEnd"],
            "testStart": fold["testStart"], "testEnd": fold["testEnd"],
            "selectedFeatures": [feature_names[i] for i in sel],
            "metrics": block,
        })
        pooled_y.extend(y[test].tolist())
        pooled_pred.extend(np.asarray(pred, dtype=float).tolist())
        pooled_row.extend(int(i) for i in test)
        if proba is not None:
            pooled_proba.extend(np.asarray(proba, dtype=float).tolist())
        else:
            pooled_proba.extend([None] * int(test.size))

    if not any(f.get("status") == "ok" for f in fold_results):
        raise MLError(INSUFFICIENT_DATA, "no fold produced a usable training/test split", 422)

    py = np.asarray(pooled_y, dtype=float)
    pp = np.asarray(pooled_pred, dtype=float)
    proba_arr = None
    if is_classification:
        if all(p is not None for p in pooled_proba) and pooled_proba:
            proba_arr = np.asarray(pooled_proba, dtype=float)
        n_classes = int(manifest.get("target", {}).get("nClasses")
                        or (np.nanmax(py) + 1) if py.size else 2)
        pooled_metrics = M.evaluate_classification(py, pp, proba_arr, int(n_classes))
    else:
        pooled_metrics = M.evaluate_regression(py, pp)

    # Calibrate on the pooled OUT-OF-FOLD probabilities: each row was predicted by
    # a model that never saw it, so the holdout below is only used to report the
    # effect, never to fit the curve.
    calibration_state = None
    if is_classification and config.calibration not in ("none", None, "") \
            and proba_arr is not None and proba_arr.ndim == 2 and proba_arr.shape[1] == 2:
        from .calibration import fit_calibration  # noqa: PLC0415

        calibration_state = fit_calibration(proba_arr[:, 1], py, method=config.calibration)

    per_fold_metrics = [f["metrics"] for f in fold_results if f.get("status") == "ok"]
    aggregate = _aggregate(task, per_fold_metrics, pooled_metrics)

    result: dict[str, Any] = {
        "engineVersion": ML_ENGINE_VERSION,
        "task": task,
        "modelFamily": config.model_family,
        "hyperparameters": dict(config.hyperparameters),
        "seed": config.seed,
        "folds": fold_results,
        "splitSummary": coverage_summary(folds, X.shape[0]),
        "splitAssignments": fold_assignments(folds, X.shape[0]),
        "pooledMetrics": pooled_metrics,
        "foldMetricsMean": aggregate["mean"],
        "foldMetricsStd": aggregate["std"],
        "oos": {
            "y": pooled_y,
            "pred": [None if not np.isfinite(v) else float(v) for v in pooled_pred],
            "proba": pooled_proba,
            "rowIndex": pooled_row,
        },
        "dependencyVersions": {"numpy": np.__version__, "python": platform.python_version()},
        # A `column` target's class labels travel with the run so a registered
        # model can decode its numeric predictions back to the operator's labels.
        "classLabels": manifest.get("target", {}).get("classLabels"),
    }

    if train_final_model:
        _check_cancel()
        _progress(0.95, "fitting final model")
        final = _fit_final(X, y, feature_names, config, task, manifest,
                           calibration=calibration_state)
        result["finalModel"] = final["modelState"]
        result["finalFeatureImportance"] = final["importance"]
        result["finalSelectedFeatures"] = final["selectedFeatures"]
        result["finalEvaluation"] = final["evaluation"]
        if final.get("calibratedEvaluation") is not None:
            result["finalCalibratedEvaluation"] = final["calibratedEvaluation"]
        result["finalPermutationImportance"] = final.get("permutationImportance")

    result["calibration"] = calibration_state
    return result


def _fit_final(X: np.ndarray, y: np.ndarray, feature_names: list[str], config: ExperimentConfig,
               task: str, manifest: dict[str, Any],
               calibration: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fit the production model on all rows not reserved as the final holdout.

    We use the union of fold TRAIN rows as the final training set so the final
    model never sees any held-out observation. When no folds exist (defensive),
    fall back to the full finite dataset.
    """
    label_start = np.asarray(manifest.get("_labelStart", []), dtype=int)
    finite_all = np.where(np.isfinite(y) & np.isfinite(X).all(axis=1))[0]
    if finite_all.size < 8:
        raise MLError(INSUFFICIENT_DATA, "not enough finite rows to fit a final model", 422)
    # chronological 80/20 holdout by row order for the final evaluation
    split_at = int(finite_all.size * 0.8)
    train_rows = finite_all[:split_at]
    holdout_rows = finite_all[split_at:]

    scaler = _Standardizer().fit(X[train_rows])
    selection = fit_selection(scaler.transform(X[train_rows]), y[train_rows], task, feature_names,
                              method=config.selection.get("method", "none"),
                              top_k=int(config.selection.get("topK", 0) or 0),
                              threshold=float(config.selection.get("threshold", 0.0) or 0.0))
    sel = selection["selected"]
    model = adapters.build_model(config.model_family, task, config.hyperparameters, config.seed)
    model.fit(apply_selection(scaler.transform(X[train_rows]), sel), y[train_rows])

    holdout_pred = model.predict(apply_selection(scaler.transform(X[holdout_rows]), sel))
    calibrated_evaluation = None
    if task == "classification":
        proba = model.predict_proba(apply_selection(scaler.transform(X[holdout_rows]), sel))
        n_classes = int(manifest.get("target", {}).get("nClasses")
                        or (adaptive_max(y) + 1))
        evaluation = M.evaluate_classification(y[holdout_rows], holdout_pred, proba, n_classes)
        if calibration and proba is not None and np.asarray(proba).ndim == 2 \
                and np.asarray(proba).shape[1] == 2:
            from .calibration import apply_calibration  # noqa: PLC0415

            p1 = apply_calibration(calibration, np.asarray(proba, dtype=float)[:, 1])
            calibrated = np.column_stack([1.0 - p1, p1])
            calibrated_evaluation = M.evaluate_classification(
                y[holdout_rows], holdout_pred, calibrated, n_classes)
            calibrated_evaluation["calibration"] = calibration.get("method")
    else:
        evaluation = M.evaluate_regression(y[holdout_rows], holdout_pred)

    imp = model.feature_importances()
    state = model.to_dict()
    state["preprocessing"] = {"mean": scaler.mean.tolist(), "std": scaler.std.tolist()}
    state["selected"] = [int(i) for i in sel]
    state["featureNames"] = feature_names
    if calibration:
        # Travels with the artifact so `predict_proba` returns calibrated scores.
        state["calibration"] = calibration

    # Model-agnostic explanation on the holdout: works for the families that expose
    # no split-based importance (linear, k-means centroids, torch MLP).
    from .importance import permutation_importance  # noqa: PLC0415

    holdout_matrix = apply_selection(scaler.transform(X[holdout_rows]), sel)
    perm = permutation_importance(
        model.predict, holdout_matrix, y[holdout_rows],
        task=task, seed=config.seed, n_repeats=5,
        feature_names=[feature_names[i] for i in sel])
    return {
        "modelState": state,
        "importance": None if imp is None else {feature_names[sel[i]]: float(imp[i])
                                                for i in range(len(sel))},
        "permutationImportance": perm,
        "selectedFeatures": [feature_names[i] for i in sel],
        "evaluation": evaluation,
        "calibratedEvaluation": calibrated_evaluation,
    }


def adaptive_max(y: np.ndarray) -> int:
    return int(np.nanmax(y)) if y.size else 0


# ── unsupervised path ────────────────────────────────────────────────────────


def _finite_feature_rows(X: np.ndarray, idx: np.ndarray) -> np.ndarray:
    if idx.size == 0 or X.shape[1] == 0:
        return idx
    return idx[np.isfinite(X[idx]).all(axis=1)]


def _run_unsupervised(
    *,
    X: np.ndarray,
    feature_names: list[str],
    config: ExperimentConfig,
    task: str,
    manifest: dict[str, Any],
    label_start: np.ndarray,
    label_end: np.ndarray,
    train_final_model: bool,
    should_cancel: Optional[Callable[[], bool]],
    on_progress: Optional[Callable[[float, str], None]],
    max_folds: Optional[int],
    deadline: Optional[float],
) -> dict[str, Any]:
    """Clustering / anomaly detection over the feature matrix.

    There is no label, so nothing here may report a supervised metric. The SAME
    temporal folds and the same leakage assertion are used, and every evaluation
    is out-of-sample: the model is fitted on the fold's training rows only and
    scored on its test rows. Metrics that are mathematically undefined (e.g. a
    silhouette when a test fold has one cluster) are ``None``, never a stand-in.
    """
    if task not in ("clustering", "anomaly"):
        raise MLError(INVALID_INPUT, f"unsupported unsupervised task {task!r}")
    if config.selection.get("method", "none") != "none":
        raise MLError(INVALID_INPUT,
                      "feature selection needs a label; use selection.method='none' "
                      "for an unsupervised task")

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise MLError(CANCELLED, "the experiment was cancelled", 409)
        if deadline is not None and time.monotonic() > deadline:
            raise MLError("TIME_BUDGET_EXCEEDED",
                          "the experiment exceeded its wall-clock budget", 408)

    def _progress(fraction: float, message: str) -> None:
        if on_progress is not None:
            on_progress(fraction, message)

    contamination = float(config.hyperparameters.get("contamination", 0.05))

    def _evaluate(rows: np.ndarray, model: Any, scaler: _Standardizer) -> dict[str, Any]:
        Xe = scaler.transform(X[rows])
        pred = model.predict(Xe)
        if task == "clustering":
            return M.evaluate_clustering(Xe, pred, centers=model.centers_)
        return M.evaluate_anomaly(model.score(Xe), pred, contamination=contamination)

    folds = build_splits(config.split, label_start, label_end)
    assert_no_leakage(folds, label_start, label_end)
    if max_folds is not None and len(folds) > max_folds:
        raise MLError(INVALID_INPUT,
                      f"the split design produced {len(folds)} folds (limit {max_folds})")

    fold_results: list[dict[str, Any]] = []
    pooled_rows: list[np.ndarray] = []
    pooled_pred: list[float] = []
    pooled_score: list[float] = []
    pooled_row: list[int] = []

    for fold in folds:
        _check_cancel()
        _progress((fold["index"] / max(1, len(folds))) * 0.9,
                  f"fold {fold['index'] + 1}/{len(folds)}")
        train = _finite_feature_rows(X, np.asarray(fold["trainIdx"], dtype=int))
        test = _finite_feature_rows(X, np.asarray(fold["testIdx"], dtype=int))
        if train.size < 4 or test.size < 1:
            fold_results.append({**{k: fold[k] for k in (
                "index", "nTrain", "nTest", "nPurged", "nEmbargoed", "trainStart",
                "trainEnd", "testStart", "testEnd")},
                "status": "skipped", "reason": "insufficient finite rows", "metrics": {}})
            continue

        scaler = (_Standardizer() if config.scale else _IdentityScaler()).fit(X[train])
        model = adapters.build_model(config.model_family, task, config.hyperparameters, config.seed)
        model.fit(scaler.transform(X[train]), np.zeros(train.size, dtype=float))
        Xte = scaler.transform(X[test])
        block = _evaluate(test, model, scaler)
        fold_results.append({
            "index": fold["index"], "status": "ok",
            "nTrain": int(train.size), "nTest": int(test.size),
            "nPurged": fold["nPurged"], "nEmbargoed": fold["nEmbargoed"],
            "trainStart": fold["trainStart"], "trainEnd": fold["trainEnd"],
            "testStart": fold["testStart"], "testEnd": fold["testEnd"],
            "selectedFeatures": list(feature_names),
            "metrics": block,
        })
        pooled_rows.append(Xte)
        pooled_pred.extend(np.asarray(model.predict(Xte), dtype=float).tolist())
        if task == "anomaly":
            pooled_score.extend(np.asarray(model.score(Xte), dtype=float).tolist())
        pooled_row.extend(int(i) for i in test)

    if not any(f.get("status") == "ok" for f in fold_results):
        raise MLError(INSUFFICIENT_DATA, "no fold produced a usable training/test split", 422)

    X_pooled = np.vstack(pooled_rows)
    if task == "clustering":
        pooled_metrics = M.evaluate_clustering(X_pooled, np.asarray(pooled_pred, dtype=float))
    else:
        pooled_metrics = M.evaluate_anomaly(np.asarray(pooled_score, dtype=float),
                                            np.asarray(pooled_pred, dtype=float),
                                            contamination=contamination)
    per_fold_metrics = [f["metrics"] for f in fold_results if f.get("status") == "ok"]
    aggregate = _aggregate(task, per_fold_metrics, pooled_metrics)

    result: dict[str, Any] = {
        "engineVersion": ML_ENGINE_VERSION,
        "task": task,
        "modelFamily": config.model_family,
        "hyperparameters": dict(config.hyperparameters),
        "seed": config.seed,
        "folds": fold_results,
        "splitSummary": coverage_summary(folds, X.shape[0]),
        "splitAssignments": fold_assignments(folds, X.shape[0]),
        "pooledMetrics": pooled_metrics,
        "foldMetricsMean": aggregate["mean"],
        "foldMetricsStd": aggregate["std"],
        "oos": {"y": [], "pred": [None if not np.isfinite(v) else float(v)
                                  for v in np.asarray(pooled_pred, dtype=float)],
                "proba": [None] * len(pooled_pred), "rowIndex": pooled_row},
        "dependencyVersions": {"numpy": np.__version__, "python": platform.python_version()},
        "classLabels": None,
    }

    if train_final_model:
        _check_cancel()
        _progress(0.95, "fitting final model")
        finite_all = _finite_feature_rows(X, np.arange(X.shape[0], dtype=int))
        if finite_all.size < 8:
            raise MLError(INSUFFICIENT_DATA, "not enough finite rows to fit a final model", 422)
        split_at = int(finite_all.size * 0.8)
        train_rows, holdout_rows = finite_all[:split_at], finite_all[split_at:]
        final_scaler = (_Standardizer() if config.scale else _IdentityScaler()).fit(X[train_rows])
        final_model = adapters.build_model(config.model_family, task,
                                           config.hyperparameters, config.seed)
        final_model.fit(final_scaler.transform(X[train_rows]),
                        np.zeros(train_rows.size, dtype=float))
        evaluation = _evaluate(holdout_rows, final_model, final_scaler)
        state = final_model.to_dict()
        state["preprocessing"] = (
            {"mean": final_scaler.mean.tolist(), "std": final_scaler.std.tolist()}
            if getattr(final_scaler, "mean", None) is not None else None)
        state["selected"] = list(range(X.shape[1]))
        state["featureNames"] = list(feature_names)
        result["finalModel"] = state
        result["finalFeatureImportance"] = None
        result["finalSelectedFeatures"] = list(feature_names)
        result["finalEvaluation"] = evaluation

    return result


def _aggregate(task: str, per_fold: list[dict[str, Any]], pooled: dict[str, Any]) -> dict[str, Any]:
    keys = M.metric_keys(task)
    mean: dict[str, Any] = {}
    std: dict[str, Any] = {}
    for k in keys:
        vals = [f.get(k) for f in per_fold if isinstance(f.get(k), (int, float))]
        mean[k] = float(np.mean(vals)) if vals else None
        std[k] = float(np.std(vals, ddof=1)) if len(vals) > 1 else None
    return {"mean": mean, "std": std, "pooled": pooled}


__all__ = ["run_experiment", "_Standardizer", "_IdentityScaler"]
