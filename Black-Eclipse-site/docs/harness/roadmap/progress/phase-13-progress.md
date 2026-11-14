# Phase 13 — Source authority and freshness arbitration — progress

Gates as unchecked boxes before the work started (roadmap §5). Raw output of every
gate is pasted below once run.

- [x] G1 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_source_authority.py -v`
- [x] G2 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_retrieval.py python/tests/test_retrieval_scenarios.py python/tests/test_retrieval_health.py -q`
- [x] G3 — `grep -rn "_PLAN\|_SINGLE_BEST" python/harness/retrieval/ | wc -l` (expect 0)
- [x] G4 — `git status --short jdds.db prisma/` (expect empty)
- [x] G5 — `npx vitest run src/lib/i18n/plain-language.test.ts`
- [x] G6 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q`
- [x] G7 — `npm run check:all`

## Audit notes (measured before implementing)

Each claim in the prompt was read against the tree:

- `planner._PLAN` and `layer._SINGLE_BEST` existed exactly as described; the
  vault was first for `current_quote`/`historical_prices`/`macro_series`.
- `data-bridge.ts::marketSnapshot` hard-coded `cadenceSeconds: 24*60*60`.
- `validate.py` measured staleness only at dataset level (`_newest_timestamp`).
- The live provider was never consulted for `current_quote` once the vault
  answered (`_execute_single` returns on first OK).
- `liveQuote` hard-coded `asOf: new Date().toISOString()` — the retrieval clock,
  not a market as-of. Corrected to `observationTime: null`,
  `observationSource: "unknown"`; the scraper chain exposes no market timestamp,
  so an as-of would be fabricated.

### Existing tests whose expectations I changed

- `test_retrieval.py::test_planner_selects_structured_for_quotes_and_history`
  — old `quote.sources[0] == "JDDS"`, new `== "LIVE_STRUCTURED"` (and `JDDS` still
  present). Why: Phase 13 puts a live structured reading ahead of a saved
  snapshot for a current price.
- `test_retrieval.py::test_structured_quote_via_layer` — old `strategy[0] ==
  "JDDS"`, new `"LIVE_STRUCTURED"`; fixture dated now + `snapshot_write`, because
  arbitration rejects a stale candidate.
- `test_retrieval.py::{test_cache_reuses_recent_retrieval,
  test_inflight_deduplication_shares_one_retrieval}` — fixture only: the quote is
  dated now (and marked `snapshot_write`) so it is not rejected as stale. No
  assertion changed.
- `test_retrieval.py::test_cache_does_not_serve_realtime_stale_quote` — fixture
  only (fresh quote); assertions unchanged.
- `test_retrieval_scenarios.py` fixtures (`history_payload`, snapshot payloads)
  — regenerated relative to `now` so a "current" series ends now and a quote is
  dated now. No assertion changed.
- `test_retrieval_health.py::test_layer_static_order_when_no_health_is_available`
  — old `result.strategy[0] == "JDDS"`, new `"LIVE_STRUCTURED"` (and `JDDS` in the
  strategy). Why: the static order is now the AUTHORITY order, which leads with
  the live provider for a current price.
- `test_graph.py::test_retrieval_tool_runs_through_the_graph` — fixture quote
  dated now + `snapshot_write`; assertions unchanged.

No test was weakened — every change either moves an ordering the phase
deliberately re-routes or makes a fixture genuinely current, which the new
freshness gate requires.

## Gate output

All commands run from `Black-Eclipse-site/`.

### G1 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_source_authority.py -v`

