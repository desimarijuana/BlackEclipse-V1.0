"""Deterministic replay of a playbook over the journal.

A playbook is a *filter*, so "did it help?" is a question about the trades it
would have allowed. Replaying on the same trades that produced the findings is
in-sample, and in-sample filters always look good. The replay therefore reports
two windows — the **fit** window the loop learned from and the **holdout** window
it did not — and acceptance reads the holdout only.

The result is a simulation over recorded trades, not a live result, and the
output says so.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .model import Playbook, Trade, parse_trades


def _parse(value: Any) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def chronological(trades: list[Trade]) -> list[Trade]:
    return sorted(trades, key=lambda t: (t.entry_time or "", t.id))


def split_trades(trades: Any, split_pct: float) -> tuple[list[Trade], list[Trade]]:
    ordered = chronological(parse_trades(trades))
    if not ordered:
        return [], []
    cut = int(len(ordered) * min(max(split_pct, 0.1), 0.95))
    cut = max(1, min(cut, len(ordered) - 1)) if len(ordered) > 1 else len(ordered)
    return ordered[:cut], ordered[cut:]


def _day(value: Optional[str]) -> Optional[str]:
    moment = _parse(value)
    return moment.date().isoformat() if moment else None


def _limit_for_risk(playbook: Playbook, trade: Trade, equity: float) -> Optional[float]:
    pct = float(playbook.limits.get("riskPerTradePct") or 0)
    if pct <= 0:
        return None
    if equity > 0:
        return equity * pct / 100.0
    notional = (trade.entry or 0.0) * (trade.quantity or 0.0)
    return notional * pct / 100.0 if notional > 0 else None


def decide(playbook: Playbook, trades: Any, *, equity: float = 0.0) -> list[dict[str, Any]]:
    """One decision per closed trade, in entry-time order."""
    trades = parse_trades(trades)
    limits = playbook.limits
    blocked_symbols = {str(s).upper() for s in limits.get("symbolBlocklist") or []}
    sessions = [str(s).strip().lower() for s in limits.get("sessionAllowlist") or []]
    suspended = {str(s) for s in limits.get("suspendedStrategies") or []}
    max_day = int(limits.get("maxTradesPerDay") or 0)
    max_streak = int(limits.get("maxConsecutiveLosses") or 0)
    max_day_loss = float(limits.get("maxDailyLossR") or 0)
    require_stop = bool(limits.get("requireStop"))
    min_rr = float(limits.get("minPlannedRR") or 0)

    decisions: list[dict[str, Any]] = []
    day_counts: dict[str, int] = {}
    day_r: dict[str, float] = {}
    losing_streak = 0

    for trade in chronological([t for t in trades if t.status == "closed"]):
        reason: Optional[str] = None
        if trade.strategy_id and trade.strategy_id in suspended:
            reason = "strategy_suspended"
        elif trade.symbol.upper() in blocked_symbols:
            reason = "symbol_blocked"
        elif sessions and trade.session and trade.session.strip().lower() not in sessions:
            reason = "session_not_allowed"
        elif require_stop and trade.stop_loss is None:
            reason = "missing_stop"
        else:
            limit = _limit_for_risk(playbook, trade, equity)
            if limit is not None and trade.risk_amount is not None and trade.risk_amount > limit:
                reason = "risk_over_limit"
            elif min_rr > 0 and trade.actual_rr is not None and trade.actual_rr < min_rr:
                reason = "planned_rr_below_min"

        day = _day(trade.exit_time) or _day(trade.entry_time)
        if reason is None and day and max_day > 0 and day_counts.get(day, 0) >= max_day:
            reason = "day_trade_cap"
        if reason is None and max_streak > 0 and losing_streak >= max_streak:
            reason = "consecutive_loss_cap"
        if reason is None and day and max_day_loss > 0 and day_r.get(day, 0.0) <= -abs(max_day_loss):
            reason = "daily_loss_cap"

        decisions.append({
            "tradeId": trade.id,
            "symbol": trade.symbol,
            "allowed": reason is None,
            "reason": reason,
            "rMultiple": trade.r_multiple,
        })
        if reason is not None:
            continue

        if day:
            day_counts[day] = day_counts.get(day, 0) + 1
        r = trade.r_multiple
        if r is not None:
            if day:
                day_r[day] = day_r.get(day, 0.0) + r
            losing_streak = losing_streak + 1 if r < 0 else 0
    return decisions


def metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = [row for row in decisions if row["allowed"]]
    blocked = [row for row in decisions if not row["allowed"]]
    with_r = [row["rMultiple"] for row in allowed if row["rMultiple"] is not None]
    blocked_with_r = [row["rMultiple"] for row in blocked if row["rMultiple"] is not None]
    wins = [r for r in with_r if r > 0]
    reasons: dict[str, int] = {}
    for row in blocked:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    n = len(with_r)
    return {
        "trades": len(decisions),
        "allowed": len(allowed),
        "blocked": len(blocked),
        "rAvailable": n,
        "netR": round(sum(with_r), 6) if n else None,
        "expectancyR": round(sum(with_r) / n, 6) if n else None,
        "winRate": round(len(wins) / n, 4) if n else None,
        "blockedR": round(sum(blocked_with_r), 6) if blocked_with_r else None,
        "blockedReasons": reasons,
        "sample": "simulated over recorded trades",
    }


def evaluate(
    playbook: Playbook,
    trades: list[Trade],
    *,
    equity: float = 0.0,
) -> dict[str, Any]:
    return metrics(decide(playbook, trades, equity=equity))


def walk_forward(
    playbook: Playbook,
    trades: list[Trade],
    *,
    split_pct: float = 0.7,
    equity: float = 0.0,
) -> dict[str, Any]:
    fit, holdout = split_trades(trades, split_pct)
    return {
        "fit": evaluate(playbook, fit, equity=equity),
        "holdout": evaluate(playbook, holdout, equity=equity),
        "splitPct": split_pct,
        "fitTrades": len(fit),
        "holdoutTrades": len(holdout),
    }


__all__ = ["chronological", "decide", "evaluate", "metrics", "split_trades", "walk_forward"]
