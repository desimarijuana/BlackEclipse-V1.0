---
title: Agent Workspace — Execution Observability
status: Current
last-verified: 2026-10-07
---

# Agent Workspace — Execution Observability

**Who this is for:** anyone asking "where does Eclipse show what the agent is
doing, and how do I extend it?"

The Agent Workspace is the app's **execution-observability layer**. It answers
"what is Eclipse doing right now" — current task, plan, tool activity, files
inspected/changed, terminal, research, browser, computer-use, artifacts,
approvals, context usage, telemetry — without flooding the chat transcript.

## The three-surface rule

```
CHAT             = conversation (the answer, and a one-line activity summary)
AGENT WORKSPACE  = execution visibility (what the agent is doing, in real time)
VIEWER           = large artifacts/output (opened from the workspace)
```

A tool's **output text never enters chat or the workspace**. Chat keeps a short
summary ("Tests completed. 3 failed."); the workspace shows the structured step
("npm test · exit 1 · 15,827 lines"); the Viewer renders the full output. This is
what keeps a tool-heavy run readable.

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
| UI (dock + 13 panels + viewers) | `src/components/agent-workspace/**` |
| Mount point | `src/app/layout.tsx` (`<AgentWorkspace />`, portaled) + top-bar toggle |

## It is an extension, not a redesign

There is **no right sidebar** in this app: "sidebar" everywhere means the LEFT
navigation rail (`src/components/layout/sidebar.tsx`). The only pre-existing right
region is `TerminalDock slot="right"` in the shell's primary row. The Agent
Workspace is therefore a **separate, global, portaled panel** that coexists with
the sidebar and every screen — it does not modify, replace or move any of them.

- Mounted once in `src/app/layout.tsx`, portaled to `<body>` (so its glass samples
  the page and it sits above keep-alive screens).
- Its store uses its own persistence keys
  (`black-eclipse:workspace-{open,panel,pinned}`) — never the `be_sidebar_*` keys
  or the `--sidebar-*` CSS tokens.
- The shell (`stock-chat.tsx`) is untouched, so the size ratchet and every
  existing tab/keep-alive behaviour are preserved.

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
ChatBot tab, the floating dock, future surfaces) feeds the workspace with no
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
- **Windowed lists.** Activity and artifact output render a slice (200 / 400
  rows) with incremental "show more", so no virtualization dependency is needed.
- **Duplicate/out-of-order tolerant.** Duplicate event *envelopes* are dropped by
  id at ingest; out-of-order frames are still applied (each maps to its own row)
  and counted in `state.outOfOrder` — never lost, never duplicated.
- **Lazy large output.** Artifact content is fetched only when the Viewer opens.

## Auto-active panels (gentle)

`pickAutoFocus` switches the panel when a subsystem becomes active
(permissions > research > browser > computer), but only when the user has not
manually chosen a panel (`userChosen`) and the target is not pinned. Pin a panel
from the header to keep it fixed. Pins, the selected panel, and open/closed state
persist in `localStorage`.

## Honesty rules (this is a financial product)

- Never expose private reasoning or chain-of-thought — only operational summaries.
- Never fabricate a value: an unreported metric renders "Not available" (cost,
  context window, coordinates, screenshots, telemetry).
- The Viewer states when the runtime retained only a **truncated** copy.
- The Approvals panel is a **UI surface**, not the authority: deciding POSTs to
  the existing approvals endpoint; the runtime's `approval.resolved` is final.

## Gaps (honest)

- Browser and computer-use have **no dedicated live screenshot rendering** yet —
  the panels show the session/URL/application, action count and any screenshot
  *reference the runtime emitted*, but do not stream pixels. There is no
  `/api/browser` or `/api/computer` front door; the workspace reflects the events
  that reach the run's stream.
- Subsystem (terminal/browser/computer) events emitted **without a run id** do
  not reach a run's SSE stream, so the workspace shows the tool-scoped events it
  does receive. Scoping those emitters to the run is a runtime change, not a UI
  change.
- Cost is shown only when the runtime reports one (`RunTelemetry.costUsd`); it is
  never derived from a price table the UI does not own.
