---
title: Execution Fabric
status: Current
last-verified: 2026-10-25
---

# Execution Fabric

**Who this is for:** anyone adding a background/long-running capability, a new
worker, a new queue, or asking "where does asynchronous work run in Eclipse?"

The Execution Fabric is the **common execution substrate** beneath the agent
runtime. It does not replace the agent loop, the tool registry, the orchestration
DAG engine, the automation engine, the event system, the plugins or the browser
runtime — it decides **HOW** a unit of work runs (inline, concurrent, background,
durable) and provides the queue, worker pool, retries, dead-letter queue,
idempotency, distributed locks, cancellation, priority and observability around
the existing capabilities.

It is implemented in `python/harness/fabric/`, on the ONE `agent-memory.db`
connection. No Redis, BullMQ or PostgreSQL is introduced: the runtime is a
single-process, zero-config, SQLite-backed Python service (AGENTS.md), and the
durable queue is native.

## The one rule

> Agents, tools, automations and events call `ExecutionManager`. They never
> enqueue directly, and workers never re-implement a capability — they invoke an
> existing one.

## Execution modes

| Mode | When | Flow |
|---|---|---|
| `DIRECT` | fast, no queue | caller → worker handler inline → result (not persisted) |
| `CONCURRENT` | caller waits, concurrency managed | enqueue → worker → await result |
| `BACKGROUND` | outlives the request | enqueue → worker → job id returned |
| `DURABLE` | must survive restart, idempotent | enqueue persisted + dedup → worker |

The mode comes from the job **type's policy** (`fabric/policies.py`) and may be
overridden per submission. Trivial work is never enqueued.

## Architecture

```
agent / tool / automation / event / JDdS
            |
     ExecutionManager          (fabric/manager.py)
            |
   DIRECT | CONCURRENT | BACKGROUND | DURABLE
            |
   FabricStore (SQLite, agent-memory.db)   WorkerManager (fabric/workers.py)
            |                                     |
     durable queue ────────────────────────> worker pool
                                                   |
              +-----------+-----------+------------+---------+
              |           |           |            |         |
            Agent       Browser     Python      Plugin   Notification
              |           |           |            |         |
              +-----------+-----------+------------+---------+
                                                   |
                                    existing capability
                     (service.run, ToolRegistry.execute, code.sandbox,
                      PluginManager, AutomationEngine, Event System)
```

## Job model & state machine

A job carries `id`, `type`, `queue`, `status`, `priority`, `taskId`,
`parentJobId`/`rootJobId`, `agentId`/`sessionId`/`userId`, `input`/`output`/
`error`, `progress`, `attempts`/`maxAttempts`, `timeoutMs`, `idempotencyKey`,
`correlationId`/`traceId`, `workerId`, `durable`, timestamps and `metadata`
(`fabric/models.py`).

Status is a **closed state machine** (`fabric/state.py`); every transition is
validated and an illegal one is refused:

```
CREATED → QUEUED → RUNNING → SUCCEEDED
                          → FAILED      → RETRYING → QUEUED
                                        → DEAD_LETTER → QUEUED (replay)
                          → TIMED_OUT
                          → CANCEL_REQUESTED → CANCELLED
QUEUED → PAUSED → QUEUED
```

`RETRYING`/`PAUSED` are delayed (re-queued at `availableAt`); `DEAD_LETTER`
holds exhausted retryable work for admin replay.

## Queues & priority

Queues are named (`user`, `agent`, `research`, `browser`, `scraping`, `market`,
`quant`, `python`, `code`, `plugin`, `notification`, `automation`, `event`,
`maintenance`, `graph`), each with a resource class and a default concurrency. Priority
weights: `USER_REQUEST` 1000 → `TRADING_ALERT` 900 → `AGENT_INTERACTIVE` 750 →
`RESEARCH` 500 → `INGESTION` 250 → `MAINTENANCE` 100. A large ingestion backlog
cannot starve an interactive request.

## Workers

`BaseWorker` declares `kind`, `queues`, `concurrency` and `handle(ctx)`.
`build_default_workers` wires one worker per domain, each delegating to an
existing capability:

| Worker | Delegates to |
|---|---|
| agent | `service.run` (a normal run) |
| tool | `ToolRegistry.execute` |
| research / browser / scraping / market / quant | a named tool, else an agent run |
| python / code | `code.sandbox` (isolated, cancellable) |
| plugin | `PluginManager.run_command` / plugin tool |
| notification | the live bus + Event System (in-app/SSE) |
| automation | the Automation Engine (`fire`) |
| event | the Event System / bus `publish` |
| graph | `GraphService.execute_job` — a durable Graph Studio run, resumed from node checkpoints |

