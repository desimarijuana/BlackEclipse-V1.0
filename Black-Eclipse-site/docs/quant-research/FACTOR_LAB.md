---
title: Factor & Alpha Research Lab — Implementation Tracker
status: In Progress
last-verified: 2026-10-11
---

# Factor & Alpha Research Lab

The Factor Lab is a net-new vertical inside the existing Quant Research
workspace. It does **not** introduce a second framework: it reuses the ONE
Python harness runtime, the ONE `agent-memory.db` store, the safe formula
language, the immutable-dataset/universe stores, the quant validation
primitives, the Execution Fabric for long-running runs, the Artifact/Evidence
stores, and the Next.js front-door proxy pattern.

## Repository audit findings (Phase 0)

| Need | Reuse | Path |
| --- | --- | --- |
| Safe expression language | `stats.formula.parse/evaluate` (38 functions) | `python/harness/stats/formula.py` |
| Feature definition/versioning pattern | `FeatureRegistry` + `StatsFeatureVersion` | `python/harness/stats/feature_registry.py`, `stats/store.py` |
| Response envelope + provenance + errors | `Provenance`, `make_response`, `StatsError` | `python/harness/stats/base.py` |
| Student-t p-values | `t_two_sided_p`, `norm_sf` | `python/harness/stats/dist.py` |
| Immutable datasets | `DatasetStore` | `python/harness/quant/dataset_store.py` |
| Point-in-time universe membership | `UniverseStore.members_as_of` (SCD-2) | `python/harness/market/universe_store.py` |
| Market data (PIT, verified) | `get_market_data` / gateway | `python/harness/market/research_tools.py` |
| Robustness / overfitting primitives | `validation.py`, `multiple_testing.py`, `walkforward.py` | `python/harness/quant/` |
| Background execution | Execution Fabric `quant` queue | `python/harness/fabric/` |
| Artifacts / provenance files | `ArtifactService.register_bytes` | `python/harness/artifacts/` |
| Agent tool registration | `ToolDefinition` + `registry.register`; allowlist in `agents.py` | `python/harness/tools.py`, `agents.py` |
| Operator-gated REST | `Depends(require_operator)` | `python/harness/deps.py` |
| Front door | `[...path]/route.ts` proxy + client | `src/app/api/*/[[...path]]/route.ts` |

**Databases:** SQLite only. Metadata → `agent-memory.db` (additive idempotent
DDL). Large series → gzipped JSON artifacts under `.black-eclipse/factors/`.
There is **no PostgreSQL** in this application and none will be added.

## Phase status

Status vocabulary: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `IMPLEMENTED`,
`TESTING`, `VERIFIED`, `FAILED`.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repository audit + tracker | VERIFIED |
| 1 | Research data foundation (reuse dataset/universe stores) | VERIFIED (reused) |
| 2 | Factor registry + formula engine | IMPLEMENTED |
| 3 | Built-in factor library | IMPLEMENTED |
| 4 | IC / Rank IC / decay | IMPLEMENTED |
| 5 | Quantile portfolios + cost-aware simulation | IMPLEMENTED |
| 6 | Correlation / redundancy / attribution | IMPLEMENTED |
| 7 | Alpha composer | IMPLEMENTED |
| 8 | Stability / regime | IMPLEMENTED |
| 9 | Validation + bias controls (gate) | IMPLEMENTED |
| 10 | Strategy promotion (factor → `QuantStore` strategy + experiment + approval + lineage) | IMPLEMENTED |
| 11 | Agent tools | IMPLEMENTED |
| 12 | Production hardening (tests, security, observability) | IMPLEMENTED |

## Architecture

```
python/harness/factors/
  engine.py    pure NumPy quantitative core (the authoritative math)
  library.py   built-in factor definitions (formula text)
  models.py    dataclasses + envelopes
  store.py     FactorStore on agent-memory.db (immutable versions)
  service.py   orchestration facade (datasets + engine + store)
  tools.py     FACTOR_TOOLS (agent tools)
  bootstrap.py install_factor_layer(service)
python/harness/routers/factors.py      /factors/v1 (operator-gated)
src/app/api/factors/[...path]/route.ts Next.js front door
src/lib/factors-client.ts              typed client
```

## Conventions (documented, tested)

- Forward return: `R(i,t,h) = P(i,t+h)/P(i,t) − 1` (simple; `log` optional).
- IC(t,h) = cross-sectional Pearson corr of `factor(i,t)` vs `R(i,t,h)`.
- Rank IC = Spearman (average-rank ties), identical sample masks.
- IC IR = mean(IC) / std(IC), **periodic** unless `periodsPerYear` given.
- Turnover = one-way = `½·Σ|w_new − w_prev|`; cost = `turnover · cost_bps/1e4`.
- Annualization factor must be supplied; never assumed.
- A factor is never labelled validated on in-sample strength alone.

## Promotion bridge (Phase 10)

`factors/promotion.py` `promote_to_strategy` turns a **validated** factor version
into a first-class strategy without duplicating the strategy engine:

* the strategy is persisted through the ONE `QuantStore` (immutable version +
  the native `request_approval`/`decide_approval` governance);
* its execution is delegated to the Factor Lab cross-sectional quantile engine
  (`metadata.execution = "factor_portfolio"`) — the event-driven engine is
  per-instrument and cannot express cross-sectional sorts, so this is the honest
  executor;
* the portfolio run is persisted through `QuantStore.save_experiment`
  (kind `factor_portfolio`) so it sits beside native backtests in
  `/quant/experiments`;
* lineage (factor version → strategy version → experiment) is recorded in the
  Factor store and exposed at `/factors/v1/lineage`.

REST: `POST /factors/v1/promote`. Tool: `promote_factor_to_strategy`.

## Remaining / future work

1. Browser end-to-end scenario through the agent harness.
2. Wire factor portfolio runs into the Execution Fabric `quant` queue so a
   promotion can run as a durable background job.
3. Regime labels currently use a cross-sectional dispersion split; a pluggable
   regime provider (reusing `stats.m_regime`) is a natural extension.
