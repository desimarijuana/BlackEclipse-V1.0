---
title: Task / Plan System
status: Current
last-verified: 2026-10-19
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
| `model.py` | The closed vocabularies (states, priorities, reasons, dependency kinds, event types, task types) and the validated input contracts (including `GoalContract` / `TaskBudget`). |
| `state.py` | The task and plan state machines — closed transition tables, no wildcards. |
| `store.py` | The durable tables on the ONE agent-memory connection; the atomic claim SQL; the additive `taskType`/`goalContract` columns. |
| `dag.py` | Pure graph math: cycle detection, unmet dependencies, parent status, weighted progress, topological layers. |
| `manager.py` | `TaskManager` — the ONE writer of task/plan state (CRUD, dependencies, criteria, verification, cancellation, roll-ups). |
| `context.py` | The execution context envelope built from durable state, and its renderer (quotes the most recent FAILED attempt). |
| `goal.py` | Round 4 (W8.1/W14): the deterministic goal intake (`intake_goal`, `classify_task_type`, `durable_decision`, `parse_required_sections`) and `budget_violations`. PURE. |
| `verification.py` | Round 4 (W8.4/W14): the task-type verifier registry (`verify_task`) — evidence-based completion per `taskType`, reading the real evidence shapes. PURE. |
| `scheduler.py` | `TaskScheduler` — claim, heartbeat, retry/backoff, lease-expiry recovery, dispatch, budget + verification gates. |
| `tools.py` | The curated LLM-facing tool surface (`create_goal` included). |
| `bootstrap.py` | Boot wiring onto `AgenticService` (the production executor). |

## Task states

Exactly one of: `TODO`, `IN_PROGRESS`, `VERIFYING`, `ASKING_USER`, `BLOCKED`,
`WAITING`, `FAILED`, `COMPLETED`, `CANCELLED`. No module mutates status directly;
every change goes through `TaskManager`, which asks `state.py` first.

```
TODO ──► IN_PROGRESS ──► VERIFYING ──► COMPLETED
 │            │              ├────────► FAILED
 │            ├────────► WAITING ──► (resume) TODO
 │            ├────────► ASKING_USER ──► (resume) TODO
 │            ├────────► BLOCKED ──► (unblock) TODO
 │            └────────► CANCELLED
 ├──► BLOCKED / WAITING / ASKING_USER / FAILED / CANCELLED
```

- **VERIFYING** is the authoritative state between a completed run and the
  completion decision: the scheduler enters it, then evaluates acceptance
  criteria and the completion contract. An interrupted verification is
  recoverable as `VERIFYING`, not indistinguishable from a plain run. It may
  resolve to any terminal outcome, or fall back to `IN_PROGRESS`/`TODO` when a
  check fails and must be repaired.
- **ASKING_USER** is the durable "parked on a human" state: a question or an
  approval (`WaitingReason.USER_INPUT`/`APPROVAL`) enters it, distinct from
  `WAITING` (an external event) and `BLOCKED` (an unavailable prerequisite).

A terminal state (`COMPLETED`/`FAILED`/`CANCELLED`) has no ordinary outgoing
edge. Crossing back requires an explicit **operation**:

- `retry_task` — `FAILED`/`BLOCKED`/`WAITING`/`VERIFYING`/`ASKING_USER` → `TODO`
  (also used for a stale `IN_PROGRESS` lease).
