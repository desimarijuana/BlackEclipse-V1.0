"""Agent-facing ML Research Lab tools.

Typed, permission-checked tools that execute the REAL deterministic pipeline. The
dataset tool fetches through the run's market gateway (the ONE data path);
training runs the same pipeline the HTTP surface uses. Handlers return a concise
text summary plus the full structured payload; failures are structured and never
fabricated.
"""

from __future__ import annotations

from typing import Any

from . import service as S
from ..stats.base import StatsError

ML_TOOLS: tuple[str, ...] = (
    "ml_list_datasets",
    "ml_list_features",
    "ml_build_dataset",
    "ml_plan_model",
    "ml_run_experiment",
    "ml_compare_models",
    "ml_search_hyperparameters",
    "ml_get_run",
    "ml_list_experiments",
    "ml_reproduce_run",
    "ml_register_model",
    "ml_create_ensemble",
    "ml_list_models",
    "ml_verify_model",
    "ml_model_drift",
    "ml_predict",
    "ml_model_capabilities",
    "ml_job_status",
    "ml_list_jobs",
    "ml_cancel_job",
)


def _error(tool: str, exc: Exception) -> tuple[str, Any]:
    code = getattr(exc, "code", "ML_ERROR")
    return (f"{tool} — error [{code}]: {exc}",
            {"status": "error", "tool": tool, "error": {"code": code, "message": str(exc)}})


def _gateway(ctx: Any) -> Any:
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


