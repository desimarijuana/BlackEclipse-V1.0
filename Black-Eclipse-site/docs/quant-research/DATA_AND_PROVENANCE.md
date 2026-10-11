# Data & Provenance

> `last-verified: 2026-10-10`
> Code: `python/harness/stats/datasets.py`, `service.py`, `store.py`

## The engine never fetches data itself

The statistical engine is pure computation. Market data enters one of two ways:

1. **Caller-supplied arrays** — the direct tool API (`/stats/v1/{tool}`) takes
   series in the request body. No provider, no database.
2. **The market adapter** (`datasets.py`) — `execute_with_data` asks the ONE
   Market Data Gateway for normalized historical series per symbol/timeframe and
   passes plain timestamp-aligned arrays to a tool.

The adapter adds **no** second market-data system: it reuses
`gateway.get_historical_prices(...)` (which resolves the symbol, routes the
provider, paces rate limits, normalizes the record and quality-checks it). An
unavailable symbol/timeframe is an honest typed `StatsError` (`INVALID_INPUT`
/`INSUFFICIENT_DATA`) — never a fabricated series.

## Normalization

`resolve_series` returns `{symbol, interval, field, timestamps[], values[],
provenance}`. `resolve_frame` fetches several symbols and **aligns them to the
intersection of timestamps** (a rectangular frame); symbols that share no
overlap fail honestly rather than being silently dropped.

## What provenance records

Every response carries a `provenance` block (see `base.Provenance`): source,
dataset id, symbols, window, frequency, adjustment, missing-data policy, tool
version, parameters, dependency (library) versions, random seed, warnings and
timestamps. When data came from the adapter, the dataset reference (symbols,
interval, field, date range, provider/quality provenance, observation count) is
attached under `provenance.dataset`.

## What is persisted, and where

- **Metadata** → the ONE `agent-memory.db` connection (idempotent additive DDL):
  features/versions, analyses, runs, validations, audit events, artifact refs.
  Never `jdds.db`, never `eclipse-memory.db`.
- **Large result series** → gzipped JSON artifacts under
  `.black-eclipse/stats/artifacts/`, referenced by a SHA-256 checksum. A result
  series over 5000 points is spilled to an artifact automatically and the
  response carries `{"__artifact__": id, "length": n}` instead of the array.

## Point-in-time integrity

Every built-in feature transform is causal (value at `t` uses only data up to
`t`). Forward-return targets start at `t` and are used only as the evaluation
target. Feature versions carry a `pitSafe` flag; the registry treats all
built-ins as point-in-time safe and never lets a forward target enter a feature.
