---
title: Round 5 - Core Integrity (a world-class general harness)
status: In progress (C0-C6 shipped 2026-11-11; C7-C9 open)
last-verified: 2026-11-11
depends_on: rounds 1-4, docs/harness/architecture.md, docs/harness/execution-fabric.md
---

# Round 5 - Core Integrity

**The one sentence.** Rounds 1-4 made Eclipse *broad*; Round 5 makes it
*trustworthy*, because a harness that can do anything is only useful if it
cannot silently do the wrong thing, lose a run, or lie about what happened.

**Why this round exists.** A code-level audit on 2026-11-11 against OpenCode
v2.2.7 found that Eclipse's capability surface is genuinely world-class, while
its *core loop* still has gaps that no amount of new tools can compensate for.
Two of them contradict the Round 4 scorecard (Loop 9.5, Ops 4.0):

- `graph.py:725` calls `model_stream.ainvoke_streaming` directly, so
  `ModelRuntime.invoke`'s retry/backoff/fallback/circuit breaker is **never used
  on the main agent path**. One transient 429 ends a 24-step run.
- `service.py:1343` (`run`, the foreground path) never registers in
  `service._active` (that only happens at `service.py:1792`, the background
  path), so `stream_run` replays and closes while the run is still executing,
  and `cancel()` finds no task.

Those are not polish. They are the difference between a demo and a harness.

---

## 0. The verdict

| Layer | State | Evidence |
|---|---|---|
| Capability breadth (tools, finance, code, memory, skills) | **World-class** | ~950 registered tools, 70 subsystems, 422k Python lines |
| Governance intent (approvals, claims, honesty) | **World-class** | digest-bound approvals, `HandleVerifier`, `UNAVAILABLE`, release gates |
| Core loop correctness | **Not world-class** | no retry on the hot path, per-call timeout mislabeled as run timeout, foreground SSE/cancel inert |
| Execution architecture | **Over-built** | 4 schedulers / 4 state machines / 4 retry vocabularies |
| Context and tool economics | **Adequate, not competitive** | char budgets, 950-tool surface, compaction default OFF |
| Safety envelope | **Strong policy, weak enforcement** | excellent authorization seam, no OS sandbox, single-tenant default |
| Measurement | **Claims outrun evidence** | scorecard dimensions not backed by runnable gates |

**This round is not a rewrite.** It is one loop, one scheduler, one event log,
one tool contract, one policy seam, plus the tests that prove it.

### Implementation status (2026-11-11)

| Workstream | Status | Shipped |
|---|---|---|
| C0 evidence reset | **Done** | `scripts/harness-scorecard.js`, `docs/harness/scorecard.json`, generated `docs/harness/scorecard.md`, strict gate (`npm run harness:scorecard:gate`) |
| C1 StepExecutor | **Done (core)** | `retry_policy.py`, `step.py`, graph deadline + `model.retry`, `RUN_TIMEOUT` |
| C2 one execution plane | **Done** | foreground registration + cancel/SSE parity + `HARNESS_MAX_CONCURRENT_RUNS`; `execution_plane.py` vocabulary; `migrations.py` ledger; `RunMessage` checkpoint cursor; Fabric `task` worker + scheduler submission; `execution_log.py` canonical log across run/fabric/graph/task/orchestration; `RunScope`/`RunSpec` replace the 45-kwarg `build_graph`. |
| C3 context/tool economics | **Done** | measured model-window budgeting + provider usage (pre-existing); always-on deterministic compaction (pre-existing); artifact handles + `read_tool_output` pager; `tool_search`/`tool_invoke`; opt-in `HARNESS_LAZY_TOOLS`; sandboxed read-only `tool_code` (`HARNESS_CODE_MODE=1`). |
| C4 plan/verify/evidence | **Done** | goal/plan/step view; `EvidenceClaim`/`Handle` ledger; verifier registry (finance/citation/code/artifact); answer seam; bounded evidence replan; plan cursor in checkpoint; outcome blocks. |
| C5 one agent fabric | **Done** | `spawn` over Fabric `agent` jobs; depth/fanout/token caps; shared root-scoped blackboard; child evidence in the parent ledger; deterministic synthesis; A2A/team task execution routed through `spawn` (`tasks/spawn_bridge.py`). |
| C6 safety envelope | **Shipped** | auth-by-default outside loopback; `SandboxProfile` resolver + gateway/executor enforcement (terminal, background, computer); native bubblewrap/Seatbelt/AppContainer; per-call effect tokens; escape suite; Ed25519/HMAC plugin install signing + review. Follow-up: human review UI. |
| C7-C9 | **Not started** | - |

