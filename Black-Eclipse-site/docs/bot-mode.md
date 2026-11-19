---
title: Bots Mode
status: Current
last-verified: 2026-11-18
---

# Bots Mode

**Who this is for:** anyone asking "what is a bot, where does its conversation
live, when does it run, and why did it or didn't it?"

Bots mode is the app's chat-first surface over the Native Automation Engine
(`docs/harness/automation-engine.md`). A **bot** is an ordinary `Automation`
tagged `bot`/`monitor`; this page covers only the workspace, the conversation
state, and the two deliberate cross-surface rules.

## Layout (one of each)

| Area | Owner | Notes |
| --- | --- | --- |
| Conversation | `src/components/bots/bot-chat.tsx` / `group-chat-room.tsx` | The page IS the conversation; no page header. |
| Bot + group list | `src/components/bots/bots-sidebar-panel.tsx` | The ONE list, rendered in the left sidebar only in Bots mode. |
| Scheduler + monitors | `src/components/bots/scheduler-dock.tsx` | Right-docked Agent Workspace slot; opens from the sidebar. |
| Empty state | `src/components/screens/bots/bots-screen.tsx` | New bot, new group, finance pack, Institution committee. |

Deep links are `?tab=bots&bot=<id>` / `?tab=bots&group=<id>`. Escape closes an
open conversation and returns to the empty state (suppressed while a field or
dialog owns Escape).

## A bot's parts

- **Identity**: name, title/description, ghost face (Bot / Generate / Upload /
  Pet) or an uploaded photo.
- **Brain**: a live agent preset (built-ins + the operator's Settings › Agents
  presets), a saved Graph Studio workflow, or a saved quant **strategy** version.
  A workflow bot's message becomes the graph run's Start value. A strategy bot
  decides on the last closed bar and trades; it does not answer from an agent
  loop. The preset list is never hardcoded in the UI.
  **The same brain answers both chat and scheduled runs**: the interactive turn
  forwards the bot's `agentId` to the chat run, so a bot set to a specialist
  preset does not secretly answer as `eclipse-agent`. An unpinned bot defaults to
  `eclipse-agent`, which is the full agent.
- **Objective**: the standing instructions injected as the persona each turn.
- **Schedule**: manual, once, daily, weekdays, weekly, monthly, interval (floor
  30s), cron, event, condition. The trigger's IANA zone is preserved on edit so a
  bot created elsewhere does not silently shift.
- **Run behaviour**: misfire policy, concurrency conflict rule, max concurrent
  runs, max attempts, per-run timeout, and an optional provider/model pin.

## Trading bots

A **strategy bot** (`action.type = "run_strategy"`) is an automation whose brain
is one saved strategy version. It is created as a draft, then **prepared**: the
server checks the approval + backtest, creates a bounded trial/mandate and stores
the operator's standing consent on the bot. Only then is it activated.

- **Modes**: `shadow` (decide, send nothing), `demo`, `live`.
- **Auto mode**: the operator types the consent phrase ONCE. `action.config.consent`
  is a standing grant (modes, symbols, orders/day, margin, positions, expiry); the
  bot renews its own bounded mandate while it is valid. Revoking is one PATCH; an
  objective/strategy edit bumps the version and invalidates the mandate.
- **Authority**: L0 proposes, L1 fills demo, L2 fills live. It lives on
  `definition.executionAuthority` and is enforced at submit by `trade/authority.py`.
  Live also needs an armed connection and a bot-pinned mandate.
- **Decisions**: every run persists a `DecisionRecord` on the execution —
  including "no signal", "session closed" and every refusal code. Run history and
  the Trading section both read it, so "why didn't it trade?" is answerable.
- **Learning**: repeated failures (same code, N times) become one concrete
  proposal in `src/lib/bots/trading/learning.ts`. The bot shows the proposal and
  waits; applying it patches config/authority and re-prepares under the standing
  consent. It can only tighten on its own.
- **Visual teaching**: up to 4 bounded images with captions. In a chat turn and
  on a scheduled agent run the image is sent as a REAL image part (the provider
  decides whether it can see it); a text block labels it as pattern guidance,
  never live market data.
- **Multi-symbol**: with "scan the universe each bar", the runner evaluates every
  symbol and acts on the first actionable signal (exits first, then the highest
  score). Without it, the bot is pinned to its first symbol. The trading panel's
  **Find trades** button runs the same last-bar scan and can adopt the
  actionable symbols as the universe (then re-prepares under the standing
  consent). A scan is a condition, never an order.
- **Learning in chat**: a trading bot's chat turn carries a lesson digest built
  from its own recent decisions, so "why didn't you trade?" and "can we improve?"
  are answered from real refusal codes. The bot may propose; it may not apply.

