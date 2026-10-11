---
title: Quantitative Research Data Infrastructure
status: Current
last-verified: 2026-10-10
---

# Quantitative Research Data Infrastructure

**Who this is for:** anyone asking "how do we get trustworthy research data, and
how do I prove where a number came from?"

## Why this exists

JDdS and the free provider set are **not inherently trustworthy**. Observations
can be stale, delayed, incomplete, mis-mapped or mutually inconsistent. This
layer makes that uncertainty explicit instead of hiding it: it retrieves from
suitable sources, independently verifies when asked, records provenance and
conflicts, and never presents unverified data as verified.

It is **not** a second ingestion system. It sits on top of the existing Market
Data Gateway (routing/quality/provenance), the Quant Engine (backtesting,
calculations) and the Evidence & Research Engine.

## The layers (bottom → top)

```
provider adapters (TS bridge)
        │
Market Data Gateway            python/harness/market/gateway.py
  routing · pacing · normalize · quality · provenance · provider pinning
        │
Verification engine            python/harness/market/verification.py
  policies · cross-source compare · conflicts · scorecard   (pure, no I/O)
        │
Transforms                     python/harness/quant/transform.py
  resample_rows · align_rows     (pure, deterministic)
        │
Immutable datasets             python/harness/quant/dataset_store.py
  content hash · versions · manifests · artifacts
        │
Research tool surface          python/harness/market/research_tools.py
  get_market_data · verify_market_data · build_research_dataset · …
```

Agents and workflows call only the tool surface; the tools call the shared
services. No tool re-implements provider routing, verification or storage.

## Named verification policies (the contract)

Selected per request; **never silently downgraded**.

| policy | requires verification | min sources | fails on conflict | single source allowed |
|---|---|---|---|---|
| `cached_fast` | no | 1 | no | yes |
| `fresh_preferred` | no | 1 | no | yes |
| `cross_verified` | yes | 2 | no (flagged) | no |
| `historical_reproducible` | yes | 2 | **yes** | no |
| `strict_research` | yes | 2 | **yes** | no (also requires authority ≥ 0.8) |

`resolve_policy()` raises on an unknown name — a typo is a hard error, not a
fallback to a weaker policy.

## Verification invariants

- **No averaging.** Two disagreeing sources produce a `Conflict` record; the
  wider tolerance under which values agree is a relative difference (default
  1.5%, `HARNESS_MARKET_CONFLICT_TOLERANCE`).
- **Independence is earned, not assumed.** A provider absent from
  `_UPSTREAM_LINEAGE` reports `independence="unknown"`; two providers sharing a
  known upstream are classified `shared_upstream_divergence`, not verified.
- **Authority is documented.** `AUTHORITY` ranks officials/filings above vendor
  feeds above keyless scrapes. `strict_research` enforces a floor.
- **Status is one of** `verified`, `unverified`, `conflicted`, `failed`. Only
  `verified` sets `verified=true`.

## Dataset invariants

- A version is **insert-only**; there is no update path.
- The `contentHash` (sha256 over canonicalized rows, symbol-order independent)
  makes build idempotent: identical content returns the **same** version.
- New data / changed adjustments / corrected normalization yields `vN+1`; the old
  version and its artifact are preserved and remain readable.
- The manifest records universe, interval, range, adjustment basis, per-symbol
  coverage, quality, lineage, retrieval timestamps and the hash.
- Metadata lives on `agent-memory.db`; rows are gzipped JSON under
  `.black-eclipse/quant/datasets/`. Never `jdds.db` / `eclipse-memory.db`.

## Transform invariants

- Resampling: open=first, high=max, low=min, close=last, volume=sum; buckets with
  fewer members than expected are flagged `partial`.
- A finer target than the source is **refused** — intraday prices are never
  manufactured from daily data.
- Alignment forward-fills **only** when `fill="ffill"` is explicit; the default
  leaves missing values null and reports the count.

## Tools

`resolve_instrument`, `list_providers`, `get_provider_health`, `get_market_data`,
`verify_market_data`, `resample_data`, `align_timeseries`,
`build_research_dataset`, `get_dataset_versions`, `compare_datasets`,
`query_dataset`, `get_data_quality_report`, `get_data_provenance`,
`get_trading_calendar`, `get_currency_conversion`, `get_corporate_actions`,
`get_universe`, `record_universe`, `list_universes`, `export_dataset`,
`refresh_dataset`, `analyze_dataset`.

All are `read`/low-risk, registered in `market/bootstrap.py`, and allowlisted for
the Eclipse agent (`agents.py`). The secondary handlers (calendar, FX, corporate
actions, universe, export/refresh) live in `research_tools_ext.py` to keep each
module under the size budget.

**Trading calendar.** `market/calendar.py` models US-equity weekday sessions
(09:30–16:00 ET with US holidays, DST from the statutory rule), FX (Sun 17:00 –
Fri 17:00 ET) and crypto (24/7) with no `tzdata` dependency. Freshness is
session-aware: a closed market with an observation at/after the last close is
`closed_recent`, never mislabelled `stale`.

**Persistent bars.** `market/series_store.py` stores normalized OHLCV per
(symbol, interval, provider, adjusted, eventTime) on `agent-memory.db` so
coverage is queryable and datasets can be exported/refreshed without a full
re-fetch. Built datasets are also catalogued in the Artifact Center when an
artifact service is bound.

