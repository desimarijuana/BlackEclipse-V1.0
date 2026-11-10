"""Governed live-strategy trial routes.

Every route is operator-gated. The broker layer remains the only execution
path; these routes create a trial, read the last closed-bar signal, submit one
order under a live mandate, read broker results, or stop the trial.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant.live import LiveStrategyService
from .quant import _http, _store

router = APIRouter(tags=["quant"])


def _live() -> LiveStrategyService:
    return LiveStrategyService(_store())


def _gateway() -> Any:
    return service.server_market_gateway()


class TrialBody(BaseModel):
    strategyId: str
    version: str
    connectionId: str
    symbols: list[str] = Field(min_length=1)
    timeframe: str = "H1"
    volume: float = 0.01
    stopLossPoints: float = 100.0
    takeProfitPoints: float = 200.0
    maxOrders: int = 5
    maxMargin: float
    ttlSeconds: int = 3600
    confirmation: str = ""
    note: str = ""


@router.post("/quant/live/trials")
async def create_trial(body: TrialBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return _live().prepare(
            strategy_id=body.strategyId, version=body.version,
            connection_id=body.connectionId, symbols=body.symbols,
            timeframe=body.timeframe, volume=body.volume,
            stop_loss_points=body.stopLossPoints,
            take_profit_points=body.takeProfitPoints,
            max_orders=body.maxOrders, max_margin=body.maxMargin,
            ttl_seconds=body.ttlSeconds, confirmation=body.confirmation,
            note=body.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/live/run-due")
async def run_due_all(_: bool = Depends(require_operator)) -> dict:
    """Scheduler hook: run every active trial on its current closed bar."""
    try:
        from ..quant.live_scheduler import run_due

        return await run_due(_live(), _gateway())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/live/trials")
async def list_trials(strategyId: Optional[str] = None, limit: int = 50,
                      _: bool = Depends(require_operator)) -> dict:
    try:
        return {"trials": _live().list(strategy_id=strategyId, limit=limit)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/live/trials/{trial_id}")
async def get_trial(trial_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"trial": _live().get(trial_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class SignalBody(BaseModel):
    symbol: Optional[str] = None


@router.post("/quant/live/trials/{trial_id}/signal")
async def trial_signal(trial_id: str, body: SignalBody,
                       _: bool = Depends(require_operator)) -> dict:
    try:
        return {"signal": await _live().signal(
            trial_id, gateway=_gateway(), symbol=body.symbol)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class RunBody(BaseModel):
    symbol: Optional[str] = None
    volume: Optional[float] = None


@router.post("/quant/live/trials/{trial_id}/run")
async def trial_run(trial_id: str, body: RunBody,
                    _: bool = Depends(require_operator)) -> dict:
    try:
        return await _live().run_once(
            trial_id, gateway=_gateway(), volume=body.volume, symbol=body.symbol)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/live/trials/{trial_id}/run-due")
async def trial_run_due(trial_id: str, body: RunBody,
                        _: bool = Depends(require_operator)) -> dict:
    """A scheduler hook. It is idempotent per closed bar via the runner key."""
    try:
        return await _live().run_once(
            trial_id, gateway=_gateway(), volume=body.volume, symbol=body.symbol)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/live/trials/{trial_id}/results")
async def trial_results(trial_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return _live().results(trial_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/live/trials/{trial_id}/stop")
async def trial_stop(trial_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"trial": _live().stop(trial_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
