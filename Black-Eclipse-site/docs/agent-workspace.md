---
title: Agent Workspace — Execution Observability
status: Current
last-verified: 2026-10-12
---

# Agent Workspace — Execution Observability

**Who this is for:** anyone asking "where does Eclipse show what the agent is
doing, and how do I extend it?"

The Agent Workspace is the app's **execution-observability layer**, docked as a
**right sidebar**. It answers "what is Eclipse doing right now, and what did it
produce" — a live output feed of tool activity (with large outputs expanded in
place), file changes, approvals and run history — without flooding the chat
transcript.

## The three-surface rule

```
CHAT             = conversation (the answer, and a one-line activity summary)
AGENT WORKSPACE  = execution visibility (what the agent did/produced, in real time)
VIEWER           = large artifacts/output (opened from the workspace)
```

A tool's **output text never enters chat or the workspace collapsed view**. Chat
keeps a short summary ("Tests completed. 3 failed."); the workspace's Output feed
shows the structured row ("npm test · exit 1 · 15,827 lines") that expands to the
bounded output; the Viewer renders it full-height when opened. This is what keeps
a tool-heavy run readable.

## Where it lives

| Concern | Path |
|---|---|
| Normalized model (pure types) | `src/lib/agent-workspace/types.ts` |
| Raw frame → normalized events | `src/lib/agent-workspace/normalize.ts` |
| Normalized events → state (pure fold) | `src/lib/agent-workspace/reducer.ts` |
| Live state store (zustand + immer) | `src/lib/agent-workspace/store.ts` |
| Stream client (live) / trace replay (history) | `src/lib/agent-workspace/stream.ts`, `history.ts` |
| Existing-stream ingest seam | `src/lib/agent-workspace/ingest.ts` |
| Display formatting (pure) | `src/lib/agent-workspace/format.ts` |
| Context-usage math (pure) | `src/lib/agent-workspace/context-usage.ts` |
| Reopen a past chat → load its last run | `src/lib/agent-workspace/restore.ts` |
| UI (docked sidebar + 5 panels + Viewer) | `src/components/agent-workspace/**` |
| Mount point | `src/components/screens/stock-chat.tsx` (`<AgentWorkspace />` — or, in Bots mode, `<BotSchedulerDock />` — a sibling of the main column) + top-bar toggle + `workspace-keybind.tsx` (mounted in `app/layout.tsx`) |

## It is a docked right sidebar

The Agent Workspace is a **real docked column** in the app shell's primary row —
mounted as a sibling of the main panel in `stock-chat.tsx`, so the main panel
**shrinks to make room** instead of being overlapped. This is the same pattern as
`TerminalDock slot="right"`; the two can coexist (both are right-side columns).

Previously it was a global, portaled, floating panel. That was replaced because a
floating overlay "is not a sidebar" and its 13 tabs buried the useful output
under telemetry noise (see the ADR-042 amendment in `docs/DECISIONS.md`).

- **Minimal tabs:** **Output** (default), **Context**, **Changes**, **Approvals**,
  **History**. The overview/activity/tasks/telemetry/research/browser/computer/
  artifacts panels were removed as noise — the Output feed carries the signal. The
  **Context** tab was added back (2026-10-09) once the need was concrete: a
  session-context gauge answering "how full is the model's window, and what fills
  it?", mirroring the OpenCode session sidebar. It reads the already-normalized
  `state.context` + `state.contextSources` + `state.telemetry` and resolves the
  window from the declared model catalog (`context-usage.ts`).
- **Toggle:** **Ctrl/Cmd + Shift + E** (the VS Code "toggle Explorer" chord). A
  dedicated capture-phase listener (`src/components/agent-workspace/workspace-keybind.tsx`)
  is mounted in `app/layout.tsx` beside the terminal keybind, so it works whether
  the sidebar is open or closed; it skips while typing. Listed in the
  keyboard-shortcuts help dialog.
- **Output feed density (Claude-Code style):** timestamps are hidden from the row
  (kept in the expanded detail), consecutive same-tool calls GROUP into one row
  with a ×N badge (expanding to the list), and a **Collapse all** control appears
  in the feed header whenever a row is expanded.
- **Resizable:** drag the inner (left) edge on desktop; width persists under
  `black-eclipse:workspace-width` (clamped 300–760 px). No hard border frame — the
  frosted-glass edge is the separation.
- On narrow screens it becomes a full-width strip below the content (never an
  overlay).
- **Bots mode swaps the dock's content to the scheduler.** On the Bots tab the
  right dock renders `src/components/bots/scheduler-dock.tsx` (hosting
  `scheduled-jobs-panel.tsx`) instead of the run observability panels. It shares
  the SAME `useWorkspaceStore.open` state, so the left-sidebar **Open scheduler**
  button, the top-bar toggle and **Ctrl/Cmd + Shift + E** are all one control.
- Its store uses its own persistence keys
  (`black-eclipse:workspace-{open,panel,width}`) — never the `be_sidebar_*` keys
  or the `--sidebar-*` CSS tokens.

Reachability is asserted in
`src/components/agent-workspace/agent-workspace-reachability.test.ts`.

## Event-driven, one stream (no second bus)

The Python runtime already emits ~140 event types over ONE SSE stream
(`GET /api/harness/runs/{id}/stream`, see `docs/harness/architecture.md`). The
workspace consumes that same stream — it does **not** add an event bus, an agent
loop, or a model adapter.

