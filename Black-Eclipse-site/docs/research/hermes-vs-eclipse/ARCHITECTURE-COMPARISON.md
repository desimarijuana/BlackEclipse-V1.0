---
title: Hermes vs Eclipse — Subsystem Architecture Comparison
status: Current
last-verified: 2026-11-12
evidence-window: Eclipse working tree + NousResearch/hermes-agent @ 72c8803
---

# Architecture Comparison

Every subsystem below is evaluated against the same six questions: how Hermes
implements it, how Eclipse implements it, the architectural difference, what
Hermes does better, what Eclipse does better, and what is missing. Status tags
are `implemented`, `partial`, `stub` or `missing`, based on code inspected — not
on README claims.

Path notation: Eclipse paths are relative to `Black-Eclipse-site/python/harness/`
unless prefixed with `src/`; Hermes paths are relative to the repository root.

---

## 1. Core architecture and system design

**Hermes — implemented.** `run_agent.py` is a thin facade over an `AIAgent`
assembled from mixins; the loop is `agent/conversation_loop.py`, with one
sibling module per turn phase (`turn_preflight`, `turn_api_call`,
`turn_tool_round`, `turn_overflow`, `turn_recovery`, …). It is a synchronous
loop with a thread pool for tools, a SQLite session DB (`hermes_state*.py`), a
gateway for 20+ platforms, a cron scheduler, and provider plugins. The design is
battle-tested but module sizes are enormous (`context_compressor.py` 328 KB,
`conversation_compression.py` 248 KB, `agent_init.py` 118 KB,
`error_classifier.py` 100 KB), and ownership is enforced socially through
`AGENTS.md` invariants rather than by type boundaries.

**Eclipse — implemented.** Next.js is the front door; FastAPI
(`main.py`) hosts `AgenticService` (`service.py`), which owns one LangGraph loop
(`graph.py`), one tool registry (`tools.py`), one policy gateway
(`security/gateway.py`), one event log (`events.py` + `event_system/`), a
Fabric execution plane (`fabric/`), and domain routers. `docs/harness/core-architecture.md`
states the "five ones" explicitly. 1,749 Python files / ~431k lines, plus 2,360
TS/TSX files.

**Difference.** Hermes optimises for *one process that survives anything a
provider or shell throws at it*. Eclipse optimises for *one run that can be
audited, resumed and trusted*. Hermes has richer provider and channel
abstractions; Eclipse has richer execution, security and evidence abstractions.

**Hermes better:** provider/channel breadth, onboarding, daily-driver polish,
and years of failure-mode handling encoded in the classifier and compression
ladder.

**Eclipse better:** explicit invariants, one policy seam, one event log, one
execution plane, durable run semantics, and domain layering.

**Gap type:** implementation maturity, not architecture. Eclipse's shape is
sound; several seams are declared but not actually used on the live path (see
§19).

---

## 2. Agent runtime and execution lifecycle

**Hermes — implemented.** Synchronous `while` loop bounded by
`max_iterations` (default 500) and `IterationBudget`; each turn is
preflight → API call → response intake/check → tool round → post-tool
compression. Interruptible API calls run the HTTP request on a background
thread and abandon it on `/stop` or a new user message. Tool-call turns are
persisted *before* side effects; a failed canonical append ends the turn rather
than executing from process-only state (`agent/turn_tool_round.py:1-20,
100-170`). Streaming has watchdogs and a length-continuation path. Session
admissions, worker executions and worker receipts are durable ledger tables
(`website/docs/developer-guide/session-storage.md`).

**Eclipse — implemented.** One LangGraph `StateGraph`: `START → agent →
(tools | replan | END)`, with `verify_repair` and `exhausted` terminals
(`graph.py:1345-1378`). Chat budget 24 (ceiling 32), hard cap 240 steps, a
wall-clock `RunDeadline`, one retry policy, one model-call path
(`step.py:57`), per-run leases, checkpoints, resume, effect ledger and
watchdog. Exactly one terminal state is written by a fenced update.

**Difference.** Hermes has no resumable agent run; it has durable *session*
state and admission ledgers, and it relies on persist-before-tool plus provider
retries. Eclipse can resume a run from a checkpoint, refuse to re-execute an
effect whose outcome is unknown, and fence a stale worker out of the terminal
write.

**Hermes better:** provider-level recovery inside the loop (fallback model
mid-session, credential rotation, content-policy handling), interruption
semantics, and the breadth of turn-phase handling.

**Eclipse better:** crash recovery, at-most-once effects, lease/fencing,
deterministic budgets, and a second execution plane (Fabric) for children.

**Missing/weak in Eclipse:** progress counter writes are unfenced
(`graph.py:884`, `:1197`); checkpoint and message writes are separate commits
(`_write_checkpoint`, `graph.py:689`); checkpoint failures are swallowed;
tool idempotency is recorded after execution. These are correctness edges, not
missing architecture.

---

## 3. Tool calling and orchestration

