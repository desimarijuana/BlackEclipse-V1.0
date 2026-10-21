---
title: "RSL v2 — plan"
status: Current
last-verified: 2026-10-20
---

# RSL v2 — plan

RSL v1 is code-complete and operator-gated. v2 widens **what can be improved**
and **how the search is driven**, without changing the safety floor: the operator
still owns every landing, the judge (tests/evaluator/gates/policy/security/
datasets) stays frozen, and there is no new runtime, queue or database.

## Status

| Slice | Status |
|---|---|
| Multi-objective Pareto frontier + operator card | Done |
| Trial-only model-identity experiments | Done |
| Opt-in cross-scope lesson transfer | Done |
| Canary split for code (pre-landing) | Done |
| Continuous climb scheduling | Done (runner injectable) |
| Multi-objective search integration | Done |
| Model-identity live activation | Rejected (trial-only, ADR-H275) |
| Skill-draft promotion path | Existing skills lifecycle (ADR-H276) |
| Hardening and acceptance | Done (ADR-H277) |

## V2.1 — Canary split for code (done)

A validated code candidate must survive a second disjoint split before the
operator can prepare it for landing.

- `HARNESS_RSL_CANARY=on` runs the patched worktree on `held_out` (configurable)
  after the validation comparison.
- A target drop beyond the tolerance, an unmeasured split, or any critical-task
  regression rejects the candidate.
- The canary record rides on the decision record; post-landing
  restart/health monitoring remains a separate front-door seam.

**Acceptance.** An accepted validation win can be rejected by the canary split
(`test_worktree_invoker.py`); `evaluated_ok` and `prepare-landing` require the
canary to pass when enabled.

## V2.2 — Continuous climb scheduling (done)

- `HARNESS_RSL_CLIMB_SECONDS` (0 = off) and `HARNESS_RSL_CLIMB_SCOPE`.
- The search is an injected `climb_runner(loop, scope)`; without one the schedule
  is inert (`climbEnabled=false`).
- `POST /evolution/rsl/climb/pause|resume` and the operator toggle.
- Status reports interval, next run, pause state and last result. Budget, busy,
  mode and strategy gates still apply.

**Acceptance.** One due climb runs once, pause stops it, and the budget/busy gates
are checked (`test_rsl_loop.py`).

## V2.3 — Multi-objective search (done)

- `HARNESS_RSL_OBJECTIVE=single|pareto`, default `single`.
- In `pareto`, a measured, non-critical trade-off can be accepted when the
  current state does not dominate it on at least two comparable objectives.
- `single` is unchanged; the climb result carries the frontier in `pareto`.

**Acceptance.** The same trade-off is rejected by `single` and retained by
`pareto` (`test_rsl_hillclimb.py`).

## V2.4 — Identity expansion (decided)

1. **Model identity:** measured comparisons are allowed, but live activation is
   refused. Model/credential resolution stays in the front door (ADR-H275).
2. **Skill drafts:** v1b measures inert drafts in a trial; promotion stays in the
   existing skills lifecycle, not a second RSL route (ADR-H276).

## V2.5 — Hardening and acceptance (done)

- Contamination-resistant held-out/release suites remain the canary gate.
- Cross-scope transfer is opt-in and still enters the injected/control cohorts.
- Slice-level evidence is recorded in `rsl-v2-acceptance.md` (ADR-H277).
- The v1 live operator run remains the manual sign-off.

## Safety floor (unchanged)

- Operator approval is the only landing path; canary auto-rollback is not
  auto-promotion.
- Frozen judge: tests, evaluator, gates, policy, security and datasets.
- `UNMEASURED` never passes; critical regressions always veto.
- Every experiment carries identity, provenance and a recorded decision.
- Defaults stay off: `HARNESS_RSL_MODE=off`, continuous climb off, transfer off.

## Definition of done for v2

1. A code candidate survives a canary split before landing; post-landing
   restart/health canary remains a separate front-door seam.
2. A bounded climb can be scheduled and paused; budgets and leases hold.
3. Pareto selection is opt-in and never auto-promotes.
4. Model identity is explicitly trial-only; skill promotion uses the existing
   skills lifecycle (ADR-H275/H276).
5. Slice-level evidence is recorded; the one live operator acceptance remains
   the manual v1 sign-off.

---

Acceptance evidence: `docs/self-improvement/rsl-v2-acceptance.md`.
