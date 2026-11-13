---
title: W6 — Run-Kernel Integrity and Safety (Detailed Plan)
status: Proposed
last-verified: 2026-11-12
owner: Agent runtime
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
scope: implementation landed 2026-11-12
---

# W6 — Run-Kernel Integrity and Safety

> ## Implementation status (2026-11-12)
>
> **Landed:** W6.1–W6.5 and W6.6a/b are implemented, with W6.6c's enforce path
> and startup warning (the `shadow` default is deliberately unchanged).
>
> - `run_lease.fenced_progress` + `LeaseLost`; `RunScope.runtime_id`;
>   `execute_run(runtime_id=)`; every `graph.py`/`tool_turn.py`/`run_flags.py`
>   mutation is fenced. A lost lease returns `RUN_LEASE_LOST` without a terminal
>   write.
> - `RunLineage.save_boundary` (one transaction, one retry) and
>   `CheckpointWriteFailed`; `execute_run` maps it to
>   `CHECKPOINT_WRITE_FAILED`. The legacy two-commit path remains behind
>   `HARNESS_CHECKPOINT_ATOMIC=off`.
> - `ToolExecutionIdempotency.state` (`started|done|unknown`), pre-dispatch
>   `mark_tool_started`, `mark_tool_done`, `mark_tool_unknown`; effect
>   `finish`/`mark_unknown` is guaranteed in the dispatch path. A read-only
>   `started` is replayed; an effectful `started` is refused.
> - `event_sequence.EventSequence` allocates `MAX(seq)+1` inside
>   `BEGIN IMMEDIATE`, creates the unique `(runId, seq)` index, and repairs
>   legacy duplicate seqs. `RunEmitter` uses it under `HARNESS_EVENT_SEQ`;
>   transient deltas use a separate id/negative-seq space.
> - `find_stalled(live_run_ids=)` and the sweep's lease query prevent a live
>   run from being failed by another runtime.
> - `security/hardline.py` denies root wipes, fork bombs, raw device writes,
>   pipe-to-root, recursive permission wipes, root shells and OS-directory
>   deletes before grants/policy/approval. `code/shell.py` now runs `shell_run`
>   through `code/sandbox.run` and `shell_spawn` through
>   `terminal.spawn.spawn_process` (tree kill, scrubbed env, named refusal).
> - `SECURITY_UNAVAILABLE` refusal under `HARNESS_EFFECT_TOKENS=enforce`;
>   `shadow` logs a one-time production warning.
>
> **Tests:** `test_run_lease.py`, `test_run_lineage.py`,
> `test_events_sequence.py`, `test_run_watchdog.py`, `test_run_kernel_faults.py`,
> `test_hardline.py`, `test_shell_sandbox_parity.py`, `test_c6_effect_tokens.py`
> plus the existing graph/tool/security/resume suites.
>
> **Deliberate gaps (do not report these as landed):**
> - The intent-marker fallback for a long boundary transaction is not built; the
>   single transaction is the shipped path.
> - `HARNESS_EFFECT_TOKENS` still defaults to `shadow`. Flipping the production
>   default requires the ADR + canary described in §9.
> - The hardline pattern list is finite and code-reviewed; it is not a sandbox
>   and does not attempt to parse arbitrary shell grammar.

W6 makes the run kernel honest under concurrency, crashes and hostile input.
It is the P0 wall between “the agent usually finishes” and “the agent cannot
duplicate an effect, lose a checkpoint, overwrite another worker's run, or be
talked into a destructive command”.

The gap is not architectural: leases, checkpoints, an effect ledger and a
security floor already exist. The gap is that several of them are **best-effort
observers** instead of **enforced participants**:

1. **Progress writes are unfenced.** `fenced_update_run` exists and terminal
   writes use it, but the model-step counters, token totals and tool counters
   still call `store.update_run`. A worker that lost its lease can still write.
2. **A checkpoint is two commits.** `save_messages` and `save_checkpoint` each
   commit separately; a crash between them leaves a message cursor with no
   boundary (or a boundary with no messages). Failures are swallowed.
3. **Tool idempotency is post-hoc.** `mark_tool_executed` is written after the
   tool returns, so a crash during the call leaves no row. Only the effect
   ledger knows, and only for tools it classifies as effectful.
4. **Event sequences are per emitter.** `RunEmitter._seq` starts at zero in
   every instance and `HarnessEvent` has no unique `(runId, seq)` constraint.
   Two emitters for one run (a resume beside a live path, a watchdog beside the
   owner) can emit colliding ids; `INSERT` then fails and the event is dropped.
5. **The watchdog ignores leases.** `find_stalled` fails a silent run even when
   another runtime holds a live lease and is still working.
6. **The safety floor is shape-based and the shell bypasses the sandbox.**
   `security/floor.py` protects paths and action classes, but has no command
   hardline; `code/shell.py` calls `subprocess` directly, without the Job
   Object / process-group tree kill that `code/sandbox.py` and
   `terminal/spawn.py` already provide; and effect tokens still default to
   `shadow`, so a replayed or widened call is logged but not blocked.

**Duration:** 3–4 engineer-weeks.
**Flags:** `HARNESS_FENCED_PROGRESS` (`on`), `HARNESS_CHECKPOINT_ATOMIC`
(`on`), `HARNESS_EVENT_SEQ` (`on`), `HARNESS_EFFECT_TOKENS` (`shadow`, target
`enforce`). All four are already declared in `config/flags.py`; W6 gives them
their first consumers.
**Dependencies:** W0 flag discipline (landed); the existing `run_lease`,
`run_lineage`, `run_effects`, `events`, `run_watchdog`, `security` and
`code/sandbox` modules.
**Rollback:** every slice is flag-off reversible; no slice deletes a run, a
checkpoint, an event or an audit row. The schema changes are additive.

