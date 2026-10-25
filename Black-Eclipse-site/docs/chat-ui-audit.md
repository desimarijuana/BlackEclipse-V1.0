---
title: Chat & Agent Experience — Audit and Overhaul Plan
status: Current
last-verified: 2026-10-25
---

# Chat & Agent Experience — Audit and Overhaul Plan

**Who this is for:** anyone changing the chat UI, the streaming presentation,
or how agent/tool activity is shown. This is **Phase 0** of the UI overhaul: the
audit, the root causes, and the phased plan. Implementation phases append to
this file (or land beside it) as they complete.

The governing rule for this document is the same as the rest of `docs/`: record
what the code cannot tell you. The code is the source of truth for *what*; this
records *why the current experience is shaped this way* and *what will change*.

---

## 1. Existing architecture (as built)

Chat is **one stack, two surfaces**:

- Full-page surface: `src/components/screens/stock-chat.tsx` (the `chat` tab),
  which owns conversation state and persistence.
- Floating surface: `src/components/chat/chat-dock.tsx` (Gemini-style bottom
  dock, portaled to `<body>`, owns its own `localStorage` conversation).

Both call the **same** client provider and render the **same** presentational
components (`ChatHistory`, `ChatInput`/inline composer, `Markdown`).

```
stock-chat.tsx / chat-dock.tsx
   │  getAgentProvider().chat(messages, tools, { chatId, onRunId, onStatus, onDelta })
   ▼
src/lib/agent/registry.ts  (client)
   │  POST /api/harness/chat/stream  (SSE relay; falls back to /api/harness/chat)
   ▼
src/app/api/harness/chat/stream/route.ts   (front door: validates, resolves, proxies)
   │  POST /runs (Python) → GET /runs/{id}/stream (Python SSE)
   ▼
python/harness/ graph.py ⇄ events.py  (LangGraph agent⇄tools loop, event bus)
```

The Python runtime owns the event model, ordering (`seq`), persistence
(`agent-memory.db`), and the terminal status. The TS side only relays frames.

### Relevant files

| Layer | File | Role |
|---|---|---|
| Full page | `src/components/screens/stock-chat.tsx` | conversation state, send/edit/cancel, render |
| Floating | `src/components/chat/chat-dock.tsx` | second surface, own conversation |
| Provider | `src/lib/agent/registry.ts` | SSE parse, status mapping, delta assembly, fallback |
| Types | `src/lib/agent/types.ts` | `AgentStatusEvent`, `ChatOptions` |
| Message | `src/types/chat.ts` | `Message { id, role, content }` only |
| List | `src/components/chat/chat-history.tsx` | transcript, inline edit, status header |
| Markdown | `src/components/chat/markdown.tsx` + `src/lib/chat/markdown.ts` | custom subset parser + renderer |
| Composer | `src/components/chat/chat-input.tsx` | full-page composer |
| Empty | `src/components/chat/empty-state.tsx` | initial state |
| Front door | `src/app/api/harness/chat/stream/route.ts` | start + relay + persist |
| Proxy | `src/app/api/harness/runs/[id]/stream/route.ts` | raw SSE relay |
| Runtime | `python/harness/graph.py`, `events.py`, `main.py` | event vocabulary + stream |

---

## 2. Current streaming / event model

### The actual event vocabulary (Python-authoritative)

Runtime frames are full envelopes: `{ id, runId, type, seq, at, data, transient? }`.

| Event | Data | Persisted |
|---|---|---|
| `run.created` | `agentId` | yes |
| `run.started` | `maxSteps`, `provider` | yes |
| `model.requested` | `step`, `messages` | yes |
| `model.delta` | `text`, `finalizing` | **no (transient)** |
| `model.completed` | `step`, `hasToolCalls`, token counts | yes |
| `tool.requested` | `name`, `toolCallId`, `step` | yes |
| `tool.completed` | `name`, `toolCallId`, `durationMs` | yes |
| `tool.failed` | `name`, `toolCallId`, `code`, `durationMs` | yes |
| `retrieval.planned` / `cache_hit` / `deduplicated` / `source_start` / `source_ok` / `source_unavailable` | source + dataType | yes |
| `run.completed` | `steps` | yes |
| `run.failed` | `error { code, message }` | yes |
| `run.cancelled` | `reason` | yes |

Front-door frames (added by the TS relay, top-level fields, no envelope):

| Event | Data |
|---|---|
| `client.run` | `runId`, `documentsUsed` |
| `client.final` | `runId`, `status`, `output`, `error`, `provider`, `model` |
| `client.error` | `message` |
| `stream.end` | `{}` |

### What the client consumes today

`registry.ts` maps only five events to a coarse status via `statusFromEvent`:
`run.started → "Getting ready…"`, `model.requested → "Thinking…"`,
`tool.requested → "Using <tool>…"`, `tool.completed → "<tool> done"`,
`model.delta → "Writing…"`, `run.completed → "Done"`. Everything else —
`tool.failed`, all `retrieval.*`, `run.failed`, `run.cancelled`,
`model.completed`, token counts — is **discarded by the UI**.

