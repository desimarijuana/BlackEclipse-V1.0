---
title: Harness Phase 4 — Evidence-Grounded Answering
status: In progress
last-verified: 2026-09-23
---

# Harness Phase 4 — Evidence-Grounded Answering

**Phase:** 4 — Research mandates, answer validation, point-in-time evidence,
deterministic calculations, and evaluation
**Status:** In progress — Phase 5 web escalation + Phase 6 resilient multi-source research added + Phase 7 global market research

## Phase 7 — Global market research (2026-09-23)

**Brief.** Make Eclipse useful to people in any country, not US-centric. Observed
failures: market coverage lists countries but statements/instruments are not
retrievable; many international stocks unavailable; SEC attempted for non-US
listings (HTTP 400); web search/fetch UNAVAILABLE; JavaScript-only filings and
PDF reports; duplicate/ambiguous source-health rows; `get_coverage` telling the
agent to stop when JDdS lacks a ticker.

**Verified causes (reproduced against the live endpoints and the failing runs).**

Real international runs exist in `agent-memory.db` (TSMC `run_9810a931…`,
Samsung `run_ed480294…`, Petrobras `run_c5845c5f…`). Findings:

1. **The browser User-Agent is the 403 cause, not the hosts.**
   `web-research.ts` sends a Chrome UA. Through the real `safeGet` transport,
   SEC, TSMC IR (`investor.cld.tsmc.com`), `pr.tsmc.com` and
   `www.sec.gov/files/company_tickers.json` all return **403 with the browser UA**
   and **200 with a declared bot UA that includes a contact** (verified both
   ways). The SEC-filings `.htm` the agent needed returns 200 `text/html` with
   the declared UA. So "all web fetch UNAVAILABLE" was a self-inflicted 403.
2. **International tickers are stored WITHOUT the Yahoo suffix the user types.**
   The vault holds `2330` (TW), `005930` (KR), `PETR4` (BR); users ask for
   `2330.TW`, `005930.KS`, `PETR4.SA`. `resolveInstrument` receives the suffixed
   string, finds no exact row, and returns `not_found`: the failing TSMC run
   recorded "JDDS: 2330.TW is not in the Taiwan universe". Verified: bare `2330`
   with `market=TW` resolves; `2330.TW` yields `not_found`.
3. **SEC is attempted for a non-US issuer and returns HTTP 400.**
   `fundamentals_get_financials("2330.TW","TW")` ran strategy `SEC, JDDS`; the
   SEC bridge returned HTTP 400. The SEC adapter's `supports()` gate is
   `market === 'US'`, but the *retrieval planner* still lists `SEC` first for
   `financial_statements` regardless of market, and the bridge `secFilings` route
   passes the bare suffixed symbol to it.
4. **PDF and JSON/XML documents are dropped by the fetch layer.**
   `fetchWebPage` rejects any content-type without html/xml/text; TSMC's annual
   report PDFs and the SEC `.htm` files were all reported "not usable HTML". A
   PDF-only annual report is currently unreadable even when reachable.
5. **Source-health rows are duplicated and mis-keyed.** `sourceHealth()` emits a
   row per `(declared source × market × assetClass)` from `healthTargets()`
   (31 markets × 3 asset classes × 2 sources) but attaches a single market-level
   aggregate to each of those rows, so `JDDS (US, equity)` and `JDDS (US, etf)`
   share one counter and read as separate identical results; FX/CRYPTO are also
   pushed twice. Verified against the live aggregation logic.
6. **`get_coverage` instructs the agent to stop.** `finance_tools.py:200` tells
   the model "If a request targets a market/asset class not listed here, it is NOT
   COVERED — return UNAVAILABLE rather than trying another source"; it also
   advertises `financial_statements` for every listed market because only
   `current_quote` actually works there.

