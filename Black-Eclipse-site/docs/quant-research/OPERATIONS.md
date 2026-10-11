# Operations

> `last-verified: 2026-10-10`
> Code: `service.py`, `cache.py`, `runner.py`, `store.py`, `bootstrap.py`,
> `routers/stats.py`.

## Execution modes

- **Synchronous** — `POST /stats/v1/analyses` (caller-supplied data) or
  `POST /stats/v1/analyses/run` (data-driven via the gateway). Returns the full
  envelope.
- **Asynchronous** — `POST /stats/v1/analyses/submit` returns a `runId`
  immediately; poll `GET /stats/v1/jobs/{runId}`, cancel with
  `POST /stats/v1/jobs/{runId}/cancel`. The in-process `StatsRunner` bounds
  concurrency with a semaphore.

## Caching

`cache.get_or_compute` reuses a value only when the **complete computation
identity** matches: tool + tool version + validated parameters + a SHA-256 hash
of the data-bearing inputs. Any change yields a different key, so stale results
are never served. The cache is process-local, bounded (LRU, default 256) and
bypassable per request (`useCache:false`). `GET /stats/v1/capabilities` and the
cache `stats()` expose hit/miss counts.

## Persistence & recovery

- Metadata in `agent-memory.db`; results/blobs in `.black-eclipse/stats/`
  (gzipped JSON, checksummed).
- Background run state is mirrored to `StatsRun`, so job history survives a
  process restart (poll `GET /stats/v1/jobs`).
- Persistence is **best-effort and never blocks a computation**: a store failure
  degrades to a computation-only response, never a fabricated result.

## Errors

Structured `{code, message}` with HTTP status: 400 invalid input, 422
insufficient/missing data, 404 unknown tool/feature/analysis/run/artifact, 503
store or gateway unavailable, 500 internal. A failed calculation returns
`status:"error"`; it is never reported as success.

## Authorization & audit

All routes are operator-gated (`require_operator`, the same gate as `/quant`).
Sensitive operations (feature save/rollback, analysis run, formula execution
with `persist`) write `StatsAudit` rows (`GET /stats/v1/audit`). Per-workspace
scoping is tracked as remaining work (see `IMPLEMENTATION_STATUS.md`).

## Bootstrap

`install_stats_layer(service)` (called from `service.py`) registers the tools and
installs the store + runner singletons. It is best-effort: a failure leaves the
capability unavailable rather than blocking boot.

## Benchmarks

Run `scripts/vendor/python/python.exe -m pytest python/tests/test_stats_performance.py -q -s`.
Representative measurements (Windows, vendored Python 3.12, NumPy 2.5):

| workload | time |
| --- | --- |
| returns, 100k points | ~36 ms |
| rolling volatility (20), 50k | ~408 ms |
| correlation matrix 20×2000 | ~13 ms |
| build 20 features on 20k | ~39 ms |
| formula preview on 20k | ~277 ms |
| cross-sectional IC 200×50 | ~12 ms |
