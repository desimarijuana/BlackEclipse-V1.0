---
title: Desks — user-authored bot teams
status: Current
last-verified: 2026-11-18
---

# Desks: user-authored bot teams

**Who this is for:** anyone asking "can I put my news bot and my trading bot on one
job, and get one good answer out?" — and anyone changing the builder, the runner,
the trigger chain or the execution boundary.

The team layer it builds on is `docs/harness/bot-team-orchestration.md`; the
workspace surface is `docs/bot-mode.md`; the fixed cast that came first is
`docs/harness/institution-preset.md`.

## Implementation status

| Phase | State |
|---|---|
| P0 — generalize `run_team` from `config.team` | **Shipped.** `dispatcher._run_team`; the Institution preset remains the fallback. |
| P0 — create-time team validation, refuse `order_submit` | **Shipped.** `automation/validation.py::_validate_team_action`, `TeamService.validate`, `_team_tools`. |
| P0 — `read_run_output` owned by the team layer | **Shipped.** `team/tools.py`; `institution/tools.py` is a re-export. |
| P1 — desk builder (`New desk`) | **Shipped.** `desk-builder-dialog.tsx` + `src/lib/bots/desk.ts`; `POST /team/validate` is the save gate. |
| P2 — desk room (timeline, result, history) | **Shipped.** `desk-room.tsx`; `GET /team/runs/by-root/<runId>` resolves the stage timeline. |
| P3 — `automation.completed` + event authoring + lead | **Shipped.** Engine emits the event; `bot_create`/`bot_update` accept event/condition triggers; the schedule editor authors them; `contextAutomationId` adds a labelled lead. |
| P4 — execution approval surfacing | **Shipped.** `Dispatcher._pending_trade_approvals` matches a desk's subtask run via `Task.assigned_run_id`, and the desk room mounts the same self-polling `TradeApprovalBanner` the bot composer uses. |
| Housekeeping — `wait_idle` busy loop | **Fixed.** The done-callback needed one loop turn. |

## The question, answered honestly

A **group room** (`group-chat-room.tsx`, 2–6 bots) is a round table: on send, the
addressed members run **in parallel** off the same prompt, each in its own private
memory, and none of them sees another member's reply from the same turn. It is
good for cheap, adversarial takes. It is not a pipeline, has no arbiter, no shared
artifact and no hand-off, so it cannot turn a monitor bot's finding into an
executor bot's order.

The pipeline machinery **already exists**: the team layer runs a dependency-aware
durable DAG, passes completed prerequisite memos by run id, reconciles evidence,
reviews independently and repairs. But `run_team` is hardcoded to one cast
(`dispatcher._run_team` accepts only `presetId == "institution"`), the definition
is not saved anywhere except inside a `TeamRun`, and nothing publishes the
`automation.completed` event the trigger engine would need.

A **desk** is the smallest thing that closes exactly that gap.

## Decisions (and why)

**D1. A desk is an automation, not a new entity.** `action.type = "run_team"`,
`action.config.team = <TeamDefinition>`, `tags: ["bot", "desk"]`. The automation
store already gives durability, versioning, schedule/event/condition triggers,
misfire and concurrency policy, delivery, run history, approvals, pause and
delete. A new `Team` table would duplicate all of it. The definition JSON is
bounded (`TeamDefinition`: 12 members, 64 subtasks) and is snapshotted onto every
`TeamRun.definition`, so an edit never rewrites history.

**D2. Roles are team members, not bot rows.** `TeamService._ensure_member_agent`
already registers each member on the A2A registry and installs its agent preset
from `member.instructions` / `member.tools`. Seeding one bot per seat (what the
Institution does, deliberately, so each seat can be chatted with) would clutter
the Bots list for every desk. A desk has one row; its stages are inside it.

**D3. The desk proposes; a trading bot executes.** A team run is not a bot, has
no pinned mandate and no `automationId` in the execution context. `order_submit`
therefore fails closed for live (`LIVE_REQUIRES_BOT`). A **demo** submit could
still pass if exactly one active mandate covers the symbol, so a team member
declaring `order_submit` must be refused at validation, in both
`TeamService.validate` and automation validation. A desk may call
`order_preview` (L0): it produces the operator's approval card and the normal
submit route sends that exact order. Execution belongs to a strategy/agent
trading bot at L1/L2 with its own mandate — one order path, unchanged.

