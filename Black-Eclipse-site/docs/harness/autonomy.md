---
title: Autonomy — goals, gates, loops and heartbeats (W4)
status: Current
last-verified: 2026-11-12
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
| Goal store | `python/harness/goals/store.py` | `GoalRecord` (contract/gates/turns/session/model/workspace), `GoalVerdict`, `GoalGateRun`, `AutonomyLoop`; additive migration `2026-11-12-006-goal-autonomy` |
| Goal loop | `python/harness/goals/goal_runtime.py` | Create, start a turn (a durable task), evaluate gates → judge → verdict, apply `done/continue/blocked/wait`, pause/resume/cancel, no-progress guard |
| Gate runner | `python/harness/goals/gates.py` | Closed `COMMAND_CLASSES` + validated argv → `policy.decide_command` → `sandbox.run`; tail-only output; exit-code failure is definitive |
| Judge | `python/harness/goals/judge.py` | One strict-JSON model call (one repair), gate-aware downgrade, no tools, no transcript |
| Loop runtime | `python/harness/goals/loop_runtime.py` | Session loops/heartbeats; idle-only, coalescing, digest suppression, max ticks, one run in flight |
| Wiring | `python/harness/goals/bootstrap.py`, `python/harness/tasks/bootstrap.py` | Install on the service, subscribe terminal task events, register the heartbeat on the automation tick |
| API | `python/harness/routers/autonomy.py`, `src/app/api/{goals,loops}` | Operator-gated create/read/control/verdicts/health |
| Commands | `src/lib/harness/commands/*` | `/goal`, `/goal status|pause|resume|cancel`, `/loop`, `/heartbeat` |
| UI | `src/components/chat/goal-bar.tsx` | Goal turns, gate status, last verdict, next tick; pause/resume/cancel |

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
cap named (the existing scheduler path).

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
  otherwise (`WORKSPACE_REQUIRED_FOR_GATES`).
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
  (`JUDGE_INVALID_OUTPUT`). A `done` with a red gate or a non-completed run is
  downgraded to `continue`.
- The judge never sees messages, never runs a tool, and never streams to the UI.
- Model precedence: `HARNESS_GOAL_JUDGE_PROVIDER`/`MODEL` → the goal's stored
  provider/model → `HARNESS_TASK_*` / `HARNESS_JOB_*` defaults.

## Loops and heartbeats

A loop is a **heartbeat on the existing automation tick**
(`AutomationEngine._loop → _tick → _due_tick`), not a scheduler.

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
| `HARNESS_GOAL_LOOP` | `off` | `off` / `shadow` (record goal verdicts; start no autonomous turn or loop) / `on` |
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
- `POST /goals/{id}/pause|resume|cancel`
- `GET /goals/{id}/verdicts`
- `POST /loops`, `GET /loops`, `POST /loops/{id}/pause|resume|cancel`
- `GET /autonomy/health`

The Next.js front door mirrors them under `/api/goals` and `/api/loops`. Create
requests carry provider/model/baseUrl only; a credential is never stored on a
goal or loop.

## Events

`goal.created`, `goal.turn.started`, `goal.gate.started`/`finished`,
`goal.verdict`, `goal.completed`/`paused`/`blocked`/`cancelled`, `loop.created`,
`loop.tick`, `loop.delivered`, `loop.no_change`, `loop.paused`/`cancelled`/
`completed`. They ride the existing event bus; a run's own trace is unchanged.

## Known limitations (honest)

- **Background credentials.** A goal/loop continuation uses the same provider
  resolution as a scheduled task: the Python runtime reads `HARNESS_TASK_*` /
  `HARNESS_JOB_*` (or the provider's environment key). The TS settings vault is
  not readable from Python, so a cloud provider configured only in the vault
  will make the continuation/judge `blocked (unconfigured)` rather than invent an
  answer. A keyless local provider (Ollama) works out of the box.
- **Gate workspace.** Gates require a durable code workspace id. A chat-created
  goal with no workspace can use acceptance + the judge, but cannot declare
  gates.
- **Judge quality.** The judge is advisory by design; a weak model can only
  cause `continue`/`blocked`, never a false `done` past a red gate.
- **`/subgoal`.** Not implemented; the task DAG already expresses sub-work.
  Deferred deliberately.

## Tests

- `python/tests/test_w4_autonomy.py` — flags, contract, store roundtrip,
  gate ordering/retry rules, judge invalid JSON and red-gate downgrade,
  continuation/turn cap, task-event bridge, loop unchanged-reply pause,
  busy-session deferral.
- `python/tests/test_w4_autonomy_api.py` — operator gate, goal/loop lifecycle,
  workspace-required gates, health.
- Existing coverage that must stay green: `test_goal_runtime.py`,
  `test_c4_goals.py`, `test_tasks_*`, `test_automation_*`, `test_flags.py`.
