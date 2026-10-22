"""The Pine route — run a Pine Script on Eclipse's own bars.

A thin adapter over the same `PineRunner` the agent tool uses, so the UI and
the agent can never disagree about what a Pine script did. Operator-gated: a
Pine run spends CPU in a child process and must be bounded.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant.pine import PineError, PineRunConfig, PineRunner

router = APIRouter(tags=["quant"])


class PineRunBody(BaseModel):
    source: str
    bars: Optional[list[dict[str, Any]]] = None
    datasetId: Optional[str] = None
    version: Optional[str] = None
    symbol: str = "UNKNOWN"
    timeframe: str = "1d"
    timeoutS: float = 60.0
    maxBars: int = 20_000
    simulations: int = 300
    seed: int = 42


@router.get("/quant/venues")
async def list_venues_route(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Every strategy language Eclipse knows, and whether it can run now."""
    from ..quant.venues import list_venues

    return {"venues": list_venues()}


@router.get("/quant/pine")
async def pine_status(_: bool = Depends(require_operator)) -> dict:
    """Whether the Pine engine is installed, and why not when it is not."""
    runner = PineRunner()
    reason = runner.unavailable_reason()
    return {
        "available": reason is None,
        "reason": reason,
        "engine": str(runner.engine),
    }


@router.post("/quant/pine")
async def run_pine_route(body: PineRunBody,
                         _: bool = Depends(require_operator)) -> dict:
    runner = PineRunner()
    if not body.source.strip():
        raise HTTPException(status_code=422, detail="the Pine script is empty")
    bars = body.bars
    if not bars and body.datasetId:
        from ..quant.advanced_tools import _pine_bars_from_dataset

        store = getattr(service, "quant_store", None)
        if store is None:
            raise HTTPException(status_code=503,
                                detail="the quant store is unavailable in this runtime")
        try:
            bars = _pine_bars_from_dataset(store, body.datasetId, body.version,
                                           body.symbol if body.symbol != "UNKNOWN" else None)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not bars:
        raise HTTPException(
            status_code=422,
            detail="provide `bars` or a `datasetId` to run the script on")

    config = PineRunConfig(timeout_s=body.timeoutS, max_bars=body.maxBars,
                           symbol=body.symbol, timeframe=body.timeframe)
    try:
        result = runner.run(body.source, list(bars), config=config)
    except PineError as exc:
        raise HTTPException(status_code=400, detail={
            "code": exc.detail.get("code", exc.code),
            "message": exc.message,
            **exc.detail,
        }) from exc
    return {"status": "OK", **result.to_dict()}


@router.post("/quant/pine/report")
async def pine_report_route(body: PineRunBody,
                             _: bool = Depends(require_operator)) -> dict:
    """Grade a Pine run with Eclipse's own machinery."""
    from ..quant.edge_report import build_edge_report
    from ..quant.montecarlo import MonteCarloConfig, MonteCarloEngine
    from ..quant.pine_report import build_pine_artifact, regime_attribution

    runner = PineRunner()
    if not body.source.strip():
        raise HTTPException(status_code=422, detail="the Pine script is empty")
    bars = body.bars
    if not bars and body.datasetId:
        from ..quant.advanced_tools import _pine_bars_from_dataset

        store = getattr(service, "quant_store", None)
        if store is None:
            raise HTTPException(status_code=503,
                                detail="the quant store is unavailable in this runtime")
        try:
            bars = _pine_bars_from_dataset(store, body.datasetId, body.version,
                                           body.symbol if body.symbol != "UNKNOWN" else None)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not bars:
        raise HTTPException(
            status_code=422,
            detail="provide `bars` or a `datasetId` to run the script on")

    config = PineRunConfig(timeout_s=body.timeoutS, max_bars=body.maxBars,
                           symbol=body.symbol, timeframe=body.timeframe)
    try:
        result = runner.run(body.source, list(bars), config=config)
    except PineError as exc:
        raise HTTPException(status_code=400, detail={
            "code": exc.detail.get("code", exc.code),
            "message": exc.message,
            **exc.detail,
        }) from exc

    artifact = build_pine_artifact(result, list(bars), symbol=body.symbol,
                                   timeframe=body.timeframe).artifact
    regimes = regime_attribution(list(bars), list(result.trades or []))
    monte_carlo = None
    try:
        monte_carlo = MonteCarloEngine.from_recorded(
            trades=artifact["trades"], equity_curve=artifact["equityCurve"],
            metrics=artifact["metrics"],
            config=MonteCarloConfig(
                method="regime_block_bootstrap", simulations=body.simulations,
                seed=body.seed,
                initial_capital=artifact["configuration"]["initialCapital"]),
        ).run().to_dict()
        if regimes:
            monte_carlo["regimeAttribution"] = regimes
    except Exception as exc:  # noqa: BLE001 - the report is still worth reading
        monte_carlo = None

    report = build_edge_report(artifact, monte_carlo)
    return {
        "status": "OK",
        "verdict": report.verdict,
        "markdown": report.markdown,
        "metrics": artifact["metrics"],
        "trades": artifact["trades"],
        "regimes": regimes,
        "warnings": report.warnings,
        "diagnostics": result.diagnostics,
    }


__all__ = ["router"]