The remainder is the plan below; nothing in it is claimed as done.

---

## 1. What is actually lacking

Severity: **P0** = correctness/trust bug; **P1** = blocks "world-class";
**P2** = needed to ship and stay good.

### 1.1 P0 - the loop can fail or lie

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| L1 | No retry on the agent's model call | `graph.py:725` bypasses `ModelRuntime.invoke`; `model_stream.py` has no retry | one 429/500/disconnect kills the run |
| L2 | Run timeout is really a per-call timeout | `graph.py:223,241` (`HARD_RUN_TIMEOUT_S` applied per call) | a 24-step run can occupy 24 x 120 s; only the silence watchdog notices |
| L3 | Foreground runs are invisible to stream/cancel | `service.py:1343` vs `service.py:1792` | SSE closes mid-run; cancel is a no-op |
| L4 | No admission control | `_active` is an unbounded dict; no run semaphore | burst of background runs = unbounded event-loop tasks on one SQLite writer |
| L5 | Process-wide mutable run state | `service.py:1350-1352` rebinds `market_gateway._bridge` per run; `ToolRegistry._active_ctx` | two concurrent runs can cross-wire transports/contexts |
| L6 | Cancellation has no single contract | async tasks, threads, subprocesses, approvals each cancel differently | "stop" can leave a child process or a half-written side effect |
| L7 | Checkpoints are lossy on long runs | `checkpoint_io.py`: 60 messages x 12,000 chars | a resumed 200-step run loses its early evidence |
| L8 | Error vocabularies do not compose | `PROVIDER_*`, `ErrorClass`, `JobState`, `NodeStatus`, `TaskStatus`, `RunStatus` | recovery code cannot be reused; "what failed" is per-subsystem |

### 1.2 P1 - architecture and economics

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| A1 | Four execution planes | `graph.py`, `graph_runtime/executor.py`, `orchestration/engine.py`, `fabric/manager.py` (+ `tasks/`, `automation/`) | ~4,000 lines of overlapping scheduler semantics; four "resume" stories |
| A2 | God objects | `ToolContext` ~100 fields (and `project_store` declared twice, `tools.py:322`); `build_graph` ~45 kwargs | silent-`None` bugs, high onboarding cost |
| A3 | 380+ tables, emergent migrations | 415 `CREATE TABLE` statements across `agent-memory.db` + `eclipse-memory.db` | schema coherence is emergent; no single migration ledger |
| A4 | Duplicate model construction/invocation | `models.build_chat_model` vs `model_runtime.build` vs `model_stream` | the runtime's best features are dormant on the main path |
| A5 | 950-tool surface bound every run | `surface.py`; lazy loading is still a future-tense comment | context bloat, schema drift, slow cold start |
| A6 | Context budget is char-based; compaction default OFF | `context_budget.py`, `compaction.py` | token overflow is estimated, not measured; long sessions degrade |
| A7 | Large tool outputs are truncated, not offloaded | `MAX_TOOL_RESULT_CHARS = 24_000` | the model loses data it may need; no handle to re-read |
| A8 | Four context-reduction paths | history bound, compaction, dropped-context mining, profile snapshot | inconsistent behavior, four places to fix |
| A9 | Four agent/task planes | `delegation`, `a2a`, `team`, `fabric` | no single subagent contract; duplicated budget/approval logic |
| A10 | Global capabilities are not negotiated | no harness/protocol version handshake between TS and Python | a stale front door can call a moved contract |

