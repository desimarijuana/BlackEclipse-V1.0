---
title: W7 — Delegation & File Safety (Detailed Plan)
status: Implemented (flag-gated)
last-verified: 2026-11-12
owner: Agent runtime + code filesystem
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
scope: W7 code landed behind flags; defaults preserve pre-W7 behaviour
---

# W7 — Delegation & File Safety

The W7 scorecard line reads:

> **No async delegation/steering/schema repair; no `/rollback` file checkpoints.**

That is accurate today. Eclipse has durable **runs**, durable **Fabric jobs**,
a bounded in-process **fan-out**, and an in-memory **per-operation** file
transaction — but it has no way to:

- let a parent continue while delegated work runs, then collect the result later;
- validate a child's output against a contract and repair it once;
- send a steering message into a running child at a safe boundary;
- give a writing child its own worktree and return a diff handle;
- list, diff and restore the file changes an agent made.

W7 closes those gaps **on existing seams**. It adds no second scheduler, agent
loop, model client, approval store or event bus. The Execution Fabric remains
the only durable job owner; `execute_run` remains the only agent loop;
`ToolRegistry` remains the only tool seam; `mcp/approvals.py` remains the only
single-use approval store; `FileSystemService` remains the only filesystem
facade.

**Duration:** 3–4 engineer-weeks.
**Dependencies:** W0 flag registry (landed), W6 run-kernel integrity (durable
effect/idempotency/lease seams), Phase 7 `delegate` (shipped), Execution Fabric
(shipped), `code/worktree.py` (shipped), `FileTransaction` (shipped).

---

## 0. Scorecard line → outcome

| Gap | Today | W7 outcome |
|---|---|---|
| Async delegation | `delegate` blocks the parent for up to 1 800 s | `delegate_async` returns durable job handles; the parent continues |
| Status/result | Only the synchronous return value | `delegate_status` / `delegate_result` / `delegate_cancel` / `delegate_wait` |
| Schema repair | Child prose is trusted; no contract | `output_schema` validated; **one** bounded repair turn; raw text preserved |
| Steering | Nothing reaches a running child | `delegate_steer`; delivered only at the child's next step boundary |
| Worktree per child | A writing child needs a workspace the parent already has | `isolated` child gets its own worktree; parent receives a diff handle, never an auto-merge |
| File checkpoints | In-memory only; commit discards | Shadow-git snapshots + `list` / `diff` / `restore` + `/rollback` |

---

## 1. Goals

1. **A parent never waits for a fan-out it does not need to wait for.** Three
   independent children should let the parent keep reasoning, then consume
   results when they are ready — without losing the result if the parent or the
   process dies.
2. **Every delegated result has a shape.** A child asked for structured output
   returns either valid data or an honest `schemaValid: false` with the raw text
   and the validation errors — never a fabricated object.
3. **A running child can be corrected.** An operator or parent can add context
   (a constraint, a changed requirement) and be certain it arrives at a step
   boundary, never in the middle of a tool call.
4. **A writing child cannot touch another child or the user's checkout.**
   Isolation is per child; the parent gets a diff to review.
5. **Every agent file mutation is undoable.** A bad edit is listable, diffable
   and restorable, and a restore itself is undoable.
6. **Nothing new becomes a second seam.** No new queue, approval store, agent
   loop, tool dispatch path or event bus.

## 2. Non-goals

- No unlimited fan-out. Existing caps stay: 4 children per fan-out, depth 2,
  bounded tokens/time.
- No mid-tool injection. Steering is delivered **before** the next model call,
  not into a running tool.
- No automatic merge of a child's worktree. The parent reviews and promotes.
- No second model call for routing/merging. Aggregation stays deterministic.
- No new database file. New durable rows live on the ONE `agent-memory.db`.
- No replacement of run checkpoints (`RunCheckpoint`). File checkpoints are a
  separate, clearly named concept.
- No restoring `.git`, databases, `.env`, secrets, ignored roots or the
  checkpoint store itself.
- No remote `$ref` resolution in `output_schema` (SSRF and surprise-network
  surface).
- No silent fallback when git is unavailable: an unavailable checkpoint store
  is reported, never simulated.

---

## 3. Current path (measured 2026-11-12)

### 3.1 Delegation

```
delegate tool                    delegation_tools.py:409
  └─ run_delegation(...)         delegation.py:465
       ├─ child_actor(...)       delegation.py:204   (narrowing; never operator)
       ├─ narrow_tools(...)      delegation.py:237
       ├─ asyncio.create_task    delegation.py:612   (in-process, all children)
       ├─ run_child(...)         delegation_tools.py:274
       │    └─ execute_run(...)  delegation_tools.py:356 (same graph/registry)
       └─ gather + aggregate     delegation.py:613–671 (parent awaits ALL)
  └─ _record_blob(...)           delegation_tools.py:468 (HarnessRun.delegation)
```

Facts that shape the plan:

- The tool call **blocks the parent's model turn** until every child finishes or
  the total timeout (1 800 s) fires.
