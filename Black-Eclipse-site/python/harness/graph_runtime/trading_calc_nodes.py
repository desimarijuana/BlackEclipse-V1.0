"""Pure trading-system primitives (Phase 9).

These nodes compute; they never contact a broker and never submit anything:

- `trading.size_by_risk` turns an equity risk budget and a stop distance into a
  volume, floored to the symbol's step so the risk cap is never exceeded.
- `trading.bracket` derives a stop and a target from an ATR multiple or an
  explicit stop distance, with a reward:risk multiple.
- `trading.spread_guard` refuses a trade when the broker's spread is wider than
  the configured cap.
- `trading.session_filter` combines the broker's own `tradeMode` (when a quote is
  wired) with an explicit UTC clock window.

Honesty rules: a missing stop is an outcome with a reason, not a zero; a
volume below the symbol minimum is refused rather than bumped up (bumping would
exceed the risk the caller asked for); and the clock window is OUR filter, not a
claim about the broker's session calendar (the adapter does not expose one).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_MAX_PRICE = 1_000_000_000


def _number(context: NodeExecContext, handle: str, config_key: str | None = None) -> float | None:
    raw = context.inputs.get(handle)
    if raw is None or raw == "":
        raw = context.config.get(config_key or handle)
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError(f"{handle} must be a number")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{handle} must be a number") from exc


def _payload(raw: Any) -> dict[str, Any]:
    """A service read envelope or a bare object."""
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def _positive(value: float | None, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} is required")
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


def exec_size_by_risk(context: NodeExecContext) -> dict[str, Any]:
    """Volume from an equity risk budget, a stop distance and contract size."""
    equity = _positive(_number(context, "equity"), "equity")
    entry = _positive(_number(context, "entry"), "entry")
    stop = _positive(_number(context, "stop"), "stop")
    risk_pct = _positive(_number(context, "riskPct") or 1.0, "riskPct")
    distance = abs(entry - stop)
    if distance < 1e-12:
        raise ValueError("entry and stop must differ; a zero stop distance has no risk")

    quote = _payload(context.inputs.get("quote"))
    contract = float(quote.get("contractSize") or context.config.get("contractSize") or 1.0)
    step = float(quote.get("volumeStep") or context.config.get("volumeStep") or 0.0)
    minimum = float(quote.get("volumeMin") or context.config.get("volumeMin") or 0.0)
    maximum = float(quote.get("volumeMax") or context.config.get("volumeMax") or 0.0)
    if contract <= 0:
        raise ValueError("contractSize must be greater than zero")

    risk_budget = equity * risk_pct / 100.0
    risk_per_unit = distance * contract
    raw_volume = risk_budget / risk_per_unit
    capped = False
    if maximum > 0 and raw_volume > maximum:
        raw_volume = maximum
        capped = True
    quantity = raw_volume
    if step > 0:
        # Floor, never round up: rounding up would spend more than the budget.
        quantity = math.floor(raw_volume / step + 1e-9) * step
    quantity = round(quantity, 8)

    if quantity <= 0:
        reason = (
            f"the {risk_budget:g} risk budget buys less than one volume step "
            f"({step:g}) at {risk_per_unit:g} risk per unit"
        )
        context.emit(f"size: no volume ({reason})")
        return {
            "quantity": 0.0,
            "riskBudget": round(risk_budget, 6),
            "riskAtStop": 0.0,
            "capped": False,
            "ok": False,
            "reason": reason,
        }
    if minimum > 0 and quantity < minimum:
        reason = (
            f"the sized volume {quantity:g} is below the symbol minimum {minimum:g}; "
            "the requested risk is smaller than one minimum lot"
        )
        context.emit(f"size: no volume ({reason})")
        return {
            "quantity": 0.0,
            "riskBudget": round(risk_budget, 6),
            "riskAtStop": 0.0,
            "capped": False,
            "ok": False,
            "reason": reason,
        }

    risk_at_stop = quantity * risk_per_unit
    context.emit(
        f"size: {quantity:g} units for {risk_budget:g} risk "
        f"({risk_at_stop:g} at the stop)"
    )
    return {
        "quantity": quantity,
        "riskBudget": round(risk_budget, 6),
        "riskAtStop": round(risk_at_stop, 6),
        "capped": capped,
        "ok": True,
        "reason": "capped at the symbol maximum volume" if capped else "",
    }


def exec_bracket(context: NodeExecContext) -> dict[str, Any]:
    """Stop and target from an ATR multiple or an explicit stop distance."""
    side = str(
        context.inputs.get("side") or context.config.get("side") or ""
    ).strip().lower()
    if side not in ("buy", "sell"):
        raise ValueError("bracket needs a side (buy or sell)")
    entry = _positive(_number(context, "entry"), "entry")
    atr = _number(context, "atr")
    atr_multiple = _positive(_number(context, "atrMultiple") or 1.5, "atrMultiple")
    stop_distance = _number(context, "stopDistance")
    reward_risk = _number(context, "rewardRisk") or 0.0

    if stop_distance is not None and stop_distance > 0:
        distance = stop_distance
        basis = "stopDistance"
    elif atr is not None and atr > 0:
        distance = atr * atr_multiple
        basis = "atr"
    else:
        reason = (
            "no risk distance: wire an ATR (broker_bars) or set a positive "
            "stop distance"
        )
        context.emit(f"bracket: none ({reason})")
        return {
            "stopLoss": None,
            "takeProfit": None,
            "riskDistance": 0.0,
            "rewardDistance": None,
            "basis": "none",
            "ok": False,
            "reason": reason,
        }

    direction = 1.0 if side == "buy" else -1.0
    stop_loss = round(entry - direction * distance, 8)
    take_profit = (
        round(entry + direction * distance * reward_risk, 8) if reward_risk > 0 else None
    )
    context.emit(
        f"bracket {side} @ {entry:g}: SL {stop_loss:g}"
        + (f", TP {take_profit:g}" if take_profit is not None else ", no target")
    )
    return {
        "stopLoss": stop_loss,
        "takeProfit": take_profit,
        "riskDistance": round(distance, 8),
        "rewardDistance": (
            round(distance * reward_risk, 8) if take_profit is not None else None
        ),
        "basis": basis,
        "ok": True,
        "reason": "",
    }


def exec_spread_guard(context: NodeExecContext) -> dict[str, Any]:
    """Allow a trade only while the broker's spread is within the cap."""
    cap = _positive(_number(context, "maxSpreadPoints") or 10.0, "maxSpreadPoints")
    quote = _payload(context.inputs.get("quote"))
    spread = context.inputs.get("spreadPoints")
    if spread is None or spread == "":
        spread = quote.get("spreadPoints")
    if spread is None or spread == "":
        return {
            "ok": False,
            "spreadPoints": None,
            "maxSpreadPoints": cap,
            "reason": (
                "the quote carries no spread; wire broker_quote (which reports it) "
                "or the spread directly"
            ),
        }
    try:
        points = float(spread)
    except (TypeError, ValueError) as exc:
        raise ValueError("spreadPoints must be a number") from exc
    allowed = points <= cap
    reason = "" if allowed else f"spread {points:g} points is above the {cap:g} cap"
    context.emit(
        f"spread {points:g} vs {cap:g}: {'ok' if allowed else 'blocked'}"
    )
    return {
        "ok": allowed,
        "spreadPoints": points,
        "maxSpreadPoints": cap,
        "reason": reason,
    }


