---
title: Learning Loop Closure
status: Current
last-verified: 2026-10-27
---

# Learning Loop Closure

**Who this is for:** anyone changing the post-run review, learning candidates,
skill evaluation, the advisory ledger, source health, or memory consolidation.

**Why this exists:** the machinery recorded 545 reviews and accepted zero
lessons. Recording is not learning. This doc names the contracts that make each
joint falsifiable, and the evidence that would prove a change worked.

## The four joints

```
run outcome ──► review ──► typed lesson ──► candidate ──► evaluation ──► approval
                  │                                          │
                  └── explicit null (reason + evidence)      └── vs a named base

advice ──► basis at issue time ──► horizon ──► score at deadline ──► calibration
```

Every joint has a required output. A null is allowed only when it names what was
inspected and why nothing was extractable.

## Contracts

### Review (`harness/learning_review.py`, `harness/self_improvement/lesson_contract.py`)

- Every completed review carries `noLearningReason` when `noLearning` is true.
- A `no_learning` outcome has `reason` and `evidenceChecked`; an unjustified null
  (`justified: false`) is a defect.
- Observation is always on. `skill_learning_mode` gates **run-analysis
  auto-detection** only: with it off, `analyze_run` still reports the typed
  lesson but does not persist a candidate. The recovery-incident lane
  (`recovery/learning.py`) and the RSL observation lane are separate surfaces
  with their own gates (`HARNESS_RSL_MODE`); they too create only inert
  candidates. No lane may activate anything.
- `aggregate_from_store` folds typed lessons across reviews. A signal is
  `eligible` only after two distinct runs; one observation is evidence, not a
  lesson.
- A re-review of the same run updates that row and refreshes its timestamp, so a
  corrected lesson is current rather than stranded in a pre-contract row.

### Candidate (`harness/skills/learning.py`, `harness/recovery/learning.py`)

A `failure_recovery` candidate must carry:

- `failedCall` and `recoveredCall` (the observable pair),
- `precondition` (the error code/message that triggers it),
- `proposedProcedure` (classify → recover → verify),
- `replayTest` (how to reproduce and check it).

Those fields are persisted on `LearningCandidate` (migration 32), not only in the
in-memory draft. A legacy row without them is quarantined, never silently
treated as conforming.

Templated titles (`Recovery after <tool> failure`), a constant `0.55` confidence,
a generic action, or missing evidence are rejected at creation
(`candidate_problems`). Confidence is derived from evidence count, recurrence and
whether a replay test exists. A later tool that merely succeeds is NOT a
recovery: the recovery must be the same tool (a retry) or the same recorded
capability, and its body must not report `UNAVAILABLE`/`TimeoutError`/
`TOOL_FORBIDDEN`. A lesson whose replay fails is withdrawn, not kept as accepted.

### Evaluation (`harness/skills/evaluation.py`)

`evaluate_skill` adds a `discrimination` dimension:

- a root version is `not_applicable`;
- a version with a named base but no outcome metrics is `needs_review` (a gap,
  never a fabricated metric);
- identical candidate/base metrics make the dimension `failed` (mandatory), so
  the candidate cannot be promoted as an improvement;
- three or more identical passing evaluations of one unchanged version are
  reported as a broken harness signal;
- regression never compares a version against a LATER version (the old fallback
  could grade 1.1.0 against 1.1.1).

Outcome metrics: `taskSuccess`, `retrievalHitRate`, `citationCoverage`,
`unsupportedClaimRate`, `costUsd`.

### Advice (`harness/advisory/`)

- A recommendation records its `method` and `horizon` at issue time; `dueAt` is
  derived from the horizon. Without an explicit method the basis class is used
  (`portfolio_computation` / `portfolio_read` / `model_advice`), never the action
  verb. Without an explicit horizon the policy default is `30d`; both are stored
  as basis entries. A quote tool contributes an entry price for later scoring.
- `scorecard` reports `unscored`, `overdue`, per-method hit rate and
  `demotedMethods` (measured hit rate below 0.5 with enough samples).
- An unscored recommendation is a defect, not a default.

### Route diagnosis (`harness/retrieval/health.py`)

`diagnose_routes` distinguishes a **routing defect** (generic route failing while
specific markets succeed) from a **provider failure** (every observed market
fails, or only a generic route is observed and it fails). A routing defect names
the healthy markets and says to stop recording it as a provider outage.