**Hermes — implemented.** Self-registering tools (`tools/registry.py`), AST
discovery of `tools/*.py`, toolset resolution, `check_fn` availability probing
with a 30 s TTL, and 70+ tools across ~28 toolsets. Multiple tool calls in one
model response execute concurrently in a `ThreadPoolExecutor`
(`_MAX_TOOL_WORKERS = 8`, `agent/tool_executor.py:136`), with ordered result
insertion, interactive-tool serialisation, a start-order gate and a 420 s
default batch timeout. Agent-level tools (`todo`, `memory`, `session_search`,
`delegate_task`) are intercepted before registry dispatch. Tool search provides
tiered progressive disclosure with BM25 and stemming (`tools/tool_search.py`).

**Eclipse — implemented.** `ToolRegistry` with a `ToolDefinition` carrying
permission, risk, timeout, effect, output schema, version and deprecation
metadata (`tools.py:426`). Pydantic validation, allowlist, effect authorization,
effect-token enforcement, widening checks, a hard timeout via `await_bounded`,
24k-char output bounding and full-output spill to `ToolOutputStore`
(`tools.py:580-751`). But sibling calls in one model turn run **sequentially**
(`graph.py:997`), and lazy tool disclosure is off by default
(`tool_surface.py:39-44`).

**Difference.** Hermes treats tools as a latency/convenience problem; Eclipse
treats them as a security/contract problem. Both are right about their own
domain.

**Hermes better:** concurrency, default progressive disclosure, tool guardrails
(identical-call/cycle/stall detection in `agent/tool_guardrails.py`), and the
ergonomics of adding a tool by dropping a file in `tools/`.

**Eclipse better:** per-tool effect/permission/risk taxonomy, contract audit,
output spill, policy composition, and the fact that an effectful call cannot
silently bypass approval.

**Change required:** parallelise independent read-only calls in `tools_node`
with ordered results while keeping effectful calls serialised; promote
`tool_search` to default-on with BM25; add a tool-call guardrail controller.

---

## 4. Planning, reasoning and task decomposition

**Hermes — implemented, prompt-centric.** `todo_list` is a revisioned,
compression-surviving task list (`tools/todo_tool.py`). `/goal` adds a standing
objective with an auxiliary judge model, optional completion contract
(outcome/verification/constraints/boundaries/stop_when), deterministic quality
gates, and automatic continuation (`website/docs/user-guide/features/goals.md`).
`/loop` and `/heartbeat` add timer-driven and idle-driven turns. The system
prompt carries task-completion and steering guidance. There is no planner that
produces a typed plan/DAG consumed by the runtime.

**Eclipse — partial-to-implemented.** `plan_mode.py` appends a fenced
`<plan_mode>` block (guidance, not enforcement). `replan.py` has a bounded
`ReplanBudget(max_replans=2)`, evidence-triggered replanning, and is **default
off** (`HARNESS_REPLAN_ENABLED`). `goals/runtime.py` has `PlanRuntime` with
goal/step prompt blocks, tool-result handles, answer claims, verifier registry,
evidence replan and `settle`. `graph_runtime/planner.py` converts a chat request
into a validated workflow IR (structure only, never executed). `tasks/` has a
real DAG plan/task runtime.

**Difference.** Hermes closes the loop from objective to continuation; Eclipse
has stronger verification primitives but no standing objective driver. Eclipse's
plan mode can be ignored by the model; Hermes' `/goal` cannot be ignored because
the runtime re-prompts.

**Hermes better:** the autonomy contract and the "done" judge.

**Eclipse better:** typed plans, evidence claims, verifier registry, and the
fact that a plan step can be tied to a tool handle rather than prose.

**Missing in Eclipse:** a goal driver, deterministic gates, and a plan that is
enforced rather than suggested.

---

## 5. Persistent memory and context management

**Hermes — implemented, deliberately small.** Two files: `MEMORY.md`
(2,200 chars) and `USER.md` (1,375 chars), frozen into the system prompt at
session start, edited only through the `memory` tool (`add`/`patch`/`remove`,
batch-atomic, no `replace`). The `MemoryManager` orchestrates provider plugins
with hooks (`build_system_prompt`, `prefetch`, `sync_turn`, `on_session_end`,
`on_pre_compress`, `on_delegation`). `session_search` provides FTS5 + trigram
search over the session DB with discovery/scroll/read/browse shapes and lineage
dedup (`tools/session_search_tool.py`). External providers (ByteRover,
RetainDB, Honcho, etc.) are opt-in.

**Eclipse — implemented, structured.** `eclipse_memory/` has 25+ tables:
`MemoryRecord`, evidence, links, retrieval events, suggestions, recurrence,
profiles, compaction proposals; types include episodic/semantic/procedural/
preference/constraint/correction/observation/summary. Writes go through a
deterministic decision gate (`decision.py`), exact-signature dedupe, conflict
assessment (`conflicts.py`), authority (`explicit` vs `automatic`), retention,
and budget enforcement. Retrieval is lexical with stemming, synonyms, typo
tolerance, authority/recency/importance scoring, a scope guard and a
contradiction guard (`retrieval.py:89-466`). Session search is FTS5/BM25 with
run lineage (`session_index.py`, `persistence.py:963+`). External memory
providers exist but external search is off by default.

