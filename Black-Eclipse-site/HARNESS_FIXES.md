# HARNESS_FIXES.md — data-integrity remediation (D1–D12)

Branch: `fix/harness-data-integrity`

Root artefacts:

- `scripts/repro_harness_defects.py` — offline reproduction through the REAL
  tool/layer surface.
- `scripts/repro_baseline.txt` — output **before** the fixes (0/10).
- `scripts/repro_after.txt` — output **after** the fixes (10/10).
- `python/tests/test_harness_data_integrity.py` — 32 regression tests.
- `src/lib/harness/data-bridge-statements.test.ts` — statement cache contract.
- `scripts/capability-matrix-check.ts` — capability-matrix CI gate.

## Reconnaissance map

| ID | Owning code | Root cause | Confidence |
|----|-------------|------------|------------|
| D1 | `market/gateway.py::_dispatch`; `retrieval/authority.py::decide_source`; `finance_tools.py::get_market_snapshot` | Quality was per-provider; the first success won. No cross-source comparison step; the retrieval conflict key included the timestamp, so two sources with different clocks never compared. | High |
| D2 | `src/lib/harness/data-bridge-statements.ts`; `retrieval/layer.py::_finalize_single` | Cache freshness used the fetch timestamp, not the reported period end. A fresh write around an FY2018 payload looked current. No cache-key version. | High |
| D3 | `market/instruments.py::classify_identifier`; `market/gateway.py::get_fx_rate`; `retrieval_tools.py::market_get_quote`; `market/research_tools_ext.py::get_currency_conversion` | Three separate pair-resolution paths; `USDPKR`/`USD-PKR` were classified as equity; quote bypassed the FX gateway. | High |
| D4 | `retrieval/authority.py::_is_stale`; `retrieval/policies.py` | One global 12h macro window, cadence-blind. | High |
| D5 | `market/research_tools.py::get_provider_health` | Read only in-process router counters (always 0 on a fresh process), never the recorded `source_health` ledger. | High |
| D6 | `retrieval/health.py`; `retrieval/layer.py::retrieve` | Health only reordered sources; it never demoted/skipped a 0-success route. | High |
| D7 | `src/lib/harness/capability.ts`; `scripts/eval-capability-matrix.ts` | Contradiction was flagged but had no mismatch block naming both values/config key; CI gate had no exception allowlist and did not fail on an injected contradiction in tests. | High |
| D8 | `finance_tools.py::get_news` | Items with no date were returned in time-sensitive answers without an `undated` flag or filtering. | High |
| D9 | `retrieval/retry.py`; `retrieval/web.py` | `is_retryable` retried every ERROR, including definitive 4xx; no body cache; no achieved success-rate report. | High |
| D10 | `tools.py::ToolRegistry.execute` | `TOOL_NOT_FOUND` had no suggestions and no structured data. | High |
| D11 | `retrieval_tools.py::research_retrieve_source` | A zero-text fetch returned `status: OK` with an empty body. | High |
| D12 | new `market/quality_contract.py`; tool finalizers | Each surface had its own quality vocabulary; no shared envelope/invariant. | High |

## Defect → fix → test

