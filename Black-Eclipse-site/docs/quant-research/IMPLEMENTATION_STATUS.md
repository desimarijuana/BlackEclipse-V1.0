# Statistical Analysis & Feature Engineering — Implementation Status

> **Status: backend complete and verified; the visual UI (Research Studio, visual
> feature-factory node editor) is the remaining work.**
> `last-verified: 2026-10-10` — engine, persistence, registry, jobs and tests
> re-read against source.

This tracker records what is implemented, verified, and still outstanding. A task
is only `VERIFIED` when its acceptance criteria are met **and** runtime test
evidence is recorded. Status: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`,
`IMPLEMENTED`, `TESTING`, `VERIFIED`, `FAILED`.

## Summary

| Area | Status | Evidence |
| --- | --- | --- |
| Shared contract (schema, provenance, errors, validation) | VERIFIED | `base.py`; `test_stats_registry.py` |
| Distributions (t/χ²/F/normal, from first principles) | VERIFIED | `dist.py`; `test_stats_dist.py` |
| 14 statistical tools | VERIFIED | `m_*.py`; engine tests (82) |
| Safe formula language | VERIFIED | `formula.py`; `test_stats_formula.py` |
| Market-data adapter (gateway-backed) | VERIFIED | `datasets.py`; `test_stats_datasets.py` |
| Persistence (features, analyses, runs, validations, audit, artifacts) | VERIFIED | `store.py`; `test_stats_store.py` |
| Feature registry + immutable versioning + dependencies | VERIFIED | `feature_registry.py`; `test_stats_features.py` |
| Computation-identity cache | VERIFIED | `cache.py`; `test_stats_service.py` |
| Background jobs + cancellation | VERIFIED | `runner.py`; `test_stats_runner.py` |
| Service orchestration + audit | VERIFIED | `service.py`; `test_stats_service.py` |
| Agent tool registration (31 tools) | VERIFIED | `tools.py`; `agents.py`; `test_stats_registry.py` |
| Harness boot wiring | VERIFIED | `bootstrap.py`; `service.py` |
| HTTP surface `/stats/v1` (23 routes) | VERIFIED | `routers/stats.py`; route probe |
| Next.js front door + client | VERIFIED | `src/app/api/stats/[...path]/route.ts`; `src/lib/stats-client.ts` |
| Performance benchmarks | VERIFIED | `test_stats_performance.py`; `OPERATIONS.md` |
| **Research Studio UI (13 sections)** | NOT_STARTED | — |
| **Visual feature-factory (node editor)** | NOT_STARTED | — |
| Per-workspace authorization | PARTIAL | operator gate reused; workspace scoping outstanding |

## Phase checklist

- **Phase 0 — Repository audit** — VERIFIED. Reused the FastAPI harness, tool
  registry, agent allowlist, operator gate, `agent-memory.db` store pattern and
  the Next.js proxy pattern; added no second framework.
- **Phase 1 — Quant Service foundation** — VERIFIED. Uniform envelope,
  `StatsError`, `Provenance`, validation, `dist.py`, registry, one real
  calculation end-to-end.
- **Phase 2 — All fourteen tools** — VERIFIED (see `STATISTICAL_METHODS.md`).
- **Phase 3 — Persistence & execution** — VERIFIED. `StatsStore` (features,
  analyses, runs, validations, audit, artifacts), immutable feature versions,
  computation-identity cache, background jobs with cancellation and durable
  state mirroring, artifact spilling for large series.
- **Phase 4 — Research Studio UI** — NOT_STARTED.
- **Phase 5 — Formula Editor & Feature Factory** — PARTIAL: safe parser +
  evaluator + registry (versioning, dependencies, validation, preview, rollback)
  done and tested; the **visual** node editor UI is NOT_STARTED.
- **Phase 6 — Agent & workflow integration** — VERIFIED (backend): all 14 tools,
  data-driven analysis, formulas and registry operations are registered and
  allowlisted; a dedicated multi-step scenario + visual-response integration in a
  run remains to be exercised in the UI phase.
- **Phase 7 — Performance & research validation** — VERIFIED for benchmarks
  (`test_stats_performance.py`) and leakage/PIT (causal transforms, direct tests);
  factor walk-forward screening UI is part of Phase 4.
- **Phase 8 — Production hardening** — PARTIAL: operator gate, structured errors,
  bounded inputs, audit trail, best-effort persistence done; per-workspace
  authorization and a full browser E2E remain.

## Verification commands

```
# From Black-Eclipse-site/
scripts/vendor/python/python.exe -m pytest python/tests/test_stats_*.py -q
npx tsc --noEmit
node scripts/test-python.js
npx vitest run
node scripts/test-evals.js
```

## Known limitations / residual constraints

- **GARCH(1,1)** uses a deterministic Nelder–Mead MLE (no SciPy); reproducible but
  a local optimum, flagged provisional when it does not converge.
- **ADF/KPSS/Johansen p-values** are interpolated from published critical-value
  tables (`pValueApprox`); the statistics are exact.
- **Isolation forest** is from-scratch, signed by a fixed seed.
- **Correlation matrices / IC use the full sample** (retrospective); regime
  thresholds are retrospective unless `expandingThresholds` is set — stated in
  every response.
- The **visual UI** and **per-workspace authorization** are not built.

## Exact remaining tasks

1. Quant Research Studio UI (13 sections) over `/api/stats/*`.
2. Visual feature-factory node editor (reuse the existing workspace/graph engine).
3. Per-workspace authorization, quotas and cross-workspace isolation.
4. A browser end-to-end scenario through the agent harness.