**Architectural outcomes (implemented).** A capability matrix that separates
market recognition / searchable universe / quote+history / fundamentals / official
filing routes / web+document routes / live health / period coverage / fixture-vs-
live-smoke, returned by `get_coverage` and phrased so the agent continues through
eligible routes. Health re-keyed by `(source, market, assetClass, dataType)` with
distinct counts/last-success/last-error and zero-attempts=`unknown`. Global
instrument identity that strips/normalizes Yahoo-style suffixes and honours an
explicit market. Provider eligibility routing (SEC skipped for non-US). Document
support for JSON/XML/XBRL and bounded text-PDF extraction, with scanned-PDF
reported as unsupported rather than fetched as noise. Per-leg statuses and the
persistent bounded research loop from Phase 6 reused unchanged.

**Known limits to carry.** OCR is unavailable (scanned PDFs are reported, not
read); some official hosts sit behind bot walls that redirect to a non-https
challenge (Canada SEDAR/ShieldSquare) and are therefore unreadable through the
https-only transport — reported, not bypassed. Live smoke coverage is opt-in and
per-route. Non-US statements are served live via the keyless yfinance bridge
(verified TSMC/Samsung); a market whose issuer yfinance does not cover still
reports a precise gap (see Follow-up 1/2 below).

**Implementation (files).** TS: `src/lib/harness/capability.ts` (capability
matrix), `markets.ts` (`EXCHANGE_SUFFIX_ALIASES`, `splitExchangeSuffix`),
`data-bridge.ts` (suffix-aware `resolveVaultInstrument`, re-keyed `sourceHealth`,
`capability_matrix` capability, extraction/language on `web_fetch`),
`web-research.ts` (declared email UA, PDF text extraction, JSON/XML/text
passthrough, `javascript_only`), `retrieval-diagnostics.ts`
(`unsupported_document`/`javascript_only`), `web-search.ts` (declared UA),
`fundamentals/providers/sec-edgar.ts` (exported `secAvailable`, email UA),
`app/api/harness/data/route.ts` (whitelist). Python: `retrieval/structured.py`
(`SecFilingsSource.eligible`, `infer_market_from_symbol`),
`research/escalation.py` (market-aware filing query), `finance_tools.py`
(`get_coverage` rewritten, `get_capability_matrix`, `get_source_health`),
`retrieval_tools.py` (`research_retrieve_source` surfaces category/extraction),
`prompts.py` (global routing + continue-through-eligible-routes),
`skills/learning.py` (`provider_eligibility_improvement`, diagnostics + scope),
`eclipse_memory/{schema,store}.py` (migration 4, diagnostics/scope columns),
`research/smoke.py` (non-US IR + PDF probes).

**Verification.** Python **460 passed** (was 423). New: `test_phase7_global.py`
(31), `test_phase7_skill_feedback.py` (6). Vitest **1633 passed** (127 files);
new `global-research.test.ts` (10) plus updated `data-bridge.test.ts`. `tsc`
clean. Live route verification (direct, not mocked): with the declared
email-contact UA, `www.sec.gov` filings HTML, the ticker map, `data.sec.gov`
XBRL JSON, and `investor.cld.tsmc.com` (TSMC IR) all return 200; the same
endpoints returned **403 with the previous browser UA** — the verified cause of
"all web fetch UNAVAILABLE". A scanned/image PDF correctly reports
`unsupported_document`. Live smoke is operator-triggered and separate
(`npm run test:smoke`).

