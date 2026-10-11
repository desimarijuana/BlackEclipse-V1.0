# Testing

> `last-verified: 2026-10-10`

## Layout

| File | Covers |
| --- | --- |
| `tests/test_stats_dist.py` | distributions vs published critical values |
| `tests/test_stats_core.py` | returns, volatility, drawdown, autocorrelation |
| `tests/test_stats_relationships.py` | correlation, beta, regression, lead-lag, IC |
| `tests/test_stats_inference.py` | ADF/KPSS, Engle–Granger/Johansen |
| `tests/test_stats_structure.py` | regime, build_features, outliers |
| `tests/test_stats_formula.py` | formula correctness + **security** |
| `tests/test_stats_registry.py` | 14-tool registry contract, agent registration |
| `tests/test_stats_store.py` | persistence, immutable versions, artifacts, audit |
| `tests/test_stats_features.py` | registry versioning, deps, cycles, preview, validate |
| `tests/test_stats_datasets.py` | gateway adapter, alignment, honest errors |
| `tests/test_stats_service.py` | cache identity, persistence, artifact spilling |
| `tests/test_stats_runner.py` | background jobs, cancel, failure, mirroring |
| `tests/test_stats_performance.py` | wall-clock benchmarks |

## Commands

```
# From Black-Eclipse-site/
scripts/vendor/python/python.exe -m pytest python/tests/test_stats_*.py -q
npx tsc --noEmit
node scripts/test-python.js       # full Python suite
npx vitest run                    # front-end suite
node scripts/test-evals.js        # evaluation gates
```

## Conventions

- **Known values first** — every tool is asserted against a hand-computed number,
  not just shape.
- **Honest-failure tests** — insufficient data, invalid input, unknown variables,
  cycles and injection attempts are asserted to fail *as data*, never silently.
- **Security tests** — `test_stats_formula.py` asserts the language rejects
  `__import__`, `open`, `eval`, `exec`, attribute access and over-long input.
- **Leakage/PIT** — causal-only transforms and forward-target alignment are
  exercised via the IC and feature tests.
- **Generous performance budgets** — benchmark assertions use wide ceilings so a
  regression is caught without CI flakiness; the measured numbers print with `-s`.

## Baseline

At the time of writing: 122 stats tests (82 engine + 40 persistence/registry/
jobs/perf) pass locally; the full Python suite, Vitest and the eval gates pass.
