---
title: Data Flow
status: Current
last-verified: 2026-09-18
---

# Data Flow

**Who this is for:** anyone asking "where does this number come from, and why is
it old?" This is the doc to read before debugging anything data-related.

## The one diagram to remember

```
   EXTERNAL SOURCES
   TradingView scanner · yfinance bridge · RSS feeds ·
   crypto APIs · macro providers · user API keys
              │
              ▼  (scheduled, in-process)
   ┌──────────────────────────────────────────────┐
   │  INGESTION — src/lib/scraper/, lib/news/      │
   │  upsert-only, idempotent, batched,             │
   │  timezone-aware (skips closed markets)         │
   └──────────────────────────────────────────────┘
              │
              ▼
   ┌──────────────────────────────────────────────┐
   │  JDDS — jdds.db (SQLite)                      │
   │  Assets · Prices · IndexQuote · NewsItem ·    │
   │  MacroSeries · research memory · journal       │
   └──────────────────────────────────────────────┘
              │
              ▼  (read-only, on request)
   ┌──────────────────────────────────────────────┐
   │  API ROUTES — src/app/api/**                  │
   │  query JDDS, shape a JSON response            │
   └──────────────────────────────────────────────┘
              │
        ┌─────┴─────┐
        ▼           ▼
   DataHub topics   direct fetches
   (dashboard)      (screens)
        │
        ▼
      SCREENS
```

The rule that follows from this: **screens never call a data provider.** If a
screen needs a number, it either reads JDDS through an API route, or subscribes
to a DataHub topic that wraps that route.

## Operator data sources (the connector tier)

Beyond the built-in scraper, the operator can connect their own REST API. That
path is a **separate tier**, not a replacement for the scraper chain:

```
Widget → DataHub topic → GET /api/data/[capability] → resolver
       → scraper | operator connector → real data | UNAVAILABLE
       → DataHub → Widget     (route-level demo fallbacks stay in their routes)
```

`GET /api/data/[capability]` resolves capability → connector server-side and
returns `{ ok, data, provenance, source, retrievedAt }`. DataHub passes
`provenance` through (it does not infer a tag for connectors); `CUSTOM` means the
row came from an operator data source.

Custom API responses are mapped into **`CustomDatasetRecord`**, never into
`Asset`/`Price`/`Candles`. `(datasetId, recordKey)` is unique, so re-importing
the same response upserts. Imports report `written` / `extracted` / `rejected` /
`deduped` rather than a bare success — a partially-imported response says so.

A pull may be **multi-value**: a parameter like `symbol=BTC,ETH,SOL` becomes one
request per value, capped at 25 with the overflow reported. Datasets with
`refreshEnabled` are re-pulled in the background on their own cron, which yields
to the scraper's whole-market jobs. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "The Universal Data Connector Layer"
and ADR-010.

## Fundamentals (the merging provider tier)

Fundamentals is a second, additive provider tier. Where the connector tier picks
one connector per capability, fundamentals MERGES complementary providers:

```
GET /api/fundamentals?symbol=AAPL&market=US
  → fundamentals.get()                     (src/lib/fundamentals/index.ts)
     → configuredProviders()  SEC → FMP → Yahoo (authority order)
     → buildSnapshot()        first provider with periods = primary statements,
                              others fill quote / valuation / earnings / ownership
     → normalize + compute    Eclipse schema + derived metrics + insights
  → FundamentalsCache (JDDS, @@unique([symbol, market]))  + in-memory map
  → FundamentalsSnapshot → Fundamentals UI
```

**Caching:** fresh (< 24h) served directly; stale served immediately with a
background refresh (stale-while-revalidate); > 7 days blocks. A provider outage
returns the stale snapshot, never a blank page. `FundamentalsCache.payload` is
the full UI-ready JSON document; `primarySource` records the statement provider.

**Sources:** SEC EDGAR (US, keyless, authoritative filings + XBRL), Yahoo
(yfinance bridge, global fallback), Financial Modeling Prep (optional key,
normalized fundamentals + estimates). Non-US markets skip SEC. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md) → "Fundamentals".