**Difference.** Hermes' built-in memory is a prompt cache-friendly scratchpad;
Eclipse's is a governed knowledge base. Hermes' provider protocol is more
mature; Eclipse's data model is far richer.

**Hermes better:** provider pluggability, prefetch/sync lifecycle, end-of-session
hooks, and the fact that memory writes are cheap and always visible.

**Eclipse better:** conflict handling, evidence links, authority, retention,
correction records, mistakes, and auditability.

**Missing in Eclipse:** production hybrid retrieval. `eclipse_memory/hybrid.py`
has BM25 and weights but is explicitly **not wired** (`hybrid.py:1-7`);
`semantic_indexing_enabled` defaults false. Memory consolidation runs at boot
or on operator request, not periodically. `ProfileRegistry` does not filter
memory rows.

---

## 6. Skills architecture and dynamic skill creation

**Hermes — implemented.** Skills are `SKILL.md` directories with frontmatter,
optional `references/`, `templates/`, `scripts/`, `assets/`, platform and
toolset conditions, config vars and credential requirements. The system prompt
carries a mandatory index with 60-char descriptions; `skill_view` loads the body
and support files on demand; `skill_manage` creates/patches/writes/deletes with
read-before-write enforcement. `/learn` turns a source or a conversation into a
skill. A background **curator** (`agent/curator.py`) runs every N hours when
idle, does deterministic stale/archive transitions, and optionally forks an
agent to consolidate narrow skills into umbrellas with ledgered writes and
rollback. Skills Hub installs from official/ClawHub/GitHub with a security scan.

**Eclipse — implemented, governance-heavy.** `skills/` has registry tiers
(project > profile/user > installed > bundled), trust, content scanning,
quarantine, versioning, patch parser, canary/rollback, bundles, evaluation
(manifest/schema/deps/permissions/tools/financial integrity/cases), learning
candidates, drafts, auto-drafting, auto-enable of read-only learned skills
(default on), and `skill_quality` execution metrics. 91 skills ship in the
library. Matching is keyword-only and limited to 8 in the manifest
(`prompt_segments.py:166-198`, `registry.discover:682`).

**Difference.** Hermes has a *library culture*: mandatory index, `/learn`,
curation, hub. Eclipse has a *supply-chain culture*: trust, signatures, scans,
versioning, evaluation, promotion. Each is weak where the other is strong.

**Hermes better:** discovery, authoring ergonomics, consolidation, and use-time
feedback ("if a skill was missing steps, patch it before finishing").

**Eclipse better:** provenance, quarantine, version promotion gates, rollback,
and execution metrics.

**Missing in Eclipse:** a curator that merges/deduplicates prose; behavioural
evaluation before auto-enable (the current evaluation never executes the skill);
and a semantic/usage-ranked matcher.

---

## 7. Learning from mistakes and self-improvement

**Hermes — implemented, mostly prompt-and-curator.** The system prompt nudges
"after difficult/iterative tasks, offer to save as a skill" and "if a skill you
loaded was missing steps, update it." The curator consolidates. Memory captures
corrections through the `memory` tool. There is no deterministic mistake ledger,
no recurrence threshold, no lesson contract, and no code self-modification.

**Eclipse — implemented, layered, partly dark.** `eclipse_memory/mistakes.py`
captures deterministic mistake categories per run; `skills/learning.py`
detects corrections, failure→recovery pairs, validation improvements, successful
procedures, source-selection and provider-eligibility improvements;
`skills/draft.py` drafts inert skills; `self_improvement/` has lessons, drift
watch, RSL (default off), hillclimb (off), archive/CMP/islands (off), autonomy
(off), self-modification (read-only learned skills, default on), widening
(operator-gated), code evolution/promotion (operator-only). Lessons are injected
only after operator adoption and a completed validation run; outcome feedback is
live.

**Difference.** Eclipse has the rigorous machinery and keeps it mostly dark;
Hermes has a light mechanism and keeps it on. The result is that Hermes learns
more often, while Eclipse learns more safely.

**Hermes better:** actually closing the loop in normal use.

**Eclipse better:** mistake taxonomy, recurrence, evidence links, validation
runs, promotion gates, drift detection, and the ability to audit why a lesson
was adopted.

**Missing in Eclipse:** a safe default-on path from mistake → lesson → prompt
injection, and a periodic consolidation/curation job. RSL being off by default
is reasonable; the *simple* lesson loop should not be.

---

## 8. Long-running and autonomous execution

**Hermes — implemented.** `/goal` (judge-driven continuation, quality gates,
wait barriers), `/loop` (fixed or self-paced, `--times`, `--until`), `/heartbeat`
(idle-only recurring prompt in the same session), cron (durable jobs, admission
recovery, preflight validation, no-agent mode, event triggers), and kanban
(durable board with worker lanes, goal-mode cards, dependencies, review).
Run state survives `/resume` and compression.

