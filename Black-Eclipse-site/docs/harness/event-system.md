---
title: Event System
status: Current
last-verified: 2026-10-08
---

# Event System

The Event System is Eclipse's durable, reactive nervous system. It is the ONE
canonical event model: every subsystem publishes through it, every consumer
subscribes through it, and every event is validated, redacted and persisted
before it is delivered.

**Who this is for:** anyone publishing an event, adding a consumer, debugging a
flow, or operating the console.

## What exists already (and what this adds)

The runtime already had **fragments** of event handling, and this subsystem
unifies them rather than replacing them:

| Existing | Role now |
|---|---|
| `python/harness/events.py` (`EventBus` + `RunEmitter`) | the **live run bus** — the low-latency per-run SSE fan-out. It stays exactly as it is. |
| `orchestration/events.py`, `tasks` `HarnessTaskEvent`, `automation` execution events | subsystem-local persisted histories. They keep their own ledgers. |
| `AutomationEngine` event-trigger routing | the durable rule engine; the Event System **feeds** it and exposes a one-call bridge to declare rules. |

What was missing — and this subsystem adds — is a **canonical envelope**, a
**centralized registry**, a **durable, indexed event store** queryable by
correlation/causation/task/workflow/agent, **consumer idempotency**, a real
**dead-letter queue**, **replay**, **metrics**, **security** and a **console**.

There is **one** transport abstraction (the run bus) and **one** event model
(canonical `EclipseEvent`). The `EventBus` in `event_system/bus.py` **bridges**
to the live run bus: it ingests every legacy event and echoes new typed events
back, so there is no second bus and no dead consumer.

## Layers

```
python/harness/event_system/
  envelope.py    EclipseEvent (canonical), Actor, correlation/causation context,
                 from_legacy(), secret redaction
  registry.py    EventRegistry + EventTypeSpec (schema, producer, consumers,
                 permission, priority, retention, retry, delivery, sensitivity)
  filters.py     exact / namespace-wildcard / predicate subscriptions
  store.py       durable store: HarnessEventLog + Consumer + DeadLetter +
                 Subscription tables on agent-memory.db (indexed columns)
  metrics.py     counters + p50/p95/p99 latency (bounded reservoir)
  middleware.py  composable publish stages (validation → authorization →
                 redaction → enrichment → tracing → logging)
  security.py    publish/subscribe authorization + sanitize()
  bus.py         publish/subscribe core: async workers, backpressure,
                 idempotency, retry, DLQ, request/reply, legacy bridge
  rules.py       EventRuleBridge — event → action rules via the Automation Engine
  replay.py      observe / simulation / full replay
  service.py     EventSystem facade + built-in consumers + market sampler
  bootstrap.py   install/start/stop on the AgenticService
```

Related: routes `python/harness/routers/events.py` (`/events/*`),
`src/lib/harness/events-client.ts`, `src/app/api/events/[[...path]]/route.ts`,
the standalone console at `/events`.

## The event envelope

An event describes something that **already happened** (past tense). Commands
request actions, tasks hold work state, workflows orchestrate — they are distinct
and never collapsed.

```python
EclipseEvent(
    id, type, version=1, timestamp, source,
    correlation_id, causation_id, trace_id, actor,
    session_id, task_id, workflow_id, agent_id,
    priority, payload, metadata, depth, replay,
)
```

* `id` — globally unique (`evt_<uuid>`), immutable event identity.
* `timestamp` — UTC ISO-8601.
* `type` + `version` — the contract identity.
* `depth` — how many causation hops deep; used for loop prevention.

### Correlation and causation (automatic)

Every user-initiated execution receives a correlation id. Follow-up events
inherit it **without the developer threading ids through every call** — the
bus runs each handler inside `event_context(...)` and `EclipseEvent.create`
reads that context:

```python
with event_context(correlation_id="ABC"):
    await bus.publish(EclipseEvent.create("task.created", {"taskId": "t1"}))
```

`EclipseEvent.child("...")` sets `causation_id` to the parent's id and
`depth = parent.depth + 1`.

## Event naming

Names are hierarchical, dot-separated, and declared **once** in the registry —
never scattered as magic strings. Examples:

