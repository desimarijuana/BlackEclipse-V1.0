---
title: Harness Phase 2 Progress
status: Current
last-verified: 2026-09-21
---

# Harness Phase 2 — Hybrid Financial Data & Web Research Layer

**Phase:** 2 — Hybrid Financial Data & Web Research Layer
**Status:** Complete (core foundation)
**Last updated:** 2026-09-21

## Objective

Make the agent able to answer *"what information do I need → what is the best
source → structured data, cache, web research, or several → can I retrieve them
in parallel → is the evidence fresh and reliable → how do I return it?"* —
without coupling the agent to JDdS, yfinance, a search provider, or any single
data source.

## Completed milestones

| Milestone | What was built | Files |
|---|---|---|
| 2A Audit | Read Phase-1 harness + existing JDdS/yfinance/fundamentals/economics/web infrastructure before changing anything | (read-only) |
| 2B Retrieval contract | Provider-agnostic request/result/evidence models | `python/harness/retrieval/contract.py` |
| 2C Source selection | Deterministic, explainable task-aware planner | `retrieval/planner.py` |
| 2D Structured retrieval | JDdS vault + live structured provider behind one `RetrievalSource` contract | `retrieval/structured.py`, `retrieval/sources.py` |
| 2E yfinance/fallback | Planner-ordered providers; vault first, live provider second, web last; precise data never web-sourced | `planner.py`, `structured.py` |
| 2F Web research | First-class search → rank → retrieve page → evidence path, primary-source preference | `retrieval/web.py`, `src/lib/web-research.ts` |
| 2F Evidence contract | `source/sourceType/url/title/publishedAt/retrievedAt/evidence/query/freshness/validationStatus`; missing metadata is `null` | `contract.py` |
| 2G Normalization | Provider payloads → one `NormalizedFinancialObject`, provenance preserved, transforms recorded | `retrieval/normalize.py` |
| 2H Cache | Per-data-type TTL cache with `cachedAt`/`originalRetrievedAt`/`source`/`dataTimestamp`/`freshness` + in-flight dedup | `retrieval/cache.py`, `policies.py` |
| 2I Parallel retrieval | Concurrency limit, per-task timeout, partial failure, cancellation, error isolation | `retrieval/parallel.py` |
| 2J Evidence aggregation | `EvidenceSet` keeps structured/derived/web/user/cached/unverified distinct | `retrieval/aggregate.py` |
| 2K Validation | valid/warning/invalid/unknown; negative earnings stay valid | `retrieval/validate.py` |
| 2L Conflicts | Discrepancies preserved; resolved only with a stated reason, else `conflicting` | `retrieval/conflicts.py` |
| 2M Initial tools | `market.get_quote`, `market.get_ohlcv`, `fundamentals.get_*`, `research.*`, `macro.get_series` | `python/harness/retrieval_tools.py` |
| 2N Harness integration | Layer built per run, shared cache in service, tools registered, agent allowlist updated | `service.py`, `graph.py`, `agents.py`, `main.py` |
| 2M TS capabilities | `live_quote`, `price_history`, `macro_series`, `web_search`, `web_fetch` on the read-only bridge | `src/lib/harness/data-bridge.ts`, `types.ts`, route |
| 2O End-to-end tests | The 10 required scenarios + layer unit tests | `python/tests/test_retrieval*.py` |

## Files created

**Python (`python/harness/`):**
`retrieval/__init__.py`, `retrieval/contract.py`, `retrieval/policies.py`,
`retrieval/sources.py`, `retrieval/structured.py`, `retrieval/normalize.py`,
`retrieval/web.py`, `retrieval/cache.py`, `retrieval/parallel.py`,
`retrieval/validate.py`, `retrieval/conflicts.py`, `retrieval/aggregate.py`,
`retrieval/planner.py`, `retrieval/layer.py`, `retrieval_tools.py`;
`tests/test_retrieval.py`, `tests/test_retrieval_scenarios.py`.

**TypeScript (`src/lib/`):**
`web-research.ts` (the ONE shared search+fetch implementation),
`harness/data-bridge-phase2.test.ts`.

## Files changed

- `python/harness/tools.py` — `ToolContext` gains lazily-attached
  `retrieval`/`retrieval_cache` (no core import cycle).
- `python/harness/service.py` — registers retrieval tools; owns the one shared
  `RetrievalCache`; passes the cache into runs; adds `retrieval_metrics()`.
- `python/harness/graph.py` — threads the shared cache to the per-run context.
- `python/harness/agents.py` — Eclipse Agent allowlist adds the Phase-2 tools.
- `python/harness/main.py` — `/health` reports retrieval metrics; new
  `GET /retrieval/metrics`.
- `src/lib/harness/data-bridge.ts` — five new read-only capabilities reusing the
  scraper fallback chain, the Yahoo bridge, the economics sources and the shared
  web-research transport.