- Children run **in the parent's process** (`execute_run`), not as Fabric jobs.
  A process crash loses the fan-out; only the parent's checkpoint survives.
- `spawn/service.py` **already** submits a Fabric `agent` job and honours
  `spec.background` (`await_result=not spec.background`, `spawn/service.py:202`),
  returning `ChildOutcome(status="queued", job_id=...)`. The generic
  `fabric_job_status` / `fabric_job_cancel` tools exist (`fabric/tools.py`).
  But there is no delegation-specific lifecycle, no result contract, no
  completion delivery, and `delegate` and `spawn` remain two different surfaces.
- `DelegationChild` has `goal/context/approach/agent_id/model/temperature/
  tool_subset/workspace_id` and **no `output_schema`** (`delegation.py:79–99`).
  `_coerce_outcome` accepts free text or a mapping and never validates it
  (`delegation.py:685`).
- There is no steer mailbox. `graph.agent_node` builds `model_messages` from
  `state["messages"]` only (`graph.py:774`). A2A has task status/cancel but no
  message injection into a running run (`a2a/service.py:461`).

### 3.2 File safety

```
fs tools        code/fs_tools.py
  └─ FileSystemService            code/fs/service.py
       └─ operations.write_file   operations.py:244
            ├─ FileTransaction    transactions.py:116
            │    ├─ backup(path)  in-memory bytes (transactions.py:134)
            │    └─ commit()      DISCARDS the snapshot (transactions.py:156)
            └─ atomic write
```

- `FileTransaction` protects **one operation**. On success it discards the
  backup; there is no history to return to after the turn.
- Terminal commands (`code/shell.py`, the terminal subsystem) bypass the fs
  transaction entirely.
- `worktree.py` isolates normal code builds, but `direct=True` binds the user's
  real folder (`worktree.py:259–297`) and `release` deliberately never deletes it.
  A direct build therefore has no undo surface.
- `git/safety.py` classifies risk but does not snapshot.
- `project_state.ensure_state_dir` already creates `.black-eclipse/` with a
  self-ignoring `.gitignore` (`code/project_state.py:21`), so a shadow store has
  a safe, invisible home.

---

## 4. Design invariants (non-negotiable)

1. **One durable job owner.** Async children are Fabric `agent` jobs. The
   delegation layer stores the mapping and the contract; it never schedules.
2. **One agent loop.** A child is still `execute_run`. Repair is a bounded
   `execute_run` with tools disabled, not a second loop.
3. **Authority only narrows.** `child_actor` stays the only grant computation.
   A Fabric payload carries data, never authority: the worker recomputes the
   actor and refuses a superset. `operator` is never inherited or serialized.
4. **No mid-tool steering.** The steer drain happens once, at the top of
   `agent_node`, after the previous step checkpoint.
5. **Exactly one terminal outcome per child.** A Fabric retry, a duplicate
   completion or a cancel race must converge on one row and one event.
6. **Raw text is preserved.** A failed schema validation never discards what
   the child actually said.
7. **Checkpoint before mutation, once per turn.** A second write in the same
   turn reuses the turn's snapshot.
8. **Restore is explicit and itself undoable.** A pre-restore snapshot is taken
   before any restore; a partial restore is the default, `all` is opt-in.
9. **Protected paths are never captured or restored.**
10. **Flags default to today's behaviour.** `off` reproduces the current path
    exactly.

---

## 5. W7.1 — Async delegation lifecycle

### 5.1 Surface

New tools, all registered through the existing `code/tools.py` /
`register_spawn_tools` pattern:

| Tool | Kind | Contract |
|---|---|---|
| `delegate_async` | write (job creation) | Submit 1–4 bounded children; return `delegationId` + per-child job handles immediately |
| `delegate_status` | read | Status/progress/attempts per child; never a transcript |
| `delegate_result` | read | Typed `ChildOutcome` list + aggregate + budget; idempotent |
| `delegate_cancel` | write | Cooperative cancel at the child's next boundary |
| `delegate_steer` | write | Append a bounded message for the next step boundary |
| `delegate_wait` | read | Bounded wait (default 0 s = poll); used by the sync wrapper and tests |

`delegate` stays as a **synchronous wrapper**: `delegate_async` + `delegate_wait`
+ aggregate. With `HARNESS_ASYNC_DELEGATION=off` it keeps the current in-process
path byte-for-byte. `spawn` stays for single-child use; its `background` path is
re-used by the implementation, not duplicated.

### 5.2 Execution path

```
delegate_async
  ├─ validate width/depth/budget/narrowing           (existing delegation.py)
  ├─ for each child:
  │    ├─ create HarnessDelegation row (status=queued)
  │    ├─ fabric.submit("agent", payload, await_result=False,
  │    │                 parent_job_id=..., idempotency_key=delegationId:childIndex)
  │    └─ persist jobId + childRunId
  ├─ emit delegation.async.started
  └─ return handles

Fabric agent worker
  ├─ recompute actor + allowlist from the persisted contract (never trust payload)
  ├─ execute_run(childRunId, parentRunId=parent)
  ├─ apply output_schema validation + at most one repair
  ├─ persist result (idempotent on delegationId:childIndex:attempt)
  ├─ emit delegation.child.completed on the PARENT run stream
  └─ mark the delegation row terminal
```