```
system.started          task.created           workflow.started
agent.failed            tool.completed          process.failed
file.changed            research.completed      market.price.updated
filing.discovered       portfolio.position.added risk.threshold.breached
backtest.completed      strategy.signal.generated schedule.triggered
memory.created          evaluation.completed    model.failed
```

Namespaces (`browser.**`, `code.**`, `market.**`, `document.**`, `vision.**`,
`mcp.**`, `git.**`, …) share one policy without enumerating every sub-event.

## The registry

`event_system/registry.py` declares, per type or namespace: version, payload
schema (`required_fields`, `field_types`), producer, allowed consumers,
permission, priority, retention, retry policy, delivery mode and sensitivity.
The registry **validates** events and **discovery** (`GET /events/registry`).
An event with an unknown type is refused by the typed publish path; the legacy
ingest bridge **auto-registers observed namespaces** so no event is silently
lost.

## The bus

`publish()` / `publish_many()` / `subscribe()` / `unsubscribe()` / `once()` /
`request()`.

Publish pipeline: **validation → authorization → redaction → enrichment →
persistence → routing → delivery → metrics**. Empty per-subscription queues apply
**backpressure**: `critical`/`high` events wait (bounded); `bulk`/`low` events
are dropped with a metric, so a price storm can never stall a run.

Delivery modes: `sync` (inline), `async` (per-subscription worker),
`at_least_once`, `best_effort`. A consumer that declares itself idempotent
skips an already-processed `(eventId, consumerId)` pair. Handlers are invoked
with a global concurrency semaphore (`EVENT_MAX_CONCURRENCY`, default 16).

## Retry, dead letters and idempotency