- `src/lib/harness/types.ts` — `DataCapability` union extended.
- `src/app/api/harness/data/route.ts` — capability whitelist extended.
- `src/lib/agent/tools.ts` — `search_web` now delegates to `web-research.ts`
  (removed the inline DuckDuckGo parser; no second search system).

## Tests and validation results

| Check | Command | Result |
|---|---|---|
| Python tests | `python -m pytest python` (vendored 3.12) | Pass — 83 tests |
| Retrieval unit tests | `pytest tests/test_retrieval.py` | Pass — 23 |
| Scenario tests (2O) | `pytest tests/test_retrieval_scenarios.py` | Pass — 14 |
| Graph integration | `pytest tests/test_graph.py` | Pass — a retrieval tool runs end to end |
| Typecheck | `npx tsc --noEmit` | Pass (0 errors) |
| Lint | `npx eslint src/lib/harness src/lib/web-research.ts src/lib/agent/tools.ts` | Pass |
| TS tests | `npx vitest run` | Pass — 1456 tests |
| Build | `npm run build` | Pass; all harness routes present |

The 10 required scenarios are covered in `tests/test_retrieval_scenarios.py`
(1–10, plus 8b/9b sub-cases). Each asserts the *decision* the layer made, not a
provider: history is structured-only, "what happened today" combines market +
web, web evidence is provenance-tagged and snippet-only results are marked
`unverified`, no-number-is-invented holds for historical/macro requests, and
concurrent identical requests share one provider call.

## Post-completion defect fixes (2026-09-21)

Three defects surfaced by end-to-end testing against the live bridge:

1. **Historical prices were completely unavailable (blocker).** `market_get_ohlcv`
   passed its `period` argument ("6mo") straight through as the bridge's
   `interval`, so yfinance received an invalid interval and never ran the history
   path. Fixed by classifying `quantity` against the interval/range vocabularies
   in `retrieval/structured.py` (`_params_for`): a range → `range`, an interval →
   `interval`. Verified live: 126 / 251 / 1254 bars for 6mo / 1y / 5y.
2. **Macro series returned zero observations.** The `fred-analytics` source built
   rows keyed by FRED's dynamic value header (`{ observation_date, GDP }`), which
   the normalizer's key lists did not recognize. Fixed to emit the canonical
   `{ date, value }` shape; verified live at 318 rows.
3. **`company_profile` returned an empty body despite valid quality.** Conflict
   resolution is numeric-only and dropped every string fact (sector, industry,
   description). Fixed in `retrieval/layer.py` `_resolve` to pass non-numeric
   objects through untouched.
4. **Blanket, uninformative quality warnings.** The validator applied a per-row
   age check, so every bar in a 5-year series (and every macro observation) was
   flagged "possible quality issue". Staleness is a dataset property: it is now
   checked once against the series' newest timestamp, and value warnings name the
   metric and the specific reason.

Regression tests added for all four (Python + TS).

## Known limitations

- **Cache is in-process.** It survives across runs within one runtime process but
  not across a restart. This is deliberate (no new database); a durable cache
  would belong in `agent-memory.db` under a later ADR.
- **Web evidence extraction is text-first.** `web_fetch` returns readable page
  text + title, not structured entity extraction. Good enough for evidence, not
  for tables.
- **Primary-source detection is host-hint based**, used to LABEL provenance
  (never to invent it). A better classifier could use filing metadata.
- **`research.retrieve_source` returns raw text**; the model reads it. No
  document QA/summarization is done by the layer (that is the agent's job).
- **Live-provider breadth depends on the existing scraper chain.** `live_quote`
  reuses it as-is; `price_history` depends on the Python yfinance bridge being
  installed.
- **`derived_metric` plans structured inputs but does not yet compute a named
  metric** (e.g. Sharpe) automatically — the agent computes from returned data.
  A deterministic calculator is a natural next step.

## Decisions

- **A dedicated `retrieval/` package, not new tools.** Provider-agnosticism
  lives in one layer the tools call; tools never name a provider.
- **The planner is data, not branches.** New data types are new rows.
- **No second web-search system.** `web-research.ts` is the single search+fetch
  path; the legacy agent tool now delegates to it.
- **One shared process-wide cache.** Safe because in-flight dedup is keyed per
  retrieval; two runs asking for the same dataset share one provider call.
- **Precise data is never web-sourced.** `historical_prices`, `macro_series` and
  `derived_metric` remove WEB from the plan entirely.
- **Conflicts are grouped by fact, not by metric name.** Bars at different dates
  are separate observations (a bug the scenario tests caught: a 20-bar series
  had collapsed to one bar).

## Next action

Recommended next implementation step: **a deterministic derived-metric
calculator** (Sharpe, volatility, drawdown, CAGR) that consumes
`market.get_ohlcv` output and returns `derived` evidence — closing the
`derived_metric` path with computed, provenance-carrying values instead of
leaving the arithmetic to the model.
