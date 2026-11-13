---
title: W4 — Autonomy: Goal, Loop, Heartbeat (Detailed Plan)
status: Implemented (core)
last-verified: 2026-11-12
owner: Agent runtime
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
baseline: docs/harness/baselines/w0-0a7ec906-2026-11-12.json
scope: planning only — no production code changed
---

# W4 — Autonomy: Goal, Loop, Heartbeat

## Implementation status (2026-11-12)

**Landed:**

- `config/flags.py` — `HARNESS_GOAL_LOOP` (`off|shadow|on`, default `off`) plus
  the turn/gate/judge/loop caps; `HARNESS_AUTONOMY` remains the global kill
  switch and vetoes W4.
- `tasks/model.py` — `GoalContract` gains `verification`, `boundaries`,
  `stop_when`; new `GoalGate` (closed check vocabulary).
- `goals/model.py` / `goals/store.py` — `Goal` read view fields; additive
  migration `2026-11-12-006-goal-autonomy` (`GoalRecord` columns,
  `GoalVerdict`, `GoalGateRun`, `AutonomyLoop`) and the CRUD/verdict/loop
  methods.
- `goals/gates.py` — closed-broker gate runner with tail capture and the
  "failing exit is definitive" rule.
- `goals/judge.py` — strict-JSON advisory judge with one repair and the red-gate
  downgrade.
- `goals/goal_runtime.py` — create, durable task per turn, gate-first
  evaluation, continuation, no-progress guard, pause/resume/cancel.
- `goals/loop_runtime.py` + `goals/bootstrap.py` — session loops/heartbeats on
  the existing automation tick, task-event bridge, health.
- `routers/autonomy.py` + `main.py` — `/goals`, `/loops`, `/autonomy/health`.
- Next.js front door (`src/app/api/{goals,loops}`), typed client, `/goal`,
  `/loop`, `/heartbeat` commands and the chat goal bar.
- Tests: `test_w4_autonomy.py` (14) and `test_w4_autonomy_api.py` (6), plus the
  existing goal/task/automation/flag suites.