**Follow-up — non-US statements are now reachable (2026-09-23).** The first cut
still left non-US statements unreachable: `financialStatements` read ONLY the
`FundamentalsCache` table, so a market with no committed snapshot returned
`no_data` even though the keyless yfinance bridge serves it (verified:
`yfinance_fundamentals.py 005930.KS` returns full KRW statements; the provider
`isConfigured`/`supports` are keyless and `market`-agnostic). Fixed by adding a
**live provider fallback** to `financialStatements` that reuses the EXISTING
`getFundamentals` service (SEC → FMP → yfinance) and persists its result — no
second pipeline. Live-verified end-to-end: `getFundamentals("005930","KR")` →
yahoo/KRW 4 periods (latest FY2025 revenue 333.6T KRW); `getFundamentals("2330","TW")`
→ yahoo/TWD 5 periods. The capability matrix was corrected to report non-US
fundamentals as `configured` when the keyless vendor is usable (it previously
claimed `unconfigured`, which understated real coverage), and the JDDS source now
labels the REAL provider (`provider`/`statementSource`) instead of always saying
"JDDS" — a provenance lie would be worse than a missing value. Python 460 passed;
Vitest **1633 passed**; `tsc` clean.

**Follow-up 2 — local official filing routes + bounded redirects (2026-09-23).**
Workstream D: each market now has a locally authoritative filing hint
(`LOCAL_FILING_HINTS` in `retrieval/web.py`) used by the escalation query —
Taiwan MOPS, Korea DART, Japan TDnet, HKEXnews, India BSE/NSE, UK Companies
House, Brazil CVM, Canada SEDAR, ASX, SGX, Bursa, SET, IDX, PSX, Tadawul, etc. —
and the classifier labels those regulator/exchange hosts as `primary`. A generic
fallback covers markets with no hint. Verified live: Korea DART fetches 200 with
`lang=ko` (original language preserved); the classifier returns `primary` for
MOPS/DART/SEDAR hosts.

Discovered and fixed a real transport gap: `safeGet` refused ALL redirects, but
official regulator hosts commonly 301/302 (Taiwan MOPS, Canada SEDAR). Added
**bounded redirect following that re-validates every hop** through the same
`validateOutboundUrl` + DNS-pinned gate, https-only, default 0. Verified live:
MOPS now follows to its (JavaScript-only) shell and is categorised
`javascript_only`; SEC/TSMC unaffected. **Limitation (honest):** Canada SEDAR is
behind a ShieldSquare bot wall that redirects to an `http://perfdrive.com`
challenge, which the https-only guard correctly REFUSES — SEDAR is therefore not
readable from this transport, and that is reported, not bypassed.

Vitest **1648 passed** (128 files; new redirect-guard tests in `security.test.ts`);
Python **464 passed**; `tsc` clean.

## Phase 6 — Resilient, multi-source research (2026-09-23)

**Brief.** The NVDA test (`run_74f251a6-…`, plus `run_c2ce2c1f-…`) returned only
FY2019 from JDdS; every official web source, SEC endpoint and NVIDIA IR page
returned `UNAVAILABLE`; the run stopped with no verified answer. The goal is not
just more JDdS coverage: every web fallback route shares one transport whose
failures are opaque.

**Verified root cause (evidence, not assumption).** Three independent defects,
all reproduced directly against the live endpoints:

1. **Search failure was indistinguishable from zero results.**
   `webSearch()` (`src/lib/web-research.ts:40`) does `if (!res.ok) return []` and
   `catch { return [] }`. DuckDuckGo's HTML endpoint now answers with **HTTP 202
   and a ~14 KB anti-bot page** (`result__a` count = 0). 202 passes `res.ok`, so
   cheerio parses a page with no result anchors and the caller receives `[]` — the
   same value as a genuine empty search. Evidence: every `research_search` in the
   failed run returned in 485–1515 ms with no error; a direct fetch of
   `https://html.duckduckgo.com/html/?q=…` returns status 202, 14 KB, 0 result
   anchors.
2. **A valid SEC JSON response was rejected as "not usable HTML".**
   `fetchWebPage()` (`web-research.ts:100`) requires `contentType` to contain
   `html`/`xml`/`text`. `https://data.sec.gov/api/xbrl/companyconcept/…json`
   returns **HTTP 200 `application/json`** (verified), so the JSON facts the agent
   needed were fetched successfully and then thrown away. The SEC browse-edgar
   and filing `.htm` URLs return `200 text/html`; NVIDIA IR
   (`investor.nvidia.com/…/annual-reports`) returns **403** for non-browser
   clients (verified).
