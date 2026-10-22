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
**deterministic scripted** tier (not live-model evidence), and the task corpus
is still small. The corpus grew from 53 to 62 tasks with two new datasets:
`adversarial_v1` (4 refusal/overclaim fixtures: an unavailable service stays
unavailable, a stale quote carries its as-of date, a note cannot widen the
agent's scope, the wrong metric is not the requested metric) and `finance_v1`
(5 recomputed ratios: net margin, operating margin, EV/EBITDA, EPS, position
weight). Every finance number is a synthetic literal in the task and every
answer is graded by an INDEPENDENT recomputation; no provider call, no market
data. Replay generation exists, but no replay dataset is committed yet. There is
no external-framework dependency: the RSL, its evaluator and its evidence are
Eclipse-owned. The corpus itself is now portable: `evaluation/export.py` writes
it as a self-describing bundle (one entry per dataset, with a content
checksum), reads it back through the same task schema, and VERIFIES it by
recomputing the checksums - `npm run rsl:corpus -- --out <file>` /
`--verify <file>`. A bundle is tamper-evident, not trusted.

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
reports them (absent stays `UNKNOWN`), and the self-evolution metric block now
reports `rsl_cost_usd` and `rsl_cost_per_accepted` — the cost of the recorded
experiments divided by the accepted ones. A run that reported no cost never
becomes a zero-cost run.

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

### P3 slice 2 — surface-controlled CONTEXT (implemented)

A surface may now narrow what the agent is reminded of:

- `skillManifest`: `none` | `top3` | `top8` — how many skills are listed as a
  hint. The manifest is a hint; narrowing it removes hints, never a capability.
- `memoryPolicy`: `off` | `profile_only` | `profile_plus_search` — whether
  recalled memory, the persistent profile, or both are injected.

Both are closed sets on `AgentConfig` and on `HarnessSnapshot` (digest-additive,
so an older snapshot keeps its identity); an unknown value is refused. Neither
grants a tool, a permission or an effect, and neither touches the tool
allowlist. Enforced where the blocks are built (`graph_context.py`).

Deterministic guardrails (a violation fails the run with a named code) and
subagent prompts remain P3 work.

### P3 slice 3 — guardrails the RUNTIME enforces (implemented)

A guardrail is a rule the runtime checks, not a rule the model is told:

- `require_tool_before_answer` — the run executed at least one tool.
- `require_citation` — the answer carries a citation (the evaluator's own
  citation parser decides what a citation is).
- `maxAnswerChars` — the answer is not longer than the bound.

They are checked once, at the end of the run, against what the run really did
(the persisted tool executions) and what it really answered. A violation
**fails** the run with a named code (`GUARDRAIL_TOOL_REQUIRED`,
`GUARDRAIL_CITATION_MISSING`, `GUARDRAIL_ANSWER_TOO_LONG`) and the answer is
not shipped as a completed result. A broken guardrail implementation degrades to
"no violation" — it can never break a run. The codes are part of the runtime
error contract on both sides (Python `HarnessErrorCode` + the TS union).

Subagent prompts remain the last open P3 surface.

### P3 slice 4 — the delegated child inherits the context policy (implemented)

`subagentPrompt` (≤4,000 chars) lets a surface give DELEGATED children their
own bounded instructions. The child keeps its own preset prompt, gains the
surface's instructions, and its tools are the NARROWED set the delegation
already computed. It is prompt evidence: no tool, no ceiling, no permission, no
effect. The delegation path is unchanged when the field is absent.

That closes the editable-surface set: **prompt, tool guidance, tool subset,
ceilings, context policy (skill manifest + memory), guardrails, and the delegated
child's prompt.**

### P4 slice 2 — the unattended session is a gate (implemented)

`npm run rsl:nightly` runs the corpus once (the deterministic tier), compares
the result with the recorded baseline through the EXISTING per-dimension
regression gates, writes a dated JSON + Markdown report, and exits non-zero
when a CRITICAL measure regressed (task success, safety, hallucination rate,
financial accuracy, routing). Cost / latency / token movements are warnings and
do not fail the session. The baseline only moves forward on a clean run and
only with `--promote`.

The gate is proven by PLANTING a regression: a test adds a task that does not
pass and asserts the session says FAIL, names the regressed measure and writes
it to the report. A gate that cannot fail is decoration.

### P4 slice 1 — the loop reports on itself (implemented)

- `GET /evolution/rsl/report?days=7` returns the digest: experiments, accepted /
  rejected / unmeasured, the real cost and the cost per accepted improvement,
  the candidates in flight, the lessons adopted and where production is
  drifting. A measure that was never taken reads `UNKNOWN` — never a fabricated
  zero. The same digest renders as Markdown, so a person or CI can read it.
- The operator panel gained a weekly card (`rsl-weekly-card.tsx`): what was
  tried, what improved, what it cost, and the current drift state.
- `HARNESS_RSL_DRIFT_AUTOCANDIDATE=on` lets the drift watch open, on a NEW
  transition into drift, the SAME inert candidate the operator route opens. The
  candidate carries no target and no operations; it enters the existing
  propose → verify → land flow and lands nothing by itself. Off by default.

Still open in P4: an unattended run scheduled by the operator's own scheduler
(the session itself is implemented; the scheduling is the operator's choice) and
a real CI job that runs it on every change.

### P4 slice 3 — the corpus gate is in the release gate (implemented)

`python/harness/evaluation/baselines/corpus_v1.json` is the COMMITTED record
of what the corpus measures today (the stable measures only — cost, latency
and token usage move every run and are never pinned). BOTH the local
`npm run check:all` and the repository workflow (`/.github/workflows/ci.yml`)
end with the corpus gate: a critical regression fails the release. Refreshing
the baseline is a deliberate act
(`npm run rsl:nightly -- --dataset all --write-baseline <file>`).

`replay_v1.json` joins the corpus as six AUTHORED replay fixtures in the shape
the replay builder produces from real runs (expected behavior = the recorded
tool sequence, never an invented answer). They are live-only, so the scripted
tier reports them UNMEASURED rather than pretending a stale model response
replays. The corpus is now 76 tasks (64 validation / 10 optimization / 2
held_out).

The corpus grew again with a second tranche: `adversarial_v1` (8) and
`finance_v1` (9). The new adversarial fixtures are about HONESTY under
pressure: two sources that disagree (report both), a quote in the wrong
currency (name the currency you have), a price with no currency at all (the unit
is missing), and a document carrying an injected instruction (it is data, and
publishing is not allowed). The new finance fixtures are independently
recomputed: percentage change, three-year CAGR, free cash flow after capital
spending, and a position size from reward and risk.

## P5 — the lab improves the harness itself (implemented slice)

Everything the loop can change is code (a worktree, a promotion) or a surface
(prompt, tool guidance, context policy, guardrails). The surface is the cheap one
— no worktree, no landing — and it is where most of the headroom is.

`npm run rsl:lab` (the **surface lab**) does exactly that, honestly:

- the variants are **deterministic** and derived from the lessons the loop
  already **adopted** (one lesson, the top three, their cues as a checklist);
  with no adopted lesson there is no variant, because the lab never invents an
  instruction nobody verified;
- each variant is measured on the SAME tasks through the existing measured
  surface path, against the base's own run;
- an **unmeasured** variant is never a winner, a **critical regression** (safety,
  adversarial) is **vetoed** even when the average is better, and "flat" is a
  result, not a win;
- the winner is a **candidate for the operator** — the lab never lands, never
  activates and never writes to the harness.

On the scripted tier the lab correctly finds NO improvement, because a scripted
answer does not depend on the prompt. That is the point: the lab reports what it
measured.

### P5 slice 2 — one surface path; the lab stages evidence (implemented)

- `self_improvement/surface_candidate.py` owns the identity of a surface
  experiment and the row it creates. The operator route and the lab BOTH call
  it, so a lab winner and an operator experiment are the same thing to the rest
  of the system, and re-running the same experiment never creates a second row.
- The lab stages its winner as an **inert** surface candidate whose problem
  statement carries the measured delta and the lessons it came from.
  `POST /evolution/surface-lab/{id}/queue` is the operator's one click to queue
  it; the loop then verifies it through the **same** measured path, and only then
  can it be activated (canary + rollback). The lab never lands, never activates
  and never queues.

The session can also be scheduled by the operator's own scheduler
(`HARNESS_RSL_SESSION_SECONDS`); the corpus gate runs in the repository
workflow as well as locally.

### P5 slice 3 — the live tier (implemented)

The lab has two tiers and they are not interchangeable:

- the **scripted** tier (default) replays a deterministic answer — it proves the
  harness path works, and it **cannot** see a prompt change, so it reports
  "flat" and no winner (the honest result);
- the **live** tier (`npm run rsl:lab -- --live --provider <p> --model <m>`,
  key from `HARNESS_EVAL_API_KEY`) runs the **same** measured path with a real
  model. The runtime never guesses a provider, a model or a key, and a live run
  without explicit settings is refused before it starts.

The live tier is the only tier in which a verdict about a PROMPT change means
anything, so a report says which tier produced it.

### Decided, not deferred

- **A3 — the loop stays `off` by default.** Zero-config must not write: the
  `observe` mode creates inert candidates from post-run review, so flipping the
  default would make a fresh install write to the store before anyone asked.
  The operator opts in (`HARNESS_RSL_MODE=observe|propose|verify|auto`), and
  `POST /evolution/rsl/config` does the same without a restart.
- **V1 — the size ratchets stay with their history.** Moving the pins into a
  data file would make the churn cheaper but would trade the re-pin notes (the
  audit trail of WHY a file grew) for convenience. The real fix is splitting the
  hot files - the split candidates are named in the ratchet comments.

## Remaining phases

| Phase | Goal | Gate |
|---|---|---|
| P1 (rest) | done: replay fixtures, the committed baseline, an 88-task corpus; still open: more adversarial/finance tasks | a published report with Wilson intervals and a reproducible benchmark table |
| P2 | done: parallel search, per-scope leases, cost per accepted improvement | — |
| P3 | done: tool guidance, context policy, guardrails, delegated-child prompt | — |
| P4 (rest) | done: the release-gate step; the session can be scheduled by the operator's own scheduler (`HARNESS_RSL_SESSION_SECONDS`) | one week of unattended runs with a readable report |
| P5 (rest) | done: the live tier, the whole-surface lab, the staged-evidence path | a measured surface candidate the operator can activate in one click |
| P6 | done: the root workflow runs the same gate as `check:all` | one gate, one place, documented |

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
- `test_surface_context_policy.py` — the manifest bounds and the memory bounds
  a surface may set.
- `test_rsl_guardrails.py` — the guardrail rules; `test_graph.py` — a run that
  breaks a guardrail FAILS with the named code.
- `test_delegation_tool.py` — the delegated child inherits the surface's prompt
  and the NARROWED tool set.
- `test_surface_lab.py` — the variants are bounded and derived; a critical
  regression vetoes; an unmeasured variant never wins; the scripted tier reports
  "flat" and NO winner.
- `test_surface_candidate.py` — ONE surface identity and row; the staged winner
  is inert; nothing is staged without a winner.
- `test_rsl_digest.py` — the digest (UNKNOWN, never a fake zero);
  `test_drift_watch.py` — the opt-in drift candidate; `rsl-weekly-card.test.tsx`
  — the card; `test_evaluation_nightly.py` — a PLANTED regression must fail the
  unattended session and be named in the report.

See ADR-H278 (post-landing + hot config), ADR-H279 (live ablation + replay
labels), ADR-H282 (parallel candidate verification) and ADR-H283 (tool guidance
is not authority) for the decisions, and `docs/harness/architecture.md` for the
module map.