### 1.3 P1 - safety and operations

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| S1 | Single-tenant by default | `deps.py`: loopback or `CRON_SECRET`; `deployment_guard` only warns | unsafe the moment it binds a network |
| S2 | No OS-level sandbox for shell/terminal/computer | approvals are the only containment; `code/sandbox.py` is the exception | a permitted `shell` is host-level |
| S3 | Plugins/skills execute in-process | plugin/skill loaders import Python | a bad plugin is a process compromise |
| S4 | Egress policy exists but is not the only path | `security/network.py` vs direct transport use | bypasses are possible by construction |
| S5 | SLOs are not enforced | observability exists; no error budget / alert gate | regressions are discovered by users |

### 1.4 P2 - measurement and delivery

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| M1 | Scorecard claims are not evidence-gated | Loop 9.5 claimed despite L1/L3 | planning on a false baseline |
| M2 | No external suite | no SWE-bench/GAIA/tau-bench adapter | "world-class" is self-asserted |
| M3 | Offline eval replays scripts | `evaluation/runner.py` `ScriptedAgentInvoker` | measures the runtime, not the agent |
| M4 | No published release | Round 4 O1/O3/O6: not landed, no tag, no PyPI | cannot be adopted or compared |
| M5 | Harness architecture docs are fragmented | `architecture.md`, `execution-fabric.md`, `failure-recovery.md`, 22 phase files | invariants live in comments, not one place |

---

## 2. The standard: what "world-class" means here

| Property | Definition | Measured by |
|---|---|---|
| **Exactly-once** | every run reaches exactly one terminal state; every side effect executes at most once | crash matrix, idempotency ledger |
| **Invisible resilience** | transient provider/tool failures are retried, not surfaced | fault-injection suite |
| **Bounded** | steps, tokens, cost, wall clock and concurrency all have hard ceilings | budget tests |
| **Honest** | unavailable data, truncation and failure are labeled, never fabricated | finance/honesty suites |
| **Composable** | one tool contract; one subagent contract; one job contract | contract tests |
| **Isolated** | effectful work runs under an explicit capability + sandbox profile | escape suite |
| **Measurable** | every scorecard number maps to a runnable gate | scorecard script |
| **Portable** | any model, any MCP server, any host; honest `Unavailable` | provider matrix |

**Anti-goal:** "can do anything" does not mean "no limits". A world-class harness
is one where the limits are explicit, enforced, and rarely hit in normal work.

---

## 3. Target architecture

```
 Next.js front door
 (auth, settings vault, JDdS bridge, UI)
        |
        |  signed RunSpec + SSE
        v
 Harness API  (ONE admission path, versioned)
        |
 ExecutionRegistry  (foreground AND background)
        |
 Scheduler / Fabric  (ONE Job state machine, leases, budgets)
        |
 StepExecutor  (StepOutcome algebra: completed | retry | compacted | limit | failed)
        |
 RunScope  (config, policy, sinks, budget, workspace - composed, not 100 fields)
   |-- ModelGateway   (routing + retry + usage, ONE path)
   |-- ToolSurface    (lazy, namespaced, ONE execute seam)
   |-- ContextManager (measured tokens, compaction, artifact handles)
   |-- Verifier       (evidence ledger, domain verifiers)
   |-- SandboxRouter  (process/OS isolation profiles)
        |
 Append-only event log  -->  projections (runs, messages, checkpoints, cost)
```

**The five "ones" (non-negotiable):**

1. One loop: `StepExecutor` is the only place a model is called for a run.
2. One scheduler: `fabric` is the only durable executor; everything else compiles
   to a job.
3. One event log: all durable facts append once; projections are derived.
4. One tool contract: `ToolRegistry.execute` remains the single enforcement seam.
5. One policy seam: `security/gateway.py` is the only authorization decision.

---

## 4. Workstreams

Each workstream is independently shippable and ends with a runnable gate.

### C0 - Evidence reset and a safety net (P0, 4-5 days)

