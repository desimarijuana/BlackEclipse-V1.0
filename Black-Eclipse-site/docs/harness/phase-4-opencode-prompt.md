# OpenCode Implementation Prompt — BlackEclipse Harness Phase 4

You are continuing work in the BlackEclipse repository. Implement **Harness
Phase 4: Evidence-Grounded Answering** in the existing Python agentic runtime.
The goal is to make research answers auditable and materially reduce unsupported
financial claims by enforcing a path from user objective → research mandate →
retrieval → evidence coverage → structured claims → validated answer.

Do not stop after proposing a plan. Audit first, then implement the milestones
below in small, reviewable steps, update progress docs as you go, run required
checks after each coherent change, and finish with a concise report of files,
behavior, checks, and limitations.

## Product and architecture context

- The agentic runtime is **Python** under `Black-Eclipse-site/python/harness/`
  (FastAPI + LangChain + LangGraph). Agents, tools, prompts, retrieval,
  persistence, and events are Python-authoritative.
- Next.js is the front door: validates inputs, resolves LLM configuration,
  serves the read-only JDdS bridge, and proxies runtime APIs. Do not implement an
  agent loop, financial retrieval planner, model adapter, or answer gate in TS.
- Financial data uses the existing Financial Retrieval Layer and the single
  JDdS bridge for vault data. Do not create a second financial-data control
  plane.
- Eclipse already has typed retrieval contracts, source planning, identity,
  provenance, freshness/quality, conflict handling, unavailable/degraded states,
  durable retrieval records, run/tool/event persistence, Eclipse-Memory, skills,
  and skill evaluation. Reuse these; do not create competing versions.
- Known gap: retrieval quality/provenance are stronger than final-answer
  enforcement. There is no general structured mandate → coverage → answer claim
  gate. `derived_metric` is planned but calculations such as Sharpe are left to
  model reasoning.

## Non-negotiable repository rules

1. Read root `AGENTS.md`, `docs/NAVIGATION.md`, owning harness architecture/
   progress docs, and applicable skills before edits.
2. Inspect `git status` and `git diff` first. Preserve unrelated user changes;
   never revert/overwrite them. Do not commit, push, or open a PR.
3. Read code before changing it; reuse existing services, contracts, guards, UI
   components, and bridge routes. Keep files small and avoid unjustified deps.
4. Never fabricate prices, facts, publication times, citations, source authority,
   or confidence. Unknown metadata stays unknown; missing precise facts remain
   unavailable. Distinguish sourced facts, derived values, estimates,
   assumptions, interpretations, stale data, and user-provided input.
5. Do not let a model decide its own evidence validity. Deterministic checks
   enforce structural/metadata rules. If semantic entailment is uncertain, mark
   it unverified or send it for review; do not claim perfect verification.
6. No automatic skill promotion or autonomous policy changes. Keep existing
   operator gates and the read-only financial research boundary.
7. Add no external writes or trading/order functionality.
8. Append a dated entry to `docs/CHANGELOG.md` for every change. Update owning
   docs when architecture, contracts, setup/operations, major modules, or
   decisions change; bump `last-verified` only on docs actually rechecked.
9. After each change, from `Black-Eclipse-site/`, run required `npm run test`
   and `npx tsc --noEmit`. Also run relevant Python tests and targeted checks.
   Report failures honestly; do not mask unrelated baseline failures.

## Objective

For a supported research task, Eclipse should know what facts the answer must
establish; which entities, metrics, periods, bases, units, sources, and cutoffs
apply; what evidence arrived; which requirements are covered, conflicting,
unavailable, or unknown; and whether each material claim links to matching
evidence.

The model handles interpretation and explanation. The harness owns retrieval
policy, evidence identity, coverage status, calculation truth, structural
validation, and final accept/partial/reject decisions.

## Milestone 0 — Audit before design changes

Inspect at minimum:

- `docs/harness/architecture.md`, `phase-2-progress.md`,
  `phase-3-architecture.md`, `phase-3-progress.md`,
  `phase-3-memory-progress.md`, and `docs/DECISIONS.md`.
