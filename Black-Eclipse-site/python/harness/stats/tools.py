"""Agent-facing statistical tools.

Registers the fourteen statistical-engine tools plus the feature registry,
formula, data-driven analysis and background-job tools on the harness registry.
Each handler runs the deterministic engine and returns a concise text summary
plus the full structured payload. Failures are structured, never fabricated.
"""

from __future__ import annotations

from typing import Any, Optional

from .feature_registry import FeatureDefinition, FeatureRegistry
from .registry import TOOLS, TOOL_NAMES, run_tool_safe
from .runner import get_runner
from .service import execute, execute_with_data, execute_formula, get_stats_store, validate_formula

_CATEGORY_CAPABILITY: dict[str, str] = {
    "returns": "available", "volatility": "available", "relationships": "available",
    "risk": "available", "inference": "available", "regression": "available",
    "regime": "available", "features": "available", "anomaly": "available",
    "factor": "available",
}

STATS_TOOLS: tuple[str, ...] = (
    *TOOL_NAMES,
    "stats_capabilities",
    "run_statistical_analysis",
    "submit_statistical_analysis",
    "stats_analysis_status",
    "stats_cancel_analysis",
    "stats_list_analyses",
    "stats_get_analysis",
    "validate_formula",
    "execute_formula",
    "stats_save_feature",
    "stats_list_features",
    "stats_get_feature",
    "stats_version_feature",
    "stats_rollback_feature",
    "stats_validate_feature",
    "stats_preview_feature",
    "stats_feature_dependencies",
)


def _render(envelope: dict[str, Any]) -> str:
    status = envelope.get("status", "ok")
    tool = envelope.get("tool", "stats")
    lines = [f"{tool} — {status}"]
    summary = envelope.get("summary") or {}
    for key, value in list(summary.items())[:8]:
        if isinstance(value, float):
            lines.append(f"  {key}: {value:.6g}")
        elif isinstance(value, (int, str, bool)) or value is None:
            lines.append(f"  {key}: {value}")
    for w in envelope.get("warnings", [])[:4]:
        lines.append(f"  ! {w}")
    for e in envelope.get("errors", [])[:3]:
        lines.append(f"  ERROR {e.get('code')}: {e.get('message')}")
    return "\n".join(lines)


def _make_handler(tool_name: str):
    async def handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
        envelope = run_tool_safe(tool_name, args or {})
        return _render(envelope), envelope

    handler.__name__ = f"stats_{tool_name}"
    return handler