**Problem.** The scorecard says Loop 9.5 while L1/L3 are true.

**Change.**
- `scripts/harness-scorecard.js` reads test IDs + measurements and emits
  `docs/harness/scorecard.md`; a dimension with no evidence is `UNMEASURED`,
  not a number.
- `python/tests/faults/` - a scripted fake provider (429, 500, disconnect
  mid-stream, hang, malformed tool call) and a crash injector.
- Golden traces: 10 canonical runs recorded as event sequences.

**Acceptance.** `npm run harness:scorecard` exits non-zero if any dimension
lacks evidence; fault fixtures prove the current failures (red) before C1 fixes
them (green).

### C1 - StepExecutor: one model call, one retry policy (P0, 8-10 days)

**Problem.** L1, L2, L8, A4.

**Change.**
- New `python/harness/step.py` (shipped):
  `StepOutcome` is still the target algebra; today the module returns the model
  response or re-raises the original exception, which keeps the graph's existing
  overflow/provider classification authoritative.
- New `python/harness/retry_policy.py` (shipped): one
  `RetryPolicy(attempts, base_s, cap_s, jitter, max_elapsed_s)` used by the model
  path; tool/job adoption is still to do.
- Route streaming through `ModelGateway.stream_step()`; keep transient deltas,
  record usage/attempt, classify errors once.
- Separate `model_call_timeout_s` from `run_deadline_s`; enforce the deadline
  in the loop and at every tool boundary.
- `verify_repair` and `replan` become `StepOutcome` consumers, not parallel
  control flow.

**Acceptance.** Fault matrix rows 1-5 pass; a run survives 3 consecutive 429s;
`run_deadline_s` terminates a 100-step run on time; usage recorded per attempt.

### C2 - One durable execution plane (P0, 15-20 days)

**Problem.** L3-L7, A1-A3, A8.

**Change.**
- `ExecutionRegistry`: every run (foreground and background) registers a task;
  `stream` and `cancel` read from it; admission semaphore per provider + global.
  **Shipped:** both paths register in `service._active`, `run()` ends its stream
  on completion, and `HARNESS_MAX_CONCURRENT_RUNS` adds the global semaphore.
  Per-provider slots remain a later refinement; the Fabric job row is the durable
  identity of the same work.
- `fabric` becomes the substrate. `JobKind` = `run | graph | task | automation |
  delegate`; `graph_runtime`, `orchestration` and `tasks` become adapters that
  compile to jobs. Retire duplicate state machines behind compatibility shims.
  **Shipped:** a `task` job + worker, task-scheduler submission with inline
  fallback, graph dispatch (already), and `submit_dag` for orchestration. The
  legacy claim/producer loops remain; they no longer own a second execution path.
- `RunScope` + `RunSpec` replace `build_graph(**45)` and most of `ToolContext`;
  keep a `ToolContext` adapter until all tools migrate. **Shipped:** `RunScope` +
  `RunSpec` in `run_scope.py`, `build_graph(spec, scope)`, and a contract test
  pinning the two-parameter signature. `ToolContext` remains the tool-facing
  context; migrating its fields is a separate tool refactor.
- One append-only event log + projections; checkpoints become cursors/pointers
  into the message store (no 60-message truncation).
  **Shipped:** the message store + cursor (`RunMessage`,
  `RunCheckpoint.payload.messageSeq`, legacy fallback), and the one append-only
  `ExecutionEvent` log written by run/fabric/graph/task/orchestration (legacy
  tables stay as projections). **Still to do:** migrating UI/observability
  readers to the canonical log.
- One migration ledger: `HarnessMigration` table + ordered SQL files; both DBs
  share the runner. **Shipped:** `harness/migrations.py`, used by `RunLineage`,
  the execution log and the run-message cursor; **still to do:** moving the
  legacy per-subsystem DDL onto it.

**Acceptance.** kill -9 at each state (queued, running, waiting approval,
writing final) resumes with no duplicate side effect; one state-machine test
covers every job kind; `stream` works for foreground runs; cancel p95 < 2 s;
concurrent runs never share a bridge/context.