3. **There was no independent route and no diagnostic trail.** All four attempted
   web sources (DDG search, SEC XBRL JSON, SEC browse-edgar, NVIDIA IR) share the
   one `web-research.ts` transport; `escalation.py` inspects only
   `status == "OK"` and discards the reason, so receipts read "no pages
   retrieved" with no cause and the run cannot explain which capability failed.

**Architectural outcomes.** Structured failure diagnostics on the shared
transport (provider/tier/httpStatus/latency/timeout/resultCount/bytes/parse/
category/retryable) and a bounded health probe; SEC XBRL as an independent
`financial_statements` source with a planner-visible tier; a second,
operator-configurable search provider behind the existing settings vault; a
deterministic provider-selection policy; a resilient per-leg loop (bounded
retries, provider switching, unresolved-leg targeting, budget stop-reason); and
a keep-going final response that reports every verified fact plus what routes
failed and why.

**Known limits to carry.** The JDdS statement snapshot still has no per-period
consolidation basis for all issuers and a multi-year coverage gap; the SEC route
covers US issuers only. Skill-candidate review/promotion (brief Outcome 6) is
deferred to a follow-up and remains operator-gated.

**Implementation (files).** TS: `src/lib/retrieval-diagnostics.ts` (diagnostic
contract), `src/lib/web-search.ts` (independent search providers incl. the
operator-configurable JSON API), `src/lib/web-research.ts` (diagnosed fetch +
facade), `data-bridge.ts` (`sec_filings`, `research_health`, diagnostics on
`web_search`/`web_fetch`), `provider-keys.ts`/`providers/directory.ts`
(`SEARCH_API_CONFIG`/`SEARCH_API_KEY`), `fundamentals/providers/sec-edgar.ts`
(`fetchSecCompanyFacts`). Python: `retrieval/retry.py`, `retrieval/structured.py`
(`SecFilingsSource`), `retrieval/{planner,web,layer,normalize,sources,contract}.py`,
`research/{engine,run,receipt,escalation}.py`, `finance_tools.py`
(`get_research_health`), `research/eval/nvda.py` + `dataset_nvda_v1.json`,
`research/smoke.py`.

**Verification.** Python **423 passed** (was 404). New tests:
`test_phase6_resilience.py` (16), `test_phase6_nvda_eval.py` (3). Vitest **1619
passed** (126 files) including `retrieval-diagnostics.test.ts` and
`data-bridge-phase6.test.ts`. `npx tsc --noEmit` clean; eslint clean on the new
modules. Evaluations (`python -m harness.research.eval`): semantic-support 8/8
(`669e70f0…`), escalation 8/8 (`c28e7de5…`), **NVDA labeled regression 5/5,
coverage accuracy 1.0, precision 1.0, 0 false accepts (`fd3c7efa…`)**. Live smoke
checks are operator-triggered and separate from the default suite
(`npm run test:smoke`, contacts DuckDuckGo/SEC only).

## Phase 5 — Bounded web escalation (2026-09-23)

## Phase 5 — Bounded web escalation (2026-09-23)

**NVDA receipt root cause (run `run_f1a3dd8b-…`).** A structured source returned
only an unrelated FY2019 row and all four legs came back `unknown`. Three
compounding bugs, all now fixed and entity-agnostic (nothing is special-cased to
NVDA or any ticker):

1. **Packet truncation by object order.** `synthesis.build_evidence_packet` did a
   blind `objects[:20]`. `normalize_fundamentals` emits period-by-period, so the
   first 20 objects of a multi-year statement were ALL the oldest fiscal year —
   the model never saw FY2024/FY2025. Fixed: requested metrics/periods are
   surfaced first (`_select_objects`), so the packet always contains the facts
   the mandate asks for.