`tool.*` names are raw registry ids (`market_get_quote`,
`fundamentals_get_financials`, `research_search`), shown verbatim to the user.

### Cancellation

The client owns the run id (`buildPayload`), posts to
`/api/harness/runs/{id}/cancel`. The runtime cooperates. The stream is *not*
aborted client-side; the UI waits for the reply to resolve and shows
`"Run stopped."` when it is empty.

### Delegation / parallelism

**There is no subagent delegation event in the current runtime.** The graph is a
single agent ⇄ tools loop. Tool calls within one step are executed sequentially
in `tools_node`. No `agent.started`/`agent.completed`, no parallel tool
execution. Any subagent UI would be fabricated today — see Risk R4.

---

## 3. Current rendering flow

1. User sends → an **empty placeholder** assistant `Message` is appended.
2. `onStatus` sets a single `agentStatus` string.
3. `onDelta` accumulates text in a local variable and **rewrites the whole
   message array** (`replaceAssistantReply` / `patchAssistant`) on **every token**.
4. On resolve, the placeholder is replaced by a new id with the final text.
5. Errors become assistant prose: `Chat failed: <message>`.

`ChatHistory` renders the status as a "thinking header" above the *last*
assistant turn, and renders assistant content through the custom `Markdown`.

### Formulas in the chat

The Markdown subset **typesets mathematics**. A formula is LaTeX: `$...$`
inline, `$$...$$` as its own block. The parser (`src/lib/chat/markdown.ts`)
recognises them and the renderer (`src/lib/chat/math.tsx`) draws them with
KaTeX, so a Sharpe ratio, a VaR, a duration or a Black-Scholes line arrives as a
formula instead of as source text.

**Display math opens a block.** `$$...$$` starts a display block even when the
previous line is prose with no blank line between them — the common model shape
`**Return definition**\n$$r_t = ...$$`. The same applies to `\[...\]`, and a
`$$...$$` written mid-line is still display mathematics rather than two stray
dollar signs. The alternate LaTeX delimiters `\(...\)` (inline) and `\[...\]`
(display) are accepted too, so a model that emits them still typesets.

