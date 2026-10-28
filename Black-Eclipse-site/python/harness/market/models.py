"""Canonical market-data contract — provider-neutral records.

Every provider adapter returns a payload; the gateway normalizes it into ONE of
these records. Agents and analytics never see a provider's response shape. Each
record preserves provenance (provider, source, timestamps, quality, freshness)
so a number can always be explained.

Vocabulary is shared with the retrieval layer where it already exists
(`FreshnessRequirement`, `QualityStatus`) — never a second, drifting enum.
"""

from __future__ import annotations

import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ── Shared vocabulary ────────────────────────────────────────────────────────

AssetType = Literal[
    "equity", "etf", "fund", "crypto", "fx", "commodity", "index",
    "derivative", "bond", "option", "future", "macro", "unknown",
]
DataStatus = Literal["OK", "UNAVAILABLE", "STALE", "PARTIAL", "CONFLICTING", "UNKNOWN"]
QualityStatus = Literal["valid", "warning", "invalid", "unknown"]
Freshness = Literal["realtime", "intraday", "daily", "slow", "any"]
# How a timestamp was obtained. `provider_asof` = the market's own time; a
# `retrieval_clock` value is when we fetched it; `snapshot_write` is a stored
# row's write time. Never dress one up as another.
ObservationSource = Literal["provider_asof", "retrieval_clock", "snapshot_write", "unknown"]

Interval = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() % 1 * 1000):03d}Z"


class MarketMeta(BaseModel):
    """Provenance + identity carried by every market record. Never fabricated."""

    instrument_id: Optional[str] = None
    symbol: Optional[str] = None
    asset_type: Optional[AssetType] = None
    exchange: Optional[str] = None
    venue: Optional[str] = None
    currency: Optional[str] = None
    # The market's own time the value is about, when the provider reports one.
    event_time: Optional[str] = None
    # When we retrieved it.
    retrieved_at: str = Field(default_factory=_now_iso)
    # When the provider published it, when known.
    published_at: Optional[str] = None
    observation_source: ObservationSource = "unknown"
    provider: Optional[str] = None
    source: Optional[str] = None
    data_type: Optional[str] = None
    data_status: DataStatus = "OK"
    freshness: Freshness = "any"
    quality: QualityStatus = "unknown"
    warnings: list[str] = Field(default_factory=list)


class MarketRecord(BaseModel):
    """Base for every canonical record: identity/provenance + a value payload."""

    meta: MarketMeta = Field(default_factory=MarketMeta)
    raw: Optional[dict[str, Any]] = None
    # True when at least two configured providers disagreed materially. Such a
    # record is never silently presented; the candidates ride in `conflict`.
    conflict: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


# ── 1. Quote ─────────────────────────────────────────────────────────────────

class Quote(MarketRecord):
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    volume: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    previous_close: Optional[float] = None
    open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    market_status: Optional[str] = None  # open | closed | pre | post | unknown
    timestamp: Optional[str] = None      # the market time of the quote
    age_seconds: Optional[float] = None


# ── 2/3/4. History / OHLCV / Volume ──────────────────────────────────────────

class OHLCVBar(BaseModel):
    timestamp: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    # True when Eclipse aggregated a finer series into this interval (never
    # claimed as provider-native).
    aggregated: bool = False


class HistoricalPriceSeries(MarketRecord):
    interval: Optional[Interval] = None
    adjusted: Optional[bool] = None
    bars: list[OHLCVBar] = Field(default_factory=list)
    start: Optional[str] = None
    end: Optional[str] = None
    aggregation: Optional[str] = None  # e.g. "Eclipse aggregated 1m→1h (mean)"
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_timestamps: int = 0
    corporate_actions: list[dict[str, Any]] = Field(default_factory=list)


class VolumeStats(MarketRecord):
    total_volume: Optional[float] = None
    buy_volume: Optional[float] = None
    sell_volume: Optional[float] = None
    average_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    volume_change: Optional[float] = None
    window: Optional[str] = None
    # Which fields the provider supplied natively vs which Eclipse derived.
    native_fields: list[str] = Field(default_factory=list)
    derived_fields: list[str] = Field(default_factory=list)


# ── 5. Order book ────────────────────────────────────────────────────────────