The parent does not poll. At the top of its next `agent_node` it drains a
**completion inbox**: terminal delegations that the parent has not yet consumed
are appended as one bounded `ToolMessage`-style result block (or a
`HumanMessage` marked `<delegated-result>`), so the parent can synthesize. If
the parent already finished, the completion remains a durable card on the turn;
an opt-in `onComplete: "continue"` may start a follow-up run.

### 5.3 Durable row

`python/harness/delegation_store.py` (new, small), table `HarnessDelegation`
created idempotently and registered in `harness/migrations.py`:

```
id                TEXT PRIMARY KEY       -- dlg_...
parentRunId       TEXT NOT NULL
parentJobId       TEXT
childIndex        INTEGER NOT NULL
fabricJobId       TEXT
childRunId        TEXT
status            TEXT NOT NULL          -- queued|running|completed|failed|timed_out|cancelled|refused|unknown
attempt           INTEGER NOT NULL DEFAULT 0
schemaJson        TEXT                   -- bounded, null when none
schemaValid       INTEGER                -- null until terminal
schemaErrors      TEXT                   -- bounded JSON list
rawSummary        TEXT                   -- always preserved
resultJson        TEXT                   -- bounded ChildOutcome / aggregate
tokens            INTEGER NOT NULL DEFAULT 0
reason            TEXT
createdAt/updatedAt
UNIQUE(parentRunId, childIndex, attempt)
```

A second small table `HarnessDelegationSteer`:

```
delegationId TEXT NOT NULL
seq          INTEGER NOT NULL
message      TEXT NOT NULL
createdAt    TEXT NOT NULL
consumedAt   TEXT
PRIMARY KEY(delegationId, seq)
```

No new DB file. Both tables are additive; old rows are untouched.

### 5.4 Completion delivery

- **While the parent runs:** the next `agent_node` consumes completed children
  and injects one bounded block. No extra model turn.
- **After the parent ends:** `GET /delegations?parentRunId=...` returns the
  durable state; the chat hydrates a delegation card. `delegation.*` events are
  also appended to the parent run's durable event log so `GET /runs/{id}/events`
  is complete.
- **Opt-in continuation:** `onComplete: "continue"` starts exactly one follow-up
  run, idempotent on `delegationId:completed`. Default is `"card"` (no
  unsolicited turn).
- **Reconnect:** `delegate_status`/`delegate_result` are pure reads; a reloaded
  UI re-fetches, never replays a completion.

### 5.5 Cancellation and recovery

- `delegate_cancel` calls the existing Fabric cancel; the child's `cancel_event`
  is set; the row becomes `cancelled` only when the run reaches a terminal
  state. A cancel race is resolved by the idempotent terminal write (first
  terminal wins).
- Boot recovery: a row left `running` with a terminal/missing Fabric job is
  reconciled at startup (the existing Fabric recovery + run recovery already do
  the heavy lifting). If the job is gone and no result exists, the row is
  `unknown` — never a fabricated success.
- A parent resume re-reads the inbox from the store; consumed markers prevent a
  duplicate injection.

---

## 6. W7.2 — `output_schema` and one bounded repair

### 6.1 Contract

Add to `DelegationChild` and `SpawnSpec`:

```python
output_schema: Optional[dict[str, Any]] = None   # bounded JSON Schema, <= 16 KB
schema_repair: bool = True                       # one repair turn at most
```

Rules:

- The schema is **data**, bounded to 16 KB, depth ≤ 12, and may not contain a
  remote `$ref` (`http://`, `https://`, `file:`). A resolver that refuses
  unknown refs is used; no network.
- The child prompt appends a compact instruction: "Return ONLY JSON that
  satisfies this schema" + the schema. The schema is also put in the run's
  `context` so it survives a resume (bounded).
- Validation runs with `jsonschema` (already a declared dependency) using
  `Draft202012Validator`.
- On failure: **one** repair turn. The repair is a bounded `execute_run` with
  tools disabled, `maxSteps=1`, the original raw output and the validation
  errors in `input.context`. It uses the same provider/credential and the same
  narrowed actor. It is a new run linked to the original (`parentRunId`), not a
  second loop.
- The result always contains:
  - `summary` — the validated JSON text when valid, else the raw text;
  - `rawSummary` — always the child's original text;
  - `schemaValid` — true/false;
  - `schemaErrors` — bounded list (≤ 10, each ≤ 500 chars);
  - `repairAttempted`, `repairRunId`.
- A repair that fails marks `schemaValid=false`. It never invents fields or
  coerces types silently.

### 6.2 Why a separate repair run