2. **Missing basis blocked the value.** The vault rows carry `basis=null` while
   the mandate required `consolidated`, so every leg became `unknown`. The JDdS
   statement snapshot genuinely lacks a per-period basis field. Fixed: a missing
   *qualifying* field yields `qualified` (value present, basis disclosed as
   unconfirmed), not a hard failure.
3. **No escalation path existed.** `WebResearchSource.dataTypes` excluded
   `financial_statements`, so WEB could never be planned for a statement leg.
   Fixed: WEB serves statements, and `engine.run_research` escalates unsatisfied
   legs through a bounded primary→secondary search/fetch/extract/validate path.

**New modules.** `research/budget.py` (search/fetch/page/time/token caps +
exhaustion record), `research/web_facts.py` (span-anchored deterministic
extraction/validation; page text is untrusted), `research/escalation.py`
(primary→secondary hierarchy), plus additive `EvidenceRef` provenance fields,
`ResearchReceipt.escalation`/`budget`, and `NormalizedFinancialObject` revision
fields. Coverage gained `qualified`, `no_matching_period`, `stale`.

**Verification.** Python suite **403 passed** (was 371). New tests:
`test_research_escalation.py` (17), `test_research_escalation_engine.py` (11),
`test_research_eval_escalation.py` (4). Evaluations (`python -m
harness.research.eval`): semantic-support dataset `1.0.0`
(`669e70f0…`) 8/8, 0 false accepts; escalation dataset `1.0.0`
(`c28e7de5…`) 8/8, precision 1.0, 0 false accepts. `tsc --noEmit` clean;
Vitest 1604 passed (124 files, 0 failed).

**Known limits.**

- Restatement chains remain `unavailable` until a provider exposes revision
  metadata (unchanged from Phase 4).
- When neither primary nor secondary web sources expose a requested value, the
  answer is an honest partial naming the exact missing field and the attempted
  paths; the escalation eval measures precision/coverage, not semantic accuracy.
- The JDdS statement snapshot has no per-period consolidation basis; a
  `consolidated` mandate therefore yields `qualified` legs from the vault. A
  provider-side basis field is the real fix and remains a documented gap.

**Next action:** add a provider-side consolidation-basis field so statement legs
can be `covered` rather than `qualified` from the vault, and wire a model-critic
slice into the semantic evaluation (advisory only).

## Milestone 0 — Audit (2026-09-23)

**Baseline:** `node scripts/test-python.js` → **266 passed** (6.12s). Vitest and
`tsc` are unaffected until the TS surface changes (Phase 4 is Python-only).

**Where the seam is (source-authoritative).**

- `retrieval/contract.py` — provider-agnostic request/result/evidence models:
  `FinancialRetrievalRequest`, `FinancialRetrievalResult`, `EvidenceItem`,
  `NormalizedFinancialObject`, `InstrumentIdentity`, `SourceReference`.
  `NormalizedFinancialObject` already carries `name/value/unit/currency/
  dataTimestamp/period/instrument/identity/source`, but **not** a consolidation
  `basis` or a per-observation `publishedAt`.
- `retrieval/layer.py` — `FinancialRetrievalLayer.retrieve()` is the one
  orchestration seam tools call. Single-best vs multi-source, conflict
  resolution, D2 truncation, D3 top-level degradation, D1 durable replay.
- `retrieval/cache.py::key_for` — cache identity is
  `dataType|instrument|market|quantity|query`; **no** temporal cutoff today.
- `retrieval/planner.py` — deterministic per-data-type source order; removes WEB
  for precise types.
- `retrieval_tools.py` — the agent-facing tools; each builds a request and calls
  `_layer(ctx)`, whose event logger forwards `retrieval.*` to the run emitter.
- `graph.py` — `execute_run` builds the LangGraph, injects memory, writes the
  terminal status exactly once. **No answer gate exists** between the model's
  final text and `completed`.