- `reopen_task` — a terminal state → `TODO`.
- `recover` — `IN_PROGRESS`/`VERIFYING` → `TODO` (a crashed worker's lease lapsed).

`WAITING` and `BLOCKED` are deliberately separate: **WAITING** is an external
event (`USER_INPUT`, `APPROVAL`, `EXTERNAL_EVENT`, `TOOL`, `SCHEDULE`, `AGENT`);
**BLOCKED** is an unavailable prerequisite (`DEPENDENCY`, `RESOURCE`,
`PERMISSION`, `PARENT`, and round 4's `VERIFICATION` — the task-type verifier
cannot pass with the evidence the work produced). `BLOCKED` dependency edges
carry `blockedBy` (the unmet prerequisite ids) so the UI can name what it is
waiting for.

### Escalation on retry exhaustion

By default an exhausted retry budget fails the task (`FAILED`). A task may opt
into ESCALATION by setting `metadata.escalateOnExhaustion` to `"BLOCKED"` or
`"ASKING_USER"`: the scheduler then transitions there (non-terminal, inspectable,
resumable) instead of failing — for a dead-end resource or a decision only a
human can make. `TaskManager.escalate_task` is the ONE writer; it emits
`TASK_ESCALATED`.


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
   fail. A `waiting` outcome (round 4, W5/W9) means the executor deliberately
   PARKED the task — an acquisition routed to a dependency, or an operator
   decision pending — and the scheduler records the execution honestly without
   retrying or failing it; the DAG (or an explicit resume) wakes the task.

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

### Verified completion by task type (round 4, W8.4; unified in W14)

`verify_completion` checks durable STATE (dependencies, children, criteria). The
task-type verifier checks EVIDENCE — and it runs FIRST, inside the scheduler,
between `begin_verification` and `complete_task`:

- `verify_task(task, …)` (`verification.py`) dispatches on `task.taskType`. A
  task with **no** `taskType` keeps the exact pre-W8 contract (the verifier
  returns `None`) — every pre-W8 task is unchanged.
- Verifiers read records the runtime already wrote: the run's
  `codeVerification` ledger (zero-exit `unit_test`/`python_test`/`build`/
  `typecheck`/`lint` records), attached artifact references, the research
  evidence (the ordinary run's `metadata.citations`/`collectedSources` and the
  gated run's `validation.claims` + `receipt.evidenceRefs`), the recorded
  document sections, the run's analysis records, observed metrics. Never the
  model's prose.
- `code` ⇒ the run completed, every check the acceptance/deliverables NAME has a
  zero-exit record (tests/build/typecheck/lint — matched on word boundaries, so
  the verb "build" is not a build check), and every declared deliverable has a
  matching delivered artifact. `research` ⇒ traceable sources, a claim backed by
  recorded evidence, and the uncertainty RECORDED (a partial answer that names
  no open gap is refused). `document` ⇒ a delivered artifact AND every section
  the contract required. `workflow` ⇒ observed steps AND an observable state
  change (the run id is not a result). `finance` ⇒ provenance, freshness and
  claim-to-evidence, deferring to the Evidence Engine's own verdict.
  `data` ⇒ a reproducible calculation: a recorded formula with its inputs, or an
  analysis that pinned the program it ran and the inputs it read.
  `general` ⇒ a completed run with a recorded result reference or artifact.
- A declared `taskType` with NO registered verifier is a REFUSAL, never a pass;
  a crashing verifier is also a refusal (`verification.py` logs and refuses).
- A failed verification with retry budget left is retried with the missing
  evidence NAMED — the next attempt's rendered context quotes the failure
  (`context.py` lists only CONCLUDED attempts and the renderer quotes the most
  recent FAILED one). With the budget exhausted the task ends `BLOCKED` with
  `blockedReason: VERIFICATION` and the exact missing evidence, emitting
  `TASK_COMPLETION_REJECTED` + `TASK_ESCALATED` — a non-terminal, inspectable
  dead end, never a confident "done" and never an infinite repair loop.
- On success the `run_complete` checkpoint payload carries the verdict
  (`verification: {ok, checks, missing}`), so a resumed or audited task shows
  WHAT proved it.

#### What the evidence is (round 4, W14)

The verifiers read the shapes the runtime REALLY writes, not an idealized
one. Two research shapes exist and both are read: the ordinary run's collected
blob (`source_collector.to_research_blob()`) and the gated run's blob
(`status`, `validation.claims`, `coverage`, `receipt.evidenceRefs`). Three
recordings were added so the rules above can be checked at all:

- **Required sections.** A contract names them deterministically
  (`goal.parse_required_sections` — only an explicit list counts: "sections:
  risks, methodology"). The intake turns a request that names sections into the
  acceptance line `the document contains the sections: …`, and the delivered
  document records the headings it wrote (`documents/authoring.py::
  report_authored_document` → the run's `authored` documents, or the processed
  document's IR sections). A document that recorded no structure cannot prove
  its sections — that is a refusal, not a pass.
- **Reproducible calculations.** The sandbox writes one `AnalysisRecord` per
  analysis (`analysis_tools._record_analysis`); the task outcome reads them as
  bounded evidence (`analysis_tools.load_run_analyses` → `evidence.analyses`),
  alongside the research engine's own calculation records
  (`research.metadata.calculations`). A number in prose is not a computation.
- **Observable state.** A workflow's "result" is an observed record — an
  artifact, a document, an analysis, a code record, a capability or collected
  sources. The run id the scheduler stores is NOT a result, so a workflow that
  started, called one tool and produced nothing is refused.


### Contract budgets (round 4, W8.6)

A `GoalContract` may declare `TaskBudget` caps (`maxDurationMs`, `maxToolCalls`,
`maxTokens`, `maxModelSteps` — the measurable classes; `maxParallelWorkers`
rides the scheduler's EXISTING per-agent concurrency cap via
`metadata.maxConcurrency`; unmeasurable caps such as model cost are not
invented). The scheduler compares them to the run's own recorded metrics AFTER
the run: exceeding a cap records the real usage, emits
`TASK_COMPLETION_REJECTED`, and ends the task `BLOCKED` with
`BlockedReason.RESOURCE` and the violated cap named — never a silent truncation
and never a retry that spends more of the same budget. A `None` observation
never violates a cap (unmeasured ≠ violation).

## The goal contract (round 4, W8.1)

`GoalContract` (`objective`, `deliverables`, `constraints`, `acceptance`,
`budgets`) plus a `TaskType` are DATA on the task (additive `taskType`/
`goalContract` columns; `metadata` stays free-form). The deterministic intake
`goal.intake_goal` derives them from a request — task-type classification on
word boundaries, deliverable objects from build/create-style clauses, acceptance
lines from the request's own check words — or from explicit fields (explicit
always wins). An ambiguous request earns exactly ONE clarifying question instead
of a guessed contract. The contract's `acceptance` lines BECOME the task's
criteria (deduped against explicit ones), so the structural contract and the
goal contract cannot disagree; `update_task` validates a supplied
`taskType`/`goalContract` through the same pydantic models (a bad shape is
`VALIDATION_ERROR`, never a raw dict into the store).

`goal.durable_decision` is the W8.2 rule: code/workflow work, multiple
deliverables, an explicit budget or multi-step phrasing ⇒ a durable task; a
single short result does not need one. The `create_goal` tool applies it — it
creates the plan + contract-bearing task (assigned `edit_verify`-era work runs
through the ordinary scheduler) and starts the plan; an ambiguous request
returns the question with `created: false`. **The chat path is now
durable-by-default too:** `goal_runtime.wrap_service_for_goals` (installed by
`install_task_layer`) wraps `service.run`/`run_background` — a durable chat
request creates the goal task BEFORE the run and the run is its FIRST attempt
(nothing executes twice), then settlement verifies through the task-type
verifier: verified completion, or a bounded repair attempt re-queued (TODO)
for the scheduler. A task-dispatched run is never wrapped again, and a
bookkeeping failure never breaks a chat turn.

## Events, executions, checkpoints, artifacts

- `HarnessTaskEvent` is the immutable history (every transition emits one; also
  published on the process bus as `task.*`/`workflow.*` for live subscribers).
- `HarnessTaskExecution` is one attempt per row (attempt, agent, run id, status,
  error class, metrics) — the debugging trail.
- `HarnessTaskCheckpoint` is a durable resume boundary (label + payload). The
  scheduler WRITES one at dispatch (`run_start`, carrying the run id/attempt/plan)
  and one on completion (`run_complete`); `TaskManager.restore_checkpoint` reads
  the latest and can move a stuck `IN_PROGRESS`/`VERIFYING` task back to `TODO`
  with its resume metadata applied. A terminal task is never reopened by a
  restore.
- `HarnessTaskArtifact` is a REFERENCE (uri/digest/label), never the bytes. After
  a run completes, `build_task_executor` links the run's catalog entries from the
  Artifact Center (tagged with the run id) to the task by reference
  (`artifact://<id>` + checksum), so a task owns a durable pointer to what it
  produced.

### Plan revision + cancellation

Structural changes to a plan (a new task, a new/removed edge) bump a monotonic
`metadata.revision` and emit `PLAN_REVISED`, so a plan change is auditable and a
stale view is detectable; completed work is never removed. `cancel_plan` cancels
every non-terminal task in a plan (deepest-first) and marks the plan
`CANCELLED`; a terminal plan is returned untouched.

## Tools and API

LLM-facing tools (permission `read` — a task is agent-local state, like a memory
save): `create_goal`, `create_plan`, `read_plan`, `run_plan`, `create_task`,
`read_task`, `list_tasks`, `read_task_tree`, `update_task`, `complete_task`,
`cancel_task`, `cancel_plan`, `delete_task`, `add_subtask`, `decompose_task`,
`add_dependency`, `remove_dependency`, `start_task`, `block_task`, `unblock_task`,
`retry_task`, `resume_task`, `escalate_task`, `attach_task_artifact`,
`set_task_criterion`, `checkpoint_task`.

Operator-gated HTTP routes (reads AND mutations, the jobs/MCP convention):
`GET/POST /plans`, `GET /plans/{id}`, `GET /plans/{id}/tasks`,
`POST /plans/{id}/start|cancel`, `GET/POST /tasks`, `GET/PATCH/DELETE /tasks/{id}`,
`GET /tasks/{id}/tree|events|dependencies|checkpoints`,
`POST /tasks/{id}/start|complete|cancel|retry|reopen|resume|escalate|block|unblock|criteria|artifacts|checkpoints`,
`POST /tasks/{id}/checkpoints/restore`,
`POST/DELETE /tasks/{id}/dependencies…`, `PATCH /criteria/{id}`.

### UI

The **Tasks** screen (`src/components/screens/tasks/tasks-screen.tsx`, AppTab
`tasks`, mounted in `stock-chat.tsx`) renders the plan list and the live task
tree: status, priority, progress, blocked/waiting reasons, retry count,
acceptance criteria and per-task actions (Complete / Retry / Block / Unblock /
Cancel, mark a criterion passed). It is reachable from the Agentic sidebar menu
(alongside ChatBot, Skills, Eclipse Memory and Artifacts). Every value comes from
`/api/plans` + `/api/tasks` — the real store, polled every 5s; there is no mock
data. The browser-safe client is `src/lib/harness/clients/tasks-browser.ts` (fetch only,
over the Next proxy routes `src/app/api/tasks/[[...path]]/route.ts` and
`src/app/api/plans/[[...path]]/route.ts`); `src/lib/harness/clients/tasks-client.ts` is
the server-side client that reaches the Python runtime directly.

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

`python/tests/test_tasks_state_hardening.py` covers the `VERIFYING`/`ASKING_USER`
lifecycle, scheduler-entered verification, retry-exhaustion escalation
(`BLOCKED`/`ASKING_USER`/default `FAILED`), plan cancel + revision, checkpoint
write/restore, Artifact-Center linking and retention pruning.

`python/tests/test_tasks_goal.py` pins the deterministic intake (task-type
classification, deliverable/acceptance inference, the ONE-question ambiguity
rule, the durable decision, budget comparison, contract persistence + update
validation). `python/tests/test_tasks_verification.py` pins the verifier
registry (dispatch, accept/reject per type against the REAL evidence shapes,
the required-section rule, the reproducible-calculation rule, deliverable
coverage, unknown and crashing verifiers refuse).
`python/tests/test_w14_verification_evidence.py` pins the evidence itself: the
analysis records are readable as bounded run evidence, the task outcome carries
them, an authored document records its headings, and the processed-document
list is unchanged by it. `python/tests/test_goal_completion.py` is the round-4
acceptance: build → deliberate defect → the verifier rejects → repair (told what
was missing) → verified completion with the artifact and the evidence-bearing
checkpoint; an unverifiable goal ends `BLOCKED` (`VERIFICATION`); an exceeded
budget ends `BLOCKED` (`RESOURCE`); a crashed worker's task resumes from its
durable claim/lease/checkpoint and delivers exactly once.

## Configuration

Environment overrides: `HARNESS_TASK_MAX_IN_FLIGHT`, `HARNESS_TASK_TICK_SECONDS`,
`HARNESS_TASK_LEASE_SECONDS`, `HARNESS_TASK_RETENTION_DAYS` (default 90; 0
disables), and the model defaults
`HARNESS_TASK_PROVIDER/MODEL/BASE_URL/API_KEY` (falling back to the jobs'
`HARNESS_JOB_*`). The scheduler applies retention at most once an hour to aged
checkpoints/executions/events only — never to plans, tasks, criteria or artifacts.

**Model settings precedence** for a task run: the task's own
`metadata.modelSettings`, then its PLAN's `metadata.modelSettings` (so a whole
plan can pin a provider), then the env default. A headless run still needs SOME
provider; with none configured the run fails honestly (`RUNTIME_UNAVAILABLE`),
never with a fabricated answer.