**Point-in-time.** `query_dataset`/`export_dataset` take an `as_of` cut; bars
whose `knownAt` exceeds it are dropped, and when rows carry no known-at metadata
the result sets `pitUnknown: true` rather than pretending PIT was enforced.

## REST API

`python/harness/routers/research_data.py` exposes the same services over HTTP
(operator-gated), so the UI and external clients do not need an agent:

- `GET /research-data/{policies,providers,health,calendar,series,quality,universes}`
- `POST /research-data/{resolve,market-data,verify,resample,align}`
- `GET /research-data/datasets`, `GET /research-data/datasets/{id}`,
  `GET /research-data/datasets/{id}/versions`
- `POST /research-data/datasets/build`,
  `POST /research-data/datasets/{id}/{refresh,export,analyze}`
- `POST /research-data/universes/record`
- `POST /research-data/{fundamentals,macro}` — vault fundamentals / macro series
- `POST /research-data/datasets/{id}/execute` — isolated notebook (below)

The Next.js front door proxies `/api/research-data/*` → `/research-data/*`.
Registered in `main.py`; routes reach shared state only through `harness.deps.service`.

## Isolated notebook

`research/notebook.py` runs operator-supplied analytical Python in the ONE bounded
sandbox (`code.sandbox`), never in the FastAPI process. The notebook receives a
materialized, read-only copy of one dataset version as a CSV
(`os.environ['ECLIPSE_DATASET_PATH']`) and gets **no** provider credentials, vault
values, callback token or proxy (`sandbox.build_env`). Wall-clock, memory and
output are bounded; a missing sandbox is an honest refusal, never an unbounded
run. Unattended agents use the declarative `analyze_dataset` instead.

## Point-in-time universes

`record_universe` writes **effective-dated** membership to `market/universe_store.py`
(SCD-2: recording a later effective date closes the earlier open interval).
`get_universe` with a recorded `universe_id` resolves membership `as_of` a date
from that history — the survivorship-bias control. When nothing is recorded for a
date, membership is reported UNKNOWN, never guessed.

## UI

`Research Data` (`research-data` AppTab; deep link `/?tab=research-data`) is a
Dataset Explorer / Builder / Data Quality Center / Provider view over the REST
API: list datasets, inspect manifest + coverage + quality + lineage, build a new
immutable version, run deterministic analytics, export, refresh, and read
provider capabilities and health.

## Where to look

| I want to… | Open |
|---|---|
| Change a verification policy or threshold | `python/harness/market/verification.py` (`_POLICIES`, `AUTHORITY`, `_UPSTREAM_LINEAGE`) |
| Change provider capabilities | `python/harness/market/providers.py` |
| Pin / select a provider | `python/harness/market/gateway.py` (`_dispatch`, `candidate_providers`) |
| Change resampling/alignment | `python/harness/quant/transform.py` |
| Change dataset versioning | `python/harness/quant/dataset_store.py` |
| Change the trading calendar / session freshness | `python/harness/market/calendar.py` |
| Change the persistent bar store | `python/harness/market/series_store.py` |
| Change universe point-in-time membership | `python/harness/market/universe_store.py` |
| Change the research REST API | `python/harness/routers/research_data.py` + `src/app/api/research-data/[...path]/route.ts` |
| Change the Research Data screen | `src/components/screens/research-data/research-data-screen.tsx` + `src/lib/research-data/research-data-client.ts` |
| Add or change a research tool | `python/harness/market/research_tools.py` (core) + `research_tools_ext.py` (calendar/FX/corporate actions/universe/export/refresh) |

## Honest limits

- Verification is only as independent as the configured providers. If no suitable
  second provider exists, `cross_verified` returns **unverified**, not verified.
- The provider adapters themselves live on the TS bridge; their normalization
  contract is pinned with recorded, sanitized fixtures
  (`test_market_provider_contract.py`). **Live** keyed-provider calls are opt-in
  and require credentials (`test_market_live.py`, `BLACK_ECLIPSE_MARKET_LIVE=1`).
- Independence is derived from each provider's declared `upstream`: a shared
  upstream is NOT independent, and an unrecorded lineage is reported `unknown`
  (never assumed independent).
- The **backtest** screen (`backtest` AppTab) and the **Research Data** screen
  (`research-data` AppTab: Dataset Explorer + Builder + Notebook + Data Quality
  Center + Providers) are mounted; both follow the Pages/UI-Builder pattern
  (deep link / command palette, not sidebar sections).
- New research tools are registered and agent-callable but are **not yet typed
  nodes in the Workflow Graph** (deferred by request), and Evidence-Engine linkage
  is provenance passthrough + Artifact-Center cataloguing (no dataset/version-linked
  claim verification yet).
- Corporate actions are only as complete as the provider's `corporateActions`
  payload; when absent the tool returns UNAVAILABLE rather than inventing events.
- Universe membership is recorded (effective-dated) and resolved as-of from that
  history; when nothing was recorded for a date it is reported UNKNOWN — no
  provider supplies point-in-time index membership here.

## Configuration

- `HARNESS_MARKET_CONFLICT_TOLERANCE` — relative agreement tolerance (default 0.015).
- `HARNESS_MARKET_REALTIME_MAX_AGE_S` — realtime staleness ceiling (default 60).
- Provider credentials are resolved by the bridge, not Python: `POLYGON_API_KEY`,
  `FINNHUB_API_KEY`, `COINGECKO_API_KEY`, `FRED_API_KEY` enable the keyed providers.