| ID | Fix | Regression test |
|----|-----|-----------------|
| D1 | Shared verdict enum + `compare_values` (1% default, round-factor detection). Gateway compares the answering provider against the next eligible one; retrieval compares quote prices across providers even with different clocks. Both candidates/providers/timestamps are preserved; conflicts persist to `MarketQualityEvent` and surface in `get_data_provenance`. | `test_d1_ohlcv_cross_source_is_divergent_not_valid`, `test_d1_snapshot_never_returns_a_valid_blend`, `test_d1_scale_mismatch_names_the_factor` |
| D2 | Newest **period end** drives age: annual 548 days, quarterly 150. Cache key version `2`; stale cache falls through to the provider chain; failure returns `STALE` + `stale=true` + `periodEnd`/`periodAgeDays`. | `test_d2_old_statement_period_is_named_stale`, `test_d2_recent_statement_is_not_stale`, TS `data-bridge-statements.test.ts` |
| D3 | `normalize_fx_pair` accepts `USD/PKR`, `USDPKR`, `USDPKR=X`, `USD-PKR`; FX needs no venue. All three entry points route through `MarketDataGateway.get_fx_rate`. | `test_d3_all_fx_entry_points_agree_or_refuse_identically`, `test_d3_pair_spellings_normalise_to_one_instrument`, `test_d3_fx_has_no_venue_requirement` |
| D4 | `retrieval/freshness.py` policy registry keyed by provider/series/cadence, business-day + holiday-aware; intraday stays tight. | `test_d4_daily_series_is_valid_one_business_day_later_and_stale_after_five`, `test_d4_weekend_is_not_staleness`, `test_d4_intraday_keeps_a_tight_window` |
| D5 | `get_provider_health` reads the recorded `source_health` ledger first; zero runs ⇒ `UNKNOWN`, never a healthy zero. | `test_d5_provider_health_reads_the_recorded_run_ledger`, `test_d5_zero_runs_is_unknown_not_healthy`, `test_d5_the_two_health_surfaces_agree_on_every_shared_route` |
| D6 | `apply_breaker` demotes a 0-success route after ≥5 recorded failures (env `HARNESS_ROUTE_BREAKER_THRESHOLD`); half-open probe after cooldown; skipped routes appear in diagnostics as `skipped_by_breaker`. | `test_d6_dead_route_is_skipped_and_named` |
| D7 | Observed stays ledger-derived at read time; `mismatch` block names declared/observed/configKey; CI gate `capability-matrix-check.ts` fails unexplained mismatches and supports a dated allowlist. | `test_d7_ci_check_passes_on_the_real_matrix`, `test_d7_ci_check_fails_on_an_injected_contradiction`, `capability.test.ts` |
| D8 | Every item carries `undated`; `latest/today/recent` queries filter undated server-side and report `excludedUndated`; provider dates preserved verbatim. | `test_d8_undated_news_is_flagged_and_excluded_from_latest`, `test_d8_dated_news_preserves_timestamp_and_timezone`, `test_d8_undated_items_are_returned_in_a_non_time_sensitive_query` |
| D9 | `FetchQuality`: bounded exponential retry only for timeout/transport/5xx/429 (never definitive 4xx), URL body cache with distinct cache-hit reporting, browser escalation when static text is empty and the page is client-rendered, achieved success-rate per route. `WebResearchSource` uses it. | `test_d9_retries_transients_and_reaches_the_success_floor`, `test_d9_definitive_4xx_is_never_retried`, `test_d9_cache_hits_are_reported_distinctly` |
| D10 | Levenshtein ≤2 suggestions in `TOOL_NOT_FOUND` data; `autoExecuted: false` — nothing runs automatically. | `test_d10_typo_returns_suggestions_without_auto_executing` |
| D11 | Zero extractable text ⇒ `IMAGE_ONLY` (OCR available) or `OCR_UNAVAILABLE` naming the missing capability; never an empty success. | `test_d11_empty_extraction_is_image_only_or_ocr_unavailable` |
| D12 | One `DataQualityEnvelope` with value/unit/currency/provider/observation+retrieval timestamps/native cadence/verdict/conflicts/routesSkipped/stale/reasonCode. Market tools, retrieval tools, snapshot and FX/conversion emit it. Invariant rejects VALID with conflict/stale/zero provider. | `test_d12_valid_with_conflict_is_rejected_by_the_invariant`, `test_d12_valid_with_zero_providers_is_rejected`, `test_d12_valid_with_stale_observation_is_rejected`, `test_d12_market_and_retrieval_tools_emit_the_envelope` |

## Before / after evidence (pasted from real runs)

Baseline (`scripts/repro_baseline.txt`):

