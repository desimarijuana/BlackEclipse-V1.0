---
title: "RSL v1 acceptance evidence and live runbook"
status: Current
last-verified: 2026-10-20
---

# RSL v1 acceptance

RSL v1 is code-complete. This page is the acceptance record: what the checked-in
automated evidence proves, and the one operator-run experiment that must be
recorded against a live model.

## Automated evidence (checked in)

| DoD | Evidence |
|---|---|
| Recurrence → one inert candidate | `python/tests/test_self_improvement_e2e.py::test_seeded_journey_creates_inert_candidate_and_structured_ops` |
| Target byte-identical until landing | `test_self_improvement_e2e.py::test_candidate_is_inert_and_target_is_byte_identical` |
| Owning tests in a disposable worktree | `python/tests/test_code_verify.py`, `test_worktree_invoker.py` |
| Measured improvement + critical-task veto | `python/tests/test_rsl_surface_e2e.py`, `test_worktree_invoker.py`, `test_rsl_utility.py` |
| Decision/evidence recorded with provenance | `test_rsl_surface_e2e.py` (baseline + candidate `EvaluationRun`) |
| Operator preview → approval → apply/rollback | `test_self_improvement_e2e.py::test_activation_and_rollback_preserve_both_versions` |
| Lesson stored and retrieved | `python/tests/test_rsl_lessons.py`, `test_lesson_feedback.py` |
| Rejected candidate never activates | `test_rsl_surface_e2e.py`, `test_rsl_loop.py` |
| Restart-safe, budget-capped, auditable | `test_rsl_loop.py`, `test_rsl_state.py` |
| v1b inert skill-draft trial | `python/tests/test_rsl_skill_drafts.py` |
| Drift monitoring and operator inbox | `test_drift.py`, `test_drift_watch.py`, `test_evolution_rsl_routes.py` |

Gate commands:

```bash
npm test                 # Vitest + full Python + eval gates
npm run test:drift       # component + full-app browser smokes
npm run rsl:smoke        # disposable-repo conductor/worktree/surface smoke
```

## Operator-run live experiment (one required)

The automated tests use the scripted invoker. Acceptance also needs one real
model run against a real recurring failure.

1. Set `HARNESS_RSL_MODE=observe` and restart. Let a real failure recur three
   times; confirm exactly one inert observation/candidate appears.
2. Switch to `propose` (and `HARNESS_RSL_MODEL_PROPOSER=on` only if you want the
   model proposer). Stage the proposal; confirm tests pass in the worktree.
3. Switch to `verify` (or `auto`) with `HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY=1`.
   Run one tick. Record the candidate ID, baseline run ID, candidate run ID,
   target delta, and decision.
4. If rejected: confirm the candidate is `evaluated_bad` and the target is
   unchanged. If accepted: open the preview, approve through the existing
   single-use promotion path, then confirm the health check and rollback path.
5. Confirm the adopted lesson is retrieved by a later matching task
   (`prompt.lesson_injected`), or record why the lesson was retired.

Record the result in `docs/CHANGELOG.md` (candidate/run IDs, measured delta,
decision) and set `HARNESS_RSL_MODE` back to `off` unless the rollout is
deliberate.

## Rollout order

`off` (default) → `observe` (one week) → `propose` → `verify` (budget 1) →
`auto` only after the acceptance run and at least one clean promotion. `k>1`
and `HARNESS_RSL_CODE_BENCHMARK=on` are cost decisions, not autonomy grants.
Operator approval remains the only landing path in every mode.
