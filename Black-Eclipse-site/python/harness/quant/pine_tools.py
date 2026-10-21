"""The Pine agent tools.

The Pine tool lives in its own module so the advanced-tools surface keeps its
size budget, and so the Pine seam (the isolated engine, the fix loop) reads in
one place.

Two tools:

  * `run_pine_script` — run a Pine script on Eclipse's own bars, and draw the
    first plot through the ONE chart engine;
  * with `autoFix`, the same tool runs the **fix loop**: the script fails, the
    run's own model rewrites it, and the engine runs it again.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from ..tools import ToolContext
from .errors import QuantError

#: The tool names.
PINE_TOOLS: tuple[str, ...] = ("run_pine_script",)


def _pine_bars_from_dataset(store: Any, dataset_id: str, version: Optional[str],
                            symbol: Optional[str]) -> list[dict[str, Any]]:
    """Read the bars of one dataset version back out of the dataset store."""
    import gzip

    manifest = store.get_version(str(dataset_id), version)
    if not manifest:
        raise QuantError(
            f"no dataset version {dataset_id!r}"
            + (f" v{version}" if version else ""),
            detail={"code": "PINE_DATASET_NOT_FOUND"})
    path = manifest.get("artifactPath")
    if not path or not os.path.exists(path):
        raise QuantError(
            "the dataset's bars are missing from the store",
            detail={"code": "PINE_DATASET_ARTIFACT_MISSING",
                    "datasetId": dataset_id})
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    series = payload.get("series") or {}
    if symbol and symbol in series:
        return list(series[symbol])
    if symbol:
        raise QuantError(
            f"the dataset has no series for {symbol!r}",
            detail={"code": "PINE_DATASET_SYMBOL_MISSING",
                    "available": sorted(series.keys())})
    if len(series) == 1:
        return list(next(iter(series.values())))
    raise QuantError(
        "the dataset holds several series; name the one to run on",
        detail={"code": "PINE_DATASET_SYMBOL_REQUIRED",
                "available": sorted(series.keys())})


def _err(exc: Exception) -> tuple[str, Any]:
    from .errors import QuantError as _QuantError

    if isinstance(exc, _QuantError):
        return (f"ERROR - {exc.code}: {exc.message}",
                {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR - {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


async def run_pine_script(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Run a Pine Script on Eclipse's own bars."""
    try:
        from ..charts.render import ChartRenderError
        from ..charts.service import register_chart_artifact, render_spec
        from ..charts.spec import ChartSpec
        from .pine import PineRunConfig, PineRunner

        source = str(args.get("source") or "")
        if not source.strip():
            return ("ERROR - provide `source` (the Pine script).",
                    {"status": "ERROR", "error": {"code": "PINE_SOURCE_REQUIRED"}})

        bars = args.get("bars")
        if not bars:
            dataset_id = args.get("datasetId")
            if not dataset_id:
                return ("ERROR - provide `bars` (the OHLCV to run on) or `datasetId` "
                        "(a stored research dataset).",
                        {"status": "ERROR",
                         "error": {"code": "PINE_BARS_REQUIRED"}})
            store = getattr(ctx, "quant_store", None)
            if store is None:
                return ("ERROR - the quant store is unavailable in this runtime, so a "
                        "stored dataset cannot be read.",
                        {"status": "ERROR",
                         "error": {"code": "PINE_STORE_UNAVAILABLE"}})
            bars = _pine_bars_from_dataset(store, str(dataset_id), args.get("version"),
                                           args.get("symbol"))

        config = PineRunConfig(
            timeout_s=float(args.get("timeoutS") or 60.0),
            max_bars=int(args.get("maxBars") or 20_000),
            symbol=str(args.get("symbol") or "UNKNOWN"),
            timeframe=str(args.get("timeframe") or "1d"),
        )

        if args.get("autoFix"):
            from .pine_repair import repair_pine_script

            outcome = await repair_pine_script(
                source, list(bars),
                model_settings=getattr(ctx, "model_settings", None),
                config=config,
                max_attempts=int(args.get("maxFixAttempts") or 2),
                emitter=getattr(ctx, "emitter", None),
            )
            if not outcome.passed:
                return (f"The Pine script still fails ({outcome.status}): "
                        f"{outcome.message}",
                        {"status": "OK", "pineRepair": outcome.to_dict()})
            result = outcome.result
            payload: dict[str, Any] = {
                "status": "OK",
                "plots": result.plots,
                "trades": result.trades,
                "warnings": result.warnings,
                "diagnostics": result.diagnostics,
                "pineRepair": outcome.to_dict(),
                "source": outcome.source,
            }
        else:
            result = PineRunner().run(source, list(bars), config=config)
            payload = {
                "status": "OK",
                "plots": result.plots,
                "trades": result.trades,
                "warnings": result.warnings,
                "diagnostics": result.diagnostics,
            }

        if args.get("renderChart", True) and result.plots:
            name = next(iter(result.plots))
            points = (result.plots.get(name) or {}).get("points") or []
            values = [p.get("value") for p in points]
            spec = ChartSpec(
                kind="line",
                title=f"Pine · {name}",
                subtitle=f"{config.symbol} · {config.timeframe} · "
                         f"{len(result.trades)} trade(s)",
                y_label="value",
                series=[{"name": name, "data": values}],
                source="Eclipse Pine engine — computed",
            )
            try:
                rendered = render_spec(spec)
                registered = register_chart_artifact(ctx, rendered,
                                                     source_tool="pine_script")
                payload["chart"] = rendered.to_dict()
                payload["chartArtifactId"] = getattr(registered, "id", None)
            except ChartRenderError as exc:
                payload["chartError"] = {"code": exc.code, "reason": exc.reason}

        diagnostics = result.diagnostics or {}
        return (f"Pine script ran on {diagnostics.get('barCount')} bar(s): "
                f"{diagnostics.get('plotCount')} plot(s), "
                f"{diagnostics.get('tradeCount')} trade(s).",
                payload)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def register_pine_tools(registry: Any) -> list[str]:
    """Register the Pine tools on the one tool registry."""
    from ..tools import ToolDefinition

    registry.register(ToolDefinition(
        name="run_pine_script",
        description="Run a Pine Script (v5/v6) on Eclipse's own bars, in an isolated "
                    "runtime that never touches the network. Returns the script's plots "
                    "and the trades its strategy made, and draws the first plot through "
                    "the chart engine. With `autoFix`, a failing script is handed to the "
                    "run's own model to rewrite, and run again. A Pine runtime error is "
                    "reported with the script's own message; a missing engine is a named "
                    "refusal, never an empty result.",
        input_schema={"type": "object", "properties": {
            "source": {"type": "string", "description": "the Pine Script source"},
            "bars": {"type": "array", "items": {"type": "object"},
                     "description": "OHLCV bars: {time,o,h,l,c,v}"},
            "datasetId": {"type": "string",
                          "description": "a stored research dataset to run on"},
            "version": {"type": "string"},
            "symbol": {"type": "string"},
            "timeframe": {"type": "string"},
            "timeoutS": {"type": "number"},
            "maxBars": {"type": "integer"},
            "renderChart": {"type": "boolean"},
            "autoFix": {"type": "boolean",
                         "description": "when the script fails, let the run's own model "
                                        "rewrite it and run it again"},
            "maxFixAttempts": {"type": "integer"}},
            "required": ["source"]},
        handler=run_pine_script, permission="read", risk="low", timeout_ms=180_000,
        long_running=True))
    return list(PINE_TOOLS)


__all__ = ["PINE_TOOLS", "register_pine_tools", "run_pine_script"]
