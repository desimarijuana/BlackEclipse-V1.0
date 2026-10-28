# Learning Loop Closure Changes

All operator gates are unchanged: `skill_create`, `skill_update`,
`skill_learning_set`, activation and promotion remain operator-only. The changes
below close the mechanical detection → contract → draft → acceptance → scoring →
retirement path.

## T1 — Dead state transition (`drafted` could not be accepted)

**Root cause:** `routers/sessions.py:accept_candidate` required `detected`, but
the generator's auto-draft path stores `drafted`; `drafted` therefore had no
accept path.

**Fix (option B):** the accept route now accepts `detected` **and** `drafted`,
re-validates `candidate_problems`, creates the inert draft through
`propose_draft` when no artifact exists, verifies the stored skill, then records
`accepted`. The same rules are mirrored in the read-only
`learning_candidate_validate` tool. Acceptance never enables the skill.

**Why B:** auto-draft is the autonomous creation step; rejecting its state would
either disable creation or require re-emitting `detected` and losing the draft.
Re-validating at accept keeps the contract authoritative.

**Test:** `test_candidate_accept_creates_an_inert_skill` (`test_skills_api.py`)
— generator-shaped candidate → operator accept → `accepted` + stored draft skill.

**Before/after:** before, `drafted` → 409; after, `drafted`/`detected` →
`accepted` with `resultingSkillId`.

## T2 — Generator populates the contract

**Root cause:** legacy rows were produced by an older generator that never
captured the failed/recovered calls, precondition, procedure or replay test.

**Fix:** the current `skills/learning.py:analyze_run` derives all five fields from
the trace: `failedCall`/`recoveredCall` from the same-tool retry (or same
capability), `precondition` from the error code, `proposedProcedure` from the
observed steps, and `replayTest` from the run id + forced error. A draft with
missing fields is rejected by `candidate_problems` and never persisted as a
partial candidate.

**Test:** `test_synthetic_failure_recovery_yields_all_contract_fields`
(`test_self_improvement_loops.py`).

**Before/after:** legacy 10/10 failure_recovery rows lacked fields and are
quarantined; a synthetic trace now yields all five non-empty fields.

## T3 — Computed confidence

**Root cause:** legacy rows carried a literal `0.55`.

**Fix:** `failure_recovery` uses `derive_confidence(evidence_count,
occurrence_count, has_replay)`; `successful_procedure` uses
`0.5 + 0.1 * recurrence`; `user_correction` uses `derive_confidence`. No producer
contains `0.55`.

**Test:** `test_confidence_is_derived_not_constant` (low=0.4, high>`0.4`).

**Before/after:** constant 0.55 → evidence/recurrence-derived values.

## T4 — Structural recurrence + explicit-correction fast path

**Root cause:** recurrence already keyed on tool evidence in the current
generator, but the explicit user correction (highest signal) still required
recurrence ≥ 2 and could not draft on first occurrence.

**Fix:** recurrence key remains structural (`_candidate_recurrence_key`: failure
signature/tool sequence). `draft_ready` now lets `user_correction` draft at
recurrence 1; inferred procedures still require ≥ 2. Recurring signatures update
the **existing** candidate's `occurrenceCount` instead of being discarded.

**Tests:** `test_explicit_correction_drafts_on_first_occurrence`,
`test_a_recurring_recovery_candidate_is_auto_drafted_but_never_enabled`.

## T5 — Scoring loop

**Root cause:** drafts were created but never evaluated; used skills were never
re-checked; there was no retirement transition.

**Fix:**
- `evaluate_drafted_skills` runs the deterministic evaluation for every
  `learned.*` draft at startup (creation → evaluation).
- `evaluate_used_skills` evaluates learned skills after ≥3 completed uses.
- `retire_non_discriminating` deprecates a skill whose `discrimination` dimension
  fails (retained, never deleted).
- Advisory scoring still has its existing trigger (`advisory_evaluate_outcomes`);
  **no new autonomous cadence was added** (see "Not fixed" below).

**Test:** `test_identical_metrics_retire_the_skill_not_keep_it`.

**Before/after:** 0 evaluated learned skills → the existing draft evaluates
`passed` at startup; a non-discriminating skill transitions to `deprecated`.

## T6 — Memory promotion trigger

**Root cause:** `proposed` memory had no promotion path.

**Fix:** `EclipseMemoryService.promote_confirmed_proposals` promotes a
`proposed` row only when its content signature has recurrence ≥ 2 **and**
`detect_conflict` reports no conflict. Rows whose `statusReason` records a
conflict stay `proposed`. Triggered at startup and on `commit_decision`.

**Test:** `test_proposed_memory_promotes_after_recurrence_but_not_on_conflict`.

**Before/after:** proposed rows inert forever → recurrence-backed, conflict-free
rows become active; conflicting rows stay proposed.

## T7 — Legacy debt

**Fix:** `LearningReview.legacyUnscored` is an additive column; startup
`mark_legacy_reviews(CONTRACT_SINCE)` marks pre-contract completed reviews once.
No history is rewritten.

**Not done:** the 14 legacy advisory recommendations were not bulk-scored; that
needs the market gateway and a deliberate backfill run. They remain explicitly
`unscored`, not fabricated.

## Not fixed (explicit)

1. **Autonomous advisory scoring cadence.** The scorer exists and is callable;
   no scheduler was added because it requires live market prices and a policy
   decision about cadence. `advisory_evaluate_outcomes` remains the trigger.
2. **Legacy advisory backfill.** 14 legacy recommendations are untouched; a
   backfill needs entry prices and a market gateway.
3. **Autonomous enablement/promotion.** Deliberately not built. Acceptance and
   activation remain operator-gated.

## Definition-of-done status

Live store after the change (2026-10-28): candidates **detected=1, accepted=1,
drafted=0, rejected=10**; learned skill `learned.reusable-procedure-analysis-run`
is `draft` with a persisted evaluation `status=passed`; **109** legacy reviews
are marked `legacyUnscored`; memory has automatic records (one active, one
conflict-proposed).

- `detected > 0`: yes (one new contract-clean candidate is waiting).
- `accepted > 0`: yes (operator accept route).
- `evaluated > 0`: yes (`SkillEvaluation` passed).
- Operator gates: unchanged; acceptance created/kept a draft, it did not enable.
