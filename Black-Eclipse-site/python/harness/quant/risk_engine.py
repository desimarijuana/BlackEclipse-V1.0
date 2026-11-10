"""Hard risk checks for a live strategy.

Limits are data. Every order is checked against them before submit, and a kill
state blocks new orders when capital, drawdown, data or broker health is bad.
"""

from __future__ import annotations

import math
from typing import Any


DEFAULT_LIMITS: dict[str, Any] = {
    "maxRiskPerTradePct": 0.5,
    "maxLot": 0.10,
    "maxNotional": 20_000.0,
    "maxMargin": 2_000.0,
    "maxOpenPositions": 2,
    "maxSpreadPoints": 30.0,
    "maxDailyLossPct": 2.0,
    "maxDrawdownPct": 8.0,
    "requireStop": True,
    "maxGrossExposurePct": 100.0,
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def position_size(
    *, equity: float, risk_pct: float, stop_distance: float,
    contract_size: float = 100_000.0, lot_step: float = 0.01,
    min_lot: float = 0.01, max_lot: float = 0.10,
) -> dict[str, Any]:
    """Risk-per-trade sizing. A zero stop distance is refused, not guessed."""
    if equity <= 0:
        return {"available": False, "reason": "equity must be positive", "lots": 0.0}
    if stop_distance <= 0:
        return {"available": False, "reason": "stop distance must be positive", "lots": 0.0}
    if contract_size <= 0:
        return {"available": False, "reason": "contract size must be positive", "lots": 0.0}
    risk_cash = equity * (max(0.0, risk_pct) / 100.0)
    raw = risk_cash / (stop_distance * contract_size)
    stepped = math.floor(raw / lot_step) * lot_step
    lots = max(min_lot, min(stepped, max_lot))
    return {
        "available": True,
        "riskCash": risk_cash,
        "lots": round(lots, 8),
        "capped": stepped > max_lot,
        "belowMinimum": stepped < min_lot,
    }


def kill_state(
    *, account: dict[str, Any], limits: dict[str, Any] | None = None,
    peak_equity: float | None = None, day_start_equity: float | None = None,
    data_healthy: bool = True, broker_healthy: bool = True,
) -> dict[str, Any]:
    rules = {**DEFAULT_LIMITS, **(limits or {})}
    equity = _num(account.get("equity"))
    balance = _num(account.get("balance"), equity)
    reasons: list[str] = []
    if not data_healthy:
        reasons.append("DATA_UNHEALTHY")
    if not broker_healthy:
        reasons.append("BROKER_UNHEALTHY")
    if day_start_equity and day_start_equity > 0:
        loss_pct = (day_start_equity - equity) / day_start_equity * 100.0
        if loss_pct >= _num(rules["maxDailyLossPct"]):
            reasons.append(f"DAILY_LOSS {loss_pct:.2f}%")
    if peak_equity and peak_equity > 0:
        drawdown = (peak_equity - equity) / peak_equity * 100.0
        if drawdown >= _num(rules["maxDrawdownPct"]):
            reasons.append(f"MAX_DRAWDOWN {drawdown:.2f}%")
    if equity < balance * 0.5:
        reasons.append("EQUITY_HALVED")
    return {
        "triggered": bool(reasons),
        "reasons": reasons,
        "equity": equity,
        "balance": balance,
        "rule": "new orders are blocked while the kill state is triggered",
    }


def check_order(
    *,
    intent: dict[str, Any],
    quote: dict[str, Any],
    account: dict[str, Any],
    positions: list[dict[str, Any]] | None = None,
    limits: dict[str, Any] | None = None,
    peak_equity: float | None = None,
    day_start_equity: float | None = None,
    data_healthy: bool = True,
    broker_healthy: bool = True,
) -> dict[str, Any]:
    """Return an explained allow/refuse decision for ONE order."""
    rules = {**DEFAULT_LIMITS, **(limits or {})}
    positions = positions or []
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, *, critical: bool = True) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail,
                       "critical": critical})

    volume = _num(intent.get("volume"))
    price = _num(intent.get("price") or quote.get("ask") or quote.get("bid"))
    contract = _num(quote.get("contractSize"), 1.0)
    notional = abs(volume * price * contract)
    margin = _num(quote.get("margin"), notional / max(_num(account.get("leverage"), 1.0), 1.0))
    spread = _num(quote.get("spreadPoints"))
    stop = intent.get("stopLoss")

    add("volume", volume > 0, f"volume={volume:g}")
    add("max_lot", volume <= _num(rules["maxLot"]),
        f"volume {volume:g} vs max {rules['maxLot']:g}")
    add("max_notional", notional <= _num(rules["maxNotional"]),
        f"notional {notional:,.2f} vs max {rules['maxNotional']:,.2f}")
    add("max_margin", margin <= _num(rules["maxMargin"]),
        f"margin {margin:,.2f} vs max {rules['maxMargin']:,.2f}")
    add("max_spread", spread <= _num(rules["maxSpreadPoints"]),
        f"spread {spread:g} points vs max {rules['maxSpreadPoints']:g}")
    add("max_positions", len(positions) < int(rules["maxOpenPositions"]),
        f"{len(positions)} open vs max {rules['maxOpenPositions']}")
    if rules.get("requireStop"):
        add("required_stop", stop not in (None, 0, ""),
            "a stop-loss is required")
    else:
        add("required_stop", True, "a stop-loss is not required", critical=False)

    gross = sum(abs(_num(p.get("volume")) * _num(p.get("currentPrice")))
                for p in positions)
    equity = _num(account.get("equity"), 1.0)
    gross_pct = (gross + notional) / equity * 100.0 if equity > 0 else 999.0
    add("gross_exposure", gross_pct <= _num(rules["maxGrossExposurePct"]),
        f"gross exposure {gross_pct:.1f}% vs max {rules['maxGrossExposurePct']:g}%")

    kill = kill_state(
        account=account, limits=rules, peak_equity=peak_equity,
        day_start_equity=day_start_equity,
        data_healthy=data_healthy, broker_healthy=broker_healthy,
    )
    add("kill_state", not kill["triggered"], "; ".join(kill["reasons"]) or "clear")

    failed = [c for c in checks if c["critical"] and not c["passed"]]
    return {
        "allowed": not failed,
        "checks": checks,
        "reasons": [f"{c['check']}: {c['detail']}" for c in failed],
        "kill": kill,
        "metrics": {"volume": volume, "notional": notional, "margin": margin,
                    "spreadPoints": spread, "grossExposurePct": gross_pct},
        "limits": rules,
    }


__all__ = ["DEFAULT_LIMITS", "check_order", "kill_state", "position_size"]