- `persistence.py` — `agent-memory.db`, idempotent DDL + `_migrate()` ADD
  COLUMN. Owns `HarnessRun/HarnessEvent/HarnessToolExecution/RetrievalRecord`.
  This is the correct home for a research receipt; `eclipse-memory.db` is the
  separate Phase-3-M control DB (never market facts).
- `events.py` — `RunEmitter` (seq + persist + bus). New research events ride it.
- `schemas.py` / `main.py` — the wire contracts + FastAPI endpoints.

**Key finding — the gap.** Retrieval produces provenance, identity, freshness and
conflicts, but nothing turns a user *objective* into an explicit set of required
facts, checks that each fact is covered by admissible evidence, validates the
model's citations against that evidence, or gates the final answer. `derived_metric`
is a data type with no calculation implementation; Sharpe is left to the model.

**Smallest end-to-end flow chosen.** A period-over-period company financial
comparison: objective → mandate (entities + metric legs) → one retrieval per leg
through the existing layer/tools → deterministic per-leg coverage → structured
claims → deterministic citation/metadata validation → research receipt.

**Decisions taken (recorded here, mirrored in `decisions.md` as ADR-H15..H19).**

1. Phase 4 is a **new Python package `python/harness/research/`**, reusing the
   retrieval layer; no new agent loop, no new data plane, no TS logic.
2. Two **additive** optional fields on `NormalizedFinancialObject` (`basis`,
   `publishedAt`) carry consolidation basis and point-in-time availability
   without breaking existing providers.
3. The answer gate is **deterministic** (ID existence, field compatibility,
   coverage, admissibility, conflict visibility). Semantic entailment is
   reported as `needs_review`/unverified, never asserted as verified.
4. Receipts persist in `agent-memory.db` (existing ownership), one additive
   table, never in `eclipse-memory.db`.
5. The cutoff `asOf` enters the retrieval **cache key** through request metadata.

**Migration implications.** Additive pydantic fields and idempotent DDL only; no
data backfill, no rewrite of existing rows. Existing tests must stay green.

## Milestones 1–8 — implementation (2026-09-23)

All milestones implemented and exercised by tests. Files:

| File | Milestone |
|---|---|
| `python/harness/research/mandate.py` | 2 — typed mandate + narrow classifier |
| `python/harness/research/coverage.py` | 3 — per-leg coverage gate |
| `python/harness/research/claims.py` | 4 — structured claims + validator |
| `python/harness/research/calculations.py` | 6 — derived metrics |
| `python/harness/research/citations.py` | 4/8 — citations + response metadata |
| `python/harness/research/failures.py` | 3 — failure classification |
| `python/harness/research/receipt.py` | 7 — durable receipt |
| `python/harness/research/engine.py` | 8 — orchestration |
| `python/harness/retrieval/contract.py` | 5 — additive `basis`/`publishedAt`, `asOf` |
| `python/harness/retrieval/cache.py` | 5 — `asOf` in cache identity |
| `python/harness/retrieval/normalize.py` | 5 — basis/publishedAt on statement rows |
| `python/harness/persistence.py` | 7 — `ResearchReceipt` table + accessors |
| `python/harness/service.py` | 8 — `build_bridge`/`retrieve_for_research` |
| `python/harness/main.py` | 8 — `/research/*` endpoints |
| `python/tests/test_research_calculations.py` | 1/6 — 19 tests |
| `python/tests/test_research_flow.py` | 1–5/8 — 29 tests |
| `python/tests/test_research_receipt.py` | 7/8 — 13 tests |

**Tests:** the three new files add 61 tests. Full suite **327 passed** (was 266).
`npx tsc --noEmit` clean; `npm run test` = 1613 Vitest + 327 pytest, all green.

**Bugs found and fixed during testing:** the engine deduplicated a
never-populated local list instead of `outcome.evidence` (empty evidence in the
end-to-end path); validator gaps were not merged into `unresolved`; and
`period_change`'s default marker dates sorted incorrectly (`"end"` < `"start"`).

**Deferred / known limits.**