async def ml_list_datasets(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        datasets = S.list_datasets(limit=int(args.get("limit", 100)))
        return (f"{len(datasets)} dataset(s)",
                {"status": "ok", "datasets": datasets})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_list_datasets", exc)


async def ml_list_features(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .datasets import builtin_feature_catalog  # noqa: PLC0415

        builtin = builtin_feature_catalog()
        registered: list[dict[str, Any]] = []
        registry = getattr(ctx, "feature_registry", None) if ctx is not None else None
        if registry is not None:
            try:
                registered = [{"name": f"feature:{f['name']}", "source": "registry",
                               "category": f.get("category")} for f in registry.list()]
            except Exception:  # noqa: BLE001
                registered = []
        return (f"{len(builtin)} built-in feature(s); {len(registered)} registered",
                {"status": "ok", "builtin": builtin, "registered": registered})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_list_features", exc)


async def ml_build_dataset(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        source = str(args.get("source") or "market")
        if source == "records":
            if not args.get("records"):
                raise StatsError("INVALID_INPUT", "records are required for a records dataset", 422)
        elif not args.get("symbols"):
            raise StatsError("INVALID_INPUT", "symbols are required", 422)
        registry = getattr(ctx, "feature_registry", None) if ctx is not None else None
        result = await S.build_dataset_version(
            _gateway(ctx), args, name=str(args.get("name") or "dataset"),
            description=args.get("description"), owner=args.get("owner"), registry=registry)
        q = result.get("quality") or {}
        return (f"dataset {result['datasetId']}@{result['version']} built "
                f"({result.get('manifest', {}).get('rows', 0)} rows, quality "
                f"{'ok' if q.get('ok') else 'has findings'})",
                {"status": "ok", **{k: result[k] for k in ("datasetId", "version", "artifactId",
                                                            "dataHash", "quality")}})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_build_dataset", exc)


async def ml_plan_model(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Plan (never train) a model for a dataset version or an inline data profile."""
    try:
        result = S.plan_model(dict(args))
        plan = result["plan"]
        summary = (f"plan: {plan['task']} via {plan['modelFamily']}, "
                   f"walk-forward {plan['split']['nSplits']} folds"
                   + (f" — {len(plan['warnings'])} warning(s)" if plan["warnings"] else ""))
        return (summary, {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_plan_model", exc)


async def ml_run_experiment(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        if args.get("background"):
            job = await S.submit_experiment_background(args, owner=args.get("owner"))
            return (f"training submitted as job {job.get('jobId')} "
                    f"(poll ml_job_status)",
                    {"status": "ok", "background": True, "job": job})
        result = await S.execute_experiment(args, owner=args.get("owner"))
        pooled = result.get("result", {}).get("pooledMetrics", {})
        return (f"experiment {result['experimentId']} run {result['runId']} completed; "
                f"pooled metrics {pooled}",
                {"status": "ok", "experimentId": result["experimentId"], "runId": result["runId"],
                 "artifactId": result["artifactId"], "pooledMetrics": pooled,
                 "registered": result.get("registered")})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_run_experiment", exc)


async def ml_job_status(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        job = S.get_job(str(args.get("jobId") or ""))
        if job is None:
            raise StatsError("NOT_FOUND",
                             "unknown ML job (the Execution Fabric may be unavailable)", 404)
        return (f"job {job.get('jobId')}: {job.get('status')} "
                f"({int(float(job.get('progress') or 0) * 100)}%)",
                {"status": "ok", "job": job})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_job_status", exc)


async def ml_list_jobs(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        jobs = S.list_jobs(limit=int(args.get("limit", 50)))
        return (f"{len(jobs)} ML job(s)", {"status": "ok", "jobs": jobs})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_list_jobs", exc)


async def ml_cancel_job(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = await S.cancel_job(str(args.get("jobId") or ""))
        return (f"cancel requested for {args.get('jobId')}", {"status": "ok", "cancellation": result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_cancel_job", exc)


async def ml_compare_models(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Compare several families on one dataset version with the same folds."""
    try:
        result = await S.compare_models(dict(args), owner=args.get("owner"))
        c = result["comparison"]
        winner = c.get("winner") or {}
        summary = (f"compared {len(c['rows'])} family(ies) on {c.get('primaryMetric', {}).get('key', 'no metric')}: "
                   + (f"{winner.get('modelFamily')} leads" if winner else "no clear winner")
                   + (f" — {c['note']}" if c.get("note") else ""))
        return (summary, {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_compare_models", exc)


async def ml_search_hyperparameters(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Grid/random search over one family's hyperparameters on the same folds."""
    try:
        result = await S.search_hyperparameters(dict(args), owner=args.get("owner"))
        best = result.get("best") or {}
        summary = (f"{len(result['trials'])} trial(s) for {result['family']}: "
                   + (f"best {best.get('hyperparameters')} ({best.get('metric')}="
                      f"{best.get('value'):.4g})" if best else "no clear winner")
                   + f"; {result['note']}")
        return (summary, {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_search_hyperparameters", exc)


async def ml_create_ensemble(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Register an ensemble of already-trained models."""
    try:
        result = S.create_ensemble(dict(args), owner=args.get("owner"))
        metric = next(iter(result["metrics"].items()), None)
        summary = (f"ensemble {result['modelId']}@{result['version']} over "
                   f"{len(result['members'])} members"
                   + (f" — {metric[0]}={metric[1]:.4g}" if metric else ""))
        return (summary, {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_create_ensemble", exc)


async def ml_get_run(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        run = S.get_run_result(str(args.get("runId") or ""))
        if run is None:
            raise StatsError("NOT_FOUND", "unknown run", 404)
        return (f"run {run['id']}: {run['status']} ({len(run.get('folds', []))} fold(s))",
                {"status": "ok", "run": run})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_get_run", exc)


async def ml_list_experiments(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        experiments = S.list_experiments(limit=int(args.get("limit", 50)))
        return (f"{len(experiments)} experiment(s)", {"status": "ok", "experiments": experiments})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_list_experiments", exc)


async def ml_reproduce_run(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = S.reproduce_run(str(args.get("runId") or ""))
        return (f"reproduced {result['runId']}: within tolerance={result['withinTolerance']}",
                {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_reproduce_run", exc)


async def ml_register_model(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        reg = S.register_from_run(str(args.get("runId") or ""),
                                  name=str(args.get("name") or "model"),
                                  owner=args.get("owner"))
        return (f"registered model {reg['modelId']}@{reg['version']}",
                {"status": "ok", "model": reg})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_register_model", exc)


async def ml_list_models(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        models = S.list_models(limit=int(args.get("limit", 100)))
        return (f"{len(models)} model(s)", {"status": "ok", "models": models})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_list_models", exc)


async def ml_verify_model(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = S.verify_model_artifact(str(args.get("modelId") or ""), args.get("version"))
        return (f"artifact integrity for {result['modelId']}: {'ok' if result.get('ok') else 'FAILED'}",
                {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_verify_model", exc)


async def ml_predict(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        import numpy as np  # noqa: PLC0415

        X = np.asarray(args.get("features") or [], dtype=float)
        if X.ndim != 2:
            raise StatsError("INVALID_INPUT", "features must be a 2-D matrix", 422)
        # Chat names a model ("my momentum model") more often than an id.
        target = str(args.get("modelId") or args.get("modelName") or "")
        model_id = S.resolve_model_id(target)
        result = S.predict_with_model(model_id, X, args.get("version"))
        return (f"predicted {len(result['pred'])} row(s) with {result['modelId']}@{result['version']}",
                {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_predict", exc)


async def ml_model_drift(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Drift between a registered model's training data and a later dataset."""
    try:
        result = S.model_drift(str(args.get("modelId") or ""),
                               dataset_id=str(args.get("datasetId") or ""),
                               dataset_version=str(args.get("datasetVersion") or ""),
                               version=args.get("version"))
        report = result["report"]
        return (f"drift {report['verdict']} — {len(report['driftedFeatures'])} feature(s) moved",
                {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_model_drift", exc)


async def ml_model_capabilities(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        caps = S.engine_capabilities()
        available = [m["family"] for m in caps["models"] if m["available"]]
        return (f"ML engine available={caps['available']}; model families: {', '.join(available)}",
                {"status": "ok", **caps})
    except Exception as exc:  # noqa: BLE001
        return _error("ml_model_capabilities", exc)


def register_ml_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 60_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
            version="1.0.0",
        ))

    _def("ml_list_datasets", "List ML datasets and their versions.",
         ml_list_datasets, {"type": "object", "properties": {"limit": {"type": "integer"}}}, 5_000)
    _def("ml_list_features", "List built-in ML features and registered Feature Registry features.",
         ml_list_features, {"type": "object", "properties": {}}, 5_000)
    _def("ml_build_dataset", "Build and persist an immutable ML dataset version. "
         "source='market' resolves symbols through the market gateway; "
         "source='records' trains on operator-supplied rows (featureNames are the "
         "numeric columns, target.kind='column' names the label column and its task).",
         ml_build_dataset, {"type": "object", "properties": {
             "name": {"type": "string"}, "description": {"type": "string"},
             "source": {"type": "string", "enum": ["market", "records"]},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "featureNames": {"type": "array", "items": {"type": "string"}},
             "target": {"type": "object"}, "missingPolicy": {"type": "string"},
             "minCoverage": {"type": "number"}, "owner": {"type": "string"},
             "records": {"type": "array", "items": {"type": "object"}},
             "timeColumn": {"type": "string"}, "idColumn": {"type": "string"}},
             "required": ["featureNames"]}, 120_000, long_running=True)
    _def("ml_plan_model", "Plan (never train) a model recipe for a dataset version or an "
         "inline data profile: family, hyperparameters, validation design, feature selection, "
         "with the reason for each choice and any warnings. Returns a ready-to-run experiment body.",
         ml_plan_model, {"type": "object", "properties": {
             "datasetId": {"type": "string"}, "datasetVersion": {"type": "string"},
             "rows": {"type": "integer"}, "features": {"type": "integer"},
             "task": {"type": "string",
                      "enum": ["classification", "regression", "clustering", "anomaly"]},
             "classCount": {"type": "integer"},
             "preference": {"type": "string",
                            "enum": ["balanced", "interpretable", "accurate", "deep"]},
             "seed": {"type": "integer"}},
             "required": []}, 10_000)
    _def("ml_run_experiment", "Train, validate and evaluate a model on a dataset version. "
         "Set background=true to run as a durable Execution Fabric job (recommended for large work).",
         ml_run_experiment, {"type": "object", "properties": {
             "datasetId": {"type": "string"}, "datasetVersion": {"type": "string"},
             "title": {"type": "string"}, "modelFamily": {"type": "string"},
             "hyperparameters": {"type": "object"}, "selection": {"type": "object"},
             "split": {"type": "object"}, "seed": {"type": "integer"},
             "calibration": {"type": "string", "enum": ["none", "platt", "isotonic"]},
             "registerModel": {"type": "boolean"}, "background": {"type": "boolean"},
             "name": {"type": "string"}, "owner": {"type": "string"}},
             "required": ["datasetId", "datasetVersion", "modelFamily"]}, 900_000, long_running=True)
    _def("ml_compare_models", "Train several model families on ONE dataset version with the "
         "SAME split spec and seed, then report a comparison table and an honest verdict "
         "(no winner when the margin is inside fold noise; no ranking for an unmeasured metric "
         "or a task without ground truth).",
         ml_compare_models, {"type": "object", "properties": {
             "datasetId": {"type": "string"}, "datasetVersion": {"type": "string"},
             "families": {"type": "array", "items": {"type": "string"}},
             "hyperparameters": {"type": "object"}, "selection": {"type": "object"},
             "split": {"type": "object"}, "seed": {"type": "integer"},
             "scale": {"type": "boolean"}, "owner": {"type": "string"}},
             "required": ["datasetId", "datasetVersion", "families"]},
         900_000, long_running=True)
    _def("ml_search_hyperparameters", "Grid/random hyperparameter search over ONE family, "
         "every trial validated on the same folds. Returns the trials, a ranking and the best "
         "config, plus the caveat that the winner was selected on the same folds (optimistic).",
         ml_search_hyperparameters, {"type": "object", "properties": {
             "datasetId": {"type": "string"}, "datasetVersion": {"type": "string"},
             "modelFamily": {"type": "string"}, "grid": {"type": "object"},
             "maxTrials": {"type": "integer"}, "maxSeconds": {"type": "number"},
             "selection": {"type": "object"}, "split": {"type": "object"},
             "seed": {"type": "integer"}, "scale": {"type": "boolean"},
             "calibration": {"type": "string", "enum": ["none", "platt", "isotonic"]},
             "owner": {"type": "string"}},
             "required": ["datasetId", "datasetVersion", "modelFamily"]},
         900_000, long_running=True)
    _def("ml_create_ensemble", "Register an ensemble of already-trained models on the SAME "
         "dataset version: their out-of-fold predictions are aligned by row and blended "
         "(mean of probabilities, or a majority vote). Nothing is re-fitted, and members "
         "validated on different folds are refused rather than averaged.",
         ml_create_ensemble, {"type": "object", "properties": {
             "name": {"type": "string"},
             "members": {"type": "array", "items": {"type": "object"}},
             "owner": {"type": "string"}}, "required": ["members"]}, 120_000)
    _def("ml_get_run", "Fetch a training run, its folds and metrics.",
         ml_get_run, {"type": "object", "properties": {"runId": {"type": "string"}},
                      "required": ["runId"]}, 5_000)
    _def("ml_list_experiments", "List ML experiments.",
         ml_list_experiments, {"type": "object", "properties": {"limit": {"type": "integer"}}}, 5_000)
    _def("ml_reproduce_run", "Re-run an experiment from its manifest and compare metrics.",
         ml_reproduce_run, {"type": "object", "properties": {"runId": {"type": "string"}},
                            "required": ["runId"]}, 120_000, long_running=True)
    _def("ml_register_model", "Register a run's final model in the versioned registry.",
         ml_register_model, {"type": "object", "properties": {
             "runId": {"type": "string"}, "name": {"type": "string"}, "owner": {"type": "string"}},
             "required": ["runId"]}, 30_000)
    _def("ml_list_models", "List registered ML models and versions.",
         ml_list_models, {"type": "object", "properties": {"limit": {"type": "integer"}}}, 5_000)
    _def("ml_verify_model", "Verify a model artifact's SHA-256 integrity.",
         ml_verify_model, {"type": "object", "properties": {
             "modelId": {"type": "string"}, "version": {"type": "string"}},
             "required": ["modelId"]}, 10_000)
    _def("ml_predict", "Run inference with a registered model — by id OR by the model's name. "
         "Rows are feature matrices in the dataset's selected feature order.",
         ml_predict, {"type": "object", "properties": {
             "modelId": {"type": "string"}, "modelName": {"type": "string"},
             "version": {"type": "string"},
             "features": {"type": "array"}}, "required": ["features"]}, 30_000)
    _def("ml_model_drift", "Compare a registered model's training dataset with a later "
         "dataset version: per-feature PSI + KS, a verdict (stable/watch/drift), and the "
         "features that moved. Never imputes and never calls the model.",
         ml_model_drift, {"type": "object", "properties": {
             "modelId": {"type": "string"}, "version": {"type": "string"},
             "datasetId": {"type": "string"}, "datasetVersion": {"type": "string"}},
             "required": ["modelId", "datasetId", "datasetVersion"]}, 30_000)
    _def("ml_model_capabilities", "Report which ML model families are actually available.",
         ml_model_capabilities, {"type": "object", "properties": {}}, 5_000)
    _def("ml_job_status", "Get the status/progress/output of a background ML training job.",
         ml_job_status, {"type": "object", "properties": {"jobId": {"type": "string"}},
                         "required": ["jobId"]}, 10_000)
    _def("ml_list_jobs", "List background ML training jobs.",
         ml_list_jobs, {"type": "object", "properties": {"limit": {"type": "integer"}}}, 10_000)
    _def("ml_cancel_job", "Request cancellation of a running ML training job.",
         ml_cancel_job, {"type": "object", "properties": {"jobId": {"type": "string"}},
                         "required": ["jobId"]}, 15_000)
    return list(ML_TOOLS)


__all__ = ["ML_TOOLS", "register_ml_tools"]
