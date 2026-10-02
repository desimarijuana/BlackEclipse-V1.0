---
title: "Phase 17 — Working on a Cadence"
status: Not started
phase: 17
depends_on: [6, 14]
unlocks: [20]
last-verified: 2026-10-02
---

# Phase 17 — Working on a Cadence

| | |
|---|---|
| **Depends on** | Phase 6 (the job model, scheduler, triggers and delivery adapters — all reused unchanged) and Phase 14 (the chat surface that must be able to start and schedule a work order). |
| **Unlocks** | Phase 20 (the gate grades the refusal path and the unattended honesty rules). |
| **Estimated work** | 10–14 h of agent time. No new scheduler, no new store — an allowlist, an operator toggle, and the refusal path. |
| **Deliverable type** | one permission/authorization change + one operator setting + the unattended-answer contract. |
| **Decision records** | ADR-H122 (the agent may schedule its own work, within a fixed catalogue and with an operator master switch) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The catalogue (data, one row per shape)](#61-the-catalogue-data-one-row-per-shape)
  - [6.2 The tools](#62-the-tools)
  - [6.3 The operator switch](#63-the-operator-switch)
  - [6.4 The unattended answer contract](#64-the-unattended-answer-contract)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

Eclipse can put **its own recurring work** on a schedule: "check my portfolio every
morning", "watch this filing and tell me when it changes", "re-run that screen
weekly". The scheduling is still Phase 6's machinery, the catalogue is still fixed
templates, and the operator still holds the master switch — what is new is that the
agent can create the job instead of only the user filling in an editor.

## 2. Why this phase exists

**(a) The job model already anticipates an agent-created job.** `jobs/model.py`:

```python
class JobTarget(BaseModel):
    kind: JobTargetKind
    skill_id: Optional[str] = None
    skill_version: Optional[str] = None          # pinned; a job is reproducible
    objective: Optional[str] = Field(None, max_length=4000)
    agent_id: str = "eclipse-agent"
    workspace_root: Optional[str] = None
    autonomy: Optional[JobAutonomy] = None
```

`templates.py` ships seven parameterizable jobs (Morning portfolio brief, Overnight
news digest, Filing watch, Earnings look-ahead, Data-freshness watchdog,
Fundamentals refresh check, Build or fix a finance app), each with
`enabled=False  # discovery is not activation`. `scheduler.py` reuses the MCP circuit
breaker and reconciles missed runs. The model, the templates, the persistence and
the delivery adapters all exist and are proven — this phase does not touch any of
them.

**(b) Nothing in the agent's tool set can create a job.** Verified:

```
grep -rn 'name="job|job_create|job_run|"schedule' python/harness --include=*.py
# only jobs/scheduler.py internals (triggered_by="schedule") — no tool
```

`JobStore` is constructed in `service.py` and used by `routers/jobs.py`, which is
`require_operator` on **every** route (reads included). So the only ways to create a
job are the UI editor and the operator-gated route. "Cannot schedule tasks" is
accurate as a statement about the agent, and false as a statement about the system.

**(c) The decision is a permission, not a mechanism.** The runtime already
distinguishes `SAFE_PERMISSIONS` (the default actor) from `OPERATOR_PERMISSIONS`,
and `routers/jobs.py` gates mutations on `require_operator` at transport level. Letting
the *agent* create a job means deciding **what it may create** and **how the operator
consents** — the two questions §6 answers.

**(d) An unattended run has a different honesty contract, and it is not stated.**
A job runs with no user watching. Today's answer surface was designed for a live
turn: a refusal reaches a person who can respond. An unattended run that hits a
refusal, a stale source, or a budget ceiling must **say so in its delivered report**,
in the same plain language, and must never present a degraded run as a complete one.
Nothing in the tree states this rule, and it is the reason this phase exists as more
than a permission flip.

## 3. In scope

1. **A fixed scheduling catalogue** as data: the job shapes the agent may create
   (which template, which parameters, which agent, which profile). Not free-form job
   authoring — one row per shape, and a test asserting the catalogue is exhaustive.
2. An operator setting — **one master switch** — that enables agent-created jobs for
   the installation, default **off**, surfaced in the existing jobs screen as a plain
   sentence.
3. The tools: `job_list`, `job_describe_template`, `job_create` (creates **disabled**,
   always), and `job_run_now` (an on-demand run). No `job_delete`, no `job_enable` —
   enabling stays an operator action in the UI, so "discovery is not activation"
   survives at the top of the chain.
4. The **unattended answer contract**: what a delivered job report must contain when
   the run was degraded, refused or partial, and the test that asserts it.
5. A plain-language surface for every refusal the agent can hit while scheduling
   (switch off, catalogue miss, parameter outside the shape, no operator).

## 4. Who can use it (the non-expert obligation)

The person here is a portfolio manager or an analyst who wants a standing brief, not
a cron expression. They say the job; Eclipse names it back:

- "Every weekday at 07:30, summarise my portfolio" → Eclipse replies "Every weekday
  at 07:30 — Morning portfolio brief. It's saved but switched off; turn it on in
  Scheduled Jobs." (i18n keys under `jobs.agent.*`.)
- The operator's switch reads "Let Eclipse schedule work for you" — the existing
  template vocabulary, no mechanism word (`cron`, `interval`, `webhook`, `trigger`,
  `scheduler` stay in the trace).
- When a delivered report was degraded, its first line says so in one sentence, and
  the report names what was not checked — because nobody is watching at 07:30.

## 5. Non-goals (do not do these)

- **No change to the job model, the scheduler, the store or the delivery adapters.**
  If a change to `jobs/model.py` looks necessary, the correct output is an honest
  partial report naming it (the rule Phase 11 already states for the same file).
- **No free-form job authoring by the agent.** The catalogue is the boundary; a
  request outside it is refused with the closest available shape.
- **No self-enabling, no self-deleting.** `job_create` always writes `enabled=False`
  and no tool removes a job.
- **No new trigger kind**, no new delivery adapter, no second scheduler.
- **No widening of `require_operator` on the existing routes.** The agent's tools
  call the store through their own authorized path, not by relaxing the routes.
- **No autonomous code jobs from this phase.** Phase 14 creates a disabled code job
  from an explicit user action; the agent does not schedule code changes on its own
  initiative beyond the catalogue's declared shapes.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The catalogue (data, one row per shape)

```python
# python/harness/jobs/catalogue.py
@dataclass(frozen=True)
class SchedulableJobShape:
    id: str                        # stable id the agent asks for
    label_key: str                 # i18n key — plain words, the job's name
    template_id: str               # the EXISTING template this instantiates
    agent_id: str                  # "eclipse-agent" or "code-agent"
    autonomy: Optional[str]        # None for research/analysis shapes
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    max_frequency_per_day: int     # a hard ceiling: no shape may run every minute
    delivery: str                  # an existing adapter name

SHAPES: dict[str, SchedulableJobShape] = {
    "portfolio_brief": SchedulableJobShape(
        id="portfolio_brief", label_key="jobs.agent.shape.portfolioBrief",
        template_id="morning_portfolio_brief", agent_id="eclipse-agent",
        autonomy=None, required_params=("symbols",), optional_params=("horizon",),
        max_frequency_per_day=4, delivery="in_app",
    ),
    "data_freshness": SchedulableJobShape(
        id="data_freshness", label_key="jobs.agent.shape.dataFreshness",
        template_id="data_freshness_watchdog", agent_id="eclipse-agent",
        autonomy=None, required_params=(), optional_params=("markets",),
        max_frequency_per_day=24, delivery="in_app",
    ),
    # one row per template that may be scheduled by the agent; a template with no
    # row is not schedulable by the agent (the UI may still use it).
}
```

### 6.2 The tools

```python
async def job_create(args, ctx) -> tuple[str, Any]:
    """Create a scheduled job from the catalogue — ALWAYS disabled.

    Refuses with a stable code when: agent scheduling is off for this installation;
    the shape id is unknown; a required parameter is missing or outside the closed
    set; the requested cadence exceeds the shape's ceiling; the actor holds no
    scheduling grant. On success the job exists, is disabled, and the reply says so
    in one plain sentence plus where to switch it on.
    """

async def job_run_now(args, ctx) -> tuple[str, Any]:
    """Run an existing job once, on demand. Refuses if the job is disabled."""

async def job_list(args, ctx) -> tuple[str, Any]:
    """List jobs for the caller's scope: name, schedule in plain words, last
    outcome, and whether it is on. Read-only."""
```

Registered through a new `register_job_tools(registry)` called from `service.py`,
and listed in `agents.ECLIPSE_AGENT` and the chat code profile. `job_create` is
effectful (`permission="write"`, `effect="external_action"`) so it goes through the
existing approval primitive when the operator requires confirmation — reusing
`mcp/approvals.py`, not a second store.

### 6.3 The operator switch

```ts
// The existing settings vault, one key. Default false.
// src/lib/settings.ts
export interface SchedulingConfig {
  /** Let the agent create scheduled work. Default off. */
  agentSchedulingEnabled: boolean;
}
// Surfaced in the jobs screen as one sentence + a toggle (i18n
// `jobs.agent.settings.label` / `.help`).
```

The runtime reads it through the existing settings path and refuses every scheduling
tool when it is false — the switch is enforced in Python, and the tool is **removed
from the bound set** when off, so the model cannot even attempt it.

### 6.4 The unattended answer contract

```python
# python/harness/jobs/delivery.py — ADDITIVE contract, one helper
def render_run_report(job: JobDefinition, status: str, outcome: dict[str, Any]) -> str:
    """The text a delivered job run must carry.

    Rules (asserted by test, not by convention):
      1. The FIRST line states the outcome in plain words: completed / could not
         finish / finished with limits.
      2. A run whose status is degraded, refused or partial names EVERY limit it hit
         (stale source, exhausted collection limit, refused check, missing input) —
         never a silent short report.
      3. A run that produced no data says so and names the next step; it never
         delivers an empty report as a success.
      4. No mechanism word reaches the text (the denylist applies to it like any
         user-facing string).
    """
```

## 7. Work items (ordered)

1. `python/harness/jobs/catalogue.py` — the shapes + a test asserting every shape
   names a real template and a real adapter.
2. `python/harness/jobs/delivery.py` — `render_run_report` + its tests (the honesty
   contract first: it is what makes unattended runs trustworthy).
3. `python/harness/jobs/tools.py` — the four handlers + `register_job_tools`.
4. `python/harness/service.py` — one registration line; the switch read at run
   resolution time.
5. `python/harness/agents.py` — the allowlists, and the removal of the job tools from
   the bound set when the switch is off.
6. `src/lib/settings.ts` + the jobs screen toggle (one sentence, i18n keys).
7. `src/app/api/harness/…` — nothing new: the switch rides the existing settings
   route. Confirm, do not add.
8. `en.ts` — `jobs.agent.*`.
9. `python/tests/test_job_tools.py`, `test_job_catalogue.py`,
   `test_job_report_honesty.py`.
10. `docs/harness/roadmap/progress/phase-17-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/jobs/catalogue.py` | new — the fixed schedulable shapes |
| `python/harness/jobs/tools.py` | new — the four tools + registration |
| `python/harness/jobs/delivery.py` | changed — `render_run_report` |
| `python/harness/service.py` | changed — one registration line + switch wiring |
| `python/harness/agents.py` | changed — allowlists + the switch removal |
| `src/lib/settings.ts` | changed — the operator switch |
| `src/components/screens/jobs/**` | changed — the toggle, one sentence |
| `src/lib/i18n/dictionaries/en.ts` | changed — `jobs.agent.*` |
| `docs/harness/decisions.md` | changed — ADR-H122 |
| `docs/harness/runbook-add-a-job.md` | changed — the agent-created path |

## 9. Acceptance gates

```bash
# G1 — the catalogue is the boundary.
./scripts/vendor/python/python.exe -m pytest python/tests/test_job_catalogue.py -v

# G2 — every scheduling refusal is blocked AND recorded, and the switch removes
#      the tools from the bound set.
./scripts/vendor/python/python.exe -m pytest python/tests/test_job_tools.py -v

# G3 — an unattended degraded run states its limits.
./scripts/vendor/python/python.exe -m pytest python/tests/test_job_report_honesty.py -v

# G4 — the job model, store and scheduler are unchanged.
git diff --stat python/harness/jobs/{model,store,scheduler,triggers}.py
# expected: empty

# G5 — the plain-language gates cover the new strings.
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q

# G6 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | Every shape names an existing template id and an existing delivery adapter; a shape with a cadence ceiling above its declaration is a failure; an unknown shape id is refused. |
| G2 | With the switch off, the job tools are **absent from the bound tool set** (asserted on the resolved allowlist, not on the prompt); with it on, each of these is blocked and recorded: unknown shape, missing required param, param outside the closed set, cadence above the ceiling, actor without the grant. A created job is `enabled=False` in the store, read back and asserted. |
| G3 | A degraded, refused and partial run each render a first line naming the outcome and a body naming every limit; an empty result renders "produced nothing" with a next step; no mechanism-denylist word appears in any rendered report. |
| G4 | `jobs/model.py`, `store.py`, `scheduler.py`, `triggers.py` are byte-unchanged — this phase adds a catalogue and tools, not a scheduler. |
| G5 | Every new key passes both plain-language gates. |
| G6 | `ALL GATES PASSED`; counts reported as observed. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-17-progress.md`.

## 10. Definition of done

- The agent can create a scheduled job from a fixed catalogue, always disabled, and
  can say where to switch it on.
- The operator switch defaults off and, when off, the tools are not merely refused
  but absent from the bound set.
- Every unattended report states its outcome and its limits; a degraded run can never
  read as a clean one.
- The job model, store, scheduler and delivery adapters are byte-unchanged.
- ADR-H122 written; changelog appended; NAVIGATION rows 72/78 and the runbook
  updated; `status:` and the index row flipped.

## 11. Implementation prompt

```text
Task: Phase 17 — the agent can schedule its own work.

Read first, in full:
- docs/harness/roadmap/phase-17-working-on-a-cadence.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3 invariants, §6 non-goals)
- python/harness/jobs/{model,store,scheduler,triggers,templates,delivery}.py
- python/harness/routers/jobs.py (the require_operator posture you must NOT relax)
- python/harness/service.py (the ONE registry assembly point)
- python/harness/agents.py, python/harness/skills/permissions.py
- python/harness/code/policy.py (the profile/allowlist pattern to mirror)

Goal: Eclipse can put its own recurring work on a schedule from the conversation,
through a fixed catalogue, with an operator master switch that defaults off, and with
an unattended run that always states its limits.

In scope: §3 items 1–5 and the ordered work items in §7.

Non-goals (do NOT do these):
- Do NOT modify jobs/model.py, jobs/store.py, jobs/scheduler.py or jobs/triggers.py.
  If a change to one looks necessary, STOP and report it — that is the finding.
- No free-form job authoring; the catalogue is the boundary.
- No self-enabling and no deletion tool. job_create always writes enabled=False.
- No new trigger kind, no new delivery adapter, no second scheduler.
- Do NOT relax require_operator on any existing /jobs route.
- The agent must not schedule code changes on its own initiative.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: register on the existing registry from service.py.
- The operator switch is enforced in Python and REMOVES the tools from the bound set
  when off — not merely a refusal.
- Reuse the single-use approval primitive (mcp/approvals.py) for effectful creates;
  no second store.
- Every user-facing string is an i18n key; the mechanism denylist applies, including
  to rendered job reports.
- Measure before implementing; a corrected audit is a valid outcome. Do not weaken any
  existing test — name every changed expectation with its old and new value.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-17-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_job_catalogue.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_job_tools.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_job_report_honesty.py -v
  git diff --stat python/harness/jobs/model.py python/harness/jobs/store.py python/harness/jobs/scheduler.py python/harness/jobs/triggers.py
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 18 — Visual Output](./phase-18-visual-output.md)