- The model-backed synthesizer is not yet wired into the live chat run — the
  deterministic mandate/coverage/validation engine and endpoints are complete,
  but production chat still uses the Phase-1–3 answer path until the synthesizer
  is injected. This is the next action.
- Semantic entailment remains `needs_review` (ADR-H17); no labeled evaluation set
  exists yet to measure false accepts/rejects.
- Evidence supersession/restatement links are recognised as fields but no
  supersession chain is populated by providers yet.

**Next action:** wire a model-backed `SynthesizeFn` into `execute_run` for
supported mandates (parse structured JSON claims → `validate_claims` →
`render_prose`), add the TS proxy for `/research/*`, and expose the response
metadata in the chat surface.

## Follow-up — wire and harden Phase 4 in live chat (2026-09-23)

All five follow-up workstreams implemented. 61 → now **371 Python tests** (was
327); Vitest **1614**; `tsc --noEmit` clean.

**Workstream 1 — deterministic matching + stable identifiers.** Confirmed the
three reported conditions were present and fixed them:

- `research/periods.py` (new) — canonical annual/quarter/date/range parsing.
  Replaces the substring-of-digits test that let `FY2024` match `20244` or a
  quarter. An explicit fiscal label never cross-matches granularity; a date
  `dataTimestamp` may satisfy the annual/quarter leg it falls inside.
- `research/coverage.py` — a required unit/currency/basis/instrument that the
  evidence **omits** is now `unknown`, never covered; identity is compared on the
  strongest supplied field (canonical identity → instrument → market).
- `research/ids.py` (new) — SHA-256 digests over canonical JSON replace the
  salted built-in `hash()`. Receipt evidence hashes are now content+provenance
  sensitive and reproducible across processes; calculation ids include version,
  formula, inputs, window, assumptions and value, so distinct values for the same
  dates never collide.
- `research/receipt.py` / `research/calculations.py` — switched to the digests.
- Tests: `python/tests/test_research_hardening.py` (19), including a
  cross-process determinism test that spawns a fresh interpreter.

**Workstream 2 — live-chat integration.** `research/synthesis.py` (new) is a
bounded, tool-less, memory-free `ModelSynthesizer` that receives only the
mandate, a bounded evidence packet and the coverage report; its output is strict
JSON + Pydantic. `research/run.py` (new) orchestrates the gated flow;
`graph.execute_run` routes an unambiguous supported comparison into it **before**
the agent graph (no duplicate retrieval). A supported request is never silently
downgraded: a synthesis/model-init failure yields an honest partial/rejected
result. The classifier was hardened — `ResearchMandate.supported` now requires a
single entity, two periods and no ambiguity, so a company-vs-company or vague
"growth" ask falls back to the existing path. Unsupported-claim text is never
echoed into the answer (it may embed a fabricated figure).
Tests: `python/tests/test_research_live.py` (11) — success, partial, fallback,
invalid JSON, unsupported claim, repair→success, repair→reject, provider failure,
model-init failure, receipt persistence/cancellation.

**Workstream 3 — surface metadata + receipts.** Additive `research` blob on
`HarnessRun` (idempotent column) and `RunResult`; the chat stream's `client.final`
carries `research`; TS contracts (`ResearchRunInfo`/`ResearchMetadata`), a
read-only `GET /api/harness/runs/[id]/receipt` route, and a frosted-glass
`ResearchEvidencePanel` render coverage/citations/claims/gaps inline. Content
never says "verified" for a `needs_review` claim. Older runs and ordinary chat
carry no `research` (fully backward compatible).

**Workstream 4 — semantic-support evaluation.**
`python/harness/research/eval/` holds `dataset_v1.json` (8 human-labeled
claim/evidence pairs, versioned + SHA-256 checksummed) and a deterministic
baseline judge that never sees the label. Runner: `python -m harness.research.eval`
(via `PYTHONPATH=python`). Current metrics — dataset `1.0.0`,
checksum `669e70f0a8aa0ef862a6429cbe2e1a71`, 8 cases, accuracy 1.0,
**falseAccepts 0**, falseRejects 0, per-slice reported. Not marketed as a truth
guarantee; production status stays `needs_review` where support is unproven.

