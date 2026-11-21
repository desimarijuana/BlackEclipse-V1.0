"""Market execution rules — what a trading market permits, separate from cost.

**Naming, stated once.** `quant/venues.py` uses "venue" for a strategy
*language* (Pine, NinjaScript, …). This module uses **market** for a place that
trades instruments (US equities, A-shares, Hong Kong, crypto). The two are
different axes and must not be conflated.

`ExecutionAssumptions` describes *what a fill costs* (commission shape, spread,
impact). This module describes *what the market permits*: settlement, lot
rounding, price limits, sell-side taxes and whether retail shorting exists.
Both are needed; conflating them is how a backtest silently stops meaning
anything outside the US.

Scope and honesty:

  * The rules here are **declarations with explicit provenance**. `us_equity`
    and `crypto` are simple (no price limits, fractional size). `a_share`
    reproduces the published mainland rules: T+1, no retail short, board price
    limits, 100-share lots (200 on STAR, 100 then 1-share steps on Beijing),
    CNY 5 minimum commission, 0.05% sell-side stamp duty, 0.001% transfer fee.
  * `hk_equity` declares T+0 sellability and 0.10% stamp duty on **both** sides;
    its lot size is per instrument, so `round_size` refuses to invent one.
  * A rule this module cannot know (ST status, listing-day exemptions, per-stock
    HK lot sizes) is **not guessed** — `band()` takes an explicit `board`, and
    `round_size()` returns the quantity unchanged when the market has no fixed
    lot, leaving the decision to the instrument data.
  * `market` is recorded on every strategy spec and therefore on the run
    manifest; `validate_strategy` rejects an unknown market and a retail short
    in a market that bans it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

#: Price-limit boards a caller may name. A symbol's board is instrument data,
#: never inferred from a bare ticker here.
BOARDS: tuple[str, ...] = ("main", "chinext", "star", "beijing", "st", "unknown")


@dataclass(frozen=True)
class MarketRules:
    """One market's execution mandates. Pure data plus pure helpers."""

    id: str
    label: str
    currency: str
    #: Days before bought shares become sellable (1 = T+1).
    settle_buy_days: int = 0
    #: Fixed lot increment; 0 means "the instrument decides" (fractional/HK).
    lot_size: float = 0.0
    #: Quantity decimals used when `lot_size` is 0.
    quantity_precision: int = 6
    #: Board -> allowed move as a fraction (0.10 = +/-10%). Empty = no limit.
    price_limits: dict[str, float] = field(default_factory=dict)
    #: Sell-side stamp duty in basis points.
    stamp_duty_bps_sell: float = 0.0
    #: Stamp duty charged on both sides, in basis points (HK).
    stamp_duty_bps_both: float = 0.0
    #: Transfer/exchange fee in basis points, both sides.
    transfer_fee_bps: float = 0.0
    #: Minimum commission in the market currency.
    commission_min: float = 0.0
    #: Whether a retail account may open a short.
    allows_short: bool = True

    # -- limits ---------------------------------------------------------

    def band(self, prev_close: float, board: Optional[str] = None) -> Optional[tuple[float, float]]:
        """The allowed (low, high) price band for the session, or None.

        Returns None when the market has no limit OR the board is unknown for a
        market that has limits: an unknown board is never silently treated as
        the loosest one.
        """
        if not self.price_limits or prev_close is None or prev_close <= 0:
            return None
        key = (board or "unknown").strip().lower()
        pct = self.price_limits.get(key)
        if pct is None:
            return None
        return (
            round(prev_close * (1.0 - pct), self.quantity_precision + 2),
            round(prev_close * (1.0 + pct), self.quantity_precision + 2),
        )

    # -- size -----------------------------------------------------------

    def round_size(self, raw: float) -> float:
        """Round a computed quantity to the market's tradeable increment.

        `lot_size > 0` floors to a whole lot (a size below one lot becomes 0,
        i.e. no trade — never a partial lot). `lot_size == 0` keeps fractional
        size at `quantity_precision` decimals.
        """
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            return 0.0
        if self.lot_size > 0:
            return math.floor(value / self.lot_size) * self.lot_size
        return round(value, self.quantity_precision)

    # -- permissions ----------------------------------------------------

    def can_sell(self, *, bought_today: bool) -> tuple[bool, str]:
        """Whether a sell is permitted now."""
        if bought_today and self.settle_buy_days > 0:
            return False, f"{self.id}: T+{self.settle_buy_days} — shares bought today are not sellable"
        return True, ""

    def can_short(self) -> tuple[bool, str]:
        """Whether a retail short is permitted at all."""
        if not self.allows_short:
            return False, f"{self.id}: retail short selling is not permitted"
        return True, ""

    # -- taxes ----------------------------------------------------------

    def sell_tax(self, notional: float) -> float:
        """Stamp duty + transfer fee charged on a sell of `notional`."""
        if notional <= 0:
            return 0.0
        bps = self.stamp_duty_bps_sell + self.stamp_duty_bps_both + self.transfer_fee_bps
        return notional * bps / 10_000.0

    def buy_tax(self, notional: float) -> float:
        """Transfer fee (and any both-sides stamp duty) charged on a buy."""
        if notional <= 0:
            return 0.0
        bps = self.stamp_duty_bps_both + self.transfer_fee_bps
        return notional * bps / 10_000.0

    def describe(self) -> dict:
        """The JSON shape recorded on a run manifest."""
        return {
            "id": self.id,
            "label": self.label,
            "currency": self.currency,
            "settleBuyDays": self.settle_buy_days,
            "lotSize": self.lot_size,
            "priceLimits": dict(self.price_limits),
            "stampDutyBpsSell": self.stamp_duty_bps_sell,
            "stampDutyBpsBoth": self.stamp_duty_bps_both,
            "transferFeeBps": self.transfer_fee_bps,
            "commissionMin": self.commission_min,
            "allowsShort": self.allows_short,
        }


