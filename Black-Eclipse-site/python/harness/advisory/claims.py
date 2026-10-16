"""Deterministic extraction of actionable recommendations from an answer.

No model call. A sentence yields a claim only when it carries an actionable
directive (`buy`, `sell`, `rebalance`, …) AND a tradable token — a symbol or a
numeric target (weight / amount / share count). Ordinary conversation, and an
opinion with neither, is never flagged, so the gate stays silent unless there is
a concrete recommendation to verify.

Matching is deliberately conservative: a false "unverified" would be noise, so a
sentence must be unambiguous to become a claim.
"""

from __future__ import annotations

import re

from .model import AdvisoryClaim

# ── Directives ────────────────────────────────────────────────────────────────
# Ordered longest-first so "go long" wins over "long" and "add to" over "add".
_DIRECTIVES: tuple[tuple[str, str], ...] = (
    ("go long", "buy"),
    ("go short", "short"),
    ("take profits", "sell"),
    ("take profit", "sell"),
    ("add to", "add"),
    ("rebalance", "rebalance"),
    ("allocate", "allocate"),
    ("hedge", "hedge"),
    ("harvest", "harvest"),
    ("reduce", "reduce"),
    ("increase", "increase"),
    ("trim", "trim"),
    ("exit", "exit"),
    ("buy", "buy"),
    ("sell", "sell"),
    ("short", "short"),
    ("add", "add"),
)
_DIRECTIVE_MAP = {word: action for word, action in _DIRECTIVES}
_DIRECTIVE_RE = re.compile(
    r"\b(" + "|".join(re.escape(word) for word, _ in _DIRECTIVES) + r")\b",
    re.IGNORECASE,
)

# ── Tradable tokens ───────────────────────────────────────────────────────────
# Uppercase 2–5 letter tokens with an optional exchange suffix (BRK.B, 7203.T).
_SYMBOL_RE = re.compile(r"\$?\b([A-Z]{2,5}(?:[.\-][A-Z0-9]{1,3})?)\b")

# Common uppercase words that are NOT tickers (avoid flagging prose).
_SYMBOL_STOP = frozenset({
    "I", "II", "III", "IV", "AI", "PE", "PB", "PS", "EV", "ROE", "ROA", "ROI",
    "NAV", "HHI", "EPS", "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
    "ETF", "ETFS", "IPO", "CEO", "CFO", "COO", "CTO", "GDP", "CPI", "PPI", "FED",
    "ECB", "YTD", "QOQ", "YOY", "MOQ", "USD", "P", "IRR", "NPV", "WACC", "DCF",
    "GAAP", "IFRS", "SEC", "FDA", "OK", "USA", "EU", "UK", "US", "AS", "OR", "SO",
    "IT", "IF", "IN", "ON", "TO", "OF", "AT", "IS", "BE", "BY", "WE", "NO", "DO",
    "BUY", "SELL", "ADD", "TRIM", "EXIT", "LONG", "SHORT", "HOLD", "N/A", "TBD",
})

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_DOLLAR_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?([kKmMbB])?")
_SHARES_RE = re.compile(r"\b(\d[\d,]*)\s+shares?\b", re.IGNORECASE)
_RATIO_RE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")

_SUFFIX = {"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}


def _parse_numbers(sentence: str) -> tuple[list[float], list[str]]:
    """Every numeric target in a sentence, as floats + the labels that named them."""
    values: list[float] = []
    labels: list[str] = []

    for match in _PERCENT_RE.finditer(sentence):
        values.append(float(match.group(1)))
        labels.append(match.group(0).strip())

    for match in _DOLLAR_RE.finditer(sentence):
        amount = float(match.group(1).replace(",", ""))
        suffix = (match.group(2) or "").lower()
        if suffix:
            amount *= _SUFFIX[suffix]
        values.append(amount)
        labels.append(match.group(0).strip())

    for match in _SHARES_RE.finditer(sentence):
        values.append(float(match.group(1).replace(",", "")))
        labels.append(match.group(0).strip())

    for match in _RATIO_RE.finditer(sentence):
        values.append(float(match.group(1)))
        values.append(float(match.group(2)))
        labels.append(match.group(0).strip())

    return values, labels


def _symbols(sentence: str) -> list[str]:
    found: list[str] = []
    for match in _SYMBOL_RE.finditer(sentence):
        symbol = match.group(1)
        if symbol.upper() in _SYMBOL_STOP:
            continue
        if symbol not in found:
            found.append(symbol)
    return found


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _dedupe_target(labels: list[str]) -> str | None:
    if not labels:
        return None
    # Keep the first label — the most descriptive of the recommendation's shape.
    return labels[0]


def extract_claims(answer: str) -> list[AdvisoryClaim]:
    """Every actionable recommendation in `answer`, in the order it appears.

    A claim needs a directive AND (a symbol OR a numeric target). Duplicates on
    (action, symbols, target) collapse to one.
    """
    claims: list[AdvisoryClaim] = []
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()

    for sentence in _sentences(answer):
        directive = _DIRECTIVE_RE.search(sentence)
        if directive is None:
            continue
        action = _DIRECTIVE_MAP[directive.group(1).lower()]

        symbols = tuple(_symbols(sentence))
        values, labels = _parse_numbers(sentence)
        if not symbols and not values:
            continue

        target = _dedupe_target(labels)
        key = (action, symbols, target)
        if key in seen:
            continue
        seen.add(key)
        claims.append(
            AdvisoryClaim(
                action=action,
                symbols=symbols,
                target=target,
                values=tuple(values),
                sentence=sentence,
            )
        )
    return claims


__all__ = ["extract_claims"]