### Memory consolidation (`harness/eclipse_memory/consolidation.py`)

`consolidate_active` supersedes an exact duplicate, a near-duplicate (containment
or a subject named in the other statement), or a contradictory statement on the
same dimension, resolving to the later statement. Rows are retained and linked;
nothing is deleted. The verbosity axis ("straight to the facts" vs "detailed
with sources") is recognised even when the two records carry no subject. A short
active fragment (<=4 tokens, no subject) is reported as `residue`; it is not
treated as a resolved conflict and is not modified.

### Gate reachability (`harness/self_improvement/loop_health.py`)

`gate_report` reports a `detected` queue older than the window with zero accepted
as a design failure, not a normal backlog. `expire_stale_candidates` is the
operator-run drain. `evidence_plan()` states, per change, what success and
failure look like over the next 30 days.

The gate measures the **current contract window** (`HARNESS_LEARNING_CONTRACT_SINCE`,
default `2026-10-28T00:00:00Z`). Rows written before it are returned under
`legacyReviews` / `legacyAdvisory` and still shown, but do not keep the gate red.
The advice failure is due-aware: an unscored recommendation is a defect at its
stated horizon, not before it.

## Measuring the change

Do not describe architecture as an outcome. `loop_metrics` reads the review,
candidate and advisory stores; a missing input is a gap, never a zero.
`gate_report` is the before/after check: run it against the deployed store before
and after this change and compare `withTypedLesson`, `staleDetected`,
`accepted`, `evaluated`, `unscored` and `overdueCount`.

Surfaces:

- `GET /learning-review/health` now includes `gate` and `loop`; the gate reports
  `reviews_emit_unjustified_nulls` and `candidates_nonconforming`, not only a
  typed-lesson count.
- `learning_review_list` also returns `gate` (ok, gaps, `contractSince`, current
  and legacy reviews, current and legacy advice, candidates, and the memory
  consolidation counts), so a chat run can read and record every gate domain
  from a bound read tool.
- `learning_candidate_list` prints `staleDetected`/`nonconforming`, an accepted
  row's limitations, and the full store counts by status plus how many rows the
  50-row page hides. `memory(action="inventory")` prints the consolidation
  dry-run counts (`duplicateCount`, `conflictCount`, `residueCount`,
  `relatedCount`).
- `learning_review_list` shows each typed lesson and labels a bare null
  `UNJUSTIFIED`; `learning_candidate_list` shows the method fields and
  `CONTRACT VIOLATION` for a stored candidate that predates the contract.
- `GET get_source_health` includes a `diagnosis` block and prints routing
  defects separately from provider failures.
- `POST /eclipse-memory/consolidation/sweep` (operator-gated, `{dryRun}`) runs the
  consolidation sweep.
- `POST /learning/candidates/quarantine` (operator-gated, `{dryRun}`) rejects
  nonconforming `detected` candidates; rows are retained.
- `POST /advisory/backfill` (operator-gated, `{dryRun}`) makes legacy
  method/horizon explicit (`unscored` is still a defect; no outcome is invented).
  A recommendation with no stated method is recorded as `unclassified`, never
  as its action verb.
- `POST /learning/candidates/{id}/accept` (operator-gated, `{operator:true}`)
  accepts a falsifiable `detected` candidate; it never enables a skill.
- `POST /skills/{id}/evaluate` accepts `baseVersion`, `metrics` and
  `baseMetrics`, so the `discrimination` comparison is reachable over HTTP.
- `skill_discrimination_check` is the read-only probe: it runs the same
  comparison with caller-supplied metrics and persists nothing, so the
  identical/better/worse rules can be falsified from a chat run. Its text
  prints the `mandatory` flag.
- `learning_candidate_validate` is the read-only dry-run of the operator accept
  route: 404 missing, 409 not detected, 422 non-falsifiable, 200 acceptable.
  It writes nothing.
- The gate adds `intake_disabled` when `skill_learning_mode=off`: a frozen
  detector is a policy defect, not a passing state.

Historical rows written before this contract remain visible as defects; the
gate does not hide them. New writes cannot reproduce them.

## What these changes do not do

- They do not auto-accept or auto-enable anything. Operator approval is
  preserved.
- They do not invent missing metrics or outcomes.
- They do not change the review queue, evaluator runtime, or database ownership.
