---
status: Current
last-verified: 2026-10-08
---

# Parallel Execution & DAG Orchestration

The orchestration layer lets Eclipse run independent work **concurrently** instead
of sequentially, while still honouring dependencies. It is orchestration ON TOP of
the existing runtime — it does **not** replace `execute_run`, the tool registry,
the event bus or the persistence layer.

- An **agent** node calls `execute_run` (the one execution plane).
- A **tool** node calls `ToolRegistry.execute` (the one tool seam).
- A **function** node calls a callable the engine itself registered (used by
  map/reduce).
- An **aggregate**/**join** node combines the structured outputs of its
  dependencies.

Code: `python/harness/orchestration/` (`engine.py` scheduler, `graph.py` DAG,
`runner.py`, `batching.py`, `cache.py`, `recovery.py`, `store.py`, `primitives.py`,
`tools.py`, `events.py`). Routes: `python/harness/routers/orchestration.py`
(`/orchestration/*`, operator-gated). Wiring: `orchestration/bootstrap.py`, called
from the runtime lifespan (`boot.py`). It is deliberately **not** in `service.py`
(which is under a size ratchet); the layer attaches itself to the shared service.

## Why a new layer (and not `workflows/`)?

`python/harness/workflows/` is a bounded, versioned **plan** (max 32 steps) whose
"parallel" kind gathers a single step's branches. It is the right tool for a saved
pipeline. The orchestration layer is the general execution substrate: an arbitrary
DAG with priority, resource-aware concurrency, retries, timeouts, cancellation,
join/race/quorum semantics, dedup/caching, persistence and crash recovery. Tools
and agents use it directly; a saved workflow does not need to change.

## The two models

**Execution** — `ExecutionGraph`: `id`, `root_task_id`, `status`, `failure_policy`,
`nodes`, `edges`, timestamps.

**Node** — `ExecutionNode`: `id`, `kind`, `status`, `dependencies`, `dependents`,
`input`, `output`, `error`, `priority`, `retry`, `timeout_ms`, `resources`,
`join`, `metadata`, `attempt_count`, timestamps, `dedup_key`.

Nodes are stored as JSON columns; dependencies/dependents are also written to an
edge table so the graph is queryable.

## State machine

Node: `PENDING → READY → RUNNING → {COMPLETED, FAILED, CANCELLED, TIMED_OUT}`,
plus `BLOCKED`, `SKIPPED`, `PAUSED`. Every transition is checked in
`orchestration/state.py`; a terminal node has no normal outgoing edge. The one
controlled exception is the **retry edge**: `FAILED`/`TIMED_OUT`/`SKIPPED`/`BLOCKED
→ PENDING`, used only by `retry_node`, the `RETRY_FAILED` policy and crash recovery.

Execution: `PENDING → READY → RUNNING → {COMPLETED, PARTIAL_SUCCESS, FAILED,
CANCELLED}`, with `PAUSED` reachable from `RUNNING`.

## Scheduling

One asyncio coordinator per execution. Each pass it:

1. computes every node whose dependencies are satisfied (`evaluate_readiness`);
2. orders the ready set by priority, then critical-path membership, then FIFO age
   (starvation prevention);
3. admits each node against the resource manager (all-or-nothing) and launches it;
4. waits on a node completion, a resource release, or cancellation.

Independent nodes start together by construction — there is no per-node manual
"parallel" flag. A failed dependency never unlocks a task: dependents become
`SKIPPED` unless the node declares a partial-tolerant join.

### Join policies (`JoinConfig`)

`ALL` (default), `ANY`, `FIRST_SUCCESS`, `QUORUM`, `THRESHOLD`. An early policy
(`ANY`/`FIRST_SUCCESS`/`QUORUM`) cancels remaining dependencies that no other live
node needs. `allow_partial=True` lets a join run once every dependency is
terminal, receiving the failures as structured `errors` — this is how the research
aggregator still runs when one leg fails, and knows it failed.

### Failure policies (`FailurePolicy`)

`FAIL_FAST`, `CONTINUE`, `PARTIAL_SUCCESS`, `RETRY_FAILED`, `REQUIRE_QUORUM`.
`CONTINUE`/`PARTIAL_SUCCESS` end as `PARTIAL_SUCCESS` when some nodes failed;
incomplete work is never reported as a clean success (the result carries
`failed_tasks`, `coverage`, and per-node errors).

## Resources, retries, timeouts

- `ResourceManager` enforces a `global` limit plus per-class limits (`agent`,
  `llm`, `browser`, `code`, `database`, `network`, arbitrary `provider:<name>`).
  Admission is all-or-nothing; a node never half-acquires.
- `RetryPolicy`: `max_attempts`, exponential `backoff_ms`/`multiplier`/
  `max_backoff_ms`, `jitter`, and explicit `retryable_errors`/`non_retryable_errors`.
  Transient codes (`TASK_TIMEOUT`, `PROVIDER_ERROR`, `RATE_LIMITED`, …) retry by
  default; authorization/validation/argument errors do not.
- `timeout_ms` per node wraps the runner in `asyncio.wait_for`; a timeout marks the
  node `TIMED_OUT`, releases resources, and feeds the retry policy.

Limits come from `HARNESS_ORCH_*` env vars (`..._MAX_CONCURRENCY`,
`..._AGENT_CONCURRENCY`, `..._LLM_CONCURRENCY`, `..._BROWSER_CONCURRENCY`,
`..._CODE_CONCURRENCY`, `..._DATABASE_CONCURRENCY`, `..._NETWORK_CONCURRENCY`).

A node may declare `rateKey`; the engine draws a token from that bucket before
running and, when empty, fails the attempt with a retryable `RATE_LIMITED` so the
retry/backoff path applies.

### Batching

A tool/function node opts into scheduler-level batching with a `batch` block:

```json
{"tool": "get_quote", "args": {"symbol": "AAPL"},
 "batch": {"key": "quotes", "maxSize": 100, "argField": "symbols", "itemField": "symbol"}}
```

The scheduler groups every READY node that shares the batch key and identical
other arguments (up to `maxSize`) into **one call**, passing
`args[argField] = [each member's item]`; the returned list is fanned back out to
the members in order (a misaligned result fails them honestly). The
`task_map(batchSize)` and `task_batch` primitives build such nodes for "N items →
batches of B → concurrency C" workloads, so 10,000 symbols can become 100 calls of
100 instead of 10,000 requests.

## Deduplication and caching

Two nodes whose fingerprinted work is identical share a single execution
(tool/function nodes are fingerprinted automatically; an explicit `dedupKey`
overrides, `dedup: false` disables). Deduplication is **per execution** by default;
a node sets `dedupScope: "engine"` (or the engine default is changed) to share one
run across executions, process-wide.

Every shared key is scoped by **authorization** — the invoking run's authorized
tool set, user/tenant, and (for an agent node) the resolved provider/model. Two
nodes only share when they would run under equivalent authorization, so a shared
result can never cross a privilege or tenancy boundary. A node that is `cacheable`
with a positive `cacheTtlMs` reuses a fresh result for the whole TTL across
executions (same scoping). A failed owner never poisons a later retry: the shared
key is dropped on failure and the cache only ever holds successful, fresh values —
stale financial data is never served.

## Persistence and recovery

Everything lands on the ONE agent-memory connection (`OrchestrationExecution`,
`OrchestrationNode`, `OrchestrationEdge`, `OrchestrationAttempt`,
`OrchestrationEvent`, `OrchestrationLease`). Running nodes hold a lease that is
heart-beated. `OrchestrationEngine.recover()` re-drives executions left mid-flight:
completed nodes stay `COMPLETED`, running nodes are reset to `PENDING` (attempts
preserved), and the scheduler continues. Idempotent — a finished execution is
skipped.

**Credential-aware recovery.** Agent nodes need model credentials, which the
runtime resolves per run from the vault and never persists. When recovery has no
credentialed runtime, an execution containing agent nodes is **parked** (status
`PAUSED`, `metadata.awaitingRuntime`, event `EXECUTION_AWAITING_RUNTIME`) instead of
failing its agent work — tool/function executions still recover automatically. The
front door resumes it with credentials via
`POST /orchestration/executions/{id}/resume` (body: `modelSettings` and/or
`callbackBaseUrl`); `POST /orchestration/recover` accepts the same body to recover
agent work in one pass. Per-execution runtimes are honored, so recovery never
needs a process-wide provider config.

## Primitives and tools

`parallel_execute`, `task_fork`, `task_join`, `task_race`, `task_quorum`,
`task_map`, `task_batch`, `task_reduce`, `dependency_graph`, `execution_status`,
`execution_cancel` are defined in `orchestration/tools.py` and exposed over
`/orchestration/*`. They are deliberately **not registered on the booted tool
registry**: no built-in agent allowlist names them, so registering them only
advertised a surface the model could never call. `register_orchestration_tools`
still exists for an explicit future surface (and its own tests). A task spec is a plain mapping: `{id, kind,
tool|function|query, args, input, priority, timeoutMs, retry, resources,
dependsOn, join, dedupKey, dedupScope, shared, rateKey, batch, cacheable,
cacheTtlMs}`.

## Security

Children inherit least privilege: an agent node's tools are the **intersection** of
the invoking run's allowlist and the node's requested tools (`narrow_allowed`), and
a tool node is refused unless the name is in the run's allowlist — the same
`ToolRegistry.execute(allowed=...)` seam every other tool call uses.

## Observability

Events: `TASK_CREATED/READY/STARTED/COMPLETED/FAILED/RETRYING/CANCELLED/TIMEOUT/
BLOCKED/SKIPPED` and `EXECUTION_STARTED/PAUSED/RESUMED/COMPLETED/PARTIAL/FAILED/
CANCELLED`, persisted to `OrchestrationEvent` and published on the shared bus. The
result carries a per-node timeline and the true weighted critical path.

## Adding a node kind

Implement a runner strategy in `orchestration/runner.py` (return a `NodeOutcome`),
add the value to `NodeKind`, and expose it via the primitives/tools schemas. Never
add a second execution path — route through `execute_run` or `ToolRegistry.execute`.