- `python/harness/retrieval/contract.py`, `planner.py`, `layer.py`,
  `normalize.py`, `validate.py`, `conflicts.py`, `aggregate.py`, `cache.py`,
  `structured.py`, and retrieval tools.
- `python/harness/graph.py`, `events.py`, `persistence.py`, `schemas.py`,
  `prompts.py`, `tools.py`, and runtime service wiring.
- Existing run/event/retrieval ownership; do not put market-data tables in
  `eclipse-memory.db`.
- Chat/response rendering, run detail/activity surfaces, API guards/proxies,
  test conventions, evaluation fixtures, and current git changes.

Record current behavior, integration points, migration implications, and
baseline results in `docs/harness/phase-4-progress.md`. Find the smallest
end-to-end flow. Source code is authoritative where this prompt differs.

## Milestone 1 — Evaluation baseline

Before implementing the gate, add deterministic cases for a narrow
period-over-period financial comparison:

- Correct entity and complete facts.
- Ambiguous ticker or wrong company/venue.
- Missing metric/period; consolidated/standalone mismatch.
- Currency/unit mismatch.
- Duplicate/overlapping observations and source disagreement.
- Incomplete, invalid, degraded, stale, or provenance-missing data.
- Unknown publication time and evidence after an as-of cutoff.
- Unsupported numeric claim, nonexistent evidence ID, citation to wrong fact.
- Calculation with too few observations or missing assumptions.
- Provider timeout/error and honest partial/unavailable behavior.

Test fixtures must be clearly synthetic and never enter production/JDdS data.
Report separate measures for identity, period/basis, coverage, citation
validity, temporal admissibility, conflict disclosure, calculation correctness,
and answer status. Establish a baseline; do not optimize for fluency alone.

## Milestone 2 — Research mandate contract

Add a small typed Python contract near the existing retrieval/orchestration seam.
Represent task type (initially `financial_comparison`), requested entities and
canonical identities, required fact legs (metric, period, basis, unit/currency,
required flag, necessary source tier), optional `asOf`/timezone, deliverables
and their evidence requirements, parse warnings, and ambiguity state.

Mandate generation can combine deterministic parsing and model-assisted
structured extraction validated against a schema. The plan is a request, never
evidence. Unknown concepts remain unresolved, not invented. Preserve user
periods/bases. Ask only when ambiguity changes retrieval. Unsupported/general
chat continues through the current path. Do not build a universal planner,
workflow editor, new agent architecture, or broad ontology here.

## Milestone 3 — Evidence coverage gate

Run mandate legs through existing retrieval tools/layer. Produce deterministic
coverage for every leg:

- `covered`: usable evidence matches identity, metric, period, basis, and unit /
  currency requirements.
- `conflicting`: eligible sources disagree without an explicit supported
  resolution.
- `unavailable`: retrieval was attempted but no usable evidence exists.
- `unknown`: evidence exists but required metadata (e.g. basis or publication
  time for point-in-time work) cannot be established.
- `not_applicable`: excluded by an explicit task rule with a reason.

Successful HTTP/tool execution does not equal coverage. Wrong-period/basis rows,
search snippets, planning responses, stale cache, and ambiguous identity cannot
satisfy numeric legs. Keep primary/structured/web/user/derived/cached/unverified
evidence distinct.

For a material gap, permit at most one bounded, targeted retrieval/repair round.
Reuse `src/lib/web-research.ts` through the existing bridge when allowed; add no
second search system. Quantitative history/derived metrics stay structured-only.
If still incomplete, return partial with explicit gaps or unavailable; never
ask the model to fill gaps from prior knowledge.

## Milestone 4 — Structured claims and answer validator

For the initial flow, define structured synthesis output containing material
claims with text, claim kind (`reported_fact`, `derived_fact`, `qualitative_fact`,
`interpretation` or equivalent), evidence IDs, coverage per mandate leg,
conflicts, assumptions, estimates, interpretations, and gaps. Render user-facing
prose from validated structure where practical.

Deterministically check: evidence IDs exist in this run; fact citations match
entity/security, metric, period, basis, unit, and currency where established;
derived claims reference registered calculations and inputs; unverified snippets
are not presented as verified facts; conflicts remain visible absent a documented
resolution; unknown/unavailable/post-cutoff legs are not established; and the
model cannot introduce a citation URL absent from retrieved evidence.

