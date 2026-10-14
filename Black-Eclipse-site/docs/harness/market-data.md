---
title: Market Data Layer
status: Current
last-verified: 2026-10-13
---

# Market Data Layer

**Who this is for:** anyone asking "where does a market price come from, and why
did the agent answer the way it did?"

The Market Data Layer gives Eclipse agents first-class, provider-agnostic market
data. An agent asks for a *capability* (`get_quote`, `get_orderbook`, …) and the
gateway decides which provider answers. No agent ever names Yahoo, Binance or
CoinGecko.

## Architecture

```
Eclipse Agent
  → Tool Registry                         python/harness/market/tools.py
  → Market Data Tools                     python/harness/market/gateway.py
  → Market Data Gateway (routing/quality) python/harness/market/router.py
  → Provider Router                       python/harness/market/providers.py
  → Provider Adapters (TS adapters)       src/lib/harness/market/providers/*
  → External APIs / WebSockets
  → Normalization                         python/harness/market/gateway.py (_normalize_*)
  → Data Quality                          python/harness/market/quality.py
  → Cache / Storage                       python/harness/market/{cache,store}.py
  → Evidence / Provenance                 python/harness/market/provenance.py
  → Agent
```

The **retrieval layer** (`python/harness/retrieval/`) remains the general
provider-agnostic path for quotes/statements/news. The Market Data Layer is the
deeper, market-specific surface (order books, trades, funding, options, FX,
bonds, streaming). Both share the ONE read-only TS bridge transport and the ONE
`agent-memory.db` connection; there is no second HTTP client or database.

### Why the adapters live in TypeScript

