---
title: Institution Multi-Agent Preset
status: Current
last-verified: 2026-10-28
---

# Institution Multi-Agent Preset

The Institution is a **preset cast** for an investment-committee decision:

```
analyst -> debate (bull + bear + chair) -> trader -> risk -> PM
```

It is a composition layer over the Bot Team Orchestration runtime
(`docs/harness/bot-team-orchestration.md`), which itself composes A2A delegation
and the durable Task/Plan scheduler. It adds **no** agent loop, tool registry,
model adapter or store.

---

## 1. What is a "seat"?

Each seat is defined once in `python/harness/institution/cast.py` (`ROLES`) and
materialised into three contracts by `python/harness/institution/preset.py`:

| Materialisation | Consumer |
|---|---|
| `AgentConfig` preset (`agent_configs()`) | `service.run` / a standalone bot turn |
| A2A `AgentDefinition` (`a2a_definitions()`) | team delegation + capability routing |
| `TeamMember` + `TeamSubtask` (`build_team()`) | the durable committee task graph |
| bot spec (`bot_specs()`) | the Bots workspace seeder (real `AutomationDefinition`s) |

One spec, four views. The bot identities can never drift from the agents the
team actually runs.

### Seats

| Seat | Agent id | Stage | Tool surface |
|---|---|---|---|
| Analyst | `institution-analyst` | `analysis` | market/fundamentals/research/portfolio read + `read_run_output` |
| Bull | `institution-bull` | `debate` | research + market + `read_run_output` |
| Bear | `institution-bear` | `debate` | research + market + `read_run_output` |
| Chair | `institution-chair` | `debate` | `read_run_output` only |
| Trader | `institution-trader` | `trader` | read-only market/portfolio + `read_run_output`; **no execution tools** |
| Risk | `institution-risk` | `risk` | portfolio risk read tools + market + `read_run_output` |
| PM | `institution-pm` | `pm` | `read_run_output` only |

### Task graph

```
analysis
├── bull_case ─┐
├── bear_case ─┴── debate ── trade_proposal ── risk_review ── decision
```

`bull_case` and `bear_case` run concurrently. Every later stage lists the memos
it must read **directly** as dependencies, because the task context renders only
direct prerequisites (`tasks/context.py::render_task_query`).

Policy: `requireReview=true` with an independent `qa-agent`, `STRICT`
strictness, `REQUIRE_ALL` for required stages, `maxConcurrency=4`,
`perAgentConcurrency=1`, `maxDepth=8` (the A2A budget counts every delegation).

---

## 2. Handoff contract

A downstream stage does not inherit an upstream agent's prose. The task context
lists a completed prerequisite as `output: <runId>`. The read-only
`read_run_output` tool (`institution/tools.py`) reads that run's final output
from the ONE run store.

This is why the trader/risk/PM prompts say "read the analyst brief / debate
record / proposal" and why every downstream subtask lists those seats as direct
dependencies.

---

## 3. The debate is not a vote

The chair must produce a structured record:

1. points of agreement,
2. unresolved disagreements (bull position, bear position, evidence each side
   relies on, why it is not settled),
3. missing facts that would settle a disagreement (`UNAVAILABLE` when the data
   does not exist),
4. a neutral restatement of the decision.

The chair must not pick a side, score the debate, or average numbers. The
existing `team/conflicts.py` reconciles evidence deterministically and never
averages/votes; the independent reviewer discloses unresolved conflicts.

---

## 4. Surfaces

### Interactive

Bots workspace → **Institution committee**. The dialog:

- seeds the seven bots as real automations (idempotent by name),
- starts the committee through `POST /api/team/presets/institution/run`,
- polls the durable task graph and renders the stage timeline,
- finalises/reviews on terminal and shows the deterministic decision memo.

The chat room ("Investment Committee") is created with six seats for casual
conversation only; the pipeline is **always** a Team run, never a group turn.

### HTTP (Python, operator-gated)

| Route | Purpose |
|---|---|
| `GET /team/presets` | stable preset catalogue |
| `GET /team/presets/institution?objective=…` | filled `TeamDefinition` + bot specs |
| `POST /team/presets/institution/run` | build + start the committee |
| `POST /team/runs` | start any `TeamDefinition` (existing) |

### Scheduled

Automation action `type: "run_team"` (`automation/model.py`, dispatched in
`automation/dispatcher.py::_run_team`). Config:

```json
{ "type": "run_team", "objective": "…", "config": {
    "presetId": "institution",
    "universe": "…", "horizon": "…",
    "constraints": ["max 5% single name"]
} }
```

The dispatcher starts the team, waits up to the automation's
`execution.maxRuntimeS`, finalises and returns the synthesis. A timeout is an
honest failure (`TEAM_INCOMPLETE`), never a fabricated decision.

### Chat

`eclipse-agent` already carries `TEAM_TOOLS`; it can call `team_run` with a team
object, and the preset routes are available to any operator client.

---

## 5. Safety invariants

- **No execution.** The trader has read-only tools; the PM returns a proposal.
  A separate approval-gated executor would be required to act.
- **Risk veto.** The risk officer returns `APPROVE`, `APPROVE WITH LIMITS` or
  `VETO`; the PM must state a written, evidence-backed reason to override one.
- **No fabrication.** Every role inherits the `UNAVAILABLE` / cite-source /
  as-of rule.
- **No averaging.** Debate disagreements are disclosed, never blended.
- **Least privilege.** Each seat declares a closed tool list; `read_run_output`
  is read-only.
- **Opt-in.** The preset never becomes the default path. ADR-H213 still requires
  a measured benchmark win before multi-agent routing is promoted.

---

## 6. Known limits

- **One model per team run.** `TeamService.run` accepts one `modelSettings` for
  the whole graph; per-seat model overrides are not implemented. Standalone bot
  runs still honour the per-bot model pin.
- **Bot edits do not rewrite the preset.** The cast owns the prompts; editing a
  seeded bot changes that bot's standalone behaviour, not the team graph.
- **Single-pass debate.** Bull/bear are independent cases plus a chair. A
  multi-round debate needs a bounded loop primitive and is deliberately not in
  v1.
- **Review is post-hoc.** `POST /team/runs` plans and starts; the UI (or the
  `run_team` dispatcher) calls `finalize` when the graph is terminal.

---

## 7. Code map

```text
python/harness/institution/
  cast.py       roles, prompts, tool surfaces, shared evidence rules
  preset.py     agent_configs / a2a_definitions / build_team / bot_specs / descriptor
  tools.py      read_run_output (read-only handoff)
  bootstrap.py  install_institution_layer (boot.py, after the team layer)
python/harness/routers/team.py        /team/presets* routes
python/harness/automation/dispatcher.py  run_team action
src/lib/harness/team-client.ts        typed preset client
src/lib/bots/institution-bots.ts      idempotent bot seeder
src/components/bots/institution-run-dialog.tsx  run form + live stage timeline
```

Tests: `python/tests/test_institution_preset.py`,
`src/lib/institution/preset-client.test.ts`.

A supporting fix: `tasks/manager.py::recompute_plan` now keeps a plan `RUNNING`
while any task is still `TODO`; previously a deeper multi-level DAG could be
marked `BLOCKED` after its first stage completed, and the scheduler would stop
dispatching runnable work.