### C3 - Context and tool economics (P1, 12-15 days)

**Problem.** A5-A8; costs grow with surface, not with task.

**Change.**
- Token accounting from provider usage; tokenizer fallback; `ContextPlan`
  (system, pinned facts, rolling summary, recent turns, artifact handles).
  **Done:** provider usage is persisted per run, the budget measures the actual
  request against the model's declared window, and the char estimator is the
  fallback when no window is known. Artifact handles are the `ToolOutput` pager.
- Compaction always on: deterministic skeleton + rolling narrative; pin
  decisions, claims and tool results; never compact approvals/evidence.
  **Done:** the deterministic skeleton is always built; the model narrative is
  additive and fails closed.
- Artifact offload: tool results above a threshold become an artifact with
  `handle`, `preview`, `digest`; a `read_artifact` tool re-reads on demand.
  **Shipped:** `ToolOutput` + `output_id` + `read_tool_output` (run-scoped,
  paged); the older 24k truncation stays as the fail-open fallback.
- Tool surface v2: `tool_search` + namespaces + per-agent curated sets; a hard
  schema-token budget that *refuses* rather than silently overflows.
  **Shipped:** `tool_search`, read-only `tool_invoke`, and the opt-in
  `HARNESS_LAZY_TOOLS` surface. **Still to do:** namespaces and the schema-token
  budget.
- Code mode: one `execute` tool running confined Python over the tool catalog
  (reuse the analysis sandbox) so the model composes tools without extra turns.
  **Shipped:** `tool_code` (`HARNESS_CODE_MODE=1`) runs a Python child through
  `code/sandbox.py` with a JSON-lines bridge; read-only tools only, 20 calls,
  bounded timeout, fresh temp cwd, no network, scrubbed env, named refusal when
  isolation is unavailable.

**Acceptance.** p50 context tokens down >= 40% at equal task success; visible
tool definitions <= 50 per run with no loss of reachable capability; prompt
cache hit rate not worse; no run exceeds the measured window.

### C4 - Plan, act, verify, remember (P1, 10-12 days)

**Problem.** The loop answers well but does not *finish* long work or prove it.

**Change.**
- Durable `Goal` / `Plan` / `Step` entities (on the one event log).
- `EvidenceLedger`: every claim carries a handle (`path | run_id |
  artifact_digest | record_id | citation`); verifiers reject unsupported claims.
- Generic `Verifier` registry: code (tests/diff), finance (calculation +
  provenance), research (citation + freshness), artifact (schema).
- `replan` enabled by default with a bounded budget; `verify_repair` generalized
  past code.
- Todos + progress + resumable multi-hour goals.

**Acceptance.** a 2-hour task survives a restart and continues from its plan; a
fabricated claim fails the ledger gate; replan never widens authority.

**Shipped.** `harness/goals/`: Goal/Plan/Step view, `EvidenceClaim` + handle
ledger, deterministic verifier registry (finance/citation/code/artifact),
answer-seam recording/disclosure, bounded evidence replan (max 2, supersedes the
failed draft and keeps its tool evidence), plan cursor in the checkpoint, and
`goal`/`evidence` blocks in the run outcome. The plan steps ARE the todo/progress
list; no separate todo surface was added. Kill/resume and two-run continuation
are covered by tests.

### C5 - One agent fabric (P1, 8-10 days)

**Problem.** A9: four ways to spawn work, none shared.

**Change.**
- One `spawn` primitive on fabric jobs: depth, budget, allowlist, actor
  intersection (never inherit `operator`), timeout.
- Shared blackboard + artifact bus; child results return claims + handles.
- Deterministic synthesis (dedupe, conflict resolution, provenance), not "ask a
  model to merge".
- Keep A2A wire compatibility as an adapter, not a second runtime.

**Acceptance.** 8-child fanout with exact budget accounting; no operator
inheritance; conflicting child claims surface as a conflict, never a merge.

