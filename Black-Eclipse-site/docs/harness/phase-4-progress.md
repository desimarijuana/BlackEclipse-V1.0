---
title: Harness Phase 4 — Evidence-Grounded Answering
status: In progress
last-verified: 2026-09-23
---

# Harness Phase 4 — Evidence-Grounded Answering

**Phase:** 4 — Research mandates, answer validation, point-in-time evidence,
deterministic calculations, and evaluation
**Status:** In progress — Phase 5 web escalation added

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