```text
D1 FAIL - ohlcv quality=valid conflict=no close=386.53000000000003; snapshot quality= sides=['JDDS']
D2 FAIL - status=OK stale=False periodEnd=None
D3 FAIL - fx=UNAVAILABLE/None/None; conversion=UNAVAILABLE/None/None; quote=UNAVAILABLE/None/None
D4 FAIL - ModuleNotFoundError: No module named 'harness.retrieval.freshness'
D5 FAIL - provider health={"yahoo": [0, 0], "binance": [0, 0], ...}
D6 FAIL - price_history called=True diagnostics=[]
D7 FAIL - capability-matrix-check.ts missing
D8 FAIL - count=8 excluded=None flagged=True
D9 FAIL - ModuleNotFoundError: No module named 'harness.retrieval.fetch_quality'
D10 FAIL - code=TOOL_NOT_FOUND suggestions=[]

0/10 defect reproductions pass
```

After (`scripts/repro_after.txt`):

```text
D1 PASS - ohlcv quality=warning conflict=yes close=386.53000000000003; snapshot quality=scale_mismatch sides=['JDDS']
D2 PASS - status=STALE stale=True periodEnd=2018-09-29
D3 PASS - fx=OK/276.51/2026-10-23T10:00:00Z; conversion=OK/276.51/2026-10-23T10:00:00Z; quote=OK/276.51/2026-10-23T10:00:00Z
D4 PASS - tolerance=259200s (Thursday 86400s, 5 business days 604800s)
D5 PASS - provider health={"JDDS": [0, 423], "yfinance": [634, 0]}
D6 PASS - price_history called=False diagnostics=[{"provider": "LIVE_STRUCTURED", ..., "normalizedStatus": "skipped_by_breaker", ...}]
D7 PASS - [capability-matrix-check] PASS (34 markets; every contradiction is explained)
D8 PASS - count=0 excluded=8 flagged=True
D9 PASS - {"liveFetches": 24, "cacheHits": 20, "successes": 40, "retries": 4, "successRate": 1.0}
D10 PASS - code=TOOL_NOT_FOUND suggestions=['get_historical_prices']

10/10 defect reproductions pass
```

Tests actually run:

```text
$ python -m pytest python/tests/test_harness_data_integrity.py -q
32 passed

$ npx vitest run src/lib/harness/phase4-routes.test.ts src/lib/harness/data-bridge-statements.test.ts
14 passed

$ npx vitest run src/lib/harness
501 passed (before the fixture update), then 502 passed after
```

(Full Python suite was started — 8,296 collected — and the harness/finance
subsets relevant to this change all pass: 32 + 68 + 52 + 110 + the existing
market/research tests.)

## OPEN / residual limitations

- **D11 OCR backend.** The fix classifies image-only documents honestly. Actual
  OCR extraction still depends on the OS OCR backend (`winocr`/`tesseract`);
  when absent the tool returns `OCR_UNAVAILABLE` by design. We did not bundle an
  OCR binary.
- **D9 browser escalation.** Escalation fires only when the bridge marks a page
  `clientRendered`/`javascriptOnly`. The static extraction path cannot itself
  prove client rendering; a page that returns empty text without that marker is
  reported as `unsupported_document`, not silently browsed.
- **D4 holiday calendar.** Business-day tolerance uses the existing US-equity
  holiday calendar. Non-US macro release calendars are not modelled; a route can
  declare its own cadence via policy but releases specific to other jurisdictions
  are not holidays in this calendar.
- **D12 coverage.** The envelope is emitted by the market tools, the retrieval
  market/statement/macro tools, the snapshot tool and FX conversion. Legacy tools
  that return a raw `dumps(payload)` (e.g. `get_fundamentals` profile dump) still
  return their provider payload without the envelope; they should be migrated
  when their provider shape is frozen.
- **D2 statement freshness** in Python is based on the newest reported period.
  A provider that legitimately reports only a lagging annual period now returns
  explicit STALE rather than “latest”; consumers must handle `status: "STALE"`.