**Money is not a formula.** A `$...$` span only counts as mathematics when it
looks like mathematics: it carries a LaTeX operator (`\`, `^`, `_`, `{`, `}`,
`=`, `+`, `<`, `>`), is a single non-digit symbol (`$x$`, `$\mu$`), or is a
compact term mixing digits and letters (`$2x$`). On top of that, the opening `$`
may not follow a word character or a digit (`US$100`), the span may not break
over a line, and the closing `$` may not be followed by a digit (`$100`).
Whitespace just inside the delimiters is trimmed (`$ x $` is a formula), but a
money-shaped span (`$ 100 $`, `$5 and $10`) is not. An escaped `\$100` is always
money. So `it trades at $100` stays money and
`$S = \frac{r_p - r_f}{\sigma}$` is a formula. The agent is told the same rule:
**never write money inside a dollar sign** - write `USD 100`
(`python/harness/prompts.py`, "Formulas").

**KaTeX is loaded on demand.** The library is imported dynamically, so the
chat's initial bundle does not carry it; until it arrives the formula shows
its own source, and a formula KaTeX cannot parse shows the same way rather
than crashing the message. Its stylesheet is global (`src/app/katex.css`),
because KaTeX ships one stylesheet for its whole typesetting and its own
maths faces.

The same renderer serves the `eclipse-response` fence, so a `markdown` block
inside a structured answer typesets formulas too (see
`docs/interactive-response-engine.md`).

---

## 4. Current UI problems (concrete)

| # | Problem | Evidence |
|---|---|---|
| P1 | One generic status string for every phase; only 5 of ~15 events mapped. | `registry.ts:22` |
| P2 | Raw tool ids shown to users (`market_get_quote done`). | `registry.ts:30`, `:34` |
| P3 | Tool failures are **invisible** — the turn just says "Thinking…" until text appears. | `statusFromEvent` has no `tool.failed` |
| P4 | No activity history. Tool/retrieval events are ephemeral; nothing is shown after the run. | `chat-history.tsx` has no activity model |
| P5 | Streaming rewrites the entire message array per token — O(n) per delta, re-parses full Markdown each time. | `chat-dock.tsx:339`; `stock-chat.tsx:488` |
| P6 | Markdown re-parsed in full on every token; partial structures (open fence handled, but tables/lists mid-write) can flicker/reflow. | `markdown.tsx:62` |
| P7 | `scrollIntoView({ behavior:'smooth' })` on *every* message identity change can fight the user scrolling up. | `chat-history.tsx:35` |
| P8 | No message action toolbar (copy / regenerate / retry / feedback). | not present |
| P9 | Errors are injected as assistant markdown — indistinguishable from a real answer, no retry. | `stock-chat.tsx:517`, `chat-dock.tsx:368` |
| P10 | Cancelled run shows `"Run stopped."` as a normal assistant message, no distinct state. | `stock-chat.tsx:502` |
| P11 | `Message` has no status/activity/error fields — every state is faked through `content`. | `types/chat.ts` |
| P12 | Assistant identity avatar only in non-compact mode; status line is tiny mono text, weak hierarchy. | `chat-history.tsx:78-87` |
| P13 | No copy for code blocks/tables; tables can overflow without a clear affordance. | `markdown.tsx:99,118` |
| P14 | Empty state is generic ("Any new ideas to explore?") and offers one hard-coded button. | `empty-state.tsx:25` |
| P15 | Two divergent send implementations (dock vs page) — duplicated streaming logic to keep in sync. | `chat-dock.tsx:322` vs `stock-chat.tsx:457` |

---

## 5. Root causes

1. **The message model is too thin.** `Message { id, role, content }` cannot
   express queued/streaming/tool/error/cancelled. Every richer state is forced
   through `content` strings or a single ambient `status` prop. → P3, P4, P9,
   P10, P11, P12.
2. **The client throws away the event stream.** `registry.ts` reduces the rich
   event vocabulary to a status string and a delta callback *before* the UI ever
   sees it. There is no typed event model on the client. → P1, P3, P4.
3. **No client-side event normalization layer.** Raw ids, raw codes, envelopes
   vs top-level fields are all handled ad hoc inside one parser. → P2, P5.
4. **Streaming state lives in component closures.** Accumulation + per-token
   array rewrites are duplicated per surface with no shared reducer. → P5, P15.
5. **Presentation is coupled to transport.** `onDelta`/`onStatus` callbacks push
   straight into React state; rendering cannot reason about "this is a tool
   result" vs "this is prose". → P6.

These are architectural, not cosmetic. The fix is a **typed response lifecycle
model + one shared hook**, then presentation built on top.

---

## 6. Proposed component / state architecture

Add a typed layer **without touching the Python protocol** (the runtime is
already rich enough for Phases 1–3; delegation is genuinely absent — R4).

### 6.1 Response lifecycle model (client)

`src/lib/agent/response-model.ts` (new):

```ts
type ResponseStatus =
  | 'queued' | 'planning' | 'tool_running' | 'streaming'
  | 'completed' | 'cancelled' | 'error';

interface ActivityItem {
  id: string;              // toolCallId when present, else generated
  kind: 'tool' | 'retrieval';
  name: string;            // raw id (kept, not shown raw)
  label: string;           // human label
  source?: string;         // retrieval source / data type
  status: 'running' | 'completed' | 'failed';
  durationMs?: number;
  code?: string;           // failure code
}

interface AssistantTurn {
  status: ResponseStatus;
  text: string;            // accumulated prose
  activities: ActivityItem[];
  error?: { code?: string; message: string };
  finalText?: string;      // authoritative client.final
}
```

### 6.2 Normalizer + shared hook

- `src/lib/agent/events.ts` (new): `normalizeHarnessEvent(type, payload)` →
  a typed `HarnessUiEvent` union (`status | delta | activity_start |
  activity_end | final | error`). This is the **one** place raw ids/codes are
  interpreted. A `toolLabel(name)` map turns `market_get_quote` →
  "Retrieving market quote".
- `src/lib/agent/use-agent-run.ts` (new hook): owns the run lifecycle — status,
  activities, delta accumulation, cancel, retry. Both surfaces consume it,
  ending the dock/page duplication (P15).

### 6.3 Presentation components

- `components/chat/response-status.tsx` — polished multi-state indicator.
- `components/chat/activity-feed.tsx` + `activity-item.tsx` — compact,
  expandable tool/retrieval cards; failures shown distinctly; no raw JSON.
- `components/chat/message-actions.tsx` — copy / regenerate / retry / feedback.
- `components/chat/assistant-message.tsx` / `user-message.tsx` — split out of
  `chat-history.tsx` so status/activity/error render cleanly.
- Extend `Message` → `Message { id, role, content, status?, activities?, error? }`
  (backward-compatible: existing persisted conversations still load).

Everything reuses existing primitives (`glass-card*`, tokens, `Markdown`).

---

## 7. Event normalization strategy

1. Keep the **raw protocol**; add a pure client normalizer. No backend change
   for Phases 1–3.
2. Prefer `client.final` as the authoritative text; the streamed text is the
   live view. Never let the final text *lose* to assembled deltas.
3. Correlate `tool.requested → tool.completed|tool.failed` by `toolCallId`.
4. `retrieval.source_start`/`source_ok`/`source_unavailable` aggregate under the
   activity of the tool that triggered them (best-effort; no toolCallId on
   retrieval events — document as a known correlation gap, R3).
5. `statusFromEvent` becomes a thin wrapper over the normalizer (keep its export
   for compatibility, or migrate callers — check `registry.ts` consumers first).

---

## 8. Dependency recommendations

**None required.** The custom Markdown parser, React 19, and existing glass
primitives cover Phases 1–5. Optional, only if a real gap appears:
- Streaming-friendly Markdown: the current parser already degrades gracefully;
  no `react-markdown`/`shiki` needed yet.
- Table virtualization: not needed until proven slow.

---

## 9. Risks and compatibility concerns

- **R1 — Persisted conversations.** `Message` gains optional fields; loaders
  must tolerate old `{id,role,content}` rows. localStorage keys (`be_chat_dock_v1`,
  conversation store) are unchanged.
- **R2 — Two surfaces.** The shared hook must preserve dock-specific behavior
  (portal, minimize, session id). Migrate one surface at a time.
- **R3 — Retrieval events lack `toolCallId`.** Correlating them to a parent tool
  is heuristic. Either pass the id through (small Python change) or display them
  as top-level activity items. Decide in Phase 3; document if deferred.
- **R4 — No subagent/delegation events exist.** Phase 3's "agent delegation"
  display is **blocked on a backend capability that does not exist**. Do not
  fabricate. Implement single-agent tool activity now; add delegation when the
  runtime emits `agent.*`.
  *Resolved (2026-10-25):* the runtime now emits `delegation.*` and the child
  bridge (`python/harness/delegation_progress.py`) streams per-part progress;
  the chat renders `src/components/chat/parallel-agents-panel.tsx`. The
  paragraphs below record the state at audit time, not today's build.
- **R5 — Cancellation.** Current cancel does not abort the fetch reader; the UI
  waits for the stream to close. Phase 1 should abort the reader AND mark the
  turn `cancelled`, while still honoring a late `client.final`.
- **R6 — Do not break** terminal, market, portfolio, settings, charts, auth.
  Changes are confined to chat components + one agent-lib module.

---

## 10. Phased implementation plan

Each phase is small, independently verifiable, and preserves existing behavior.

### Phase 1 — Streaming foundation
- Add `response-model.ts`, `events.ts`, `use-agent-run.ts`.
- Extend `Message` with optional `status/activities/error`.
- Multi-state status indicator (`response-status.tsx`) replacing the single
  string; distinct tool-running / streaming / completed / cancelled / error.
- Fix scrolling: only auto-scroll when the user is already near the bottom.
- Stop generation: abort reader + mark `cancelled`; keep final-on-late-close.
- Acceptance: short/long/slow streams, cancel, failure, empty all render correct
  and distinct states; no duplicated/lost text.

### Phase 2 — Modern AI chat UX
- Message action toolbar (copy response, copy code, retry, regenerate, feedback).
- Errors as recoverable error states (not assistant prose) with Retry.
- Composer polish; prevent duplicate submit; input behavior during generation.
- Professional empty state (financial-native suggestions, not a fixed catalog).
- Acceptance: actions work on real messages; copy feedback; retry after failure.

### Phase 3 — Agent activity & tool execution UI
- `activity-feed.tsx` / `activity-item.tsx` from the normalized activity model.
- Human labels; start/done; duration; failure; expandable details; no raw JSON.
- Retrieval source lines grouped under their tool.
- Delegation UI only if/when Python emits `agent.*` (R4). Otherwise document gap.
- Acceptance: real tool flow (fixture or live) shows running→done/failed cards.

### Phase 4 — Financial-native rendering
- Optional structured blocks derived from real content (metrics/tables/sources)
  — only when the answer genuinely contains them; never fabricate.
- Table overflow/alignment/copy; source list with honest missing metadata.
- Charts only when compatible data exists (reuse existing chart system).
- Acceptance: unavailable data renders an explicit unavailable state.

### Phase 5 — Polish & design system
- Responsive pass (mobile tables, activity expansion, composer).
- Motion limited to purposeful transitions; reduced-motion respected.
- Consistency with the frosted-glass system and tokens.

### Phase 6 — Performance, a11y, quality
- Measure per-token re-renders; memoize message items; stable ids.
- Keyboard nav, labels, status announcements (not per token), contrast.
- Long-conversation and large-activity-list checks.

---

## 11. Verification plan

- Static: `npm run test` (vitest + pytest) and `npx tsc --noEmit` from
  `Black-Eclipse-site/` after every phase.
- New unit tests for `events.ts` (envelope/unwrap, tool correlation, failed
  tools, retrieval aggregation) and the run reducer.
- Functional via a faithful fixture replaying recorded frames: short/long/slow
  stream, incomplete Markdown, code, table, tool start/done/fail, cancel, error,
  empty.
- Visual: desktop/tablet/mobile; long conversation; expandable cards.
- Regression: terminal, screener, portfolio, settings, charts, auth unchanged.

---

## 12. Phase 0 status

Audit complete. No product code changed in Phase 0. Awaiting approval before
Phase 1 (streaming foundation). Phase 1 is ready to start because it is confined
to new agent-lib modules + chat components, with a backward-compatible `Message`
extension and a documented fallback for any missing backend capability.

---

## 13. Phase 1 — Streaming foundation (implemented 2026-09-22)

### What changed

- **Typed response model** — `src/lib/agent/response-model.ts`: `ResponseStatus`,
  `ActivityItem`, `TurnError`, `AssistantTurn`, plus the one place raw ids become
  human labels (`toolLabel`, `sourceLabel`).
- **One normalizer** — `src/lib/agent/events.ts`: `normalizeHarnessEvent` turns
  every harness frame into a typed `HarnessUiEvent` (`status | delta |
  activity_start | activity_end | final | error`). `unwrapEventPayload` now lives
  here and is re-exported from `registry.ts` for existing importers.
- **Shared run hook** — `src/lib/agent/use-agent-run.ts`: owns status, streamed
  text, activities, cancel (aborts the fetch reader AND asks the runtime to
  cancel), duplicate-submit guard, and terminal states. It publishes a snapshot
  to the host, which maps it onto its own message store. Text deltas are
  rAF-coalesced (one render per frame, not per token).
- **`Message` extended** — `src/types/chat.ts` gains optional
  `status` / `activities` / `error`. Optional means pre-existing localStorage
  conversations (`{id,role,content}`) still load unchanged.
- **`ResponseStatusLine`** — `src/components/chat/response-status.tsx`: distinct
  UI per state (preparing / reviewing / tool-running / preparing response /
  done / stopped / error), named by the running activity, no generic "Thinking…".
- **`ChatHistory` rebuilt** — per-message status/activity/error rendering,
  recoverable error block with **Retry**, copy + regenerate toolbar, memoized
  assistant Markdown, and bottom-aware auto-scroll (never yanks the viewport
  while the user scrolls up).
- **Both surfaces migrated** — `stock-chat.tsx` and `chat-dock.tsx` now call the
  shared hook instead of duplicating streaming logic. Cancellation marks the turn
  `cancelled`; failures mark it `error` and are retryable.

### Backend note

No Python change. The runtime already emits `tool.*`, retrieval, `run.failed`
and `run.cancelled`; the client simply stopped discarding them. Retrieval events
still lack a `toolCallId`, so correlation to their parent tool falls back to
"most recent running item with the same name" (Risk R3).

### Verification

- `npx tsc --noEmit` — pass.
- `npx eslint` (touched files) — pass, 0 errors/0 warnings.
- `npx vitest run` — 1510 passed (adds 14 normalizer/model tests).
- `node scripts/test-python.js` — 91 passed.
- `npm run build` — compiled + type-check pass; fails at the **pre-existing**
  `/favicon.ico` prerender error (unrelated, no routing touched).
- Live browser verification deferred to Phase 2 (no dev server was run here).

---

## 14. Phase 2 — Modern AI chat UX (implemented 2026-09-22)

### What changed

- **Code + table copy** — `src/components/chat/copy-button.tsx` (one clipboard
  affordance, transient "Copied"). Code blocks expose a hover copy button; tables
  expose a TSV copy so a paste into a spreadsheet stays aligned. Markdown is now
  a client component (`markdown.tsx`) since it owns clipboard interaction.
  Pure helpers (`inlineText`, `tableToTsv`) live in `lib/chat/markdown.ts` and
  are unit-tested.
- **Feedback** — `Message.feedback` (`'up' | 'down'`), rendered as a subtle
  thumbs control that persists with the message in both surfaces and toggles off
  on a second click.
- **No fabricated model picker** — the composer's fake "Flash-Lite / Flash / Pro"
  dropdown (which changed nothing) was removed and replaced with the **real**
  configured provider label (same as the dock).
- **Composer polish** — `aria-label`, `aria-busy`, and `showProvider` (renamed
  from the misleading `showModelSelect`).
- **Empty state** — financial-native starting points (analyse a stock, compare
  fundamentals, sentiment, portfolio review) that are examples, not a fixed
  capability list; clicking one fills the composer and focuses it. Reworded
  headline/subhead to state the JDdS-grounded, cited-answer promise.

### Verification

- `npx tsc --noEmit` — pass.
- `npx eslint` (touched files) — 0 errors/warnings.
- `npx vitest run` — 1512 passed (adds 2 copy-helper tests).
- Dev server (`npm run dev`) hot-recompiled the touched modules; harness runs
  completed against ollama + the JDdS bridge with no new errors.
- Live click-through of copy/feedback not automated; deferred to manual QA.

---

## 15. Phase 3 — Agent activity & tool-execution UI (implemented 2026-09-22)

### What changed

- **`activity-item.tsx`** — one tool/retrieval operation, compact by default:
  category icon, human label, status, optional duration, optional result
  summary. Expandable only when there is something safe to show (operation name,
  retrieval source, failure code). Never raw JSON, credentials, or reasoning.
- **`activity-feed.tsx`** — groups a turn's activities into one collapsible
  card. Collapsed it is a single summary line (`Activity · 4 steps · 2 sources ·
  1 failed`); it auto-expands while the run is live and collapses when it ends,
  unless the user has toggled it. The expanded list scrolls at a fixed max
  height so a long tool list cannot push the answer off screen.
- **Result summaries** — the normalizer now reads `objects` off
  `retrieval.source_ok` and attaches a user-safe `"N records"` summary. When the
  runtime sends no count, no summary is shown (never inferred).
- **Both presentation modes** — the same components render in the floating dock
  (`compact`) and the full-page Chat tab (detailed). Density is the only
  difference; there is no second rendering system.

### Delegation (still blocked)

There are no `agent.*` / subagent events in the runtime (Risk R4), so no
delegation card was built and none was faked. This remains backend-gated.

### Verification

- `npx tsc --noEmit` — pass.
- `npx eslint` (touched files) — 0 errors/warnings.
- `npx vitest run` — 1513 passed (adds a retrieval-summary test).
- Dev server recompiled the new components with no UI errors. A pre-existing
  Python data-bridge `SyntaxError` appears in the harness log; it is unrelated to
  this phase (no API route changed).

---

## 16. Phase 4 — Financial-native rendering (implemented 2026-09-22)

### Scope decision (grounded in what exists)

The runtime's terminal output is **plain Markdown**; the only structured payload
the SSE stream carries is a retrieval *object count*. Evidence/reference objects
(`url`, `title`, `source`, timestamps) live inside tool results and are never
emitted to the client. Therefore Phase 4 does **not** invent a structured-block
schema or fabricate metric cards. It improves how the model's real output is
presented, and renders an explicit unavailable state only for markers the model
actually writes.

### What changed (`lib/chat/markdown.ts` + `components/chat/markdown.tsx`)

- **Numeric tables** — a column whose cells are genuinely numeric (thousands
  separators, currency, percent, magnitude, parenthesised negatives) is
  right-aligned with tabular figures; tickers/words are left alone. Negative
  values render in the loss colour.
- **Unavailable marking** — a cell or inline run that is exactly an unavailable
  marker (`UNAVAILABLE`, `n/a`, `—`, `null`, …) renders as a muted chip, so
  "we don't have this" never reads as a value.
- **Sources/references** — a heading like "Sources" reads as a quiet section
  label; a list whose items are essentially just links renders as a source list
  showing the display host, so a bare URL never floats unlabelled.
- **Links** — external links gain a hover affordance and a host tooltip.

All helpers (`isNumericText`, `isNegativeValue`, `isUnavailableText`,
`isSourceHeading`, `extractHost`, `collectLinks`) are pure and unit-tested.

### Not built (documented gaps)

- No metric cards / structured financial blocks — there is no structured data
  contract on the wire to back them. Adding one is a backend change (emit
  evidence/source references on the stream); see Risk R4/R7.
- No ECharts-in-chat — no chart payload reaches the chat stream.

### Verification

- `npx tsc --noEmit` — pass; `npx eslint` (touched files) — clean.
- `npx vitest run` — 1519 passed (adds 6 financial-helper tests).
- Dev server recompiled the renderer with no UI errors. The `/api/forex` 500 in
  the log is the pre-existing Python data-bridge JSON error, unrelated.

---

## 17. Phase 5 — UI polish & design system (implemented 2026-09-22)

### Audit result

- **Reduced motion** — already covered globally in `globals.css`
  (`@media (prefers-reduced-motion: reduce)` kills animation/transition
  durations). No chat-specific work needed there.
- **Frosted glass** — chat surfaces already use `glass-card` /
  `glass-card-strong` / `glass-card-subtle`. No raw blur introduced.
- **The real gap was touch.** Message actions, the code-block copy button, the
  table copy control, and the Edit affordance all relied on hover
  (`opacity-0 group-hover:opacity-100` or `hidden group-hover:flex`). On a touch
  device there is no hover, so those controls were invisible or unreachable.

### What changed

- **`.hover-reveal` utility** (`globals.css`) — keeps the existing Tailwind
  hover classes for pointer devices, and via `@media (hover: none)` forces the
  control visible and tappable on touch, plus a reduced-motion override. Applied
  to the message action toolbar, the Edit button, and both copy buttons.
- **Edit button** — was `hidden group-hover:flex` (unreachable on touch); now
  always rendered and revealed by opacity.
- **Action toolbar** — now `flex-wrap` so Copy / Regenerate / feedback do not
  overflow on a narrow bubble.
- **Message row** — a `group` class so hover-revealed controls have a stable
  ancestor in both compact and full layouts.

### Not done (deliberately)

- No new animation added; motion stays restrained and the global reduced-motion
  rule applies.
- No global component restyle — changes are confined to the chat surface.

### Verification

- `npx tsc --noEmit` — pass; `npx eslint src/components/chat` — clean.
- `npx vitest run` — 1519 passed.
- Dev server recompiled CSS + components with no errors.

---

## 18. Phase 6 — Performance, accessibility & quality (implemented 2026-09-22)

### Performance

- **The hottest write, found by inspection.** Both chat surfaces serialized the
  **entire transcript to `localStorage` on every streamed frame** — roughly
  60 writes/second of a growing JSON document during a long answer. Streaming
  frames now update React state only; the transcript is persisted **once** when
  the turn reaches a terminal state (and in the `finally`, so cancel/abort paths
  are covered too). `ChatHistory` already memoized assistant Markdown, so the
  remaining per-frame cost is bounded.

### Accessibility

- **Error turns announce.** The error block is now `role="alert"` so it is read
  on appearance, without relying on colour alone.
- **Status granularity is per phase, not per token.** `ResponseStatusLine`
  keeps `role="status" aria-live="polite"` and its label changes only on a
  lifecycle transition, so a stream does not spam a screen reader.
- **Activity disclosure semantics.** The feed toggle already had
  `aria-expanded`; it now also has `aria-controls` pointing at the expanded
  region (`useId`), so the relationship is machine-readable.
- Keyboard reachability of actions/copy/Edit was fixed in Phase 5.

### Quality

- **Clean production build verified.** A flaky first `next build` was traced to
  the dev server sharing `.next` (`.next` torn down mid-build), not to code: with
  the dev server stopped and `.next` removed, `npm run build` compiles, type-
  checks, and generates all pages cleanly.

### Verification

- `npx tsc --noEmit` — pass; `npx eslint` (touched files) — clean.
- `npx vitest run` — 1519 passed; `node scripts/test-python.js` — 91 passed.
- `npm run build` (clean `.next`) — success.
- Dev server restarted healthy on :3000.

---

## 19. Definition of done — status

| Area | State |
|---|---|
| Streaming | Reliable deltas, correct Markdown/code/tables, distinct states, stop/cancel, error + retry |
| Chat UX | Copy, regenerate, retry, edit/resend, feedback, professional composer, financial empty state |
| Agent experience | Live multi-state status, tool/retrieval activity cards, expandable safe details, failures surfaced; delegation backend-gated (R4) |
| Financial rendering | Numeric tables, unavailable chips, source lists, link affordance; structured blocks/charts backend-gated (R7) |
| Design quality | Token/glass consistent, touch-reachable controls, restrained motion + reduced-motion, responsive |

**Known gaps (documented, not faked):** subagent delegation (no runtime
events); structured metric/chart blocks in chat (no wire contract); retrieval →
parent-tool correlation is heuristic (R3).

---

## 20. Post-phase fixes (2026-09-22)

### Bug fixed — retrieval activity never reached the UI

The Phase-3 activity feed could show tool steps but **never the sources a tool
consulted**, because the retrieval layer's `retrieval.*` events were dropped
before they reached the stream.

- `graph.py` built the run's `ToolContext` with `log=lambda m, d=None: None` — a
  **no-op**. `retrieval_tools._event_logger` forwarded retrieval events only to
  that callback, so `retrieval.planned` / `source_start` / `source_ok` /
  `source_unavailable` were silently discarded (never emitted, never persisted,
  never streamed).
- Fix: `ToolContext` gained an `emitter` field; `graph.py` attaches the run's
  `RunEmitter`; `_event_logger` now `await emitter.emit(...)` when present and
  falls back to `ctx.log` otherwise (unit tests). The run's per-run
  `FinancialRetrievalLayer` is now the only one built (an unused layer in
  `service.run` was removed, which had also been constructed without any event
  hook).
- Verified live: a quote query now streams `retrieval.planned` (1),
  `retrieval.source_start` (1), `retrieval.source_ok` (1) alongside the tool
  events. A regression test (`test_graph.py`) asserts these reach the bus.

### Also observed

- The transient `SyntaxError: Unexpected end of JSON input` / `/api/forex` 500
  seen earlier did not reproduce after a clean restart: the data bridge returns
  200 and forex returns 200. It was Python-bridge start-up churn, not a code
  defect; left as-is rather than patching a non-reproducing symptom.
- `R3` (retrieval → parent-tool correlation) is now moot for the live UI: the
  feed shows retrieval sources as their own rows, correlated by name when no
  `toolCallId` exists.

### Bug fixed — a failed/cancelled turn bricked the whole conversation

Reported symptom: "not getting output, something went wrong." The dev log showed
repeated `POST /api/harness/chat 400` / `chat/stream 400` with
`INVALID_INPUT`.

- **Regression introduced in Phase 1.** Failed and cancelled assistant turns
  moved from a non-empty string (`Error: …`, `Run stopped.`) to a structured
  turn with `content: ""` + `status: error|cancelled`. The front door's history
  validator (`validation.ts`) required every turn to have non-empty content, so
  the empty turn made **every subsequent request in that conversation** fail
  with 400 — the user saw "something went wrong" forever after one failure.
- **Fix (both ends).**
  - `validation.ts`: an empty history turn is now **skipped**, not an error
    (`if (!content.trim()) continue;`). A malformed role is still rejected.
  - `registry.ts` `buildPayload` and `stock-chat.tsx`'s history builder now omit
    empty turns, so the client does not send them either.
- **Verified live:** a request whose history contains
  `{ role: "assistant", content: "" }` returns 200 on both `/api/harness/chat`
  and `/api/harness/chat/stream`. Regression tests added in
  `validation.test.ts`.

### Bug fixed — duplicate React keys in the activity feed

Reported console error: `Encountered two children with the same key,
retrieval:LIVE_STRUCTURED:macro_series`.

- **Cause.** The normalizer emits *deterministic* ids
  (`retrieval:<source>:<dataType>`, `tool:<name>`). A run that consults the same
  source (or calls the same tool) twice therefore produced two activity items
  with the same id, so `ActivityFeed` keyed two rows identically — React
  duplicates or drops them.
- **Fix.** New pure `lib/agent/activity-reducer.ts`: each activity *instance*
  gets a unique id (`<logical>#<seq>`) while a logical-id → instance stack keeps
  start→end correlation LIFO, so overlapping runs of the same operation still
  resolve correctly. `use-agent-run` delegates to it. A `hasUniqueIds` invariant
  and five reducer tests (including the exact duplicate-id case) were added.

---

## 21. Turn length — the front door no longer refuses a long message (2026-10-21)

### The rule

**A turn is whatever the person pasted.** The front door's bound on a chat turn
(`MAX_QUERY_LENGTH`, `src/lib/harness/validation.ts`) guards **one request
body** — it is not a prompt limit, and it is not a policy about how much a
person may ask. It is currently 100 000 characters (~25k tokens), mirrored by
the runtime's `RunInput.query` bound (`python/harness/schemas.py`,
`MAX_QUERY_CHARS`).