**Eclipse — implemented infrastructure, missing UX.** `jobs/` (cron, triggers,
delivery, misfire policy), `automation/` (cron/interval/event/condition/manual,
conditions DSL, breakers, dry-run, resume), `tasks/` (durable DAG scheduler,
leases, verification, goal budgets), `fabric/` (durable jobs, retries, DLQ),
`goals/` (plan runtime), `orchestration/` (DAG engine). There is no in-session
`/goal` judge, no `/loop`, no heartbeat, and no user-facing board.

**Difference.** Eclipse has the durable substrate; Hermes has the product
surface. Building Hermes-style autonomy on Eclipse's Fabric/jobs is mostly
composition, not new infrastructure.

**Hermes better:** the user-facing autonomy contract and cancellation semantics.

**Eclipse better:** durability, lease/fencing, budget accounting, and
deterministic verification hooks.

**Missing in Eclipse:** a judge/continuation engine and a simple loop/heartbeat
API.

---

## 9. Background agents and parallel execution

**Hermes — implemented.** `delegate_task` top-level calls run in the background
and return a handle; results arrive as new messages. Batch mode runs up to 10
concurrent subagents by default. Each child gets an isolated conversation,
its own terminal/process ownership and a restricted toolset. `execute_code`
runs a Python script that can call tools over RPC, collapsing multi-step work
into one model turn. Background terminal processes have a registry with output
buffers, watch patterns, heartbeats and completion notices
(`tools/process_registry.py`).

**Eclipse — implemented, more rigorous.** `delegation.py` (max 4 children,
depth 2, per-child/total timeouts, token budgets, semaphore, permission
narrowing), `spawn/` (max 8 children, depth 2, 120k tokens, 24 steps, 900 s,
Fabric jobs, blackboard, deterministic synthesis), `fabric/` (durable jobs,
claim/heartbeat/retry/DLQ), `orchestration/` (resource-limited DAG), `tasks/`
(durable scheduler), `a2a/` (message bus, durable budgets), `team/`
(independence-aware review), `institution/` (seven-seat team preset).

**Difference.** Eclipse models children as durable jobs with budgets and
evidence; Hermes models them as threads with excellent ergonomics. Eclipse is
safer for long financial work; Hermes is faster to use.

**Hermes better:** background completion UX, per-child worktrees, image
forwarding, output schemas and steering.

**Eclipse better:** durability, budget accounting, deterministic merge,
blackboard, independence checks and audit.

**Missing in Eclipse:** async completion into chat, schema-repair handshake,
steering, and a lifecycle API for external callers.

---

## 10. Multi-agent orchestration and delegation

Covered structurally in §9. The distinct architectural point is **who owns the
merge**. Hermes returns each child's final summary; the parent model synthesises
prose. Eclipse's `delegation.aggregate` / `partition_claims` / `HandleVerifier`
and `spawn.synthesize` merge only re-checkable claims, surface conflicts, and
drop unconfirmed prose. Eclipse's `team/review.py` enforces producer/reviewer
independence and blocks approval on unresolved material conflicts.

**Hermes better:** ease of fan-out, lifecycle control, and the ability to
deliver results asynchronously.

**Eclipse better:** correctness of the merged answer, auditability, and
institutional role separation.

**Change required:** expose Eclipse's existing child jobs through a Hermes-like
ergonomic API; do not weaken the evidence merge.

---

## 11. Shell, terminal and filesystem capabilities

**Hermes — implemented.** Terminal backends: local, Docker, SSH, Modal, Daytona,
Vercel Sandbox, plus plugin backends. A background process registry with
systemd-scope support on Linux, output buffers capped at 200k chars, watch
patterns with rate limits, and restart-safe ownership. `read_file`, `write_file`,
`patch`, `search_files` with path and size guards. Shadow-git checkpoints before
mutations (`tools/checkpoint_manager.py`).

**Eclipse — implemented.** `code/sandbox.py` (env scrubbing, Job Object /
process-group kill, memory/CPU/process limits, no-network by default),
`code/terminal.py` (allow/ask/deny classification, shell metacharacter denial),
`terminal/tools.py` (27 tools, approvals, owned processes), `code/fs/`
(permissions, editing, search, symbols, transactions, verify, watch), `git/`
(safety, secret scan, protected branches, approvals, VCS providers),
`code/worktree.py`, `code/policy.py` protected paths. Weakness:
`code/shell.py` bypasses the sandbox isolation and does no tree kill
(`shell.py:72,143,179`).

**Difference.** Hermes has breadth of execution backends; Eclipse has depth of
policy and verification. Eclipse's local isolation is stronger; Hermes' remote
backends are much broader.

**Hermes better:** remote/container backends, background process watch/heartbeat,
and rollback UX.

**Eclipse better:** path policy, secret scrubbing, git risk assessment, process
ownership, and effect approvals.

**Missing in Eclipse:** SSH/Modal/Daytona-style backends, a user-facing file
rollback, and a fix for the `code/shell.py` bypass.

---

## 12. Browser automation and computer use