* Retry: exponential backoff + jitter (`RetryPolicy`), **non-retryable error
  classes are never retried** (reuses `automation.model`'s classification).
* Dead-letter: exhausted deliveries are persisted with event, consumer, error,
  error class, attempts, first/last failure time and stack trace.
* Idempotency: `HarnessEventConsumer` records `(eventId, consumerId)`; a
  duplicate delivery does not re-run the handler.

## Replay

`POST /events/replay` with `mode`:

* `observe` — return the matched events, deliver nothing.
* `simulation` — report which subscribers **would** run, deliver nothing.
* `full` — re-publish to real subscribers. Requires operator authorization and,
  for destructive/financial types, `confirmDestructive`.

A replayed event is a **new** event (new id, `replay=true`,
`metadata.originalId` set), so idempotency keys on the new id and the replay
actually fires.

## Security

* Publishing or subscribing to a `sensitive` event requires an operator actor.
* An event's declared `permission` is checked against the actor's resolved
  grants (`skills.permissions`).
* Payloads and metadata are **redacted** (secret keys + value patterns) as a
  publish middleware — a secret can never reach the event store.
* Event payloads never execute commands; rule actions dispatch through the
  ordinary run path, subject to the same permission/allowlist checks.

## Financial / high-frequency events

`market.price.updated` is `bulk` priority and `best_effort`. The built-in
**MarketSampler** coalesces ticks per symbol and emits one
`market.snapshot.updated` per interval (bounded symbol count), so a price tick
can **never** cause one LLM call. Subscribers can additionally sample with a
predicate filter (e.g. `payload.changePercent > 5`).

## Built-in consumers

* **Memory candidate extractor** — selected durable events (`task.completed`,
  `run.completed`, `research.completed`, `evaluation.completed`,
  `memory.updated`) become bounded `memory.candidate.created` events. The Event
  Store is **never** agent memory; a candidate must pass the memory subsystem's
  own gates.
* **Self-improvement trigger** — failures (`task.failed`, `agent.failed`,
  `tool.failed`, `workflow.failed`, `run.failed`, …) request an
  `evaluation.started` **at most twice per correlation** and never past
  `MAX_CAUSATION_DEPTH = 6`, so `failure → analyzer → failure` cannot loop.
* **Market sampler** — see above.

## Publishing from code

```python
# async code (the normal case)
await service.events.publish("task.completed", {"taskId": t.id}, source="tasks",
                             correlation_id=corr, task_id=t.id)

# synchronous seam (fire-and-forget onto the loop)
service.events.emit_nowait("filing.discovered", {"ticker": "AAPL"}, source="research")

# subscribe
service.events.subscribe("task.completed", handler, consumer_id="my.consumer")
```

The legacy run bus keeps working unchanged; its events are ingested
automatically (with known legacy names normalized — e.g. `terminal.process.*`
becomes canonical `process.started/completed/failed`).

### Event families emitted at source

| Family | Emitted from |
|---|---|
| `run.*`, `model.*`, `tool.*`, `research.*`, `browser.*`, `code.*`, `delegation.*` | the run bus, ingested by the bridge |
| `task.*`, `workflow.*` (plans) | `tasks/bootstrap.py` |
| `schedule.triggered` | `automation/engine.py` |
| `process.*` | terminal process lifecycle (normalized from `terminal.process.*`) |
| `file.created/changed/deleted` | the workspace watcher (`code/fs/service.py`), debounced |
| `portfolio.position.added/updated/removed` | `portfolio/service.py` |
| `memory.created/updated` | `eclipse_memory/service.py` |
| `backtest.started/completed/failed` | `quant/runner.py` |
| `market.snapshot.updated` | the bus's own `MarketSampler` |

A subsystem without a bus handle publishes with the thread-safe emitter:
`from ..event_system.emit import publish_event`. Every remaining registered type
(e.g. `filing.*`, `fundamental.*`, `strategy.signal.generated`) can be published
the same way or via `POST`/the facade, and is ingested from the legacy bus when
its subsystem emits it.

## Operating the console

`/events` (standalone route) shows History, Live tail, Event detail,
Subscriptions, Dead letter, Replay, Graph, Metrics and Registry. The same data
is on the operator-gated API:

```
GET  /events?correlationId=…            GET  /events/{id}
GET  /events/graph?correlationId=…       GET  /events/metrics
GET  /events/registry                    GET  /events/types
GET  /events/subscriptions               POST /events/subscriptions
GET  /events/dlq                         POST /events/dlq/{id}/retry
POST /events/dlq/{id}/discard            POST /events/replay
GET  /events/rules                       POST /events/rules
```

`event_system/metrics.py` exposes `published/processed/delivered/failed/
retried/deadLettered/deduplicated/droppedBackpressure` and p50/p95/p99
processing + queue latency, folded into `/events/metrics`.

## Configuration

All values have safe defaults (`event_system/config.py`); a bad value falls back
rather than crashing boot.

| Env | Default | Meaning |
|---|---|---|
| `EVENT_BUS_ENABLED` | on | start the Event System at boot |
| `EVENT_STORE_ENABLED` | on | persist events (off ⇒ live-only, no durable log) |
| `EVENT_DEDUPLICATION_ENABLED` | on | consumer-level idempotency checks |
| `EVENT_REPLAY_ENABLED` | on | allow replay (still operator-gated) |
| `EVENT_ECHO_LEGACY` | on | echo new typed events to the live run bus |
| `EVENT_MAX_CONCURRENCY` | `16` | global handler concurrency |
| `EVENT_MAX_RETRIES` | `5` | default consumer retry attempts |
| `EVENT_MAX_QUEUE` | `1000` | per-consumer queue bound (backpressure) |
| `EVENT_RETENTION` | `30` (days) | event-log retention swept on boot |

The store is `agent-memory.db` (never `jdds.db`/`eclipse-memory.db`); the DDL is
idempotent and applied on first use, so a fresh install and an existing database
both work with no manual step.

## Degradation contract

If the event store cannot be opened the Event System reports itself stopped and
the rest of the harness boots normally — it never blocks boot and never
fabricates data. A handler failure is recorded (attempt → retry → dead letter);
it never crashes the publisher.

## Tests

`python/tests/test_events_core.py` (envelope/registry/filters/store/security),
`test_events_bus.py` (delivery/idempotency/retry/DLQ/backpressure/request-reply/
legacy bridge/shutdown), `test_events_service.py` (built-in consumers, loop
guard, market sampler, replay, rule bridge) and `test_events_api.py`
(the console API).
