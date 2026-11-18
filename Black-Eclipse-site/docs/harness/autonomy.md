---
title: Autonomy — goals, gates, loops and heartbeats (W4)
status: Current
last-verified: 2026-11-17
owner: Agent runtime
---

# Autonomy (W4)

Eclipse can carry an objective across turns without a human re-prompting it, and
it can run a session-scoped cadence. The design rule is simple: **deterministic
gates are authoritative; the judge is advisory; the user always wins.**

This doc explains the system as built. The plan and slice history are in
`docs/harness/roadmap/w4-autonomy-plan.md`.

## Why it exists

Hermes-style harnesses offer `/goal`, `/loop` and `/heartbeat`. Eclipse already
had durable tasks, leases, retries, evidence verifiers and a sandboxed command
broker. W4 connects those existing seams into a bounded autonomy loop instead of
adding a second agent loop or scheduler.

## Components

| Piece | File | Responsibility |
|---|---|---|
| Goal contract | `python/harness/tasks/model.py` (`GoalContract`, `GoalGate`) | Objective, deliverables, constraints, acceptance, budgets, `verification`/`boundaries`/`stop_when`; a gate names a closed command class |
| Goal store | `python/harness/goals/store.py` | `GoalRecord` (contract/gates/turns/session/model/workspace/`currentRunId`), `GoalVerdict`, `GoalGateRun`, `AutonomyLoop`; additive migrations `2026-11-12-006-goal-autonomy` and `2026-11-17-007-goal-live-turn` |
| Goal loop | `python/harness/goals/goal_runtime.py` | Create, start a turn (a durable task), evaluate gates → judge → verdict, apply `done/continue/blocked/wait`, pause/resume/cancel, no-progress guard |
| Gate runner | `python/harness/goals/gates.py` | Closed `COMMAND_CLASSES` + validated argv → `policy.decide_command` → `sandbox.run`; tail-only output; exit-code failure is definitive |
| Judge | `python/harness/goals/judge.py` | One strict-JSON model call (one repair), gate-aware downgrade, no tools, no transcript |
| Loop runtime | `python/harness/goals/loop_runtime.py` | Session loops/heartbeats; idle-only, coalescing, digest suppression, max ticks, one run in flight |
| Wiring | `python/harness/goals/bootstrap.py`, `python/harness/tasks/bootstrap.py` | Install on the service, subscribe terminal task events, register the heartbeat on the automation tick |
| API | `python/harness/routers/autonomy.py`, `src/app/api/{goals,loops}` | Operator-gated create/read/control/verdicts/health |
| Commands | `src/lib/harness/commands/*` | `/goal`, `/goal status|pause|resume|cancel`, `/loop`, `/heartbeat` |
| UI | `src/components/chat/goal-bar.tsx`, `src/lib/harness/clients/autonomy-browser.ts` | Goal turns, gate status, last verdict, next tick; pause/resume/cancel. The browser calls the Next `/api/goals` + `/api/loops` front door (never the server-only `autonomy-client`, which imports the Python launcher) |

## The turn loop

```
goal created ──► plan + first task (durable)
                     │
             TaskScheduler claims it
                     │
              service.run (the ONE runtime)
                     │
        terminal task event (completed/failed/blocked)
                     │
              GoalRuntime.evaluate
                     ├─ run gates (deterministic, sandboxed)
                     │    └─ any fail ──► continue (or blocked at the turn cap); judge NOT called
                     ├─ all pass ──► judge (strict JSON, one repair)
                     │    ├─ done     ──► complete through the task verifier
                     │    ├─ continue ──► next durable task with a compact brief
                     │    ├─ wait     ──► paused + nextRunAt
                     │    └─ blocked  ──► park the task BLOCKED with the reason
                     └─ no-progress guard: 3 identical verdicts ⇒ blocked
```