## Ingestion — how data gets into JDDS

Everything is an **upsert**, never a blind insert. Re-running an import updates
in place, because the schema enforces uniqueness:

- `Asset` — unique on `[marketId, symbol]`
- `Price` — one row per `assetId` (latest price only)
- `IndexQuote` — unique on `[marketId, symbol]`
- `NewsItem` — unique `dedupKey` (hash of url/headline)

### Price data

`src/lib/scraper/` is the engine. Key pieces:

- `price-scraper.ts` — `runPriceScraper`, `refreshMarketBatch`. Routes each
  market to the right fetcher.
- `fetchers/tradingview.ts` — whole-market scans. One request prices an entire
  market (~1s). This is the primary path and covers markets Yahoo misses.
- `fetchers/yfinance.ts` + `scripts/yfinance_bridge.py` — batched bridge for
  markets TradingView covers poorly. Optional Python dependency.
- `fetchers/http.ts`, `fetchers/browser.ts` (Playwright), `fetchers/scrapling.ts`,
  `fetchers/crypto.ts` — the fallback chain.
- `SourceHealth` records success/fail counts per strategy so the chain can learn
  which source is reliable and self-heal.
- `csv.ts` — CSV/API imports write `Price.source = 'csv'` instead of `'scraper'`.

**`Price.source` is the provenance field.** `'scraper'` = live scrape;
`'csv'` = imported. Use it to distinguish fresh from imported data.

### Universe data

- `universe-sync.ts` — scans TradingView markets, upserts new listings, and
  deactivates symbols that miss repeatedly. Runs daily so IPOs appear on their own.
- `scripts/import-*.js` — one-off universe seeders per market
  (`import-psx.js`, `import-india.js`, `import-china.js`, `import-japan.js`, …).

### News

`src/lib/news/ingest.ts` fetches ~55 RSS feeds, enriches each item (ticker guess
validated against the JDDS universe, sentiment via `src/lib/sentiment.ts`),
upserts with a `dedupKey`, and prunes items older than 14 days. `/api/news` then
reads the DB instead of hitting feeds per request.

### Macro

`src/lib/economics/` fetches macro series, caches them in `MacroSeries` as JSON
(`cacheKey` = source + params hash) so the Economics page loads from JDDS.

### Investor Eye world state

`src/lib/investor-eye/` is its own ingestion tier (ADR-011). Per cycle it runs
each configured `EventSource` (GDELT, USGS, the stored RSS corpus, NASA FIRMS)
through the shared `safeGet` transport, normalizes records into
`NormalizedEvent`s, clusters/dedupes them, then:

- upserts into `GeopoliticalEvent` on the unique `dedupKey` (idempotent),
- records one `SourceRun` per source (received/accepted/rejected + error),
- assembles markets from the **existing** `IndexQuote` + yfinance path,
- caches the assembled state (SWR, 3 min) and persists a last-known snapshot in
  `SystemConfig`.

FIRMS is the one source that aggregates *before* the event model: ~25,600 raw
single-pixel detections become ≤400 grid clusters (real detection count + summed
FRP), because the raw row count must never reach the database or the browser. A
fire cluster's country comes from `admin-boundaries.ts` (point-in-polygon against
the shipped Natural Earth GeoJSON), not a centroid guess.

Governance metadata (licence, commercial-use, attribution, rate limit) lives
alongside in `source-catalog.ts`; `/api/investor-eye/health` joins it onto the
`SourceRun` accounting for the Data Sources panel, and a test enforces that every
registered source has an entry.

A failing source is reported as `UNAVAILABLE` and the rest of the feed still
serves. `/api/investor-eye/state` returns the assembled payload; the client
reads it through DataHub topics. The world-state cron runs in-process from
`instrumentation.ts` and skips a tick while the scraper holds the write path.

## Background schedules (what makes data "current")

