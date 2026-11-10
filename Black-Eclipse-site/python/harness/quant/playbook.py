"""Turn a method or a tested strategy into a plain-language trading playbook.

A backtest answers "did it work in the past". A user still needs: what do I do,
when, how much, when do I stop, and what would tell me the method has broken?
This module renders those from the *actual spec* and the *actual evidence* — it
adds no rule the spec does not contain and no claim the evidence does not support.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import QuantError
from .strategy import StrategySpec, parse_strategy


def _operand(op: dict[str, Any]) -> str:
    if not isinstance(op, dict):
        return str(op)
    if op.get("ref"):
        return str(op["ref"]).replace("_", " ")
    if op.get("value") is not None:
        return str(op["value"])
    expr = op.get("expr")
    if isinstance(expr, dict):
        left = _operand(expr.get("left") or expr.get("operand") or {})
        right = _operand(expr.get("right") or {})
        return f"({left} {expr.get('op', '?')} {right})".replace("  ", " ")
    return "?"


def _conditions(node: Any) -> list[str]:
    if not isinstance(node, dict):
        return []
    if node.get("type") == "group":
        parts = []
        for child in node.get("conditions") or []:
            inner = _conditions(child)
            parts.extend(inner)
        joiner = " AND " if node.get("combine", "all") == "all" else " OR "
        return [joiner.join(parts)] if parts else []
    left = _operand(node.get("left") or {})
    right = _operand(node.get("right") or {})
    return [f"{left} {node.get('op', '?')} {right}"]


def _exit_lines(spec: StrategySpec) -> list[str]:
    lines = []
    rules = spec.rules.exit
    for side, node in (("long", rules.long), ("short", rules.short)):
        if node is not None:
            lines.append(f"Exit {side} when: " + "; ".join(_conditions(node.model_dump())))
    if rules.stop_loss is not None:
        lines.append(f"Protective stop: {rules.stop_loss.type} {rules.stop_loss.value}")
    if rules.take_profit is not None:
        lines.append(f"Take profit: {rules.take_profit.type} {rules.take_profit.value}")
    if rules.trailing_stop is not None:
        lines.append(f"Trailing stop: {rules.trailing_stop.type} {rules.trailing_stop.value}")
    if rules.time_stop_bars:
        lines.append(f"Time stop after {rules.time_stop_bars} bars")
    return lines


def build_playbook(spec: dict[str, Any], *, symbol: Optional[str] = None,
                   evidence: Optional[dict[str, Any]] = None,
                   method_family: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Render a trading playbook from a validated StrategySpec."""
    parsed = parse_strategy(spec)
    entry = []
    if parsed.rules.entry.long is not None:
        entry.append("Long entry: " + "; ".join(_conditions(parsed.rules.entry.long.model_dump())))
    if parsed.rules.entry.short is not None:
        entry.append("Short entry: " + "; ".join(_conditions(parsed.rules.entry.short.model_dump())))
    if not entry:
        raise QuantError("the strategy has no entry rule; a playbook needs one")

    sizing = parsed.position_sizing
    sizing_text = f"{sizing.type} {sizing.value}"
    if sizing.atr_indicator:
        sizing_text += f" (ATR {sizing.atr_indicator})"
    if sizing.max_fraction is not None:
        sizing_text += f", capped at {sizing.max_fraction:g}x equity"

    risk_lines = []
    r = parsed.risk
    if r.max_risk_per_trade_pct is not None:
        risk_lines.append(f"Max risk per trade: {r.max_risk_per_trade_pct}% of equity")
    if r.max_position_pct is not None:
        risk_lines.append(f"Max position: {r.max_position_pct}% of equity")
    if r.max_gross_exposure is not None:
        risk_lines.append(f"Max gross exposure: {r.max_gross_exposure}x equity")
    if r.max_daily_loss_pct is not None:
        risk_lines.append(f"Daily loss circuit-breaker: {r.max_daily_loss_pct}%")
    if r.require_stop:
        risk_lines.append("A protective stop is required before entry")
    if not r.allow_short:
        risk_lines.append("Long only")

    ex = parsed.execution
    execution = {
        "fillAt": ex.fill_at,
        "commission": ex.commission.model_dump(exclude_none=True),
        "slippage": ex.slippage.model_dump(exclude_none=True),
        "spread": ex.spread.model_dump(exclude_none=True),
        "marketImpact": ex.market_impact.model_dump(exclude_none=True),
        "borrow": ex.borrow.model_dump(exclude_none=True),
        "financing": ex.financing.model_dump(exclude_none=True),
        "margin": ex.margin.model_dump(exclude_none=True),
        "fillModel": ex.fill_model.model_dump(exclude_none=True),
    }

    method = method_family or {}
    playbook = {
        "name": parsed.name,
        "strategyId": parsed.id,
        "version": parsed.version,
        "symbol": symbol or (parsed.universe.symbols[0] if parsed.universe.symbols else None),
        "timeframe": parsed.timeframes.primary,
        "thesis": method.get("thesis"),
        "edgeSource": method.get("edge_source"),
        "entry": entry,
        "exit": _exit_lines(parsed),
        "positionSizing": sizing_text,
        "riskControls": risk_lines or ["No explicit risk limits are set; add them before trading"],
        "execution": execution,
        "whenItWorks": method.get("best_regimes") or [],
        "whenItFails": method.get("failure_modes") or method.get("worst_regimes") or [],
        "howToTrade": [
            "Wait for a CLOSED bar that satisfies the entry rule; never act on an "
            "unfinished bar.",
            "Size from the stated method and risk limits, not from conviction.",
            "Place the protective stop/target at the same time as the entry.",
            "Record the entry, the reason, the regime and the resulting fill.",
            "Review after every 20–30 trades; compare with the research result.",
        ],
        "invalidation": [
            "Out-of-sample or paper results diverge materially from research.",
            "The edge disappears after real commission/slippage/spread.",
            "The result depends on one regime, one symbol or a handful of trades.",
            "A structural change makes the method's stated edge source implausible.",
        ],
        "monitoring": [
            "Rolling Sharpe and drawdown vs the research window",
            "Trade count and hit rate vs expectation",
            "Realised costs vs the assumption",
            "Regime mix of live entries vs the research mix",
        ],
        "paperFirst": "Deploy to paper and accumulate a forward record before any live use. "
                      "Live order routing is disabled in Eclipse; a deployment is bookkeeping, "
                      "not execution.",
        "disclaimer": "Research output, not investment advice. A playbook describes a rule; "
                      "it does not promise a return.",
    }
    if evidence:
        playbook["evidence"] = evidence
        playbook["evidenceNote"] = (
            "Evidence is reported as measured; a missing metric stays missing. "
            "A positive backtest is not a guarantee of future results."
        )
    return playbook


def playbook_for_method(method_family: Any, *, symbol: str, interval: str = "1d",
                        params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    from .discovery.synthesize import build_strategy  # noqa: PLC0415

    spec = build_strategy(method_family["id"], symbol=symbol, interval=interval,
                          params=params)
    return build_playbook(spec, symbol=symbol, method_family=method_family)


__all__ = ["build_playbook", "playbook_for_method"]