**Hermes — implemented.** Browser backends: Browserbase, Browser Use cloud,
local Chrome/Brave/Chromium/Edge via CDP, local Chromium. `browser_exec` is
Python over CDP; `browser_cdp`, dialog handling, vault fills, profiles, session
lifecycle, cloud sessions and a supervisor. `computer_use` is a single tool
gated by platform capabilities.

**Eclipse — implemented, finance-aware.** ~100 browser tools
(`browser/tools.py:1146`) with domain policy, allow/deny/ask, private-target
routing, destructive-action detection (payments), injection scanning and
untrusted-content fencing (`browser/policy.py`). Evidence URLs feed the run's
source collector (`browser/evidence.py`). Computer use has 22 tools, a
fail-closed policy, a finance firewall (`finance_read: ALLOW`,
`finance_mutate: DENY`), OCR, accessibility drivers for four OSes, grounding,
verification and takeover.

**Difference.** Hermes offers more browser deployment options and a more
polished single `browser_exec`; Eclipse offers stronger safety and financial
evidence integration.

**Hermes better:** backend choice, cloud browsers, and real-profile login
handling.

**Eclipse better:** policy, finance firewall, evidence capture, and
verification.

**Weakness in Eclipse:** many mutating browser tools are declared
`permission="read"` at the registry and rely on the handler to enforce policy.

---

## 13. MCP and external integrations

**Hermes — implemented.** MCP client with stdio/HTTP transport discovery,
OAuth (including device flow), per-server tool filtering, sampling,
elicitation, schema cache, health/liveness, tool costs and spend limits, and
tool-search integration. Untrusted servers require a trust prompt for writes.
YOLO/`mode: off` can skip the trust prompt.

**Eclipse — implemented, security-heavy.** `mcp/client.py` supports stdio,
Streamable HTTP and SSE, TLS/mTLS, OAuth, vault-backed headers. Manager has
lifecycle tasks, retries, circuit breaker, reconnect, schema cache, presets.
Security includes SSRF checks, stdio command screening, OSV malware lookup for
the exact package/version, trust tiers, digest-bound single-use approvals, audit
and orphan reaping. Stdio servers are not OS-sandboxed; supply-chain check is
fail-open on network error.

**Difference.** Both are mature. Eclipse's security review is deeper; Hermes'
OAuth and spend-limit UX is broader.

**Hermes better:** OAuth breadth, spend limits, tool-search integration,
one-command catalog installs.

**Eclipse better:** SSRF/OSV/screening, approval digest binding, audit.

**Change required:** add spend/quota metadata to MCP descriptors; expose MCP
tool discovery through the tool-search surface.

---

## 14. Scheduling and recurring tasks

**Hermes — implemented.** `cron/` with croniter expressions, natural-language
schedules, per-job model/reasoning pins, attached skills, delivery to origin or
platforms, no-agent script mode, event-triggered jobs, preflight validation
that avoids spending tokens on misconfigured jobs, durable admission recovery,
and paused-on-interruption semantics. Cron sessions skip memory by default.

**Eclipse — implemented twice.** `jobs/` (5-field cron, file/webhook/manual
triggers, missed-run policy, delivery adapters, breaker) and `automation/`
(cron/interval/event/condition/manual, conditions DSL, misfire, retries,
dry-run, lease renewal, metrics). Graph Studio also has its own cron schedules
and webhooks. Agent-facing scheduling tools are operator-gated.

**Difference.** Hermes' scheduler is one coherent product surface; Eclipse has
more capable primitives but three schedule paths (`jobs`, `automation`, Graph
Studio), which is an ownership risk.

**Hermes better:** preflight validation, no-agent jobs, ad-hoc model pinning,
and delivery ergonomics.

**Eclipse better:** conditions, misfire policies, breaker, durable DAG
execution, and workflow-native scheduling.

**Missing in Eclipse:** a single scheduler owner; consolidate or clearly
subordinate the three paths.

---

## 15. Session management and conversation continuity

**Hermes — implemented, very mature.** SQLite WAL `state.db` with sessions,
messages, FTS5 + trigram, `session_model_usage`, compression locks, async
delegations, delivery obligations, runtime epoch, admission FIFO, worker
executions and receipts. Session lineage on compression. Resume across gateway
restarts. Cross-platform continuity. A single canonical writer (the profile's
gateway) prevents split-brain transcript writes.

**Eclipse — implemented.** `ChatSession`, `SessionMessage`, per-conversation
transcripts, `session_index` FTS5/BM25 with filters (role, date, run, session,
profile, market, skill, memory action), `session_search`/`session_open` tools
with a bounded window, session fork/export/summary, profile routes. Run lineage
links parent/child/workflow.

**Difference.** Hermes has stronger write arbitration and admission semantics;
Eclipse has stronger lineage and run-level durability. Eclipse's session summary
is generated but not auto-injected (`summary_prompt_block` is unused).

**Hermes better:** canonical writer, admission ledger, trigram search, recovery
tooling.

**Eclipse better:** run lineage, per-run indexing, scope filters.

**Missing in Eclipse:** auto-injected session summary, cross-session "browse"
semantics, and a canonical-writer rule for multiple runtime processes.

---

