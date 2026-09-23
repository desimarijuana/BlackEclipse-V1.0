---
title: Harness Phase 4 — Evidence-Grounded Answering
status: In progress
last-verified: 2026-09-23
---

# Harness Phase 4 — Evidence-Grounded Answering

**Phase:** 4 — Research mandates, answer validation, point-in-time evidence,
deterministic calculations, and evaluation
**Status:** In progress — Milestone 0 complete

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
| 7 | Research receipt persistence and inspection surface | Done (engine + persistence + API; UI surface deferred) |
| 8 | Regression, compatibility, documentation, verification | Done (engine/endpoints; live-chat synthesizer wiring deferred) |

## Initial implementation boundary

Start with period-over-period company financial comparisons. Keep model-based
semantic entailment out of the initial hard gate: enforce evidence ID existence,
field compatibility, coverage, explicit gaps, and conflict handling first. Add
semantic support scoring only when a labeled evaluation set can measure false
accepts and false rejects.