---

## 1. Goals

1. **One owner writes.** Every run mutation proves the writer still owns the
   lease epoch. A stale worker stops with `RUN_LEASE_LOST`; it never writes a
   counter or a terminal status over the new owner.
2. **A boundary is atomic.** Conversation cursor and checkpoint commit in one
   SQLite transaction. A crash lands either before both or after both; never in
   between. A failed boundary stops the run honestly instead of continuing
   without durable state.
3. **At-most-once dispatch is pre-recorded.** An idempotency row is written
   **before** the tool runs. `done` is reusable, `started`/`unknown` is not
   re-executed for an effectful tool, and the operator gets a reconciliation
   instruction.
4. **Event ids cannot collide.** The durable sequence is allocated inside
   `BEGIN IMMEDIATE` from the store, unique per run, and retried once on a
   collision. Transient deltas use a separate id space.
5. **The watchdog respects ownership.** A run with a live lease is never failed
   by another runtime's sweep.
6. **Hostile commands hit a hardline.** Root wipes, fork bombs, raw
   block-device writes, pipe-to-shell-as-root and recursive permission wipes
   are denied before grants, YOLO, policy or approval are consulted.
7. **The shell is a sandboxed citizen.** `shell_run` and `shell_spawn` use the
   same isolation primitives as terminal/analysis execution, with tree kill and
   the scrubbed environment.
8. **Zero-config still works.** No SQLite, no lease table and no security
   gateway are all handled as today: fail-open for observability, fail-closed
   only where an effect would otherwise run unguarded.

## 2. Non-goals

- No second event bus, run store, lease manager, scheduler or approval path.
- No exactly-once claim. W6 is **at-most-once for effects**, with `unknown` as
  a first-class outcome.
- No rewrite of `graph.py`. Progress writes route through a small helper; tool
  idempotency extends the existing `RunLineage`; the event change extends the
  existing `RunEmitter`.
- No default flip to `HARNESS_EFFECT_TOKENS=enforce` without a separate ADR and
  a canary (see §12, D1). W6 ships the enforcement path, a startup warning and
  the rollout plan; the default stays `shadow` until the canary is green.
- No network sandbox for the local shell. The local isolation primitive still
  refuses `network=True`; a shell is **not** a network boundary and the docs
  must keep saying so.
- No retroactive rewrite of historical checkpoints or events beyond the
  one-time duplicate-seq repair needed to create the unique index.

---

## 3. Current state (grounded)

| Area | Today | Evidence |
|---|---|---|
| Fenced writes | `fenced_update_run` exists and terminal paths use it; `RunScope` has no runtime id | `run_lease.py:253-292`, `run_lease.py:323-357` |
| Unfenced progress | Model counters and token totals use `store.update_run`; tool counters too; `surface`, `codeVerification`, `memory` blobs are unfenced | `graph.py:883-889`, `:1196`, `:1621-1626`, `:2085`, `:2247` |
| Unfenced running write | Both run start paths use `store.update_run(status="running")` | `graph.py:1476`, `:1503` |
| Checkpoint write | `save_messages` commits, `save_checkpoint` computes `MAX(seq)+1` and commits; `_write_checkpoint` swallows every failure | `run_lineage.py:247-277`, `:211-232`, `graph.py:695-708` |
| Tool idempotency | `mark_tool_executed` writes **after** dispatch; `was_tool_executed` has one terminal shape | `run_lineage.py:301-343`, `graph.py:1036-1060`, `:1133-1135` |
| Effect ledger | `begin` before dispatch, `finish` after success, but `finish` is not in a `finally`; a crash still leaves `started` (correct outcome) | `run_effects.py:66-90`, `graph.py:1089-1120` |
| Event sequence | Per-instance `_seq`; `HarnessEvent` has a **non-unique** `(runId, seq)` index; ids are `evt_<run>_<seq>` | `events.py:71-164`, `persistence.py:715-729`; schema has `idx_harness_event_run`, not `UNIQUE` |
| Watchdog | `find_stalled` sees only event silence; recovery (`fail_orphaned_runs`) already skips a live lease, the watchdog does not | `run_watchdog.py:75-90`, `:130-178`; `run_recovery.py:57-65`, `:95-96` |
| Hardline | No `security/hardline.py`; `terminal._DENY_ARGS` is five substrings and shell classification is separate | `security/` has no hardline module; `code/terminal.py:79`, `:84`, `:107-130` |
| Shell isolation | `shell.run`/`spawn` call `subprocess` directly; scrubbed env only; no Job Object / process-group tree kill | `code/shell.py:72-112`, `:143-167` |
| Effect tokens | Default is `shadow`; `enforce` is opt-in; the shadow verdict is recorded but not blocking | `security/effect_tokens.py:58-64`; `test_c6_effect_tokens.py:70-75` |
| Security unavailable | Gateway construction is best-effort; `_wrap_with_security` returns `inner` when no gateway; an effectful tool with no inner authorizer can fall through | `service.py:515-526`, `security/bootstrap.py:26-62`, `security/integration.py:143-148`, `code/authorizers.py:332-352` |
| W6 flags | Declared with owner W6, no consumer | `config/flags.py:212-229` |

The current behaviour is therefore **usually correct** and **not guaranteed**
under exactly the conditions W6 exists for: a crash, a duplicate submission, a
lease steal, two emitters, or a hostile command.

---

## 4. Target path