def _minutes(text: str) -> int:
    try:
        hours, minutes = str(text).strip().split(":")
        value = int(hours) * 60 + int(minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"time window must be HH:MM, got {text!r}") from exc
    if not 0 <= value < 24 * 60:
        raise ValueError(f"time window must be within 00:00-23:59, got {text!r}")
    return value


def _parse_when(raw: Any) -> datetime:
    if raw is None or raw == "":
        return datetime.now(timezone.utc)
    if isinstance(raw, datetime):
        moment = raw
    else:
        try:
            moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"time must be an ISO datetime, got {raw!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _in_minute_window(minute: int, start: int, end: int) -> bool:
    if start == end:
        return True  # a full-day session
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end  # wraps over midnight


def session_state(
    moment: datetime,
    *,
    start: str,
    end: str,
    weekdays: str,
    trade_mode: str = "",
    side: str = "",
    sessions: list[dict[str, Any]] | None = None,
    server_offset_minutes: float = 0.0,
) -> tuple[bool, str]:
    """The pure decision behind `trading.session_filter` (exposed for tests).

    With broker `sessions`, the calendar comes from the broker (evaluated in the
    broker's server time via `server_offset_minutes`) and the configured UTC
    window is not used. Without them, the UTC window and weekday list apply.
    """
    if sessions:
        server = moment + timedelta(minutes=float(server_offset_minutes or 0))
        minute = server.hour * 60 + server.minute
        inside = False
        for item in sessions:
            if not isinstance(item, dict):
                continue
            try:
                day = int(item.get("day"))
                opens = _minutes(str(item.get("from") or ""))
                closes = _minutes(str(item.get("to") or ""))
            except (TypeError, ValueError):
                continue
            if day == server.weekday() and _in_minute_window(minute, opens, closes):
                inside = True
                break
        if not inside:
            return False, (
                f"{server.strftime('%a %H:%M')} server time is outside the "
                f"broker's {server.strftime('%A')} trade sessions"
            )
    else:
        allowed_days = {
            item.strip().lower()[:3] for item in str(weekdays or "").split(",") if item.strip()
        }
        if allowed_days and moment.strftime("%a").lower()[:3] not in allowed_days:
            return False, f"{moment.strftime('%A')} is outside the configured weekdays"
        start_minute = _minutes(start)
        end_minute = _minutes(end)
        if start_minute != end_minute:
            minute = moment.hour * 60 + moment.minute
            if not _in_minute_window(minute, start_minute, end_minute):
                return False, (
                    f"{moment.strftime('%H:%M')}Z is outside the {start}-{end}Z window"
                )

    mode = str(trade_mode or "").strip().lower()
    if mode == "disabled":
        return False, "the broker reports this symbol as disabled for trading"
    if mode == "close_only":
        return False, "the broker reports this symbol as close-only"
    if mode == "long_only" and side == "sell":
        return False, "the broker reports this symbol as long-only"
    if mode == "short_only" and side == "buy":
        return False, "the broker reports this symbol as short-only"
    if mode == "unknown":
        return False, "the broker reports an unknown trade mode; refusing to guess"
    return True, ""