`WorkerManager` runs `concurrency` consumer slots per worker, claims jobs
atomically, heartbeats leases, enforces timeouts, hard-cancels (propagating into
the handler), retries with exponential backoff + jitter, dead-letters exhausted
work, recovers orphaned jobs after a crash and drains on shutdown.

Graph runs use the same manager: a `graph` DURABLE job carries the IR, grants
and pinned subworkflow bundle. The worker runs the synchronous graph scheduler
in a thread and forwards cancellation. A node failure is recorded on the graph
run (the Fabric job succeeds; the queue must not retry a deterministic graph
failure). A worker/process crash is different: the lease expires, the job is
requeued, and `execute_job` resumes from the successful node checkpoints.

## Idempotency & locks

Durable jobs and idempotent policies derive a stable key from
`type + canonical(input)`; a second submission returns the existing job
(`deduplicated: true`). `DistributedLockManager` provides owner+token locks with
a TTL, safe release and expiry purge — for universe sync, ingestion, migrations
and plugin actions.

## Events & automation integration

`fabric/integrations.py` maps selected events to jobs (DATA, not code spread
across producers): `market.alert.triggered`/`PRICE_THRESHOLD_REACHED` →
notification; `earnings.released`/`EARNINGS_RELEASED` → research;
`plugin.connected`/`PLUGIN_CONNECTED` → market sync; `task.completed` →
notification. Job lifecycle publishes `fabric.job.*` on the shared bus and the
Event System, so both observability surfaces stay coherent.

## Configuration

All knobs are env-overridable with safe desktop defaults (`fabric/config.py`):

```
HARNESS_FABRIC_ENABLED              1|0
HARNESS_FABRIC_POLL_SECONDS         default 0.5
HARNESS_FABRIC_LEASE_SECONDS        default 120
HARNESS_FABRIC_MAX_ATTEMPTS         default 3
HARNESS_FABRIC_JOB_TIMEOUT_MS       default 120000
HARNESS_FABRIC_SHUTDOWN_TIMEOUT_S   default 20
HARNESS_FABRIC_DLQ_LIMIT            default 1000
HARNESS_FABRIC_LOCK_TTL_MS          default 30000
HARNESS_FABRIC_<QUEUE>_CONCURRENCY  per-queue worker count
HARNESS_FABRIC_RATE_<KEY>           rps,burst token bucket per key
```

## Surfaces

- **Agent tools** (`fabric/tools.py`, on the ONE registry): `fabric_submit`,
  `fabric_job_status`, `fabric_jobs_list`, `fabric_job_cancel`,
  `fabric_jobs_children`, `fabric_dlq_list`, `fabric_job_retry`,
  `fabric_workers`, `fabric_stats`.
- **HTTP admin API** (`python/harness/routers/fabric.py`, every route
  `require_operator`): `/fabric/{status,health,queues,metrics,workers,jobs,dlq}`
  plus `/fabric/jobs/{id}` and its `events`/`attempts`/`children`/`cancel`/
  `retry` and `/fabric/dlq/{id}/replay`.
- **UI console**: `/fabric` (`src/app/fabric/`) via the Next proxy
  `src/app/api/fabric/[[...path]]/route.ts` — Queues, Workers, Jobs (with a
  timeline + attempts detail), Dead letters and Metrics.

## Boot & recovery

`boot.py` calls `install_fabric_layer(service)` then `start_fabric(service)`
after the subsystems it works over (agent runtime, tools, automation, events,
plugins). `start_fabric` runs `recover()` first, re-driving any job whose worker
died. `stop_fabric` drains before the Event System stops so terminal
publications still reach a live bus.

## Adding a job type

1. Add an `ExecutionPolicy` in `fabric/policies.py` (mode, queue, timeout,
   retries, durability, idempotency).
2. Ensure a worker serves the queue — reuse a domain worker, or register a new
   `FunctionWorker` in `fabric/builtin_workers.py` that calls an existing
   capability.
3. Submit via `ExecutionManager.submit(type, payload, ...)` or the
   `fabric_submit` tool.

## Adding a worker

Subclass `BaseWorker` (or wrap a handler in `FunctionWorker`) and register it on
the `ExecutionManager` (or add it to `build_default_workers`). The manager owns
claiming, leases, retries, DLQ, cancellation and metrics — a worker only
implements `handle(ctx)` and returns a `WorkerOutcome`.

## Tests

`python/tests/test_fabric_{state,store,workers,manager,integration}.py` — the
state machine, atomic claim/priority/leases/locks/idempotency, retry/DLQ/
timeout/cancellation/concurrency/recovery/graceful-shutdown, the four execution
modes, DAG-delegation unavailability, the event rules, the builtin workers
against a stub runtime + the real sandbox, and the HTTP router round-trip.
`src/lib/harness/fabric-types.test.ts` covers the console's pure helpers.