**The real limit belongs to the runtime.** It measures the assembled request —
system prompt, tool schemas, per-run blocks, the user turn — against the
resolved model's declared context window (`context_budget.py`) and reports an
honest `CONTEXT_OVERFLOW` with a reason and a remedy when a prompt genuinely
does not fit. A front-door rejection cannot make that judgement; it can only
guess a number, and a guessed number refuses legitimate work.

**The two bounds are mirrored on purpose.** The front door's bound must stay
`>=` the runtime's, or the runtime would reject a request the app accepted
with a bare pydantic 422 instead of a readable error. Change one, change both.

### Why it changed

A message over 4 000 characters was refused by the front door and rendered as
the generic "Something went wrong" card. The composer had accepted the text;
the refusal happened on the way to the agent; and the card gave the user no way
to tell a rejected request from a broken agent.

Two consequences are now fixed with it:

- **A refusal carries a stable code.** The front door answers a refused turn
  with `INVALID_INPUT`, and the client keeps it (`ChatRequestError` in
  `src/lib/agent/registry.ts`) so the chat card badges the real reason instead
  of showing a bare sentence.
- **A refusal is not repeated.** A refused request used to be sent three times
  — stream 400, one-shot fallback 400, one-shot retry 400 — all failing
  identically. A refused request now fails **once**. A missing streaming
  ENDPOINT (404/405, an older front door) still falls back to the one-shot
  path; that is a different failure and it still recovers.

