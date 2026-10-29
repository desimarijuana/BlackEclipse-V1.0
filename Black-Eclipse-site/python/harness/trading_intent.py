"""Per-run directives that keep a trade request from becoming a research project.

Two turns look alike to a language model and must not: "analyze X and place a
trade" (an execution request with a brief justification) and "analyze X" (a
research request). Without a deterministic nudge the first one browses news and
scrapers until its step budget runs out, and no order is ever placed.

The block is added to the per-run `runtime_context`, never to the byte-stable
system head, so it cannot invalidate the prompt cache. It grants nothing: the
tools, the mandate caps and the demo-only rule are enforced by the service. A
miss only means the model keeps the generic prompt guidance.

Detection is lexical and deterministic. A refusal ("do not place a trade") and a
question ("should I buy...") always win, so advice is never turned into an order.
"""

from __future__ import annotations

import re
from typing import Any

#: An execution verb. Word-bounded so "seller" or "opening" never match.
_TRADE_VERB_RE = re.compile(r"\b(place|buy|sell|submit|execute|open)\b")
_TRADE_NOUNS = ("order", "trade", "position", "lot", "mandate")
_TRADE_REFUSALS = (
    "do not place", "don't place", "dont place", "do not buy", "don't buy",
    "dont buy", "do not sell", "don't sell", "dont sell", "do not trade",
    "don't trade", "dont trade", "no trade", "no order", "without placing",
    "without trading", "do not close", "don't close", "dont close", "no close",
    "analysis only", "just analyze", "only analyze",
    "explain only", "paper only",
)
_TRADE_QUESTION_PREFIXES = ("should i", "should we", "is it a good", "would you", "what if i")

_TRADE_CLOSE_RE = re.compile(
    r"\b(close|exit|flatten|liquidate|square off|cash out|get out)\b"
)
_TRADE_CLOSE_NOUNS = ("position", "trade", "order", "exposure", "all", "everything")

_TRADE_MODIFY_RE = re.compile(
    r"\b(move|trail|tighten|loosen|adjust|breakeven|break even)\b"
)
_TRADE_MODIFY_NOUNS = ("stop", "take profit", "target", "bracket", "sl", "tp")


def trading_intent_block(query: str) -> str:
    """The per-run directive for a trade or close turn ("" when not one)."""
    text = (query or "").strip().lower()
    if not text or any(marker in text for marker in _TRADE_REFUSALS):
        return ""
    if text.startswith(_TRADE_QUESTION_PREFIXES):
        return ""
    if _TRADE_CLOSE_RE.search(text) and any(
        noun in text for noun in _TRADE_CLOSE_NOUNS
    ):
        return (
            "# Close request\n"
            "This turn asks to close exposure, so treat it as an execution task. Do "
            "not research, do not open a new order, and never call `order_preview`.\n"
            "Call `position_close` with `all: true` when the user wants to step out "
            "of everything, with the `ticket` they named, or with `symbol` to close "
            "one instrument. Pass `volume` for a partial close. Closing only reduces "
            "exposure, so it needs no mandate and no approval; the only connection "
            "is resolved for you, so do not ask for an id.\n"
            "Report each ticket, its close price and any broker refusal. A live "
            "close is refused and belongs in the terminal."
        )
    if _TRADE_MODIFY_RE.search(text) and any(
        noun in text for noun in _TRADE_MODIFY_NOUNS
    ):
        return (
            "# Modify request\n"
            "This turn asks to change a position's stop/target, so treat it as an "
            "execution task. Do not close and reopen the position, do not research, "
            "and never call `order_preview`.\n"
            "Call `position_modify` with the `ticket` and the new `stopLoss` and/or "
            "`takeProfit` (0 removes a level). It needs no mandate or approval; the "
            "only connection is resolved for you.\n"
            "If the change widens risk (a stop farther away, or removed), say so "
            "plainly before reporting the broker's stored bracket."
        )
    if not _TRADE_VERB_RE.search(text):
        return ""
    if not any(noun in text for noun in _TRADE_NOUNS):
        return ""
    return (
        "# Trading request\n"
        "This turn asks for a trade, so treat it as an execution task with a brief "
        "justification, not a research project. Do not browse the web, search news, "
        "scrape pages or run datasets; a trade does not need a news sweep.\n"
        "1. `broker_quote` for the live price, then `broker_bars` on the broker "
        "symbol (H1 or D1, ~120 bars). It returns the broker's own series and a "
        "deterministic ATR(14); never substitute a proxy ETF for the instrument "
        "being traded. Two reads are enough to place a stop and a target.\n"
        "2. Do not ask the user for a mandate id or connection id. `order_submit` "
        "resolves the active demo mandate that covers the symbol and the only "
        "connection on its own; call `broker_mandates` only if it reports that no "
        "single mandate applies.\n"
        "3. Call `order_submit` ONCE with `intent` {symbol, side, type: \"market\", "
        "volume, stopLoss, takeProfit}; size it small (0.01 lots) when the user says "
        "\"small\". Never call `order_preview` first.\n"
        "4. Report the ticket, fill price, stop/target and the mandate orders left. "
        "This is demo only and live is unreachable.\n"
        "If no active mandate covers the symbol, say so and stop; never substitute "
        "another account, broker or symbol."
    )


#: The tools a trade/close/modify turn actually needs. A trade turn binds only
#: these (plus presentation), instead of the agent's ~700-tool surface. The set
#: is deliberately a strict subset of the declared tools; it can never add one.
TRADE_SURFACE_TOOLS = frozenset({
    "broker_connections",
    "broker_account",
    "broker_positions",
    "broker_orders",
    "broker_quote",
    "broker_bars",
    "broker_mandates",
    "broker_fills",
    "broker_reconciliation",
    "order_ledger",
    "order_preview",
    "order_submit",
    "position_close",
    "position_modify",
    "response_block_schema",
    "response_style_guide",
    "response_validate",
    "clarify",
})

_EFFECT_TOOLS = frozenset({"order_submit", "position_close", "position_modify"})


def is_trade_turn(query: str) -> bool:
    """Whether the per-run trading directive applies to this turn."""
    return bool(trading_intent_block(query))


def narrow_trade_surface(allowed: set[str]) -> set[str]:
    """The trade-turn subset of `allowed`, or `allowed` when it cannot apply.

    A run that cannot submit, close or modify has no business being narrowed
    (the user may be asking a pure analysis question), and a surface with no
    broker tool at all is left untouched, so this can only ever remove.
    """
    if not (_EFFECT_TOOLS & set(allowed)):
        return set(allowed)
    narrowed = {name for name in allowed if name in TRADE_SURFACE_TOOLS}
    return narrowed or set(allowed)


def apply_trade_surface(query: Any, allowed: set[str], resolution: Any):
    """Narrow `allowed` (and the reported resolution) for a trade turn."""
    if not allowed or not is_trade_turn(query):
        return allowed, resolution
    narrowed = narrow_trade_surface(allowed)
    if narrowed == allowed:
        return allowed, resolution
    from dataclasses import replace  # noqa: PLC0415

    return narrowed, replace(
        resolution, allowed=frozenset(narrowed), boundTools=len(narrowed)
    )


__all__ = [
    "TRADE_SURFACE_TOOLS",
    "apply_trade_surface",
    "is_trade_turn",
    "narrow_trade_surface",
    "trading_intent_block",
]