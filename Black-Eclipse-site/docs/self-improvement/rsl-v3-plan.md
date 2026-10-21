---
title: "RSL v3 — closing the post-landing and operator loop"
status: Current
last-verified: 2026-10-20
---

# RSL v3 — plan and P0 status

v2 proved that a candidate can be measured and prepared for landing. v3 closes
the two remaining operational gaps before the loop can claim a 9.5:

1. **Post-landing proof.** A pre-landing canary cannot prove the restarted
   runtime still boots. P0 adds the restart → health probe → rollback path.
2. **Hot operation.** The conductor no longer needs a process restart to change
   its bounded mode/budget, and the last operator override survives a restart.

The safety floor is unchanged: the judge is frozen, the operator is the only
landing path, and nothing here auto-promotes a change.

## P0 — implemented

### P0.1 Post-landing canary (`self_improvement/post_landing.py`)

- `run_post_landing(...)` accepts injected `restart`, `verify` and `rollback`
  callables and persists a bounded `HarnessPostLanding` row on
  `agent-memory.db`.
- Flow: restart → health probe (`GET /health`) → keep; on failure → rollback →
  restart → re-probe.
- `restart_already_done` supports the front-door protocol: the supervisor
  restarts first (the runtime cannot cleanly restart itself), then the runtime
  probes and rolls back on failure.
- With no restart seam the result is `unverified`, never a success. A failed
  rollback is recorded as `rollback_failed`; its message is bounded.
- `POST /code/tasks/{runId}/promote` now returns a `postLanding` hint for an
  `rsl-*` landing that needs a restart, including the rollback id and the probe
  URL. `POST /code/promotions/{rollbackId}/post-landing` runs the probe;
  `GET /code/promotions/post-landing` lists the records.
- The promotion card (`promote-change.tsx` → `postLandingProbe`) calls the probe
  after the front-door restart and shows `healthy`, `rolled_back` or
  `unverified`; it never calls a probe result "live" without the health record.

### P0.2 Hot, persisted config (`self_improvement/runtime_settings.py`)

- `RSLConfig.from_dict` / `apply_payload` reuse the same clamps as `from_env`;
  unknown keys are refused.
- `RSLLoop.set_config(payload)` applies a bounded override without a restart,
  starts the conductor when a previously-off mode is enabled, and stops it when
  the mode returns to `off`.
- The last override is stored in `HarnessRuntimeSetting` on `agent-memory.db`
  and overlaid on the env defaults at the next boot. `POST /evolution/rsl/config`
  is the operator surface; `GET /evolution/rsl` reports `configSource`.
- Defaults remain `HARNESS_RSL_MODE=off`. Making observe the default is a
  separate product decision (it would create inert candidates from post-run
  review) and is not part of P0.

## P1 — ablation foundation (implemented slice)

`python/harness/evaluation/ablation.py` runs the same tasks, trials and seed
through:

1. `baseline` — the production agent prompt + the tools the evaluation registry
   actually exposes;
2. `surface` — an operator-supplied `HarnessSnapshot`;
3. `surface+lessons` — that snapshot plus a per-task verified lesson manifest
   (optional `--lessons-db`).

Every arm uses the existing `CandidateAgentInvoker` / `EvaluationRunner`; the
report carries the Wilson interval, measured trials, per-category rates, cost,
and a critical-regression veto (`safety` / `adversarial`). `npm run rsl:bench`
wraps the CLI with a disposable `agent-memory.db`. `--live --provider … --model
…` (API key from `HARNESS_EVAL_API_KEY`) runs the same arms against a real
model; the report labels the tier and states that the isolated evaluation bridge
still reports external data `UNAVAILABLE`.

`python/harness/evaluation/replay_builder.py` turns recorded completed runs into
deduplicated, redacted, live-only regression tasks (expected behavior = the
recorded tool sequence, never an invented answer). It is not run automatically:
the operator chooses the output path and reviews the generated dataset. Failed
runs stay in the existing mining pipeline.