## 16. Checkpointing, recovery and fault tolerance

**Hermes — implemented for files, not runs.** Persist-before-tool; session
admissions that become `unknown` on owner loss and are never replayed; worker
receipts; a shadow-git checkpoint store for filesystem rollback; process
ownership; retry/fallback. There is no run checkpoint with resumption of the
agent loop after a crash, and subagent handles cannot reconnect after a process
restart (`subagent-lifecycle-api.md`).

**Eclipse — implemented for runs.** `RunCheckpoint`, `RunMessage`,
`ToolExecutionIdempotency`, `RunEffects`, `RunLease`, `RuntimeInstance`,
`fail_orphaned_runs`, `find_stalled`, `sweep_stalled_runs`, resume endpoint,
SSE replay, `interrupted` state, partial output preservation. Known edges:
checkpoint not atomic with messages; sequence outside a transaction; failures
swallowed; watchdog not lease-aware; counter writes unfenced.

**Difference.** Different targets: Eclipse can resume a run; Hermes can undo a
file. Eclipse should keep its run kernel and add the file rollback.

**Hermes better:** user-visible file rollback, process-scope cleanup, and
admission semantics.

**Eclipse better:** run resumption, fencing, effect ledger, orphan recovery.

---

## 17. Permissions, security and sandboxing

**Hermes — implemented, personal-agent threat model.** Eight layers: user
authorization (allowlists/pairing), dangerous-command approval
(smart/manual/off), hardline blocklist, user deny globs, file write sandbox,
container isolation, MCP credential filtering, context-file injection scanning,
cross-session isolation, input sanitisation. `--yolo`/`/yolo` disables prompts;
container backends skip dangerous-command checks because the container is the
boundary. A supervised-gateway guard prevents self-termination.

**Eclipse — implemented, production threat model.** One `SecurityGateway` chain:
risk → floor → policy → capability → approval, with an approval store
unreachable ⇒ deny. Effect tokens (`off|shadow|enforce`, default **shadow**),
tenant isolation, capability issue/delegate/revoke, sandbox profiles that
refuse when unenforceable, Docker/AppContainer/local backends, secret grants,
JSONL audit with hash chain + HMAC.

**Difference.** Hermes is designed for a trusted individual on their own
machine; Eclipse is designed for money-adjacent multi-tenant operation.

**Hermes better:** approval UX (cards, session/permanent allowlists, smart
approval), user deny rules, and hardline floor.

**Eclipse better:** every structural property that matters for finance.

**Weakness in Eclipse:** effect tokens default to shadow; the gateway is
constructed best-effort; approval TTL 900 s; grants match program strings.

---

## 18. Observability, tracing and execution auditing

**Hermes — implemented, product-metrics oriented.** Structured logging, a
`FailoverReason` taxonomy, shared product metrics (`hermes.model_call`,
`tool_call`, `compression`, `fallback`, `memory.op`, `curator.run`,
`delegation.run`, …), session insights/cost estimates, trace upload to Hugging
Face in Claude Code JSONL shape with mandatory secret redaction. No
OpenTelemetry/Langfuse/Sentry exporter was found in the inspected modules.
There is no per-run span tree or SLO gate in the Eclipse sense.

**Eclipse — implemented.** `observability/` hub with spans, W3C traceparent,
exporters (in-memory, console, JSONL, OTLP/HTTP, Langfuse, Sentry), metrics,
cost engine, SLOs, health, anomaly/loop detection, redaction, sampling;
`run_observability.explain_run`; `run_outcome`; `event_system` with middleware,
dedupe, replay and authorization. Scorecard and SLO gates are generated from
runs.

**Difference.** Eclipse observes *runs*; Hermes observes *the product*. Eclipse
is the better base for regulated/financial audit; Hermes is the better base for
product analytics.

**Hermes better:** failover classification, cost insight, and trace sharing.

**Eclipse better:** span tree, SLO budgets, failure taxonomy, event replay,
redaction, audit chain.

**Weakness in Eclipse:** two event buses bridged both ways; `RunEmitter._seq`
is per-instance so event IDs can collide across emitters and drop events;
projection failures log at debug only.

---

## 19. Model/provider abstraction and routing

**Hermes — implemented, best-in-class for breadth.** `runtime_provider.py`
maps `(provider, model)` to `(api_mode, key, base_url)`; 18+ providers; three
API modes; OAuth flows; credential pools with rotation on 429/5xx; fallback
providers mid-session; per-task auxiliary routing (curator, vision, embeddings,
title, session_search, compression, goal judge); model metadata and context
limits; OpenRouter provider preferences.

**Eclipse — implemented, but the best part is not on the live path.**
`model_runtime/` has capability priors, task profiles, a scored router with
eligibility (health, circuit, rate limit, context, cost, reliability),
`fallback_depth=3`, usage normalisation and a cost tracker. But `graph.py`
calls `step.invoke_model_step` → `ainvoke_streaming` and then
`runtime.record_step`; it never calls `ModelRuntime.invoke` or
`stream_for_graph`. Cross-provider fallback requires `HARNESS_MODEL_FALLBACK`
and is not exercised by the graph. Two retry knobs exist with different
defaults (`HARNESS_MODEL_RETRIES=1` vs `HARNESS_MODEL_ATTEMPTS=3`).

