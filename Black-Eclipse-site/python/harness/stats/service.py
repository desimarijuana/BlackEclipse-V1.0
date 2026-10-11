"""Statistical engine service — orchestration, persistence, caching, audit.

Wraps the deterministic tools with: a computation-identity cache (a cached value
is reused only when tool+version+parameters+input hash all match), durable
analysis records and audit events, artifact storage for large results, and a
market-gateway-backed path (`execute_with_data`) so a caller can run any tool
against a live symbol without hand-assembling arrays.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

from .base import INVALID_INPUT, STATS_VERSION, StatsError, make_response
from .cache import computation_key, get_cache
from .formula import FormulaError, evaluate, parse
from .registry import get_tool, run_tool_safe

_store: Any = None


def set_stats_store(store: Any) -> None:
    global _store
    _store = store


def get_stats_store() -> Any:
    return _store


# Input keys per tool that carry series data (used both for arg-building and for
# the cache identity).
_SINGLE_VALUE_TOOLS = {
    "calculate_returns", "calculate_volatility", "calculate_drawdown",
    "calculate_stationarity", "calculate_autocorrelation", "calculate_regime",
    "build_features", "detect_outliers",
}


def _inputs_for_cache(args: dict[str, Any]) -> Any:
    # Hash only the data-bearing keys so cosmetic options don't change identity.
    return {k: v for k, v in args.items() if isinstance(v, (list, tuple)) or k in ("values", "series", "x", "y", "asset", "benchmark", "predictor", "target", "factor", "prices")}


def execute(tool: str, args: dict[str, Any], *, owner: Optional[str] = None,
            dataset_ref: Optional[dict[str, Any]] = None, use_cache: bool = True,
            persist: bool = True) -> dict[str, Any]:
    """Run a tool with caching, persistence and audit. Returns the envelope plus
    `analysisId` and `cacheHit`."""
    spec = get_tool(tool)  # raises 404 for unknown
    key = computation_key(tool, STATS_VERSION, args, _inputs_for_cache(args))
    cache = get_cache()
    started = time.perf_counter()
    try:
        envelope, cache_hit = cache.get_or_compute(
            key, lambda: run_tool_safe(tool, args), enabled=use_cache
        )
        # Never mutate the cached object: return a shallow copy so per-call
        # metadata (cacheHit, durationMs, analysisId) does not accumulate.
        envelope = {**envelope}
    except Exception as exc:  # noqa: BLE001 - never fabricate
        envelope, cache_hit = make_response(
            tool, args, status="error",
            errors=[{"code": "NUMERICAL_ERROR", "message": str(exc)}]), False
    duration_ms = int((time.perf_counter() - started) * 1000)
    envelope["cacheHit"] = cache_hit
    envelope["durationMs"] = duration_ms

    if persist and _store is not None and envelope.get("status") == "ok":
        try:
            analysis_id = _store.record_analysis(
                tool=tool, tool_version=envelope.get("toolVersion"), parameters=args,
                dataset_ref=dataset_ref, status=envelope.get("status"),
                summary=envelope.get("summary") or {}, provenance=envelope.get("provenance") or {},
                duration_ms=duration_ms, owner=owner,
            )
            envelope["analysisId"] = analysis_id
            _store.audit(action="analysis.run", subject_type="tool", subject_id=tool,
                         actor=owner, detail={"analysisId": analysis_id, "dataset": bool(dataset_ref)})
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass
    envelope["provenance"] = dict(envelope.get("provenance") or {})
    if dataset_ref:
        envelope["provenance"]["dataset"] = dataset_ref
    return envelope


def _series_to_values(series: dict[str, Any]) -> list[Optional[float]]:
    return series["values"]


def build_args_for_tool(tool: str, frame: dict[str, Any], base_args: dict[str, Any]) -> dict[str, Any]:
    """Assemble a tool's data arguments from a resolved frame.

    `frame` is either a single series (`resolve_series`) or a multi-symbol frame
    (`resolve_frame`). Options in `base_args` are preserved.
    """
    args = dict(base_args)
    if "symbols" in frame:  # multi-symbol frame
        symbols = frame["symbols"]
        rows = frame["values"]
        if tool == "calculate_cointegration":
            args["series"] = [list(r) for r in rows]
        elif tool == "calculate_correlation":
            if len(rows) == 2:
                args["x"], args["y"] = list(rows[0]), list(rows[1])
            else:
                args["series"] = [list(r) for r in rows]
                args.setdefault("labels", symbols)
        elif tool == "calculate_beta":
            if len(rows) < 2:
                raise StatsError(INVALID_INPUT, "calculate_beta needs two symbols")
            args["asset"], args["benchmark"] = list(rows[0]), list(rows[1])
        elif tool == "analyze_lead_lag":
            if len(rows) < 2:
                raise StatsError(INVALID_INPUT, "analyze_lead_lag needs two symbols")
            args["predictor"], args["target"] = list(rows[0]), list(rows[1])
        else:
            args["values"] = _series_to_values({"values": rows[0]})
    else:
        if tool in _SINGLE_VALUE_TOOLS or tool == "calculate_information_coefficient":
            args["values"] = frame["values"]
            if tool == "calculate_information_coefficient":
                args.setdefault("prices", frame["values"])
                args.pop("values", None)
        else:
            args["values"] = frame["values"]
    return args


async def execute_with_data(
    tool: str, gateway: Any, symbols: list[str], *,
    interval: str = "1d", start: Optional[str] = None, end: Optional[str] = None,
    field: str = "close", tool_args: Optional[dict[str, Any]] = None,
    owner: Optional[str] = None, use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch market data, run the tool, and return the envelope with the dataset
    provenance attached."""
    from .datasets import resolve_frame, resolve_series  # noqa: PLC0415

    if not symbols:
        raise StatsError(INVALID_INPUT, "at least one symbol is required")
    if len(symbols) == 1 and tool in _SINGLE_VALUE_TOOLS:
        frame = await resolve_series(gateway, symbols[0], interval=interval, start=start,
                                     end=end, field=field)
    elif tool == "calculate_information_coefficient":
        series = await resolve_series(gateway, symbols[0], interval=interval, start=start,
                                      end=end, field=field)
        frame = series
    else:
        frame = await resolve_frame(gateway, symbols, interval=interval, start=start,
                                    end=end, field=field)
    args = build_args_for_tool(tool, frame, tool_args or {})
    dataset_ref = {
        "symbols": symbols, "interval": interval, "field": field,
        "start": start, "end": end,
        "provenance": frame.get("provenance"),
        "observations": len(frame.get("timestamps") or []),
    }
    return execute(tool, args, owner=owner, dataset_ref=dataset_ref, use_cache=use_cache)