**D4. One trigger contract.** Wire the already-declared
`event_system/registry.py` events `automation.completed` / `automation.failed`
where an execution reaches a terminal state. A desk subscribes with an
`eventFilter`. Do not hang the chain off `automation.delivered`: that only fires
when a delivery target is configured, and it is a delivery record, not a
completion contract.

**D5. The user authors the graph; no model invents it.** A planner that writes
its own DAG cannot be reviewed, costed or bounded. The builder edits members,
stages and dependencies; `TeamService.validate` is the only gate.

## What is reused (not rebuilt)

| Piece | Where | What it gives a desk |
|---|---|---|
| Task graph + scheduler | `team/graph.py`, `tasks/` | Durable dependencies, concurrency caps, leases, retries, restart recovery |
| Delegation | `a2a/` | Real per-member runs, least-privilege tool intersection, budgets, durable messages |
| Memo hand-off | `tasks/context.py` (`output: <runId>`), `read_run_output` | A downstream stage reads the actual prerequisite output, not injected prose |
| Findings / conflicts | `team/conflicts.py` | Evidence-backed findings, unresolved disagreements disclosed, never averaged |
| Review + repair | `team/review.py` | Independent reviewer (`UNABLE_TO_VERIFY` if it produced the work), bounded repair |
| Execution record | `automation/` | Version, schedule, trigger, history, timeline, output, delivery, approvals |
| Runner UI | `institution-run-dialog.tsx`, `team-client.ts` | Live stage timeline, review verdict, synthesis |
| Model pin | `_model_settings_for(definition)` | Per-desk provider/model, same rule as every bot |

## Topology

```
Monitor bot (interval | condition | event)
  └─ automation.completed  ──►  Desk (run_team automation)
                                  members: user-authored roles
                                  stages: research → challenge → chair
                                          → proposal → risk → decision
                                  output: proposal + disclosed conflicts + review
        ┌───────────────────────────────┴───────────────────────────────┐
        │ operator confirms the order_preview card                       │
        │ (the one manual live path — no mandate needed)                 │
        └────────────────────────────────────────────────────────────────┘
        │ or: "Send to executor" starts a manual run of the trading bot
        ▼
Executor bot (strategy | agent, L1 demo / L2 live, own mandate)
```

Three separate objects, each with the least authority that does its job. The
monitor is cheap and always-on; the desk is expensive and on demand; the executor
owns the money and the mandate.

## Contracts

**Desk automation**

```json
{
  "name": "Rates desk",
  "state": "active",
  "tags": ["bot", "desk"],
  "trigger": { "type": "event", "eventType": "automation.completed",
               "eventFilter": { "automationId": "<monitor bot id>" } },
  "action": {
    "type": "run_team",
    "objective": "Decide whether the current rates move justifies a position.",
    "config": {
      "teamId": "desk-rates",
      "team": {
        "id": "desk-rates", "name": "Rates desk",
        "agentId": "eclipse-orchestrator", "objective": "…",
        "members": [
          { "agentId": "desk-analyst", "label": "Analyst", "role": "analyst",
            "capabilities": ["analysis"], "tools": ["research_search", "research_search_news",
              "market_get_ohlcv", "macro_get_series", "read_run_output"],
            "instructions": "Build the evidence base. Cite source and as-of. UNAVAILABLE, never estimate." },
          { "agentId": "desk-trader", "label": "Trader", "role": "trader",
            "capabilities": ["proposal"], "tools": ["get_quote", "portfolio_get", "order_preview",
              "read_run_output"], "instructions": "Fully specified proposal. Never claim execution." }
        ],
        "subtasks": [
          { "id": "analysis", "assignedAgentId": "desk-analyst", "objective": "…",
            "expectedOutput": { "brief": "string", "evidence_refs": "array" } },
          { "id": "proposal", "assignedAgentId": "desk-trader", "dependsOn": ["analysis"],
            "objective": "…", "expectedOutput": { "instrument": "string", "entry": "string" } }
        ],
        "policy": { "delegationEnabled": true, "maxConcurrency": 3, "maxRuntimeMs": 900000,
                    "requireReview": true, "reviewStrictness": "STRICT",
                    "optionalFailurePolicy": "REQUIRE_ALL" }
      }
    }
  }
}
```

**Execution detail** (already the shape `_run_team` returns): `teamRunId`,
`teamStatus`, `reviewOutcome`, `conflicts`, plus `output` = `synthesize()`.

**Event** (`automation.completed`): `{ automationId, executionId, runId, status }`.
The output is **not** put on the bus (size and content); a consumer reads it
through the automation service or through a declared `contextAutomationId`.