```
platform win32 -- Python 3.12.8, pytest-9.1.1, pluggy-1.6.0 -- <repo>\Black-Eclipse-site\scripts\vendor\python\python.exe
cachedir: .pytest_cache
rootdir: <repo>\Black-Eclipse-site\python
configfile: pytest.ini
plugins: anyio-4.15.1, langsmith-0.13.0, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 15 items

python\tests\test_source_authority.py::test_authority_has_one_row_per_data_type_and_expected_policies PASSED [  6%]
python\tests\test_source_authority.py::test_decide_source_rejects_web_for_precise_types PASSED [ 13%]
python\tests\test_source_authority.py::test_decide_source_is_pure_and_has_no_side_effects PASSED [ 20%]
python\tests\test_source_authority.py::test_sources_disagree_yields_no_chosen_value PASSED [ 26%]
python\tests\test_source_authority.py::test_labelled_authority_cases[fresh_live_reading_beats_saved_snapshot] PASSED [ 33%]
python\tests\test_source_authority.py::test_labelled_authority_cases[saved_snapshot_outside_window_is_rejected] PASSED [ 40%]
python\tests\test_source_authority.py::test_labelled_authority_cases[two_sources_disagree_beyond_tolerance] PASSED [ 46%]
python\tests\test_source_authority.py::test_labelled_authority_cases[two_sources_agree_within_tolerance] PASSED [ 53%]
python\tests\test_source_authority.py::test_three_stale_rows_in_a_fresh_payload_produce_warnings PASSED [ 60%]
python\tests\test_source_authority.py::test_a_saved_snapshot_is_never_worded_as_live PASSED [ 66%]
python\tests\test_source_authority.py::test_old_payloads_without_observation_fields_still_load PASSED [ 73%]
python\tests\test_source_authority.py::test_layer_arbitrates_live_and_vault_and_shows_the_conflict PASSED [ 80%]
python\tests\test_source_authority.py::test_vault_only_answer_is_labelled_a_saved_snapshot_not_live PASSED [ 86%]
python\tests\test_source_authority.py::test_with_no_bridge_no_source_can_run PASSED [ 93%]
python\tests\test_source_authority.py::test_historical_prices_never_returns_a_web_result PASSED [100%]

============================= 15 passed in 0.18s ==============================
```

### G2 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_retrieval.py python/tests/test_retrieval_scenarios.py python/tests/test_retrieval_health.py -q`

```
.................................................                        [100%]
49 passed in 0.45s
```

### G3 — `grep -rn "_PLAN\|_SINGLE_BEST" python/harness/retrieval/ | wc -l`

```
0
```

### G4 — `git status --short jdds.db prisma/`

```
(no output)
```

### G5 — `npx vitest run src/lib/i18n/plain-language.test.ts`

```
 ✓ src/lib/i18n/plain-language.test.ts (4 tests) 10ms

 Test Files  1 passed (1)
      Tests  4 passed (4)
```

### G6 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q`

```
.........................                                                [100%]
25 passed in 3.04s
```

### G7 — `npm run check:all`

```
 Test Files  175 passed (175)
      Tests  1996 passed (1996)
...
================= 2293 passed, 1 warning in 205.92s (0:03:25) =================
...
  contradiction gate: PASS
  compaction gate: PASS
  Code verification eval — code-verify-v1
  code_verify gate: PASS
    dataset=code-tasks-v1 checksum=9e3896284be04e482fadecdccb6dc527
  safety: S1=PASS, S2=PASS, S3=PASS, S4=PASS, S5=PASS, S6=PASS, S7=PASS, S8=PASS, S9=PASS, S10=PASS, S11=PASS
  code gate: PASS
  route_health gate: PASS
  workflow gate: PASS
  resume gate: PASS
  capability_matrix gate: PASS
eval gates: ALL PASS

[check-all] ALL GATES PASSED
```

Observed counts (not predicted): vitest **175 files / 1996 tests**, pytest **2293
passed**. The pre-change Python baseline was 2291 passed / 1 failed (the failure
was the now-fixed `test_graph` stale fixture); Phase 13 adds 15 authority tests and
the regression suite gains the corrected fixtures.

## Follow-up: the price-route the demo actually used (same day)

The Phase-13 arbitration fixed the retrieval LAYER, but the reported demo asked
for a market cap and the agent used `get_market_snapshot`, which read JDdS
directly and never called the layer — so a months-old cap was still shown. Fix:

- `finance_tools.get_market_snapshot` now runs its price/change/market-cap leg
  through the arbitrated `current_quote` path (`_verified_price_leg`); a stale
  snapshot is not asserted, the observation age is stated, and a disagreement shows
  every contested figure (the headline no longer falls back to the stored value).