Two honest limits are printed in every report: the default tier is the
**deterministic scripted** tier (not live-model evidence), and the task corpus is
still the existing 53 tasks. Replay generation exists, but no replay dataset is
committed yet; adversarial/finance expansion remains P1 work. There is no
external-framework dependency: the RSL, its evaluator and its evidence are
Eclipse-owned.

The production Eclipse prompt is ~34k characters, so `HarnessSnapshot`'s cap was
raised from 16k to 48k; otherwise the baseline could not be represented at all.
The ablation baseline intersects the agent's tool list with the evaluation
registry (a production tool the registry does not register is a hard failure,
not a silent omission).

## P2 — parallel candidate search (implemented slice)

`HARNESS_RSL_MAX_PARALLEL` (1–8, default 2) bounds one bounded semaphore per
experiment. `recursion.run_recursive` now verifies the `k` candidates
concurrently with `asyncio.gather`, keeps proposal order for selection, and turns
one verification exception into that candidate's non-answer (never a batch
failure). `hillclimb.run_hillclimb` evaluates independent validation neighbors
concurrently under the same cap, then runs the replay gate in order. The daily
budget still trims `k` before any call, and `HillClimbConfig.max_evaluations` is
counted before the parallel batch. The result carries `maxParallel` for
observability.

Per-scope concurrency is now a lease per scope: two experiments in different
scopes may run at once, while the same scope refuses a second one. The conductor
tick still owns the global busy flag, so a tick and an operator experiment do
not overlap. Recursive results carry `costUsd`/`totalTokens` when the verifier
reports them (absent stays `UNKNOWN`). Cost per accepted improvement remains a
reporting follow-up.

## P3 — editable surface, first slice (implemented)

`HarnessSnapshot` gained `toolGuidance` (≤4,000 chars), a bounded block of
per-tool instructions. It is prompt EVIDENCE, never permission: the registered
tool allowlist is still the execution boundary, and guidance cannot add a tool.
`effective_prompt()` appends it; candidate trials (`to_agent_config`) and the
live surface (`apply_active_surface`) both use that prompt. The digest includes
guidance only when non-empty, so every snapshot written before this field keeps
its exact digest.

Guardrails, memory policy, subagent prompts and the skill-manifest policy remain
P3 work.

## Remaining phases

| Phase | Goal | Gate |
|---|---|---|
| P1 (rest) | replay/adversarial/finance datasets, live-model tier, native benchmark adapter | a published report with Wilson intervals and a reproducible benchmark table |
| P2 (rest) | cost per accepted improvement reporting | real usage survives into the experiment report |
| P3 (rest) | guardrails, memory policy, subagent prompts, skill-manifest policy | an accepted non-prompt surface survives verify, canary, preview, activation and rollback |
| P4 | Operator digest, drift → candidate automation, nightly `rsl:bench` | one week of unattended runs with a readable report and a planted regression caught in CI |

## Tests

- `python/tests/test_post_landing.py` — healthy, rollback, no seam, failed
  rollback, restart failure, timeout, front-door restart.
- `python/tests/test_rsl_config.py` — payload clamps, unknown keys, round trip.
- `python/tests/test_rsl_loop.py` — hot config persists and reloads.
- `python/tests/test_ablation.py` — arm projection, critical veto, measured gain,
  fake-runner orchestration, live-settings guard, snapshot round trip.
- `python/tests/test_replay_builder.py` — dedupe, redaction, live-only tasks,
  failed-run exclusion, dataset round trip.
- `test_rsl_recursion.py` — parallel cap, order preservation, per-scope lease,
  real usage aggregation.
- `test_rsl_hillclimb.py` — parallel validation neighbors under the cap.
- `test_rsl_snapshot.py` / `test_live_surface.py` — bounded tool guidance,
  digest discipline, live application without widening the allowlist.

See ADR-H278 (post-landing + hot config), ADR-H279 (live ablation + replay
labels), ADR-H282 (parallel candidate verification) and ADR-H283 (tool guidance
is not authority) for the decisions, and `docs/harness/architecture.md` for the
module map.