Putting the repair inside the child's loop would require a graph post-answer
hook and a second "answer" path. A one-step, tool-less run reuses
`execute_run` unchanged, is trivially bounded, and is easy to test. The cost is
one extra model call only when validation fails.

---

## 7. W7.3 — Steering

### 7.1 Semantics

- `delegate_steer(delegationId|jobId, message, mode="append")` appends to
  `HarnessDelegationSteer`. It never runs a tool and never mutates the child's
  state directly.
- At the **top** of the child's `agent_node` (after the previous step
  checkpoint, before `model_messages` is built), drain pending rows in `seq`
  order, coalesce consecutive messages into one block (≤ 4 000 chars total),
  and append a `HumanMessage` wrapped as `<operator_steer>…</operator_steer>`.
- Mark drained rows `consumedAt` in the **same transaction** as the step
  checkpoint, so a crash either re-delivers once or does not deliver at all —
  never a lost-and-forgotten message and never an infinite redelivery.
- A steer arriving while the child is inside `tools_node` waits. It is not
  injected mid-batch.
- Caps: ≤ 4 pending messages per child, ≤ 4 KB each, ≤ 8 KB total; excess is
  refused with `DELEGATION_STEER_LIMIT`, not silently dropped.
- Only an operator or the parent run may steer. A child may not steer a sibling
  or its parent (no escalation).

### 7.2 UI/API

- `POST /delegations/{id}/steer` (operator or parent-run token), plus the
  `delegate_steer` tool.
- The delegation card gets a one-line "Add guidance" input while a child is
  running; disabled once terminal, with an honest "already finished" state.
- `delegation.steered` event records the delegation id, seq and character count
  — never the message text in the event log (privacy); the text lives in the
  steer table and is visible to the run owner.

---

## 8. W7.4 — Per-child worktree isolation

- `DelegationChild.isolated: bool = False`.
- When `isolated=True`, the Fabric worker calls
  `worktree.allocate(root=<resolved project root>)` before the child starts and
  binds the child's tool context to that worktree. The child cannot name a
  different root; the root is resolved by the runtime, not the request body.
- A writing child **must** be isolated. If allocation fails (no git and the
  snapshot fallback is too large, or no isolation primitive), the child is
  `refused` with `WORKTREE_UNAVAILABLE`. It never falls back to writing the
  user's checkout.
- On completion the parent receives a **diff handle**:
  `{workspaceId, strategy, base, digest, filesChanged, additions, deletions,
  unifiedPreview<=64KB}`. The full diff stays behind
  `worktree.diff(workspaceId)`.
- No auto-merge. Landing uses the existing preview → single-use approval →
  apply path (`code/promotion.py`). A child's worktree is released by the
  existing TTL sweep or by `worktree.release` after promotion.
- A non-isolated child gets **no write tools** (the narrowed allowlist removes
  `WRITE_TOOLS`); it is a read-only researcher.

---

## 9. W7.5 — Shadow-git file checkpoints and `/rollback`

### 9.1 Store

New `python/harness/code/checkpoints.py`.

- One bare git repository per project:
  `<project>/.black-eclipse/checkpoints/store` (created with `git init --bare`).
  `.black-eclipse/` is already self-ignored (`project_state.ensure_state_dir`).
- Snapshots are commits under
  `refs/eclipse/<project-hash>/<UTC-stamp>-<checkpointId>`. The commit message
  carries `runId`, `turnKey`, `reason` and the checkpoint id; refs are the
  source of truth, so no new database is introduced.
- A temporary index (`GIT_INDEX_FILE` under
  `.black-eclipse/checkpoints/index/`) means the snapshot **never reads or
  writes the user's index**.
- Excludes come from a store-local excludes file, not the project's
  `.gitignore`: `.git`, `.black-eclipse`, `node_modules`, `.next*`, `dist`/
  `build`/`target`/`out`, `*.db`/`*.sqlite*`, `.env*`, secret files, artifacts,
  files > 10 MB, and symlinks that resolve outside the project.
- If git is unavailable: `CHECKPOINT_UNAVAILABLE` with a remedy. The feature
  never fakes a store.
- Bounds: `HARNESS_FILE_CHECKPOINT_MAX_MB` (default 500) and
  `HARNESS_FILE_CHECKPOINT_RETENTION` (default 50 per project / 14 days).
  Prune deletes old refs and runs a bounded `git gc --prune=now`; a full store
  refuses new snapshots with `CHECKPOINT_STORE_FULL` rather than growing forever.

### 9.2 Snapshot rule

- At most **one snapshot per project per turn**. The first mutating tool in a
  turn takes it; every later mutation in the same turn reuses it.
- Keyed by `(projectRoot, runId, turnKey)`; `turnKey` is the run's step/plan
  step, so a resume does not re-snapshot the same turn.
- Reasons: `before-write`, `before-patch`, `before-terminal`, `before-promote`,
  `pre-restore`.