async def stats_capabilities(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    capability = {name: _CATEGORY_CAPABILITY[spec.category] for name, spec in TOOLS.items()}
    data = {"status": "OK", "tools": list(TOOL_NAMES), "capability": capability}
    return ("Statistical engine: all 14 tools available\n" + "\n".join(
        f"  {n}" for n in TOOL_NAMES), data)


def _gateway(ctx: Any) -> Any:
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


def _require_store():
    store = get_stats_store()
    if store is None:
        raise RuntimeError("the statistical store is unavailable in this runtime")
    return store


def _definition(args: dict[str, Any]) -> FeatureDefinition:
    pipeline = args.get("pipeline")
    return FeatureDefinition(
        expression=args.get("expression") or None,
        pipeline=list(pipeline) if pipeline else None,
        param_schema=args.get("paramSchema") or {},
        input_schema=args.get("inputSchema") or {},
        output_schema=args.get("outputSchema") or {},
        changelog=args.get("changelog"),
    )


def _sample(args: dict[str, Any]) -> Optional[dict[str, Any]]:
    sample = args.get("sample")
    return sample if isinstance(sample, dict) else None


# ── data-driven analysis + jobs ──────────────────────────────────────────────

async def run_statistical_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _require_store()
        tool = str(args.get("tool") or "")
        symbols = [str(s) for s in (args.get("symbols") or [])]
        gateway = _gateway(ctx)
        envelope = await execute_with_data(
            tool, gateway, symbols,
            interval=str(args.get("interval") or "1d"),
            start=args.get("start"), end=args.get("end"),
            field=str(args.get("field") or "close"),
            tool_args=args.get("arguments") or {},
        )
        if store is not None and envelope.get("status") == "ok":
            _maybe_artifact(store, envelope)
        await _publish_computed(ctx, envelope)
        return _render(envelope), envelope
    except Exception as exc:  # noqa: BLE001
        return _error("run_statistical_analysis", args, exc)


async def _publish_computed(ctx: Any, envelope: dict[str, Any]) -> None:
    """Publish the engine's computed metrics as a resolvable computed result.

    Without this a metric the engine computed had NO record in the transcript:
    the renderer could not resolve a reference to it, so it was shown as
    "this number has no record of where it came from" — the honest refusal for a
    number nobody can trace. The metrics are deterministic and carry their own
    provenance, so they travel the same way the sandbox's computed result does.
    """
    results = envelope.get("results")
    if not isinstance(results, dict) or not results:
        return
    outputs: dict[str, Any] = {}
    for key, value in list(results.items())[:50]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            outputs[str(key)] = value
    if not outputs:
        return
    provenance = envelope.get("provenance") or {}
    dataset = provenance.get("dataset") if isinstance(provenance, dict) else None
    label = "Stats engine"
    if isinstance(dataset, dict) and dataset.get("symbols"):
        label = f"Stats engine — {', '.join(str(s) for s in dataset['symbols'][:3])}"
    detail = "deterministic statistical engine"
    if isinstance(dataset, dict):
        detail = f"interval {dataset.get('interval') or '1d'}"
        if dataset.get("start") or dataset.get("end"):
            detail += f", {dataset.get('start') or 'start'} → {dataset.get('end') or 'now'}"
    try:
        from ..code.events import emit_code_event  # noqa: PLC0415

        await emit_code_event(ctx, "analysis.completed", {
            "status": "ok",
            "source": "stats",
            "result": {
                "outputs": outputs,
                "provenance": {"label": label, "detail": detail},
            },
        })
    except Exception:  # noqa: BLE001 - a publication must never break the tool
        return


def _maybe_artifact(store: Any, envelope: dict[str, Any]) -> None:
    """Persist an oversized result series as an artifact reference instead of
    returning it inline (keeps responses bounded)."""
    results = envelope.get("results") or {}
    for key, value in list(results.items()):
        if isinstance(value, list) and len(value) > 5000:
            ref = store.save_artifact({key: value}, analysis_id=envelope.get("analysisId"))
            results[key] = {"__artifact__": ref["id"], "length": len(value)}
            envelope.setdefault("artifactReferences", []).append(ref)


async def submit_statistical_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _require_store()
        tool = str(args.get("tool") or "")
        symbols = [str(s) for s in (args.get("symbols") or [])]
        gateway = _gateway(ctx)
        dataset_ref = {"symbols": symbols, "interval": args.get("interval") or "1d"}

        async def factory(progress):
            progress("running", 0, len(symbols) or 1)
            envelope = await execute_with_data(
                tool, gateway, symbols,
                interval=str(args.get("interval") or "1d"),
                start=args.get("start"), end=args.get("end"),
                field=str(args.get("field") or "close"),
                tool_args=args.get("arguments") or {},
            )
            progress("done", len(symbols) or 1, len(symbols) or 1)
            return envelope

        run_id = get_runner().submit("analysis", factory, message=f"{tool} {symbols}")
        data = {"status": "OK", "runId": run_id, "datasetRef": dataset_ref}
        return f"submitted analysis run {run_id} ({tool} {symbols})", data
    except Exception as exc:  # noqa: BLE001
        return _error("submit_statistical_analysis", args, exc)


async def stats_analysis_status(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    run = get_runner().get(str(args.get("runId") or ""), include_result=bool(args.get("includeResult")))
    if run is None:
        return "unknown run", {"status": "ERROR", "error": {"code": "NOT_FOUND", "message": "unknown run"}}
    return f"run {run['runId']}: {run['status']} ({run['percent']}%)", {"status": "OK", **run}


async def stats_cancel_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    ok = get_runner().cancel(str(args.get("runId") or ""))
    return (f"cancel {'requested' if ok else 'rejected'}", {"status": "OK", "cancelled": ok})


async def stats_list_analyses(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    rows = _require_store().list_analyses(tool=args.get("tool"), limit=int(args.get("limit") or 50))
    return f"{len(rows)} analyses", {"status": "OK", "analyses": rows}


async def stats_get_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    record = _require_store().get_analysis(str(args.get("analysisId") or ""))
    if record is None:
        return "unknown analysis", {"status": "ERROR", "error": {"code": "NOT_FOUND", "message": "unknown analysis"}}
    return f"analysis {record['id']}: {record['status']}", {"status": "OK", "analysis": record}


# ── formulas ─────────────────────────────────────────────────────────────────

async def validate_formula_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = validate_formula(str(args.get("expression") or ""))
    data = {"status": "OK" if result.get("valid") else "ERROR", **result}
    text = "formula valid: " + ", ".join(result.get("variables", [])) if result.get("valid") else f"invalid: {result.get('message')}"
    return text, data


async def execute_formula_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    result = execute_formula(str(args.get("expression") or ""), args.get("sample") or {})
    return (f"formula {'ok' if result.get('status') == 'ok' else 'error'}", result)


# ── feature registry ─────────────────────────────────────────────────────────

async def stats_save_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        registry = FeatureRegistry(_require_store())
        feature = registry.save(
            name=str(args.get("name") or ""), definition=_definition(args),
            description=args.get("description"), owner=args.get("owner"),
            visibility=str(args.get("visibility") or "personal"), category=args.get("category"),
            tags=list(args.get("tags") or []), feature_id=args.get("featureId"),
            bump=str(args.get("bump") or "patch"),
        )
        return f"saved feature {feature['id']} @ {feature['latestVersion']}", {"status": "OK", "feature": feature}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_save_feature", args, exc)


async def stats_list_features(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        rows = FeatureRegistry(_require_store()).list(
            owner=args.get("owner"), category=args.get("category"),
            include_archived=bool(args.get("includeArchived")))
        return f"{len(rows)} features", {"status": "OK", "features": rows}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_list_features", args, exc)


async def stats_get_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        out = FeatureRegistry(_require_store()).get(str(args.get("featureId") or ""), args.get("version"))
        return f"feature {out['feature']['id']} @ {out['version']['version']}", {"status": "OK", **out}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_get_feature", args, exc)


async def stats_version_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        registry = FeatureRegistry(_require_store())
        src = registry.get(str(args.get("featureId") or ""))["feature"]
        feature = registry.save(
            name=str(args.get("name") or src["name"]),
            definition=_definition(args) if (args.get("expression") or args.get("pipeline")) else
            FeatureDefinition(expression=registry.get(src["id"])["version"]["expression"],
                              pipeline=registry.get(src["id"])["version"]["pipeline"]),
            description=args.get("description") or src["description"], owner=args.get("owner") or src["owner"],
            visibility=str(args.get("visibility") or src["visibility"]), category=args.get("category") or src["category"],
            tags=list(args.get("tags") or src["tags"]), feature_id=src["id"],
            bump=str(args.get("part") or "patch"),
        )
        return f"feature {feature['id']} now @ {feature['latestVersion']}", {"status": "OK", "feature": feature}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_version_feature", args, exc)


async def stats_rollback_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        feature = FeatureRegistry(_require_store()).rollback(
            str(args.get("featureId") or ""), str(args.get("version") or ""))
        return f"rolled back to {feature['latestVersion']}", {"status": "OK", "feature": feature}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_rollback_feature", args, exc)


async def stats_validate_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        registry = FeatureRegistry(_require_store())
        if args.get("featureId"):
            result = registry.validate(feature_id=str(args["featureId"]), version=args.get("version"),
                                       sample=_sample(args))
        else:
            result = registry.validate(definition=_definition(args), sample=_sample(args))
        return f"validation: {result['status']}", {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_validate_feature", args, exc)


async def stats_preview_feature(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        registry = FeatureRegistry(_require_store())
        if args.get("featureId"):
            result = registry.preview(feature_id=str(args["featureId"]), version=args.get("version"),
                                      sample=_sample(args))
        else:
            result = registry.preview(definition=_definition(args), sample=_sample(args))
        return f"preview: {result['summary']['finite']} finite of {result['summary']['observations']}", {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_preview_feature", args, exc)


async def stats_feature_dependencies(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = FeatureRegistry(_require_store()).dependencies(
            str(args.get("featureId") or ""), args.get("version"))
        return f"dependencies: {result['direct']}", {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _error("stats_feature_dependencies", args, exc)


def _error(tool: str, args: dict[str, Any], exc: Exception) -> tuple[str, Any]:
    from .base import StatsError  # noqa: PLC0415

    if isinstance(exc, StatsError):
        payload = {"status": "ERROR", "error": exc.to_dict()}
        return f"ERROR — {exc.code}: {exc.message}", payload
    payload = {"status": "ERROR", "error": {"code": "INTERNAL_ERROR", "message": str(exc)}}
    return f"ERROR — {type(exc).__name__}: {exc}", payload


# ── registration ─────────────────────────────────────────────────────────────

_SCHEMA_PROP = {"type": "array", "items": {"type": "object"}}

_FEATURE_ARGS = {
    "type": "object",
    "properties": {
        "name": {"type": "string"}, "description": {"type": "string"},
        "expression": {"type": "string"}, "pipeline": {"type": "array"},
        "paramSchema": {"type": "object"}, "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"}, "changelog": {"type": "string"},
        "owner": {"type": "string"}, "visibility": {"type": "string", "enum": ["personal", "team", "public"]},
        "category": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
        "featureId": {"type": "string"}, "bump": {"type": "string", "enum": ["major", "minor", "patch"]},
        "sample": {"type": "object"},
    },
    "required": ["name"],
}


def register_stats_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 30_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
            version="1.0.0",
        ))

    for name, spec in TOOLS.items():
        _def(name, spec.description, _make_handler(name), spec.input_schema,
             120_000 if name in ("build_features", "calculate_regime") else 30_000,
             long_running=name in ("build_features",))

    _def("stats_capabilities", "Report the available statistical-engine tools and capability status.",
         stats_capabilities, {"type": "object", "properties": {}}, 5_000)
    _def("run_statistical_analysis",
         "Fetch market data for symbols, run one statistical tool, persist the analysis and return provenance.",
         run_statistical_analysis, {
             "type": "object",
             "properties": {
                 "tool": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
                 "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
                 "field": {"type": "string"}, "arguments": {"type": "object"}},
             "required": ["tool", "symbols"]}, 120_000, long_running=True)
    _def("submit_statistical_analysis",
         "Submit a data-driven statistical analysis as a background job; returns a run id.",
         submit_statistical_analysis, {
             "type": "object",
             "properties": {
                 "tool": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
                 "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
                 "field": {"type": "string"}, "arguments": {"type": "object"}},
             "required": ["tool", "symbols"]}, 15_000)
    _def("stats_analysis_status", "Get the status/result of a submitted analysis run.",
         stats_analysis_status, {"type": "object", "properties": {
             "runId": {"type": "string"}, "includeResult": {"type": "boolean"}}, "required": ["runId"]})
    _def("stats_cancel_analysis", "Cancel a queued or running analysis run.",
         stats_cancel_analysis, {"type": "object", "properties": {"runId": {"type": "string"}},
                                  "required": ["runId"]})
    _def("stats_list_analyses", "List persisted analyses.",
         stats_list_analyses, {"type": "object", "properties": {
             "tool": {"type": "string"}, "limit": {"type": "integer"}}})
    _def("stats_get_analysis", "Get a persisted analysis by id.",
         stats_get_analysis, {"type": "object", "properties": {"analysisId": {"type": "string"}},
                               "required": ["analysisId"]})
    _def("validate_formula", "Validate a safe-formula expression (syntax, functions, variables).",
         validate_formula_tool, {"type": "object", "properties": {"expression": {"type": "string"}},
                                  "required": ["expression"]}, 5_000)
    _def("execute_formula", "Execute a safe-formula expression against sample data.",
         execute_formula_tool, {"type": "object", "properties": {
             "expression": {"type": "string"}, "sample": {"type": "object"}}, "required": ["expression"]})
    _def("stats_save_feature", "Create or re-version a feature definition in the registry.",
         stats_save_feature, _FEATURE_ARGS, 15_000)
    _def("stats_list_features", "List registered features.",
         stats_list_features, {"type": "object", "properties": {
             "owner": {"type": "string"}, "category": {"type": "string"},
             "includeArchived": {"type": "boolean"}}})
    _def("stats_get_feature", "Get a feature and one of its versions.",
         stats_get_feature, {"type": "object", "properties": {
             "featureId": {"type": "string"}, "version": {"type": "string"}}, "required": ["featureId"]})
    _def("stats_version_feature", "Create a new version of an existing feature.",
         stats_version_feature, {**_FEATURE_ARGS, "properties": {
             **_FEATURE_ARGS["properties"], "part": {"type": "string", "enum": ["major", "minor", "patch"]}},
             "required": ["featureId"]}, 15_000)
    _def("stats_rollback_feature", "Roll a feature back to an earlier immutable version.",
         stats_rollback_feature, {"type": "object", "properties": {
             "featureId": {"type": "string"}, "version": {"type": "string"}},
             "required": ["featureId", "version"]})
    _def("stats_validate_feature", "Validate a feature definition (syntax, execution, coverage, PIT).",
         stats_validate_feature, {**_FEATURE_ARGS, "required": []}, 15_000)
    _def("stats_preview_feature", "Preview a feature's computed series on sample data.",
         stats_preview_feature, {**_FEATURE_ARGS, "required": []}, 15_000)
    _def("stats_feature_dependencies", "Show a feature's dependency graph.",
         stats_feature_dependencies, {"type": "object", "properties": {
             "featureId": {"type": "string"}, "version": {"type": "string"}}, "required": ["featureId"]})

    return list(STATS_TOOLS)


__all__ = ["STATS_TOOLS", "register_stats_tools"]
