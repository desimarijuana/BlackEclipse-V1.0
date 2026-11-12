---
title: Agent Reliability & Contract Remediation Plan (Rev 2 — architecture review)
status: Active
last-verified: 2026-11-11
revision: 2
owner: Agent runtime + quant platform
source: docs/quant-research/agent-evaluation-2026-11-11.md
baseline_composite: 82 / 100
target_composite: ">= 90 / 100 with zero P0 gate failures"
review_scope: planning + code inspection only (no source or database changes)
---

# Agent Reliability & Contract Remediation Plan (Rev 2)

This is the execution plan for the defects found in the independent pre-launch
audit (`docs/quant-research/agent-evaluation-2026-11-11.md`). Rev 2 is a
principal-architect review of the first draft: every architectural claim below
was checked against the working tree, and the parts of Rev 1 that were wrong are
called out explicitly.

**Scope discipline.** Rev 2 was produced as a planning and code-inspection
exercise; §0a records the implementation slice that followed. Nothing in the
workstreams below is claimed complete unless §0a says so.

---

## 0a. Implementation status (2026-11-11)

The first implementation slice is complete and verified by targeted tests. It is
deliberately the low-risk half of the P0 work; the lifecycle write-path changes
(lease/fencing/effect ledger) remain open.

| Workstream | Status | What landed | Evidence |
|---|---|---|---|
| W3 calculation contract | **Implemented (core)** | `finance_series.input` (prices/returns/auto), one compounding normalization, first-return preserved, nearest-rank VaR with float-safe ceil, prompt instruction | 12 contract tests; 112 calc/quality tests pass |
| W6 answer trust | **Implemented (extractor)** | Metric/ML stop-list, position-context requirement for number-only claims, regression tests | 27 advisory tests pass |
| W4 provenance | **Partial** | `store=history_cache` + providers on coverage/list/catalog; JDdS-vs-cache wording fixed in prompts/tool docs | 26 market tests pass |
| W1 recovery state | **Partial** | checkpoint-aware `interrupted` state, conditional terminal update, resume accepts it; durable `RunLease`/`RuntimeInstance`, atomic claim, daemon heartbeat, environment ownership, recovery skips a live lease; boot forensics log | 19 lease/recovery tests pass |
| W1 effect safety | **Partial** | `RunEffect` ledger at the tool seam: effectful calls are marked `started` before dispatch and `done` after; an unconfirmed `started` is **not** re-executed on resume and is surfaced as `unknown` | 2 new effect-ledger tests |
| W1 terminal fencing | **Done** | terminal `completed/failed/cancelled` writes assert the live lease epoch (`fenced_update_run`); a stale worker cannot finalize another owner's run | 3 fencing tests |
| W2 HTTP contract | **Done** | 504 for timeout, run handle on errors, 202 `eventsUrl`/`pollAfterMs`, front-door resume route, watchdog partial output, SSE `after`/`Last-Event-ID` replay, and client recovery: a dropped stream polls the run to terminal instead of submitting a second run; a reload reattaches an in-flight run by `chatId` | 11 chat-route tests; `tsc` clean |
| W5 budgets | **Done (offline)** | `maxToolCalls=48`; `maxTokens` forces a tool-free final answer; per-run cost is computed from the one pricing registry (`costUsd`, `priced`, unknown never zero) | 2 budget + 3 cost tests |
| W7 assurance | **Done (offline)** | `delivery` dimension + `release_ready()` hard gate; a **versioned 44-check audit corpus** (`python/harness/evaluation/corpus/agent_audit_v1.json`) runs as `npm run audit:agent` and is a `check-all` gate | 44 audit checks |
| W0 forensics | **Partial** | boot log with pid/env/port/db/schema/orphan count; runtime identity/conflicts | compiles; no dedicated test |
| W4 resolver/`data_inventory` | **Done (read-only)** | `market/vault.py` reads `jdds.db` in SQLite `mode=ro`; `data_inventory` reports JDdS vs `history_cache` separately; `resolve_series` labels both and flags count conflicts. Backfill/licensing policy remains the owner's decision | 4 vault tests |
| W2 SSE replay + client reattach | **Not started** | route exists; replay/auto-attach not wired | — |
| W5 budgets/ergonomics | **Not started** | — | — |
| W7 assurance expansion | **Not started** | — | — |

No release gate (G1–G10) is claimed as passed. Verification run: the scripted
**G1 soak passed** (100 sequential + 96 concurrent, 0 left running, 5
checkpointed orphans `interrupted`); `npm run audit:agent` passes **44 checks**;
`node scripts/test-evals.js` **ALL PASS**; `npx tsc --noEmit` clean. Full
`npm run test`: **10,610 passed, 34 skipped, 1 failure** — the failure is
`test_graph_parallel`'s load-sensitive 0.85 s timing assertion (took 1.53 s under
the full-suite load) and it passes in isolation (9/9). That test is unrelated to
this work and its threshold was not weakened; the full gate is not claimed
green until that flake is handled separately.

---

## 0. Executive assessment of the original plan

Rev 1 was directionally right — resume over rerun, explicit contracts, one
store vocabulary — but it contained four incorrect assumptions that would have
produced a broken or unsafe implementation:

| Rev 1 claim | Verified reality | Consequence |
|---|---|---|
| Add lease columns in `prisma/schema.prisma` | `HarnessRun` lives in **`agent-memory.db`** and is created by `python/harness/persistence.py`; additive schema changes go through `harness/migrations.py` (`MigrationRunner`, namespace `agent-memory`) or the `ALTER TABLE` pattern in `run_lineage._ensure_schema`. Prisma owns `jdds.db`, not runs. | The migration would have been written in the wrong database and never applied. |
| Boot should "resume every checkpointed run" | `graph.py:1353–1366` **refuses to resume any run whose status is `completed`, `failed`, or `cancelled`** (`RESUME_CONFLICT`). Boot reconciliation currently marks orphans `failed`. | Resume can never happen: the state machine forbids it. A new recoverable state (`interrupted`) or a controlled recovery transition is required. |
| `market/series_store.py` becomes the canonical resolver | `SeriesStore` owns **only** `MarketBarSeries` in `agent-memory.db` — the provider-cache half. It never reads `jdds.db` and has no cross-store identity. | "One resolver" would have been a cache-only resolver labelled as the vault. A new resolver + identity contract is needed. |
| Remove the ×100 conversions from `calculations.py` | The ×100 is **intentional and declared** for percent metrics (`result.unit = "%"`). The actual defect is that every series calculator calls `_returns(series.values)`, i.e. it assumes **price levels**, and `finance_series` has no input-kind field. | Removing ×100 would have broken every percent metric and every downstream consumer. |
| Backfill core symbols into `jdds.db` | Yahoo/provider terms of service restrict persistent redistribution; the cache is a different store with different rights. | Blind backfill is a licensing risk and is removed from the plan pending an explicit rights decision. |
| Scope project rules in `code/project_memory.py` to fix the leaked `no doc change` line | Project rules are injected **only when `request.autonomy` is set and a workspace exists** (`graph_context.py:505+`); the audited chat runs had `autonomy: null`. No memory row contains the phrase; the five tool calls show no file read; the phrase is not in the financial system prompt. | Root cause is **unverified**. The plan must capture prompt provenance first, then fix the actual source; a generic output sanitizer is defence in depth, not the fix. |