A continuation is a **fresh run**, carrying the contract, the last failing gate
tail, the evidence handles and the next-step hint — never the transcript. The
turn cap (`HARNESS_GOAL_MAX_TURNS`, default 20) and the goal's `TaskBudget` are
the spend ceiling; exceeding a budget ends the task BLOCKED with the violated
cap named (the existing scheduler path). Reaching the turn cap ends the goal
**BLOCKED** with the reason named; `/goal extend <turns>` (bounded, audited) is
the only way to grant more.

Two invariants keep a turn honest:

- **A failed run never reaches the judge.** Gates and the judge are skipped when
  the dispatched run did not complete; the next turn's brief carries the failure.
  (Before this, a failed run still paid for a gate sweep and a judge call.)
- **A judge `done` must pass the task verifier.** Completion goes through
  `verify_task` — the same authority the chat settlement path uses — and the task
  is completed *before* the goal is marked completed. A judge can say `continue`,
  `blocked` or `wait`; it can never complete a goal on prose alone.

A goal created from chat is **session-scoped** (`sessionId`), so the "user always
wins" rule has a session to inspect. A goal turn is also **visible in the chat
transcript**, as ONE message per turn: `useGoalWatch` polls the front door while
the conversation is open and fills that message with the turn's live tool steps
(read from the same persisted trace the Agent Workspace replays), then finalises
the same id with the verdict — so the steps and the verdict never split into two
bubbles. The first poll only primes the seen-set, so reopening a chat never
replays old verdicts or old steps. The GoalBar remains the live status strip.
One active goal per session is enforced (`GOAL_ALREADY_ACTIVE`) unless the caller
passes `allowParallel`. A goal turn is
a normal task run dispatched **inside the goal's workspace**
(`RunRequest.workspaceId` from the task metadata), so the agent's edits and the
gates check the same tree.

