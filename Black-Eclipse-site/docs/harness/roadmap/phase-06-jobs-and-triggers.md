---
title: "Phase 6 — Harness-Owned Jobs and Event Triggers"
status: Not started
phase: 6
depends_on: [5]
unlocks: [11]
last-verified: 2026-09-30
---

# Phase 6 — Harness-Owned Jobs and Event Triggers

| | |
|---|---|
| **Depends on** | Phase 5 (a settled agent/tool surface to schedule) |
| **Unlocks** | Phase 11 (delivery to other surfaces) |
| **Estimated work** | 6–10 h of agent time |
| **Deliverable type** | new `jobs/` package + route group + 2 tables + job templates |
| **New ADRs** | ADR-H108 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the real gap)](#2-why-this-phase-exists-the-real-gap)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The definition — `python/harness/jobs/model.py`](#61-the-definition--pythonharnessjobsmodelpy)
  - [6.2 Persistence — `HarnessJob` / `HarnessJobRun` (`agent-memory.db`)](#62-persistence--harnessjob--harnessjobrun-agent-memorydb)
  - [6.3 The scheduler — `python/harness/jobs/scheduler.py`](#63-the-scheduler--pythonharnessjobsschedulerpy)
  - [6.4 Cron parsing — `jobs/cron.py` (stdlib only)](#64-cron-parsing--jobscronpy-stdlib-only)
  - [6.5 Triggers — `python/harness/jobs/triggers.py`](#65-triggers--pythonharnessjobstriggerspy)
  - [6.6 Routes — `python/harness/routers/jobs.py`](#66-routes--pythonharnessroutersjobspy)
  - [6.7 Guardrails (enforced in code, at save time)](#67-guardrails-enforced-in-code-at-save-time)
  - [6.8 Delivery — `jobs/delivery.py`](#68-delivery--jobsdeliverypy)
  - [6.9 The finance job library — `jobs/templates.py` (data)](#69-the-finance-job-library--jobstemplatespy-data)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Give the harness its own **durable job model** so finance work runs on a cadence
and on events — a morning portfolio brief, a filing watch, a data-freshness
watchdog, a code task — without a human opening the app.

This is the phase that turns Eclipse from a *tool you operate* into a *harness
that operates*.

## 2. Why this phase exists (the real gap)

Scheduling in this repo today is **entirely on the TypeScript side**, and it does
one thing: refresh data. Verified paths:

| Existing scheduler | What it does |
|---|---|
| `src/lib/scraper/scheduler.ts` | drives the scraper's ingest loop |
| `src/lib/connectors/refresh-scheduler.ts` | refreshes connector data |
| `src/lib/investor-eye/scheduler.ts` | drives the Investor Eye feed |

Nothing there can run an **agent**. There is no job model, no run history, no
delivery, and no way to express *"every weekday at 07:30, run the portfolio-brief
skill and tell me what changed."* `ExecutionMode` includes a `scheduled` literal
(`python/harness/skills/manifest.py`) — the *type-level* intent exists with nothing
behind it.

Two existing pieces already do the hard parts, and this phase reuses both rather
than inventing:

- **Run execution + traces + persistence** — `execute_run`, `HarnessRun`,
  `RunEmitter`. A job run is a normal run with a job id attached.
- **Failure containment** — `python/harness/mcp/circuit.py` is a proven
  CLOSED/OPEN/HALF_OPEN breaker with named thresholds and an operator reset. A job
  that keeps failing should use *that shape*, not a second backoff implementation.

**Explicitly additive.** The three TS schedulers stay exactly as they are; this
phase adds the harness job model **beside** them and says so in the ADR. Replacing
them is not in scope and would be a regression risk with no user-visible benefit.

## 3. In scope

1. `python/harness/jobs/` — `model.py`, `store.py`, `scheduler.py`, `triggers.py`.
2. Two tables in `agent-memory.db`: `HarnessJob`, `HarnessJobRun`.
3. A route group `python/harness/routers/jobs.py` registered by `main.py`.
4. A delivery-adapter interface + an in-app and saved-artifact adapter.
5. A finance **job library** (templates), plus skill-backed jobs.
6. Guardrails: permission binding at save time, breaker on repeated failure,
   workspace confinement for code jobs, an explicit missed-run policy.

## 4. Who can use it (the non-expert obligation)

This is the **most user-visible phase in the roadmap**, so the audience rule bites
hardest here: a portfolio manager must be able to set up a morning brief without
ever meeting the word "cron".

1. **Cadence in human language.** The editor offers "Every weekday at 7:30am",
   "Every 6 hours", "When a file in this folder changes", "When something calls
   this web address" — and shows the raw expression only behind "details". The
   cron string is data, never a field a non-expert must author.
2. **Templates, not definitions.** The seven library jobs (§6.9) are
   **one-click**: the user answers "which tickers?" / "which folder?" and their
   job is built. They never author a `JobTarget` or pick a skill id by hand.
3. **The job's own name is the user's words.** A job is labelled by the user's
   description ("Overnight news on my holdings"), not by its skill id or kind.
4. **Failure is one plain sentence with a next step.** A breaker-opened job says
   *"This job has failed 3 times, so I paused it. Here's what each attempt said."*
   A permission refusal says *"This job needs to read market data, which isn't
   allowed for it yet."* The machine reason stays on the run row.
5. **Delivery reads like a message, not a log.** The in-app/artifact adapters
   render the run's answer plus a plain outcome line ("Ran at 7:30am · 12 seconds ·
   delivered"), never exit codes or digests.
6. **All strings via i18n keys** in `src/lib/i18n/` — this is also what makes the
   job library translatable, which matters because the finance audience is global.
7. **The plain-language gate** (§9 G7) covers the job editor, the library copy and
   the delivery templates against `policy.PLAIN_LANGUAGE_DENYLIST`.

## 5. Non-goals (do not do these)

- No distributed scheduler, no multi-node, no leader election.
- No replacement or modification of the three TS schedulers.
- No new scheduling dependency — a minimal stdlib cron matcher, not `croniter` /
  `APScheduler`.
- No unbounded concurrency: a job run is one run.
- No job that can raise its own permissions or enable a skill.
- No job with `approve_external` unless an operator explicitly set it.
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 The definition — `python/harness/jobs/model.py`

```python
"""A job is a durable, reviewable intent to run something later.

It is DATA. A job never holds executable code, never holds a prompt body that
grants anything, and never widens authority: it references a skill (by id +
version) or an objective + agent id, and the run it produces is subject to exactly
the same permission, allowlist and policy checks as a user-initiated run.
"""

JobKind = Literal["cron", "interval", "file_watch", "webhook", "manual"]
OnMissed = Literal["skip", "run_once"]           # both recorded; never silent
JobTargetKind = Literal["skill", "objective"]

class JobTarget(BaseModel):
    kind: JobTargetKind
    skill_id: Optional[str] = None
    skill_version: Optional[str] = None          # pinned; a job is reproducible
    objective: Optional[str] = Field(None, max_length=4000)
    agent_id: str = "eclipse-agent"
    # Code jobs only. Absent ⇒ a research/analysis job.
    workspace_root: Optional[str] = None
    autonomy: Optional[Literal["plan_only", "edit_verify", "approve_external"]] = None

class JobDelivery(BaseModel):
    adapter: Literal["in_app", "artifact"] = "in_app"
    title: Optional[str] = Field(None, max_length=200)
    # Phase 11 adds "messaging"; unknown adapter ⇒ refused at save time.

class JobDefinition(BaseModel):
    id: str                                       # uuid4 hex, server-assigned
    name: str = Field(..., max_length=120)
    kind: JobKind
    cron: Optional[str] = None                    # 5-field, validated by §6.4
    interval_seconds: Optional[int] = Field(None, ge=60, le=30 * 24 * 3600)
    watch_path: Optional[str] = None              # file_watch; must be inside a workspace
    webhook_token_hash: Optional[str] = None      # webhook; SHA-256, never the token
    timezone: str = "local"                       # "local" or an IANA name
    on_missed: OnMissed = "skip"
    target: JobTarget
    delivery: JobDelivery = JobDelivery()
    enabled: bool = False                         # discovery is not activation
    max_runtime_s: int = Field(900, ge=30, le=7200)
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None
    consecutive_failures: int = 0
    breaker: Literal["closed", "open", "half_open"] = "closed"
    breaker_opened_at: Optional[str] = None
    breaker_reset_by: Optional[str] = None        # operator id, or None
```

**Mirrors an existing, proven convention:** `enabled` defaults to **False** and a
job does nothing until an operator enables it — the same rule MCP applies
(*"discovery is not activation"*, ADR-H39). A job is the most consequential thing
in this file, so it inherits the strictest existing default.

### 6.2 Persistence — `HarnessJob` / `HarnessJobRun` (`agent-memory.db`)

Additive, idempotent, in the same style as every other table in
`python/harness/persistence.py`. If `persistence.py` is at its ratchet, the
read/write helpers go in `jobs/store.py` bound to the single `AgentMemoryStore`
connection — exactly the ownership pattern `run_lineage.py` documents for its own
tables.

```sql
CREATE TABLE IF NOT EXISTS HarnessJob (
  id                   TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,
  kind                 TEXT NOT NULL,
  cron                 TEXT,
  intervalSeconds      INTEGER,
  watchPath            TEXT,
  webhookTokenHash     TEXT,
  timezone             TEXT NOT NULL DEFAULT 'local',
  onMissed             TEXT NOT NULL DEFAULT 'skip',
  targetJson           TEXT NOT NULL,     -- JobTarget
  deliveryJson         TEXT NOT NULL,     -- JobDelivery
  enabled              INTEGER NOT NULL DEFAULT 0,
  maxRuntimeS          INTEGER NOT NULL DEFAULT 900,
  createdAt            TEXT NOT NULL,
  updatedAt            TEXT NOT NULL,
  consecutiveFailures  INTEGER NOT NULL DEFAULT 0,
  breaker              TEXT NOT NULL DEFAULT 'closed',
  breakerOpenedAt      TEXT,
  breakerResetBy       TEXT
);

CREATE TABLE IF NOT EXISTS HarnessJobRun (
  id            TEXT PRIMARY KEY,
  jobId         TEXT NOT NULL,
  runId         TEXT,                    -- the harness run this job produced
  triggeredBy   TEXT NOT NULL,           -- 'schedule' | 'webhook' | 'file_watch' | 'manual'
  scheduledFor  TEXT NOT NULL,
  startedAt     TEXT NOT NULL,
  finishedAt    TEXT,
  status        TEXT NOT NULL,           -- 'running'|'ok'|'failed'|'skipped'|'timed_out'|'refused'
  outcomeReason TEXT,                    -- non-secret, operator-facing
  deliveryJson  TEXT,                    -- per-adapter outcome
  missed        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobrun_job ON HarnessJobRun(jobId, startedAt);
```

`runId` links to the existing `HarnessRun` row — **the job run is a normal run**
with a trace, events, tool executions and (for code jobs) a verification ledger.
Never a second execution record.

### 6.3 The scheduler — `python/harness/jobs/scheduler.py`

One lifespan task, started from the existing FastAPI lifespan
(`main._lifespan` → `AgenticService`), alongside `start_mcp()`/`run_startup_maintenance`:

```python
class JobScheduler:
    """Single-process durable scheduler. One tick at a time; no overlap.

    Durability rule: a job that SHOULD have fired while the process was down is
    reconciled ONCE at startup against HarnessJobRun — never silently skipped. The
    job's on_missed policy decides what happens and the decision is always
    recorded, so "it didn't run" is never a mystery.
    """

    async def start(self) -> None: ...       # in the lifespan; idempotent
    async def stop(self) -> None: ...        # cancels in-flight runs cooperatively
    async def _tick(self) -> None: ...       # every 30s: due jobs → launch (bounded)
    async def _reconcile_missed(self) -> None: ...
    async def _apply_breaker(self, job, outcome) -> None: ...
```

**Rules the implementation must enforce:**

| Rule | Behaviour |
|---|---|
| No overlap | A job already `running` is not re-launched; the tick records `skipped` with the reason. |
| Bounded concurrency | At most N job runs in flight (default 2 — this is a desktop app, not a server). |
| Missed runs | Reconciled once at startup per `on_missed`; every decision recorded with `missed=1`. |
| Runtime cap | `max_runtime_s` → cooperative cancel, then `timed_out`; never a zombie. |
| Breaker | Consecutive failures ≥ threshold → `open`, skip with a recorded reason, re-probe once after a cooldown, operator reset. Reuse `mcp/circuit.py`'s thresholds and states rather than new constants. |
| Timezone | `local` or a named zone; the resolved next-fire time is stored on the run row so a DST change is auditable. |

### 6.4 Cron parsing — `jobs/cron.py` (stdlib only)

A minimal **5-field** matcher (`minute hour dom month dow`), supporting `*`, `N`,
`a-b`, `a,b,c` and `*/N`. ~120 lines, ~20 tests. Deliberately not a dependency:
the repo's standing rule is *"Do not add dependencies without justification;
prefer the lighter option"* (`AGENTS.md`), and a full cron library is not
justified by 5-field expressions.

It must refuse, with a specific error: a 6-field (seconds) expression, a
`@reboot`-style macro, a name alias (`MON`), and any field that does not parse.
`next_fire(after: datetime) -> datetime` is pure and exhaustively tested
(including Feb 29 and a DST boundary).

### 6.5 Triggers — `python/harness/jobs/triggers.py`

Three inbound paths, all of which enqueue exactly what the scheduler would:

| Trigger | Mechanism | Auth |
|---|---|---|
| `file_watch` | a bounded poller over `watch_path` (mtime+size hash), inside an existing workspace root | n/a — local path, policy-checked |
| `webhook` | `POST /jobs/{id}/trigger` | the job's token, compared as a **SHA-256 hash**; the token is shown once at creation and never stored |
| `manual` | the UI / route | `require_operator` |

A webhook trigger carries **no parameters that can change the job** — it fires the
stored definition or nothing. A body cannot select a skill, raise a budget, or
widen a permission. This is the same "an inbound message can never widen
authority" rule the MCP layer applies to server results.

### 6.6 Routes — `python/harness/routers/jobs.py`

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — never by importing `main`.

| Method + path | Auth | Purpose |
|---|---|---|
| `GET /jobs` | `require_operator` | list definitions + last run |
| `POST /jobs` | `require_operator` | create (validates permissions §6.7, cron §6.4) |
| `PATCH /jobs/{id}` | `require_operator` | update; absent means preserve (copy the MCP round-trip rule) |
| `DELETE /jobs/{id}` | `require_operator` | delete; run history is retained |
| `POST /jobs/{id}/enable` · `/disable` | `require_operator` | activation is explicit |
| `POST /jobs/{id}/run` | `require_operator` | manual fire now |
| `POST /jobs/{id}/trigger` | job token (hashed) | webhook entry |
| `POST /jobs/{id}/reset-breaker` | `require_operator` | the operator reset |
| `GET /jobs/{id}/runs` | `require_operator` | history |
| `GET /jobs/templates` | `require_operator` | the finance job library |

**Every route carries `require_operator` — reads and mutations**, exactly as the
MCP route group was hardened to do (ADR-H48). A directly reachable runtime must
not expose job control to an unauthenticated caller.

### 6.7 Guardrails (enforced in code, at save time)

1. **Permission binding.** A skill-backed job resolves the skill's manifest
   permissions and refuses to save when the job's declared needs exceed them —
   *with the exact missing permission named*. A job can never be the path by which
   a permission is acquired.
2. **Autonomy.** `workspace_root` + `autonomy` are only valid for a code job; a
   code job with `approve_external` requires an explicit operator flag and is never
   the default. A code job without a workspace is refused.
3. **Delivery.** An unknown adapter is refused at save time, not silently ignored at
   delivery time.
4. **Watch path.** Must resolve inside a declared workspace root (`policy.resolve_within`);
   a path outside is refused.
5. **Skill pinning.** A job referencing a skill pins a version; a skill that is
   later disabled or rolled back makes the job fail **honestly** with that reason
   rather than running an unexpected version.

### 6.8 Delivery — `jobs/delivery.py`

```python
class DeliveryAdapter(Protocol):
    name: str
    async def deliver(self, job: JobDefinition, run_id: str, summary: DeliverySummary) -> DeliveryOutcome: ...
```

Phase 6 ships two: `in_app` (rides the existing SSE/notification surface —
`src/lib/alerts/notifier.ts` is the TS half) and `artifact` (a saved report under
`.black-eclipse/artifacts/<runId>/`, reusing the research receipt rendering). The
messaging adapter is Phase 11 — the interface exists now so that phase adds an
adapter rather than refactoring the job model.

`DeliveryOutcome` records per-adapter success/failure and a non-secret reason. A
delivery failure never fails the job run; it is reported on the run row.

### 6.9 The finance job library — `jobs/templates.py` (data)

| Template | Kind | Target | Cadence (default, disabled) |
|---|---|---|---|
| Morning portfolio brief | cron | `research-planning` skill over held positions | `30 7 * * 1-5` |
| Overnight news digest | cron | `research/search_news` objective for holdings | `0 7 * * 1-5` |
| Filing watch | cron | `source-verification` skill for a watchlist | `0 18 * * 1-5` |
| Earnings look-ahead | cron | earnings-calendar objective, next 14 days | `0 8 * * 1` |
| Data-freshness watchdog | interval | `get_source_health` / `get_capability_matrix` objective | every 6 h |
| Fundamentals refresh check | interval | `financial-data-quality` skill | every 12 h |
| Build/fix a finance app | manual | code job, `edit_verify`, a declared workspace | operator-fired |

Every template ships `enabled: false`. Templates are **data** — the operator
picks, parameterizes (tickers/watchlist), enables.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-06-progress.md` with §9's gates as
   unchecked boxes.
2. `jobs/cron.py` + `python/tests/test_jobs_cron.py` (pure; write this first — it
   has no dependencies and its edge cases are the risky part).
3. `jobs/model.py` (§6.1) and the DDL + store helpers (§6.2).
4. `jobs/scheduler.py` (§6.3) wired into `AgenticService`'s startup/shutdown
   alongside `start_mcp()`.
5. `jobs/triggers.py` (§6.5) including the hashed webhook token.
6. `jobs/delivery.py` + the two adapters.
7. `routers/jobs.py` (never inline in `main.py`) + `include_router`.
8. `jobs/templates.py` (§6.9).
9. Front door: `src/app/api/jobs/**` proxies + `src/lib/harness/jobs-client.ts` +
   UI `src/components/screens/jobs/**` (list, editor, run history, breaker state,
   template picker). Frosted-glass conventions
   (`.opencode/skills/black-eclipse-ui/SKILL.md`).
10. Tests `python/tests/test_jobs_api.py` (auth on every route), `test_jobs_scheduler.py`
    (using an injected clock — never the real clock), `test_jobs_guardrails.py`.
11. ADR-H108; `docs/CHANGELOG.md`; `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/jobs/{__init__,model,store,cron,scheduler,triggers,delivery,templates}.py` | new package |
| `python/harness/routers/jobs.py` | new route group |
| `python/harness/main.py` | `include_router` only (+ lifespan start/stop) |
| `python/harness/service.py` | scheduler lifecycle |
| `python/harness/persistence.py` | additive DDL for the two tables |
| `python/tests/test_jobs_{cron,api,scheduler,guardrails}.py` | new |
| `src/app/api/jobs/**`, `src/lib/harness/jobs-client.ts`, `src/components/screens/jobs/**` | new front door |
| `docs/harness/decisions.md` | ADR-H108 |
| `docs/harness/roadmap/progress/phase-06-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — cron correctness (pure, injected clock)
./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_cron.py -v

# G2 — an injected-clock scheduler test: the same job fires twice in the window
./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_scheduler.py -v

# G3 — EVERY jobs route refuses a non-operator (reads and mutations)
./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_api.py -v

# G4 — guardrails
./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_guardrails.py -v

# G5 — the suite + the release gate
npm run test && npm run check:all

# G6 — nothing else moved
git status --short        # the three TS schedulers must be UNCHANGED; jdds.db absent

# G7 — plain language: the job editor, library copy and delivery templates
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
# every new string is an i18n key and contains no term from
# policy.PLAIN_LANGUAGE_DENYLIST; no job UI shows a cron expression, skill id,
# job kind or machine reason outside the "details" affordance
```

| Gate | Assertion |
|---|---|
| G1 | `* * * * *`, `*/15 * * * *`, `30 7 * * 1-5`, leap-day and DST cases all resolve; a 6-field expression, `@reboot`, and `MON` are each refused with a specific error. |
| G2 | With an injected clock, an interval job fires twice and both appear in `HarnessJobRun` with their delivery outcome; a job still `running` is not re-launched. |
| G2b | A missed window is reconciled **once** at startup and recorded with `missed=1` — asserted by policy, never by sleeping. |
| G3 | Every route in §6.6 refuses a non-operator: the MCP convention `test_read_routes_refuse_a_non_operator` copied to jobs. |
| G4 | A job bound to a skill lacking a required permission is refused **at save time** naming the exact missing permission; a code job without a workspace is refused; a job with `approve_external` and no operator flag is refused; a `watch_path` outside a workspace is refused; an unknown delivery adapter is refused. |
| G4b | A job failing repeatedly trips the breaker, skips with a recorded reason, and only an operator reset closes it. |
| G4c | A disabled skill pinned by a job makes the run fail honestly with that reason. |
| G5 | Full suite + `check:all` green. |
| G6 | The three TS schedulers are byte-unchanged; no `*.db` change. |
| G7 | Plain language: every new job-editor / library / delivery string is an i18n key and contains no mechanism word from `policy.PLAIN_LANGUAGE_DENYLIST`; each refusal has a plain sentence plus a recovery step. |

## 10. Definition of done

- Every gate run, raw output pasted, observed counts recorded.
- No job route reachable without operator proof — reads included.
- All seven templates ship **disabled**.
- A job run is provably a normal `HarnessRun` (the row links; the trace exists).
- The three TS schedulers are untouched, and the ADR says why.
- `status:` flipped here and in the index.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 6 — Harness-owned jobs and event triggers (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-06-jobs-and-triggers.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §5)
- python/harness/routers/mcp.py  ← the route-group convention you copy (registered
  by main.py via include_router; shared state from deps.py; NEVER import main)
- python/harness/mcp/circuit.py  ← the breaker you reuse (CLOSED/OPEN/HALF_OPEN,
  named thresholds, operator reset). Do not write a second backoff implementation.
- python/harness/mcp/config.py   ← the config round-trip rule you copy: absent
  means PRESERVE, explicitly present means replace; never silently widen authority.
- python/harness/main.py (_lifespan + require_operator), python/harness/deps.py,
  python/harness/service.py, python/harness/persistence.py, python/harness/events.py

Goal: give the harness its own durable job model so finance work runs on a cadence
and on events without a human clicking. A job run IS a normal run — never a second
execution path.

In scope:
1. jobs/cron.py — a stdlib-only 5-field matcher (*, N, a-b, a,b,c, */N) with a pure
   next_fire(after); refuse 6-field expressions, @macros, name aliases with
   specific errors. NO new dependency (AGENTS.md: prefer the lighter option).
2. jobs/model.py — JobDefinition/JobTarget/JobDelivery per §6.1. enabled defaults
   FALSE (discovery is not activation, ADR-H39).
3. jobs/store.py + persistence.py — HarnessJob and HarnessJobRun exactly as §6.2,
   additive and idempotent, in agent-memory.db. If persistence.py is at its size
   ratchet, own the helpers in jobs/store.py bound to the single AgentMemoryStore
   connection (the ownership pattern run_lineage.py documents).
4. jobs/scheduler.py — ONE lifespan task alongside start_mcp(): a 30s tick, no
   overlap, bounded in-flight runs (default 2), max_runtime_s cooperative cancel,
   missed-run reconciliation ONCE at startup per on_missed with every decision
   recorded (missed=1), and the circuit breaker reused from mcp/circuit.py.
   Never sleep-based tests — take an injected clock.
5. jobs/triggers.py — file_watch (bounded mtime+size poller inside a workspace),
   webhook (POST /jobs/{id}/trigger; SHA-256 of the token is all that is stored;
   shown once at creation), manual.
6. jobs/delivery.py — a DeliveryAdapter protocol with 'in_app' (the existing SSE /
   src/lib/alerts/notifier.ts surface) and 'artifact' (.black-eclipse/artifacts/).
   Messaging is Phase 11 — define the interface, implement only the two.
7. routers/jobs.py — every route per §6.6 behind require_operator (READS TOO, as
   the MCP group was hardened to do, ADR-H48); the webhook route authenticates on
   the hashed token instead. Register via app.include_router in main.py.
8. jobs/templates.py — the seven finance templates in §6.9, all enabled:false.
9. Guardrails enforced at SAVE time (§6.7): permission binding to the pinned
   skill's manifest (refuse naming the exact missing permission), workspace
   required for a code job, approve_external only with an explicit operator flag,
   watch_path confined by policy.resolve_within, skill version pinned, unknown
   delivery adapter refused.
10. Front door: src/app/api/jobs/** proxies, src/lib/harness/jobs-client.ts, UI
    src/components/screens/jobs/** (list/editor/history/breaker/template picker)
    using the frosted-glass conventions.
11. Tests test_jobs_cron.py, test_jobs_scheduler.py (injected clock),
    test_jobs_api.py (auth on every route), test_jobs_guardrails.py.
12. ADR-H108; docs/CHANGELOG.md dated entry; docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No distributed/multi-node scheduler, no leader election.
- Do NOT modify or replace src/lib/{scraper,connectors,investor-eye}/*scheduler* —
  they stay exactly as they are; this phase adds the harness job model beside them.
- No new dependency (no croniter/APScheduler).
- No job that can raise its own permissions, enable a skill, or be triggered into
  changing its own definition (a webhook body can never alter the job).
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: a job run is a normal execute_run with a job id; no second loop.
- Policy and permissions stay in code.
- New logic in new modules; main.py grows only by include_router.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-06-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_cron.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_scheduler.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_api.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_jobs_guardrails.py -v
  npm run test && npm run check:all
  git status --short   (the three TS schedulers must be UNCHANGED; jdds.db absent)

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 7 — Delegation and child runs](./phase-07-delegation.md)
