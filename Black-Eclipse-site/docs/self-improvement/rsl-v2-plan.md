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
| Continuous climb scheduling | Planned |
| Multi-objective search integration | Planned |
| Model-identity live activation | Decision required |
| Skill-draft promotion path | Decision required |

## Phase V2.1 — Canary landing for code (next)

**Goal.** An operator-approved code change lands through a canary, is
health-checked, and is automatically rolled back on failure.

**Scope**
- A `canary` stage between "accepted" and "current": a bounded window of real
  runs (or a fixed number) executes with the patched worktree.
- A health predicate over those runs (success rate, critical tasks, latency/cost
  ceilings) with the same critical-regression veto as verification.
- Automatic rollback via the existing `code/selfhost.py` path on failure; keep
  both versions and record the rollback as an `EvolutionAttempt`.
- Operator UI: canary status, health, rollback button, and the exact diff.

**Non-goals.** No automatic promotion, no bypass of the single-use approval, no
canary without a verified measured candidate.

**Acceptance**
- A scripted canary that fails its health check rolls back, preserves both
  versions, and records why.
- A passing canary can be promoted; the prior version stays recoverable.
- `rsl:smoke` covers one canary → promote and one canary → rollback.

## Phase V2.2 — Continuous climb scheduling

**Goal.** The hill climb can run on a cadence/drift trigger instead of only an
operator tick.

**Scope**
- `HARNESS_RSL_CLIMB_SECONDS` (default off), sharing the daily budget and lease
  with the conductor.
- Drift transition can wake a climb for the affected scope (still bounded,
  still candidate-only).
- Operator pause/kill switch and visible next-run time.

**Acceptance.** A drift transition schedules at most one bounded climb; the
budget is never exceeded; pause stops future runs without killing an in-flight
one.

## Phase V2.3 — Multi-objective search integration

**Goal.** Use the Pareto frontier in selection, not only as a read-only view.

**Scope**
- Hill-climb neighbours can be kept on a trade-off frontier (e.g. cheaper but
  slightly less accurate) instead of only the single weighted utility.
- An explicit operator mode `HARNESS_RSL_OBJECTIVE=single|pareto`; `single`
  remains the default.
- Pareto acceptance still requires no critical regression and a measured sample.

**Acceptance.** With `pareto`, a trade-off state is retained and visible but not
auto-promoted; with `single`, behaviour is byte-identical to today.

## Phase V2.4 — Identity expansion (decision-gated)

Two candidates, each requiring an explicit decision record before code:

1. **Model-identity live activation.** Today the surface preview refuses model
   identity; v2 could apply a measured provider/model/temperature only if the
   front door's credential resolution still owns secrets. Otherwise keep
   trial-only.
2. **Skill-draft promotion.** v1b measures inert drafts in a trial; v2 could
   promote a measured draft through the existing `skills/versioning.py` path.

**Rule.** No identity expansion without a measured comparison, the existing
approval path, and a rollback plan.

## Phase V2.5 — Hardening and rollout

- Contamination-resistant held-out/release suites for every new subject.
- Cross-scope transfer diagnostics: which scope a lesson came from and its
  measured lift in the new scope.
- Canary budget and blast-radius telemetry.
- Docs/runbook updates and one live operator acceptance per subject type.

## Safety floor (unchanged)

- Operator approval is the only landing path; canary auto-rollback is not
  auto-promotion.
- Frozen judge: tests, evaluator, gates, policy, security and datasets.
- `UNMEASURED` never passes; critical regressions always veto.
- Every experiment carries identity, provenance and a recorded decision.
- Defaults stay off: `HARNESS_RSL_MODE=off`, continuous climb off, transfer off.

## Definition of done for v2

1. A code candidate survives a canary split before landing; post-landing\n   restart/health canary remains the next seam.
2. A bounded climb can be scheduled and paused; budgets and leases hold.
3. Pareto selection is opt-in and never auto-promotes.
4. One identity expansion (model or skill) is either implemented through the
   existing approval path or explicitly rejected with an ADR.
5. One live operator acceptance per subject type is recorded.
