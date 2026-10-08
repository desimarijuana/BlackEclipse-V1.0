---
title: Task / Plan System
status: Current
last-verified: 2026-10-08
---

# Task / Plan System

**Who this is for:** anyone asking "how does Eclipse track multi-step work, and
why did a step run, wait, retry or refuse to complete?"

The Task / Plan System is Eclipse's **durable execution backbone**. A `Plan`
contains an arbitrary hierarchy of `Task`s. Tasks carry dependencies, acceptance
criteria, priorities, agent assignments, retries and leases. The scheduler
discovers runnable tasks, claims them atomically under a lease, and dispatches
each one through the EXISTING runtime (`service.run`) — so a task run is an
ordinary run with its own trace, events, tool executions and verification. There
is no second agent loop, no second tool registry and no second model adapter.

It lives in `python/harness/tasks/` and persists to the ONE `agent-memory.db`
connection (never `eclipse-memory.db`, never `jdds.db`).

## Where it sits

```
Planner / agent ──create_plan, create_task, add_dependency …──►  TaskManager
                                                                    │  (state machine)
                                                                    ▼
                                                              HarnessPlan / HarnessTask / …
                                                              (agent-memory.db)
                                                                    ▲
                                          TaskScheduler (claim + lease + retry)
                                                                    │
                                                                    ▼
                                                    service.run(RunRequest)   ← the ONE run plane
```

`orchestration/` (see `docs/harness/parallel-orchestration.md`) is the
*within-a-run* parallel primitives layer (`task_fork`/`task_join`/…). The Task /
Plan System is the *durable, cross-run* graph. They are complementary: a task
run may itself use `task_fork` to fan out.

## Package layout

| Module | Owns |
|---|---|
| `model.py` | The closed vocabularies (states, priorities, reasons, dependency kinds, event types) and the validated input contracts. |
| `state.py` | The task and plan state machines — closed transition tables, no wildcards. |
| `store.py` | The durable tables on the ONE agent-memory connection; the atomic claim SQL. |
| `dag.py` | Pure graph math: cycle detection, unmet dependencies, parent status, weighted progress, topological layers. |
| `manager.py` | `TaskManager` — the ONE writer of task/plan state (CRUD, dependencies, criteria, verification, cancellation, roll-ups). |
| `context.py` | The execution context envelope built from durable state, and its renderer. |
| `scheduler.py` | `TaskScheduler` — claim, heartbeat, retry/backoff, lease-expiry recovery, dispatch. |
| `tools.py` | The curated LLM-facing tool surface. |
| `bootstrap.py` | Boot wiring onto `AgenticService` (the production executor). |

## Task states

Exactly one of: `TODO`, `IN_PROGRESS`, `BLOCKED`, `WAITING`, `FAILED`,
`COMPLETED`, `CANCELLED`. No module mutates status directly; every change goes
through `TaskManager`, which asks `state.py` first.

```
TODO ──► IN_PROGRESS ──► COMPLETED
 │            ├────────► FAILED
 │            ├────────► WAITING ──► (resume) TODO
 │            ├────────► BLOCKED ──► (unblock) TODO
 │            └────────► CANCELLED
 ├──► BLOCKED / WAITING / FAILED / CANCELLED
```

A terminal state (`COMPLETED`/`FAILED`/`CANCELLED`) has no ordinary outgoing
edge. Crossing back requires an explicit **operation**:

- `retry_task` — `FAILED`/`BLOCKED`/`WAITING` → `TODO` (also used for a stale
  `IN_PROGRESS` lease).