| Job | Default | Where | Notes |
|---|---|---|---|
| Price refresh | 15 min | `scraper/scheduler.ts` | Round-robin, 4 markets/tick, open markets only |
| Universe sync | daily | `scraper/scheduler.ts` | TradingView-covered markets |
| News ingest | 5 min | `news/ingest.ts` | Idempotent, retention-pruned |
| Boot warm-up | once | `scraper/scheduler.ts` | Production only unless `BE_WARMUP=1`; caps at 1000 rows/market |
| Alert poll | per-watch | `alerts/alertMonitor.ts` | Evaluates condition trees |
| Dataset refresh | per-dataset (≥5 min) | `connectors/refresh-scheduler.ts` | Operator connectors; skips while `syncBusy()` |
| Investor Eye ingest | 10 min | `investor-eye/scheduler.ts` | GDELT/USGS/FIRMS/news → normalized events; skips while `syncBusy()` |

### Why markets are skipped

`isMarketOpen()` reads `Market.timezone`, `openHour`, and `closeHour` and skips
closed markets (and weekends) to save provider quota. It is deliberately
conservative: **unknown hours, invalid timezones, or DB errors all resolve to
"open"**, so a data gap can never silently stop refreshing. Crypto is always open.

### Why bulk writes are chunked and slept

better-sqlite3 is **synchronous**. A large batch of writes blocks every other
request until it finishes. That is why:

- `yieldToEventLoop()` is called between write chunks,
- the scheduler sleeps between markets (3–4s),
- warm-up, sync, and scrape jobs are mutually exclusive via flags,
- there is a boot grace period before the first heavy job.

If you add a bulk job, follow those same rules or you will freeze the site.

## Serving — how data reaches the screen

### Path A: DataHub (dashboard, rail, and widgets)

1. A module registers a topic: `registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl, interval }))`.
2. A component calls `useTopic<T>(id)`.
3. The hub fetches once per topic, caches for `ttl`, refreshes every `interval`.
4. Every subscriber gets the same entry; hidden widgets unsubscribe and stop the
   timer.

`market:indices:US` is registered in `stock-chat.tsx` directly so the Aurora glow
has sentiment data on every tab, even cold-booting into chat.

### Path B: Direct fetch (full-page screens)

Screens like the screener, news, journal, and economics call their API route and
manage their own pagination/state. The screener filters and paginates
**server-side** — never pull the whole universe client-side.

## The staleness story (be precise about this)

There are several distinct "this data is old" cases. Do not conflate them:

| Case | How it shows up |
|---|---|
| Market closed | Prices are last-close; refreshing would be pointless |
| No universe imported | Screener falls back to demo data behind a `DEMO` banner |
| Imported CSV/API data | `Price.source = 'csv'` |
| Topic fetch failed | DataHub entry is `UNAVAILABLE` |
| Feed unreachable | News falls back to its mock/empty source field |

The product rule stands: **never present stale or simulated data as live.**

## Data shape contracts (do not break silently)

- `/api/news` → `{ news, source: 'rss' | 'empty' | 'error', pagination }`
- DataHub entry → `{ data, source: DataSource, updatedAt, error?, sourceId? }`
  where `DataSource` is
  `LIVE | CACHED | HISTORICAL | DEMO | ESTIMATED | CUSTOM | UNAVAILABLE`
- `/api/data/[capability]` →
  `{ ok, capability, data, provenance, source, retrievedAt, error }`
- Screener symbols are stored **uppercase**; normalize input with
  `.toUpperCase()` (SQLite via Prisma does not support `mode: "insensitive"`).

## Where to look when data is wrong

1. Is the market open? → `isMarketOpen()` / stored market hours.
2. Did a job run? → `CronJob.lastRunAt` / `nextRunAt` in JDDS, scheduler logs.
3. Is there a row at all? → query `Asset` / `Price` for that `marketId`.
4. Is it stale by design? → check `Price.source` and `Price.updatedAt`.
5. Did the route fail? → check the DataHub `source`/`error`, then the API route.
6. Is it a known gap? → see "Known Problems" in
   [`../skills/REMEMBER.md`](../skills/REMEMBER.md).