US_EQUITY = MarketRules(
    id="us_equity",
    label="US equities / ETFs",
    currency="USD",
    settle_buy_days=0,
    lot_size=0.0,
    quantity_precision=6,
    allows_short=True,
)

A_SHARE = MarketRules(
    id="a_share",
    label="Mainland China A-shares",
    currency="CNY",
    settle_buy_days=1,
    lot_size=100.0,
    quantity_precision=0,
    # Main board 10%, ChiNext/STAR 20%, Beijing 30%. ST names and listing-day
    # exemptions are instrument state and are never assumed here.
    price_limits={"main": 0.10, "chinext": 0.20, "star": 0.20, "beijing": 0.30},
    stamp_duty_bps_sell=5.0,
    transfer_fee_bps=0.1,
    commission_min=5.0,
    allows_short=False,
)

HK_EQUITY = MarketRules(
    id="hk_equity",
    label="Hong Kong equities",
    currency="HKD",
    settle_buy_days=0,
    lot_size=0.0,          # per instrument; never invented here
    quantity_precision=0,
    stamp_duty_bps_both=10.0,
    allows_short=False,
)

CRYPTO = MarketRules(
    id="crypto",
    label="Crypto spot / perpetuals",
    currency="USD",
    settle_buy_days=0,
    lot_size=0.0,
    quantity_precision=8,
    allows_short=True,
)

_MARKETS: dict[str, MarketRules] = {
    rules.id: rules for rules in (US_EQUITY, A_SHARE, HK_EQUITY, CRYPTO)
}

MARKETS: tuple[str, ...] = tuple(_MARKETS)
DEFAULT_MARKET = US_EQUITY.id


def rules_for(market: Optional[str]) -> MarketRules:
    """The rules for `market`. Raises KeyError naming the known markets."""
    key = (market or DEFAULT_MARKET).strip().lower()
    rules = _MARKETS.get(key)
    if rules is None:
        raise KeyError(f"unknown market {market!r}; known: {', '.join(MARKETS)}")
    return rules


def is_known(market: Optional[str]) -> bool:
    return (market or "").strip().lower() in _MARKETS


#: A-share board prefixes, in the order they must be tested. 688/689 = STAR
#: (科创板), 300/301 = ChiNext (创业板), 8xx/4xx/920 = Beijing (北交所).
_A_SHARE_BOARDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("688", "689"), "star"),
    (("300", "301"), "chinext"),
    (("8", "4", "920"), "beijing"),
)


def board_for_code(symbol: Optional[str]) -> str:
    """Best-effort A-share board from a code prefix; `unknown` otherwise.

    This is a **prefix mapping, not instrument truth**: ST status, the listing
    day and index-membership changes are instrument state this function cannot
    know, so they are never assumed. A caller that has the instrument master
    should pass the board explicitly to `rules_for(...).band()` instead.
    """
    raw = (symbol or "").strip().upper()
    code = raw.split(".")[0]
    # Accept 600519.SH / 600519 / SH600519.
    if code.startswith(("SH", "SZ", "BJ")):
        code = code[2:]
    if not (len(code) == 6 and code.isdigit()):
        return "unknown"
    for prefixes, board in _A_SHARE_BOARDS:
        if code.startswith(prefixes):
            return board
    return "main"


__all__ = [
    "A_SHARE",
    "BOARDS",
    "CRYPTO",
    "DEFAULT_MARKET",
    "HK_EQUITY",
    "MARKETS",
    "MarketRules",
    "US_EQUITY",
    "board_for_code",
    "is_known",
    "rules_for",
]
