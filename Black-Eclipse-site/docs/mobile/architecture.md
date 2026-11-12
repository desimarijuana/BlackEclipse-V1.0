---
title: Eclipse Mobile — Architecture
status: Proposed
last-verified: 2026-11-12
---

# Architecture

## 1. What the desktop does today (and why it cannot be copied)

```
Tauri window (desktop/src-tauri/src/main.rs)
  └─ spawns runtime/node.exe → scripts/desktop-server.js
        └─ next start -H 127.0.0.1:3100
             └─ spawns vendored python.exe → uvicorn (FastAPI + LangGraph)
  └─ WebView loads http://127.0.0.1:3100
```

Evidence: `desktop/src-tauri/src/main.rs` (`supervise`, `find_node`,
`WebviewUrl::App("index.html")` then navigation to loopback), `desktop/README.md`
("How it boots"), `scripts/desktop-server.js`.

That topology is unavailable on mobile for four independent reasons:

1. Tauri 2 does not support `bundle.externalBin` sidecars on Android/iOS.
2. iOS forbids downloading or executing code that changes app functionality
   (App Store guideline 2.5.2); a Node server plus a Python interpreter is exactly
   that.
3. The payload is desktop-sized: a ~450–500 MB installer, a 361 MB `jdds.db`, and
   a 1.6 GB `agent-memory.db`.
4. Mobile OS lifecycle suspends or kills backgrounded apps; a server child process
   and an always-on scheduler cannot be kept alive.

The mobile app therefore **owns its execution**. It is not a thin client and not a
repackaged web app.

## 2. Topology

```
┌──────────────────────────────────────────────────────────────────────┐
│ Tauri 2 app (one WebView per device)                                 │
│                                                                      │
│  ┌──────────────────────────────┐      ┌───────────────────────────┐ │
│  │ React 19 UI (Vite)           │      │ Rust runtime              │ │
│  │                              │ IPC  │                           │ │
│  │ • bot list / editor          │◄────►│ • commands (start/cancel) │ │
│  │ • 1:1 + group chat           │events│ • agent loop              │ │
│  │ • streaming transcript       │      │ • provider adapters       │ │
│  │ • approval / clarify sheets  │      │ • tool registry           │ │
│  │ • memory + history           │      │ • approvals + digests     │ │
│  │ • settings / keys (no keys)  │      │ • scheduler + catch-up    │ │
│  └──────────────────────────────┘      │ • SQLite (WAL, FTS5)      │ │
│                                        │ • key custody             │ │
│                                        └──────────┬────────────────┘ │
│                                                   │                  │
│  OS integrations                                  │ HTTPS            │
│  • notifications (local)                          ▼                  │
│  • haptics / biometrics                    OpenAI / Anthropic /      │
│  • file picker / share                     Google / OpenRouter /     │
│  • deep links                              search provider           │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
        SQLite file in the app sandbox
        (bots, threads, messages, runs, run_events,
         tool_calls, approvals, memories, schedules,
         attachments, provider_configs)
```

There is **no loopback origin**, no Next server, no Python process and no local
host. The WebView loads bundled assets from the app package.

## 3. Layers and ownership

| Layer | Owns | Must never own |
| --- | --- | --- |
| React UI | presentation, input, optimistic render, navigation | run state, retries, tool execution, keys, SQL |
| Tauri IPC | typed commands + events, capability checks | business rules |
| Rust runtime | run lifecycle, provider I/O, tool calls, approvals, persistence, scheduling decisions | rendering |
| SQLite | durable truth for bots, threads, messages, runs, events, memory, schedules | secrets (key material) |
| OS keychain | provider keys and the DB encryption key | conversation content |
| External providers | model inference, web search | durable app state |

The rule is enforced by construction: the UI **cannot** open the database. The
SQL plugin is deliberately not used (see `dependency-evaluation.md`). All reads and
writes cross named commands.

### Why Rust owns the run

iOS may reclaim the WebView under memory pressure, and both platforms suspend the
process when backgrounded. If the JS context owned a run, a re-render or a
WebView reload would lose it. Instead:

- a run row is inserted **before** the first provider request;
- every non-delta event is persisted with a monotonic `seq`;
- the UI reattaches by `(runId, lastSeq)` and replays the gap;
- deltas are checkpointed into the assistant message, so a resumed UI shows the
  text received so far;
- a run with no terminal event and no live task is reconciled to `interrupted` on
  the next app start.

Detail: `agent-runtime-design.md`.

## 4. Execution targets

Bots are defined independently of where they run. The contract carries a target:

| Target | v1 | Meaning |
| --- | --- | --- |
| `local_mobile` | **implemented** | The in-app Rust runtime on this device |
| `local_desktop` | reserved | The existing Python harness, addressed by a future client |
| `remote_worker` | reserved | A future always-on runner; **not built and not required** |

The app must never silently change target. A bot's stored target defaults to
`local_mobile`; an unknown target fails with a typed error rather than falling back.
This is the seam that lets a future cloud runner exist without forking the bot
model. See D4 in `risks-and-decisions.md`.

## 5. Contracts, not shared runtimes

Desktop and mobile share **schemas**, not code:

Both live at the **repository root**, outside `Black-Eclipse-site/`, so the
desktop `tsconfig` (`include: **/*.ts`) does not pick them up.

```
packages/agent-contracts/          (new, versioned v1)
  schema/
    bot.schema.json
    thread.schema.json
    message.schema.json
    run.schema.json
    run-event.schema.json
    tool-call.schema.json
    approval.schema.json
    memory.schema.json
    schedule.schema.json
    provider.schema.json
  src/index.ts                     generated TypeScript types
  rust/src/lib.rs                  generated Rust types (typeshare or schemars)
  fixtures/desktop/*.json          captured desktop event/run fixtures
  scripts/generate.mjs
```

Rules:

- **JSON Schema is the source of truth.** TS and Rust are generated, never
  hand-edited.
- The event vocabulary reuses the Python runtime's existing names where they
  already mean the same thing: `run.created`, `run.started`, `model.requested`,
  `model.delta`, `model.completed`, `tool.requested`, `tool.completed`,
  `tool.failed`, `approval.requested`, `approval.resolved`,
  `clarification.requested`, `clarification.answered`, `run.completed`,
  `run.failed`, `run.cancelled`. Mobile adds `run.interrupted` and
  `message.checkpoint`.
- Contract version is explicit in every payload; an unknown major version is
  rejected.
- Desktop adoption is a **conformance test**, not a rewrite: fixtures produced by
  `src/lib/agent/events.ts` must validate against the schema. Only if a mismatch is
  a real semantic divergence does desktop code change.

This package is not wired into the Next build in Phase 0. It becomes a dependency
of `mobile/` first; desktop import is a separate, optional phase.

## 6. Domain model (mobile projection)

```
Bot ──< Schedule
 │
 ├──< Thread(kind=bot) ──< Message
 │        └──< Run ──< RunEvent
 │                 ├──< ToolCall ──< Approval
 │                 └──< RunMember (group only)
 │
 └──< GroupMember >── BotGroup ──< Thread(kind=group) ──< Message
```

- A **bot** is the mobile projection of an `AutomationView` tagged `bot`/`monitor`.
  It keeps identity, objective, brain (`agent preset` or model pin), schedule and
  run behaviour. Server-only fields (`permissions`, `delivery`, `limits`,
  `breaker`) are modelled as local policy where they still make sense and dropped
  where they do not.
- A **thread** is either a 1:1 conversation (`bot_id`) or a room (`group_id`).
- A **group** has 2–6 members; each member answers in its own run with its own
  memory scope `group-<groupId>-<botId>`.
- A **message** is a user or assistant turn. Assistant messages may carry
  `run_id`, `author_bot_id`, approval/clarify state and delegations.
- A **run** is one execution of one bot turn. Tools and approvals hang off it.

The exact SQLite shape is in `data-model.md`.

## 7. Provider layer

A normalized `Provider` trait; four adapters in v1:

```
chat_stream(request) -> Stream<ProviderEvent>
ProviderEvent =
  | TextDelta(text)
  | ToolCallStart(id, name)
  | ToolCallArgsDelta(id, fragment)
  | ToolCallEnd(id)
  | Usage(input, output, cost?)
  | Finished(reason)
  | Error(class, message, retryable)
```

Provider-specific wire formats never escape the adapter. Tool-call IDs are
synthesized when a provider does not supply stable ones, and the mapping is stored
on the tool call row. Full request/response shapes: `agent-runtime-design.md` §5.

## 8. Tool layer

Static registry, compiled in. A tool declares:

```rust
pub struct ToolSpec {
    pub name: &'static str,
    pub description: &'static str,
    pub schema: &'static str,          // JSON Schema
    pub permission: Permission,        // Read | Write | ExternalAction
    pub risk: Risk,
    pub timeout: Duration,
    pub max_output_bytes: usize,
    pub requires_approval: bool,
}
```

v1 tools: `web_search`, `url_fetch`, `remember`, `recall`, `conversation_search`,
`read_attachment`, `group_context`. No shell, no Python, no JS, no dynamic
downloads, no unrestricted filesystem. Detail: `agent-runtime-design.md` §6 and
`security-model.md`.