def _session_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _configured_sessions(raw: Any) -> list[dict[str, Any]]:
    """An operator-supplied calendar, for brokers whose terminal reports none."""
    if raw is None or raw == "" or raw == []:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "sessionsJson must be a JSON array like "
            '[{"day": 0, "from": "09:00", "to": "17:00"}]'
        ) from exc
    if not isinstance(parsed, list):
        raise ValueError("sessionsJson must be a JSON array of session windows")
    sessions: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("each sessionsJson entry must be an object")
        try:
            day = int(item.get("day"))
            opens = str(item.get("from") or "")
            closes = str(item.get("to") or "")
            _minutes(opens)
            _minutes(closes)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "each sessionsJson entry needs day (0=Monday..6) and HH:MM from/to"
            ) from exc
        sessions.append({"day": day, "from": opens, "to": closes})
    return sessions


def _server_offset(context: NodeExecContext, moment: datetime, quote: dict[str, Any]) -> float:
    """Minutes the broker's server clock is ahead of UTC.

    A wired quote carries the broker's own server timestamp, so the offset is
    measured from it (rounded to the minute). Without one, the explicit config
    value is used — it is never inferred from the local clock.
    """
    server_ms = quote.get("serverTimeMs")
    if isinstance(server_ms, (int, float)) and not isinstance(server_ms, bool) and server_ms > 0:
        return round((float(server_ms) / 1000.0 - moment.timestamp()) / 60.0)
    return float(context.config.get("serverOffsetMinutes", 0.0) or 0.0)