**Validation errors** (create time, never at run time): unparsable
`config.team`; fewer than 2 members; no subtasks; unknown/cyclic dependency;
unassigned or unroutable stage; `order_submit` in any member's tools;
`requireReview` false (warning, not error); config over the model's bounds.

## Phases

The phase notes below are the design record. The status table above is the truth;
P4 remains open.

### P0 — Generalize `run_team` (backend only)

Files: `automation/dispatcher.py`, `automation/validation.py`,
`team/service.py`, `team/bootstrap.py`, `institution/tools.py` (move).

1. `_run_team`: if `config.team` is a dict, parse `TeamDefinition` and run it;
   else keep the Institution preset path. Report the real `teamId` in `detail`;
   keep `presetId` only for the preset path.
2. Extract the current order-submit refusal into `TeamService.validate` so a
   chat-authored `team_run` gets the same guard.
3. `automation/validation.py`: add `_validate_team_action` with the errors listed
   above; run it on create and update.
4. Register `read_run_output` in `team/bootstrap.py` (keep the institution
   registration idempotent) so a desk does not depend on the Institution preset.
5. Tests: `python/tests/test_automation_team_action.py` — valid desk executes and
   stores the synthesis; bad team refused at create; `order_submit` refused;
   Institution preset still runs; a restart keeps the run recoverable.

Acceptance: `POST /api/automations` with the JSON above produces an execution
whose `output` is the deterministic synthesis, and whose detail names the run.

### P1 — Authoring (smallest usable builder)

Files: `src/components/bots/create-bot-dialog.tsx` (4th brain "Desk"),
new `src/components/bots/desk-builder.tsx`, `src/lib/bots/desk.ts`,
`src/lib/harness/clients/team-client.ts`, `routers/team.py` (`POST /team/validate`).

1. Desk draft: name, description, objective template (`{{universe}}`,
   `{{horizon}}` optional), stages. A stage = label, runs-as (agent preset **or**
   custom role with instructions + tool subset), `after` (multi-select earlier
   stages), expected output keys, review toggle.
2. Save goes through the existing `createAutomation` (`type: "run_team"`);
   no new route. Edit is the normal `PATCH`, which bumps the version.
3. `POST /team/validate` is a thin wrapper over `TeamService.validate` returning
   `{ errors, stages }` so the builder shows the exact refusal before saving.
   The server re-validates on save (never trust the client).
4. Bound the editor to the model: 2–12 members, ≤64 stages, no order-submitting
   tool in the picker, `requireReview` on by default with STRICT.
5. Tests: `src/lib/bots/desk.test.ts` (draft → `TeamDefinition` mapping, cycle
   refusal, tool filter) and a Python route test for `/team/validate`.

Acceptance: a 3-stage desk (research → challenge → decide) is created, edited
(version bumps), and an invalid graph is refused with the server's message. No
bot rows are created.

### P2 — Runner and workspace surface

Files: generalize `institution-run-dialog.tsx` → `team-run-dialog.tsx`, new
`src/components/bots/desk-room.tsx`, `screens/bots/bots-screen.tsx`,
`bots-sidebar-panel.tsx`, `group-chat-dialog.tsx`.

1. Selecting a desk opens a desk view: header, stages, **Run now**, schedule,
   last run (status timeline, stage outputs via `read_run_output`, review
   verdict, disclosed conflicts, synthesis), and run history. Not the agent chat.
2. Reuse the existing dialog's polling and stage mapping; delete the
   institution-specific copy rather than fork it.
3. Chat with a desk v1 is deliberately absent: a desk is a pipeline, not a
   correspondent. (Optional later: "ask about this run" through `eclipse-agent`
   with the synthesis in context.)
4. Filter desks out of the group-room member picker — a room member is a bot
   whose turn is an agent chat, and a desk is not that.
5. UI copy: one line in group rooms — "Members answer independently. For a
   pipeline, use a desk." No behaviour change.

Acceptance: Run now shows real stage transitions, a failed stage blocks its
dependents and says so, and nothing renders a fabricated stage.

### P3 — Trigger chain and context hand-off

Files: `automation/engine.py` (publish), `automation/tools.py` (`bot_create`/
`bot_update`), `automation/validation.py`, `dispatcher.py`,
`src/lib/bots/state.ts`, `schedule-editor.tsx`.