ID validation does not prove semantic entailment. If meaning cannot be checked
deterministically, mark `supportStatus: needs_review` or equivalent and present
as unverified. A model critic may flag concerns but cannot be the sole gate. On
failure permit one repair using exact invalid claims/missing legs, then
revalidate. If still invalid, strip/qualify unsupported claims and return a
useful partial result. Preserve compatibility for other clients.

## Milestone 5 — Point-in-time evidence

Add optional `asOf` to the mandate and propagate through retrieval/cache keys
and validation. Distinguish `period` (period described), `dataTimestamp` (when
observation applies), `publishedAt`/availability time (when public), `retrievedAt`
(when fetched), and `asOf` (requested cutoff).

For strict historical analysis, exclude items with `publishedAt > asOf`. Unknown
publication time remains unknown and cannot be claimed admissible. Never infer
availability from fiscal period, retrieval time, or a current page. Preserve
restatement/version data where available; otherwise disclose that historical
values may reflect revisions. Include cutoff and temporal policy in cache
identity. Keep schema changes additive/idempotent and document migrations.

## Milestone 6 — Deterministic derived metrics

Add a small pure-Python calculation module in the existing retrieval seam. Begin
only with metrics supported by real inputs: period change, CAGR, annualized
volatility, maximum drawdown, and Sharpe only with explicit risk-free rate and
conventions.

Record calculation ID/version and formula; input evidence IDs and identity;
date window, observation count, frequency, missing-data policy; units/currency,
annualization, risk-free source and assumptions; result and warnings. Reject
mismatched instruments, undocumented duplicate dates, insufficient observations,
non-finite values, and missing assumptions. Do not interpolate/backfill
silently. Return values as `derived` evidence, never reported facts. Add pure
deterministic tests and edge cases.

## Milestone 7 — Durable research receipt

Persist a bounded, queryable receipt using existing run/event/persistence
ownership. Do not add a third database or put market facts in Eclipse-Memory.
Receipt must explain what was requested, retrieved, missing/disputed, linked to
claims, rejected by validation, repaired, and why final status is accepted or
partial.

Include run ID, mandate/schema version, identity decisions, retrieval requests
and outcomes, evidence refs or bounded snapshot/hash, temporal status, coverage,
claims/citations, validation issues, repair metadata, final status, and existing
model/provider/version metadata. Never persist secrets; avoid unbounded source
documents. Make persistence errors observable without falsely claiming success.
Expose through existing run APIs/UI only if audit shows a real need and without
duplicating retrieval endpoints. Keep APIs typed, guarded, and compatible.

## Milestone 8 — Evaluation and rollout

Test the complete path: mandate → retrieval → coverage → synthesis → validation
→ persistence/events. Include provider errors and cancellation. Report metrics
separately and add regressions for failures found.

Verify existing chat and Phase 1/2/3-M behavior, JDdS as the only vault market
data path, shared web search, no autonomous skill promotion, Next.js as thin
front door, and the existing honest 503 when Python is unavailable.

Update `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`,
`docs/harness/decisions.md` / `docs/DECISIONS.md`, and `docs/NAVIGATION.md` as
actual triggers require. Document only implemented behavior. Append every
change to `docs/CHANGELOG.md`.

## Progress tracking and acceptance

Track baseline findings, milestone state, current milestone/next action, files
and rationale, contract/API/event/persistence changes, checks/results, known
gaps, and deferred decisions in `phase-4-progress.md`. A milestone is done only
when exercised by a test or real endpoint.

Phase 4 is complete only when the comparison flow has a typed mandate and
per-leg coverage; evidence is checked for identity/metric/period/basis/quality/
conflict/freshness/as-of before claims; citations are validated; gaps survive to
the UI; one bounded repair terminates; calculations have auditable inputs,
assumptions, and tests; receipts explain decisions; evaluations cover success
and honest failure; required checks pass; docs are current; unrelated user work
is preserved.

Final report: behavior implemented, key files, exact checks/results, limitations,
and documentation status (`docs updated: ...` or `no doc change — reason`).