Lifecycle: pausing, disabling, archiving or deleting a trading bot revokes its
mandates and stops its trial. Open positions are **never** closed automatically;
the operator closes them explicitly.

### Agent trading bots

An **agent** bot (the normal LLM brain) can trade too. Turning trading on gives it
the same leash and a bot-pinned mandate: `prepare` takes an agent bot straight to a
`MANDATE DEMO|LIVE <label>` (no strategy trial), then stores the same standing
consent. At L0 it proposes with `order_preview`; at L1 it may fill a demo account;
at L2 it may fill live under the mandate. The agent still decides with its tools —
this does not create a second order path.

- **Brain is editable after creation**: an agent bot's preset and model, a
  workflow bot's workflow (with a Graph Studio link), and a strategy bot's pinned
  strategy (re-prepared under the standing consent). Every edit goes through the
  real automation API and bumps the version.
- **The New-bot strategy list is a catalog, not a dropdown**: search, evidence
  badges (backtest/approval/paper), archived toggle, Refresh, and “Open in
  Strategy Studio”. It reads the same shared catalog as the studio, so an
  agent-made strategy appears after the next refresh or turn completion.
- **Trading authorization is gated and remembered**: Authorize is disabled while
  the selected broker is unavailable (with the terminal reason), live needs L2
  plus an armed connection; the L0/L1/L2 ladder shows what L2 requires and offers
  the request once the measurable gates pass; the last used venue is preselected
  when a bot has none.

### The EUR/USD 1-minute starter
The Bots empty state has one button, **EUR/USD 1-minute bot**. It seeds a complete,
honest vertical: the strategy `eurusd_m1_ema_rsi` (EMA 9/21 cross with an RSI veto,
ATR 1.5 stop, 1.5R target, spread/slippage modelled), a **90-day 1-minute
backtest** as evidence, an approval note for shadow execution, the automation
(a 60-second interval, `misfire: skip`, one position, four orders a day, a
5-minute cooldown, London hours) and a **shadow** trial. It is idempotent by name
and every gate failure says which gate blocked it.

It starts in shadow so it cannot place money without you. Open its **Trading**
panel, type the consent phrase once (demo or live), and from then on it renews its
own bounded mandate — no repeated phrases. Live additionally needs tier L2 and an
armed connection.

## Desks (a saved team run)

A **desk** is a bot whose brain is a team, not a single agent:
`action.type = "run_team"` with `action.config.team` holding the
`TeamDefinition`, tagged `bot` + `desk`. It is created from the Bots empty state
(**New desk**) and edited in the same builder. One list, one lifecycle: schedule,
pause, delete, version and run history are the automation's own.

- **Roles are stages.** Each stage is a full member of the team (real instructions
  and a least-privilege tool list) and runs as its own durable task. The builder's
  role templates seed research / challenge / proposal / risk / decision; stages
  read an earlier stage's memo by its run id, never its prose.
- **It proposes; a trading bot executes.** A team has no pinned mandate, so
  `order_submit` is refused in every member (create-time validation and the
  delegated surface). A proposal stage calls `order_preview`; the operator
  confirms the approval card, or a separate trading bot fills under its own
  authority. There is no second order path.
- **It can wake on a bot's finish.** "When a bot finishes" makes an event trigger
  on `automation.completed` filtered to that bot, and passes the bot's last result
  in as a labelled **unverified lead** the first stage must re-check. The lead is
  never written into findings.
- **It runs from its own room.** Selecting a desk opens the stage timeline, the
  result, and the run history — not the agent composer. Desks are excluded from
  group-room members, because a room member answers as a correspondent. When a
  proposal stage called `order_preview`, the same self-polling trade-approval
  banner the bot composer mounts appears in the desk room, so the operator can
  confirm (or deny) the exact order there. A desk's execution also reports that
  approval: `Dispatcher._pending_trade_approvals` matches the stage's run, not only
  the team's root run.

The team layer itself (graph, conflicts, review, budgets) is
`docs/harness/bot-team-orchestration.md`; the design and its phases are
`docs/harness/desks-plan.md`.

## Conversation durability

The visible threads are **local-first**: the stores hydrate from localStorage so
the UI renders before (and without) the runtime. Every persisted mutation is
also mirrored, best effort, to a `BotState` document in JDdS:

- keys: `chat` (per-bot threads) and `groups` (rooms + transcripts);
- client sync: `src/lib/bots/state-sync.ts`;
- route: `src/app/api/bots/state/[key]/route.ts`.

The invariant is **newest client timestamp wins**. On hydrate the store renders
local data, then adopts the server copy only when its `updatedAt` is newer; a
newer local copy is pushed instead. A failed/offline/oversized mirror never
loses the local copy. Other tabs adopt a written document through the `storage`
event, so two tabs converge without a reload. Clearing localStorage therefore
recovers the last mirrored document; it is not a sync engine and does not merge
conflicting edits from two tabs made at the same instant.