**Shipped (core).** `harness/spawn/`: `SpawnSpec`/`ChildOutcome`, Fabric `agent`
jobs with `parentRunId` + budget (`maxSteps`/`runTimeoutMs`), depth 2 / fanout 8
/ 120k total token caps with `allocated = used + returned` reconciliation,
`BoardStore` (one board per root run, 200 entries /
200k chars), child evidence copied into the parent ledger, deterministic
synthesis + conflicts, `spawn`/`board_*` tools and `spawn.*` events. A2A/team
task execution routes through `spawn` (`tasks/spawn_bridge.py`) when the Fabric
is available, with an inline fallback; `delegate` remains the legacy entry point.

### C6 - Safety envelope (P0, 12-15 days)

**Problem.** S1-S4.

**Change.**
- Auth required by default for any non-loopback bind; signed identity from the
  front door; per-tenant stores + rate limits (much exists in `security/`).
- `SandboxProfile` = `read-only | workspace-write | network-allowlist | full`;
  enforce with Windows Job Objects/AppContainer, Linux namespaces/bubblewrap,
  macOS seatbelt; honest `Unavailable` when the host cannot enforce.
- Capability tokens per effectful call; the egress proxy is the only network
  path; secrets broker for tool credentials.
- Plugin/skill host isolation: separate process, manifest, permissions,
  signature/review at install.

**Acceptance.** escape suite (path traversal, env exfil, fork bomb, egress)
passes; zero effectful actions without a capability token; audit chain verifies.

**Shipped (core, 2026-11-11).**
- Auth posture: required by default for a non-loopback bind or a production
  build; loopback `npm run dev` stays zero-config; a non-loopback request without
  a signed `X-Harness-Identity` resolves ANONYMOUS (`test_c6_auth.py`).
- `security/profiles.py`: `read-only | workspace-write | network-allowlist |
  full`, with `resolve_profile()` returning `enforceable=False` + the exact
  `missing` guarantees when the host cannot keep the promise; exact-or-wildcard
  egress allowlist; `path_within()` traversal check; `GET /sandbox` reports each
  profile's enforceability. A configured profile the host cannot enforce refuses
  an execution action at the gateway (`security.sandbox.profile_blocked`).
- `security/effect_tokens.py`: HMAC tokens bound to
  `(runId, tool, argsDigest, tenant, expiry)`, minted by the security authorizer
  on ALLOW and verified by the tool executor before the handler runs. Modes
  `off | shadow (default) | enforce`; enforce mode covers missing, expired,
  replayed, cross-run and widened-argument tokens (`test_c6_effect_tokens.py`).
- Escape suite: `test_c6_escape.py` covers path traversal/mount scope, env
  exfiltration, fork-bomb pid/memory bounds, and raw egress without a proxy.
- Executor wiring: `terminal_run` (foreground), background process spawn and
  `computer_use` call `executor_guard()` and refuse an unenforceable configured
  profile; proven by `test_c6_executor_profile.py`.
- Native backends: `NativeSandbox` with Linux bubblewrap (`--ro-bind`/`--bind`,
  `--unshare-net`) and macOS Seatbelt (deny writes/network) argv/policy builders,
  selected before Local. `WindowsAppContainerSandbox` is the opt-in Windows
  primitive (package SID, no network capability, workspace-only ACL); the live
  smoke proves a command runs and cannot read outside the granted workspace
  (`test_c6_native.py`, `test_c6_appcontainer_live.py`).
- Plugin install signing/review: `plugins/signing.py` + `plugins/ed25519.py`,
  Ed25519 publisher keys or operator HMAC over manifest + digest, `plugin.sig`
  excluded from the content digest, `HARNESS_PLUGIN_REQUIRE_SIGNATURE` /
  `HARNESS_PLUGIN_REQUIRE_REVIEW`, install + update rollback on refusal
  (`test_c6_plugin_signing.py`, RFC 8032 vector included).

**Remaining for C6 (honest).**
- The review gate is the explicit operator acknowledgment (`operator=True`), not
  a human review UI.