- `reopen_task` — a terminal state → `TODO`.
- `recover` — `IN_PROGRESS` → `TODO` (a crashed worker's lease lapsed).

`WAITING` and `BLOCKED` are deliberately separate: **WAITING** is an external
event (`USER_INPUT`, `APPROVAL`, `EXTERNAL_EVENT`, `TOOL`, `SCHEDULE`, `AGENT`);
**BLOCKED** is an unavailable prerequisite (`DEPENDENCY`, `RESOURCE`,
`PERMISSION`, `PARENT`). `BLOCKED` dependency edges carry `blockedBy` (the unmet
prerequisite ids) so the UI can name what it is waiting for.

## Hierarchy and roll-up

A task may nest under a parent to any depth. A task with children is a
**container**: it is never dispatched directly. Its status and progress are
DERIVED from its children (`dag.derive_parent_status` / `derive_parent_progress`):

- all required children `COMPLETED` → parent `COMPLETED`;
- a required child `FAILED`/`CANCELLED` under `FAIL_FAST` → parent `FAILED`;
- any child `IN_PROGRESS` or `TODO` → parent `IN_PROGRESS` (a container is only
  `BLOCKED`/`WAITING` when *all* of its remaining work is);
- progress is the weighted mean, with a `COMPLETED` child counting as 100 and the
  result clamped to 0..100.

A child marked `required=False` never fails or blocks its parent.

### Plan status roll-up

A plan's status is derived the same way: once a task reaches a terminal state,
`TaskManager.recompute_plan` sets the plan to `COMPLETED` when every task is
`COMPLETED`, `FAILED` when any task failed, `CANCELLED` when every task was
cancelled, `BLOCKED` when all remaining work is blocked, otherwise `RUNNING`.
Only a legal transition is applied, so a plan stays `PLANNING` until `start_plan`.
This is why a plan finishes on its own when its last task completes.

## Dependencies (DAG)

`HarnessTaskDependency` is a directed edge `(taskId, dependsOnTaskId)` with kind
`BLOCKS` / `REQUIRES` (required) or `OPTIONAL` (ordering only). A task is created
`BLOCKED` when a required prerequisite is not yet `COMPLETED`, and is unblocked
exactly once — when its LAST required prerequisite completes (diamonds unblock
once).

**Cycle detection runs before the row is written**: `manager._check_no_cycle`
combines the prospective edges with the plan's existing edges and rejects a cycle
with `DEPENDENCY_CYCLE`. A self-edge and a cross-plan edge are rejected too.

## Runnable predicate

`TaskManager.is_runnable` (and `runnable_tasks`, priority-ordered) is the
deterministic predicate the scheduler uses:

```
status == TODO
AND not claimed
AND past any backoff (`availableAt`)
AND it is a leaf (no children)
AND every REQUIRED dependency is COMPLETED
AND its parent is live (not terminal/cancelled)
```

## The scheduler

`TaskScheduler` is one lifespan task (started beside the job scheduler). One tick
at a time, bounded in-flight work (`HARNESS_TASK_MAX_IN_FLIGHT`, default 2).

1. **Recover** — every `IN_PROGRESS` task whose lease expired is recovered (see
   below).
2. **Discover** — runnable tasks of `RUNNING` plans (and plan-less tasks), highest
   priority first.
3. **Claim** — `claim_task` is a single conditional `UPDATE … WHERE status='TODO'
   AND claimToken IS NULL AND (availableAt IS NULL OR availableAt <= now)`. SQLite
   serializes writes, so two workers racing for the same task cannot both win
   (proved by a 100-way concurrency test).
4. **Execute** — build a `TaskContext` from durable state, open a
   `HarnessTaskExecution` attempt, and call the injected executor (the production
   one calls `service.run`). A heartbeat task extends the lease while the run is
   in flight.
5. **Settle** — on a completed run, apply any returned criteria, then
   `complete_task` (which VERIFIES the contract and may refuse). On failure,
   retry with exponential backoff when the error class is retryable, otherwise
   fail.

### Retry

`RETRYABLE_ERRORS` (timeouts, rate limits, provider/network/infra failures, lease
expiry) retry with exponential backoff up to `maxRetries`; everything in
`NON_RETRYABLE_ERRORS` (validation, permission, security) fails immediately. The
backoff gate is `Task.availableAt`, so the next tick simply does not see the task
until the delay has passed.

### Recovery

A crashed worker leaves a task `IN_PROGRESS` with an expired lease. The scheduler
closes the stale execution as `TIMED_OUT`, releases the claim, and applies the
retry policy — a task is never left permanently `IN_PROGRESS`.

### Cancellation

`cancel_task` records `TASK_CANCEL_REQUESTED`, then cancels the task and every
non-terminal descendant deepest-first. If a cancellation lands while a run is in
flight, the scheduler sees the task is no longer `IN_PROGRESS` and records the
execution as `CANCELLED` instead of completing it — no orphaned running child.

## Completion is verified, not asserted

`complete_task` calls `verify_completion`, which fails when:

- a required dependency is not `COMPLETED`;
- a required subtask is not `COMPLETED`;
- a required acceptance criterion is not `PASSED`;
- `metadata.requireOutputReference` is set and no output reference exists;
- `metadata.requiredArtifacts` names an artifact that is not attached.

A refusal emits `TASK_COMPLETION_REJECTED` and returns a `COMPLETION_REJECTED`
error. `force=True` completes anyway but emits an auditable
`TASK_COMPLETION_OVERRIDDEN` event — never a silent override.

An agent saying "done" cannot complete a task: the RUN must complete through the
runtime AND the contract must pass. When a run completes, the scheduler marks the
task's declared criteria `PASSED` with the run id as evidence unless the task sets
`metadata.criteriaRequireExplicit` (then only explicitly reported criteria pass).

## Events, executions, checkpoints, artifacts

- `HarnessTaskEvent` is the immutable history (every transition emits one; also
  published on the process bus as `task.*` for live subscribers).
- `HarnessTaskExecution` is one attempt per row (attempt, agent, run id, status,
  error class, metrics) — the debugging trail.
- `HarnessTaskCheckpoint` is a durable resume boundary (label + payload).
- `HarnessTaskArtifact` is a REFERENCE (uri/digest/label), never the bytes.

## Tools and API

LLM-facing tools (permission `read` — a task is agent-local state, like a memory
save): `create_plan`, `read_plan`, `run_plan`, `create_task`, `read_task`,
`list_tasks`, `read_task_tree`, `update_task`, `complete_task`, `cancel_task`,
`delete_task`, `add_subtask`, `decompose_task`, `add_dependency`,
`remove_dependency`, `start_task`, `block_task`, `unblock_task`, `retry_task`,
`attach_task_artifact`, `set_task_criterion`, `checkpoint_task`.

Operator-gated HTTP routes (reads AND mutations, the jobs/MCP convention):
`GET/POST /plans`, `GET /plans/{id}`, `GET /plans/{id}/tasks`,
`POST /plans/{id}/start`, `GET/POST /tasks`, `GET/PATCH/DELETE /tasks/{id}`,
`GET /tasks/{id}/tree|events|dependencies`,
`POST /tasks/{id}/start|complete|cancel|retry|reopen|block|unblock|criteria|artifacts|checkpoints`,
`POST/DELETE /tasks/{id}/dependencies…`, `PATCH /criteria/{id}`.

### UI

The mounted **Tasks** screen (`src/components/screens/tasks/tasks-screen.tsx`,
AppTab `tasks`) renders the plan list and the live task tree: status, priority,
progress, blocked/waiting reasons, retry count, acceptance criteria and per-task
actions (Complete / Retry / Block / Unblock / Cancel, mark a criterion passed).
Every value comes from `/api/plans` + `/api/tasks` — the real store, polled every
5s; there is no mock data. The browser-safe client is
`src/lib/harness/tasks-browser.ts` (fetch only, over the Next proxy routes
`src/app/api/tasks/[[...path]]/route.ts` and `src/app/api/plans/[[...path]]/route.ts`);
`src/lib/harness/tasks-client.ts` is the server-side client that reaches the
Python runtime directly.

## Security

- Every route carries `require_operator`.
- A task's `metadata` is DATA: the runtime never reads a permission or tool grant
  out of it.
- A task runs with the executor's own authority (the run's resolved allowlist,
  autonomy and effect authorizer); assignment does not widen it.