- Snapshot is **best-effort by mode**:
  - `HARNESS_FILE_CHECKPOINTS=off` — no snapshot (today).
  - `warn` — attempt; on failure record `checkpoint.failed` and continue.
  - `enforce` — fail the mutation with `CHECKPOINT_FAILED` and a plain remedy.
  - `on` is accepted as an alias for `enforce` (backward-compatible with the
    existing bool definition).

### 9.3 Hooks (the only three)

1. **`FileSystemService`** — every mutating method (`write_file`, `create_file`,
   `delete_file`, `move_file`, `copy_file`, `rename_file`, `create_directory`,
   `delete_directory`, `patch_file`, `replace_text`, `insert_text`,
   `delete_text`, `apply_diff`, `multi_file_patch`) calls
   `checkpoints.before_mutation(...)` once before the operation. The facade is
   the one place all fs tools flow through (`code/fs/service.py`).
2. **Terminal/shell** — `code/shell.py` (and terminal tools) snapshot before a
   command that `code/policy.decide_command` classifies as `write`/`destructive`
   or that `git/safety.assess_risk` rates `destructive`+. Read-only commands
   never snapshot.
3. **Promotion** — `code/promotion.apply_promotion` snapshots before applying a
   landed change, so a promotion is undoable even after the worktree is
   released.

Skipped roots: anything under `.black-eclipse/code-workspaces` (scratch), and
any path outside the project root.

### 9.4 Tools and routes

| Surface | Contract |
|---|---|
| `checkpoint_list` | read; newest first; id, time, reason, runId, files, bytes |
| `checkpoint_diff` | read; bounded unified diff vs the current tree, or between two ids |
| `checkpoint_restore` | effectful; default preview + single-use approval; `confirm` applies |
| `GET /code/checkpoints` | operator-gated list |
| `GET /code/checkpoints/{id}/diff` | bounded diff |
| `POST /code/checkpoints/{id}/restore` | operator-gated; pre-restore snapshot; single-use digest |
| `POST /code/checkpoints/{id}/restore/preview` | what would change |

Restore rules:

- Default restores the named path(s) only. `all=true` is explicit.
- Always take a `pre-restore` snapshot first; the restore itself is undoable.
- Never restore a protected/excluded path even if the commit contains one
  (defence in depth: the snapshot should not contain it, but the restore also
  refuses).
- Restore uses `git restore --source=<commit> --worktree -- <paths>` through a
  fixed argv (`shell=False`), with `core.longpaths=true` on Windows, never a
  model-supplied argument.
- Approval reuses `mcp/approvals.py` with kind `file_restore`; the digest binds
  `checkpointId + sorted(paths) + preRestoreCommit`. An approval for one set of
  paths cannot restore another.

### 9.5 `/rollback`

- A **routed, operator-gated command** — no LLM turn
  (`src/lib/harness/commands/command-registry.ts` +
  `command-handlers.ts`).
- `/rollback` → list the latest checkpoint with a diff summary.
- `/rollback <id>` → preview restoring the files that checkpoint changed.
- `/rollback <id> --all` → full restore (explicit).
- `/rollback --last` → the most recent checkpoint.
- The result card shows `filesChanged`, additions/deletions, protected paths
  skipped, and a **Confirm restore** button bound to the single-use digest.
- `/checkpoints` → list.

### 9.6 UI

- A `checkpoint-chip` appears in the chat activity row and the Code task screen
  after the first snapshot of a turn: "Snapshot saved · Undo".
- A `checkpoint-panel` (list + diff + restore) on the Code screen, using the
  frosted-glass system (`.glass-card`), not raw blur.
- A restore dialog lists exactly what will change and what is skipped, with a
  clear "Restore" / "Cancel"; a restore result is a normal card, never a toast
  that disappears.
- The panel is read-only for non-operators; the restore route and tool both
  require operator authorization.

---

## 10. Flags

Existing flags stay the kill switches; new flags are declared in
`python/harness/config/flags.py` (std-only, no runtime import).

| Flag | Default | Values | Owner | Kill switch |
|---|---|---|---|---|
| `HARNESS_ASYNC_DELEGATION` | `off` | `off|on` | W7 | `off` = in-process synchronous `delegate` |
| `HARNESS_FILE_CHECKPOINTS` | `off` | `off|warn|enforce` (`on`→`enforce`) | W7 | `off` = no snapshots |
| `HARNESS_FILE_CHECKPOINT_MAX_MB` | `500` | 50–5 000 | W7 | lower/raise the store cap |
| `HARNESS_FILE_CHECKPOINT_RETENTION` | `50` | 1–500 | W7 | prune more/less |
| `HARNESS_DELEGATION_SCHEMA_REPAIR` | `on` | `off|on` | W7 | `off` = validate but never repair |
| `HARNESS_DELEGATION_STEER_MAX` | `4` | 0–8 | W7 | `0` disables steering |
| `HARNESS_DELEGATION_COMPLETION` | `card` | `card|continue|off` | W7 | `off` = no completion surface |

