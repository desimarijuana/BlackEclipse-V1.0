---
title: Bots Mode
status: Current
last-verified: 2026-11-10
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
  presets) or a saved Graph Studio workflow. A workflow bot's message becomes the
  graph run's Start value. The preset list is never hardcoded in the UI.
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