```
service.run / run_background
  -> RunLeaseGuard (claim epoch, heartbeat)
  -> execute_run(runtime_id=<lease runtime>)
       -> emitter = RunEmitter(store)                 # sequence from store
       -> fenced_progress(...)                        # every run mutation
       -> graph
            agent_node
              -> fenced_progress(model/token counters)
              -> _write_checkpoint("agent_step")
                   -> RunLineage.save_boundary()      # messages + checkpoint, ONE txn
            tools_node
              -> lineage.mark_tool_started()          # BEFORE dispatch
              -> effects.begin()                      # BEFORE dispatch
              -> registry.execute() -> run_tool_with_recovery()
              -> effects.finish() / mark_unknown()    # finally
              -> lineage.mark_tool_done()
              -> fenced_progress(tool counters)
              -> _write_checkpoint("tool_results")
       -> terminal status (already fenced)
  -> watchdog sweep: skip live leases
```

Security target:

```
tool dispatch
  -> SecurityGateway authorizer (if installed)
       -> hardline.evaluate(command)      # terminal, DENY, not grant-overridable
       -> floor / policy / risk / approval
       -> effect token minted for THIS call
  -> ToolRegistry.execute
       -> effect token verified (enforce => fail closed)
  -> shell_run / shell_spawn
       -> code.sandbox.run / terminal.spawn.spawn_process   # tree kill, scrubbed env
```

---

## 5. Contracts

### 5.1 Fenced progress (`run_kernel/progress`)

Keep `fenced_update_run` as the single SQL seam, and add a thin helper used by
the graph:

```python
# python/harness/run_lease.py
class LeaseLost(RuntimeError):
    code = "RUN_LEASE_LOST"

def fenced_progress(store, run_id, *, runtime_id=None, **fields) -> None:
    """Write progress iff this runtime still owns the lease epoch.

    Raises LeaseLost when the write is fenced. No caller may ignore it.
    """
```

Rules:

- `HARNESS_FENCED_PROGRESS=off` → call `store.update_run` (today's behaviour).
- `fenced_update_run` returning `False` means the row changed zero times: the
  lease was stolen, expired, or the run row is gone. The caller stops.
- `RunScope` gains `runtime_id: Optional[str] = None`. `execute_run` gains the
  same optional keyword and threads it into the scope. `service.py` passes
  `lease.manager.runtime_id` when a lease exists; otherwise `None` and
  `fenced_update_run` falls back to `default_runtime_id()` (the same identity
  the guard uses).
- Unleased/embedded runs (`leaseEpoch IS NULL`) keep working: the SQL already
  allows them.

Which writes move:

| Call site | Fields | New path |
|---|---|---|
| `graph.py:883` | `modelSteps`, `promptTokens`, `completionTokens`, `totalTokens` | `fenced_progress` |
| `graph.py:1196` | `toolCalls`, `toolErrors` | `fenced_progress` |
| `graph.py:1476`, `:1503` | `status=running`, `startedAt` | `fenced_progress` (the guard owns the run before this point) |
| `graph.py:1621` | `surface`, `autonomy`, `workspaceId` | `fenced_progress` |
| `graph.py:2085` | `codeVerification` | `fenced_progress` |
| `graph.py:2247` | `memory` | `fenced_progress` |

`run_flags.record_run_flags` also calls `store.update_run(context=...)`; it must
accept an optional `runtime_id` and use the fenced path when provided. A flag
snapshot is diagnostic, but a stale worker's snapshot must not overwrite the
owner's.

On `LeaseLost`:

1. Do not write a terminal status (it would be fenced too).
2. Emit `run.lease_lost` on the **bus only** (no persistence) with
   `{runId, runtimeId, at}`; log a warning.
3. Return a terminal `RunResult(status="failed", error={code:"RUN_LEASE_LOST"})`
   from `execute_run` without touching the row.
4. Let the new owner/recovery reconcile the run. The watchdog's live-lease
   check (5.5) prevents a sweep from racing the new owner.

### 5.2 Atomic boundary (`RunLineage.save_boundary`)

```python
def save_boundary(
    self, run_id: str, kind: str,
    payload: Optional[dict[str, Any]],
    messages: Optional[list[Any]],
    *,
    retries: int = 1,
) -> dict[str, Any]:
    """Commit the message cursor and the checkpoint in ONE transaction."""
```

Transaction:

```
BEGIN IMMEDIATE
  serialized = serialize_run_messages(messages)        (outside the txn if large)
  for seq, payload in enumerated(serialized):
      INSERT OR REPLACE RunMessage(...)
  DELETE FROM RunMessage WHERE runId=? AND seq >= len(serialized)
  seq = SELECT COALESCE(MAX(seq), -1) + 1 FROM RunCheckpoint WHERE runId=?
  INSERT RunCheckpoint(id='ckpt_<run>_<seq>', ...)
COMMIT
```

Rules:

- Payload is still bounded by `bound_checkpoint_payload`; add `messageSeq` after
  the cursor is known.
- `save_messages` and `save_checkpoint` keep their public signatures and
  delegate to shared private helpers (`_write_messages_locked`,
  `_next_checkpoint_seq_locked`). Existing callers (tests, scorecard,
  `build_session`) do not change.
- `HARNESS_CHECKPOINT_ATOMIC=off` → the graph calls the two legacy methods and
  preserves today's two-commit behaviour.
- A boundary failure is retried **once** (SQLite busy is transient). If it
  still fails, `_write_checkpoint` raises `CheckpointWriteFailed`
  (`code="CHECKPOINT_WRITE_FAILED"`). `execute_run` catches it, writes a fenced
  `failed` terminal state (if it still owns the lease) and emits `run.failed`.
  There is no silent continue without a durable boundary.
- Do not add a unique index on `RunCheckpoint(runId, seq)` in this slice: one
  lease owner plus `BEGIN IMMEDIATE` is the serialization guarantee, and a
  legacy duplicate would make the migration fail. (The event table is different
  — it is written by more than one emitter and needs the constraint; see 5.4.)
- Intent-marker fallback is **not** implemented unless measurement shows the
  single transaction holds the write lock too long. The payload is bounded and
  the message serialization happens before `BEGIN IMMEDIATE`.

### 5.3 Pre-dispatch idempotency (`ToolExecutionIdempotency.state`)

Additive schema:

```sql
ALTER TABLE ToolExecutionIdempotency ADD COLUMN state TEXT NOT NULL DEFAULT 'done';
ALTER TABLE ToolExecutionIdempotency ADD COLUMN startedAt TEXT;
ALTER TABLE ToolExecutionIdempotency ADD COLUMN finishedAt TEXT;
```

API:

```python
def mark_tool_started(run_id, step_index, tool_call_id, name) -> None: ...
def mark_tool_done(run_id, step_index, tool_call_id, result) -> None: ...
def mark_tool_unknown(run_id, step_index, tool_call_id, reason) -> None: ...
def was_tool_executed(...) -> Optional[dict]:   # includes state
```

Rules:

- `mark_tool_started` uses `INSERT OR IGNORE` with `state='started'`, so a
  re-entry cannot downgrade a `done` row.
- `mark_tool_done` updates the row (or inserts `done` when no start row exists,
  for compatibility with callers that still use `mark_tool_executed`).
- `mark_tool_executed` remains as a deprecated alias to `mark_tool_done`.
- Resume:
  - `done` → reuse the recorded `text`/`ok`/`error` (today's behaviour).
  - `started` **and** the tool is effectful → `mark_tool_unknown` and return a
    typed refusal; never dispatch.
  - `started` **and** the tool is read-only → safe to execute again; overwrite
    the row via `mark_tool_done`.
  - `unknown` → refuse and surface reconciliation, as `started`.
- The graph writes `mark_tool_started` immediately before `effects.begin` /
  dispatch. For a plugin veto or budget refusal, write `mark_tool_done` for the
  synthetic result so a resume does not re-ask.
- `effects.finish(ok=...)` moves into a `finally`; on an exception it becomes
  `effects.mark_unknown(...)`. This closes the window where a handler raises
  after the side effect but before `finish`.
- The tool's effectful classification stays exactly as today:
  `effect` truthy or `permission != "read"`.

### 5.4 Durable event sequence (`EventSequence`)

Store method (the ONE allocator):

```python
def append_event_sequenced(self, run_id, event_type, data) -> dict:
    """BEGIN IMMEDIATE; seq = MAX(seq)+1; id = evt_<run>_<seq>; INSERT; COMMIT."""
```

Rules:

- `RunEmitter.emit` / `emit_sync`: when `HARNESS_EVENT_SEQ=on`, call the store
  allocator and use its returned id/seq. The per-instance `_seq` is no longer
  the source of truth for durable events.
- On `sqlite3.IntegrityError` (the unique index), retry the allocation **once**;
  a second failure logs and drops the event (never breaks the run).
- `HARNESS_EVENT_SEQ=off` → today's per-emitter counter and `store.append_event`.
- `emit_transient`: keep localization out of the durable space. Use
  `id = f"evt_{run_id}_t_{uuid4().hex[:8]}"` and a **negative** process-local
  counter for `seq`. Transient events are never persisted, so they cannot
  collide with a durable `(runId, seq)`.
- Migration (in `run_lineage`/`migrations` or a small events migration):
  1. Find `(runId, seq)` duplicates; for each run, renumber the later rows
     deterministically by `at, rowid` (preserve every row; only `seq` changes).
  2. `CREATE UNIQUE INDEX IF NOT EXISTS idx_harness_event_run_seq ON
     HarnessEvent(runId, seq)`.
  Run the repair inside one `BEGIN IMMEDIATE`. This is the only historical
  rewrite in W6, and it is required for the constraint to exist.
- The watchdog/recovery inserts (`run_watchdog.py:159-171`,
  `run_recovery.py:126-132`) switch to `append_event_sequenced` too, so they
  cannot collide with an emitter.

### 5.5 Lease-aware watchdog

```python
def find_stalled(rows, now_epoch, threshold_for=stall_threshold_s,
                 live_run_ids: Optional[set[str]] = None) -> list[str]:
    ...
    if live_run_ids and str(row["id"]) in live_run_ids:
        continue
```

`sweep_stalled_runs` runs one bounded query before detection:

```sql
SELECT runId FROM RunLease WHERE expiresAtMs >= ?
```

It passes that set to `find_stalled`. A run with a live lease is skipped
regardless of event silence. If the lease table is absent, the set is empty and
behaviour is unchanged. The sweep still emits `run.failed`/`run.partial` via the
sequenced allocator.

### 5.6 Hardline, gateway honesty and shell parity

#### 5.6.1 `security/hardline.py` (new, pure)

```python
@dataclass(frozen=True)
class HardlineVerdict:
    rule: str
    reason: str

def evaluate(command: str, *, tool: str = "") -> Optional[HardlineVerdict]:
    """The always-on command floor. Pure, deterministic, no config."""
```

Categories and examples (anchored on normalized whole-command shapes, not bare
substrings):

| Rule | Matches | Why |
|---|---|---|
| `root-wipe` | `rm -rf /`, `rm -rf /*`, `rm --no-preserve-root /`, `rd /s /q c:\`, `del /f /s /q c:\*` | destroys the host |
| `fork-bomb` | `:(){ :|:& };:` and the common renamed variants | process exhaustion |
| `raw-device` | `dd if=... of=/dev/sd*`, `> /dev/sd*`, `mkfs*`, `format c:`, `diskpart clean`, `Clear-Disk`, `Initialize-Disk`, `Format-Volume` | destroys filesystems |
| `pipe-to-root` | `curl ... | sh|bash|sudo`, `wget ... | sh`, `Invoke-WebRequest ... | Invoke-Expression` | unverified remote code as the host user |
| `recursive-permissions` | `chmod -R 777 /`, `chmod -R 000 /`, `icacls c:\ /grant everyone`, `takeown /f c:\ /r` | privilege/availability wipe |
| `root-shell` | `sudo su`, `su -`, `runas /user:administrator`, `Start-Process -Verb RunAs` | privilege escalation |
| `system-dir-write` | destructive writes under `c:/windows`, `c:/program files`, `/etc`, `/usr`, `/bin`, `/boot` | OS corruption |

Rules:

- A match is `DENY` with `code="HARDLINE_DENIED"`; no grant, YOLO, policy,
  approval or profile can downgrade it.
- Evaluate the **command string** from `shell_run`/`shell_spawn`, the argv from
  `terminal_run`, and any `command`/`cmd` field in an effectful tool's
  arguments. Do not attempt to evaluate arbitrary prose.
- Keep the patterns precise; a benign `rm -rf ./build` or `dd if=file of=out`
  must pass. The test file carries an explicit benign list.
- The floor remains the second layer: `security/integration.make_security_authorizer`
  calls hardline **before** the gateway/floor, and `security/floor.evaluate`
  may also consult it when a `command` is supplied (defense in depth).

#### 5.6.2 No silent security fallback

Today `_wrap_with_security` returns the inner authorizer when no gateway exists,
and `make_security_authorizer` falls through when `classification is None`. That
is correct for read-only tools and legacy capability authorizers, but not for an
effectful call whose only gate would otherwise be a permissive inner.

Rule:

- When `token_mode() == "enforce"`, an effectful tool with **no** gateway is
  refused with `SECURITY_UNAVAILABLE` (audited). There is no effect token
  minter without the gateway, so `enforce` cannot be satisfied anyway.
- When `token_mode() == "shadow"`, log one warning per process
  (`security gateway unavailable; effectful calls are running on the capability
  authorizer only`) and continue — today's behaviour. This keeps zero-config
  and tests intact.
- A `classification is None` result remains a pass-through to the inner chain;
  classification gaps are a separate audit item (not a W6 behavior change).

#### 5.6.3 Effect-token enforce (staged)

- `HARNESS_EFFECT_TOKENS` stays `shadow` by default in W6.0.
- Add a startup warning when `shadow` is active outside development:
  `HARNESS_EFFECT_TOKENS=shadow: replayed effectful calls are recorded, not
  blocked`.
- Ship `enforce` behind the existing values and a canary:
  shadow → warn-only (one release) → enforce in production, per ADR.
- `token_mode()` should read the W0 flag registry where practical, but the
  registry default must remain `shadow` until the ADR changes it. Do not silently
  change the default in this slice.

#### 5.6.4 Shell parity

- `shell_run`: build a `code.sandbox.RunSpec` with
  `argv=detect_shell()+[command]`, `cwd`, `env=build_env()`,
  `timeout_s`, `output_cap_bytes=MAX_OUTPUT_CHARS`, `network=False`; call
  `sandbox.run(spec)`. Map `RawResult` → `ShellResult` (`status` from
  timeout/killed/exit). This gives the Job Object / process-group tree kill,
  output caps, resource sampling and the scrubbed env already proven by the
  analysis path.
- `shell_spawn`: build the same `RunSpec` and call
  `terminal.spawn.spawn_process(spec)`. Keep the `ProcessHandle` facade
  (`pid`, `command`, `cwd`, `output`, `poll`, `status`, `exit_code`) but back
  it with `SpawnedProcess`; `kill()` calls `kill_tree()`.
- `process_output`/`process_kill`/`process_list` keep their wire shapes.
- If the sandbox primitive is unavailable, `shell_run`/`shell_spawn` return a
  named refusal (`SANDBOX_UNAVAILABLE`) — never an unsandboxed fallback.
- Windows `taskkill /F /T /PID` and POSIX `killpg` are already implemented in
  `terminal/spawn.py`; reuse them, do not duplicate.

---

## 6. Slices and acceptance

| Slice | Change | Acceptance | Est. |
|---|---|---|---|
| **W6.1** | `fenced_progress` helper; `RunScope.runtime_id`; route all `store.update_run` in `graph.py` and `run_flags` | A stale worker cannot write counters or a terminal status; on lease loss the run stops with `RUN_LEASE_LOST`; unleased runs still work | 0.5 ew |
| **W6.2** | `RunLineage.save_boundary` + one-transaction implementation; `_write_checkpoint` uses it with one retry; `CheckpointWriteFailed` | Kill between message write and checkpoint write leaves **neither** partial; a successful boundary resumes with the same message tail; a failed boundary fails the run with `CHECKPOINT_WRITE_FAILED` | 0.5 ew |
| **W6.3** | `ToolExecutionIdempotency.state` (`started`/`done`/`unknown`), `mark_tool_started`/`done`/`unknown`; effects `finish` in `finally` | Crash after `started` → `unknown`, never re-executes an effectful tool; crash before dispatch → safe retry; a read-only `started` is replayed; plugin veto records `done` | 0.5 ew |
| **W6.4** | `append_event_sequenced`; unique `(runId, seq)`; emitter uses it; transient id space; duplicate-seq repair migration | Two emitters for one run produce no dropped/colliding ids; every durable event has a unique seq; `HARNESS_EVENT_SEQ=off` restores today | 0.5 ew |
| **W6.5** | `find_stalled(live_run_ids=...)`; sweep queries live leases | A lease-held run is never failed by another runtime; an expired lease is still swept | 0.25 ew |
| **W6.6a** | `security/hardline.py`; consult it in the authorizer before floor/policy; shell/terminal/effectful args | Root wipe, fork bomb, raw device write, pipe-to-root and recursive chmod are denied even with a grant/YOLO; benign commands pass | 0.5 ew |
| **W6.6b** | `shell_run` → `sandbox.run`; `shell_spawn` → `terminal.spawn.spawn_process`; tree kill | A shell command cannot bypass the isolation primitive; a background shell is tree-killed; scrubbed env unchanged | 0.5 ew |
| **W6.6c** | Effect-token enforce canary + startup warning; gateway-unavailable refusal under `enforce` | A replayed token is blocked under `enforce`; missing gateway refuses effectful calls under `enforce`; shadow still records without blocking | 0.5 ew |
| **W6.7** | Telemetry, flags, docs, cleanup | `checkpoint.write` / `run.lease_lost` / `event.seq_retry` / `hardline.blocked` counters exist; flags documented; `CHANGELOG` + owning docs updated | 0.25 ew |

Total: **≈3.5 engineer-weeks**.

### Slice detail — files and seams

**W6.1**

- `run_lease.py` — `LeaseLost`, `fenced_progress`.
- `run_scope.py` — `runtime_id`.
- `graph.py` — replace six `store.update_run` calls; add `runtime_id` to
  `execute_run` and `_invoke_with_history`; catch `LeaseLost`.
- `service.py` — pass `lease.manager.runtime_id` in both run paths.
- `run_flags.py` — `runtime_id` parameter.

**W6.2**

- `run_lineage.py` — `CheckpointWriteFailed`, `save_boundary`, private locked
  helpers.
- `graph.py` — `_write_checkpoint` calls `save_boundary` when the flag is on;
  retry once; propagate `CheckpointWriteFailed`.
- `execute_run` — map the failure to `CHECKPOINT_WRITE_FAILED`.

**W6.3**

- `run_lineage.py` — `state`/timestamps columns (idempotent `ALTER TABLE` in
  `_ensure_schema`), new mark methods, `was_tool_executed` state.
- `graph.py` — start before dispatch; done/unknown after; `try/finally` around
  effects; read-only replay path.
- `run_effects.py` — no schema change; optionally add `begin_many`? No.

**W6.4**

- `persistence.py` — `append_event_sequenced` (or a small
  `events_sequence.py` that owns the SQL, keeping `persistence` under its size
  ratchet).
- `events.py` — emitter path; transient id space.
- `run_lineage.py` / `migrations.py` or a new `events_migration.py` — unique
  index + duplicate repair.
- `run_watchdog.py`, `run_recovery.py` — sequenced inserts.

**W6.5**

- `run_watchdog.py` — optional live set, sweep query.
- No schema change.

**W6.6**

- `security/hardline.py` (new).
- `security/integration.py` — hardline call before gateway; `SECURITY_UNAVAILABLE`
  under enforce.
- `code/authorizers.py` — deny wrapper when enforce and no gateway.
- `code/shell.py` — `run`/`spawn` through sandbox/terminal spawn; `kill` tree.
- `security/effect_tokens.py` — startup warning; no default change.
- `security/bootstrap.py` / `service.py` — warn once; no new flag.

---

## 7. Fault matrix

| Window | Injection | Expected |
|---|---|---|
| Lease stolen between two progress writes | second manager claims; stale writer calls `fenced_progress` | `False` → `RUN_LEASE_LOST`; stale write absent; new owner's row intact |
| Crash after `save_messages`, before `save_checkpoint` | raise between the two legacy calls (flag off) / simulate a process kill in a subprocess (flag on) | Flag on: neither rows nor checkpoint partial. Flag off: documented legacy exposure only |
| Crash after `mark_tool_started`, before dispatch | raise in the dispatch seam | On resume: `started` + effectful → `unknown`, no dispatch |
| Crash after effect success, before `finish` | handler performs the effect then raises | `finally` marks `unknown`; no re-run |
| Two emitters for one run | concurrent `emit` from two `RunEmitter`s | Unique seq; no dropped event; retry once on a forced collision |
| Duplicate legacy event seq | insert duplicates before migration | Repair renumbers deterministically; unique index creates; every row preserved |
| Silent run with a live lease | age the events; hold a lease | Watchdog skips it; expired lease is swept |
| Replayed effect token under `enforce` | execute the same token twice | Second call refused (`already used`) |
| Missing gateway under `enforce` | `set_gateway(None)` + effectful tool | `SECURITY_UNAVAILABLE`; no dispatch |
| Hardline command with a standing grant | grant + `rm -rf /` | Denied at hardline; no approval card; audit row |
| Benign shell command | `rm -rf ./build`, `dd if=a of=b` | Allowed (subject to normal approval) |
| Shell background tree | spawn a parent that spawns a child; kill | Child dies with the tree |
| Unleased/embedded run | `execute_run` without a lease | Today's behaviour; fenced write allowed by `leaseEpoch IS NULL` |

---

## 8. Test plan

### New/updated Python tests

- `test_run_lease.py` — `fenced_progress` success/failure; `LeaseLost`;
  unleased compatibility; `runtime_id` threading.
- `test_run_lineage.py` — `save_boundary` atomicity (monkeypatch a failing
  insert after the message write → rollback), checkpoint seq, message cursor,
  legacy methods unchanged.
- `test_run_resume.py` — resume from `agent_step`; crash after `started`;
  read-only replay.
- `test_run_effects.py` — `finish` in `finally`; exception → `unknown`.
- `test_run_kernel_faults.py` (new) — a subprocess kill between checkpoint and
  dispatch; a two-emitter concurrency test; a stale-worker fencing test.
- `test_events_sequence.py` (new) — allocator monotonicity under threads,
  collision retry, transient ids, duplicate repair, `HARNESS_EVENT_SEQ=off`.
- `test_run_watchdog.py` — live lease skip; expired lease sweep; missing table.
- `test_hardline.py` (new) — one test per rule, benign list, grant/YOLO
  non-override, shell/terminal parity.
- `test_shell_sandbox_parity.py` (new) — `shell_run` uses the sandbox backend;
  `shell_spawn` tree-kills; unavailable backend refuses.
- `test_c6_effect_tokens.py` — keep the shadow default; add the enforce canary
  test and the missing-gateway refusal.
- `test_security_failure.py` / `test_security_integration.py` — gateway absent
  + enforce.

### Determinism rules

- Fault tests use a temp `agent-memory.db`, never `jdds.db`, and a fake model /
  stub bridge (the existing `test_run_lineage.py` pattern).
- Concurrency tests use `threading.Barrier` or `asyncio.gather` and assert
  persisted rows, not log text.
- Every slice adds at least one fault-injection or adversarial case (the global
  acceptance gate).

### Manual/live check

- One live run with `HARNESS_EFFECT_TOKENS=enforce` and a shell approval:
  approve once, observe the token, replay the same tool call → refused.
- One live run killed mid-tool (task manager / `kill -9` on the Python child)
  → resume shows `unknown` and does not re-run.

---

## 9. Rollout

| Step | Flag state | What to watch |
|---|---|---|
| 1. Land W6.1–W6.2 behind flags | `HARNESS_FENCED_PROGRESS=on`, `HARNESS_CHECKPOINT_ATOMIC=on`, `HARNESS_EVENT_SEQ=off` | `run.lease_lost` count, checkpoint write latency, no duplicate terminal writes |
| 2. Land W6.3 in shadow? | No shadow for idempotency; `started/done` is additive. Run with the pair on. | `effect.unknown` count, resumed runs |
| 3. Land W6.4 | `HARNESS_EVENT_SEQ=on` after the migration; keep `off` as rollback | dropped events, seq retries, SSE gaps |
| 4. Land W6.5 | always on | watchdog failures of still-live runs → zero |
| 5. Land W6.6a/b | always on (no kill switch for hardline; the *pattern list* is code-reviewed) | false-positive rate; shell backend availability |
| 6. Effect-token canary | `HARNESS_EFFECT_TOKENS=enforce` on one runtime/one workspace | refused legitimate calls; reconciliation prompts; audit volume |
| 7. Default decision | ADR + release note | only after two green weeks |

Kill switches:

- `HARNESS_FENCED_PROGRESS=off` → `store.update_run`.
- `HARNESS_CHECKPOINT_ATOMIC=off` → legacy two commits.
- `HARNESS_EVENT_SEQ=off` → per-emitter counter.
- `HARNESS_EFFECT_TOKENS=shadow|off` → record-only / disabled.
- Hardline has **no** runtime off switch by design; a bad rule is fixed by a
  code change + test. (The alternative — an operator toggle — would let an
  attacker with config access disable the last line of defense.)

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SQLite write-lock contention from the boundary txn | Medium | Medium | Bounded payload; serialize outside the txn; retry once; measure p95; intent marker as the documented fallback |
| Fenced progress breaks a test/embedded caller | Medium | Medium | `leaseEpoch IS NULL` allowed; `HARNESS_FENCED_PROGRESS=off`; `RunScope.runtime_id` optional |
| Old duplicate event seqs block the unique index | Medium | High | Repair migration before the index; run in `BEGIN IMMEDIATE`; backup the DB in tests |
| Idempotency `started` refuses a legitimate retry | Medium | High | Only effectful tools; read-only replay allowed; operator reconciliation message; `mark_tool_done` after a synthetic refusal |
| Hardline false positive | Medium | Medium | Precise anchored patterns; benign fixture list; no runtime toggle means a fast code fix, not a config change |
| Shell parity changes output/status semantics | Medium | Medium | Map `RawResult` explicitly; keep the `ShellResult` wire shape; tests for timeout/exit/truncation |
| Enforce breaks a workflow | Medium | High | Shadow → warn → enforce; per-tool audit; rollback `shadow`; never flip the default in the same PR |
| Two emitters still collide | Low | Medium | Unique index + retry; transient ids separate; a test forces a collision |
| Watchdog skip hides a genuinely stuck leased run | Low | Medium | Lease TTL (60 s) + heartbeat; expiry still swept; a dead runtime's lease expires |

---

## 11. File map

| File | Change |
|---|---|
| `python/harness/run_lease.py` | `LeaseLost`, `fenced_progress` |
| `python/harness/run_scope.py` | `runtime_id` |
| `python/harness/graph.py` | fenced progress, atomic boundary call, idempotency states, effects `finally`, `LeaseLost`/`CheckpointWriteFailed` handling |
| `python/harness/run_lineage.py` | `save_boundary`, state columns/methods, `CheckpointWriteFailed` |
| `python/harness/run_effects.py` | no schema change; `finish`/`unknown` usage from graph |
| `python/harness/persistence.py` | `append_event_sequenced` (or a small events-sequence module) |
| `python/harness/events.py` | durable sequence; transient id space |
| `python/harness/run_watchdog.py` | live-lease skip; sequenced inserts |
| `python/harness/run_recovery.py` | sequenced inserts (reuse allocator) |
| `python/harness/security/hardline.py` | **new** pure command floor |
| `python/harness/security/integration.py` | hardline call; `SECURITY_UNAVAILABLE` under enforce |
| `python/harness/security/effect_tokens.py` | startup warning; no default change |
| `python/harness/code/authorizers.py` | deny wrapper when enforce + no gateway |
| `python/harness/code/shell.py` | sandbox/terminal-spawn parity + tree kill |
| `python/harness/config/flags.py` | no new flag; existing W6 flags gain consumers |
| `python/tests/test_run_lease.py` | extend |
| `python/tests/test_run_lineage.py` | extend |
| `python/tests/test_run_resume.py` | extend |
| `python/tests/test_run_effects.py` | extend |
| `python/tests/test_run_watchdog.py` | extend |
| `python/tests/test_run_kernel_faults.py` | **new** |
| `python/tests/test_events_sequence.py` | **new** |
| `python/tests/test_hardline.py` | **new** |
| `python/tests/test_shell_sandbox_parity.py` | **new** |
| `python/tests/test_c6_effect_tokens.py` | extend |
| `docs/harness/roadmap/w6-run-kernel-integrity-plan.md` | this plan |
| `docs/harness/roadmap/hermes-inspired-improvement-plan.md` | add the detailed-plan pointer in W6 |
| `docs/NAVIGATION.md` | add W6 to the research reports + run-kernel row |
| `docs/CHANGELOG.md` | entry |

---

## 12. Decisions and open questions

**D1 — Effect-token default.** Keep `shadow` in W6.0. Enforce is a separate
production-default decision requiring an ADR, a canary and a release note. W6
ships the enforcement path, the startup warning and the gateway-unavailable
refusal, so flipping the default is a one-line change once the canary is green.

**D2 — Boundary atomicity vs. intent marker.** Implement the single transaction
first. The payload is bounded and serialization happens before the lock. Add the
intent marker only if measured `checkpoint.write` p95 regresses beyond the W0
baseline budget. Do not ship both paths at once.

**D3 — Idempotency for read-only tools.** `started` is recorded for every tool,
but only an effectful `started` is treated as unknown. Re-running a read-only
tool is safe and is what today's resume does. This keeps the ledger honest
without making ordinary resumptions fail.

**D4 — Hardline location.** Put it in the security authorizer (the earliest
effectful seam) **and** call it from `shell`/`terminal` classification. The
floor remains the second layer. This avoids a new approval path and keeps the
command string where it is available.

**D5 — Shell background processes.** Reuse `terminal/spawn.py` rather than
adding a third spawn implementation. Keep the `ProcessHandle` facade so the
tools' wire shapes do not change.

**D6 — Unique index on checkpoints?** No. One lease owner + `BEGIN IMMEDIATE`
is enough; a legacy duplicate would make the migration brittle. Events are
different because more than one emitter writes them.

**Open:** should the watchdog emit `run.lease_skipped` at debug level for
operator visibility, or stay silent? Recommendation: a single counter
(`watchdog.lease_skipped`) and no per-run event.

---

## 13. Exit criteria

W6 is done when:

1. `npm run test` and `npx tsc --noEmit` pass from `Black-Eclipse-site/`.
2. Every new test in §8 passes, including at least one fault-injection case per
   slice.
3. The offline evaluation gate (`node scripts/test-evals.js`) and
   `npm run audit:agent` do not regress.
4. A stale worker cannot write progress or terminal state; a crash at the
   message/checkpoint boundary leaves no partial state; a crash after
   `started` never re-executes an effect; two emitters never collide; a live
   lease is never failed by the watchdog; a replayed token is blocked under
   enforce; a hardline command is blocked with a grant; a shell command is
   tree-killed through the sandbox.
5. Each flag has a kill switch, documented in `w0-flags-and-review.md`.
6. `CHANGELOG.md` records the change and the owning docs are updated.

---

## 14. Relationship to W0/W1/W2/W3/W7

- **W0** supplies the flag registry and the “no second seam” gate. W6 consumes
  the four W6 flags; no new registry is added.
- **W1** already returns per-attempt usage and a classified error. W6 fences the
  run-level write of that usage; it does not change the gateway.
- **W2** uses `RunEffects.has_started` and checkpoints for any-step overflow
  recovery. W6 makes both more trustworthy: the boundary is atomic and the
  effect row is pre-dispatch.
- **W3** adds parallel read-only tools. W6's idempotency state is written before
  dispatch, so a parallel batch still records each call exactly once.
- **W7** (delegation / file checkpoints) builds on durable job state and
  `RunScope`; the W6 idempotency and boundary guarantees are its prerequisite.

---

## 15. Suggested first implementation sequence

| Day | Work |
|---|---|
| 1 | `fenced_progress` + `runtime_id`; move the six `graph.py` writes; `LeaseLost` handling; tests |
| 2 | `save_boundary` + `_write_checkpoint`; `CheckpointWriteFailed`; fault test |
| 3 | `ToolExecutionIdempotency.state`; pre-dispatch start; `finally` for effects; resume tests |
| 4 | `append_event_sequenced` + unique index + duplicate repair; two-emitter test |
| 5 | Watchdog live-lease skip; test |
| 6–7 | `security/hardline.py` + authorizer wiring + tests |
| 8–9 | Shell sandbox parity (`run` + `spawn` + tree kill) + tests |
| 10 | Effect-token enforce canary + gateway-unavailable refusal + docs/CHANGELOG |