- All external input is validated by the pydantic contracts before persistence.

## Testing

`python/tests/test_tasks_{state,dag,manager,scheduler,tools,api}.py` cover the
state machine, the graph math, the manager (hierarchy, dependencies, cycles,
criteria, cancellation, roll-ups), the scheduler (100-way claim race, retry and
backoff, lease-expiry recovery, cancellation mid-run), the tool surface, the API
surface, and an end-to-end DAG dispatch through the PRODUCTION executor
(`build_task_executor`) — only the model backend is a test double.

`python/tests/test_tasks_e2e.py` runs the SAME path through the REAL runtime: a
real `AgenticService`, the real scheduler, and the real `service.run` →
`execute_run` graph, with only the LLM scripted at the ONE `build_chat_model`
seam. It proves a plan reaches `COMPLETED` on its own, that each task produced a
real `HarnessRun` row, that a rejected completion fails the task and the plan,
and that model-settings precedence (task → plan → env) holds — deterministically,
with no network.

## Configuration

Environment overrides: `HARNESS_TASK_MAX_IN_FLIGHT`, `HARNESS_TASK_TICK_SECONDS`,
`HARNESS_TASK_LEASE_SECONDS`, and the model defaults
`HARNESS_TASK_PROVIDER/MODEL/BASE_URL/API_KEY` (falling back to the jobs'
`HARNESS_JOB_*`).

**Model settings precedence** for a task run: the task's own
`metadata.modelSettings`, then its PLAN's `metadata.modelSettings` (so a whole
plan can pin a provider), then the env default. A headless run still needs SOME
provider; with none configured the run fails honestly (`RUNTIME_UNAVAILABLE`),
never with a fabricated answer.