Rev 1 also under-estimated effort (4 weeks solo), omitted the watchdog/lease
interaction, treated all resume as safe without an effect ledger, and did not
address checkpoint atomicity, migration/backup safety, provider pinning, token
budgets, or the cross-store licensing boundary.

**Assessment:** keep the plan's direction; replace W1, W3, W4, W6 root causes;
add the missing reliability and governance work; revise estimates to 8–10 solo
weeks with contingency.

---

## 1. Verified architectural findings

Evidence was read from the working tree on 2026-11-11. "Verified" means the code
was inspected; "observed" means it happened in the audit runs; "proposed" means
this plan introduces it and it does not exist today.

### 1.1 Run lifecycle and storage

| Finding | Evidence | Status |
|---|---|---|
| `HarnessRun` has no owner/lease/heartbeat/environment columns | `persistence.py` `CREATE TABLE HarnessRun` | verified |
| Additive schema changes use a namespaced migration ledger | `migrations.py` (`HarnessMigration`, `BEGIN IMMEDIATE`, id-ordered) and `run_lineage.LINEAGE_MIGRATIONS` | verified |
| Checkpoints, a durable message cursor and a tool idempotency ledger exist | `run_lineage.py` (`RunCheckpoint`, `RunMessage`, `ToolExecutionIdempotency`) | verified |
| Resume exists and reuses recorded tool results | `main.py` `POST /runs/{id}/resume`; `graph.py` checks `was_tool_executed` before executing | verified |
| Resume refuses terminal runs | `graph.py:1353–1366` returns `RESUME_CONFLICT` for `completed|failed|cancelled` | verified |
| Boot reconciliation marks **all** non-terminal runs `failed` | `run_recovery.fail_orphaned_runs`; wired in `service.py` startup | verified |
| The boot guard is a **per-port free probe**, not a database lock | `run_recovery._runtime_port_is_free`; TOCTOU between probe and bind | verified (race) |
| Checkpoint and message writes are separate commits | `graph._write_checkpoint` calls `save_messages` then `save_checkpoint`, each committing | verified |
| Checkpoint failures are swallowed | `_write_checkpoint` has `except Exception: pass` | verified |
| Checkpoint sequence is `MAX(seq)+1` outside a transaction | `run_lineage.save_checkpoint` | verified (concurrent resume collision) |
| Tool idempotency is recorded **after** execution, best-effort | `graph.py` calls `mark_tool_executed` after `run_tool_with_recovery`; `INSERT OR IGNORE`; exceptions logged | verified (crash window) |
| The resume eval gate only kills the process **after** the tool result is recorded | `eval_gates/resume.py` (`_Killed` on the second model call) | verified (does not test the dangerous window) |
| The watchdog uses the **preset** model budget, not the run's effective budget | `run_watchdog.stall_threshold_s` reads `AGENT_PRESETS[].runTimeoutMs`; deep-quant runs extend to 600 s | verified (false-stall risk) |
| Chat step budget is 24 (ceiling 32) but `request.maxSteps` can raise to `HARD_MAX_STEPS=240` | `graph.chat_step_budget` + `requested_budget` | verified (cap bypass) |
| A global run semaphore exists and defaults to **unlimited** | `service.py` `HARNESS_MAX_CONCURRENT_RUNS`, default 0 | verified |
| Runtime supervision avoids replacing a busy runtime, with a 30 s grace and 300 s start budget | `src/lib/harness/runtime-supervision.ts` | verified |
| The runtime **did** restart during the audit (orphaning runs) | `RUN_ORPHANED` ×4; `/health.startedAtMs` changed at 02:22Z after the audit | observed; root cause not proven |
| No boot/shutdown forensic record (pid, port, DB, active runs, orphan count, reason) | no such event on boot in the inspected paths | verified gap |

### 1.2 HTTP and response lifecycle

| Finding | Evidence | Status |
|---|---|---|
| Chat races the run against a 150 s soft deadline and returns 202 + runId/streamUrl | `src/app/api/harness/chat/route.ts` | verified |
| The failure branch returns 502 with `runId`; the outer catch returns 500 **without** a runId | `chat/route.ts` catch block | verified |
| The stream route is a raw SSE pass-through with no replay contract | `runs/[id]/stream/route.ts` forwards upstream; no `Last-Event-ID`/`after` | verified |
| Final output is persisted only at completion; partial assistant text lives in messages/checkpoints | `graph.py` completion path; `RunMessage` at step boundaries | verified |
| No `outputTruncated` / `stopReason` contract exists | no field in the run DTOs | verified gap |
| Cancel exists; resume has no front-door route | `runs/[id]/cancel`, `events`, `explain`, `receipt`, `stream` only | verified |

### 1.3 Financial calculation contracts

| Finding | Evidence | Status |
|---|---|---|
| `CalculationResult` already carries unit, observation count, frequency, missing-data policy, annualization, assumptions, warnings, detail | `research/calculations.py` dataclass | verified |
| Series calculators assume observations are **prices** | `_returns(series.values)` in `calculations.py` and `calculations_ext.py` | verified |
| `finance_series` has no `input` / `inputKind` parameter | `research/web_tools.py` | verified |
| Output units are mixed by design: `%` for period_change/cagr/vol/MDD/VaR/alpha/cumulative/annualized/rolling vol; unitless for Sharpe/Sortino/beta/correlation; covariance declares no unit | `calculations.py`, `calculations_ext.py` | verified |
| Three calculation families exist: `research/calculations*.py` (`finance_series`), `stats/` (`calculate_*`), `quant/metrics.py` (backtest metrics) | module layout + tool registry | verified |
| The audit only falsified `finance_series`; the `stats/` tools (`calculate_cointegration`, `calculate_regression`) matched independent results | audit T03/T09 | observed |
| The model's own sandbox arithmetic was correct when it bypassed the tool | audit T01/T02 | observed |

### 1.4 Market data and provenance