### C7 - Observability that bites (P1, 5 days)

**Problem.** S5.

**Change.** OTel spans per run/step/tool; RED/USE metrics; cost per run;
failure taxonomy from the unified error model; SLOs with error budgets and
release gates (terminal correctness, p95 latency, resume time, orphan rate).

**Acceptance.** a dashboard per SLO; CI fails a release that regresses a budget.

### C8 - Evaluation as a gate (P1, 10 days)

**Problem.** M1-M3.

**Change.** Conformance suite = fault matrix + golden traces + contract tests;
external adapters (SWE-bench Lite subset, GAIA, tau-bench, FinanceBench);
internal finance QA; the scorecard is regenerated from runs, never typed.

**Acceptance.** every dimension has a gate; two consecutive releases publish
comparable numbers; the offline tier exercises the real agent, not a script.

### C9 - Ship it (P2, 8 days)

**Problem.** M4, M5.

**Change.** Land, tag, PyPI package, versioned harness API + plugin SDK, ACP;
one authoritative `docs/harness/core-architecture.md` with the five "ones" and
the invariants; ADR-H348 onward.

**Acceptance.** `pip install` + `npm install` both work; an external user can
run the conformance suite against their install.

---

## 5. Sequencing

| Wave | Workstreams | Gate |
|---|---|---|
| 0 | C0 | scorecard is evidence-backed; faults are reproducible |
| 1 | C1, then C2 | loop survives faults; one scheduler; foreground stream/cancel |
| 2 | C3, C7 | context -40%; SLOs live |
| 3 | C4, C5 | long-horizon resume; one agent contract |
| 4 | C6, C8 | escape suite; external numbers |
| 5 | C9 | tag + package + docs |

**Effort.** ~95-120 engineer-days. Solo: 4-5 months. Two engineers: ~10-12
weeks. Waves 0-1 alone (2-3 weeks solo) remove the P0 trust bugs and are worth
doing even if nothing else ships.

**Critical path.** C0 -> C1 -> C2 -> C3 -> C4 -> C6 -> C8 -> C9. C5 and C7 can
run in parallel with C4/C6.

---

## 6. Definition of done (measurable)

| Property | Metric | Target |
|---|---|---|
| Terminal correctness | runs ending in exactly one terminal state | 99.9%, zero orphans |
| Side effects | duplicate executions of one tool call | 0 |
| Transient recovery | runs succeeding after injected 429/500/disconnect | >= 95% |
| Crash resume | p95 time from restart to continued run | < 10 s |
| Cancellation | p95 time from cancel to stopped | < 2 s |
| Deadline | runs exceeding `run_deadline_s` | 0 |
| Context | p50 prompt tokens per completed task | -40% |
| Tool surface | visible tool definitions per run | <= 50 |
| Cost | cost per completed task | -30% |
| Safety | effectful calls without capability token | 0 |
| Sandbox | escape-suite failures | 0 |
| Honesty | fabricated claims surviving the ledger | 0 |
| Measurement | scorecard dimensions with a runnable gate | 100% |

---

## 7. Test plan

### 7.1 Fault matrix (must be automated)

| # | Fault | Invariant |
|---|---|---|
| 1 | provider 429 | retried with backoff, same step, no duplicate message |
| 2 | provider 500 | retried, then honest failure |
| 3 | disconnect mid-stream | assembled content is either complete or discarded, never half |
| 4 | provider hangs | hard deadline, task cancelled, run terminal |
| 5 | malformed tool call | one repair attempt, then model-visible error |
| 6 | tool raises | `ToolResult` error, run continues |
| 7 | tool hangs | bounded, child process killed |
| 8 | 24k+ tool output | artifact handle + preview, no silent loss |
| 9 | SQLite busy | bounded retry, one writer |
| 10 | kill -9 at each state | resume, no duplicate side effect |
| 11 | SSE disconnect | reconnect replays then tails |
| 12 | cancel at model/tool/approval | one terminal `cancelled` |
| 13 | approval expiry | denial, not hang |
| 14 | context overflow | compact or fail honestly, never truncate silently |
| 15 | concurrent runs, different bridges | no cross-wire |