## 9. Scheduling and lifecycle

```
app foreground ──► scheduler tick (30 s while active)
                   ├─ due local schedules → start run
                   └─ catch-up policy (skip | run_once | catch_up_max)

app background ──► OS may suspend; in-flight run is checkpointed.
                   Android: WorkManager slot (≥15 min, inexact).
                   iOS: BGAppRefresh/BGProcessing (opportunistic).

app cold start ──► reconcile runs without terminal events → interrupted
                   recompute next_run_at; offer "missed while away"
```

Always-on execution is **not** delivered by v1. The honest matrix and the exact
platform APIs are in `scheduling-limitations.md`.

## 10. Build and release topology

| Target | Where it builds | Notes |
| --- | --- | --- |
| Android debug | This Windows machine | Android Studio + NDK + Rust Android targets |
| Android release | CI `ubuntu-latest` (or Windows) | Keystore + AAB/APK |
| iOS simulator/device | macOS only | Xcode + CocoaPods; CI `macos-latest` |
| Shared contracts | Any | Node script generates TS + Rust |
| UI | Any | Vite build, bundled into the app |

The desktop release chain (`desktop:payload` → `desktop:build` → `desktop:package`
→ `desktop:installer`) is untouched. Mobile has its own `mobile:*` scripts.

## 11. Size budget (targets, to be measured)

| Component | Target |
| --- | --- |
| Rust binary + WebView shell | 12–20 MB |
| JS bundle (no Monaco/Plotly/Mermaid) | 2–4 MB |
| Fonts/icons | 1–2 MB |
| **Total installed** | **20–40 MB** |

No Node, Python, Next server, JDdS, or desktop runtime is bundled. Attachments and
the SQLite file grow with use and are excluded from the install size.

## 12. Deliberately rejected designs

| Design | Why rejected |
| --- | --- |
| Bundle Node/Python and spawn them | Tauri mobile has no sidecars; iOS forbids it; payload impossible |
| Load the existing web UI from a host | That is pairing/remote, explicitly out of scope, and fails offline |
| Static-export the Next app into the WebView | Still needs a server for every `/api` call; bot UI imports Next-only code |
| Port the harness to WASM | Python + native wheels do not port; no filesystem/process sandbox |
| Run an on-device LLM | Not required, and quality/size/latency are unacceptable for v1 |
| Use `tauri-plugin-sql` from JS | Exposes SQL to the WebView and puts schema ownership in the wrong layer |
| Use Rig's agent loop unchanged | Its loop is not durable, not approval-bound and not our event model |

## 13. Invariants

1. No provider key ever crosses into the WebView.
2. No run starts before its row and input are committed.
3. No effectful tool executes without a persisted tool-call row.
4. An approval is bound to the exact `(tool, canonical args digest)`; a mismatch
   denies.
5. A crash never replays an external action; interrupted runs surface as
   `interrupted`, not `completed`.
6. The UI can always reconstruct the visible thread from SQLite alone.
7. Uninstalling the app deletes its sandbox; export is explicit and user-driven.
8. No background-execution claim is made that the platform cannot keep.

## 14. Mobile UI shape

The UI is a native-feeling app, not a responsive desktop page.

```
Root
├─ Bots            list of 1:1 bots + group rooms; unread/last-run badges
├─ Room / Bot      full-height transcript, streaming, composer, header menu
│                   (details = sheet: identity, model pin, schedule, memory, runs)
├─ Schedules       per-bot next attempt, last result, missed slots, "run now"
└─ Settings        providers (keys), privacy, data export/delete, appearance
```

Patterns:

- one primary action per screen; the composer is the centre of gravity;
- bottom sheets for approvals, clarify, bot details and model pickers — never a
  desktop-style anchored popover;
- a segmented control on a bot screen for Chat / Details; no sidebars;
- long-press on a message for copy/share/regenerate (additive to visible actions);
- skeletons for cold-start hydration; no empty flash;
- optimistic user message, then a real assistant message keyed by `runId`;
- per-member status chips in a room, with individual cancel.

Reuse: ghost SVG, markdown parser/renderer (minus `eclipse-response`), KaTeX,
copy button, icons, translator, token block, status labels.
Rebuild: navigation, chat layout, bot list, creation flow, approval/clarify
surfaces, memory/history, settings, attachment UI, schedules.
Do not port: Monaco, xterm, 3D, charts, the desktop tab bar, drag-and-drop
workspaces, the scheduler dock.

The visual identity stays Eclipse (dark-first, brand green, ghost faces, glass
used sparingly), but blur is disabled while scrolling and under
`prefers-reduced-motion`; a solid-surface fallback is always available.