The app's market-data engine (scraper chain, yfinance bridge, Yahoo chart,
crypto connector, SEC, economics) already lives in Next.js and is the single
place secrets are resolved (`src/lib/provider-keys.ts`) and outbound calls are
hardened (`src/lib/connectors/security.ts#safeGet`, SSRF-guarded). The Python
runtime owns routing/quality/provenance/streaming and reaches providers through
one bridge capability, `market_data`. This keeps ONE transport, ONE secret
store, and ONE instrument master (the bridge's `market_snapshot`).

## Tools

All fourteen tools are registered by `register_market_tools` and exposed on the
`eclipse-agent` allowlist. Each returns a text summary + a structured `data`
dict and records provenance into the run's source collector.

| Tool | Capability | Notes |
|---|---|---|
| `get_quote` | quote | freshness-aware; never serves stale as realtime |
| `get_historical_prices` | historical | adjusted series; never web-sourced |
| `get_ohlcv` | ohlcv | native bars; aggregation labelled |
| `get_volume` | volume | native vs derived fields labelled |
| `get_orderbook` | orderbook | crypto/fx/derivatives only |
| `get_trades` | trades | side only when provider-supplied |
| `get_market_cap` | market_cap | share basis stated |
| `get_supply` | supply | crypto circulating/total/max/FDV |
| `get_funding_rate` | funding | annualized is labelled derived |
| `get_open_interest` | open_interest | |
| `get_options_chain` | options | missing Greek = unavailable, never 0 |
| `get_fx_rate` | fx | cross conversion labelled |
| `get_bond_data` | bonds | Treasury yields via FRED |
| `stream_market_data` | stream | real WebSocket, action=sample/subscribe/unsubscribe/snapshot |

## Providers

Declared in `python/harness/market/providers.py`; runnable adapters in
`src/lib/harness/market/providers/`. A provider is `implemented=True` only when
an adapter exists; catalogued-only providers are recorded honestly.

| Provider | Adapter | Capabilities | Key |
|---|---|---|---|
| `yahoo` | `providers/yahoo.ts` | quote, historical, ohlcv, volume, market_cap, options, fx | keyless |
| `binance` | `providers/binance.ts` | quote, ohlcv, historical, orderbook, trades, funding, open_interest | keyless |
| `polygon` | `providers/polygon.ts` | quote, orderbook (NBBO), trades, historical, ohlcv | `POLYGON_API_KEY` |
| `finnhub` | `providers/finnhub.ts` | quote, historical, ohlcv (+ real-time trades over WS) | `FINNHUB_API_KEY` |
| `coingecko` | `providers/coingecko.ts` | quote, market_cap, supply | `COINGECKO_API_KEY` (optional) |
| `stooq` | `providers/stooq.ts` | historical, ohlcv, quote | keyless |
| `treasury` | `providers/treasury.ts` | bonds (Treasury tenors + ICE BofA corporate indices) | `FRED_API_KEY` (optional) |
| `fx` (ECB) | `providers/ecb-fx.ts` | fx | keyless |

Equity **order books** (top-of-book NBBO) and **trades** are served by the keyed
Polygon/Finnhub adapters; **equity streaming** is served by the keyed Finnhub
WebSocket. Without the relevant key those routes report `AUTHENTICATION_FAILED`
honestly (never fake data) and the gateway falls through the provider order.

Provider credentials come from `resolveProviderKey` (env → encrypted vault).
The Python runtime never holds a key for REST (the TS adapter does). For a KEYED
*stream*, the socket URL/token is resolved by the `market_stream_config` bridge
capability and handed to the authenticated runtime — the same trust boundary as
`mcp_secret_resolve`; the token is never persisted or logged by Python.

## Routing, fallback, health

`ProviderRouter` (`router.py`) selects providers by capability + asset class +
configured priority (`config.DEFAULT_PRIORITY`, overridable by env), skipping
operator-disabled providers and any provider whose circuit breaker is open. The
breaker is `mcp/circuit.CircuitBreaker` (reused verbatim). The gateway tries up
to `HARNESS_MARKET_MAX_PROVIDERS` providers in order; a provider-level failure
falls through to the next. Health counters are mirrored to
`MarketProviderHealth`.

Because routing is keyed on asset class, the asset class the identity carries is
**load-bearing**: a null/`unknown` asset class yields no provider order at all
and surfaces as `no provider supports '<capability>' for unknown`. The bridge's
`market_snapshot` therefore returns the RESOLVED coarse asset class
(`identity.assetClass`, derived from `securityType`/`assetClass` via
`toAssetClass`), never the raw vault column — most JDdS equity rows store
`assetClass = null` with only a `securityType` (e.g. `"Stock"`). The Python
`_asset_type_from` fallback mirrors this: a recognised non-empty `securityType`
with no asset class classifies as that type (or `equity`), and only a fully
unclassified request (no asset class AND no security type) is `unknown`.

Errors use the closed vocabulary in `errors.py`
(`PROVIDER_UNAVAILABLE`, `RATE_LIMITED`, `AUTHENTICATION_FAILED`,
`SYMBOL_NOT_FOUND`, `DATA_NOT_AVAILABLE`, `DATA_STALE`, `DATA_CONFLICT`,
`INVALID_INTERVAL`, `INVALID_DATE_RANGE`, `STREAM_DISCONNECTED`,
`STREAM_RESYNC_REQUIRED`, `UNSUPPORTED_CAPABILITY`, `INVALID_REQUEST`,
`CONFIGURATION_ERROR`).

## Data quality

`quality.py` evaluates every record: OHLC consistency, negative/crossed values,
duplicate timestamps, gaps, >50% outlier bars, freshness vs the requested class.
An **invalid** finding withholds the value (the gateway tries the next provider);
a **warning** is surfaced on `meta.warnings`. The engine never repairs silently.

## Freshness & caching

**Requested windows.** A history request that names `start`/`end` is honored
end-to-end: the Yahoo adapter sends the window as `period1`/`period2` (a bare
date is inclusive, padded to that day's last second) and picks the smallest
provider `range` that COVERS it for the batched bridge, whose rows are then
filtered to the window — a Dec-2025 window can no longer return the whole
history and get head/tail truncated. The retrieval authority judges a SERIES by
COVERAGE of the requested window (7-day cadence otherwise), not by the 6h
bar-timestamp ceiling every daily series fails after the last close.

**Crypto identity & volume.** A bare base (`BTC`, `SOL`) classifies as the
USD-quoted spot pair in BOTH classifiers (TS `instrument-identity`, Python
`retrieval/structured`), so it routes to the crypto source and never to an
equity/vault read — bare `BTC` on Yahoo is the Grayscale mini-trust ETF, which
is exactly how a wrong price used to appear. Binance's two 24h volumes travel
explicitly labelled: `volume` = quote notional, `volumeBase` = base-asset units.

`cache.py` is a per-capability in-process TTL cache with an explicit-freshness
guard: a `realtime` request is never served a value older than the realtime
ceiling, even if the write TTL has not elapsed. In-flight requests are
deduplicated. There is no Redis (single-node, zero-config).

## Rate limiting — measured, not assumed

`ratelimit.py` paces providers on the DECLARED limit **and** the provider's REAL
quota reported in its responses:

  * declared `requests_per_minute` / concurrency are enforced with a sliding
    window and an in-flight cap;
  * a provider's live quota is OBSERVED from response headers (Binance
    `X-MBX-USED-WEIGHT-1M`, generic `x-ratelimit-*`, `Retry-After`) and the
    **effective** limit is the stricter of declared and observed;
  * a 429 opens a cooldown for that provider;
  * per-provider call counts and latency are tracked, and declared-vs-observed is
    surfaced (never conflated) in the operator console.

Headers are captured in TS (`connectors/security.ts` now returns response
headers; `market/rate-limit.ts` parses them per provider) and fed back through
the bridge payload's `rateLimit` block into `MarketRateLimiter.observe`.

## Observability & admin (console)

The Market Data Layer has an operator console rendered inside Settings › Data &
providers (composed with the Financial Data Gateway panel — no parallel admin):
providers + key presence, per-provider health, **declared-vs-observed rate
limits** with latency, the real-time stream state/subscriptions/metrics, the
cache stats, and recent data-quality findings. It reads the SAME Python state the
agent tools use, through the front-door proxy.

Routes (operator-gated): `GET /market/providers`, `GET /market/health` (cache,
metrics, provider metrics + rate limits), `GET /market/quality`,
`GET /market/stream`, `POST /market/stream/subscribe`,
`POST /market/stream/unsubscribe`. The front door proxies them at
`/api/harness/market/*` (`src/app/api/harness/market/[...path]/route.ts`), merging
credential presence for `/market/providers`. Client: `src/lib/harness/market-client.ts`;
UI: `src/components/screens/market-data-console.tsx`.

## Streaming

`streaming.py` is a real WebSocket architecture: one connection manager per
provider (Binance crypto, keyless; Finnhub equities, keyed), subscriptions
multiplexed → normalizer → sequence validation + dedup → bounded event bus →
subscribers.
Durability is explicit: subscribe/unsubscribe, multiple symbols/event types,
heartbeat, **jittered** exponential-backoff reconnect, ordered resubscription,
sequence-gap detection (`book_state="resync_required"`), deduplication (bounded
LRU), backpressure (oldest event dropped), a **silence watchdog** that reconnects
a connected-but-silent socket, an optional reconnect cap (parks honestly at
`state="backoff"`; a later subscribe resets it), and graceful shutdown. It is
covered by deterministic reconnect/soak tests and an opt-in live soak
(`BLACK_ECLIPSE_MARKET_LIVE=1`).

## Provenance & point-in-time

`provenance.py` converts a record into the retrieval layer's `EvidenceItem` /
`NormalizedFinancialObject`, so market data flows into the SAME Evidence &
Research Engine (run `source_sink`, `finance_facts` analysis). `knows_at` /
`filter_point_in_time` fail closed: a record with no usable timestamp is not
admissible at a cutoff.

## Storage

`store.py` owns four tables on `agent-memory.db`: `MarketInstrument`,
`MarketSnapshot`, `MarketQualityEvent`, `MarketProviderHealth`. Large history is
not duplicated — a dedicated time-series backend can be added later without
changing the tool layer.

## Derived analytics

`analytics.py` computes ATR/RSI/MACD/VWAP/beta/correlation/VaR/Sharpe/Sortino/
drawdown/volume-profile/orderbook-imbalance/funding-zscore/OI-change above
normalized data, delegating to `research/calculations.py` where a formula already
exists. Every result is marked `derived=True`.

**Option Greeks** (`greeks.py`): Yahoo supplies implied volatility but no Greeks.
When `get_options_chain(greeks=True)` is called, Eclipse CALCULATES delta, gamma,
theta, vega and rho with Black-Scholes from the provider IV and the chain's
underlying price, labelled `greeks_source="calculated(black-scholes, no-dividend)"`.
A provider-supplied Greek always wins; a missing input keeps `None` (reported as
unavailable, never zero). Assumptions are documented (European, no dividends,
constant `r`; `HARNESS_MARKET_RISK_FREE`, default 4%).

**Bond analytics** (`bondmath.py`): Macaulay/modified duration and convexity are
computed from coupon, yield and time-to-maturity when a provider supplies them;
a provider figure always wins and a missing input stays `None`.

## Configuration

Env vars (safe defaults; no source edit required):
`HARNESS_MARKET_MAX_PROVIDERS`, `HARNESS_MARKET_TIMEOUT_MS`,
`HARNESS_MARKET_MAX_RETRIES`, `HARNESS_MARKET_BACKOFF_BASE_S`,
`HARNESS_MARKET_BACKOFF_MAX_S`, `HARNESS_MARKET_BREAKER_THRESHOLD`,
`HARNESS_MARKET_BREAKER_RESET_S`, `HARNESS_MARKET_CACHE`,
`HARNESS_MARKET_CONFLICT_TOLERANCE`, `HARNESS_MARKET_REALTIME_MAX_AGE_S`,
`HARNESS_MARKET_RISK_FREE`,
`HARNESS_MARKET_STREAMING`, `HARNESS_MARKET_STREAM_MAX_SUBS`,
`HARNESS_MARKET_STREAM_QUEUE`, `HARNESS_MARKET_STREAM_RECONNECT_MAX_S`,
`HARNESS_MARKET_STREAM_BACKOFF_BASE_S`, `HARNESS_MARKET_STREAM_JITTER`,
`HARNESS_MARKET_STREAM_STALE_S`, `HARNESS_MARKET_STREAM_MAX_RECONNECTS`,
`HARNESS_MARKET_DISABLED_PROVIDERS` (comma-separated).

## Testing

`python/tests/test_market_unit.py`, `test_market_gateway.py`,
`test_market_streaming.py`, `test_market_ratelimit.py`,
`test_market_derivatives.py` cover contracts, instruments, quality, cache,
routing, pacing (declared + observed quota), failure handling, streaming
lifecycle **and durability/soak**, Black-Scholes Greeks, bond analytics, the
keyed streaming normalizers, and full tool invocation through the real registry.
`test_market_live.py` is an opt-in live REST/WS soak
(`BLACK_ECLIPSE_MARKET_LIVE=1`). TS: `src/lib/harness/market/{bridge,rate-limit,keyed-providers}.test.ts`.
All offline tests fake provider calls; no network.

## Observation freshness (web price surfaces)

The Next.js price surfaces (`/api/price-history`, `/api/quote`) attach an
observation envelope from the ONE shared module
`src/lib/chart/observation-freshness.ts`: `observationTime`, `retrievedAt`,
`freshness` and `stale`. Freshness is interval-aware (`1m` decays in minutes,
`1d` is current for the session it belongs to), and an unknown observation time
is `unknown`/stale — never `live`. The `/api/price-history` JDDS snapshot
fallback is dated from the row's real `updatedAt`, never `now`, so a stale close
cannot be drawn under today's date; the chart header/footer render such a series
amber and say "stale · as of <date>" instead of "live". This is symbol- and
market-agnostic — every instrument on both endpoints flows through it; there is
no per-ticker special case.

## Known limitations (honest)

- **Equity order books are top-of-book only** (Polygon NBBO) and require a keyed
  provider; there is no free depth-of-book for US equities. Without a key the
  route reports `AUTHENTICATION_FAILED`, not fake depth.
- **Option Greeks are model-derived** (Black-Scholes, no dividends) unless the
  provider supplies them; labelled `calculated`, never presented as provider data.
- **Streaming**: Binance (crypto, keyless) and Finnhub (equities, keyed) are
  implemented; reconnect/durability is covered by deterministic soak tests and an
  opt-in live soak.
- **Corporate bonds**: keyless *index* yields/spreads (ICE BofA via FRED) are
  supported; a per-ISSUE corporate bond (CUSIP) requires a premium vendor and is
  reported honestly as unavailable when no keyed provider supplies it.
- **Polygon/Finnhub are keyed**: absent a credential their routes report
  `AUTHENTICATION_FAILED` (never fake data).