**Known limitation (unchanged from scheduled tasks):** a background continuation
resolves provider credentials from `HARNESS_TASK_*`/`HARNESS_JOB_*` (or the
provider's env key); the Python runtime cannot read the TS settings vault. A
cloud provider configured only in the vault therefore yields a truthful
`blocked (unconfigured)` verdict instead of a fabricated answer.

W4 closes the gap that Hermes fills with `/goal` + a judge loop, `/loop`, and
`/heartbeat`: **Eclipse cannot carry an objective across turns on its own, and
it has no deterministic "is this actually done?" gate in the chat path.** It has
most of the machinery already — durable tasks, leases, retries, verifiers,
evidence and a sandboxed command broker — but the chat path never runs a goal
loop and there is no in-session cadence.

This document is the implementation plan. It corrects three assumptions in the
parent plan (`hermes-inspired-improvement-plan.md` §W4) after reading the code:

1. **Do not create `autonomy/goal_runtime.py`.** A root-level `goal_runtime.py`
   already exists for durable chat intake, and `goals/` already owns the goal
   store/runtime. W4 extends those two seams; a third module would be a second
   goal authority.
2. **Do not add `GoalContract` to `goals/model.py`.** The single contract type is
   `tasks/model.py::GoalContract`, which already travels on the durable task.
   W4 extends it; `goals/model.py::Goal` is the read view.
3. **`HARNESS_AUTONOMY` already means "the recovery autonomy kill switch."**
   Reusing it as W4's on/off flag would silently change behavior. W4 gets its own
   flag and checks the existing kill switch as a veto (§3.1).

It also tightens two safety rules:

- A gate that fails on exit code is **definitive**: it is not retried and never
  reaches the judge. Retries apply only to infrastructure failures.
- A loop/heartbeat tick is a **heartbeat**, not a scheduler. It runs on an
  existing tick and starts at most one session run at a time.

**Duration:** 4.5–5.5 engineer-weeks (fits the parent plan's 4–5 plus hardening).
**Flag:** `HARNESS_GOAL_LOOP=off|shadow|on` (default `off`).
**Depends on:** W0 flags/baseline, W1 model gateway, W2 context economics, W6 run
kernel. W4 reads the gateway/run plane but adds no model client.

---

## 0. Implementation status (2026-11-12)

**Landed already (reuse, do not rebuild):**

| Capability | Where | What W4 uses |
|---|---|---|
| Deterministic goal intake | `tasks/goal.py::intake_goal`, `durable_decision`, `budget_violations` | Turns a request into `GoalContract` + `TaskType` with no model call |
| Durable chat→task lifecycle | `goal_runtime.py::wrap_service_for_goals`, `maybe_start_goal`, `settle_goal` | Wraps `service.run` / `run_background`; settles through the task verifier |
| Goal + evidence store | `goals/store.py` (`GoalRecord`, `GoalPlan`, `GoalStep`, `EvidenceClaim`, `EvidenceHandleRow`, `PlanIteration`), `goals/runtime.py::PlanRuntime`, `goals/answer.py` | The goal read view, evidence ledger, replan and answer enforcement |
| Durable task runtime | `tasks/manager.py`, `tasks/scheduler.py`, `tasks/store.py`, `tasks/verification.py`, `tasks/context.py` | One scheduler, leases, retries, per-agent/plan caps, verifier dispatch, a run = `service.run` |
| Types/contracts | `tasks/model.py` (`GoalContract`, `TaskBudget`, `TaskType`, `TaskStatus`) | The contract that travels on the task |
| Scheduled work | `automation/engine.py`, `automation/service.py`, `automation/model.py` | The interval/cron tick that W4's loop runtime hooks into |
| Closed command broker + sandbox | `code/commands.py` (`COMMAND_CLASSES`, `resolve_class`, `build_argv`), `code/sandbox.py` (`RunSpec`, `build_env`, `run`), `code/policy.py` (`decide_command`, `WorkspaceBinding`) | Deterministic gates with a fixed argv and no shell |
| Flags | `config/flags.py`, `run_flags.py` | Declared flag + per-run snapshot |
| Slash commands | `src/lib/harness/commands/command-registry.ts`, `command-router.ts`, `command-handlers.ts` | `/goal`, `/loop`, `/heartbeat` |

**Missing (the actual W4 work):**

- `GoalContract` has no `verification`, `boundaries` or `stop_when`.
- `GoalRecord` has no contract, gates, turn counter, last verdict, session or
  wakeup; `goals/model.py::Goal` mirrors only the old columns.
- No gate runner; no judge; no `GoalVerdict` audit; no continuation run.
- No session-scoped loop or heartbeat; no idle/coalesce/digest rules.
- No `/goal`, `/loop`, `/heartbeat`; no `/goals` API; no goal bar.
- `HARNESS_AUTONOMY` is declared for W4 but has no W4 consumer, and it means
  something else in `recovery/envelope.py`.

---

## 1. What we adopt from Hermes — and what we deliberately do not

| Hermes behavior | W4 in Eclipse | Why the mechanism differs |
|---|---|---|
| `/goal <objective>` sets a session objective | `GoalRecord` + `GoalContract` on a durable task | Eclipse already has a contract + task runtime; a goal is data, never a prompt |
| A judge decides "done" | Deterministic gates first; judge only after all gates pass | Hermes trusts the model; Eclipse has a sandbox and a verifier, so the model must not be the authority |
| Judge loops until done | `maxTurns`, no-progress counter, cost/token caps, pause/resume/cancel | Unbounded "continue" is the main spend risk |
| `/loop [interval] <prompt>` | Session-scoped `AutonomyLoop` (fixed or self-paced) | Reuses the existing run plane; no second scheduler |
| `/heartbeat every <interval> <prompt>` | Idle-only session heartbeat with coalescing and digest de-dup | Must never fire mid-run or fight a user message |
| Continuation keeps context | A compact goal brief: contract + last gate output + evidence handles | Do not replay the transcript (cost + drift) |

**Not adopted:** a separate Hermes-style agent loop, a plugin-level judge, a
second scheduler, or a shell string as a gate. Gates are a closed vocabulary.

---

## 2. Design invariants (non-negotiable)

1. **One goal authority.** `tasks/model.py::GoalContract` is the contract;
   `goals/model.py::Goal` is the read view; `GoalStore` is the store. No new
   contract type, no second goal table, no third runtime module.
2. **One scheduler.** Goal continuation is a durable task dispatched by
   `TaskScheduler`. Loop/heartbeat ticks ride the automation engine's existing
   pass (`AutomationEngine._loop` → `_tick` → `_due_tick`), not a new
   `asyncio` loop.
3. **Gates are data over the closed broker.** A gate names a
   `code/commands.py::COMMAND_CLASSES` entry plus validated arguments and a
   workspace binding. No free-form command strings, no shell metacharacters.
4. **A failing gate is definitive.** Non-zero exit is `continue` (or `blocked`
   after the turn cap) and never calls the judge. Infrastructure errors
   (`COMMAND_EXECUTABLE_MISSING`, `SANDBOX_UNAVAILABLE`, timeout) are the only
   retryable gate outcomes.
5. **The judge is advisory and bounded.** Strict JSON; one schema-repair
   attempt; invalid output becomes `blocked`. The judge never sees the full
   transcript and never runs tools.
6. **Continue is a fresh run.** It carries the contract, the last gate tail, the
   evidence handles and the next-step hint — not the prior messages.
7. **The user wins.** A user message in the session pauses autonomous
   continuation and defers heartbeat/loop ticks. No tick fires while the session
   has an active run.
8. **Fail closed.** Unknown autonomy profile, missing workspace for a declared
   gate, unknown gate class, unconfigured provider → typed refusal or `blocked`,
   never a fabricated success.
9. **Additive schema only.** Old goals and tasks load unchanged; every new
   column is nullable or defaulted.
10. **Two switches.** `HARNESS_GOAL_LOOP` enables the engine;
    `HARNESS_AUTONOMY=off` vetoes every unattended action, including W4.

---

## 3. Decisions to make before coding

### 3.1 `HARNESS_AUTONOMY` is taken (must resolve)

Today:

- `config/flags.py` declares `HARNESS_AUTONOMY` as a W4 bool with default `off`.
- `recovery/envelope.py::autonomy_enabled()` reads the **raw env var** and treats
  *absent* as `True`; `HARNESS_AUTONOMY=0/false/off` is a global kill switch.
- `docs/harness/failure-recovery.md` documents it as the recovery kill switch.
- The W0/W1/W2 baselines snapshot it as `"off"` (from the flag registry), even
  though the recovery path would consider autonomy enabled when the var is unset.

**Decision:** keep `HARNESS_AUTONOMY` as the global "*unattended actions*" kill
switch and give W4 its own engine flag:

```
HARNESS_GOAL_LOOP = off | shadow | on        (default off, owner W4)
```

- `off` — no goal evaluation, no loop ticks, commands return "autonomy is off".
- `shadow` — gates and the judge run and verdicts are recorded, but a `continue`
  never starts a run. This is the canary mode.
- `on` — `continue` starts the next turn subject to every cap.
- W4 also calls `recovery.envelope.autonomy_enabled()`; if false, the engine
  refuses to act even when `HARNESS_GOAL_LOOP=on`.

Update `config/flags.py`, `docs/harness/roadmap/w0-flags-and-review.md`,
`.env.example`, `docs/harness/failure-recovery.md` and the W0 baseline note so
the flag has one meaning. Add a kill-switch test asserting both vetoes.

### 3.2 Which goal type is authoritative

**Decision:** extend `tasks/model.py::GoalContract`; do not duplicate it.

```python
class GoalContract(BaseModel):          # tasks/model.py (extended)
    objective: str = ""
    deliverables: list[str] = []        # existing
    constraints: list[str] = []         # existing
    acceptance: list[str] = []          # existing
    budgets: TaskBudget | None = None   # existing
    # W4 additions — all defaulted, so old rows/tasks load unchanged:
    verification: list[str] = []        # named gate ids that must pass
    boundaries: list[str] = []          # out-of-scope paths/actions
    stop_when: list[str] = []           # conditions the judge must honor
```

`goals/model.py::Goal` gains the mirror fields (`contract`, `gates`, `max_turns`,
`used_turns`, `last_verdict`, `session_id`, `next_run_at`, `no_progress`) as
plain dataclasses, populated from the new columns. `GoalStore.get_goal` reads
them with safe defaults so an old row is still a `Goal`.

### 3.3 Gate vocabulary (closed)

**Decision:** a gate is a *named check*, not a command line.

```python
class GoalGate(BaseModel):              # tasks/model.py
    id: str                             # stable, unique within the goal
    check: str                          # ∈ unit_test|python_test|typecheck|lint|build|format_check
    args: dict[str, Any] = {}           # validated by commands.build_argv
    workspace_id: str | None = None     # required to execute; absent ⇒ gate cannot run
    timeout_seconds: int = 600          # clamped to the class's own ceiling
    retries: int = 0                    # infrastructure retries only
```

Why: `build_argv` already validates every argument against `ArgSpec` and pins an
absolute executable; `sandbox.run` already scrubs the env, caps output and
enforces resource limits. A free-form string would bypass all of it. The six
checks cover the acceptance lines the deterministic intake already produces
("tests pass", "the project builds without errors", "the type check passes",
"lint is clean", "the program runs…").

`/goal --gate unit_test` is sugar; the API stores the structured gate.

### 3.4 Loop/heartbeat storage and tick

**Decision:** a new session-scoped table (`AutonomyLoop`) plus a `LoopRuntime`
tick invoked once from the automation engine's `_due_tick` pass. Do **not** model a loop as an
`AutomationDefinition`:

- automations are operator-scoped, global, versioned and delivered as bots;
- a chat loop is session-scoped, idle-aware, coalesced and digest-suppressed;
- an automation has no `sessionId`, no "defer while the user is typing" and no
  "do not deliver an unchanged reply".

The tick is a heartbeat, not a scheduler: it checks `due` loops, skips any whose
session has an active run, and starts at most one `run_background` per loop.

### 3.5 Judge model

**Decision:** the judge is a separate one-shot call built with
`models.build_chat_model(settings)` and `model_runtime.structured`:

- settings precedence: `HARNESS_GOAL_JUDGE_PROVIDER`/`MODEL` → the goal's stored
  provider/model → `tasks/bootstrap.py::_task_model_settings` default;
- the goal stores `provider`, `model`, `baseUrl` only — **never an api key**;
  the key is resolved at call time from the environment/vault, exactly as a
  scheduled task does today;
- no streaming, no deltas, no tool access;
- an unconfigured provider is a `blocked` verdict with `UNCONFIGURED_PROVIDER`,
  not a silent heuristic.

---

## 4. Data model and migration

Add one new migration to `goals/store.py::GOAL_MIGRATIONS` (id
`2026-11-12-006-goal-autonomy`). Additive only; `MigrationRunner` applies it on
the one `agent-memory.db`.

```sql
-- Extend the goal record (nullable/defaulted so old rows load).
ALTER TABLE GoalRecord ADD COLUMN contract TEXT;          -- GoalContract JSON
ALTER TABLE GoalRecord ADD COLUMN gates TEXT;             -- [GoalGate] JSON
ALTER TABLE GoalRecord ADD COLUMN maxTurns INTEGER NOT NULL DEFAULT 20;
ALTER TABLE GoalRecord ADD COLUMN usedTurns INTEGER NOT NULL DEFAULT 0;
ALTER TABLE GoalRecord ADD COLUMN lastVerdict TEXT;       -- GoalVerdict JSON
ALTER TABLE GoalRecord ADD COLUMN sessionId TEXT;
ALTER TABLE GoalRecord ADD COLUMN nextRunAt TEXT;         -- 'wait' wakeup
ALTER TABLE GoalRecord ADD COLUMN noProgressCount INTEGER NOT NULL DEFAULT 0;
ALTER TABLE GoalRecord ADD COLUMN modelProvider TEXT;
ALTER TABLE GoalRecord ADD COLUMN modelName TEXT;
ALTER TABLE GoalRecord ADD COLUMN modelBaseUrl TEXT;
ALTER TABLE GoalRecord ADD COLUMN workspaceId TEXT;

-- One row per evaluated turn: the durable audit of what the judge saw.
CREATE TABLE IF NOT EXISTS GoalVerdict (
  id          TEXT PRIMARY KEY,
  goalId      TEXT NOT NULL,
  runId       TEXT,
  turn        INTEGER NOT NULL,
  verdict     TEXT NOT NULL,          -- done|continue|blocked|wait
  reason      TEXT,
  evidence    TEXT,                   -- [EvidenceHandle] JSON
  gateResults TEXT,                   -- [GateResult] JSON
  usage       TEXT,                   -- {tokens,toolCalls,modelSteps,durationMs}
  createdAt   TEXT NOT NULL,
  FOREIGN KEY (goalId) REFERENCES GoalRecord(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_goal_verdict_goal ON GoalVerdict(goalId, createdAt);

-- One row per gate execution: a failure is inspectable without JSON parsing.
CREATE TABLE IF NOT EXISTS GoalGateRun (
  id         TEXT PRIMARY KEY,
  goalId     TEXT NOT NULL,
  verdictId  TEXT,
  gateId     TEXT NOT NULL,
  checkName  TEXT NOT NULL,
  exitCode   INTEGER,
  timedOut   INTEGER NOT NULL DEFAULT 0,
  durationMs INTEGER,
  outputTail TEXT,                    -- last 3 KB, never the whole log
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goal_gate_goal ON GoalGateRun(goalId, createdAt);

-- Session-scoped loop / heartbeat.
CREATE TABLE IF NOT EXISTS AutonomyLoop (
  id               TEXT PRIMARY KEY,
  sessionId        TEXT NOT NULL,
  kind             TEXT NOT NULL,     -- loop|heartbeat
  prompt           TEXT NOT NULL,
  mode             TEXT NOT NULL,     -- fixed|self_paced
  intervalSeconds  INTEGER NOT NULL,
  nextTickAt       TEXT,
  lastTickAt       TEXT,
  maxTicks         INTEGER NOT NULL DEFAULT 50,
  usedTicks        INTEGER NOT NULL DEFAULT 0,
  noChangeCount    INTEGER NOT NULL DEFAULT 0,
  lastDigest       TEXT,
  lastRunId        TEXT,
  status           TEXT NOT NULL,     -- active|paused|cancelled|completed
  modelProvider    TEXT,
  modelName        TEXT,
  modelBaseUrl     TEXT,
  workspaceId      TEXT,
  createdAt        TEXT NOT NULL,
  updatedAt        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loop_session ON AutonomyLoop(sessionId, status);
CREATE INDEX IF NOT EXISTS idx_loop_next ON AutonomyLoop(status, nextTickAt);
```

Notes:

- **No foreign key from `GoalVerdict.goalId` to a task.** A goal may exist before
  a task; the task remains the execution unit.
- **`GoalRecord.contract` is the serialized contract**, so a goal read does not
  need the task. The task also carries the same contract (existing behavior);
  the goal runtime keeps them in sync at create and on update.
- **Gate output is untrusted data.** It is stored tail-only and rendered inside a
  delimited block in the judge prompt; it is never concatenated as instructions.

---

## 5. Contracts and modules

### 5.1 `goals/model.py` — the read view

```python
@dataclass
class Goal:
    id: str
    objective: str
    acceptance: tuple[str, ...] = ()
    plan_id: str | None = None
    task_id: str | None = None
    status: str = "active"                  # + paused
    budget: dict[str, Any] = field(default_factory=dict)
    contract: dict[str, Any] | None = None  # GoalContract JSON
    gates: list[dict[str, Any]] = field(default_factory=list)
    max_turns: int = 20
    used_turns: int = 0
    last_verdict: dict[str, Any] | None = None
    session_id: str | None = None
    next_run_at: str | None = None
    no_progress: int = 0
    created_at: str = ""
    updated_at: str = ""
```

Add `"paused"` to `GOAL_STATUSES`. Add `GOAL_VERDICTS =
frozenset({"done","continue","blocked","wait"})`.

### 5.2 `goals/gates.py` — deterministic gate runner

```python
@dataclass(frozen=True)
class GateResult:
    gate_id: str
    check: str
    ok: bool
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    output_tail: str
    error_code: str = ""       # COMMAND_* | SANDBOX_UNAVAILABLE | WORKSPACE_MISSING

def validate_gate(raw: dict[str, Any]) -> GoalGate: ...
def run_gate(gate: GoalGate, binding: WorkspaceBinding) -> GateResult: ...
def run_gates(gates: list[GoalGate], binding: WorkspaceBinding) -> list[GateResult]: ...
```

`run_gate`:

1. `command_class = commands.resolve_class(gate.check)` — raises a typed
   `CommandUnavailable` for an unknown/absent/gated class.
2. `argv = commands.build_argv(command_class, gate.args)` — validated args only.
3. `policy.decide_command(actor, binding, gate.check, argv)` — the same
   profile/permission gate as a chat command; an autonomy profile that cannot
   execute yields `PROFILE_DENIED`.
4. Cap the timeout to `min(gate.timeout_seconds, command_class.timeout_s)`.
5. `sandbox.run(RunSpec(argv=argv, cwd=binding.root, env=sandbox.build_env(),
   timeout_s=cap, output_cap_bytes=command_class.output_cap_bytes,
   network=command_class.network))`.
6. `ok = exit_code == 0 and not timed_out and not killed`.
7. Tail-truncate output to 3 KB (a helper that keeps the last N chars and says
   how much was dropped).

Retry rule: retry only when `error_code` is an infrastructure code, up to
`gate.retries`, with a short fixed backoff. A non-zero exit is returned
immediately.

### 5.3 `goals/judge.py` — the advisory judge

```python
JUDGE_SCHEMA = {
  "type": "object",
  "required": ["verdict", "reason"],
  "properties": {
    "verdict": {"enum": ["done", "continue", "blocked", "wait"]},
    "reason": {"type": "string", "maxLength": 800},
    "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 24},
    "wakeAt": {"type": "string"},          # required only for "wait"
    "nextStep": {"type": "string", "maxLength": 500},
  },
  "additionalProperties": False,
}

async def judge(contract, gate_results, run_summary, evidence, settings) -> GoalVerdict
```

Prompt rules:

- the contract and `stop_when` are quoted verbatim;
- gate results are a compact table (id, check, exit, tail);
- run summary is the run's `status`, `output` head/tail and metrics, not messages;
- evidence handles are ids, not contents;
- gate output is wrapped in `<gate_output>` and explicitly labelled untrusted;
- the model is told that gates are authoritative and that `done` is invalid while
  any gate is red.

Parsing: `StructuredOutputManager.parse_and_validate`; one repair prompt; a second
failure returns `blocked` with `JUDGE_INVALID_OUTPUT`. Map a schema-valid but
nonsensical verdict (e.g. `done` with a red gate) to `continue` and record the
downgrade — gates remain authoritative even if the judge is wrong.

### 5.4 `goals/goal_runtime.py` — the goal loop

New module in the `goals` package (not the root `goal_runtime.py`):

```python
class GoalRuntime:
    def __init__(self, service): ...
    def create(self, objective, *, contract, gates, max_turns, session_id,
               workspace_id, model) -> Goal
    def start_turn(self, goal_id) -> str          # creates a durable task, returns task id
    async def evaluate(self, goal_id, run_id) -> GoalVerdict
    def apply(self, goal_id, verdict) -> str      # done|continue|blocked|wait|paused
    def pause(self, goal_id, reason) -> Goal
    def resume(self, goal_id) -> Goal
    def cancel(self, goal_id) -> Goal
    def list_verdicts(self, goal_id, limit=50) -> list[dict]
```

`start_turn` reuses the existing seam:

- create a child task under the goal's plan with
  `metadata = {"goalId": g.id, "turn": n, "modelSettingsRef": {...}}`,
  `task_type` from the intake, and the extended `GoalContract` as `goal_contract`;
- `manager.start_task(...)`; the scheduler dispatches it through the one executor
  (`build_task_executor` → `service.run`) with the goal context in the query;
- the goal query is a **brief**, not the transcript:
  `objective + deliverables + constraints + boundaries + acceptance + gates +
  last gate tail + last verdict reason + nextStep + "do not repeat completed work"`.

`evaluate` order (the heart of W4):

1. Load the goal, its gates and the workspace binding. Missing binding with
   declared gates ⇒ `blocked` (`WORKSPACE_MISSING`).
2. `run_gates`. Persist `GoalGateRun` rows.
3. Any gate `ok=False` ⇒ `continue` (if turns remain) or `blocked`
   (`GATE_FAILED`) when `used_turns >= max_turns`. **The judge is not called.**
4. Collect evidence handles from the run (`goals/store.py::goal_for_run` +
   `list_claims`) and the run summary.
5. Call the judge. Validate the verdict. A `done` with a red gate is downgraded.
6. Persist `GoalVerdict`; update `used_turns`, `last_verdict`, `next_run_at`.
7. `apply` the verdict:
   - `done` → `set_goal_status("completed")`; complete the task through
     `manager.complete_task` (never bypass the verifier);
   - `continue` → if `used_turns >= max_turns` → `paused` (`TURN_BUDGET`);
     else `start_turn`;
   - `wait` → status `paused` with `next_run_at` (the tick wakes it); a `wait`
     with no `wakeAt` is treated as `blocked`;
   - `blocked` → `set_goal_status("blocked")`, park the task BLOCKED with the
     reason named (no retry storm).
8. No-progress guard: if the verdict and evidence digest are identical for two
   consecutive turns, increment `no_progress`; at 3, force `blocked`
   (`NO_PROGRESS`) regardless of the judge.

Where it is wired: extend `goal_runtime.settle_goal` (root module) to hand a
completed durable task to `GoalRuntime.evaluate` when the goal has gates or
`max_turns > 0`. Keep the existing verifier path unchanged when W4 is off. This
preserves "a chat turn must never break over goal bookkeeping".

### 5.5 `goals/loop_runtime.py` — loops and heartbeats

```python
class LoopRuntime:
    def create(self, session_id, *, kind, prompt, interval_s, mode,
               max_ticks, model, workspace_id) -> Loop
    def list(self, session_id) -> list[Loop]
    async def tick(self, now) -> dict          # called from AutomationEngine.tick
    def pause(self, loop_id, reason) -> Loop
    def resume(self, loop_id) -> Loop
    def cancel(self, loop_id) -> Loop
```

`tick(now)`:

1. Select `status='active' AND nextTickAt <= now`, oldest first, bounded (e.g. 8).
2. For each:
   - session deleted / loop cancelled → skip;
   - the session is busy — any `store.session_runs(session_id)` id is in
     `service._active`, or the loop's own `lastRunId` is active → **defer**
     (`nextTickAt = now + min(interval, 60s)`), never queue;
   - user activity since the last tick (session was touched) and
     `kind='heartbeat'` → defer (user wins);
   - `usedTicks >= maxTicks` → `completed`;
   - else start one `run_background` with a loop brief and `context.loopId`.
3. Schedule the next tick:
   - fixed → `now + intervalSeconds`;
   - self-paced → the ladder `1, 2, 4, 8, 15` minutes, advancing when the reply
     digest is unchanged, reset when it changes.

Idle definition: the session has no active run (see above) and no
`SessionMessage` newer than `lastTickAt` (through the existing store reader),
not a new presence system.

Digest/no-busywork: compute `sha256` of the normalized assistant text (the run's
`output`/final message) and compare to `lastDigest`; on a match, increment
`noChangeCount`, do **not** deliver, and after 3 consecutive matches auto-pause
(`NO_CHANGE`). On a change, deliver and reset the counter.

Cancellation: mark `cancelled`; if the current loop run is active,
`service.cancel(runId)` (cooperative, at the run boundary).

### 5.6 `goals/service.py` — the thin orchestration facade

One small service that the router and the tick share:

```python
class AutonomyService:
    def __init__(self, service): ...
    # goals
    def create_goal(...); def get_goal(...); def list_goals(...)
    def pause_goal(...); def resume_goal(...); def cancel_goal(...)
    def verdicts(...)
    # loops
    def create_loop(...); def list_loops(...)
    def pause_loop(...); def resume_loop(...); def cancel_loop(...)
    async def tick(self, now) -> dict
    def health(self) -> dict
```

It owns no execution and no model call; it delegates to `GoalRuntime`,
`LoopRuntime` and `GoalStore`. This keeps the router dumb and testable.

---

## 6. API, commands, UI

### 6.1 Harness routes

New `python/harness/routers/autonomy.py` (included by `main.py`; operator-gated
like `/code/*` and `/recovery/*`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/goals` | Create a goal from an objective + optional contract/gates |
| GET | `/goals` | List goals (session filter) |
| GET | `/goals/{id}` | Goal, contract, gates, turns, last verdict |
| POST | `/goals/{id}/pause` | Pause autonomous continuation |
| POST | `/goals/{id}/resume` | Resume (respects caps) |
| POST | `/goals/{id}/cancel` | Cancel; cancels the active run |
| GET | `/goals/{id}/verdicts` | Verdict + gate audit |
| POST | `/loops` | Create a loop/heartbeat |
| GET | `/loops` | List loops (session filter) |
| POST | `/loops/{id}/pause\|resume\|cancel` | Loop lifecycle |
| GET | `/autonomy/health` | Flag mode, due loops, active goals, counters |

Request/response schemas go in `schemas.py` (pydantic, camelCase via the existing
`_CAMEL` pattern). A create-goal request must include `model {provider, model,
baseUrl?}` or the runtime uses the env default; **never an api key**.

### 6.2 Front door

- `src/app/api/goals/route.ts`, `src/app/api/goals/[id]/route.ts`,
  `src/app/api/goals/[id]/{pause,resume,cancel,verdicts}/route.ts`
- `src/app/api/loops/route.ts`, `src/app/api/loops/[id]/route.ts`
- `src/lib/harness/autonomy-client.ts` — typed client, mirroring
  `code-client.ts` (validation + honest error mapping).

The routes proxy to the Python harness with the same operator auth as the other
harness routes. No new auth mechanism.

### 6.3 Slash commands

Add three specs to `command-registry.ts`:

```ts
const GOAL: CommandSpec = {
  id: "autonomy.goal",
  name: "goal",
  aliases: [],
  summary: "Set an objective Eclipse works toward until its gates pass.",
  category: "runtime",
  args: [{ name: "objective", description: "What to achieve.", variadic: true }],
  flags: [
    { name: "gate", description: "A check that must pass.", type: "string",
      values: ["unit_test", "python_test", "typecheck", "lint", "build", "format_check"] },
    { name: "turns", description: "Maximum turns.", type: "number" },
    { name: "workspace", description: "Workspace id the gates run in.", type: "string" },
    { name: "status", description: "Status, pause, resume or cancel an existing goal.",
      type: "string", values: ["status", "pause", "resume", "cancel"] },
  ],
  handler: { type: "native", target: "autonomy.goal" },
  permissions: { approval: "none" },       // creation is not an effect
  risk: "medium",
  executionMode: "async",
  output: { type: "response", summary: "The goal id, turn count and last verdict." },
  examples: ["/goal ship the watchlist widget with passing tests --gate typecheck",
             "/goal status", "/goal pause"],
};
```

`/loop` and `/heartbeat` mirror this with `interval` and `prompt` args; `/loop`
also accepts `--mode fixed|self-paced` and `--ticks N`. Add handlers in
`command-handlers.ts` (`autonomy.goal`, `autonomy.loop`, `autonomy.heartbeat`)
that call `autonomy-client.ts` and render `keyValue` cards. Add i18n keys under
`autonomy.*` in `src/lib/i18n/dictionaries/en.ts`.

Parsing note: the existing `command-parser.ts` handles positionals + `--flags`;
`/goal status` must be treated as `status` positional (not an objective) when it
is the only token. Implement that in the handler, not the registry.

### 6.4 Goal bar

A small `src/components/chat/goal-bar.tsx` mounted in the chat dock (reuse the
frosted-glass classes per the UI skill):

- objective (truncated), `turn n / max`, last verdict badge, last gate status,
  next wakeup;
- pause / resume / cancel buttons (operator actions);
- a "why" disclosure showing the last gate tail and the judge reason;
- for loops: a compact pill in the composer footer with tick count and cancel.

No new global state: read from the goals/loops client on mount and after each
terminal run event; poll at a low cadence or subscribe to the existing event bus.

---

## 7. Flags, budgets and caps

| Knob | Default | Meaning |
|---|---|---|
| `HARNESS_GOAL_LOOP` | `off` | `off` / `shadow` / `on` engine mode |
| `HARNESS_AUTONOMY` | (unset = on) | Existing global kill switch; `off` vetoes W4 |
| `HARNESS_GOAL_MAX_TURNS` | 20 | Hard ceiling for a goal's turns |
| `HARNESS_GOAL_GATE_TIMEOUT_S` | 600 | Ceiling per gate execution |
| `HARNESS_GOAL_JUDGE_PROVIDER` | — | Optional judge provider |
| `HARNESS_GOAL_JUDGE_MODEL` | — | Optional judge model |
| `HARNESS_LOOP_MIN_INTERVAL_S` | 60 | Minimum tick interval |
| `HARNESS_LOOP_MAX_TICKS` | 50 | Default cap per loop |
| `HARNESS_LOOP_MAX_NO_CHANGE` | 3 | Auto-pause after unchanged replies |
| `HARNESS_GOAL_MAX_TOKENS` | 0 (off) | Optional run-level token cap per turn |

Budgets are enforced after the run through the existing
`tasks/goal.py::budget_violations` and the scheduler's `BUDGET_EXCEEDED` path; no
new budget engine. A goal's `TaskBudget` is the single cap authority.

---

## 8. Events and observability

Emit on the existing bus (`service.bus.publish`) and, where a run exists, through
`RunEmitter` so the trace shows the loop:

| Event | Key fields |
|---|---|
| `goal.created` | `goalId`, `sessionId`, `gates`, `maxTurns` |
| `goal.turn.started` | `goalId`, `turn`, `taskId`, `runId` |
| `goal.gate.started` / `goal.gate.finished` | `goalId`, `gateId`, `check`, `exitCode`, `durationMs` |
| `goal.verdict` | `goalId`, `turn`, `verdict`, `reason`, `downgraded` |
| `goal.completed` / `goal.paused` / `goal.blocked` / `goal.cancelled` | `goalId`, `reason` |
| `loop.created` / `loop.paused` / `loop.cancelled` / `loop.completed` | `loopId`, `sessionId`, `kind` |
| `loop.tick` | `loopId`, `tick`, `action` (`started`/`deferred`/`skipped`) |
| `loop.delivered` / `loop.no_change` | `loopId`, `digest`, `runId` |

Add counters to `AutonomyService.health()`: goals by status, gates by result,
verdicts by kind, due loops, deferred ticks, judge parse failures. Expose via
`GET /autonomy/health`, and add a compact card to the existing observability
screen only if it fits (not required for W4).

---

## 9. Tests

All Python tests live in `python/tests/`; TS tests sit beside the modules.

**W4.0 foundations**
- `test_autonomy_flags.py` — `HARNESS_GOAL_LOOP` default `off`, `shadow`, `on`,
  invalid value → default, `HARNESS_AUTONOMY=off` vetoes, strict mode.
- `test_goal_store_migration.py` — a pre-W4 `GoalRecord` row loads unchanged;
  new columns default; re-running the migration is a no-op.

**W4.1 gates**
- `test_goal_gates.py` — a passing gate ⇒ `ok`; a failing exit ⇒ `ok=False` and
  no retry; unknown check ⇒ typed `COMMAND_NOT_ALLOWLISTED`; missing workspace ⇒
  `WORKSPACE_MISSING`; timeout ⇒ `timed_out`; output tail ≤ 3 KB; argv never
  contains model text.
- `test_goal_gates_sandbox.py` — env scrub (no `HARNESS_*`, no callback token),
  cwd is the binding root, network refused for a non-network class.

**W4.2 judge/verdict**
- `test_goal_judge.py` — valid `done`/`continue`/`blocked`/`wait`; invalid JSON
  → one repair → `blocked`; `done` with a red gate → downgraded to `continue`;
  `wait` without `wakeAt` → `blocked`; no tool access; prompt contains no raw
  gate output outside the delimited block.

**W4.3 continuation**
- `test_goal_runtime.py` — create/read; turn budget pauses; `continue` creates a
  second task with `goalId`; a failing gate never calls the judge (fake judge
  asserts not called); identical verdict/evidence three times → `blocked`
  `NO_PROGRESS`; pause/resume/cancel; completion goes through
  `manager.complete_task`.
- `test_goal_runtime_shadow.py` — `shadow` records a verdict but starts no run.

**W4.4 loop/heartbeat**
- `test_loop_runtime.py` — fixed cadence with a fake clock; self-paced ladder
  `1→2→4→8→15`; max ticks; no mid-run fire; digest no-change suppresses
  delivery and auto-pauses; cancellation is immediate.
- `test_heartbeat.py` — idle-only; a user message wins; missed ticks coalesce to
  one; a deleted session cancels the loop.
- `test_autonomy_resume.py` — a restart restores a goal's turns and a loop's
  `nextTickAt`; a paused goal stays paused; a `wait` goal wakes at `nextRunAt`.

**API + front door**
- `test_autonomy_routes.py` — create/list/pause/resume/cancel/verdicts; operator
  gate; unknown id → 404; invalid gate → 422; a create response never echoes an
  api key.
- TS: `autonomy-client.test.ts`, `command-registry.test.ts` additions,
  `command-handlers.test.ts` for `/goal status` vs `/goal <objective>`.

**Acceptance run:** `npm run test` (from `Black-Eclipse-site/`) and
`npx tsc --noEmit`; plus the offline eval gate unchanged.

---

## 10. Slice plan (sequenced)

| Slice | Work | Files | Acceptance | Effort |
|---|---|---|---|---|
| **W4.0** Foundations | Flag split; contract extension; migration; `Goal`/store read path; event names | `config/flags.py`, `tasks/model.py`, `goals/model.py`, `goals/store.py`, docs | Old goals load; flags tested; no runtime behavior change | 3–4 d |
| **W4.1** Gate runner | `goals/gates.py`; workspace resolution; tail capture; retry policy | `goals/gates.py`, `code/commands.py` (read-only reuse), `code/sandbox.py` (reuse) | Passing/failing gate; a failure never reaches the judge; sandbox env scrub | 4–5 d |
| **W4.2** Judge + verdict | `goals/judge.py`; schema; one repair; downgrade rule; `GoalVerdict`/`GoalGateRun` persistence | `goals/judge.py`, `goals/store.py`, `models.py` (reuse) | Valid/invalid JSON; red-gate `done` downgraded; no provider ⇒ blocked | 3–4 d |
| **W4.3** Continuation | `goals/goal_runtime.py`; task-per-turn; brief builder; no-progress; pause/resume/cancel | `goals/goal_runtime.py`, `goal_runtime.py` (extend), `tasks/*` (reuse) | `continue` starts a second task; budget pauses; 3 no-progress ⇒ blocked | 5–6 d |
| **W4.4** Loop + heartbeat | `goals/loop_runtime.py`; `AutonomyLoop` store; tick hook; digest; idle/coalesce | `goals/loop_runtime.py`, `goals/store.py`, `automation/engine.py` (one `_due_tick` hook) | Fixed/self-paced; caps; no mid-run; resume restores | 5–6 d |
| **W4.5** API + commands | `routers/autonomy.py`; front-door routes/client; registry + handlers + i18n | `routers/autonomy.py`, `main.py`, `src/app/api/{goals,loops}/**`, `src/lib/harness/{autonomy-client,commands}/*` | Commands work in chat and CLI; cancel is immediate | 3–4 d |
| **W4.6** Goal bar | Chat dock component; loop pill; pause/resume/cancel; disclosure | `src/components/chat/goal-bar.tsx`, `stock-chat.tsx`, i18n | Goal state visible; actions work; no layout regression | 3–4 d |
| **W4.7** Hardening + rollout | Shadow mode, canary, metrics, fault tests, docs | all above + `docs/harness/autonomy.md` | Shadow records only; canary caps hold; full suite green | 3–5 d |

Parallel split (two engineers):

- **A (runtime):** W4.0 → W4.1 → W4.2 → W4.3.
- **B (surface + cadence):** W4.4 after W4.0; W4.5 can start against the store
  interface; W4.6 after W4.5.
- W4.7 together.

---

## 11. Flows

### 11.1 Gate → judge → apply

```
run completes
   │
   ├─ load goal + gates + binding
   │     └─ no binding & gates declared ──► BLOCKED (WORKSPACE_MISSING)
   ├─ run_gates (deterministic, sandboxed, fixed argv)
   │     ├─ any fail ──► verdict=continue (judge NOT called)
   │     │                   └─ used_turns >= max ──► BLOCKED (GATE_FAILED)
   │     └─ all pass
   ├─ evidence = claims + handles + run summary
   ├─ judge (strict JSON, one repair)
   │     ├─ invalid ──► BLOCKED (JUDGE_INVALID_OUTPUT)
   │     ├─ done + red gate ──► downgrade to continue
   │     └─ valid
   ├─ persist GoalVerdict + GoalGateRun
   ├─ no-progress check (same verdict+evidence twice ⇒ count; 3 ⇒ BLOCKED)
   └─ apply
         ├─ done     ──► complete through the task verifier
         ├─ continue ──► start_turn (new run, brief, same goalId)
         ├─ wait     ──► paused + nextRunAt (tick wakes)
         └─ blocked  ──► park the task BLOCKED with the reason named
```

### 11.2 Loop/heartbeat tick

```
AutomationEngine._loop → _tick → _due_tick
   └─ LoopRuntime.tick(now)
        ├─ due = active AND nextTickAt <= now (bounded, oldest first)
        └─ for each
             ├─ cancelled/completed ──► skip
             ├─ session busy ──► defer (no queue)
             ├─ heartbeat + user active ──► defer
             ├─ used >= maxTicks ──► completed
             ├─ start run_background(loop brief, sessionId, model)
             └─ nextTickAt = fixed or self-paced ladder
```

### 11.3 Cancellation

- Goal: `status='cancelled'`; if `runId` is active, `service.cancel(runId)`; the
  scheduler sees the task cancelled and closes the execution.
- Loop: `status='cancelled'`; if the loop's run is active, cancel it; the next
  tick ignores it.
- User message: pause autonomous continuation for that session; defer heartbeat
  ticks; a `/goal resume` is required to continue.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Runaway spend | `maxTurns`, `TaskBudget` (tokens/tool calls/steps/duration), `maxTicks`, `no_progress`, `shadow` canary |
| Judge says `continue` forever | Gates first; no-progress counter; hard turn cap; budget-exceeded → BLOCKED |
| Judge output is malformed or adversarial | Strict schema, one repair, `blocked` on failure; gate output delimited and labelled untrusted |
| A gate command hangs | Per-class timeout + sandbox kill tree; retry only infrastructure errors |
| Gate bypasses policy | Gates resolve through `COMMAND_CLASSES` + `build_argv` + `decide_command`; no shell |
| Goal fights the user | User message pauses continuation; heartbeat is idle-only; resume is explicit |
| New scheduler / duplicate loop | Ticks ride `AutomationEngine.tick()`; runs go through `service.run_background`; continuation goes through `TaskScheduler` |
| Model key leakage | Goal/loop store provider/model/baseUrl only; key resolved at call time; create response never echoes it |
| App closed during a loop | `nextTickAt` is durable; on boot the tick sees a missed time and fires **once** (coalesced), never a burst |
| Schema drift | Additive migration + a test that a pre-W4 row loads unchanged |
| Session deleted | Loop tick skips and cancels; goal remains inspectable and cancellable |
| W4 flag changes recovery behavior | Separate `HARNESS_GOAL_LOOP`; `HARNESS_AUTONOMY` stays the global veto |

---

## 13. Rollout

1. **Land shadow** (`HARNESS_GOAL_LOOP=shadow`, default): goals evaluate gates
   and the judge, verdicts are recorded, `continue` starts nothing. Measure
   gate-failure rate, judge downgrades, invalid-output rate.
2. **Canary on**: enable for a single operator/session with `maxTurns=5` and a
   required gate; watch spend per goal and no-progress blocks.
3. **On**: raise the default turn cap; keep `shadow` available as a kill switch.
4. **Removal:** after two green weeks, either promote `HARNESS_GOAL_LOOP` to a
   plain bool default `on` (keeping `shadow` for one more cycle) or remove the
   `shadow` branch. `HARNESS_AUTONOMY` remains the global kill switch.

---

## 14. Definition of done

- [ ] A goal can be created with a contract, gates, a turn cap and a session.
- [ ] A failing gate never calls the judge and never completes a goal.
- [ ] A passing goal completes only through the task verifier.
- [ ] `continue` starts a new run with the goal brief, same `goalId`, within budget.
- [ ] A fixed and a self-paced loop run on cadence, never mid-run, and stop at caps.
- [ ] A heartbeat defers to a user message and coalesces missed ticks.
- [ ] Pause/resume/cancel work and survive a restart.
- [ ] `/goal`, `/goal status|pause|resume|cancel`, `/loop`, `/heartbeat` work in
      chat and the CLI; the goal bar shows turns, last gate and next wakeup.
- [ ] `HARNESS_GOAL_LOOP` and `HARNESS_AUTONOMY` kill switches are tested.
- [ ] Old goals/tasks load unchanged; the migration is idempotent.
- [ ] `npm run test` and `npx tsc --noEmit` pass; the offline eval gate is green.
- [ ] `docs/harness/autonomy.md` documents the contracts, caps and events;
      `CHANGELOG.md` records every slice.

---

## 15. Open questions (resolve before W4.1)

1. **Judge default:** same model as the run, or require an explicit
   `HARNESS_GOAL_JUDGE_MODEL`? Recommendation: same provider/model, with an
   override; never a paid model the user did not configure.
2. **Workspace for chat goals:** should `/goal` without a workspace be allowed
   with acceptance-only judging (no gates), or refused until a workspace is
   chosen? Recommendation: allow acceptance-only, mark `gates=[]`, and say so.
3. **Loop minimum:** is 60 s too aggressive for a local model? Recommendation:
   keep 60 s, but default `/loop` to self-paced so a slow local model backs off.
4. **Heartbeat persistence:** should a heartbeat survive a restart? Recommendation:
   yes, `nextTickAt` is durable; a missed tick fires once.
5. **Delivering loop output:** is an unchanged digest the only suppression rule,
   or should an empty/whitespace reply also count? Recommendation: both.
6. **`/subgoal`:** the parent plan lists it, but it adds a hierarchy the current
   task DAG already expresses. Recommendation: defer `/subgoal`; use a plan with
   multiple tasks instead.
