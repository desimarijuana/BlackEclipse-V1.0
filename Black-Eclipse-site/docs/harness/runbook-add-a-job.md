---
title: Runbook — add a scheduled job
status: Current
last-verified: 2026-10-01
---

# Runbook — add a scheduled job

**Who this is for:** the person adding a job at 09:00 on a Monday.

A **job** is a durable, reviewable intent to run something later: on a cadence, on
a file change, or when its web address is called. It is DATA. It holds no
executable code and can never widen authority — the run it produces is subject to
exactly the same permission, allowlist and policy checks as a run you start by
hand.

## 1. Add it

Two paths, both in the app (`src/components/screens/jobs/`):

1. **From the library** — pick a ready-made finance job ("Overnight news on my
   holdings") and answer its question ("which tickers?"). This is the path a
   non-expert meets.
2. **From the editor** — name it, describe what it should do, choose a cadence,
   and pick how it should tell you: *In the app*, *Save it as a report*, or
   *Send it to my phone* (give the destination a name, e.g. "My phone").

A job is created **disabled**. Discovery is not activation: turn it on when you
are ready.

Under the hood the runtime writes a `HarnessJob` row in `agent-memory.db`
(`python/harness/jobs/store.py`). The editor never shows you a cron expression, a
skill id or an adapter name — those live behind "details".

## 2. What to check when it does not fire

| Symptom | First look | What it means |
|---|---|---|
| "Hasn't run yet" | the job's **enable** state | a disabled job never fires |
| Missed a window | the run history: a `skipped` row with a plain reason | Eclipse was closed when it was due; `on_missed` decides `skip` or `run_once` |
| A run is still going | run history has a `running` row | this round was skipped so two copies never overlap |
| It failed a few times | the **breaker** banner on the job | after `FAILURE_THRESHOLD` failures the breaker opens and pauses the job |

The scheduler is one process, one tick (`python/harness/jobs/scheduler.py`); it is
started by the runtime lifespan and reuses `mcp/circuit.py` for the breaker.
Missed runs are reconciled **once** at startup, never silently.

## 3. Read a breaker state

| State | Plain meaning | Next step |
|---|---|---|
| `closed` | working normally | nothing |
| `open` | paused after repeated trouble | fix the cause, then **Restart this job** |
| `half_open` | one probe run is allowed | watch the next run |

Only an operator restart (`POST /jobs/{id}/reset-breaker`, operator-gated) closes a
breaker. A breaker never resets itself.

## 4. Delivery

A job may be configured with one or more destinations. Each destination receives
the job **independently** and records its **own** outcome on the run row (Phase 11):
one row per target, never one rolled-up boolean. A failed destination never fails
the run — it is recorded and shown as one plain sentence with a next step.

- *In the app* — a notification on the app's event stream.
- *Save it as a report* — a saved report under `.black-eclipse/artifacts/<runId>/`.
- *Send it to my phone* — a message rendered from a template key (the runtime
  sends a key + parameters, never a composed sentence). With no destination chosen
  it refuses with `NO_DESTINATION` — it never sends to a default you did not choose.

## 5. Where the pieces live

| Piece | File |
|---|---|
| Job model | `python/harness/jobs/model.py` |
| Store (tables) | `python/harness/jobs/store.py` |
| Scheduler | `python/harness/jobs/scheduler.py` |
| Save-time rules | `python/harness/jobs/guardrails.py` |
| Routes | `python/harness/routers/jobs.py` |
| Front door | `src/lib/harness/jobs-client.ts`, `src/app/api/jobs/**`, `src/components/screens/jobs/**` |
| Tests | `python/tests/test_jobs_{cron,scheduler,api,guardrails}.py` |

The three TypeScript refresh loops are untouched; this job model sits beside them
(ADR-H108).