# ── formula helpers ──────────────────────────────────────────────────────────

def validate_formula(text: str) -> dict[str, Any]:
    try:
        parsed = parse(text)
    except FormulaError as exc:
        return {"valid": False, "code": exc.code, "message": exc.message}
    return {"valid": True, "variables": parsed.variables, "functions": parsed.functions}


def execute_formula(text: str, sample: dict[str, Any], *, persist: bool = False,
                    owner: Optional[str] = None) -> dict[str, Any]:
    try:
        values, parsed = evaluate(text, _coerce_context(sample))
    except FormulaError as exc:
        return {"status": "error", "errors": [{"code": exc.code, "message": exc.message}]}
    finite = values[np.isfinite(values)]
    result = {
        "status": "ok", "formula": text, "variables": parsed.variables,
        "functions": parsed.functions,
        "values": [None if not np.isfinite(v) else float(v) for v in values],
        "summary": {
            "observations": int(values.size), "finite": int(finite.size),
            "missingCount": int(np.isnan(values).sum()),
            "mean": float(finite.mean()) if finite.size else None,
            "std": float(finite.std(ddof=1)) if finite.size > 1 else None,
        },
    }
    if persist and _store is not None:
        _store.audit(action="formula.execute", subject_type="formula", actor=owner,
                     detail={"variables": parsed.variables})
    return result


def _coerce_context(sample: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key, value in sample.items():
        if value is None:
            continue
        arr = np.asarray(value, dtype=float)
        if arr.ndim == 1:
            context[key] = np.where(np.isfinite(arr), arr, np.nan)
    if "close" in context and "returns" not in context:
        close = context["close"]
        r = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            r[1:] = close[1:] / close[:-1] - 1.0
        context["returns"] = r
    return context


__all__ = [
    "execute", "execute_with_data", "build_args_for_tool", "validate_formula",
    "execute_formula", "set_stats_store", "get_stats_store",
]