`HARNESS_FILE_CHECKPOINTS` changing from bool to enum is a deliberate flag
semantic change: document it, add an ADR-H entry (the next free id), and keep
`on` as an alias so an existing deployment does not silently change meaning.

---

## 11. Events and observability

| Event | Payload | Why |
|---|---|---|
| `delegation.async.started` | delegationId, children, strategy | one row per fan-out |
| `delegation.child.queued` | delegationId, childIndex, jobId | parent can show "running" |
| `delegation.child.completed` | delegationId, childIndex, status, tokens | durable completion |
| `delegation.steered` | delegationId, seq, chars | no message text |
| `delegation.repair.attempted` | delegationId, childIndex | one repair, measurable |
| `delegation.repair.succeeded/failed` | delegationId, childIndex, errorCount | quality signal |
| `delegation.worktree.allocated` | delegationId, childIndex, workspaceId | isolation proof |
| `checkpoint.created` | checkpointId, reason, runId, files, bytes, durationMs | coverage + cost |
| `checkpoint.failed` | reason, code | any failure is visible |
| `checkpoint.restored` | checkpointId, paths, preRestoreId | undo is auditable |
| `checkpoint.pruned` | removed, bytesFreed | retention is real |

Metrics for W8: async completion latency (submit → terminal), repair rate,
steer delivery latency (append → consumed), checkpoint write p50/p95 and
failure rate, store size, restore count.

---

## 12. Tests

### 12.1 New test files

| File | Covers |
|---|---|
| `test_delegate_async.py` | queued handle; parent continues; status/result idempotent; cancel at boundary; terminal-once; recovery of a `running` row |
| `test_output_schema_repair.py` | valid pass-through; one repair; repair failure keeps raw; remote `$ref` refused; oversized schema refused; no silent coercion |
| `test_delegate_steer.py` | delivered at next step, not mid-tool; coalescing; caps; resume no-duplicate; only operator/parent may steer |
| `test_spawn_worktree.py` | isolated child writes only its worktree; diff handle; no auto-merge; allocation failure refuses; non-isolated child has no write tools |
| `test_file_checkpoints.py` | snapshot before write; one-per-turn dedupe; protected paths untouched; list/diff; single-file vs all restore; pre-restore snapshot; restore refusal for protected; retention; size cap; git absent; concurrent snapshot index isolation |
| `test_delegation_completion.py` | parent injects completed child at next step; parent ended → card/route read; `onComplete=continue` exactly once |

### 12.2 Extended tests

- `test_delegation_tool.py` — with the flag off, `delegate` output and events are
  unchanged.
- `test_delegation_narrowing.py` — a Fabric payload cannot widen grants; a
  serialized actor never contains `operator`.
- `test_code_fs_*`, `test_git_safety.py`, `test_promotion_filter.py` — the
  checkpoint hook does not change results or error codes.
- `test_fabric_*` — duplicate completion/retry converges on one row.
- `test_a2a_delegation.py` — A2A and W7 delegation do not share a store or
  double-deliver.

### 12.3 Fault matrix

| Window | Injection | Expected |
|---|---|---|
| Parent returns after `delegate_async` | kill parent process | Child keeps running; result persisted; reload shows it |
| Child after an effectful tool, before result | kill worker | Fabric idempotency; row `unknown` or terminal, never duplicate effect |
| Duplicate completion (retry) | worker replays | One terminal row + one event |
| Steer while child in `tools_node` | append during batch | Delivered at next step, not mid-tool |
| Steer then crash before checkpoint | kill before step checkpoint | Delivered once on resume or not at all; never twice |
| Schema repair crashes | kill repair run | Original raw preserved; `schemaValid=false` |
| Checkpoint snapshot fails (`enforce`) | fake git failure | Mutation refused with a plain remedy |
| Checkpoint snapshot fails (`warn`) | fake git failure | Mutation proceeds; `checkpoint.failed` recorded |
| Restore race (two operators) | concurrent restore | Single-use approval; second gets a conflict |
| Restore a protected path | crafted id/path | Refused, nothing written |

---

## 13. Slices (sequenced)

| Slice | Change | Acceptance |
|---|---|---|
| **W7.0** | Flags, `HarnessDelegation`/steer tables, `checkpoints.py` scaffolding, shadow snapshot only (`warn`), no user surface | Migration applies once; snapshot/restore unit tests; flag kill-switch; today's behaviour with `off` |
| **W7.1** | `delegate_async/status/result/cancel/wait` over Fabric; `delegate` as sync wrapper | Parent continues; result once; cancel at boundary; flag off is unchanged |
| **W7.2** | `output_schema` + one repair | Valid JSON passes; invalid gets exactly one repair; raw preserved |
| **W7.3** | Steering mailbox + drain at `agent_node` + route/UI | Delivered at the next step; no mid-tool injection; no duplicate on resume |
| **W7.4** | Per-child worktree + diff handle | Child writes isolated; diff returned; no auto-merge; refusal on failure |
| **W7.5** | Checkpoint hooks (fs/terminal/promotion), tools/routes, `/rollback`, UI, `warn→enforce` | Bad edit listed/diffed/restored; protected paths untouched; pre-restore snapshot |
| **W7.6** | Default-on after a green canary (delegation async + checkpoints `enforce`) | Two green weeks; eval parity; no increase in orphan/effect-unknown |