**Difference.** Hermes routes and fails over on every call; Eclipse has a
router that is mostly advisory on the agent path.

**Hermes better:** failover, credential pools, auxiliary task routing, provider
breadth.

**Eclipse better:** capability/quality scoring, cost accounting with `priced:
false` for unknown models, health/circuit model, and one usage ledger.

**Change required:** make the graph call the runtime, not bypass it. This is
P0.

---

## 20. Context compression and token efficiency

**Hermes — implemented, deep.** Dual layer (gateway 85%, agent 50%), provider
usage anchors with a bounded appended-message delta, tool-result pruning before
summary, structured summary with a protected tail (default 20 messages, tool
pairs kept), prompt-cache-stable system prompt tiers (stable/context/volatile),
Anthropic cache breakpoints, micro-compaction, prepared-ahead compaction,
failure cooldown ladder 60→300→900 s, deterministic fallback summary, native
Codex/Responses compaction, session lineage on compression, and image/reasoning
token pricing learned from provider usage.

**Eclipse — implemented, shallower.** `context_budget.py` sums estimated
tokens for system/tools/profile/skills/memory/runtime/user, resolves the model
window, reserves 1024 output and a 10% margin; unknown window ⇒ inert budget.
`history.py` keeps 20 turns / 40k chars. `compaction.py` builds a deterministic
skeleton (12 items × 400 chars) and optionally a model narrative (off by
default). `_retry_with_tighter_budget` only works at step ≤ 1. `prompt_segments`
defines a cache key and a stable/frozen segment plan, but the graph assembles
messages per run without provider cache markers.

**Difference.** Hermes treats context as a measured, provider-anchored budget;
Eclipse treats it as a heuristic guardrail.

**Hermes better:** accuracy, cache preservation, graceful degradation, and long
session behaviour.

**Eclipse better:** deterministic, auditable compaction and an honest inert mode
when the window is unknown.

**Change required:** adopt the usage-anchor + ladder design, keep Eclipse's
deterministic skeleton as the fallback, and add provider cache markers where the
provider supports them.

---

## 21. Artifact generation and file handling

**Hermes — implemented.** `write_file`, `patch`, document extraction for
PDF/Office/EPUB, image generation, vision analysis, TTS, video generation,
charts via skills/code, and a checkpointed workspace. Artifacts are files on
disk; there is no artifact registry/versioning.

**Eclipse — implemented, much deeper.** `artifacts/` content-addressed storage,
versions, collections, tags, preview, reconciliation, retention, workspace
discovery; `documents/` authoring and plan/apply/verify editing for
docx/xlsx/pptx/pdf; `canvas/` immutable artifact versions with optimistic
concurrency; `charts/` typed spec, Plotly/Matplotlib, scene rendering; agent
tools for all of it.

**Difference.** Eclipse has a real artifact system; Hermes has files plus media
generation.

**Hermes better:** media generation (image/video/TTS) and document extraction
breadth.

**Eclipse better:** versioning, provenance, editing safety, and finance
reporting.

**Missing in Eclipse:** image/video generation and TTS as first-class tools
(some exist in `vision/` and `video/`, but not the same packaging).

---

## 22. Testing, evaluation and benchmarking

**Hermes — implemented, massive but developer-facing.** 8,137 Python test files
in the repository tree (docs claim ~25,000 tests across ~1,250 files), plus
`evals/` with 33 scenario scripts (approval deny, cron races, MCP device flow,
output caps, session snapshot, vault fill, etc.). The Hermes Index/Hermes Bench
is an external product benchmark. There is no in-repo versioned task corpus with
graders, statistical aggregation, contamination controls and a release gate.

**Eclipse — implemented, evaluation-first.** 957 Python test files; a real
evaluation harness (`evaluation/`) with two invokers (scripted real-runtime and
live service), isolated environments, trajectory capture, 17 graders,
pass@1/pass@k/Wilson CI, failure taxonomy, critical dimensions, baselines,
regression gates, replay, mining, ablation, contamination controls, live/offline
tiers, and a generated scorecard tied to run IDs. The independent audit found
82/100 with release blockers (orphaned runs, 120 s model deadline with no
partial output, three finance helper scaling bugs, JDdS inventory
misattribution, expensive failure loops).

**Difference.** Hermes tests the code; Eclipse evaluates the agent. Eclipse is
ahead on agent evaluation, behind on raw test volume and provider-failure
coverage.

**Hermes better:** test breadth, provider matrix coverage, scenario evals.

**Eclipse better:** scored corpus, graders, statistics, release gates,
contamination controls, and finance/research suites.

**Missing in Eclipse:** external benchmark adapters (SWE-bench/GAIA/tau-bench),
offline coverage for research/citations, and approval-path evals.

---

## 23. Extensibility and plugin architecture

