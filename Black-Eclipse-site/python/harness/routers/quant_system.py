"""System routes for the 10/10 foundation.

Data quality, lifecycle transitions, risk checks, runner state, portfolio
allocation and one health view. Every route is operator-gated.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant.capital import capital_for, check_portfolio, risk_budget_weights
from ..quant.cost_calibration import calibrate
from ..quant.data_quality import compare_series, inspect_bars, repair_bars
from ..quant.lifecycle import LifecycleService
from ..quant.model_card import build_model_card
from ..quant.live_runner import LiveRunner
from ..quant.monitor_store import MonitorStore
from ..quant.risk_engine import check_order, kill_state
from ..quant.system_health import health
from .quant import _http, _store

router = APIRouter(tags=["quant"])


class BarsBody(BaseModel):
    rows: list[dict[str, Any]]
    interval: str = "1d"
    symbol: str = ""


@router.post("/quant/system/data-quality")
async def data_quality(body: BarsBody,
                       _: bool = Depends(require_operator)) -> dict:
    try:
        return inspect_bars(body.rows, interval=body.interval, symbol=body.symbol)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/system/data-quality/repair")
async def data_repair(body: BarsBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return repair_bars(body.rows, interval=body.interval, symbol=body.symbol)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class GoldenBody(BaseModel):
    name: str
    symbol: str
    interval: str = "1d"
    rows: list[dict[str, Any]]
    request: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/system/golden")
async def freeze_golden_route(body: GoldenBody,
                              _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.golden import freeze_golden

        dataset_store = getattr(service, "dataset_store", None)
        if dataset_store is None:
            raise HTTPException(status_code=503,
                                detail="the dataset store is unavailable")
        return freeze_golden(
            dataset_store, name=body.name, symbol=body.symbol,
            interval=body.interval, rows=body.rows, request=body.request,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class FillsBody(BaseModel):
    fills: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/quant/system/costs/calibrate")
async def cost_calibration(body: FillsBody,
                           _: bool = Depends(require_operator)) -> dict:
    try:
        return calibrate(body.fills)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ParityBody(BaseModel):
    left: list[dict[str, Any]]
    right: list[dict[str, Any]]
    label: str = "broker parity"


@router.post("/quant/system/parity")
async def parity(body: ParityBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return compare_series(body.left, body.right, label=body.label)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/model-card/{strategy_id}/{version}")
async def model_card(strategy_id: str, version: str,
                     _: bool = Depends(require_operator)) -> dict:
    try:
        return build_model_card(_store(), strategy_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/lifecycle/{strategy_id}/{version}")
async def lifecycle_get(strategy_id: str, version: str,
                        _: bool = Depends(require_operator)) -> dict:
    try:
        return LifecycleService(_store()).get(strategy_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class TransitionBody(BaseModel):
    strategyId: str
    version: str
    toState: str
    actor: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


@router.post("/quant/system/lifecycle/transition")
async def lifecycle_transition(body: TransitionBody,
                               _: bool = Depends(require_operator)) -> dict:
    try:
        return LifecycleService(_store()).transition(
            body.strategyId, body.version, body.toState,
            actor=body.actor, evidence=body.evidence, note=body.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class RiskBody(BaseModel):
    intent: dict[str, Any]
    quote: dict[str, Any]
    account: dict[str, Any]
    positions: list[dict[str, Any]] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    peakEquity: Optional[float] = None
    dayStartEquity: Optional[float] = None
    dataHealthy: bool = True
    brokerHealthy: bool = True


@router.post("/quant/system/risk/check")
async def risk_check(body: RiskBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return check_order(
            intent=body.intent, quote=body.quote, account=body.account,
            positions=body.positions, limits=body.limits or None,
            peak_equity=body.peakEquity, day_start_equity=body.dayStartEquity,
            data_healthy=body.dataHealthy, broker_healthy=body.brokerHealthy,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class AllocateBody(BaseModel):
    equity: float
    strategies: list[dict[str, Any]]
    maxWeight: float = 0.40
    reservePct: float = 0.20


@router.post("/quant/system/portfolio/allocate")
async def allocate(body: AllocateBody, _: bool = Depends(require_operator)) -> dict:
    try:
        weights = risk_budget_weights(body.strategies, max_weight=body.maxWeight)
        capital = capital_for(body.equity, weights["weights"],
                              reserve_pct=body.reservePct)
        limits = check_portfolio(weights["weights"], max_weight=body.maxWeight)
        return {"weights": weights, "capital": capital, "limits": limits}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/runs/{strategy_id}")
async def runs(strategy_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"runs": LiveRunner(_store()).runs(strategy_id=strategy_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class SnapshotBody(BaseModel):
    backtestSignals: list[dict[str, Any]] = Field(default_factory=list)
    liveSignals: list[dict[str, Any]] = Field(default_factory=list)
    baseline: dict[str, Any] = Field(default_factory=dict)
    recent: dict[str, Any] = Field(default_factory=dict)
    trades: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/quant/system/monitor/{trial_id}/snapshot")
async def monitor_snapshot(trial_id: str, body: SnapshotBody,
                           _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.live import LiveStrategyService

        results = LiveStrategyService(_store()).results(trial_id)
        return MonitorStore(_store()).record(
            trial_id=trial_id,
            backtest_signals=body.backtestSignals,
            live_signals=body.liveSignals,
            baseline=body.baseline,
            recent=body.recent,
            trades=body.trades,
            broker={"account": results.get("account"),
                    "positions": results.get("positions"),
                    "orders": results.get("orders")},
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/monitor/{trial_id}")
async def monitor_list(trial_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"snapshots": MonitorStore(_store()).list(trial_id=trial_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/report/{trial_id}")
async def trial_report(trial_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.live import LiveStrategyService

        live = LiveStrategyService(_store())
        trial = live.get(trial_id)
        results = live.results(trial_id)
        runs = LiveRunner(_store()).runs(strategy_id=trial["strategyId"], limit=20)
        return {
            "trial": trial,
            "lastSignal": trial.get("lastSignal"),
            "lastResult": trial.get("lastResult"),
            "runs": runs,
            "broker": {
                "account": results.get("account"),
                "positions": results.get("positions"),
                "orders": results.get("orders"),
                "openPositions": results.get("openPositions"),
                "openPnl": results.get("openPnl"),
            },
            "note": "The broker is the source of truth.",
        }
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/system/health")
async def system_health(strategyId: Optional[str] = None,
                        version: Optional[str] = None,
                        _: bool = Depends(require_operator)) -> dict:
    """A partial health view. A check is `unknown` until its input is supplied."""
    try:
        store = _store()
        lifecycle = None
        runner = None
        if strategyId and version:
            lifecycle = LifecycleService(store).get(strategyId, version)
            rows = LiveRunner(store).runs(strategy_id=strategyId, limit=1)
            runner = rows[0] if rows else None
        broker = None
        risk = None
        try:
            from ..trade.bootstrap import get_service

            service = get_service()
            if service is not None:
                connections = service.list_connections()
                broker = connections[0] if connections else None
                if broker:
                    account = service.account(broker["id"]).get("data") or {}
                    risk = {"allowed": True,
                            "kill": kill_state(account=account),
                            "reasons": []}
        except Exception:  # noqa: BLE001 - broker health is optional
            broker = None
        return health(broker=broker, risk=risk, runner=runner,
                      lifecycle=lifecycle)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