def exec_session_filter(context: NodeExecContext) -> dict[str, Any]:
    """Combine the broker's trade mode and sessions with an explicit clock window."""
    quote = _payload(context.inputs.get("quote"))
    facts = _payload(context.inputs.get("symbolInfo"))
    side = str(
        context.inputs.get("side") or context.config.get("side") or ""
    ).strip().lower()
    if side and side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell when set")
    moment = _parse_when(context.inputs.get("time") or context.config.get("time"))
    trade_mode = str(facts.get("tradeMode") or quote.get("tradeMode") or "")
    broker_sessions = (
        _session_rows(facts.get("sessionDeals")) if facts.get("sessionsAvailable") else []
    )
    sessions = broker_sessions or _configured_sessions(context.config.get("sessionsJson"))
    if broker_sessions:
        basis = "brokerSession"
    elif sessions:
        basis = "configuredSessions"
    else:
        basis = "clockWindow"
    offset = _server_offset(context, moment, quote) if sessions else 0.0
    open_now, reason = session_state(
        moment,
        start=str(context.config.get("startUtc") or "00:00"),
        end=str(context.config.get("endUtc") or "00:00"),
        weekdays=str(context.config.get("weekdays") or "mon,tue,wed,thu,fri,sat,sun"),
        trade_mode=trade_mode,
        side=side,
        sessions=sessions,
        server_offset_minutes=offset,
    )
    context.emit(
        f"session {moment.strftime('%a %H:%M')}Z: "
        + ("open" if open_now else f"closed ({reason})")
        + f" [{basis}]"
    )
    return {
        "open": open_now,
        "tradeMode": trade_mode,
        "basis": basis,
        "ok": True,
        "reason": reason,
    }


