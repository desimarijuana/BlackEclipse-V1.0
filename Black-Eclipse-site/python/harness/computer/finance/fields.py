"""The financial field vocabulary and pure extraction helpers.

Recognition is by label (aliases) and value shape. `extract_fields` reads
`label value` text lines (from OCR or the accessibility tree) into a structured
dict, normalizing numbers and currency. It is pure and tested without a screen.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Canonical field → the labels/aliases that name it on screen.
FINANCIAL_FIELDS: dict[str, tuple[str, ...]] = {
    "symbol": ("ticker", "symbol", "instrument", "contract", "security"),
    "price": ("price", "last", "last price", "mark", "mark price", "market price", "ltp"),
    "bid": ("bid", "bid price", "b"),
    "ask": ("ask", "offer", "ask price", "a"),
    "spread": ("spread",),
    "volume": ("volume", "vol", "qty traded", "shares traded"),
    "position": ("position", "position size", "qty", "quantity held", "net qty"),
    "quantity": ("quantity", "qty", "size", "order qty"),
    "entry": ("entry", "entry price", "avg entry", "fill price"),
    "average_cost": ("avg cost", "average cost", "avg price", "average price", "cost basis"),
    "stop_loss": ("stop loss", "stop", "sl", "stop price"),
    "take_profit": ("take profit", "tp", "target", "limit"),
    "unrealized_pnl": ("unrealized p&l", "unrealized pnl", "open p&l", "open pnl", "p&l", "pnl", "unrealized"),
    "realized_pnl": ("realized p&l", "realized pnl", "closed p&l"),
    "margin": ("margin", "margin used", "used margin"),
    "buying_power": ("buying power", "available funds", "available margin", "available"),
    "account_value": ("account value", "net liq", "net liquidation", "equity", "account balance", "balance"),
    "order_type": ("order type", "type", "ordtype"),
    "order_status": ("order status", "status"),
    "portfolio_weight": ("weight", "portfolio weight", "allocation", "% of portfolio"),
    "exposure": ("exposure", "gross exposure", "net exposure", "notional"),
    "side": ("side", "action", "buy/sell", "direction"),
}

# Fields whose value is money/quantity (numbers, possibly signed/currency).
_NUMERIC_FIELDS = frozenset({
    "price", "bid", "ask", "spread", "volume", "position", "quantity", "entry",
    "average_cost", "stop_loss", "take_profit", "unrealized_pnl", "realized_pnl",
    "margin", "buying_power", "account_value", "portfolio_weight", "exposure",
})

_MONEY = re.compile(r"[-+]?\$?\s*([0-9][0-9,]*\.?[0-9]*)")
_TICKER = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b")

_ALIAS_INDEX: dict[str, str] = {}
for _canonical, _aliases in FINANCIAL_FIELDS.items():
    for _alias in _aliases:
        _ALIAS_INDEX[_alias.lower()] = _canonical


def canonical_field(label: str) -> Optional[str]:
    """The canonical field for a label, or None."""
    cleaned = re.sub(r"[^a-z0-9&%/ ]", "", (label or "").lower()).strip()
    if not cleaned:
        return None
    if cleaned in _ALIAS_INDEX:
        return _ALIAS_INDEX[cleaned]
    # Longest alias that appears as a WHOLE token. Word boundaries matter: a
    # 1-letter alias like "a" (ask) or "b" (bid) must not match inside a ticker
    # such as "AAPL" or a word such as "balance".
    for alias in sorted(_ALIAS_INDEX, key=len, reverse=True):
        if alias and re.search(rf"\b{re.escape(alias)}\b", cleaned):
            return _ALIAS_INDEX[alias]
    return None


def parse_number(value: str) -> Optional[float]:
    """Parse a money/quantity string to a float, or None. Handles $, commas, k/m."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    multiplier = 1.0
    lowered = text.lower()
    if lowered.endswith("k"):
        multiplier, text = 1_000.0, text[:-1]
    elif lowered.endswith("m"):
        multiplier, text = 1_000_000.0, text[:-1]
    elif lowered.endswith("%"):
        text = text[:-1]
    match = _MONEY.search(text)
    if not match:
        return None
    try:
        return float(match.group(1)) * multiplier
    except ValueError:
        return None


def looks_like_symbol(token: str) -> bool:
    return bool(token and _TICKER.fullmatch(token.strip()) and token.strip().upper() not in {"P", "L", "A", "T"})


def extract_fields(lines: list[str]) -> dict[str, Any]:
    """Read `label value` lines into a structured field dict.

    Returns a dict of canonical field → value (float for numeric fields, str
    otherwise) plus a `symbol` when one is recognised. Confidence per field is not
    decided here; the extractor scores the aggregate.
    """
    fields: dict[str, Any] = {}
    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        # Split "Label: value" or "Label value" or "Label<TAB>value".
        parts = re.split(r"[:=\t]|\s{2,}", line, maxsplit=1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) == 2 else ""
        canonical = canonical_field(label)
        if not canonical:
            # A bare upper-case token is a candidate symbol.
            if not value and looks_like_symbol(label) and "symbol" not in fields:
                fields["symbol"] = label.upper()
            continue
        if canonical in _NUMERIC_FIELDS:
            number = parse_number(value if value else label)
            if number is not None:
                fields[canonical] = number
        else:
            text_value = value or label
            if canonical == "symbol":
                token_match = _TICKER.search(text_value.upper())
                fields["symbol"] = token_match.group(1) if token_match else text_value.upper()
            else:
                fields[canonical] = text_value
    return fields


__all__ = [
    "FINANCIAL_FIELDS",
    "canonical_field",
    "extract_fields",
    "looks_like_symbol",
    "parse_number",
]