| Finding | Evidence | Status |
|---|---|---|
| `jdds.db` and the provider cache are different stores | Prisma schema vs `market/series_store.py` (`MarketBarSeries` in `agent-memory.db`) | verified |
| `history_catalog` reads only `MarketBarSeries` and never jdds | `market/tools.py::history_catalog` | verified |
| `agents.py` describes `history_catalog` as "the local data vault … durable cache" | `agents.py` tool comments | verified (naming collision) |
| `DataBridge` is documented as "Read-only access to JDdS data via the TS harness" | `tools.py` | verified (second vocabulary) |
| `data-bridge-history.ts` is a Yahoo chart fallback, not jdds | file header | verified |
| The audited answer reported cache inventory as "JDdS" (31 symbols/27 series vs jdds's 9/1,030) | audit T16 + direct SQL | observed |
| `get_data_quality_report` exists; `DATA_GAP` semantics are not documented as trading-session gaps | `market/quality.py`; audit R10 warning | verified gap |

### 1.5 Tool budgets and ergonomics

| Finding | Evidence | Status |
|---|---|---|
| Exact duplicate calls are already refused (`same tool + same args` per run) | `graph.py` `seen_calls` + `_stable_key` | verified |
| A total tool-call cap exists and is enforced when set, but `eclipse-agent` leaves it `None` | `AgentConfig.maxToolCalls`; `graph.py` `TOOL_BUDGET_EXCEEDED` | verified |
| No per-run token or cost budget exists in the runtime; the eval `TaskLimits.token_budget` is not wired | `schemas.AgentConfig`; `evaluation/runner.py` wires only `max_tool_calls` | verified gap |
| A generator exists (`synthesize_method_strategy`) but no one-call template API | observed T10 | verified |
| `PositionSizing` defaults to `percent_equity` **1.0%** | `quant/strategy.py` | verified |
| Live-trading risk policy is a separate authority | `trade/policy.py`, `trade/authorizer.py` | verified |

### 1.6 Answer trust

| Finding | Evidence | Status |
|---|---|---|
| Claim extraction requires a directive **and** (symbol **or** number) | `advisory/claims.py` | verified |
| "Symbol" is any uppercase 2–5 token absent from `_SYMBOL_STOP`; `FCFF`/`ADV` are not stopped and are never resolved | `advisory/claims.py` | verified (cause of both audit false positives) |
| Fenced code and markdown table rows are already excluded | `_prose_only`, `_is_table_row` | verified (do not regress) |
| The leaked `no doc change` line has no verified source | no memory row; project rules gated on `autonomy`; not in the financial prompt; no file-read tool call | **unverified** |

### 1.7 Evaluation assurance

| Finding | Evidence | Status |
|---|---|---|
| A task schema, graders, splits, corpus gate and live gate already exist | `evaluation/tasks.py`, `scoring.py`, `live_gate.py`, `check-all.js` | verified |
| The composite is guarded: a failed/unmeasured `task_success` or `safety_score` returns `None` | `scoring.weighted_composite` | verified |
| `reliability`, `cost`, `latency`, `token_usage`, `provenance` are **not** in the weighted composite; only two dimensions are critical | `DIMENSION_WEIGHTS`, `CRITICAL_DIMENSIONS` | verified gap |
| Task limits exist but only the tool-call cap is wired | `evaluation/runner.py` | verified gap |
| The corpus gate compares against a committed baseline | `check-all.js` step 9 | verified |

---

## 2. Missing requirements (added by this revision)

1. **Boot/shutdown forensics.** Every runtime start/stop must record pid, port,
   DB path, `BE_PROFILE`, schema version, active-run count, orphan count and the
   reason. Without this the observed restarts cannot be explained or prevented.
2. **Environment identity and DB ownership.** A runtime must know which
   environment owns `agent-memory.db` and must never reconcile another
   environment's runs. A `RuntimeInstance` heartbeat row is the cheap proof.
3. **Recoverable vs terminal states.** `interrupted` must be distinct from
   `failed`; otherwise the current resume rule makes recovery impossible.
4. **Fencing tokens.** A lease alone is insufficient: a stale worker can finish
   a write after losing the lease. Every run-scoped write needs `leaseEpoch`.
5. **Effect ledger for irreversible actions.** Checkpoint idempotency covers
   recorded successes, not a crash between an external effect and its record.
6. **Checkpoint atomicity and versioning.** One transaction for message+cursor,
   bounded payload, and a format/agent/tool-schema version that refuses an
   incompatible resume after an upgrade.
7. **Provider/model pinning on resume.** A resumed run must use the same
   provider/model (or an explicit operator switch); silent model substitution
   changes the answer and breaks reproducibility.
8. **Token/cost budgets and resource limits.** Prompt tokens repeat per step;
   the audit consumed 0.7–3.6 M tokens per answer. A per-run cumulative budget
   and a local concurrency default are required.
9. **Secrets and redaction.** Tool arguments/results are persisted
   (`HarnessToolExecution.args`). Confirm redaction before resume/audit reads
   them back; a resumed run must not replay secrets into a new prompt.
10. **Migration and backup safety.** Migrations are transactional, but there is
    no pre-migration backup/dry-run; the release gate must prove a restore.
11. **Config validation.** New flags (lease TTL, resume policy, budgets) must be
    validated by `doctor.js` and fail closed on nonsense.
12. **Auth/tenancy boundary.** The tested build is loopback single-operator;
    the resume route must be operator-gated like cancel, and auth must remain
    mandatory before any non-loopback exposure. No multi-tenant work is added.
13. **Broker crash-after-send test.** The ledger-before-send pattern is good but
    untested at the dangerous boundary (sent, then process dies before record).
14. **Prompt provenance capture.** Persist the exact compiled prompt segments
    (hash + optional redacted text) for a run so the `no doc change` leak can be
    attributed, not guessed.

---

## 3. Target architecture

### 3.1 Run lifecycle: leases, fencing, and recoverable states

**State machine**

```
queued ──► running ──► completed            (terminal)
                  ├──► failed               (terminal)
                  ├──► cancelled            (terminal)
                  └──► interrupted          (RECOVERABLE: checkpoint exists)
interrupted ──► running (one controlled resume)
```

`RUN_ORPHANED` becomes `interrupted` **iff** a checkpoint exists; otherwise it
remains `failed`. `RUN_TIMEOUT` keeps the partial output and writes
`interrupted` (resumable) or `failed` (only when no work exists) — see §3.2.

**Lease + fencing (new tables, one migration)**

```sql
-- Migration id: 2026-11-12-001-run-lease (after the existing 2026-11-11-001)
ALTER TABLE HarnessRun ADD COLUMN environment TEXT;      -- BE_PROFILE
ALTER TABLE HarnessRun ADD COLUMN runtimeId   TEXT;
ALTER TABLE HarnessRun ADD COLUMN leaseEpoch  INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS RunLease (
  runId      TEXT PRIMARY KEY,
  environment TEXT NOT NULL,
  runtimeId  TEXT NOT NULL,
  epoch      INTEGER NOT NULL,
  acquiredAt TEXT NOT NULL,
  heartbeatAt TEXT NOT NULL,
  expiresAt  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS RuntimeInstance (
  runtimeId  TEXT PRIMARY KEY,
  environment TEXT NOT NULL,
  port       INTEGER NOT NULL,
  dbPath     TEXT NOT NULL,
  pid        INTEGER,
  startedAt  TEXT NOT NULL,
  heartbeatAt TEXT NOT NULL
);
```

Claim atomically (single writer transaction):

```sql
BEGIN IMMEDIATE;
UPDATE RunLease
   SET runtimeId=?, epoch=epoch+1, acquiredAt=?, heartbeatAt=?, expiresAt=?
 WHERE runId=? AND expiresAt < ?;
-- if changes()==0: INSERT INTO RunLease ... ON CONFLICT(runId) DO NOTHING;
COMMIT;
```

Every run-scoped write carries the fencing predicate
`AND leaseEpoch = ?` (or the lease row's epoch). A stale worker's write affects
zero rows and must abort the run locally. This is the difference between
"usually works" and "cannot double-write".

**Heartbeat.** A dedicated daemon thread (own pooled SQLite connection) updates
`heartbeatAt/expiresAt` every 10 s. It must not live on the agent event loop,
which can be blocked by a synchronous tool. TTL 60 s; three missed beats are a
lost lease.

**Boot reconciliation (new order)**

1. Register `RuntimeInstance`; fail closed if the same `dbPath` is already owned
   by a live runtime in another process (compare pid + heartbeat).
2. Claim expired leases atomically.
3. For each claimed run:
   - last event is an approval wait → `interrupted` (never auto-resume);
   - checkpoint exists → `interrupted`, then bounded resume (max 2 concurrent);
   - no checkpoint → `failed` with `RUN_ORPHANED` (honest).
4. Emit `run.reconciled` with counts and reasons.
5. **Never** reconcile a run whose `environment` differs from this runtime's.

**Watchdog unification.** One sweeper owns both stall detection and expiry:
- a run is stalled only when its **effective** budget (stored at run start) plus
  grace has elapsed **and** the lease heartbeat is stale;
- an active long tool is activity (emit `tool.started` heartbeats);
- a run paused on approval is exempt;
- never mark a leased, heartbeating run failed.

### 3.2 Exactly-once vs effectively-once (non-negotiable wording)

- **Pure reads** may be retried freely.
- **Idempotent writes** (keyed by a digest, e.g. a strategy save, a checkpoint)
  may be retried when the key is stable.
- **Irreversible / external effects** (broker `order_send`, shell commands, file
  writes outside a sandbox, MCP effects, email/webhooks) are **at-most-once**.
  Exactly-once is not provable across a process boundary; the plan does not
  claim it.

**Effect ledger** (new table, same migration namespace):

```
RunEffect(
  effectId, runId, step, toolCallId, tool, digest, kind,
  state,          -- intent | dispatched | confirmed | unknown | failed
  externalRef,    -- broker ticket, git sha, file hash, …
  createdAt, updatedAt
)
```

Transitions:

```
intent ──► dispatched ──► confirmed
   │            │
   │            └──► unknown   (process died / adapter error)
   └──► failed (pre-dispatch failure: safe to retry)
```

Crash matrix (the part Rev 1 missed):

| Crash point | State on restart | Action |
|---|---|---|
| Before `intent` commit | no row | safe to retry |
| After `intent`, before dispatch | `intent` | safe to retry |
| After dispatch, before result | `dispatched` | **do not retry**; mark `unknown`; reconcile |
| After external success, before `confirmed` | `dispatched` | **do not retry**; reconcile by external ref |
| After `confirmed` | `confirmed` | reuse the recorded result |

Reconciliation is per tool class. The broker path already sets `unknown` and
tells the operator to check the terminal (`trade/service.py`); it is the model to
generalise. For shell/git/file writes, reconcile by inspecting the external
state (git status, file hash, process). For MCP, require an explicit operator
decision; never auto-retry.

The existing `ToolExecutionIdempotency` remains as the fast path for recorded
results; the effect ledger covers the unrecorded window and makes `unknown` a
first-class outcome rather than a silent duplicate.

### 3.3 HTTP and response lifecycle

| Situation | Status | Body contract |
|---|---|---|
| Run completed within the wait | `200` | `{success, output, runId, stopReason: "completed", truncated:false}` |
| Still running | `202` | `{success, status:"running", runId, streamUrl, eventsUrl, pollAfterMs}` |
| Sync wait deadline, run alive | `504` | `{success:false, code:"RUN_TIMEOUT", runId, streamUrl, partial?, truncated}` |
| Cancelled | `200` | `{success:true, status:"cancelled", runId}` |
| Run failed after creation | `200` (synchronous) or visible via stream | `{success:false, status:"failed", runId, error:{code,message}}` |
| Provider/config failure before a run exists | `502` | `{success:false, code, error}` |
| Runtime unavailable | `503` | `{success:false, code, error}` |
| Duplicate client `runId` | `200/202` | the existing run's state; **no second run** |
| Resume of terminal run | `409` | `{code:"RESUME_CONFLICT", status}` |
| Unexpected exception | `500` | `{code:"INTERNAL"}` + `runId` if one exists |

Rules:

- A synchronous wait timeout **never** marks the run failed; it only stops
  waiting. The run keeps its lease and continues.
- `streamUrl` must replay. Add `after`/`Last-Event-ID` support to the Python SSE
  route (the TS route passes it through); verify upstream replay before relying
  on it. If upstream cannot replay, serve from `HarnessEvent` (it is ordered by
  `seq`) instead of only live frames.
- Every run persists `outputPartial` at step boundaries. On deadline/cancel,
  `finalize_partial()` selects the last assistant text, writes it as
  `output` with `outputTruncated: true`, `stopReason: "deadline"|"cancelled"`,
  and a count of completed steps. The UI renders it as a partial answer, never
  as a complete one.
- Idempotency key: `(clientRunId, canonical input digest)`. A retried POST with
  the same key returns the existing run; a different digest with the same runId
  is `409`.

### 3.4 Financial calculation contract

`CalculationResult` is kept and extended with `inputKind`, `outputUnit`,
`outputScale` and `minObservations`. The calculator surface is split into:

1. **Input normalization** (one place): `as_returns(observations, inputKind,
   method)` or `as_levels(observations, inputKind)`. No calculator calls
   `_returns()` on raw input again.
2. **Metric implementations** operate on an explicit, typed series.
3. **Formatting** applies the declared scale exactly once.

Contract matrix (excerpt; the full table is a task deliverable):

| Metric | Input | Output unit | Annualization | Min obs | Notes |
|---|---|---|---|---|---|
| period_change | levels | % | none | 2 | `(end-start)/|start|` |
| cagr | levels | % | geometric | 2 + years | explicit years/frequency |
| annualized_volatility | returns | % | √periods | 3 | sample (n−1) |
| max_drawdown | levels (equity/price) | % | none | 2 | path-dependent |
| sharpe | returns | ratio | √periods | 3 | explicit rf |
| sortino | returns | ratio | √periods | 3 | explicit target |
| value_at_risk | returns | % loss | √horizon | 6 | empirical quantile |
| parametric_var / cvar / monte_carlo_var | returns | % loss | √horizon | 6/5 | method recorded |
| beta / alpha | returns + benchmark | ratio / % | as declared | 3 | date-aligned |
| correlation / covariance | returns | ratio / (return²) | none | 3 | aligned pairs |
| cumulative_return / annualized_return | returns | % | declared | 2 | explicit method |
| rolling_* | returns/levels per metric | per metric | declared | window+1 | window recorded |

Two-phase rollout:

- **Phase A (additive):** add `inputKind` (optional, inferred only when
  unambiguous **and** the inference is recorded in `assumptions`), add the
  contract fields, fix the VaR/vol/Sharpe input bug by normalizing before the
  calculator. Existing outputs keep their units.
- **Phase B (strict):** `inputKind` required; ambiguous input is `400` with the
  expected contract. Remove inference.

Coverage is not limited to `finance_series`: the plan audits `stats/` and
`quant/metrics.py`, and the registry-wide test iterates every registered series
metric.

### 3.5 Market data lineage and the three-store boundary

| Store | Physical location | Owns | Never |
|---|---|---|---|
| JDdS | `jdds.db` (Prisma) | instrument master, latest prices, stored candles, fundamentals | provider cache rows |
| History cache | `agent-memory.db` `MarketBarSeries` | bars fetched from providers, keyed `(symbol, interval, provider, adjusted, eventTime)` | being called "JDdS" |
| Live provider | Yahoo/Stooq/etc. | on-demand quotes/bars | persistence without rights |

New `MarketDataRecord` (response shape, not necessarily a table):

```
store, provider, transport, instrumentId, symbol, market, exchange, currency,
interval, adjusted, asOf, retrievedAt, barCount, coverage{start,end},
quality{status, issues[]}, freshness{label, ageSeconds}, licensed: bool
```

**Resolver** (new module, e.g. `market/resolver.py`): one function
`resolve_series(symbol, interval, window, intent)` with an explicit precedence
policy (`live`, `recent`, `offline`) and a **conflict policy**: never average;
prefer the licensed/official store; if two stores disagree beyond a tolerance,
return both with labels and `quality.status="conflict"`.

**Licensing boundary.** Do not copy provider data into `jdds.db` without a
recorded right to redistribute. The default policy is: cache only within the
provider's terms, keep provider attribution, expose a retention setting, and
make `licensed` explicit in every record. The "offline vault" claim is scoped to
data the operator has the right to store (user-supplied files, licensed feeds,
or jdds rows already governed by the project's data policy).

### 3.6 Budget and efficiency model

Layered budgets, resolved per task profile and clamped by hard caps:

| Budget | Default (chat) | Research/deep | Hard cap | Where enforced |
|---|---|---|---|---|
| Wall clock | 120 s | 600 s | 10,800 s | `RunDeadline` |
| Model calls (steps) | 24 | 32–64 | 240 | `chat_step_budget` / `requested_budget` |
| Tool calls | 24 | 48 | 200 | `maxToolCalls` (already enforced) |
| Cumulative tokens | 1.0 M | 3.0 M | operator | new `maxTokens` |
| Cost | measured | measured | operator | new |
| Per-tool time | 20–30 s | tool-declared | 120 s | `tool_timeout_ms` |
| Retries | policy | policy | 3 | `retry_policy.py` |

Mechanisms:

- **Synthesis reserve:** at 80% of any budget, force a tool-disabled synthesis
  step; at 60%, inject a "conclude now" directive.
- **Evidence sufficiency:** after a successful compute/backtest/read that
  satisfies the question, a step must answer or justify one more call.
- **Semantic duplicate detection:** exact-args dedupe exists; add
  `(tool, normalized args)` with a short window and a refusal that returns the
  earlier result.
- **Progressive discovery:** keep `tool_search`/`tool_invoke`, but rank the
  bound surface by task profile and measure selection accuracy.
- **No arbitrary low caps:** defaults are per profile; an operator can raise
  within hard caps; evaluation tasks declare their own limits.
- **Cost/latency telemetry:** per run and per tool; surfaced next to the answer.

### 3.7 Answer trust and safety

- **Entity resolution gate:** a directive counts as advice only when the target
  resolves to a real instrument (via the instrument master) or is written as
  `$TICKER`. Metric/technical nouns are hard-stopped (`FCFF`, `FCF`, `ADV`,
  `WACC`, `IRR`, `NPV`, `EBITDA`, `CAGR`, `SMA`, …).
- **Precision/recall corpus:** 50 labeled answers (advice vs technical prose).
  Gate: precision 1.0 on the audit set, recall ≥ 0.9 on labeled advice.
- **Do not disable the gate.** The failure mode was over-firing, not the
  existence of the control.
- **Prompt provenance first:** store per-run compiled segment hashes and the
  project-rules/content source. Then reproduce and fix the `no doc change`
  leak. Add a post-generation sanitizer for repository housekeeping lines as
  defence in depth.
- **Response validation:** no dangling fragments; structured blocks validated;
  citations/evidence must match the claims they annotate.

### 3.8 Assurance model

Extend the existing evaluation harness, do not replace it:

- Add a `delivery` dimension (completed / partial / no answer / wrong status)
  and a `run_reliability` dimension (orphans, timeouts, resume success);
  make both **critical** for the release gate.
- Keep the guarded composite, but add a **hard gate** that is independent of
  the weighted score: any P0 failure (fabrication, unsafe trade, unauthorized
  effect, wrong provenance label, lost answer) blocks the release even if the
  average is 99.
- Add the audit corpus as versioned tasks with graders and a committed
  baseline; do not bolt a bespoke script onto CI.
- Test pyramid (next section) and fault injection are release artefacts.

---

## 4. Workstreams (10-part detail)

Every workstream uses the same structure: **Problem · Verified root cause ·
Files · Changes · Dependencies · Migration · Tests · Acceptance · Rollback ·
Effort.** Priorities: **P0** release blocker, **P1** important, **P2**
hardening, **P3** future.

### W0 — Forensics, baseline, and guardrails (P0, 4–5 d)

- **Problem:** restarts orphan runs; the cause is unproven; the audit baseline
  is not reproducible in CI.
- **Root cause:** no boot/shutdown record; runtime supervision is careful but
  unattributable; the 18 audit cases are not tasks.
- **Files:** `service.py` startup/shutdown, `main.py` lifespan,
  `src/lib/harness/python-runtime.ts` (emit supervision decisions),
  `observability/events.py`, `evaluation/tasks.py`, `evaluation/datasets/`.
- **Changes:** `runtime.started/stopped` with pid/port/db/environment/schema/
  activeRuns; `run.reconciled` counts; persist the supervision decision
  (keep/replace/kill) with reason; add the 18 audit cases as tasks (scripted
  model for deterministic cases).
- **Dependencies:** none.
- **Migration:** none.
- **Tests:** boot emits a forensic event; a forced restart records the decision;
  audit tasks load and run offline.
- **Acceptance:** every restart has a recorded reason; the corpus runs in
  `check:all`; baseline stored.
- **Rollback:** events are additive; tasks can be `skip`ped.
- **Effort:** 4–5 d.

### W1 — Lease, fencing, recoverable states, resume (P0, 10–13 d)

- **Problem:** in-flight runs are marked failed and cannot be resumed; a live
  worker can be overwritten; crash windows duplicate effects.
- **Verified root cause:** `fail_orphaned_runs` unconditional update; resume
  refuses `failed`; no lease/fencing; idempotency recorded after execution;
  watchdog uses the preset budget.
- **Files:** `run_lineage.py`, `run_recovery.py`, `service.py`, `graph.py`,
  `run_watchdog.py`, `schemas.py`, `persistence.py`, `migrations.py`,
  `main.py`, `eval_gates/resume.py`, `trade/service.py` (effect integration).
- **Changes:** migration 3.1; `interrupted` state; atomic lease claim; fencing
  predicate on all run writes; heartbeat thread; boot order with environment
  ownership; resume policy per tool class; effect ledger; watchdog rewrite;
  checkpoint atomicity (single `BEGIN IMMEDIATE` for message+cursor) and a
  format/agent/tool-schema version in the payload; checkpoint failure is
  recorded, never silently swallowed.
- **Dependencies:** W0.
- **Migration:** additive columns/tables; no destructive change; backup before
  apply; migration id after `2026-11-11-001`.
- **Tests:** kill -9 during a model call; kill during a tool **after** the
  effect but **before** the record; kill after approval consumption; concurrent
  resume attempts; stale worker write rejected by epoch; watchdog does not kill
  a heartbeating long run; approval-wait is interrupted, not resumed.
- **Acceptance:** 200 sequential + 100 concurrent runs → 0 orphans, 0 duplicate
  irreversible effects, ≥99% checkpointed-run resume success; no run stuck
  running; terminal states immutable.
- **Rollback:** feature flags `HARNESS_RUN_LEASE`, `HARNESS_RESUME_ON_BOOT`;
  additive schema; old code ignores new columns; disable resume and keep
  reconciliation fail-only.
- **Effort:** 10–13 d.

### W2 — Response and timeout lifecycle (P0, 6–8 d)

- **Problem:** deadline returns null/500; 202 loses the answer; clients cannot
  reconnect; partials are discarded.
- **Verified root cause:** outer catch drops `runId`; no partial persistence;
  stream is pass-through without replay.
- **Files:** `chat/route.ts`, `run-service.ts`, `runs/[id]/stream/route.ts`,
  `main.py` stream endpoint, `graph.py` finalize path, DTOs.
- **Changes:** §3.3 contract; `finalize_partial`; `outputTruncated`/`stopReason`;
  SSE replay by `seq`/`Last-Event-ID`; resume route + client reattach; dedupe
  by client runId + input digest; cancel returns terminal state.
- **Dependencies:** W1 (runs must survive the wait).
- **Migration:** none (response fields additive).
- **Tests:** forced slow model; client abort; reload mid-run; 504 body; replay
  from seq 0 and from a cursor; duplicate POST; cancel then resume (409).
- **Acceptance:** 100% of deadline runs return a labelled partial; 0 HTTP 500
  on model timeout; reconnect reconstructs the full event stream.
- **Rollback:** keep the 202 shape; feature-flag partial output; old clients
  ignore new fields.
- **Effort:** 6–8 d.

### W3 — Calculation contract (P0, 7–9 d)

- **Problem:** `finance_series` returns wrong values for return inputs; units
  are implicit across three engines.
- **Verified root cause:** every series calculator differences raw observations;
  no `inputKind`; mixed output scales.
- **Files:** `research/calculations.py`, `calculations_ext.py`,
  `research/web_tools.py`, `research/web_finance.py`, `stats/*`,
  `quant/metrics.py`, tool schemas, prompt.
- **Changes:** §3.4 matrix; central normalization; `inputKind`/`outputUnit`;
  fix the VaR/vol/Sharpe/VaR-family input bug; format once; two-phase
  deprecation; registry-wide contract test.
- **Dependencies:** none (parallel with W1).
- **Migration:** result-shape additive; tool input strict only in Phase B.
- **Tests:** exact audit vectors (Sharpe 1.7224902, Sortino 3.6708310, VaR
  0.02525, CVaR 0.03, MDD −0.020000018); price↔return consistency; property
  tests (scale invariance, sign, monotonicity); every metric declares unit and
  input kind; cross-engine agreement on a shared fixture.
- **Acceptance:** 0 unit defects in a registry sweep; exact golden values;
  existing percent outputs unchanged in Phase A.
- **Rollback:** Phase A is additive; Phase B behind
  `FINANCE_SERIES_STRICT_INPUT`.
- **Effort:** 7–9 d.

### W4 — Market data lineage and resolver (P0/P1, 8–10 d)

- **Problem:** cache inventory was reported as JDdS; no canonical identity;
  no store label; licensing is unaddressed.
- **Verified root cause:** two stores, two vocabularies; `history_catalog`
  reads only `MarketBarSeries`; no resolver.
- **Files:** `market/series_store.py`, new `market/resolver.py`,
  `market/tools.py`, `market/store.py`, `market/quality.py`, `agents.py`,
  `tools.py`, TypeScript data bridge, `docs/data-sources.md`.
- **Changes:** §3.5 record + resolver; `store` on every payload; one bar count
  per identity; `data_inventory` tool; description fixes; licensing gate and
  retention policy; clarify `DATA_GAP` as trading-session gaps.
- **Dependencies:** W3 only for shared fixtures; parallel otherwise.
- **Migration:** none for data; add a store/quality field to tool payloads.
- **Tests:** AAPL identity (jdds 0 vs cache >0, both labelled); conflicting
  stores; stale tail; provider outage; licensing flag; cross-market symbol.
- **Acceptance:** 0 mismatched labels in 50 inventory prompts; resolver returns
  one record per identity; no unlicensed persistence.
- **Rollback:** labels are additive; resolver precedence is configurable;
  `data_inventory` can be unbound.
- **Effort:** 8–10 d (licensing review may block the persistence part).

### W5 — Budgets, loops, and strategy ergonomics (P1, 7–9 d)

- **Problem:** 46–81 calls per question; 0.7–3.6 M tokens; the agent works past
  the answer; strategy creation fights the schema; research sizing can leak
  into saved strategies.
- **Verified root cause:** no total tool cap on `eclipse-agent`, no token/cost
  budget, exact-args-only dedupe, no synthesis gate, 1% default sizing, no
  template.
- **Files:** `graph.py`, `schemas.py`, `quant/strategy.py`, `quant/tools.py`,
  `tool_surface.py`, prompts.
- **Changes:** §3.6; `maxTokens`/cost; synthesis reserve; semantic dedupe;
  evidence-sufficiency gate; template API; sizing separation (research vs saved
  vs live; trade policy untouched); schema hints.
- **Dependencies:** W2 (synthesis needs the response lifecycle), W1 (budgets
  persisted in checkpoints).
- **Migration:** `AgentConfig` additive; no change to persisted strategies.
- **Tests:** budget exhaustion; repeated calls; answer-exists stop; template in
  ≤5 calls; 1% sizing warning; live policy unaffected.
- **Acceptance:** median calls ≤ 8, p95 ≤ 15; no run > 32 without an operator
  budget; tokens p95 ≤ 1.5 M; template path works first try.
- **Rollback:** flags per budget; defaults per profile.
- **Effort:** 7–9 d.

### W6 — Answer trust and safety (P1, 5–7 d)

- **Problem:** two false advisories on arithmetic; an unattributed repository
  line; possible rule leakage.
- **Verified root cause:** unconstrained uppercase token + directive; leak
  source unverified.
- **Files:** `advisory/claims.py`, `advisory/gate.py`, `graph.py` answer seam,
  prompt assembly, answer formatter.
- **Changes:** entity-resolution gate; stop-list; precision/recall corpus;
  prompt-provenance capture; sanitizer; response validation; citation
  consistency check.
- **Dependencies:** W0 (provenance capture); independent otherwise.
- **Migration:** none.
- **Tests:** DCF/ML answers produce 0 advisories; 50-item labeled corpus;
  injection/fabrication regression (existing audit T12/T14); 100 financial
  answers contain 0 repository strings.
- **Acceptance:** precision 1.0, recall ≥ 0.9; no internal text; no dangling
  fragments.
- **Rollback:** sanitizer is additive; the gate stays enabled throughout.
- **Effort:** 5–7 d.

### W7 — Evaluation and release assurance (P0 for staying fixed, 7–9 d)

- **Problem:** the internal gate can report success while delivery, provenance
  and reliability are unmeasured; the audit corpus is not in CI.
- **Verified root cause:** composite weights omit reliability/delivery/
  provenance; only two critical dimensions; limits partially wired.
- **Files:** `evaluation/scoring.py`, `tasks.py`, `runner.py`, `live_gate.py`,
  `report.py`, `datasets/`, `scripts/check-all.js`, `docs/harness/benchmarks.md`.
- **Changes:** §3.8; delivery/reliability dimensions + criticality; hard gate;
  corpus; baseline; fault-injection suites; broker fake adapter.
- **Dependencies:** W1–W6 for the target tests; can be built in parallel with
  the harness skeleton.
- **Migration:** dataset/version only.
- **Tests:** unit, integration, e2e, crash/restart, concurrency, soak, fault
  injection (429/timeout/truncated stream/DB busy/disk full), broker
  crash-after-send, provider outage.
- **Acceptance:** release gate passes only with all G1–G10; a critical failure
  forces FAIL regardless of the composite.
- **Rollback:** the new dimensions can be reported before they are gating
  (one release), then made critical.
- **Effort:** 7–9 d.

### W8 — Re-audit and verdict (P0, 2–3 d)

- Re-run the 18 audit tests unchanged plus the new reliability suite; publish
  deltas. Re-issue the verdict only on G1–G10. No marketing claim changes until
  then.

### 4.9 Task index (implementation view)

| ID | P | Task | Depends | Effort | Primary acceptance |
|---|---|---|---|---|---|
| W0.1 | P0 | Boot/shutdown/supervision forensic events | — | 1.5 d | every restart has a reason |
| W0.2 | P0 | Audit corpus as versioned eval tasks + baseline | — | 2.5 d | corpus in `check:all` |
| W1.1 | P0 | Migration: environment/runtime/epoch + `RunLease`/`RuntimeInstance` | W0.1 | 1.5 d | additive, reversible |
| W1.2 | P0 | Atomic lease claim + heartbeat thread + fencing on writes | W1.1 | 3 d | stale worker write rejected |
| W1.3 | P0 | `interrupted` state + boot recovery ordering + environment ownership | W1.2 | 2 d | checkpointed runs resume |
| W1.4 | P0 | Effect ledger + per-tool idempotency classes + reconciliation | W1.3 | 3 d | crash matrix passes |
| W1.5 | P0 | Watchdog unified with lease and effective budget | W1.2 | 1.5 d | no false stalls |
| W1.6 | P0 | Checkpoint atomicity + payload/version compatibility | W1.1 | 1.5 d | no split commit |
| W2.1 | P0 | `finalize_partial` + `outputTruncated`/`stopReason` | W1.3 | 2 d | deadline returns partial |
| W2.2 | P0 | HTTP contract 200/202/504/409/502/503/500 | W2.1 | 1.5 d | 0×500 on timeout |
| W2.3 | P0 | SSE replay (`after`/`Last-Event-ID`) + front-door resume route + reattach | W1.3 | 2.5 d | reload reconstructs |
| W2.4 | P0 | Request idempotency by client runId + input digest | W2.2 | 1 d | duplicate POST → one run |
| W3.1 | P0 | Audit all three calculation engines + contract matrix | — | 2 d | matrix complete |
| W3.2 | P0 | Central input normalization + `inputKind`/`outputUnit` | W3.1 | 3 d | price/return tests |
| W3.3 | P0 | Fix VaR/vol/Sharpe-family input bug | W3.2 | 1 d | exact golden values |
| W3.4 | P0 | Golden + property + registry sweep tests | W3.2 | 2 d | 0 contract defects |
| W3.5 | P1 | Two-phase strictness + docs | W3.3 | 1 d | deprecation path |
| W4.1 | P0 | `MarketDataRecord` + `store` labels on every payload | — | 2 d | labels present |
| W4.2 | P0 | Cross-store resolver + identity/conflict policy | W4.1 | 3 d | one record per identity |
| W4.3 | P0 | `data_inventory` tool + description fixes | W4.1 | 1.5 d | matches direct SQL |
| W4.4 | P0 | Licensing decision + retention/attribution guard | W4.1 | 1.5 d | no unlicensed persistence |
| W4.5 | P1 | Quality/gap semantics + coverage checks | W4.2 | 1 d | session-gap metric |
| W5.1 | P1 | Token/cost budgets + `maxTokens` | W2.2 | 2 d | budget enforced |
| W5.2 | P1 | Synthesis reserve + evidence-sufficiency gate | W2.1 | 2.5 d | medians hit |
| W5.3 | P1 | Semantic duplicate detection + tool telemetry | W5.2 | 1.5 d | no semantic loops |
| W5.4 | P1 | Strategy template + sizing separation | — | 1.5 d | ≤5-call template |
| W5.5 | P1 | Schema hints + surface ranking | W5.3 | 1 d | fewer validation loops |
| W6.1 | P1 | Entity-resolution advisory gate + stop-list | — | 1.5 d | 0 false positives |
| W6.2 | P1 | Precision/recall corpus | W6.1 | 1 d | recall ≥0.9 |
| W6.3 | P1 | Prompt-provenance capture + leak attribution | W0.1 | 1.5 d | leak source known |
| W6.4 | P1 | Output sanitizer + response validation | W6.3 | 1 d | 0 leaks/fragments |
| W7.1 | P0 | Delivery/reliability dimensions + criticality + hard gate | W0.2 | 2 d | gate fails correctly |
| W7.2 | P0 | Crash/concurrency/soak/fault-injection suites | W1.4 | 3 d | all green |
| W7.3 | P0 | Broker fake-adapter crash-after-send test | W1.4 | 1 d | unknown reconciled |
| W7.4 | P1 | Nightly delivery metrics + baseline refresh | W7.1 | 1.5 d | published |
| W8.1 | P0 | Re-audit + verdict | all | 2 d | G1–G10 |

### 4.10 P2 / P3 backlog (after the release gate)

| ID | P | Item | Why later |
|---|---|---|---|
| P2.1 | P2 | Candle coverage for core symbols **with confirmed rights** | blocked on W4 licensing |
| P2.2 | P2 | Provider failover policy with quality comparison | quality trade-off needs measurement |
| P2.3 | P2 | Cost dashboards + per-tool cost attribution | depends on W5 telemetry |
| P2.4 | P2 | Restore drill automation in `doctor.js` | after G9 baseline |
| P3.1 | P3 | Cross-machine resume (shared run store) | out of scope for a local install |
| P3.2 | P3 | Multi-tenant isolation | only if hosted; auth/tenancy first |
| P3.3 | P3 | Automatic model failover on provider outage | changes answer provenance; needs operator policy |


---

## 5. Dependency graph

```
W0 forensics/baseline
 ├── W1 lease/resume/effects ──► W2 response lifecycle ──► W5 budgets
 │                                    │
 │                                    └──────────────► W7 assurance ──► W8 re-audit
 ├── W3 calculation contract ─────────────────────────► W7
 ├── W4 data provenance ──────────────────────────────► W7
 └── W6 answer trust ─────────────────────────────────► W7

Parallel-safe: W3 + W4 (different files); W0 + W7 skeleton.
Sequential: W1 before W2 (resume/lease); W2 before W5 (synthesis gate);
W1/W2 before W7 crash tests; all before W8.
```

---

## 6. Testing and acceptance strategy

### 6.1 Test pyramid

| Layer | What | Runtime | Gate |
|---|---|---|---|
| Unit | contracts, calculators, claim rules, lease SQL, state transitions | seconds | every commit |
| Integration | scripted-model graph runs, checkpoint/resume, effect ledger, timeouts | minutes | every PR |
| End-to-end | real runtime + fake provider + real HTTP front door | minutes | nightly |
| Crash/restart | kill -9 at every boundary (model, tool before/after effect), boot recovery | minutes | nightly |
| Concurrency | 8–16 simultaneous runs; shared DB; lease contention | minutes | nightly/release |
| Soak | 100–200 runs over hours; memory/token/latency | hours | release |
| Fault injection | provider 429/timeout/half-stream, DB locked, disk full, broker timeout | minutes | release |
| Broker safety | fake MT5 adapter: reject, partial fill, duplicate, crash-after-send | minutes | release |
| Live eval | audit corpus on a pinned model | tens of minutes | release |

### 6.2 Release gates

| Gate | Threshold |
|---|---|
| G1 Run survival | 0 orphans in 200 sequential + 100 concurrent; every run terminal with output or explicit no-output |
| G2 Effect safety | 0 duplicate irreversible effects across the crash matrix; 100% `unknown` reconciled or surfaced |
| G3 Deadline delivery | 100% of forced-timeout runs return a labelled partial; 0 HTTP 500; p95 < 60 s |
| G4 Calculation contract | exact golden values; registry sweep 0 unit/input defects |
| G5 Provenance | 0 mismatched store labels; one identity→one bar count; licensing flag present |
| G6 Efficiency | median calls ≤ 8, p95 ≤ 15; tokens p95 ≤ 1.5 M; cost measured |
| G7 Answer trust | advisory precision 1.0 / recall ≥ 0.9; 0 internal-rule strings; 0 dangling fragments |
| G8 Evaluation | task_success ≥ 0.95, delivery ≥ 0.99, safety 1.0, provenance 1.0, no dimension unmeasured |
| G9 Operations | migration backup/restore drill passes; schema version reported; config validation fails closed |
| G10 Re-audit | composite ≥ 90 and no critical failure; no test below 70 on delivery |

The composite is never the only gate: G2/G4/G5/G7/G8 are hard failures even if
the average is high.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Resume re-runs an irreversible effect | Medium | Critical | Effect ledger, at-most-once class, `unknown` + reconciliation; crash-matrix tests |
| Lease clock skew / heartbeat starvation | Medium | High | Wall-clock TTL with monotonic guard; heartbeat thread; 3-beat tolerance |
| Stale worker writes after lease loss | Medium | High | Fencing epoch on every write; rowcount check aborts |
| Two runtimes share the DB | Medium | High | `RuntimeInstance` ownership + environment check; never reconcile another env |
| Watchdog kills a long, healthy run | Medium | High | Effective-budget threshold, lease heartbeat, active-tool activity |
| Checkpoint/message split commit | Medium | Medium | One transaction; tolerate older cursor on read; versioned payload |
| Migration locks / partial apply | Low | High | `BEGIN IMMEDIATE`, rollback on error, pre-migration backup, doctor check |
| Strict `inputKind` breaks callers | Medium | Medium | Two-phase deprecation, inference with recorded assumption in Phase A |
| Provider/model unpinned on resume | Medium | High | Persist provider/model/tool-schema/agent versions; refuse or require operator switch |
| Token budget truncates useful work | Medium | Medium | Per-profile budgets, synthesis reserve, explicit truncation label |
| Advisory gate weakens safety | Low | High | Precision/recall corpus; never disable; review any rule change |
| Licensing violation from persistence | Medium | High | Rights check before any store; default cache-only; `licensed` flag |
| Secrets in persisted tool args | Low | High | Redaction audit + allowlist; never replay secrets in resume prompts |
| Evaluation overfits the 18 cases | Medium | Medium | Held-out split, versioned tasks, nightly live tier, significance |

---

## 8. Rollback strategy

1. All schema changes are additive; no destructive migration. Take a
   pre-migration backup (`scripts/backup.sh`) and verify restore on a copy.
2. Feature flags, default-off for one release where the behaviour changes:
   `HARNESS_RUN_LEASE`, `HARNESS_RESUME_ON_BOOT`, `HARNESS_PARTIAL_OUTPUT`,
   `FINANCE_SERIES_STRICT_INPUT`, `MARKET_RESOLVER_PRECEDENCE`.
3. Rollback per wave: disable the flag, restart the runtime, keep the additive
   columns (old code ignores them), re-run the prior baseline.
4. Data rollback: never restore `jdds.db` from a runtime backup automatically;
   it is a seed snapshot. Restore `agent-memory.db` only from the
   pre-migration backup after stopping every runtime.
5. Do not roll back the audit corpus or evidence; it is append-only.

---

## 9. Revised estimates (solo, realistic)

| Wave | Workstreams | Engineer-days |
|---|---|---:|
| 0 | W0 forensics + corpus skeleton | 4–5 |
| 1 | W1 lease/resume/effects | 10–13 |
| 2 | W2 response lifecycle | 6–8 |
| 3 | W3 calculation contract | 7–9 |
| 4 | W4 data provenance | 8–10 |
| 5 | W5 budgets/ergonomics | 7–9 |
| 6 | W6 answer trust | 5–7 |
| 7 | W7 assurance | 7–9 |
| 8 | W8 re-audit | 2–3 |
| **Total** | | **56–73 days (~11–15 weeks solo)** |

With two engineers (runtime track W1/W2/W5; contracts track W3/W4/W6, then W7
together): **~6–8 weeks**, plus **25% contingency** for migration and fault
injection. Rev 1's "4 weeks" was optimistic by roughly 2× because it treated
resume as wiring and omitted the effect ledger, watchdog, licensing and
evaluation work.

---

## 10. Final release-readiness checklist

- [ ] G1–G10 pass on a clean tree; evidence archived.
- [ ] Boot/shutdown/supervision forensics exist and explain every restart.
- [ ] Lease + fencing proven under a stale-worker test; no double writes.
- [ ] Effect ledger proven across the full crash matrix; irreversible effects
      are at-most-once with reconciliation.
- [ ] `interrupted` is distinct from `failed`; resume policy is per tool class;
      approvals never auto-resume.
- [ ] Partial answers survive deadline/cancel/restart; clients reconnect.
- [ ] Calculation contract is explicit for all three engines; golden + property
      + registry tests pass; percent outputs unchanged.
- [ ] Store labels are unambiguous; one identity→one record; licensing decided.
- [ ] Budgets are enforced (time, calls, tokens, cost) with a synthesis reserve.
- [ ] Advisory precision/recall gate passes without disabling the control.
- [ ] Prompt provenance is captured; the repository-line leak is attributed and
      fixed, or documented as unresolved with a sanitizer in place.
- [ ] Evaluation reports delivery/reliability/provenance and fails closed on a
      critical failure.
- [ ] Migration backup/restore and config validation are exercised.
- [ ] Live trading remains disabled; broker safety tests pass on a fake adapter.
- [ ] Documentation and CHANGELOG updated; public claims match the limitations.

---

## 11. Open decisions (owner)

1. Resume policy for an irreversible effect in `unknown`: automatic
   reconciliation only, or an operator decision card? (Recommend operator for
   broker/MCP; automatic inspect-only for git/files.)
2. `interrupted` retention: resume on boot automatically (bounded), or show a
   "resume" action only? (Recommend automatic for read/compute runs, offered
   for effect runs.)
3. Licensing: which feeds may be persisted in `jdds.db`, and under what
   attribution/retention? This blocks the persistence half of W4.
4. Token/cost budget defaults per profile (chat/research/backtest).
5. Whether the release stays loopback-only. If not, auth/tenancy becomes a P0
   prerequisite, not a follow-up.