class OrderBookLevel(BaseModel):
    price: float
    quantity: float
    cumulative: Optional[float] = None


class OrderBook(MarketRecord):
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    spread_bps: Optional[float] = None
    bid_depth: Optional[float] = None
    ask_depth: Optional[float] = None
    imbalance: Optional[float] = None       # (bid_depth-ask_depth)/(bid_depth+ask_depth)
    liquidity_estimate: Optional[float] = None
    sequence: Optional[int] = None
    timestamp: Optional[str] = None
    # "snapshot" | "delta" | "resynced" — how this book was obtained.
    book_state: str = "snapshot"
    resync_count: int = 0


# ── 6. Trades ────────────────────────────────────────────────────────────────

class Trade(BaseModel):
    trade_id: Optional[str] = None
    timestamp: str
    price: float
    quantity: float
    side: Optional[Literal["buy", "sell"]] = None
    # True when Eclipse inferred the side (e.g. tick rule) rather than the
    # provider supplying it. Never presented as provider data.
    side_inferred: bool = False
    exchange: Optional[str] = None
    venue: Optional[str] = None


class TradeTape(MarketRecord):
    trades: list[Trade] = Field(default_factory=list)
    aggressive_buy_volume: Optional[float] = None
    aggressive_sell_volume: Optional[float] = None
    imbalance: Optional[float] = None
    large_trades: list[dict[str, Any]] = Field(default_factory=list)


# ── 7. Market cap ────────────────────────────────────────────────────────────

class MarketCap(MarketRecord):
    market_cap: Optional[float] = None
    price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    # Which share basis the cap uses: never silently mixed.
    shares_basis: Optional[Literal["basic", "diluted", "current", "float", "unknown"]] = None
    timestamp: Optional[str] = None


# ── 8. Supply (crypto) ───────────────────────────────────────────────────────

class Supply(MarketRecord):
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    max_supply: Optional[float] = None
    free_float: Optional[float] = None
    fdv: Optional[float] = None                 # fully-diluted valuation
    circulating_market_cap: Optional[float] = None
    timestamp: Optional[str] = None


# ── 9. Funding rate ──────────────────────────────────────────────────────────

class FundingRate(MarketRecord):
    funding_rate: Optional[float] = None
    funding_interval_hours: Optional[float] = None
    next_funding_time: Optional[str] = None
    predicted_funding: Optional[float] = None
    # Annualized is ALWAYS a derived figure — labelled, never confused with the
    # raw per-interval rate.
    annualized_funding: Optional[float] = None
    annualized_derivation: Optional[str] = None
    historical: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: Optional[str] = None


# ── 10. Open interest ────────────────────────────────────────────────────────

class OpenInterest(MarketRecord):
    open_interest: Optional[float] = None       # in contracts/base units
    open_interest_usd: Optional[float] = None
    oi_change: Optional[float] = None
    oi_change_pct: Optional[float] = None
    oi_velocity: Optional[float] = None
    window: Optional[str] = None
    native_fields: list[str] = Field(default_factory=list)
    derived_fields: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = None


# ── 11. Options chain ────────────────────────────────────────────────────────

class OptionContract(BaseModel):
    expiration: str
    strike: Optional[float] = None
    option_type: Literal["call", "put"]
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_volatility: Optional[float] = None
    # Greeks: None means "not available" — NEVER presented as zero.
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    greeks_source: Optional[str] = None  # "provider" | "calculated" | None
    iv_source: Optional[str] = None


class OptionsChain(MarketRecord):
    underlying: Optional[str] = None
    underlying_price: Optional[float] = None
    expirations: list[str] = Field(default_factory=list)
    contracts: list[OptionContract] = Field(default_factory=list)
    timestamp: Optional[str] = None


# ── 12. FX ───────────────────────────────────────────────────────────────────

class FXRate(MarketRecord):
    base: Optional[str] = None
    quote: Optional[str] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    rate: Optional[float] = None       # convenience = mid when available
    cross: bool = False                # derived by cross-conversion
    derivation: Optional[str] = None
    market_status: Optional[str] = None
    timestamp: Optional[str] = None


# ── 13. Bonds ────────────────────────────────────────────────────────────────

