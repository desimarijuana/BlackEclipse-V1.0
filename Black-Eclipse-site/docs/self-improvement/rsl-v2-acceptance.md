---
title: "RSL v2 — acceptance evidence"
status: Current
last-verified: 2026-10-20
---

# RSL v2 acceptance

v2 is code-complete. Each slice has deterministic evidence; the single live
operator landing remains the manual sign-off already defined in
`rsl-v1-acceptance.md`.

| Slice | Evidence |
|---|---|
| Pareto frontier | `test_rsl_pareto.py`; `pareto-frontier-card` component test; `GET /evolution/states/pareto` |
| Model-identity experiments (trial-only) | `test_evolution_rsl_routes.py::test_model_experiment_queues_a_trial_only_identity_change`; live preview still refuses identity |
| Cross-scope lesson transfer | `test_rsl_lessons.py::test_transfer_opt_in_allows_a_cue_match_across_scopes`; default exact-scope test |
| Canary split for code | `test_worktree_invoker.py::test_canary_split_can_reject_an_accepted_validation_win` |
| Scheduled climb | `test_rsl_loop.py::test_scheduled_climb_runs_once_due_and_pauses` |
| Pareto climb mode | `test_rsl_hillclimb.py::test_pareto_objective_accepts_a_tradeoff_that_single_rejects` |
| Safety boundary | `test_rsl_security.py`, `test_self_improvement_e2e.py`; live surface still refuses identity/drafts |

Commands:

```bash
npm test
npm run test:drift
npm run rsl:smoke
```

## Defaults

- `HARNESS_RSL_MODE=off`
- `HARNESS_RSL_CANARY=off`
- `HARNESS_RSL_CLIMB_SECONDS=0`
- `HARNESS_RSL_LESSON_TRANSFER=off`
- `HARNESS_RSL_OBJECTIVE=single`

## Deliberately not automated

- Live operator acceptance/landing.
- Model-identity live application (ADR-H275).
- Skill-draft promotion (ADR-H276); use the existing Skills lifecycle.
- Post-landing restart/health canary; the restart seam is owned by the front
  door, not the Python runtime.