**Hermes — implemented, broad.** General plugins (tools/hooks), memory
providers, context engines, model providers, browser providers, terminal
environment providers, web-search providers, image/video/TTS providers,
delegation providers, secret sources and platform adapters. Plugins can be
directory, project or pip entry-point; a catalog and Skills Hub provide
distribution. Plugin tool overrides require explicit operator opt-in.

**Eclipse — implemented, security-heavy.** `plugins/` manifest with
contributions (tools/skills/hooks/events/commands/ui/workers/webhooks/research
providers/data providers/agents/workflows), signing (ed25519), review gate,
separate-process sandbox with host-proxied config/secrets/HTTP/auth/events,
semver compatibility, dependency checks, marketplace local-first + remote index
with checksum. `capabilities/` can generate recipes/reports/tools/skills/UI/
plugins/harness changes under a restricted import/permission allowlist. SDK for
apps/dashboards/pages/themes.

**Difference.** Hermes has more provider *types*; Eclipse has stronger
distribution security and generated capabilities.

**Hermes better:** provider-plugin breadth, catalog, one-command install.

**Eclipse better:** signing, review, sandbox, capability manifests, and
generated UI/app surfaces.

**Missing in Eclipse:** a public plugin catalog/registry with ratings/versions
and a clean memory/context-engine provider interface.

---

## 24. Developer experience and usability

**Hermes — excellent for a single user.** One-line install, a TUI, a desktop
app, 20+ gateways, `/model`, `/tools`, `/skills`, `/goal`, `/loop`,
`/heartbeat`, `/compress`, `/rollback`, `/resume`, a large docs site, and a
Python-library entry point. Zero-config is "run the installer".

**Eclipse — excellent for a finance workstation, heavier to run.** `npm install
&& npm run dev` works (postinstall provisions Python), desktop Tauri shell,
offline front door, 31 tabs, chat dock with ~60 components, Graph Studio,
Strategy Studio, Portfolio, Journal, Research. The surface is much larger and
the runtime is Next.js + FastAPI + SQLite + Python. Onboarding is good, but the
sheer surface area is a cognitive tax.

**Difference.** Hermes feels like a daily assistant; Eclipse feels like a
terminal/platform.

**Hermes better:** command surface, first-run experience, TUI/gateway
continuity, and documentation ergonomics.

**Eclipse better:** domain workflows, visualization, and the financial
workbench.

**Missing in Eclipse:** a small, memorable command surface for agent control
(goal/loop/heartbeat/rollback), and a lighter local profile.

---

## 25. Performance, reliability and scalability

**Hermes — strong single-user, weak multi-tenant.** Synchronous loop with
threaded tools, SQLite WAL, one gateway writer, provider failover, and a lot of
attention to timeouts/watchdogs. The 8-worker tool pool and streaming keep
latency reasonable. Multi-process durability is limited: subagent handles die
with the process, cron is single-authority, and there is no distributed lease.

**Eclipse — stronger durability, weaker per-turn latency.** Async FastAPI,
LangGraph, SQLite WAL, leases/fencing, Fabric jobs, multiple schedulers, and
explicit concurrency caps. But sibling tools are sequential, the model fallback
path is unused, context compression is heuristic, and there are multiple
independent in-flight limits (runs, tasks, automation, jobs, fabric,
orchestration), so global capacity is the sum of local caps. The independent
audit measured 46–81 tool calls and 2.4–3.6M tokens on failing runs — a tool-loop
economics problem, not a raw throughput problem.

**Difference.** Hermes is optimised for a responsive single-user session;
Eclipse is optimised for a correct, recoverable, auditable run.

**Hermes better:** per-turn latency, tool concurrency, context efficiency.

**Eclipse better:** crash recovery, effect safety, audit, and bounded
concurrency.

**Change required:** parallel tools, live model gateway, context anchors,
tool-loop guardrails, and a global capacity budget.

---

## Cross-cutting assessment

| Dimension | Hermes | Eclipse | Verdict |
|---|---|---|---|
| Provider resilience | Excellent | Partial (unused router) | Hermes |
| Run durability | Partial | Excellent | Eclipse |
| Tool safety | Partial | Excellent | Eclipse |
| Tool latency | Excellent | Weak | Hermes |
| Context economics | Excellent | Partial | Hermes |
| Memory depth | Partial | Excellent | Eclipse |
| Memory ergonomics | Excellent | Partial | Hermes |
| Skill governance | Partial | Excellent | Eclipse |
| Skill discovery/curation | Excellent | Partial | Hermes |
| Autonomy UX | Excellent | Partial | Hermes |
| Multi-agent correctness | Partial | Excellent | Eclipse |
| Finance/quant | Absent | Excellent | Eclipse |
| Security for money | Weak | Excellent | Eclipse |
| Observability for audit | Partial | Excellent | Eclipse |
| Evaluation of the agent | Partial | Excellent | Eclipse |
| Channels/onboarding | Excellent | Partial | Hermes |

The pattern is consistent: **Hermes owns the harness layer; Eclipse owns the
trust layer and the financial layer.** The target architecture should make the
harness layer a consumer of Eclipse's trust and financial layers, not a
replacement for them.