class BondData(MarketRecord):
    price: Optional[float] = None
    yield_: Optional[float] = Field(default=None, alias="yield")
    coupon: Optional[float] = None
    maturity: Optional[str] = None
    duration: Optional[float] = None
    modified_duration: Optional[float] = None
    convexity: Optional[float] = None
    spread: Optional[float] = None
    rating: Optional[str] = None
    issuer: Optional[str] = None
    tenor: Optional[str] = None
    series_type: Optional[str] = None  # treasury | corporate | government

    model_config = {"populate_by_name": True}


# ── 14. DeFi TVL ─────────────────────────────────────────────────────────────

class TvlSnapshot(MarketRecord):
    """Total value locked for a protocol or a chain.

    `chain_tvls` is the provider's per-chain breakdown; it is never summed into
    `tvl_usd` here — a caller can see exactly which figure came from where.
    """

    protocol: Optional[str] = None
    chain: Optional[str] = None
    tvl_usd: Optional[float] = None
    change_24h_pct: Optional[float] = None
    change_7d_pct: Optional[float] = None
    chain_tvls: dict[str, float] = Field(default_factory=dict)
    timestamp: Optional[str] = None


# ── 15. On-chain account metrics ─────────────────────────────────────────────

class OnchainMetric(MarketRecord):
    """Account-scoped on-chain metrics (balance, nonce, latest block).

    These are chain facts, not market prices: the observation source is stated
    so an operator can tell a provider as-of time from our retrieval clock.
    """

    address: Optional[str] = None
    chain: Optional[str] = None
    native_balance: Optional[float] = None   # in native units (ETH, SOL…)
    tx_count: Optional[int] = None            # outbound transaction count
    latest_block: Optional[int] = None
    account_type: Optional[str] = None
    owner_program: Optional[str] = None
    executable: Optional[bool] = None
    timestamp: Optional[str] = None


# ── 16. Futures liquidations ─────────────────────────────────────────────────

class LiquidationStats(MarketRecord):
    """Forced-liquidation totals for one coin on one futures exchange.

    `windows` keeps the provider's per-window breakdown (1h/4h/12h/24h) as
    supplied; the top-level fields are the 24h figures and are never summed from
    a different window.
    """

    exchange: Optional[str] = None
    window: Optional[str] = None
    total_usd: Optional[float] = None
    long_usd: Optional[float] = None
    short_usd: Optional[float] = None
    windows: dict[str, dict[str, Optional[float]]] = Field(default_factory=dict)
    timestamp: Optional[str] = None


# ── 17. Long/short account ratio ─────────────────────────────────────────────

class LongShortRatio(MarketRecord):
    exchange: Optional[str] = None
    interval: Optional[str] = None
    long_percent: Optional[float] = None
    short_percent: Optional[float] = None
    long_short_ratio: Optional[float] = None
    series: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: Optional[str] = None


# ── 18. Streaming event ──────────────────────────────────────────────────────

MarketEventType = Literal[
    "market.quote", "market.trade", "market.orderbook", "market.ohlcv",
    "market.funding", "market.open_interest", "market.options", "market.fx",
    "market.bond",
]


class MarketDataEvent(BaseModel):
    """A normalized streaming event. Carries full provenance + timestamps."""

    event_type: MarketEventType
    meta: MarketMeta = Field(default_factory=MarketMeta)
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: Optional[int] = None
    # Deduplication key derived from provider+instrument+event+time+value.
    event_id: Optional[str] = None
    emitted_at: str = Field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


__all__ = [
    "AssetType",
    "BondData",
    "DataStatus",
    "Freshness",
    "FXRate",
    "FundingRate",
    "HistoricalPriceSeries",
    "Interval",
    "LiquidationStats",
    "LongShortRatio",
    "MarketCap",
    "MarketDataEvent",
    "MarketEventType",
    "MarketMeta",
    "MarketRecord",
    "OHLCVBar",
    "OnchainMetric",
    "OpenInterest",
    "OptionContract",
    "OptionsChain",
    "OrderBook",
    "OrderBookLevel",
    "QualityStatus",
    "Quote",
    "Supply",
    "Trade",
    "TradeTape",
    "TvlSnapshot",
    "VolumeStats",
]