def build_calc_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="trading.size_by_risk", version="1.0.0", label="Size by risk",
            category="trading",
            inputs=(
                PortDef(id="equity", name="Equity", type=PortType.NUMBER, optional=True),
                PortDef(id="entry", name="Entry price", type=PortType.NUMBER, optional=True),
                PortDef(id="stop", name="Stop price", type=PortType.NUMBER, optional=True),
                PortDef(id="quote", name="Broker quote", type=PortType.OBJECT, optional=True),
            ),
            outputs=(
                PortDef(id="quantity", name="Quantity", type=PortType.NUMBER),
                PortDef(id="riskBudget", name="Risk budget", type=PortType.NUMBER),
                PortDef(id="riskAtStop", name="Risk at stop", type=PortType.NUMBER),
                PortDef(id="capped", name="Capped at max volume", type=PortType.BOOLEAN),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("equity", "number", 100_000.0, minimum=1.0, maximum=1_000_000_000_000),
                ConfigField("entry", "number", 0.0, minimum=0.0, maximum=_MAX_PRICE),
                ConfigField("stop", "number", 0.0, minimum=0.0, maximum=_MAX_PRICE),
                ConfigField("riskPct", "number", 1.0, minimum=0.01, maximum=100.0),
                ConfigField("contractSize", "number", 1.0, minimum=0.0, maximum=1_000_000),
                ConfigField("volumeStep", "number", 0.01, minimum=0.0, maximum=1_000_000),
                ConfigField("volumeMin", "number", 0.0, minimum=0.0, maximum=1_000_000),
                ConfigField("volumeMax", "number", 0.0, minimum=0.0, maximum=1_000_000),
            ),
            capabilities=("trading.sizing",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_size_by_risk,
            metadata={
                "docs": (
                    "Volume = equity × riskPct% ÷ (|entry − stop| × contractSize), "
                    "floored to the volume step so the budget is never exceeded, and "
                    "capped at the symbol maximum. Wire broker_quote to take contract "
                    "size / step / min / max from the broker; otherwise the node's own "
                    "fields are used. A budget below one step, or a size below the "
                    "symbol minimum, is refused with a reason rather than bumped up."
                ),
            },
        ),
        NodeDef(
            type="trading.bracket", version="1.0.0", label="Bracket",
            category="trading",
            inputs=(
                PortDef(id="entry", name="Entry price", type=PortType.NUMBER, optional=True),
                PortDef(id="atr", name="ATR", type=PortType.NUMBER, optional=True),
                PortDef(id="side", name="Side", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="stopLoss", name="Stop loss", type=PortType.NUMBER),
                PortDef(id="takeProfit", name="Take profit", type=PortType.NUMBER),
                PortDef(id="riskDistance", name="Risk distance", type=PortType.NUMBER),
                PortDef(id="rewardDistance", name="Reward distance", type=PortType.NUMBER),
                PortDef(id="basis", name="Basis", type=PortType.STRING),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("side", "enum", "buy", enum=("buy", "sell")),
                ConfigField("entry", "number", 0.0, minimum=0.0, maximum=_MAX_PRICE),
                ConfigField("atrMultiple", "number", 1.5, minimum=0.01, maximum=1_000.0),
                ConfigField("stopDistance", "number", 0.0, minimum=0.0, maximum=_MAX_PRICE),
                ConfigField("rewardRisk", "number", 2.0, minimum=0.0, maximum=100.0),
            ),
            capabilities=("trading.bracket",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_bracket,
            metadata={
                "docs": (
                    "Direction-aware SL/TP. An explicit stopDistance wins; otherwise "
                    "ATR × atrMultiple (wire broker_bars' ATR). rewardRisk = 0 emits no "
                    "target. Without either input the node returns ok:false with the "
                    "reason — it never invents a stop distance."
                ),
            },
        ),
        NodeDef(
            type="trading.spread_guard", version="1.0.0", label="Spread guard",
            category="trading",
            inputs=(
                PortDef(id="quote", name="Broker quote", type=PortType.OBJECT, optional=True),
                PortDef(id="spreadPoints", name="Spread (points)", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="ok", name="Within cap", type=PortType.BOOLEAN),
                PortDef(id="spreadPoints", name="Spread (points)", type=PortType.NUMBER),
                PortDef(id="maxSpreadPoints", name="Cap (points)", type=PortType.NUMBER),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("maxSpreadPoints", "number", 10.0, minimum=0.01, maximum=100_000.0),
            ),
            capabilities=("trading.guard",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_spread_guard,
            metadata={
                "docs": (
                    "`ok` is true only while the broker's spread is at or below the "
                    "cap. A quote without a spread is not ok — the guard never treats "
                    "missing data as a tight spread."
                ),
            },
        ),
        NodeDef(
            type="trading.session_filter", version="1.0.0", label="Session filter",
            category="trading",
            inputs=(
                PortDef(id="quote", name="Broker quote", type=PortType.OBJECT, optional=True),
                PortDef(id="symbolInfo", name="Broker symbol facts", type=PortType.OBJECT, optional=True),
                PortDef(id="side", name="Side", type=PortType.STRING, optional=True),
                PortDef(id="time", name="Time (ISO, UTC)", type=PortType.DATETIME, optional=True),
            ),
            outputs=(
                PortDef(id="open", name="Open", type=PortType.BOOLEAN),
                PortDef(id="tradeMode", name="Broker trade mode", type=PortType.STRING),
                PortDef(id="basis", name="Calendar basis", type=PortType.STRING),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("startUtc", "string", "00:00", max_length=5),
                ConfigField("endUtc", "string", "00:00", max_length=5),
                ConfigField(
                    "weekdays", "string", "mon,tue,wed,thu,fri,sat,sun", max_length=40,
                ),
                ConfigField("side", "enum", "", enum=("", "buy", "sell")),
                ConfigField("serverOffsetMinutes", "number", 0.0, minimum=-1_440.0, maximum=1_440.0),
                ConfigField("sessionsJson", "string", "", max_length=4_000),
            ),
            capabilities=("trading.guard",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_session_filter,
            metadata={
                "docs": (
                    "Open only when the broker's own trade SESSIONS say so (a wired "
                    "broker_symbol carrying `sessionDeals`; evaluated in server time "
                    "using the quote's server clock, or `serverOffsetMinutes`), or by "
                    "an explicit `sessionsJson` calendar when the terminal reports "
                    "none, or — with neither — inside the configured UTC window and "
                    "weekdays. The broker's tradeMode always applies (disabled / "
                    "close_only / long_only / short_only / unknown block). `basis` "
                    "says which calendar was used (brokerSession / "
                    "configuredSessions / clockWindow). No holiday schedule is "
                    "invented: MetaTrader's Python API does not reliably expose "
                    "sessions, and an empty table falls back."
                ),
            },
        ),
    ]


__all__ = ["build_calc_nodes", "session_state"]