### The knock-on: history

A prior turn carries the same per-turn bound, so a long message is **not
silently sliced** when it returns as history on the next turn. The whole
history is bounded too, and it is bounded the way the runtime bounds it: the
**oldest whole turns are dropped**, never a turn cut in half — so the runtime
receives every turn it is given intact and applies its own budget on top. The
runtime still bounds the ASSEMBLED history against the model's window and
reports what IT drops (`memory.history_bounded` + the dropped-context block);
that is a prompt-budget decision, not a rejection.

### A big paste is an attachment, not a composer full of text

A paste above `PASTE_AS_ATTACHMENT_CHARS` (4 000, `src/lib/chat/paste.ts`) is
intercepted by the composer and attached instead: the text is written into the
conversation's session folder as a `pasted-text.txt` context document and
shows as a chip, exactly like an uploaded file. Small pastes insert normally.

**Why a chip and not a message.** A multi-thousand-character blob makes the
composer unusable (it grows four lines, then scrolls), and a message that large
is really a document the user is handing over. The chip makes that visible,
**readable** (click it for a preview of the text) and removable, and it reuses
the ONE attachment pipeline — the same extraction, the same run documents, the
same truncation provenance — instead of adding a second way to get text to the
agent.

**A paste is always visible on the turn that used it.** Pressing Enter with only
a paste attached sends a neutral "Read the attached document." turn; the pasted
text **stays a context document** (it is no longer taken back out of the
attachment list). The user bubble carries a compact `Pasted text` card — file
name, character count, a short preview, and an Open action — so the document
that went to the run is visible in the transcript and can be read again later.
A paste sent alongside a typed prompt gets the same card on that prompt. The
card is claimed for one turn only, so later messages do not re-list old pastes.

**Why the document stays attached.** Removing it deleted the only durable copy
once the text was folded into the message, and a multi-hundred-kilobyte message
then had to survive the transcript cache (localStorage quota) and the per-turn
bound. Keeping the document avoids a giant user bubble, keeps the text available
as context on later turns, and means a paste over 100 000 characters is
truncated by the document pipeline (with provenance) instead of rejected by the
turn bound. The transcript stores only the preview, never a second full copy.

**Long typed prompts collapse too.** Any user turn over 2 000 characters is
shown as an 800-character excerpt with "Show full message · N characters"; the
full text stays persisted and copyable. This keeps a long prompt (or a paste on
a surface without the attachment hook) from painting an unscrollable wall.

**Why the document caps moved.** They are now the turn bound (100 000 chars per
document, 200 000 combined). A paste that becomes a document must arrive as
readable as the same text would have as a message; a lower document cap would
have made the chip a downgrade. The runtime measures the assembled turn —
documents included — against the model window, so a document that genuinely
does not fit is reported, never silently dropped.