---

## 14. Rollout and rollback

1. **W7.0 lands inert.** `off` is byte-identical to today; `warn` snapshots are
   measurable but never block a write.
2. **W7.1 ships with `HARNESS_ASYNC_DELEGATION=off`.** Run it in `on` on the
   offline eval + a small internal canary; compare terminal rate, duplicate
   completion, orphan count and parent latency. Keep `delegate` synchronous.
3. **Steering and schema repair are per-call**; they do not change any run that
   does not ask for them.
4. **File checkpoints move `off → warn → enforce`** only after checkpoint write
   p95 and store growth are measured on the real repo. A project that is too
   large gets `warn` (honest "no snapshot" chip), not a broken build.
5. **Rollback:** set the flag `off`, restart. For async, `delegate` still works;
   any queued Fabric jobs drain or are cancelled through the existing Fabric
   admin surface. For file checkpoints, `off` stops new snapshots; existing refs
   remain restorable with the tool/route (read-only path), so turning the flag
   off does not strand history.
6. **Do not delete the checkpoint store on rollback.** It is the undo history.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Snapshot latency on a large repo | One per turn; excludes; `warn` first; measure p95; skip scratch/direct-untracked roots |
| Disk growth | `MAX_MB` + retention + prune; `CHECKPOINT_STORE_FULL` refuses rather than fills the disk |
| Snapshot races / index corruption | Per-snapshot `GIT_INDEX_FILE`; single-flight per project; no shared index |
| Windows path/case/long-path issues | `core.longpaths=true`; realpath/case-normalized project hash; tests on Windows |
| Child escapes narrowing | Recompute actor in the worker; never trust payload; test a forged payload |
| Orphan/duplicate children | Fabric lease + idempotency key `delegationId:childIndex:attempt`; one terminal row |
| Repair becomes a hidden second model turn | Exactly one, tools off, one step, same provider, event + token accounting |
| Steering drifts into prompt injection | Operator/parent-only; `<operator_steer>` wrapper; bounded; never from tool output |
| Restore destroys later hand edits | Default partial restore; pre-restore snapshot; explicit `all`; diff preview |
| Restore approval replay | Digest binds checkpoint + paths + pre-restore commit; single-use |
| A second delegation surface confuses the model | `delegate` documented as the sync wrapper; `spawn` documented for single-child; one compatibility table in the tool descriptions |

---

## 16. File map

**New**

- `python/harness/delegation_store.py` — `HarnessDelegation` + steer rows.
- `python/harness/delegation_lifecycle.py` — async submit/status/result/cancel/wait,
  completion inbox, Fabric mapping.
- `python/harness/delegation_repair.py` — schema validation + one repair run.
- `python/harness/code/checkpoints.py` — shadow store, snapshot/list/diff/restore/prune.
- `python/harness/routers/delegations.py` — `/delegations/*`.
- `python/harness/routers/checkpoints.py` (or extend `routers/code.py`) — `/code/checkpoints/*`.
- `src/app/api/delegations/[[...path]]/route.ts`,
  `src/app/api/code/checkpoints/**/route.ts`.
- `src/lib/harness/clients/delegations-{client,browser}.ts`;
  checkpoint helpers in `src/lib/harness/clients/code-{client,browser}.ts`.
- `src/components/chat/delegation-card.tsx` (extend existing delegation view);
  `src/components/screens/code/checkpoint-panel.tsx`.
- `src/lib/agent/delegation-reducer.ts` additions (`steer`, `schema`, `queued`).
- Tests in §12.

**Changed**

- `python/harness/delegation.py` — `output_schema`, `schema_repair`, `isolated`
  on `DelegationChild`; result fields.
- `python/harness/delegation_tools.py` — new tool handlers; `delegate` wrapper.
- `python/harness/spawn/model.py` + `spawn/service.py` — schema, background reuse,
  bounded result.
- `python/harness/graph.py` — drain steers at `agent_node`; inject completed
  delegations; no change when flags off.
- `python/harness/code/fs/service.py` — checkpoint hook on mutations.
- `python/harness/code/shell.py` / terminal tools — checkpoint before
  write/destructive commands.
- `python/harness/code/promotion.py` — checkpoint before apply.
- `python/harness/config/flags.py` — new/updated flags.
- `python/harness/migrations.py` — register the delegation tables.
- `python/harness/main.py` — include the new routers.
- `src/lib/harness/commands/command-registry.ts` + `command-handlers.ts` —
  `/rollback`, `/checkpoints`.
- `src/lib/agent/events.ts` — new event kinds.
- `src/lib/i18n/dictionaries/` — `checkpoint.*`, `delegation.steer.*` (respect
  the plain-language gate and the size ratchet).
