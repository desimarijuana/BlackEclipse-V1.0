"""Corporate-action awareness (Universal Financial Data Accuracy, §17).

Splits, buybacks, share issuance, rights issues, dividends, spin-offs, M&A, ADR
ratio changes, ticker/name changes, delistings and relistings can invalidate a
naive historical calculation — a price series across a 2-for-1 split is not a
50% drawdown.

This module does NOT fetch actions; it takes declared actions and:
  * adjusts a historical price/share count to a comparable basis,
  * flags when a fact spans an action with no adjustment available.

Corporate-action data is DATA (`CorporateAction`); a company is never special-cased.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .model import CorporateAction

# An action that changes the share count / price basis and therefore needs an
# adjustment before comparing pre- and post-event values.
_ADJUSTING_KINDS = {"split", "reverse_split", "buyback", "issuance", "rights", "adr_ratio"}

# An action that changes what the entity IS — a comparison across it is invalid
# unless the caller explicitly opts in.
_IDENTITY_KINDS = {"spinoff", "m_and_a", "ticker_change", "name_change", "delisting", "relisting"}


@dataclass
class ActionNotice:
    kind: str
    effective_date: Optional[str]
    affects: str  # "price" | "shares" | "identity"
    disclosure: str


def notice_for(action: CorporateAction) -> Optional[ActionNotice]:
    """What a historical comparison spanning this action must disclose."""
    kind = action.kind
    if kind in ("split", "reverse_split", "adr_ratio"):
        return ActionNotice(kind, action.effective_date, "price",
                             f"a {kind.replace('_', ' ')} on {action.effective_date} changes the price/share basis; "
                             "pre-event values must be adjusted before comparison")
    if kind in ("buyback", "issuance", "rights"):
        return ActionNotice(kind, action.effective_date, "shares",
                             f"a {kind.replace('_', ' ')} on {action.effective_date} changes the share count")
    if kind in _IDENTITY_KINDS:
        return ActionNotice(kind, action.effective_date, "identity",
                             f"a {kind.replace('_', ' ')} on {action.effective_date} changes the entity; "
                             "a naive across-event comparison is not valid")
    return None


def actions_between(actions: Sequence[CorporateAction], start: Optional[str], end: Optional[str]) -> list[CorporateAction]:
    """Declared actions whose effective date falls in [start, end]."""
    if not start or not end:
        return []
    return [a for a in actions if a.effective_date and str(start) <= str(a.effective_date) <= str(end)]


def adjust_for_split(value: Optional[float], ratio: Optional[float], *, reverse: bool = False) -> Optional[float]:
    """Adjust a pre-split per-share value to a post-split basis.

    A 2-for-1 split (`ratio=2.0`) halves the per-share price. A reverse split
    (`reverse=True`) multiplies it. Missing ratio or value → None (never assume 1).
    """
    if value is None or not ratio or ratio <= 0:
        return None
    return value * (1.0 / ratio) if not reverse else value * ratio


def comparability_disclosure(actions: Sequence[CorporateAction], start: Optional[str], end: Optional[str]) -> list[ActionNotice]:
    """Every action in the window and what the answer must disclose about it."""
    out: list[ActionNotice] = []
    for action in actions_between(actions, start, end):
        notice = notice_for(action)
        if notice is not None:
            out.append(notice)
    return out


def extract_from_series(rows: Sequence[dict], *, source: str = "market_data") -> list[CorporateAction]:
    """Derive corporate actions from a price series that carries them.

    yfinance exposes `Dividends` and `Stock Splits` on the bars where they occur.
    A bar with `split` != 0 is a split; a bar with `dividend` != 0 is a dividend.
    Nothing is inferred from a price move — only from the explicit columns.
    """
    actions: list[CorporateAction] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        date = row.get("date")
        split = row.get("split")
        if isinstance(split, (int, float)) and split not in (0, 1):
            kind = "reverse_split" if split < 1 else "split"
            actions.append(CorporateAction(kind=kind, effective_date=str(date) if date else None,
                                            ratio=float(split), source=source))
        dividend = row.get("dividend")
        if isinstance(dividend, (int, float)) and dividend != 0:
            actions.append(CorporateAction(kind="dividend", effective_date=str(date) if date else None,
                                            source=source, notes=f"cash dividend {dividend}"))
    return actions


__all__ = [
    "ActionNotice",
    "actions_between",
    "adjust_for_split",
    "comparability_disclosure",
    "extract_from_series",
    "notice_for",
]