- `retrieval/normalize.py::normalize_quote` dates a live payload from its
  `observationTime` so the cross-source conflict grouping can see it.
- `test_source_authority.py` gains the two demo regressions
  (`test_demo_stale_market_cap_is_not_returned_as_current`,
  `test_demo_disagreement_is_shown_when_sources_differ`).
- `test_context_overflow.py::test_side_effecting_tool_is_not_re_executed_across_retry`
  — the property is now asserted on **recorded tool executions** (`== 1`) instead
  of bridge calls, because one `get_market_snapshot` execution now consults several
  capabilities. Old expectation `executed["count"] == 1`; new
  `len(store.list_tool_executions("run_tool")) == 1` (plus `executed["count"] >= 1`).
  Why: the tool-execution count is what the test is actually about; the bridge-call
  count was a proxy that Phase 13 invalidated.

Re-run gates: G1 18 passed, full pytest **2296 passed**, and `npm run check:all`
below.

### Follow-up gate output

```
# python/tests/test_source_authority.py
..................                                                       [100%]
18 passed
```

```
# npm run check:all (final, after follow-up 3)
 Test Files  175 passed (175)
      Tests  2009 passed (2009)
...
================= 2296 passed, 1 warning in 200.61s (0:03:20) =================
...
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

**Honest note on flakiness:** during the follow-up verification, two full-suite
runs failed once each on environment-sensitive tests unrelated to this change —
`test_code_sandbox.py::test_kill_leaves_no_orphan_python_process` and (once)
`test_code_eval.py::test_injected_regression_makes_the_gate_fail` via its nested
`pytest` subprocess. Each passes in isolation and on rerun, and each failed on the
UNMODIFIED tree too when re-run under load. They are timing/process flakes, not
regressions from Phase 13. The final full gate above is green.

## Follow-up 2: per-field provenance (the live provider has no market cap)

The first follow-up still had the demo defect in a new form. The live provider for
US equities (yfinance `fast_info`) returns a price but **no market cap**, so the
cap always fell back to JDdS while the whole payload was labelled "verified".

- `scripts/yfinance_bridge.py` now carries `marketCap` when the provider exposes
  it; `fetchers/yfinance.ts` and `data-bridge.ts` pass it through.
- `finance_tools.get_market_snapshot` labels **each field** by origin: a value from
  a source that answered now is live; a value that fell back to the snapshot is
  annotated `— saved snapshot` with its stored time and source. The top-level
  `verified` flag is true only when the PRICE is live; `priceOrigin` and
  `marketCapOrigin` ride on the structured payload.
- Tests: `test_demo_live_price_but_no_live_cap_labels_the_cap_saved` (the real
  US-equity shape), plus the two earlier demo tests. `test_tools.py`'s
  `test_finance_tool_returns_grounded_snapshot` expectation changed from the exact
  line `Data source: JDDS (scraper)` to `saved snapshot` + `JDDS/scraper`, because
  provenance is now per field.

Gates re-run below.

## Follow-up 3: the general rule — the vault is a cache, not a precondition

Verification is a property of every data type, not just the price. Two
capabilities were still vault-bound:

- `fundamentals` (company profile) read the vault only. It now enriches from the
  live provider pipeline (SEC → FMP → Yahoo) when the vault lacks the profile and
  reports which answered (`profileSource`).
- `market_snapshot` returned UNAVAILABLE for a symbol outside the committed
  universe (and for a vault row with no price). `resolveAnyInstrument` now recovers
  a `not_found` for a known, covered market — the same rule `financial_statements`
  already followed — so a live quote serves it. The identity gate still refuses
  AMBIGUOUS / `not_covered` / wrong-currency answers.
- The yfinance bridge now carries `marketCap`.

Tests added: `data-bridge.test.ts` (profile enrichment + vault-hit short-circuit),
`data-bridge-phase2.test.ts` (live fallback for no-row and no-price).
`data-bridge-health.test.ts::records a failing route as a failure` updated: a
vault miss now falls back to live, so BOTH sources must fail for the route to be a
failure — the mock now also makes the live route empty. Why: the property is "a
route neither source can answer is a recorded failure", which is unchanged; only
the fixture had to reflect the new fallback.