A turn is enqueued as a **TODO** task: the scheduler's atomic claim accepts only
TODO, so marking a turn IN_PROGRESS at enqueue time (the old behavior) stranded
it invisibly and the goal sat active forever. `start_tasks` also repairs rows the
old path left behind (`repair_orphaned_goal_tasks`, scoped to `metadata.goalId`).
A plan that `recompute_plan` marked COMPLETED when the previous turn finished is
reopened before the next task is queued (`resume_plan_for_work`, audited REOPEN;
plus the same repair at boot), because the scheduler only runs tasks in a
RUNNING plan. The completion verifier is chosen from the contract's `taskType`; `/goal --type
finance|research|code|...` pins it, and inference prefers an explicit code
*action* ("build", "implement", "fix") over a passing mention of a code noun —
"data available in this app" no longer makes a backtest goal a code task.

`/goal retry` (API `POST /goals/{id}/reevaluate`) re-reads the **last finished
turn's** run and judges it again without starting a new run. It is the recovery
path for a transient judge/schema failure or a verifier that has since become
satisfiable. The status strip lists every active goal (not just the newest) and
shows its phase: `queued` while the turn is TODO, `running` while the task is in
flight, plus the live run id and per-goal verdict history.

A task-dispatched turn keeps the agent's **own** tool surface
(`context.taskRun` skips the chat code profile) and enables the analysis sandbox
(`RunRequest.analysisEnabled`). Without those, a finance goal could describe a
backtest but never fetch `get_historical_prices` or compute with `analysis_run` —
the exact failure the live finance goal exposed. A **backtest is research, not
execution**: the trading-intent classifier is word-bounded and treats
backtest/simulation markers as analysis, so a rule's “entry”/“exit” and an
acceptance's “all” can never narrow the run to the 18-tool trade surface; task
runs skip the trade surface entirely, so a quoted previous verdict cannot
re-classify them. The turn brief for `finance`/`data` goals names that
data/compute route explicitly. The judge now also receives the run's token/tool/
step counts (it used to read an always-empty `metrics` object).

## Gates

A gate is **not** a shell string:

```json
{ "id": "typecheck", "check": "typecheck", "args": {}, "timeoutSeconds": 600, "retries": 0 }
```

`check` is one of `unit_test`, `python_test`, `typecheck`, `lint`, `build`,
`format_check`. `build_argv` pins an absolute executable and validates every
argument; `sandbox.run` scrubs the environment (no `HARNESS_*`, no callback
token, no provider keys), uses the workspace root as cwd, and enforces the
timeout/output caps.

- A goal with gates **must** have a live `workspaceId`; creation refuses
  otherwise (`WORKSPACE_REQUIRED_FOR_GATES`). When the code workspace capability
  is installed the id is also resolved at creation, so a released workspace is
  refused (`WORKSPACE_UNAVAILABLE`) instead of failing every turn.
- A `plan_only` goal cannot declare gates (`GATES_REQUIRE_EXECUTION`).
- A non-zero exit is returned once and never retried. Only infrastructure
  failures (`COMMAND_EXECUTABLE_MISSING`, `SANDBOX_UNAVAILABLE`, timeout) may be
  retried, up to the gate's `retries`.
- Output is stored tail-only (3 KB) and the judge is told it is untrusted data.

## The judge

- Called **only** when every gate passed (or when the goal declares no gates).
- Returns `done | continue | blocked | wait`, a reason, evidence handles, an
  optional `nextStep`, and `wakeAt` (required for `wait`).
- Invalid JSON: one schema-repair attempt, then `blocked`
  (`JUDGE_INVALID_OUTPUT`). Before validation the answer is normalized: a
  `decision`/`status`/`result` key is accepted as the verdict, `completed`/
  `in_progress`/`stuck` map to the closed enum, `explanation`/`summary` is the
  reason, snake_case fields are accepted, nulls and extra keys are dropped, and
  fenced JSON is unwrapped. The VALUE is still validated against the enum, so a
  near-miss key can never manufacture a verdict the model did not give. A `done` with a red gate or a non-completed run is
  downgraded to `continue`.
- The judge never sees messages, never runs a tool, and never streams to the UI.
- Model precedence: `HARNESS_GOAL_JUDGE_PROVIDER`/`MODEL` → the goal's stored
  provider/model → `HARNESS_TASK_*` / `HARNESS_JOB_*` defaults.

## Loops and heartbeats

A loop is a **heartbeat on the existing automation tick**
(`AutomationEngine._loop → _tick → _due_tick`), not a scheduler.

`/loop [interval] <prompt>` and `/heartbeat every <interval> <prompt>` start one;
`/loop status|pause|resume|cancel [id]` inspects and controls the session's loops
from chat (the GoalBar exposes the same actions).

- `fixed` repeats at `intervalSeconds`; `self_paced` backs off `1→2→4→8→15` min.
- A tick never fires while any run in that session is active; it defers.
- A heartbeat additionally defers while the newest session run is not its own.
- Missed ticks coalesce to one.
- A reply whose normalized digest is unchanged is not delivered; after
  `HARNESS_LOOP_MAX_NO_CHANGE` (default 3) the loop auto-pauses.
- `maxTicks` (default `HARNESS_LOOP_MAX_TICKS`, 50) ends the loop `completed`.
- Cancellation is cooperative; an active run is cancelled through
  `service.cancel(runId)`.
- `nextTickAt` is durable, so a restart resumes the cadence; a missed tick fires
  once.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `HARNESS_GOAL_LOOP` | `on` | `on` / `shadow` (record goal verdicts; start no autonomous turn or loop) / `off`. The loop is user-initiated (`/goal`) and `HARNESS_AUTONOMY=off` still vetoes it. With `off`, `POST /goals` refuses (`GOAL_ENGINE_OFF`) instead of creating a goal nothing will evaluate. |
| `HARNESS_AUTONOMY` | unset = on | Pre-existing global kill switch; `off` vetoes W4 |
| `HARNESS_GOAL_MAX_TURNS` | 20 | Hard turn ceiling |
| `HARNESS_GOAL_GATE_TIMEOUT_S` | 600 | Per-gate ceiling |
| `HARNESS_GOAL_JUDGE_PROVIDER` / `_MODEL` | empty | Optional judge model |
| `HARNESS_GOAL_MAX_TOKENS` | 0 | Optional per-turn token cap |
| `HARNESS_LOOP_MIN_INTERVAL_S` | 60 | Minimum cadence |
| `HARNESS_LOOP_MAX_TICKS` | 50 | Default loop cap |
| `HARNESS_LOOP_MAX_NO_CHANGE` | 3 | Auto-pause threshold |

## API

Operator-gated (transport/token only, same as `/code/*`):

- `POST /goals`, `GET /goals`, `GET /goals/{id}`
- `POST /goals/{id}/pause|resume|cancel|extend|reevaluate`
- `GET /goals/{id}/verdicts`
- `POST /loops`, `GET /loops`, `POST /loops/{id}/pause|resume|cancel`
- `GET /autonomy/health`

The Next.js front door mirrors them under `/api/goals`, `/api/loops` and
`/api/autonomy/health`. Create requests carry provider/model/baseUrl only; a
credential is never stored on a goal or loop. `POST /goals` returns **409
`GOAL_ENGINE_OFF`** when `HARNESS_GOAL_LOOP=off` — it refuses to create a goal
the engine will never evaluate.

## Events

`goal.created`, `goal.turn.queued`, `goal.turn.started`, `goal.gate.started`/`finished`,
`goal.verdict`, `goal.extended`, `goal.completed`/`paused`/`blocked`/`cancelled`,
`loop.created`, `loop.tick`, `loop.delivered`, `loop.no_change`,
`loop.paused`/`cancelled`/`completed`. They ride the existing event bus; a run's
own trace is unchanged.

## Known limitations (honest)

- **Background credentials.** A goal/loop continuation uses the same provider
  resolution as a scheduled task: the Python runtime reads `HARNESS_TASK_*` /
  `HARNESS_JOB_*` (or the provider's environment key). The TS settings vault is
  not readable from Python, so a cloud provider configured only in the vault
  will make the continuation/judge `blocked (unconfigured)` rather than invent an
  answer. A keyless local provider (Ollama) works out of the box.
- **Gate workspace.** Gates require a durable code workspace id. `/goal` fills
  it from the session's newest code task when `--workspace` is omitted, and
  refuses (`NO_WORKSPACE`) rather than looping on `WORKSPACE_MISSING`.
- **Judge quality.** The judge is advisory by design. It cannot pass a red gate,
  and a `done` still has to pass `verify_task`, so a weak model can only cause
  `continue`/`blocked`, never a false completion.
- **No-progress detection.** The digest excludes the judge's free-form reason
  (verdict + gates + evidence only), so rephrasing the same non-progress three
  times ends the goal instead of buying another turn.
- **`/subgoal`.** Not implemented; the task DAG already expresses sub-work.
  Deferred deliberately.

## Tests

- `python/tests/test_w4_autonomy.py` — flags, contract, store roundtrip,
  gate ordering/retry rules, judge invalid JSON and red-gate downgrade,
  continuation/turn cap, task-event bridge, loop unchanged-reply pause,
  busy-session deferral, plus the hardening cases: digest stability, verifier
  refused completion, one-active-goal, turn rollback, live-run cancel,
  released-workspace refusal, failed-run short-circuit.
- `python/tests/test_w4_autonomy_api.py` — operator gate, goal/loop lifecycle,
  workspace-required gates, engine-off refusal, extend, health.
- `python/tests/test_tasks_scheduler.py` — a task's declared workspace reaches
  `RunRequest.workspaceId`.
- `src/lib/harness/commands/command-handlers-autonomy.test.ts` — session +
  workspace binding, repeated gates, gate scoping, engine-off copy, extend,
  show/verdicts.
- Existing coverage that must stay green: `test_goal_runtime.py`,
  `test_c4_goals.py`, `test_tasks_*`, `test_automation_*`, `test_flags.py`.