## When a bot runs

- **Scheduler / event / condition / webhook / fabric** launches require the
  automation to be `active`.
- **Run now** is an explicit operator request and also works while `paused`.
  Pause stops the scheduler, not the operator. Draft / disabled / archived bots
  do not run until enabled. The opt-in is `allow_paused=True` on the automation
  run route only — agent tools, the legacy job webhook and the fabric worker do
  not pass it.

## The model pin is consistent

A bot may pin `provider` + `model` on `action.config.modelSettings`. All three
surfaces apply the same rule:

1. an interactive chat turn (the bot composer);
2. a scheduled/manual run (automation dispatcher);
3. a Graph Studio `agent.bot` node that reuses the bot.

In all three, the **provider/model come from the bot**, while credentials and
the base URL resolve from the runtime / graph run's in-memory settings. A pin on
an unconfigured provider fails honestly rather than silently using another
model. (An explicit model chosen by the caller — e.g. the main-chat composer
during `@`-delegation — wins, and the bot's provider pin is dropped so a model
is never paired with the wrong provider.)

## Chat ↔ bots: one capability contract

A bot is an automation on the same run plane, so "the agent can do it" and "a
bot can do it" are meant to be the same sentence. A chat turn and a scheduled
bot run both carry:

- the bot's **own brain** (`action.agentId`, default `eclipse-agent`) and
  therefore the same tool allowlist — including automation, scheduling and team
  tools;
- the same read-only **analysis sandbox**, model pin, autonomy profile,
  workspace and reference images;
- the same **private-memory pipeline** (a bot only ever uses its own
  `conversation` bucket).

Deliberate differences — not parity gaps:

| | Chat turn | Scheduled bot run |
| --- | --- | --- |
| Approval | pauses mid-run (`approvalMode: "ask"`) | no operator present: the automation-level `permissions.requiresApproval` gate runs first, and an order awaiting a decision is reported as `AWAITING APPROVAL` |
| Memory | the signed-in user's scope | `conversation` scope, `bot-<id>` |
| Wall clock | 20 min default | `execution.maxRuntimeS`, 20 min default, up to 24 h |
| Trigger | the composer | the scheduler (cron / interval / event / condition / webhook) |

When a capability is added to one path it belongs in the other:
`python/tests/test_automation_bot_parity.py` and
`src/lib/agent/registry.test.ts` fail if the bot/scheduled request stops
carrying the shared fields.

## Chat and the full agent

Capability parity is the rule, not a best effort. A bot conversation uses the
same run plane as main chat, so it also gets the human-in-the-loop surfaces:

- **Approvals** — an effectful tool can pause the run; the bot and group threads
  render `ApprovalCard` and decide through
  `/api/harness/mcp/approvals/<id>/decide`.
- **Clarify** — a paused `clarify` question renders `ClarificationCard` and
  answers through `/api/harness/mcp/approvals/<id>/answer`.
- **Documents** — the composer attaches files to the same
  `bot-<id>` / `group-<id>-<bot>` session folder the run already reads, so
  extracted text reaches the model exactly as it does in main chat. A group
  attachment is mirrored into every member's folder (each member answers in its
  own session).
- **Computation** — scheduled/manual bot runs set `analysisEnabled`, the same
  read-only sandbox a chat turn gets, so a bot can reproduce a derived figure
  instead of only narrating it. It is still gated by `analysis.execute`.
- **Stop / edit / regenerate / feedback / run history** are unchanged.

Intentionally different: a **workflow bot** answers by running its graph, not
by calling tools; and an `agent.bot` graph node is one bounded turn (`maxSteps`
8 by default), not a schedule or a full chat.

## Packs and teams

- **Finance starter pack**: six editable scheduled bots plus the `Markets Desk`
  room; idempotent by name, seeded through the real automation API.
- **Institution committee**: analyst → bull → bear → trader → risk → PM, seeded
  as bots plus the `Investment Committee` room, driven by `run_team`
  (`docs/harness/institution-preset.md`).
- **Monitors**: condition-based portfolio monitors armed from the scheduler dock.

## Where to change what

- Invoker / persona / memory scope: `src/lib/bots/invoke.ts` (one place for bot
  turns, group turns and main-chat @-delegation).
- Store/state rules: `src/lib/bots/{chat-store,groups-store,state-sync}.ts`.
- Automation behaviour: `python/harness/automation/` (engine, dispatcher,
  policies) and `docs/harness/automation-engine.md`.
- Graph reuse: `python/harness/graph_runtime/agent_nodes.py` + `bootstrap.py`.
