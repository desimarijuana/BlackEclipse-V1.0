---
title: Market Data Layer
status: Current
last-verified: 2026-10-07
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
| `coingecko` | `providers/coingecko.ts` | quote, market_cap, supply | `COINGECKO_API_KEY` (optional) |
| `stooq` | `providers/stooq.ts` | historical, ohlcv, quote | keyless |
| `treasury` | `providers/treasury.ts` | bonds | `FRED_API_KEY` (optional) |
| `fx` (ECB) | `providers/ecb-fx.ts` | fx | keyless |
| `polygon`, `finnhub` | — | declared, not implemented | vault entries exist |

Provider credentials come from `resolveProviderKey` (env → encrypted vault).
The Python runtime never holds a key; it receives only normalized payloads.

## Routing, fallback, health

`ProviderRouter` (`router.py`) selects providers by capability + asset class +
configured priority (`config.DEFAULT_PRIORITY`, overridable by env), skipping
operator-disabled providers and any provider whose circuit breaker is open. The
breaker is `mcp/circuit.CircuitBreaker` (reused verbatim). The gateway tries up
to `HARNESS_MARKET_MAX_PROVIDERS` providers in order; a provider-level failure
falls through to the next. Health counters are mirrored to
`MarketProviderHealth`.

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

`streaming.py` is a real WebSocket architecture (Binance combined stream):
connection manager (one socket per provider, subscriptions multiplexed) →
normalizer → sequence validation + dedup → bounded event bus → subscribers.
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

## Observability & admin

Gateway metrics (`requests`, `cacheHits`, `providerCalls`, `failures`,
`conflicts`, `fallbacks`), router health and cache stats are exposed at
operator-gated routes: `GET /market/providers`, `GET /market/health`,
`GET /market/quality`, `GET /market/stream`, `POST /market/stream/subscribe`,
`POST /market/stream/unsubscribe` (`python/harness/routers/market.py`).

## Configuration

Env vars (safe defaults; no source edit required):
`HARNESS_MARKET_MAX_PROVIDERS`, `HARNESS_MARKET_TIMEOUT_MS`,
`HARNESS_MARKET_MAX_RETRIES`, `HARNESS_MARKET_BACKOFF_BASE_S`,
`HARNESS_MARKET_BACKOFF_MAX_S`, `HARNESS_MARKET_BREAKER_THRESHOLD`,
`HARNESS_MARKET_BREAKER_RESET_S`, `HARNESS_MARKET_CACHE`,
`HARNESS_MARKET_CONFLICT_TOLERANCE`, `HARNESS_MARKET_REALTIME_MAX_AGE_S`,
`HARNESS_MARKET_STREAMING`, `HARNESS_MARKET_STREAM_MAX_SUBS`,
`HARNESS_MARKET_STREAM_QUEUE`, `HARNESS_MARKET_STREAM_RECONNECT_MAX_S`,
`HARNESS_MARKET_STREAM_BACKOFF_BASE_S`, `HARNESS_MARKET_STREAM_JITTER`,
`HARNESS_MARKET_STREAM_STALE_S`, `HARNESS_MARKET_STREAM_MAX_RECONNECTS`,
`HARNESS_MARKET_DISABLED_PROVIDERS` (comma-separated).

## Testing

`python/tests/test_market_unit.py`, `test_market_gateway.py`,
`test_market_streaming.py`, `test_market_ratelimit.py` cover contracts,
instruments, quality, cache, routing, pacing (declared + observed quota),
failure handling, streaming lifecycle **and durability/soak** (many reconnect
cycles, bounded dedup memory, silence watchdog), and full tool invocation through
the real registry. `test_market_live.py` is an opt-in live REST/WS soak
(`BLACK_ECLIPSE_MARKET_LIVE=1`). `src/lib/harness/market/bridge.test.ts` and
`rate-limit.test.ts` cover the TS adapter dispatcher and header parsing. All
offline tests fake provider calls; no network.

## Known limitations (honest)

- **Equity order books / trades** are unavailable: Yahoo does not supply them and
  no equity venue adapter is implemented. The gateway returns
  `UNSUPPORTED_CAPABILITY` for an equity order book rather than a fake one.
- **Equity options Greeks** depend on the provider's `greeks=true` support; a
  missing Greek is `null`, never `0` — Eclipse does not yet compute them.
- **Streaming** implements Binance public streams; other streaming providers are
  declared but not implemented. Reconnect/durability is covered by deterministic
  soak tests; a live soak is opt-in (`BLACK_ECLIPSE_MARKET_LIVE=1`).