- `docs/harness/roadmap/hermes-inspired-improvement-plan.md` — link this plan.
- `docs/harness/roadmap/w0-flags-and-review.md` — flag rows.
- `docs/NAVIGATION.md` — pointer row.
- `docs/harness/agent-to-agent.md` — clarify A2A delegation vs W7 delegation.
- `docs/harness/code-filesystem.md` — the checkpoint hook and the restore
  contract.

---

## 17. Definition of done

- Code + flag + tests + event/metric + rollback note + `CHANGELOG.md` entry for
  every slice.
- `npm run test` and `npx tsc --noEmit` pass from `Black-Eclipse-site/`.
- With every new flag `off`, the runtime is byte-identical to today (verified by
  the existing delegation/fs/fabric tests).
- A parent can continue while 3 children run; each result arrives once.
- A schema miss gets exactly one repair; the raw text is preserved.
- A steer is delivered at the next step, never mid-tool, and never twice after
  a resume.
- A writing child cannot reach the user's checkout or another child's worktree.
- A bad edit can be listed, diffed and restored; the restore is itself undoable;
  protected paths are untouched.
- No second scheduler, loop, model client, approval store or event bus is added.

---

## 18. Open questions (resolve before W7.1)

1. **One job type or reuse `agent`?** Recommendation: reuse the Fabric `agent`
   job (it already owns lease/retry/cancel) and carry the delegation contract in
   the payload, with a `HarnessDelegation` mapping. A new `delegation` job type
   would be a second lifecycle to maintain.
2. **Completion turns.** Default `card` avoids unsolicited model turns; is
   `onComplete: "continue"` wanted for long autonomous work, and who pays for
   it? Recommendation: ship `card` only; add `continue` after a budget study.
3. **Whole-tree vs touched-paths snapshot.** Recommendation: whole tree once per
   turn (simple, exact), with excludes; revisit only if p95 is unacceptable.
4. **Store location.** Per-project `.black-eclipse/checkpoints` (travels with
   the repo, self-ignored) vs a global app-data store keyed by project hash.
   Recommendation: per-project; the project owns its undo history.
5. **`HARNESS_FILE_CHECKPOINTS` type.** Changing bool → enum needs an ADR and a
   canary; confirm `on` as the `enforce` alias is acceptable.
6. **Sync `delegate` deprecation.** Keep it indefinitely as the ergonomic,
   predictable wrapper, or deprecate in favour of `delegate_async` +
   `delegate_wait`? Recommendation: keep it; it is the safe default.

---

## 19. Implementation status (2026-11-12)

Landed behind the W7 flags (defaults preserve today's behaviour):

- **Async delegation** — `delegation_store.py` (`HarnessDelegation` + steer
  mailbox), `delegation_lifecycle.py` (Fabric `delegation` job worker,
  status/result/cancel/wait, completion inbox), `delegation_async_tools.py`
  (`delegate_async/status/result/cancel/steer/wait`), Fabric policy + worker
  registration, `/delegations` routes and front-door proxy.
- **Schema repair** — `delegation_repair.py` (bounded schema checks, no remote
  `$ref`, JSON extraction, one repair prompt); both the async worker and the
  synchronous `delegate` path run exactly one tool-less repair and preserve the
  raw answer.
- **Steering** — durable mailbox drained at the top of `agent_node`; consumed
  at the next checkpoint so a resume delivers at most once.
- **Per-child worktree** — `isolated` allocates `worktree.allocate()`, mints a
  one-run opaque token (`workspaceScratchToken`) the runtime consumes to bind
  the child to that worktree, returns a diff handle, and never merges; a
  non-isolated child loses `WRITE_TOOLS`. The synchronous `delegate` path uses
  the same token seam.
- **File checkpoints** — `code/checkpoints.py` (shadow-git snapshots, list,
  diff, restore, prune), hooks in `FileSystemService`, `shell_run` and
  `apply_promotion`, `checkpoint_*` tools, `/code/checkpoints*` routes,
  `/rollback` command and the Code-screen checkpoint panel.
- **Flags** — `HARNESS_FILE_CHECKPOINTS` is now `off|warn|enforce`;
  `HARNESS_FILE_CHECKPOINT_MAX_MB`, `HARNESS_FILE_CHECKPOINT_RETENTION`,
  `HARNESS_ASYNC_DELEGATION`, `HARNESS_DELEGATION_SCHEMA_REPAIR`,
  `HARNESS_DELEGATION_STEER_MAX`, `HARNESS_DELEGATION_COMPLETION` are in
  `config/flags.py`.
- **Tests** — `python/tests/test_file_checkpoints.py`,
  `test_delegation_lifecycle.py`; existing delegation/fs/fabric suites still
  pass. `npx tsc --noEmit` passes.

Remaining rollout work is operational, not code: run `warn` on a real project,
measure snapshot p95/store growth, then move async delegation and checkpoints to
default-on after the canary.