```
python/harness RunEmitter ─▶ SSE ─▶ src/lib/agent/registry.ts (createSseParser)
     │                                       │
     │                        ingestHarnessFrame(event, data)   ← the ONE new line
     │                                       ▼
     │                   agent-workspace/normalize.ts → WorkspaceEvent[]
     │                                       ▼
     │                   agent-workspace/store.ts (immer, throttled commit)
     │                                       ▼
     │                   workspace.tsx panels (selector subscriptions)
     └── persisted trace ─▶ /api/harness/runs/{id}/events ─▶ history.replayTrace()
```

`ingest.ts` is the ONLY glue: it binds the frame's run, normalizes it, and hands
it to the store. It lives outside `useAgentRun` so **every** chat surface (the
ChatBot tab, the floating dock, future surfaces) feeds the sidebar with no
per-surface wiring.

The workspace has its own normalizer (`normalize.ts`) rather than extending the
chat's `HarnessUiEvent` union, because it maps a **superset** of events into a
different shape (categories, changes, artifacts, telemetry). It reuses the chat's
human labels (`toolLabel`) so a tool name never reads differently in two places.

## State model (normalized, bounded)

`AgentWorkspaceState` carries: `execution` (status/phase/current tool/iteration),
`model`, `tasks`, `activity`, `changes`, `artifacts`, `permissions`, `errors`,
`context` + `contextSources`, `telemetry`, `research`, `browser`, `computer`.

The reducer is pure and **mutates a draft**; the store applies it under
`immer.produce`, so React gets structural sharing while a batch of events folds
in one pass. Bounds keep client memory flat under a runaway run: activity 5,000
(trim slack 512), artifacts 500, errors 500, changes 2,000, dedupe maps capped.
Large output is represented by an `ArtifactRef` **handle**, never inlined.

Counters are honest: `filesInspected`/`researchSources`/`queries` count *distinct*
keys (a file read twice counts once); `toolsUsed`/`toolCalls`/`toolErrors`/`retries`
are incremented from real events. Nothing is inferred.

## Performance contract

- **Batched commits.** `store.ingest` queues events and commits at most once per
  150 ms; 10k events produce a handful of React renders, not 10k.
- **Selector subscriptions.** Panels read narrow slices, so only the visible
  panel re-renders on a change.
- **Windowed lists.** The Output feed and artifact content render a slice
  (400 rows) with incremental "show more", so no virtualization dependency is
  needed.
- **Duplicate/out-of-order tolerant.** Duplicate event *envelopes* are dropped by
  id at ingest; out-of-order frames are still applied (each maps to its own row)
  and counted in `state.outOfOrder` — never lost, never duplicated.
- **Lazy large output.** Artifact content is fetched only when a result row is
  expanded (or the Viewer opens).

## Selected panel + open/closed state

The selected tab and open/closed state persist in `localStorage`
(`black-eclipse:workspace-{panel,open}`, plus `width`). There is no auto-focus or
pinning: the Output feed is the default and stays put. A pending approval shows an
attention dot on the Approvals tab; a running run shows one on Output.

## Reopening a past chat

Live runs bind the workspace through the SSE stream (`ingest.ts`). When the user
opens a **past** chat, there is no stream to bind — so `restore.ts` points the
store at that conversation's most recent run instead:

1. resolve the run id from the conversation's last `Message.runId`; if the chat
   predates that field, fall back to the runtime's session→run list
   (`GET /api/sessions/{chatId}` → `runs`, last = newest);
2. rebuild the run with `loadRunSnapshot` — replay the persisted event trace
   (`replayTrace`) *and* fold in the authoritative run record
   (`GET /api/harness/runs/{id}`: tokens, model, context window) which the trace
   may not carry;
3. commit it with `store.loadRun(runId, snapshot)`.

Opening a chat with no runs, or starting a new chat, calls `store.clear()`. A
live run that begins while a history load is in flight is never clobbered
(`restore.ts` checks the store's current run + status first). The History tab
uses the same `loadRunSnapshot` path, so a replayed run and a reopened chat are
built identically.

## Honesty rules (this is a financial product)

- Never expose private reasoning or chain-of-thought — only operational summaries.
- Never fabricate a value: an unreported metric renders "Not available" (cost,
  context window, coordinates, screenshots, telemetry).
- The Viewer states when the runtime retained only a **truncated** copy.
- The Approvals panel is a **UI surface**, not the authority: deciding POSTs to
  the existing approvals endpoint; the runtime's `approval.resolved` is final.

## Gaps (honest)

- **Context is partial by design.** The **Context** tab surfaces the context
  window, total/input/output tokens, remaining, turns kept/dropped, memories and
  estimated cost, plus a source-breakdown gauge. Two honest limits: the window is
  the runtime-reported one when known, else the catalog's declared window (never
  guessed); and `totalTokens` is the run-cumulative sum across model steps
  (`reducer.ts`), matching OpenCode's session-total semantics — it is not a
  single-request prompt size. The remaining telemetry that has no home (retries,
  tool errors) is still normalized into state and shown in the Output feed.
- **Browser / computer / research have no dedicated panels.** Their events still
  appear as rows in the Output feed, but there is no session/URL/screenshot view
  and no live screenshot pixels. There is no `/api/browser` or `/api/computer`
  front door; the sidebar reflects only the events that reach the run's stream.
- Subsystem (terminal/browser/computer) events emitted **without a run id** do
  not reach a run's SSE stream, so the sidebar shows the tool-scoped events it
  does receive. Scoping those emitters to the run is a runtime change, not a UI
  change.
- Cost is shown only when the runtime reports one (`RunTelemetry.costUsd`); it is
  never derived from a price table the UI does not own.
