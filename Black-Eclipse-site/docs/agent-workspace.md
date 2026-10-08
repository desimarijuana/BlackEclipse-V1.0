---
title: Agent Workspace — Execution Observability
status: Current
last-verified: 2026-10-07
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
| UI (docked sidebar + 4 panels + Viewer) | `src/components/agent-workspace/**` |
| Mount point | `src/components/screens/stock-chat.tsx` (`<AgentWorkspace />`, a sibling of the main column) + top-bar toggle |

## It is a docked right sidebar

The Agent Workspace is a **real docked column** in the app shell's primary row —
mounted as a sibling of the main panel in `stock-chat.tsx`, so the main panel
**shrinks to make room** instead of being overlapped. This is the same pattern as
`TerminalDock slot="right"`; the two can coexist (both are right-side columns).

Previously it was a global, portaled, floating panel. That was replaced because a
floating overlay "is not a sidebar" and its 13 tabs buried the useful output
under telemetry noise (see the ADR-042 amendment in `docs/DECISIONS.md`).

- **Minimal tabs:** **Output** (default), **Changes**, **Approvals**, **History**.
  The overview/activity/tasks/context/telemetry/research/browser/computer/
  artifacts panels were removed as noise — the Output feed carries the signal.
- **Resizable:** drag the inner (left) edge on desktop; width persists under
  `black-eclipse:workspace-width` (clamped 300–760 px). No hard border frame — the
  frosted-glass edge is the separation.
- On narrow screens it becomes a full-width strip below the content (never an
  overlay).
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

## Honesty rules (this is a financial product)

- Never expose private reasoning or chain-of-thought — only operational summaries.
- Never fabricate a value: an unreported metric renders "Not available" (cost,
  context window, coordinates, screenshots, telemetry).
- The Viewer states when the runtime retained only a **truncated** copy.
- The Approvals panel is a **UI surface**, not the authority: deciding POSTs to
  the existing approvals endpoint; the runtime's `approval.resolved` is final.

## Gaps (honest)

- **Telemetry detail is not surfaced.** Runs, tokens, cost and context-window
  figures are still normalized into state and remain available to any future
  panel, but the removed Overview/Telemetry/Context tabs are gone — the sidebar
  shows Output, Changes, Approvals and History only. Add a tab back if the need is
  real.
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