1. Publish `automation.completed` / `automation.failed` with
   `{ automationId, executionId, runId, status }` at the single terminal settle.
   Dedup already exists (`already_seen_event`, `AutomationEventDedup`); the event
   id is the execution id, so a redelivery cannot run a desk twice.
2. Accept `eventType`, `eventFilter`, `conditionExpression` on `bot_create` /
   `bot_update` for the matching trigger kinds (the engine already supports
   them; today only the raw API can author them).
3. `schedule-editor.tsx`: add "On event" authoring (event type + key/value rows)
   and replace the "preserved, not editable" note for new bots.
4. Optional `config.contextAutomationId`: at run time `_run_team` reads that
   bot's latest execution output (bounded) and prepends it to the first stage as
   **"unverified lead from <bot> run <id> as of <time> — re-verify; not
   evidence"**. Never store it into findings; a finding without an evidence ref
   still comes back `UNSUPPORTED_CLAIM`.
5. Tests: one completion → one desk run; filter matches only the named bot; a
   paused/disabled monitor cannot wake a desk; the lead is labelled; a stale or
   missing monitor run produces an explicit "no lead available" input.

Acceptance: a monitor run completes and the desk starts exactly once, with the
lead labelled and re-verified.

### P4 — Execution bridge (only after P0–P3 are stable)

Files: `src/components/bots/bot-trading-section.tsx` or the desk view,
`automation/dispatcher.py`, `trade/tools.py` (no new order path).

1. **Preferred:** the desk's proposal stage already called `order_preview`, so
   the operator confirms the card. Fix surfacing: the approval's
   `requestedByRunId` is the subtask run, not the desk execution, so
   `_pending_approvals` misses it. Match approvals across the run's lineage
   (`run_lineage.py`) instead of one id.
2. **Optional:** "Send to executor" starts a manual run of a chosen trading bot
   with the memo as its objective. The bot's own authority/mandate then applies;
   the desk still never submits.
3. Tests: approval created by a subtask is visible on the desk; an executor
   started from a memo still refuses live without L2; no second submit path.

Acceptance: the operator sees the approval the desk actually created, and an
executor's refusal codes are readable.

## Test plan

- Python: `test_automation_team_action.py` (P0), `test_automation_event_chain.py`
  (P3), additions to `test_team_service.py` (order-submit refusal) and
  `test_institution_preset.py` (preset path unchanged).
- TS: `desk.test.ts` (mapping/validation), a `team-client` test for
  `/team/validate`, and the existing bots screens text guard still passes.
- Manual: create a desk, run it, inspect one stage's memo by run id, edit a stage
  and confirm the version bump, then trigger it from a monitor.

## Risks

- **Cost.** N members × steps, and `maxCost`/`maxRuntimeMs` are advertised but not
  metered (known limitation in `bot-team-orchestration.md`). Default the builder
  to `maxConcurrency: 3`, short per-stage objectives, `ALLOW_PARTIAL` off.
- **Evidence laundering.** An injected monitor memo must stay a lead. Label it,
  never write it into findings, and keep `evidence_refs` mandatory.
- **Event storms.** A monitor on a 60 s interval can wake a desk repeatedly. Use
  `skip_if_running`, an `eventFilter` on the exact bot, and a condition gate; the
  event id dedup covers redelivery, not repeated distinct runs.
- **Desk edits mid-flight.** The `TeamRun.definition` snapshot protects the
  running graph; an edit only affects the next run.
- **Memory expectations.** Desk stages do not accumulate a chat memory across
  runs; learning lives in the trading bot's decision records. Say this in the
  desk UI so "it forgot" is not a surprise.
- **Room/desk confusion.** Two surfaces with similar names; keep desks out of
  rooms and link between them.

## Non-goals

- No orchestration inside group rooms, and no composing member replies.
- No per-seat bot rows for desks.
- No team-level order authority, no new order path.
- No model-authored graph.
- No new database table.

## Decisions taken

1. **Execution is operator-confirmed.** A desk's proposal stage calls
   `order_preview`; the desk room mounts the same trade-approval banner as the bot
   composer, and confirming sends the exact order through the normal submit route.
   A trading bot remains a separate object with its own mandate.
2. **One Bots list.** Desks live in the same sidebar list with a `desk` subtitle;
   they are excluded from group-room member pickers, not hidden from the operator.
3. **The monitor's memo is a trigger and a lead.** `contextAutomationId` is
   optional, injected only into starting stages, labelled unverified, and never
   written into findings.
