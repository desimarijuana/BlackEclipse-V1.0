"""Agent-facing intelligence tools.

Six read-only tools. They exist so bot mode and the Eclipse Agent can run the
same evidence pipeline — the automation dispatcher gives a bot the interactive
agent's surface, so nothing extra is needed to schedule a scan.

The text output always states what could NOT be measured. A model that only
reads the text must not be able to mistake "no filing found" for "nothing
happened", so `missing` is rendered explicitly.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .contracts import SIGNAL_IDS

MAX_TICKERS = 8

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_NUM = {"type": "number"}


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _owner(ctx: ToolContext) -> str:
    return str(getattr(ctx, "user_id", None) or "local")


def _tickers(args: dict[str, Any]) -> list[str]:
    raw = args.get("tickers")
    if isinstance(raw, str):
        raw = [part for part in raw.replace(",", " ").split() if part]
    if not isinstance(raw, list):
        return []
    return [str(item or "").strip().upper() for item in raw if str(item or "").strip()]


async def intel_scan(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    owner = _owner(ctx)
    tickers = _tickers(args)
    if not tickers:
        tickers = service.store.list_watch(owner)
        if not tickers:
            return (
                "No tickers given and the watchlist is empty. Pass `tickers` or add "
                "names with `intel_watch`.",
                {"status": "UNAVAILABLE", "reason": "no tickers"},
            )
    if len(tickers) > MAX_TICKERS:
        return (
            f"At most {MAX_TICKERS} tickers per scan (got {len(tickers)}). "
            "Split the scan so each call finishes inside its budget.",
            {"status": "ERROR", "error": "too many tickers"},
        )
    prices = args.get("prices") if isinstance(args.get("prices"), dict) else {}
    result = await service.scan(
        owner, tickers,
        as_of=args.get("as_of") or None,
        window_days=int(args.get("window_days") or 90),
        max_entities=MAX_TICKERS,
        max_filings=int(args.get("max_filings") or 8),
        deadline_seconds=float(args.get("deadline_seconds") or 20.0),
        price_context={str(k).upper(): v for k, v in prices.items() if isinstance(v, dict)},
    )
    return _render_scan(result), {"status": "OK" if not result.get("partial") else "PARTIAL", **result}


def _render_scan(result: dict[str, Any]) -> str:
    lines = [
        f"Intelligence scan — {result.get('asOf')} · {result.get('windowDays')}d window · "
        f"{result.get('scanned')}/{len(result.get('entities') or [])} entities read "
        f"in {result.get('elapsedMs')}ms"
    ]
    cards = result.get("cards") or []
    if cards:
        lines.append("")
        for index, card in enumerate(cards, 1):
            lines.append(
                f"{index}. {card['entity']} — {card['direction']} · priority "
                f"{card['priority']:.2f} ({card['conviction']}, {card['horizonDays']}d horizon)"
            )
            lines.append(f"   {card['thesis']}")
            for signal in card.get("signals") or []:
                lines.append(
                    f"   · {signal['signal']} {signal['score']:.2f} [{signal['source']}]: {signal['why']}"
                )
            lines.append(f"   Invalidation: {card['invalidation']}")
    else:
        lines.append("")
        lines.append("No card fired. Quiet is a result: no signal passed its gate.")

    problems: list[str] = []
    for entity in result.get("entities") or []:
        if entity.get("status") != "ok":
            problems.append(f"{entity['entity']}: {entity.get('reason') or entity.get('status')}")
            continue
        for signal, reason in (entity.get("missing") or {}).items():
            problems.append(f"{entity['entity']} {signal}: {reason}")
    if problems:
        lines.append("")
        lines.append("Could not be measured (UNAVAILABLE, not zero):")
        lines.extend(f"  - {item}" for item in problems)
    if result.get("skipped"):
        lines.append("")
        lines.append(
            "Skipped for budget (partial scan): " + ", ".join(result["skipped"])
            + ". Re-run them in a second call."
        )
    lines.append("")
    lines.append(result.get("note") or "")
    return "\n".join(line for line in lines if line is not None)


async def intel_entity(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    ticker = str(args.get("ticker") or "").strip().upper()
    if not ticker:
        return ("ticker is required.", {"status": "ERROR", "error": "ticker required"})
    data = service.entity(_owner(ctx), ticker)
    observations = data.get("observations") or []
    if not observations:
        return (
            f"No stored observations for {ticker}. Run `intel_scan` on it first — "
            "an empty series is not evidence of calm.",
            {"status": "UNAVAILABLE", "reason": "no observations", **data},
        )
    lines = [f"{ticker} — latest observation per signal:"]
    for row in observations:
        lines.append(
            f"  · {row['signal']} = {row['value']:g} {row['unit']} "
            f"(as of {row['asOf']}, confidence {row['confidence']:.2f}, source {row['source']})"
        )
        lines.append(f"      {row['method']}")
        if row.get("note"):
            lines.append(f"      note: {row['note']}")
    lines.append("")
    lines.append("Series history is available per signal with `intel_series`.")
    return "\n".join(lines), {"status": "OK", **data}


async def intel_series(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    ticker = str(args.get("ticker") or "").strip().upper()
    signal = str(args.get("signal") or "").strip()
    if not ticker:
        return ("ticker is required.", {"status": "ERROR", "error": "ticker required"})
    limit = int(args.get("limit") or 90)
    if signal:
        series = service.store.series(_owner(ctx), ticker, signal, limit=limit)
    else:
        series = []
        for signal_id in SIGNAL_IDS:
            series.extend(service.store.series(_owner(ctx), ticker, signal_id, limit=limit))
        series.sort(key=lambda row: str(row.get("asOf") or ""))
    if not series:
        return (
            f"No stored series for {ticker}" + (f" / {signal}" if signal else "")
            + ". Scan it first; nothing is inferred from an empty series.",
            {"status": "UNAVAILABLE", "reason": "no series", "entity": ticker, "signal": signal},
        )
    lines = [f"{ticker} {signal or '(all signals)'} — {len(series)} point(s)"]
    for row in series[-30:]:
        lines.append(f"  {row['asOf']}  {row['value']:>14g} {row.get('unit') or ''}")
    return "\n".join(lines), {"status": "OK", "entity": ticker, "signal": signal, "series": series}


async def intel_cards(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    cards = service.cards(_owner(ctx), limit=int(args.get("limit") or 10))
    if not cards:
        return (
            "No stored cards yet. `intel_scan` produces them; each one is a snapshot "
            "kept for later review.",
            {"status": "UNAVAILABLE", "reason": "no cards", "cards": []},
        )
    lines = [f"{len(cards)} card(s), highest priority first:"]
    for card in cards:
        lines.append(
            f"· {card['entity']} {card['direction']} {card['priority']:.2f} "
            f"({card['conviction']}, {card['horizonDays']}d, as of {card.get('asOf')})"
        )
        lines.append(f"    {card['thesis']}")
    return "\n".join(lines), {"status": "OK", "cards": cards}


async def intel_watch(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    owner = _owner(ctx)
    action = str(args.get("action") or "list").strip().lower()
    tickers = _tickers(args)
    if action == "add":
        if not tickers:
            return ("action=add needs `tickers`.", {"status": "ERROR", "error": "no tickers"})
        added = service.store.add_watch(owner, tickers)
        watch = service.store.list_watch(owner)
        return (
            f"Watching {len(watch)} name(s): {', '.join(watch)}.",
            {"status": "OK", "added": added, "watchlist": watch},
        )
    if action == "remove":
        if not tickers:
            return ("action=remove needs `tickers`.", {"status": "ERROR", "error": "no tickers"})
        removed = service.store.remove_watch(owner, tickers)
        watch = service.store.list_watch(owner)
        return (
            f"Removed {removed} name(s). Watching {len(watch)}: {', '.join(watch) or '(empty)'}.",
            {"status": "OK", "removed": removed, "watchlist": watch},
        )
    if action not in ("list", "add", "remove"):
        return ("action must be list, add or remove.", {"status": "ERROR", "error": "bad action"})
    watch = service.store.list_watch(owner)
    return (
        f"Watchlist ({len(watch)}): {', '.join(watch) or '(empty)'}.",
        {"status": "OK", "watchlist": watch},
    )


async def intel_catalog(
    args: dict[str, Any], ctx: ToolContext, service: Any,
) -> tuple[str, Any]:
    catalog = service.catalog()
    lines = ["Intelligence signal catalogue:"]
    for signal in catalog["signals"]:
        lines.append(f"· {signal['id']} — {signal['label']}")
        lines.append(f"    question: {signal['question']}")
        lines.append(f"    source: {signal['source']} · unit: {signal['unit']}")
        lines.append(f"    limit: {signal['limit']}")
    lines.append("")
    lines.append("Sources: " + ", ".join(
        f"{source['name']} (auth: {source['auth']})" for source in catalog["sources"]
    ))
    lines.append(catalog["scoring"]["note"])
    return "\n".join(lines), {"status": "OK", **catalog}


_SCHEMAS: dict[str, Any] = {
    "intel_scan": _obj({
        "tickers": {
            "type": "array", "items": _STR,
            "description": f"Ticker symbols to scan (max {MAX_TICKERS}). Empty = the stored watchlist.",
        },
        "window_days": {**_INT, "description": "Lookback window in days (default 90)."},
        "as_of": {**_STR, "description": "Evaluate as of YYYY-MM-DD (default today)."},
        "max_filings": {**_INT, "description": "Form 4 documents to read per entity (default 8)."},
        "deadline_seconds": {**_NUM, "description": "Time budget for the whole scan (default 20)."},
        "prices": {
            "type": "object",
            "description": (
                "Optional price context per ticker, e.g. "
                '{"AAPL": {"change5d": 0.01, "change30d": -0.12}}. Enables the '
                "signal-vs-price divergence read; omit it and the card says so."
            ),
            "additionalProperties": {"type": "object"},
        },
    }),
    "intel_entity": _obj({
        "ticker": {**_STR, "description": "Ticker symbol."},
    }, ["ticker"]),
    "intel_series": _obj({
        "ticker": {**_STR, "description": "Ticker symbol."},
        "signal": {**_STR, "description": "Signal id, e.g. insider_conviction. Empty = all."},
        "limit": {**_INT, "description": "Maximum points to return."},
    }, ["ticker"]),
    "intel_cards": _obj({
        "limit": {**_INT, "description": "How many stored cards to return."},
    }),
    "intel_watch": _obj({
        "action": {**_STR, "enum": ["list", "add", "remove"], "description": "Watchlist operation."},
        "tickers": {"type": "array", "items": _STR, "description": "Tickers to add or remove."},
    }, ["action"]),
    "intel_catalog": _obj({}),
}

_TOOLS: list[tuple[str, str, Any, int]] = [
    ("intel_scan",
     "Scan tickers for alternative-intelligence signals (SEC insider conviction, activist 13D "
     "stakes, filing intensity, public-attention velocity) and return ranked research cards. "
     "Every measurement is deterministic and sourced; unmeasurable signals are reported "
     "UNAVAILABLE, never assumed to be zero. Priority is a triage order, not expected return.",
     intel_scan, 30_000),
    ("intel_entity",
     "Show the latest stored observation for each intelligence signal on one ticker, with the "
     "method, source, confidence and caveat behind it.",
     intel_entity, 15_000),
    ("intel_series",
     "Show the stored time series for one ticker (optionally one signal) from previous scans.",
     intel_series, 15_000),
    ("intel_cards",
     "List the stored intelligence cards, highest priority first. Cards are immutable snapshots "
     "kept for later review and grading.",
     intel_cards, 15_000),
    ("intel_watch",
     "List, add to, or remove from the intelligence watchlist that `intel_scan` uses by default.",
     intel_watch, 15_000),
    ("intel_catalog",
     "Describe every intelligence signal (question, source, unit, rationale, honest limit) plus "
     "the scoring weights and the two keyless sources behind them.",
     intel_catalog, 10_000),
]


def register_intel_tools(registry: ToolRegistry, service: Any) -> list[str]:
    """Register the intel toolset bound to ONE `IntelService` instance."""
    added: list[str] = []
    for name, description, handler, timeout in _TOOLS:
        if registry.get(name) is not None:
            continue

        async def _bound(args: dict[str, Any], ctx: ToolContext, _handler=handler) -> tuple[str, Any]:
            return await _handler(args, ctx, service)

        registry.register(ToolDefinition(
            name=name,
            description=description,
            input_schema=_SCHEMAS[name],
            handler=_bound,
            permission="read",
            risk="low",
            timeout_ms=timeout,
        ))
        added.append(name)
    return added


__all__ = [
    "MAX_TICKERS",
    "intel_cards",
    "intel_catalog",
    "intel_entity",
    "intel_scan",
    "intel_series",
    "intel_watch",
    "register_intel_tools",
]
