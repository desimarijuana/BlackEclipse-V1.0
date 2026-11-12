---
title: Core Architecture — the five ones and the invariants
status: Current
last-verified: 2026-11-12
---

# Core Architecture

**This file is authoritative for the core-loop shape.** Other docs explain a
subsystem; this one states the invariants a change must not break. If code and
this document disagree, the code wins and this document is fixed.

## The five "ones"

| One | Owner | Invariant |
|---|---|---|
| **One loop** | `python/harness/graph.py` | A run is one LangGraph loop: model turn → tool turn → repeat, with one run deadline, one retry policy, one step budget. No second agent loop. |
| **One execution plane** | `harness/execution_plane.py`, `harness/fabric/` | Every child execution (delegation, team, A2A, spawn) is a Fabric job. No direct `execute_run` bypass. |
| **One event log** | `harness/events.py`, `harness/execution_log.py`, `harness/persistence.py` | State changes are published once and persisted once; the observability projector and the SSE stream read the same events. |
| **One policy seam** | `harness/security/gateway.py` | Every effectful operation is an `AuthorizationRequest` answered by one gateway. Sandbox profiles, effect tokens and the floor are enforced there and at the executor. |
| **One agent contract** | `harness/spawn/`, `harness/goals/` | A child is a Fabric `agent` job with a `parentRunId`, a budget and evidence claims; the parent merges deterministically. |

## Loop invariants

1. **Exactly one terminal state** per run: `completed`, `failed` or `cancelled`.
   Every failure path writes one terminal result; a crash resumes or is counted
   as an orphan.
2. **No duplicate irreversible effect.** `RunEffects.begin` is written before an
   effectful call; a resumed `started` row is `unknown`, never retried.
3. **The run deadline is wall-clock**, checked before every model call; a retry
   that would cross it is refused.
4. **Retries are bounded and classified** (`retry_policy.py`): cancellation is
   never retried, 4xx auth/bad-request are never retried, a provider
   `Retry-After` is honored.
5. **Step is observable.** Each loop iteration emits `step.started/completed`;
   the span tree is `run → step → llm/tool`.

## Execution invariants

1. A child runs as a Fabric job with `parentRunId`; depth ≤ 2, fanout ≤ 8, total
   child tokens ≤ 120k, budget reconciled as `allocated = used + returned`.
2. A child inherits user/workspace/session, never an operator grant or autonomy.
3. The parent merges child claims deterministically; a contradiction is surfaced,
   never blended.
4. The blackboard is one per root run, bounded (200 entries / 200k chars), and
   reachable only by walking `parentRunId`.

## Safety invariants (C6)

1. Auth is required outside loopback; loopback `npm run dev` stays zero-config.
2. A configured sandbox profile the host cannot enforce is a refusal at the
   gateway and at the terminal/background/computer executors.
3. Every effectful call is bound to an effect token (`off | shadow | enforce`);
   the executor verifies it before the handler runs.
4. The engine handles path traversal, env exfiltration, fork bombs and raw
   egress; the escape suite is `test_c6_escape.py`.
5. Plugin installs pass a signature + review gate; untrusted plugins run in a
   separate process.

## Observability invariants (C7)

1. Every run exports a `run → step → llm/tool` tree; every failure carries one
   class from `observability/failures.py`.
2. Cost is attributed per run and step from provider usage; an unknown model is
   `priced: false`, never a fabricated zero.
3. Five SLOs have budgets (terminal correctness, p95 latency, resume p95, orphan
   rate, cost/task); `npm run gate:slo` fails CI on a breach or regression.
4. The dashboard is derived from the same report the gate reads.

## Evidence invariants (C4/C8)

1. A claim without a handle is rejected by the verifier registry; a finance
   number needs a computation/report/citation/record.
2. The scorecard is generated from runs (`npm run scorecard:from-runs`), never
   typed; every measured dimension carries `{value, source, runId}`.
3. Conformance (`gate:conformance`) covers retry faults, a golden trace and
   contracts; external benchmark data is opt-in and a missing download is
   `unavailable`, never a pass.

## Wiring map

```
Next.js front door ──> FastAPI (python/harness/main.py)
                         ├── AgenticService (service.py)
                         │     ├── graph.execute_run (the ONE loop)
                         │     ├── tools registry (tools.py)
                         │     ├── security gateway (security/)
                         │     └── observability hub (observability/)
                         ├── Fabric (fabric/) ── agent/graph/task workers
                         └── routers/ (runs, events, observability, security…)
```

## What must not be added

- A second agent loop, scheduler, retry vocabulary or approval path.
- A telemetry stack outside `observability/`.
- A direct child `execute_run` call outside the Fabric.
- A typed scorecard number with no run/source.
- A sandbox promise the host cannot enforce.