### 7.2 Benchmarks

- **External:** SWE-bench Lite subset, GAIA, tau-bench, FinanceBench (adapters).
- **Internal:** 68-task corpus + mined production failures + finance honesty set.
- **Reporting:** scorecard regenerated from the run store; per-model breakdown.

---

## 8. Delete / retire list

Deleting is part of the plan. Target: **-3,000 to -5,000 lines** without losing
capability.

| Retire | Replacement |
|---|---|
| `orchestration/engine.py` scheduler | fabric job kind `graph`/`dag` |
| `tasks/scheduler.py` loop | fabric job kind `task` |
| `graph_runtime/executor.py` durability path | fabric worker + deterministic layer executor |
| `service._active` + `registry.set_active_context` | `ExecutionRegistry` + `RunScope` |
| `market_gateway._bridge` mutation | run-scoped gateway |
| duplicated checkpoint encoding | projection cursor |
| 4 retry implementations | `RetryPolicy` |
| `ToolContext` field sprawl | `RunScope` + adapter |
| dead/default-off flags | one feature-flag registry with owners |

---

## 9. First twelve PRs (ordered)

1. ✅ `test(harness): scripted fault provider + crash injector` (retry/registration faults shipped; crash injector still open)
2. ✅ `fix(harness): register foreground runs in ExecutionRegistry`
3. ✅ `feat(harness): StepExecutor + RetryPolicy on the model path`
4. ✅ `fix(harness): separate run deadline from model-call timeout`
5. `refactor(harness): RunScope replaces build_graph kwargs (incremental)`
6. `feat(harness): tool_search + namespaced lazy surface`
7. `feat(harness): artifact handles for large tool outputs`
8. `refactor(harness): fabric as the only durable executor`
9. `feat(harness): evidence ledger + generic verifier registry`
10. `feat(harness): one spawn primitive + budget tree`
11. `feat(security): auth on by default outside loopback + sandbox profiles`
12. `ci: scorecard evidence gate + SLO budgets`

Each PR is independently revertible. None requires a big-bang branch.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Refactor breaks the app | strangler pattern: adapters + flags default-off, flip after parity tests |
| SQLite migration corrupts data | backup + one-way migrations + test on a copied real DB |
| Scheduler merge stalls | ship C1 alone first; C2 is valuable even if C3-C9 slip |
| OS sandbox unavailable on Windows | capability matrix; honest `Unavailable`; never pretend |
| Scope creep from 950 tools | freeze the surface; no new tool without a contract test |
| Solo bandwidth | waves are independent; stop after any wave with a net win |
| Scorecard politics | C0 makes "unmeasured" the default; numbers require evidence |

---

## 11. Non-goals

- Do not rewrite the runtime in TypeScript. Next.js stays the front door.
- Do not add a fifth execution plane.
- Do not chase tool count. Fewer, better, lazily loaded.
- Do not build a hosted multi-tenant SaaS in this round.
- Do not let the model do deterministic finance math.
- Do not weaken approvals, digest binding or claim verification.

---

## 12. Open decisions (needed before C2/C6)

1. **Deployment target:** local single-user first, or multi-tenant from day one?
   (Changes C2 and C6 substantially.)
2. **Retirement appetite:** can `a2a`/`team`/`orchestration` be reduced to
   adapters, or must their wire contracts remain first-class?
3. **Sandbox scope:** Windows-only, or Windows + Linux + macOS in this round?
4. **Benchmark choice:** which external suite is the public number (SWE-bench
   Lite, GAIA, tau-bench, FinanceBench)?
5. **Capacity:** solo (4-5 months) or two engineers (~3 months)?

---

## 13. The one-line version

Eclipse already knows how to do almost anything; Round 5 makes sure it does it
once, on time, within budget, under a real sandbox, and with evidence - which is
what "world-class harness" actually means.
