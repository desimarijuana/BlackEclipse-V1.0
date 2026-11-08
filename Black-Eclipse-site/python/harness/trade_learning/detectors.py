"""Deterministic trade-mistake detectors.

A finding is a *process* observation with a field citation. It is never inferred
from profit and loss: a planned stop-out is a clean trade, and a winning trade
with no stop is still a mistake.

Every detector is a pure function of the trade (and, where it genuinely adds
evidence, the execution log). If the field a detector needs is absent the
detector reports the category as **unavailable** for that trade — it never
substitutes a zero or a guess.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any, Callable, Optional

from .model import Finding, Playbook, Trade, parse_trades

#: Which identity a category's recurrence is scoped by. A process failure is not
#: symbol-specific; a management failure usually is.
SCOPES: dict[str, str] = {
    "no_stop": "global",
    "no_plan": "global",
    "unreviewed": "global",
    "revenge_trade": "global",
    "overtraded": "global",
    "off_session": "global",
    "off_symbol": "global",
    "duplicate_entry": "global",
    "stop_widened": "symbol",
    "held_past_stop": "symbol",
    "early_exit": "symbol",
    "target_reduced": "symbol",
    "risk_over_limit": "strategy",
    "checklist_violation": "strategy",
}


def signature_for(category: str, trade: Trade) -> str:
    """The scoped recurrence key. Never contains a trade id, a price or a time."""
    scope = SCOPES.get(category, "global")
    if scope == "symbol":
        suffix = f"symbol:{(trade.symbol or 'unknown').upper()}"
    elif scope == "strategy":
        suffix = f"strategy:{trade.strategy_id or 'unknown'}"
    else:
        suffix = "global"
    raw = f"trade|{category}|{suffix}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def signature_scope(category: str, trade: Trade) -> str:
    scope = SCOPES.get(category, "global")
    if scope == "symbol":
        return f"symbol:{(trade.symbol or 'unknown').upper()}"
    if scope == "strategy":
        return f"strategy:{trade.strategy_id or 'unknown'}"
    return "global"


# ── field availability (the honest-data gate) ─────────────────────────────────

def _has(trade: Trade, *fields: str) -> bool:
    for name in fields:
        if getattr(trade, name, None) is None:
            return False
    return True


REQUIRES: dict[str, Callable[[Trade], bool]] = {
    "no_stop": lambda t: True,
    "risk_over_limit": lambda t: t.risk_amount is not None,
    "stop_widened": lambda t: True,
    "target_reduced": lambda t: True,
    "early_exit": lambda t: _has(t, "r_multiple", "mfe"),
    "held_past_stop": lambda t: _has(t, "r_multiple"),
    "overtraded": lambda t: t.exit_time is not None,
    "revenge_trade": lambda t: t.entry_time is not None,
    "no_plan": lambda t: True,
    "checklist_violation": lambda t: t.rules_checked and bool(t.checklist),
    "off_session": lambda t: t.session is not None,
    "off_symbol": lambda t: bool(t.symbol),
    "duplicate_entry": lambda t: t.entry_time is not None,
    "unreviewed": lambda t: t.exit_time is not None,
}


# ── small parsers ─────────────────────────────────────────────────────────────

def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        import json  # noqa: PLC0415 - local; detectors stay dependency-free

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_time(value: Any) -> Optional[_dt.datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _date_key(value: Optional[str]) -> Optional[str]:
    moment = _parse_time(value)
    return moment.date().isoformat() if moment else None


def _executions_for(trade_id: str, executions: Any) -> list[dict[str, Any]]:
    if not isinstance(executions, dict):
        return []
    rows = executions.get(trade_id)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


# ── the detectors ─────────────────────────────────────────────────────────────

def _f(trade: Trade, category: str, expected: str, actual: str,
       evidence: dict[str, Any], when: Optional[str] = None) -> Finding:
    return Finding(
        trade_id=trade.id,
        category=category,
        expected=expected,
        actual=actual,
        evidence=evidence,
        signature=signature_for(category, trade),
        r_multiple=trade.r_multiple,
        r_available=trade.r_multiple is not None,
        symbol=trade.symbol,
        strategy_id=trade.strategy_id,
        session=trade.session,
        occurred_at=when or trade.exit_time or trade.entry_time,
    )


def _no_stop(trade: Trade, _ctx: dict[str, Any]) -> list[Finding]:
    if trade.stop_loss is not None:
        return []
    return [_f(
        trade, "no_stop", "a stop loss protects the position",
        "the trade has no stop loss", {"stopLoss": None},
    )]


def _risk_over_limit(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    risk = trade.risk_amount
    if risk is None:
        return []
    pct = float(ctx.get("riskPct") or 1.0) / 100.0
    equity = float(ctx.get("accountEquity") or 0.0)
    if equity > 0:
        limit = equity * pct
        basis = "account equity"
    else:
        notional = (trade.entry or 0.0) * (trade.quantity or 0.0)
        limit = notional * pct
        basis = "1% of notional (no equity configured)"
    if limit <= 0 or risk <= limit:
        return []
    return [_f(
        trade, "risk_over_limit", f"risk at or below {limit:.2f} ({basis})",
        f"risked {risk:.2f}", {"riskAmount": risk, "limit": round(limit, 2), "basis": basis},
    )]


def _stop_widened(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for row in _executions_for(trade.id, ctx.get("executions")):
        if str(row.get("kind") or "") != "stop_modified":
            continue
        detail = _detail(row.get("detail"))
        before = next((_number(detail.get(key)) for key in
                       ("from", "previous", "old", "stopLossBefore") if _number(detail.get(key)) is not None), None)
        after = next((_number(detail.get(key)) for key in
                      ("to", "stopLoss", "value", "new") if _number(detail.get(key)) is not None), None)
        entry = trade.entry
        if before is None or after is None or entry is None:
            continue
        widened = (
            (trade.direction == "LONG" and after < before)
            or (trade.direction == "SHORT" and after > before)
        )
        if not widened:
            continue
        findings.append(_f(
            trade, "stop_widened", "the stop stays or moves toward the entry",
            f"stop moved {before:g} → {after:g} (risk increased)",
            {"kind": "stop_modified", "from": before, "to": after, "at": row.get("createdAt")},
            when=str(row.get("createdAt") or trade.exit_time or ""),
        ))
    return findings


def _target_reduced(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for row in _executions_for(trade.id, ctx.get("executions")):
        if str(row.get("kind") or "") != "target_modified":
            continue
        detail = _detail(row.get("detail"))
        before = next((_number(detail.get(key)) for key in
                       ("from", "previous", "old", "takeProfitBefore") if _number(detail.get(key)) is not None), None)
        after = next((_number(detail.get(key)) for key in
                      ("to", "takeProfit", "value", "new") if _number(detail.get(key)) is not None), None)
        entry = trade.entry
        if before is None or after is None or entry is None:
            continue
        reduced = (
            (trade.direction == "LONG" and after < before)
            or (trade.direction == "SHORT" and after > before)
        )
        if not reduced:
            continue
        findings.append(_f(
            trade, "target_reduced", "the target is not pulled closer before the exit",
            f"target moved {before:g} → {after:g} (closer to entry)",
            {"kind": "target_modified", "from": before, "to": after, "at": row.get("createdAt")},
            when=str(row.get("createdAt") or trade.exit_time or ""),
        ))
    return findings


def _early_exit(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    threshold = float(ctx.get("minRForEarlyExit") or 1.0)
    if trade.r_multiple is None or trade.mfe is None:
        return []
    if trade.r_multiple >= threshold or trade.mfe < threshold:
        return []
    return [_f(
        trade, "early_exit", f"hold to at least {threshold:g}R when {threshold:g}R was reached",
        f"exited at {trade.r_multiple:g}R after {trade.mfe:g}R favourable",
        {"rMultiple": trade.r_multiple, "mfe": trade.mfe, "threshold": threshold},
    )]


def _held_past_stop(trade: Trade, _ctx: dict[str, Any]) -> list[Finding]:
    if trade.stop_loss is None or trade.r_multiple is None:
        return []
    if trade.r_multiple >= -1.05:
        return []
    return [_f(
        trade, "held_past_stop", "a stopped position exits near -1R",
        f"closed at {trade.r_multiple:g}R with a stop set at {trade.stop_loss:g}",
        {"rMultiple": trade.r_multiple, "stopLoss": trade.stop_loss, "mae": trade.mae},
    )]


def _no_plan(trade: Trade, _ctx: dict[str, Any]) -> list[Finding]:
    if trade.strategy_id or trade.setup_id:
        return []
    return [_f(
        trade, "no_plan", "the trade belongs to a strategy or setup",
        "no strategy and no setup are assigned", {"strategyId": None, "setupId": None},
    )]


def _checklist_violation(trade: Trade, _ctx: dict[str, Any]) -> list[Finding]:
    if not trade.rules_checked or not trade.checklist:
        return []
    required = {
        str(rule.get("id")) for rule in trade.rules
        if str(rule.get("category") or "").lower() in ("risk", "entry")
    }
    broken = sorted(rule_id for rule_id in required if trade.checklist.get(rule_id) is False)
    if not broken:
        return []
    return [_f(
        trade, "checklist_violation", "every risk/entry rule is checked",
        "unchecked rules: " + ", ".join(broken[:8]),
        {"ruleIds": broken[:20]},
    )]


def _off_session(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    allowed = list(ctx.get("sessionAllowlist") or [])
    if not allowed or not trade.session:
        return []
    if trade.session.strip().lower() in {item.strip().lower() for item in allowed}:
        return []
    return [_f(
        trade, "off_session", "trade only in allowed sessions: " + ", ".join(allowed[:8]),
        f"traded in {trade.session}", {"session": trade.session, "allowed": allowed},
    )]


def _off_symbol(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    blocked = {item.upper() for item in (ctx.get("symbolBlocklist") or [])}
    if not trade.symbol or trade.symbol.upper() not in blocked:
        return []
    return [_f(
        trade, "off_symbol", f"{trade.symbol} is not in the plan",
        f"{trade.symbol} is on the blocklist", {"symbol": trade.symbol},
    )]


def _overtraded(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    limit = int(ctx.get("maxTradesPerDay") or 0)
    if limit <= 0:
        return []
    position = int(ctx["_day_index"].get(trade.id, 0))
    if position <= limit:
        return []
    return [_f(
        trade, "overtraded", f"at most {limit} closed trades per day",
        f"trade #{position} that day", {"position": position, "limit": limit},
    )]


def _revenge_trade(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    if (trade.emotion or "").strip().lower() == "revenge":
        return [_f(
            trade, "revenge_trade", "a trade is planned, not a reaction to a loss",
            "the trade is tagged Revenge", {"emotion": trade.emotion},
        )]
    window = int(ctx.get("revengeWindowMin") or 30)
    entered = _parse_time(trade.entry_time)
    if entered is None:
        return []
    # Only a loss that had ALREADY CLOSED before this entry can have caused it;
    # a later loss must never be read backwards into this trade.
    prior = [
        (lost_at, trade_id)
        for lost_at, trade_id in ctx["_losses_by_symbol"].get((trade.symbol or "").upper(), [])
        if lost_at is not None and lost_at <= entered
    ]
    if not prior:
        return []
    lost_at, previous_id = max(prior, key=lambda item: item[0])
    minutes = (entered - lost_at).total_seconds() / 60
    if minutes > window:
        return []
    return [_f(
        trade, "revenge_trade", f"wait more than {window} minutes after a loss",
        f"entered {minutes:.0f} min after a loss on {trade.symbol}",
        {"withinMinutes": round(minutes), "window": window, "previousTradeId": previous_id},
    )]


def _duplicate_entry(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    window = int(ctx.get("duplicateWindowMin") or 60)
    key = (trade.symbol or "").upper(), trade.direction
    entered = _parse_time(trade.entry_time)
    if entered is None:
        return []
    prior = [
        (when, trade_id)
        for when, trade_id in ctx["_entries_by_key"].get(key, [])
        if when is not None and when < entered and trade_id != trade.id
    ]
    if not prior:
        return []
    when, first_id = max(prior, key=lambda item: item[0])
    minutes = (entered - when).total_seconds() / 60
    if minutes > window:
        return []
    return [_f(
        trade, "duplicate_entry", f"one position per {key[0]} {key[1]} within {window} min",
        f"a second {key[1]} entry {minutes:.0f} min after the first",
        {"gapMinutes": round(minutes), "firstTradeId": first_id, "window": window},
    )]


def _unreviewed(trade: Trade, ctx: dict[str, Any]) -> list[Finding]:
    grace = int(ctx.get("reviewGraceHours") or 24)
    closed = _parse_time(trade.exit_time)
    now = ctx.get("_now")
    if closed is None or now is None:
        return []
    if trade.grade or trade.notes:
        return []
    if (now - closed).total_seconds() < grace * 3600:
        return []
    return [_f(
        trade, "unreviewed", "a closed trade gets a grade or a note",
        f"closed {(now - closed).total_seconds() / 3600:.0f} h ago with no review",
        {"hoursSinceExit": round((now - closed).total_seconds() / 3600)},
    )]


DETECTORS: dict[str, Callable[[Trade, dict[str, Any]], list[Finding]]] = {
    "no_stop": _no_stop,
    "risk_over_limit": _risk_over_limit,
    "stop_widened": _stop_widened,
    "target_reduced": _target_reduced,
    "early_exit": _early_exit,
    "held_past_stop": _held_past_stop,
    "no_plan": _no_plan,
    "checklist_violation": _checklist_violation,
    "off_session": _off_session,
    "off_symbol": _off_symbol,
    "overtraded": _overtraded,
    "revenge_trade": _revenge_trade,
    "duplicate_entry": _duplicate_entry,
    "unreviewed": _unreviewed,
}


# ── the review ────────────────────────────────────────────────────────────────

def review(
    trades: Any,
    *,
    executions: Any = None,
    playbook: Any = None,
    detectors: Optional[list[str]] = None,
    config: Optional[dict[str, Any]] = None,
    now: Optional[_dt.datetime] = None,
) -> dict[str, Any]:
    """Run the enabled detectors over closed trades.

    Returns `findings`, the clean-trade list (with the reason each was clean),
    and per-category coverage. Coverage is what later lets the loop say
    `insufficient_evidence` instead of inventing a pattern.
    """
    trades = parse_trades(trades)
    playbook = Playbook.from_dict(playbook) if isinstance(playbook, dict) else playbook
    settings = dict(config or {})
    limits = (playbook.limits if playbook else {})
    closed = [t for t in trades if t.status == "closed" or settings.get("includeOpen")]
    enabled = [name for name in (detectors or list(DETECTORS)) if name in DETECTORS]

    # Daily position, precomputed once so each detector stays a pure read.
    day_index: dict[str, int] = {}
    per_day: dict[str, int] = {}
    for trade in sorted(closed, key=lambda t: (t.exit_time or "", t.id)):
        key = _date_key(trade.exit_time)
        if not key:
            continue
        per_day[key] = per_day.get(key, 0) + 1
        day_index[trade.id] = per_day[key]

    # Indexes the path-dependent detectors read. They are built in chronological
    # order so a detector can never see a later event and call it a cause.
    losses: dict[str, list[tuple[Optional[_dt.datetime], str]]] = {}
    entries: dict[tuple[str, str], list[tuple[Optional[_dt.datetime], str]]] = {}
    for trade in sorted(closed, key=lambda t: (t.entry_time or "", t.id)):
        key = (trade.symbol or "").upper(), trade.direction
        entries.setdefault(key, []).append((_parse_time(trade.entry_time), trade.id))
        if (trade.r_multiple or 0) < 0 and trade.exit_time:
            losses.setdefault(key[0], []).append((_parse_time(trade.exit_time), trade.id))

    ctx: dict[str, Any] = {
        **settings,
        "executions": executions or {},
        "riskPct": settings.get("riskPct", 1.0),
        "accountEquity": settings.get("accountEquity", 0.0),
        "maxTradesPerDay": limits.get("maxTradesPerDay") or settings.get("maxTradesPerDay", 3),
        "sessionAllowlist": limits.get("sessionAllowlist") or settings.get("sessionAllowlist") or [],
        "symbolBlocklist": limits.get("symbolBlocklist") or settings.get("symbolBlocklist") or [],
        "_day_index": day_index,
        "_losses_by_symbol": losses,
        "_entries_by_key": entries,
        "_now": now or _dt.datetime.now(_dt.timezone.utc),
    }

    findings: list[Finding] = []
    coverage: dict[str, dict[str, Any]] = {}
    for name in enabled:
        requires = REQUIRES.get(name, lambda _t: True)
        available = sum(1 for trade in closed if requires(trade))
        coverage[name] = {
            "available": available,
            "total": len(closed),
            "fraction": round(available / len(closed), 4) if closed else 0.0,
        }

    flagged: set[str] = set()
    for trade in closed:
        for name in enabled:
            requires = REQUIRES.get(name, lambda _t: True)
            if not requires(trade):
                continue
            for finding in DETECTORS[name](trade, ctx):
                findings.append(finding)
                flagged.add(trade.id)

    clean: list[dict[str, Any]] = []
    for trade in closed:
        clean.append({
            "tradeId": trade.id,
            "symbol": trade.symbol,
            "clean": trade.id not in flagged,
            "rMultiple": trade.r_multiple,
        })

    findings.sort(key=lambda f: (f.occurred_at or "", f.trade_id, f.category))
    by_category: dict[str, int] = {}
    for finding in findings:
        by_category[finding.category] = by_category.get(finding.category, 0) + 1

    return {
        "findings": [finding.to_dict() for finding in findings],
        "reviewed": clean,
        "coverage": coverage,
        "summary": {
            "trades": len(closed),
            "findings": len(findings),
            "cleanTrades": sum(1 for row in clean if row["clean"]),
            "byCategory": by_category,
            "detectors": enabled,
            "detectorVersion": "1",
        },
    }


__all__ = [
    "DETECTORS",
    "REQUIRES",
    "SCOPES",
    "review",
    "signature_for",
    "signature_scope",
]