**Workstream 5 — supersession / restatement.** `research/supersession.py` (new)
builds a chain ONLY from explicit source metadata (`supersedesEvidenceId` +
`relationshipKind` in `{amends,restates,corrects,withdraws}`), rejects
dangling/cyclic/unknown-kind links, resolves `asOf` availability, and keeps
history. **Audit finding:** the vault `financial_statements` payload exposes a
filing `form`/`filed` date but no accession number, amendment indicator or
restatement relationship, and persists only the latest snapshot — so restatement
coverage is currently reported `unavailable`. No links are manufactured. Tests:
`python/tests/test_research_supersession.py` (8).

**Known limits / deferred.**

- Restatement chains remain `unavailable` until a provider exposes a reliable
  revision contract (accession/amendment metadata). Documented, not faked.
- The semantic judge is a deterministic baseline; no model-critic comparison is
  wired (the framework for one exists and is deliberately advisory-only).
- The chat panel is a compact inline surface; a full run-detail receipt viewer
  reuses the existing run route rather than a new page.

**Next action:** add a real model-critic slice to the evaluation (compared
against human labels, advisory-only), and extend supersession coverage if a
provider starts emitting revision metadata.

This phase strengthens the existing Python harness by connecting retrieval and
provenance to explicit answer requirements and a final validation gate. It does
not replace Phase 1–3-M, add a parallel financial data plane, or make the LLM
the authority on whether its answer is supported.

The implementation prompt is in
[`phase-4-opencode-prompt.md`](./phase-4-opencode-prompt.md). Update this tracker
as implementation proceeds: audit, milestones, decisions, files, checks, known
gaps, and next action.

## Definition of done

- A narrow financial-comparison flow uses a validated research mandate,
  deterministic coverage classification, evidence-linked claims, and a final
  answer validation gate.
- Invalid citations, mismatched identity/metric/period/basis, unresolved
  conflicts, and material coverage gaps cannot silently pass as verified.
- Point-in-time cutoffs are explicit; unknown publication times remain unknown.
- Named derived metrics are deterministic and carry input provenance/assumptions.
- A durable research receipt makes mandate-to-answer decisions inspectable.
- An evaluation set covers retrieval, identity, period/basis, temporal, citation,
  conflict, missing-data, and calculation behavior.
- Existing phases remain compatible and repository-required checks pass.

## Milestones

| # | Milestone | Status |
|---|---|---|
| 0 | Audit graph, retrieval, persistence, contracts, and UI surfaces | Done |
| 1 | Baseline evaluation cases and metrics | Done |
| 2 | Research mandate contract and narrow task classifier | Done |
| 3 | Evidence coverage gate for financial comparisons | Done |
| 4 | Structured claims and deterministic citation/metadata validator | Done |
| 5 | Point-in-time evidence cutoff | Done |
| 6 | Deterministic derived-metric calculations | Done |
| 7 | Research receipt persistence and inspection surface | Done |
| 8 | Regression, compatibility, documentation, verification | Done |
| F1 | Deterministic matching + stable identifiers | Done |
| F2 | Live-chat integration (model synthesizer, bounded repair) | Done |
| F3 | Run-result + chat evidence surface | Done |
| F4 | Semantic-support evaluation set + metrics | Done |
| F5 | Supersession / restatement chain | Done (source-grounded; coverage `unavailable` pending provider metadata) |

## Initial implementation boundary

Start with period-over-period company financial comparisons. Keep model-based
semantic entailment out of the initial hard gate: enforce evidence ID existence,
field compatibility, coverage, explicit gaps, and conflict handling first. Add
semantic support scoring only when a labeled evaluation set can measure false
accepts and false rejects.

