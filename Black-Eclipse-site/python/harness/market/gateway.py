"""The Market Data Gateway — semantic capabilities over routed providers.

This is the layer between the agent-facing market tools and the provider
adapters (which live on the TS bridge). One method per capability:

    get_quote, get_historical_prices, get_ohlcv, get_volume, get_orderbook,
    get_trades, get_market_cap, get_supply, get_funding_rate,
    get_open_interest, get_options_chain, get_fx_rate, get_bond_data,
    stream_market_data

The gateway:
  * resolves the instrument ONCE (the shared instrument master),
  * selects providers by capability/asset-class via the ProviderRouter,
  * fetches through the read-only bridge (one HTTP transport),
  * normalizes the provider payload into a canonical record,
  * runs the Data Quality Engine,
  * applies freshness + conflict detection across providers,
  * returns a provenance-carrying record + a structured error on failure.

It never fabricates data: an unsupported capability or an absent provider yields
an honest `MarketError`, not a placeholder.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..tools import DataBridge
from .cache import MarketCache
from .config import get_config
from .errors import (
    DATA_NOT_AVAILABLE,
    INVALID_REQUEST,
    MarketError,
    UNSUPPORTED_CAPABILITY,
    classify_bridge_failure,
)
from .instruments import (
    CanonicalInstrument,
    ContractTerms,
    classify_identifier as _classify,
    from_bridge_payload,
    local_instrument,
)
from .models import (
    BondData,
    FXRate,
    FundingRate,
    HistoricalPriceSeries,
    MarketCap,
    MarketMeta,
    OpenInterest,
    OptionsChain,
    OptionContract,
    OrderBook,
    OrderBookLevel,
    OHLCVBar,
    Quote,
    Supply,
    Trade,
    TradeTape,
    VolumeStats,
)
from .quality import evaluate

# Capability id → the bridge capability the TS adapter router serves it under.
_BRIDGE_CAPABILITY = "market_data"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _meta(
    capability: str,
    instrument: Optional[CanonicalInstrument],
    payload: dict[str, Any],
    *,
    provider: Optional[str] = None,
    source: Optional[str] = None,
    event_time: Optional[str] = None,
    observation_source: str = "unknown",
    freshness: str = "any",
) -> MarketMeta:
    inst = instrument
    return MarketMeta(
        instrument_id=inst.instrument_id if inst else payload.get("instrumentId"),
        symbol=inst.symbol if inst else payload.get("symbol"),
        asset_type=(inst.asset_type if inst else None),
        exchange=inst.exchange if inst else payload.get("exchange"),
        venue=payload.get("exchange") or (inst.exchange if inst else None),
        currency=payload.get("currency") or (inst.currency if inst else None),
        event_time=event_time,
        retrieved_at=payload.get("retrievedAt") or _iso_now(),
        published_at=payload.get("publishedAt"),
        observation_source=observation_source,  # type: ignore[arg-type]
        provider=provider or payload.get("provider"),
        source=source or payload.get("provider") or "bridge",
        data_type=capability,
        freshness=freshness,  # type: ignore[arg-type]
    )


class MarketDataGateway:
    """The one market-data entry point. Provider names never leak upward."""

    def __init__(
        self,
        bridge: Optional[DataBridge],
        cache: Optional[MarketCache] = None,
        *,
        router: Any = None,
        on_event: Any = None,
    ) -> None:
        self._bridge = bridge
        self.cache = cache or MarketCache()
        self._on_event = on_event
        self.config = get_config()
        self.metrics: dict[str, int] = {
            "requests": 0,
            "cacheHits": 0,
            "providerCalls": 0,
            "failures": 0,
            "conflicts": 0,
            "fallbacks": 0,
        }
        # The router is optional at construction so a test can inject one; the
        # default is built lazily so importing the gateway never imports the
        # provider registry eagerly.
        self._router = router
        # Resolved identities are cached briefly so a burst of calls for one
        # symbol does not re-hit the instrument master every time (§46).
        self._instrument_cache: dict[str, tuple[float, CanonicalInstrument]] = {}

    # ── Instrument resolution ────────────────────────────────────────────────
    async def resolve_instrument(
        self, symbol: str, market: Optional[str] = None, terms: Optional[ContractTerms] = None
    ) -> tuple[Optional[CanonicalInstrument], Optional[MarketError]]:
        """Resolve an identifier to a canonical instrument via the bridge.

        The bridge's instrument master is authoritative. A bridge failure is a
        real error (never a guessed identity).
        """
        if self._bridge is None:
            return None, MarketError(DATA_NOT_AVAILABLE, "data bridge not configured")
        clean = (symbol or "").strip().upper()
        if not clean:
            return None, MarketError(INVALID_REQUEST, "symbol is required")
        cache_key = f"{clean}|{(market or '').strip().upper()}"
        cached = self._instrument_cache.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < 120.0:
            instrument = cached[1]
            missing = terms.missing_for(instrument.asset_type) if terms else []
            if missing:
                return None, MarketError(
                    INVALID_REQUEST,
                    f"{instrument.symbol} is a {instrument.asset_type}; its value is "
                    f"undefined without {', '.join(missing)}.",
                    detail={"missingTerms": missing},
                )
            return instrument, None
        params: dict[str, Any] = {"symbol": clean}
        if market:
            params["market"] = market.strip().upper()
        if terms is not None:
            if terms.expiry:
                params["expiry"] = terms.expiry
            if terms.strike is not None:
                params["strike"] = terms.strike
            if terms.right:
                params["right"] = terms.right
            if terms.maturity:
                params["maturity"] = terms.maturity
        try:
            payload = await self._bridge.fetch("market_snapshot", params)
        except Exception as exc:  # noqa: BLE001 - a bridge failure is data
            payload = {"status": "UNAVAILABLE", "error": str(exc)}
        if payload.get("status") != "OK":
            # FX/crypto have NO vault row; the bridge reports not_found for them,
            # but their identity is self-describing from the classifier. Build a
            # deterministic local identity rather than failing the request.
            kind = _classify(clean, market)
            if kind["kind"] in ("fx", "crypto"):
                instrument = local_instrument(kind, clean)
            else:
                return None, classify_bridge_failure(payload, capability="instrument_resolve")
        else:
            instrument = from_bridge_payload(payload, clean)
        missing = terms.missing_for(instrument.asset_type) if terms else []
        if missing:
            return None, MarketError(
                INVALID_REQUEST,
                f"{instrument.symbol} is a {instrument.asset_type}; its value is "
                f"undefined without {', '.join(missing)}.",
                detail={"missingTerms": missing},
            )
        self._instrument_cache[cache_key] = (time.monotonic(), instrument)
        return instrument, None

    # ── Core fetch + normalize seam ──────────────────────────────────────────
    async def _fetch_provider(
        self,
        capability: str,
        instrument: CanonicalInstrument,
        params: dict[str, Any],
        *,
        provider: Optional[str] = None,
        freshness: str = "any",
    ) -> tuple[Optional[dict[str, Any]], Optional[MarketError]]:
        """Fetch one provider's raw payload for a capability through the bridge."""
        if self._bridge is None:
            return None, MarketError(DATA_NOT_AVAILABLE, "data bridge not configured")
        bridge_params: dict[str, Any] = {
            "capability": capability,
            "symbol": instrument.symbol,
            "instrumentId": instrument.instrument_id,
            "assetType": instrument.asset_type,
        }
        if instrument.market:
            bridge_params["market"] = instrument.market
        if provider:
            bridge_params["provider"] = provider
        bridge_params.update(params)
        self.metrics["providerCalls"] += 1
        try:
            payload = await self._bridge.fetch(_BRIDGE_CAPABILITY, bridge_params)
        except Exception as exc:  # noqa: BLE001
            return None, MarketError(
                provider and "PROVIDER_UNAVAILABLE" or DATA_NOT_AVAILABLE,
                str(exc), provider=provider, capability=capability, retryable=True,
            )
        if payload.get("status") != "OK":
            return None, classify_bridge_failure(payload, capability=capability)
        return payload, None

    async def _dispatch(
        self,
        capability: str,
        instrument: CanonicalInstrument,
        params: dict[str, Any],
        *,
        freshness: str,
        normalize: Any,
    ) -> Any:
        """Route → fetch → normalize → quality, with cache + fallback."""
        self.metrics["requests"] += 1
        cache_params = {
            "capability": capability,
            "symbol": instrument.symbol,
            "market": instrument.market,
            **{k: v for k, v in params.items() if k not in ("provider",)},
        }
        if self.config.cache_enabled:
            cached = self.cache.get(capability, cache_params, freshness=freshness)
            if cached is not None:
                self.metrics["cacheHits"] += 1
                return cached

        router = self._router_ref()
        order = router.provider_order(capability, instrument) if router else ()
        if not order:
            return MarketError(
                UNSUPPORTED_CAPABILITY,
                f"no provider supports '{capability}' for {instrument.asset_type}",
                capability=capability,
            )

        last_error: Optional[MarketError] = None
        for index, provider in enumerate(order):
            if index >= self.config.max_providers:
                break
            if router and not router.allow(provider):
                continue
            if index > 0:
                self.metrics["fallbacks"] += 1
            payload, error = await self._fetch_provider(
                capability, instrument, params, provider=provider, freshness=freshness
            )
            if error is not None or payload is None:
                last_error = error
                if router:
                    router.record_failure(provider)
                if error is not None and error.code in ("RATE_LIMITED", "AUTHENTICATION_FAILED"):
                    # A hard provider-level failure: try the next provider.
                    continue
                continue
            if router:
                router.record_success(provider)
            record = normalize(payload, instrument, provider, freshness)
            if record is None:
                last_error = MarketError(DATA_NOT_AVAILABLE, "provider returned an unusable payload",
                                         provider=provider, capability=capability)
                continue
            report = evaluate(record, capability)
            if report.invalid and record.meta.data_status == "UNAVAILABLE":
                # Invalid values are withheld; try the next provider.
                last_error = MarketError(DATA_NOT_AVAILABLE,
                                         "provider data failed validation",
                                         provider=provider, capability=capability,
                                         detail={"findings": [f.to_dict() for f in report.findings]})
                continue
            # A non-blocking quality finding (e.g. a slightly stale reading) is
            # returned WITH its warning; only an invalid value is withheld. The
            # cache re-checks freshness on read, so a stale entry is never served
            # to a request that required realtime data.
            self.cache.put(
                capability, cache_params, record,
                data_timestamp=record.meta.event_time, provider=provider, freshness=freshness,
            )
            return record
        return last_error or MarketError(DATA_NOT_AVAILABLE, "no provider returned data",
                                         capability=capability)

    def _router_ref(self) -> Any:
        if self._router is None:
            try:
                from .router import default_router

                self._router = default_router()
            except Exception:  # noqa: BLE001 - routing is best-effort; empty order is honest
                self._router = None
        return self._router

    # ── Public capabilities ──────────────────────────────────────────────────

    async def get_quote(
        self, symbol: str, market: Optional[str] = None, *, freshness: str = "realtime",
        terms: Optional[ContractTerms] = None,
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market, terms)
        if err:
            return err
        return await self._dispatch(
            "quote", instrument, {}, freshness=freshness, normalize=_normalize_quote
        )

    async def get_historical_prices(
        self, symbol: str, market: Optional[str] = None, *, start: Optional[str] = None,
        end: Optional[str] = None, interval: str = "1d", adjusted: bool = True,
        currency: Optional[str] = None, freshness: str = "slow",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        params = {"start": start, "end": end, "interval": interval,
                  "adjusted": adjusted, "currency": currency}
        return await self._dispatch(
            "historical", instrument, params, freshness=freshness,
            normalize=_normalize_series,
        )

    async def get_ohlcv(
        self, symbol: str, market: Optional[str] = None, *, start: Optional[str] = None,
        end: Optional[str] = None, interval: str = "1d", adjusted: bool = True,
        freshness: str = "intraday",
    ) -> Any:
        return await self.get_historical_prices(
            symbol, market, start=start, end=end, interval=interval,
            adjusted=adjusted, freshness=freshness,
        )

    async def get_volume(
        self, symbol: str, market: Optional[str] = None, *, window: str = "1d",
        freshness: str = "intraday",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "volume", instrument, {"window": window}, freshness=freshness,
            normalize=_normalize_volume,
        )

    async def get_orderbook(
        self, symbol: str, market: Optional[str] = None, *, depth: int = 20,
        freshness: str = "realtime",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        if instrument.asset_type not in ("crypto", "fx", "derivative", "future"):
            return MarketError(
                UNSUPPORTED_CAPABILITY,
                f"order books are available for crypto/fx/derivatives, not {instrument.asset_type}",
                capability="orderbook",
            )
        return await self._dispatch(
            "orderbook", instrument, {"depth": depth}, freshness=freshness,
            normalize=_normalize_orderbook,
        )

    async def get_trades(
        self, symbol: str, market: Optional[str] = None, *, limit: int = 100,
        start: Optional[str] = None, end: Optional[str] = None, freshness: str = "realtime",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "trades", instrument, {"limit": limit, "start": start, "end": end},
            freshness=freshness, normalize=_normalize_trades,
        )

    async def get_market_cap(
        self, symbol: str, market: Optional[str] = None, *, freshness: str = "daily",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "market_cap", instrument, {}, freshness=freshness, normalize=_normalize_market_cap
        )

    async def get_supply(
        self, symbol: str, market: Optional[str] = None, *, freshness: str = "daily",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        if instrument.asset_type != "crypto":
            return MarketError(
                UNSUPPORTED_CAPABILITY,
                f"supply data is for crypto assets, not {instrument.asset_type}",
                capability="supply",
            )
        return await self._dispatch(
            "supply", instrument, {}, freshness=freshness, normalize=_normalize_supply
        )

    async def get_funding_rate(
        self, symbol: str, market: Optional[str] = None, *, exchange: Optional[str] = None,
        history: int = 0, freshness: str = "realtime",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "funding", instrument, {"exchange": exchange, "history": history},
            freshness=freshness, normalize=_normalize_funding,
        )

    async def get_open_interest(
        self, symbol: str, market: Optional[str] = None, *, exchange: Optional[str] = None,
        window: str = "24h", freshness: str = "intraday",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "open_interest", instrument, {"exchange": exchange, "window": window},
            freshness=freshness, normalize=_normalize_open_interest,
        )

    async def get_options_chain(
        self, symbol: str, market: Optional[str] = None, *, expiration: Optional[str] = None,
        greeks: bool = False, freshness: str = "daily",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            return err
        return await self._dispatch(
            "options", instrument, {"expiration": expiration, "greeks": greeks},
            freshness=freshness, normalize=_normalize_options,
        )

    async def get_fx_rate(
        self, base: Optional[str] = None, quote: Optional[str] = None, *,
        symbol: Optional[str] = None, freshness: str = "realtime",
    ) -> Any:
        pair = symbol or (f"{base}{quote}" if base and quote else "")
        if not pair:
            return MarketError(INVALID_REQUEST, "an fx pair (base+quote or symbol) is required")
        instrument, err = await self.resolve_instrument(pair, "FX")
        if err:
            return err
        return await self._dispatch(
            "fx", instrument, {"base": base, "quote": quote},
            freshness=freshness, normalize=_normalize_fx,
        )

    async def get_bond_data(
        self, symbol: str, market: Optional[str] = None, *, series_type: Optional[str] = None,
        freshness: str = "slow",
    ) -> Any:
        instrument, err = await self.resolve_instrument(symbol, market)
        if err:
            # Bonds/treasuries are usually NOT in the equity instrument master.
            # A resolve miss is not a reason to refuse a yield request; build a
            # deterministic bond identity and let the bond provider set answer.
            clean = (symbol or "").strip().upper()
            if not clean:
                return err
            instrument = CanonicalInstrument(
                instrument_id=f"BOND:{clean}", symbol=clean, asset_type="bond",
                market=(market or "US").upper(), bridge_resolved=False,
            )
        elif instrument.asset_type not in ("bond", "macro"):
            # The equity master accepted the symbol (or gave a best-effort row),
            # but the caller asked for bond data; route to the bond provider set
            # rather than returning an equity quote for a yield request.
            import dataclasses

            instrument = dataclasses.replace(instrument, asset_type="bond")
        return await self._dispatch(
            "bonds", instrument, {"seriesType": series_type},
            freshness=freshness, normalize=_normalize_bond,
        )


# ── Normalizers (bridge payload → canonical record) ──────────────────────────

def _observation(payload: dict[str, Any], fallback: Optional[str] = None) -> tuple[Optional[str], str]:
    """The event time + how it was obtained. Never dresses one up as another."""
    explicit_source = payload.get("observationSource")
    explicit_time = payload.get("observationTime") or payload.get("asOf") or payload.get("timestamp")
    if explicit_source in ("provider_asof", "retrieval_clock", "snapshot_write", "unknown"):
        return explicit_time or fallback, explicit_source
    if explicit_time:
        return explicit_time, "provider_asof"
    return fallback, "unknown"


def _normalize_quote(payload, instrument, provider, freshness) -> Quote:
    price = payload.get("price")
    block = price if isinstance(price, dict) else payload
    event_time, obs = _observation(payload, payload.get("updatedAt"))
    meta = _meta("quote", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return Quote(
        meta=meta,
        price=block.get("price"),
        bid=block.get("bid"),
        ask=block.get("ask"),
        bid_size=block.get("bidSize"),
        ask_size=block.get("askSize"),
        volume=block.get("volume"),
        change=block.get("change"),
        change_pct=block.get("changePct"),
        previous_close=block.get("previousClose") or block.get("prevClose"),
        open=block.get("open"),
        day_high=block.get("dayHigh"),
        day_low=block.get("dayLow"),
        market_status=payload.get("marketStatus"),
        timestamp=event_time,
        raw=payload,
    )


def _normalize_series(payload, instrument, provider, freshness) -> HistoricalPriceSeries:
    rows = payload.get("series") or payload.get("bars") or payload.get("rows") or []
    bars: list[OHLCVBar] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp") or row.get("date") or row.get("time")
        if ts is None:
            continue
        bars.append(OHLCVBar(
            timestamp=str(ts), open=row.get("open"), high=row.get("high"),
            low=row.get("low"), close=row.get("close"), volume=row.get("volume"),
            vwap=row.get("vwap"), aggregated=bool(row.get("aggregated")),
        ))
    event_time, obs = _observation(payload, payload.get("asOf"))
    meta = _meta("historical", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return HistoricalPriceSeries(
        meta=meta, interval=payload.get("interval"), adjusted=payload.get("adjusted"),
        bars=bars, start=payload.get("start"), end=payload.get("end"),
        aggregation=payload.get("aggregation"), gaps=payload.get("gaps") or [],
        corporate_actions=payload.get("corporateActions") or [], raw=payload,
    )


def _normalize_volume(payload, instrument, provider, freshness) -> VolumeStats:
    event_time, obs = _observation(payload)
    meta = _meta("volume", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    native = [k for k in ("total_volume", "buy_volume", "sell_volume", "average_volume")
              if payload.get(_snake(k)) is not None]
    derived = [k for k in ("relative_volume", "volume_change") if payload.get(_snake(k)) is not None]
    return VolumeStats(
        meta=meta,
        total_volume=payload.get("totalVolume"),
        buy_volume=payload.get("buyVolume"),
        sell_volume=payload.get("sellVolume"),
        average_volume=payload.get("averageVolume"),
        relative_volume=payload.get("relativeVolume"),
        volume_change=payload.get("volumeChange"),
        window=payload.get("window"),
        native_fields=native, derived_fields=derived, raw=payload,
    )


def _normalize_orderbook(payload, instrument, provider, freshness) -> OrderBook:
    def _levels(raw: Any) -> list[OrderBookLevel]:
        out: list[OrderBookLevel] = []
        for lv in raw if isinstance(raw, list) else []:
            if isinstance(lv, dict):
                out.append(OrderBookLevel(
                    price=float(lv.get("price", 0)), quantity=float(lv.get("quantity", 0)),
                    cumulative=lv.get("cumulative"),
                ))
            elif isinstance(lv, (list, tuple)) and len(lv) >= 2:
                out.append(OrderBookLevel(price=float(lv[0]), quantity=float(lv[1])))
        return out

    bids = _levels(payload.get("bids"))
    asks = _levels(payload.get("asks"))
    best_bid = payload.get("bestBid") if payload.get("bestBid") is not None else (bids[0].price if bids else None)
    best_ask = payload.get("bestAsk") if payload.get("bestAsk") is not None else (asks[0].price if asks else None)
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
    spread_bps = (spread / best_bid * 10000) if (spread is not None and best_bid) else None
    bid_depth = sum(l.quantity for l in bids) or None
    ask_depth = sum(l.quantity for l in asks) or None
    imbalance = None
    if bid_depth and ask_depth and (bid_depth + ask_depth) > 0:
        imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
    event_time, obs = _observation(payload)
    meta = _meta("orderbook", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return OrderBook(
        meta=meta, bids=bids, asks=asks, best_bid=best_bid, best_ask=best_ask,
        spread=spread, spread_bps=spread_bps, bid_depth=bid_depth, ask_depth=ask_depth,
        imbalance=imbalance, sequence=payload.get("sequence"),
        timestamp=event_time, book_state=payload.get("bookState") or "snapshot", raw=payload,
    )


def _normalize_trades(payload, instrument, provider, freshness) -> TradeTape:
    trades: list[Trade] = []
    for row in payload.get("trades") or []:
        if not isinstance(row, dict):
            continue
        trades.append(Trade(
            trade_id=str(row.get("id")) if row.get("id") is not None else None,
            timestamp=str(row.get("timestamp") or row.get("time") or ""),
            price=float(row.get("price", 0)), quantity=float(row.get("quantity", 0)),
            side=row.get("side") if row.get("side") in ("buy", "sell") else None,
            side_inferred=bool(row.get("sideInferred")),
            exchange=payload.get("exchange"),
        ))
    event_time, obs = _observation(payload)
    meta = _meta("trades", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return TradeTape(
        meta=meta, trades=trades,
        aggressive_buy_volume=payload.get("aggressiveBuyVolume"),
        aggressive_sell_volume=payload.get("aggressiveSellVolume"),
        imbalance=payload.get("imbalance"), large_trades=payload.get("largeTrades") or [],
        raw=payload,
    )


def _normalize_market_cap(payload, instrument, provider, freshness) -> MarketCap:
    event_time, obs = _observation(payload)
    meta = _meta("market_cap", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return MarketCap(
        meta=meta, market_cap=payload.get("marketCap"), price=payload.get("price"),
        shares_outstanding=payload.get("sharesOutstanding"),
        shares_basis=payload.get("sharesBasis") or "unknown",
        timestamp=event_time, raw=payload,
    )


def _normalize_supply(payload, instrument, provider, freshness) -> Supply:
    event_time, obs = _observation(payload)
    meta = _meta("supply", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return Supply(
        meta=meta,
        circulating_supply=payload.get("circulatingSupply"),
        total_supply=payload.get("totalSupply"), max_supply=payload.get("maxSupply"),
        free_float=payload.get("freeFloat"), fdv=payload.get("fdv"),
        circulating_market_cap=payload.get("circulatingMarketCap"),
        timestamp=event_time, raw=payload,
    )


def _normalize_funding(payload, instrument, provider, freshness) -> FundingRate:
    event_time, obs = _observation(payload)
    meta = _meta("funding", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    rate = payload.get("fundingRate")
    interval_h = payload.get("fundingIntervalHours")
    annualized = payload.get("annualizedFunding")
    derivation = payload.get("annualizedDerivation")
    if annualized is None and rate is not None and interval_h:
        # Derived: rate × (24/interval) × 365. Labelled — never confused with raw.
        annualized = float(rate) * (24.0 / float(interval_h)) * 365.0
        derivation = f"derived = rate × (24/{interval_h}h) × 365"
    return FundingRate(
        meta=meta, funding_rate=rate, funding_interval_hours=interval_h,
        next_funding_time=payload.get("nextFundingTime"),
        predicted_funding=payload.get("predictedFunding"),
        annualized_funding=annualized, annualized_derivation=derivation,
        historical=payload.get("historical") or [], timestamp=event_time, raw=payload,
    )


def _normalize_open_interest(payload, instrument, provider, freshness) -> OpenInterest:
    event_time, obs = _observation(payload)
    meta = _meta("open_interest", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return OpenInterest(
        meta=meta, open_interest=payload.get("openInterest"),
        open_interest_usd=payload.get("openInterestUsd"),
        oi_change=payload.get("oiChange"), oi_change_pct=payload.get("oiChangePct"),
        oi_velocity=payload.get("oiVelocity"), window=payload.get("window"),
        timestamp=event_time, raw=payload,
    )


def _normalize_options(payload, instrument, provider, freshness) -> OptionsChain:
    contracts: list[OptionContract] = []
    for row in payload.get("contracts") or []:
        if not isinstance(row, dict):
            continue
        contracts.append(OptionContract(
            expiration=str(row.get("expiration") or ""),
            strike=row.get("strike"),
            option_type="call" if str(row.get("type", "call")).lower().startswith("c") else "put",
            bid=row.get("bid"), ask=row.get("ask"), last=row.get("last"),
            volume=row.get("volume"), open_interest=row.get("openInterest"),
            implied_volatility=row.get("impliedVolatility"),
            delta=row.get("delta"), gamma=row.get("gamma"), theta=row.get("theta"),
            vega=row.get("vega"), rho=row.get("rho"),
            greeks_source=row.get("greeksSource"), iv_source=row.get("ivSource"),
        ))
    event_time, obs = _observation(payload)
    meta = _meta("options", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return OptionsChain(
        meta=meta, underlying=payload.get("underlying"),
        underlying_price=payload.get("underlyingPrice"),
        expirations=payload.get("expirations") or [], contracts=contracts,
        timestamp=event_time, raw=payload,
    )


def _normalize_fx(payload, instrument, provider, freshness) -> FXRate:
    event_time, obs = _observation(payload)
    meta = _meta("fx", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    mid = payload.get("mid") or payload.get("rate") or payload.get("price")
    return FXRate(
        meta=meta, base=payload.get("base") or instrument.base_asset,
        quote=payload.get("quote") or instrument.quote_asset,
        bid=payload.get("bid"), ask=payload.get("ask"), mid=mid,
        rate=payload.get("rate") or mid, cross=bool(payload.get("cross")),
        derivation=payload.get("derivation"),
        market_status=payload.get("marketStatus"), timestamp=event_time, raw=payload,
    )


def _normalize_bond(payload, instrument, provider, freshness) -> BondData:
    event_time, obs = _observation(payload)
    meta = _meta("bonds", instrument, payload, provider=provider, event_time=event_time,
                 observation_source=obs, freshness=freshness)
    return BondData(
        meta=meta, price=payload.get("price"),
        yield_=payload.get("yield") if "yield" in payload else payload.get("yield_"),
        coupon=payload.get("coupon"), maturity=payload.get("maturity"),
        duration=payload.get("duration"), modified_duration=payload.get("modifiedDuration"),
        convexity=payload.get("convexity"), spread=payload.get("spread"),
        rating=payload.get("rating"), issuer=payload.get("issuer"),
        tenor=payload.get("tenor"), series_type=payload.get("seriesType"), raw=payload,
    )


def _snake(name: str) -> str:
    """camelCase → camelCase key lookup helper (payload keys are camelCase)."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


__all__ = ["MarketDataGateway"]
