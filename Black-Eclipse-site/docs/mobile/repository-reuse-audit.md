---
title: Eclipse Mobile — Repository Reuse Audit
status: Proposed
last-verified: 2026-11-12
---

# Repository reuse audit

Every path below was read at `2026-11-12`. Verdicts:

| Verdict | Meaning |
| --- | --- |
| **REUSE** | Take/import unchanged (pure logic or DOM-only component) |
| **EXTRACT** | Move the pure part into `packages/` or `mobile/`; leave the caller alone |
| **ADAPT** | Same intent, new transport/UI/platform |
| **REBUILD** | No usable implementation for this surface |
| **DESKTOP-ONLY** | Must not be ported; it depends on Node/Python/Next/desktop |

## 1. Summary

| Area | REUSE | EXTRACT | ADAPT | REBUILD | DESKTOP-ONLY |
| --- | --- | --- | --- | --- | --- |
| Bot domain | 5 | 2 | 4 | 5 | 3 |
| Execution | 1 | 3 | 0 | 3 | 12 |
| Presentation | 9 | 3 | 6 | 4 | 5 |
| Shell/platform | 0 | 0 | 1 | 3 | 6 |

The reusable core is small and real: ghost/identity maths, schedule and status
formatting, mention parsing, the markdown parser and renderer, the pure prompt
builders, and the status/approval *semantics*. The stores, transports, scheduler,
memory service and shell are not reusable.

## 2. Bot domain and persistence

| Path | What it is | Verdict | Mobile action / why |
| --- | --- | --- | --- |
| `src/lib/bots/state.ts` | Bot draft, schedule builders, cron/interval summaries, status labels/tones, filters/search, formatting, model pin | **REUSE** | Pure apart from a type-only import of `AutomationView`. Move to `packages/bot-personas` or copy with the type replaced by the contract `Bot`. Keeps `buildTrigger`, `draftFromBot`, `validateDraft`, `botModelPin`, `isBotAutomation` semantics. |
| `src/lib/bots/ghost.ts` | `GhostSpec`, FNV-1a hash, mulberry32, deterministic face, palette, normalizer | **REUSE** | No DOM, no framework. Tested by `ghost.test.ts`. |
| `src/lib/bots/ghost-mood.ts` | Response status/event → mood | **REUSE** | Type-only imports; map the mobile run events to the same eight moods. |
| `src/lib/bots/mentions.ts` | Bot/group mention projection, ranking and parsing | **REUSE** | Pure; use for `@`-targeting in group rooms. |
| `src/lib/bots/run-error-help.ts` | Static `errorClass` → what/fix/retryable | **REUSE** | Pure lookup; the mobile runtime must emit the same class names. |
| `src/lib/bots/invoke.ts` | `botPersona`, `buildBotMessages`, `buildGroupMemberMessages`, `botChatId`, `groupMemberChatId`; `runBotTurn` | **EXTRACT + REBUILD** | Extract the four pure builders and scope-id functions into `packages/bot-personas`. Rebuild `runBotTurn` in Rust; it currently calls `getAgentProvider().chat` → `/api/harness/chat`. |
| `src/lib/bots/chat-store.ts` | localStorage `be_bot_chat_v1`, zustand, 2 s mirror | **REBUILD** | Single-device SQLite replaces localStorage + envelope sync. Keep the `BotMessage` field semantics (`runId`, `scheduled`, `pendingApproval`, delegations). |
| `src/lib/bots/groups-store.ts` | Room + transcript localStorage | **REBUILD** | SQLite tables. Keep the 2–6 member rule and per-member transcript behaviour. |
| `src/lib/bots/bots-store.ts` | Bot cache, seen/pinned ledgers, 20 s poll of `/api/automations` | **REBUILD** | Local SQLite is the source; no polling. Keep the "seen execution" idea for unread state. |
| `src/lib/bots/avatar-store.ts` | Ghost/image maps in localStorage | **REBUILD** | Persist avatar JSON and image path in `bots`. Image bytes go to the app data dir, not base64 in the DB. |
| `src/lib/bots/state-sync.ts` | Newest-timestamp-wins mirror to `/api/bots/state/[key]` | **DESKTOP-ONLY** | Exists only because a browser can be cleared. A single device DB is durable; no merge engine should be invented. |
| `src/lib/bots/purge.ts` | Forget bot/group memory + local store cleanup | **ADAPT** | Becomes one transactional `delete_bot` / `delete_group` command with cascade, plus explicit FTS rebuild. |
| `src/lib/bots/duplicate.ts` | Copy an automation server-side | **ADAPT** | Local `duplicate_bot` command; copy brain/objective/schedule/face, pause a copied schedule (same rule). |
| `src/lib/bots/finance-bots.ts` | Six-bot finance pack, idempotent by name | **ADAPT** | Keep the spec text and schedules; seed into SQLite. Remove server calls. The finance wording must stay honest (citations/UNAVAILABLE). |
| `src/lib/bots/institution-bots.ts` | Committee preset fetched from `/api/team/presets/institution`, `run_team` | **DESKTOP-ONLY for v1** | Depends on the Python team runtime. Could be re-seeded later as six ordinary bots, without `run_team`. |
| `src/lib/bots/image.ts` | Canvas crop/downscale to 128 px JPEG data URL | **ADAPT** | Prefer `tauri-plugin-dialog` + Rust `image` crate; if done in the WebView, keep the 128 px cap and re-encode before storage. |
| `src/lib/bots/appearance.ts` | Font scale persisted in localStorage | **ADAPT** | Same clamp logic; apply a CSS variable in the mobile settings store. |
| `src/lib/bots/use-bot-delegation.ts` | `@`-delegation into bot/group turns, mirroring | **REBUILD** | Group orchestration moves into Rust. Keep the visible behaviour: one user turn, one reply per addressed bot. |
| `src/lib/bots/use-ghost-gaze.ts` | Shared pointermove → CSS vars | **ADAPT** | Works in a WebView but pointer gaze is meaningless on touch; keep the hook behind a "desktop pointer" guard or drop it. |

## 3. Execution and runtime

| Path | What it is | Verdict | Mobile action / why |
| --- | --- | --- | --- |
| `src/lib/agent/types.ts` | `ChatMessage`, `ChatOptions`, `AgentProvider`, status types | **EXTRACT** | The message/role/option shapes inform the contract; the provider interface is replaced by the Rust trait. |
| `src/lib/agent/events.ts` | The canonical desktop normalization (runtime frame → typed UI event) | **EXTRACT** | Reuse the *mapping table and event names* to define `run-event.schema.json`; implement the parser in Rust. Also captures the approval/clarify/delegation payload shapes. |
| `src/lib/agent/response-model.ts` | `ResponseStatus`, `PendingApproval`, `PendingClarification`, `DelegationView` | **EXTRACT** | These are good wire types; move to the contract package. Keep `ApprovalChallenge` (typed confirmation, cooling-off). |
| `src/lib/agent/registry.ts` | The one client provider: SSE parse, run-id minting, sessionStorage recovery, `/api/harness/*` | **REBUILD** | Rust owns the stream, run id and recovery. Do not reproduce the 1.5 s poll fallback; use durable events + resume by seq. |
| `src/lib/agent/use-agent-run.ts` | UI run reducer, approval/clarify decisions | **REBUILD** | Mobile reducer projects Rust events; decisions call Rust commands. |
| `src/lib/agent/mock-provider.ts`, `openai-provider.ts` | Mock and an OpenAI-compatible TS adapter | **REFERENCE ONLY** | Useful for request shape/tests, not shipped. Rust adapters are separate. |
| `src/app/api/harness/**` | Next proxy to Python (chat, stream, runs, approvals, memory) | **DESKTOP-ONLY** | No Next server on device. |
| `src/app/api/bots/state/[key]` | BotState mirror endpoint | **DESKTOP-ONLY** | Replaced by SQLite. |
| `src/app/api/automations/**` | Automation CRUD/history proxy | **DESKTOP-ONLY** | Local schedule/bot commands replace it. |
| `src/app/api/chat/session/**` | Server-side session file store + extraction | **DESKTOP-ONLY** | Replace with app-sandbox attachments; extraction happens in Rust at send time. |
| `python/harness/**` (service, graph, tools, memory, automation, sandbox) | The entire agent runtime | **DESKTOP-ONLY** | Reference for behaviour only. Reimplement the small subset in Rust. |
| `python/harness/automation/engine.py` | 30 s asyncio scheduler, misfire, retries, breaker, leases | **DESKTOP-ONLY** | Reproduce only due-time calculation, misfire and catch-up locally; no leases/breakers in v1. |
| `python/harness/eclipse_memory/` | Memory records, evidence, retrieval, scopes | **DESKTOP-ONLY** | Reproduce explicit memories + FTS retrieval; drop evidence graph and review workflow in v1. |
| `python/harness/mcp/approvals.py` | Single-use, digest-bound approvals, standing grants | **DESKTOP-ONLY** | Reproduce the *invariants* (digest binding, single use, expiry, no replay) in Rust. |
| `python/harness/code/sandbox.py` | OS-isolated code execution | **DESKTOP-ONLY** | Not offered on mobile; no shell/Python/JS tool. |
| `docs/bot-mode.md` | Behaviour contract for bots, memory scopes, model pins, group rules | **REUSE (as spec)** | The mobile runtime must preserve: same brain for chat and scheduled runs, per-member memory bucket, provider pin/credential rules, run-now vs paused. |
| `docs/harness/automation-engine.md` | Trigger/misfire/retry definitions | **REUSE (as spec)** | Adopt the vocabulary; document the reduced mobile subset. |

## 4. Presentation and design

| Path | What it is | Verdict | Mobile action / why |
| --- | --- | --- | --- |
| `src/components/bots/ghost-avatar.tsx` | Pure inline SVG face, `data-mood` | **REUSE** | React + `useId`/`useMemo` + `cn` only. No Next, no canvas. |
| `src/components/bots/live-ghost-avatar.tsx` | Blink/breathe wrapper gated by `IntersectionObserver` | **REUSE** | Works in WKWebView/Android WebView; keep `prefers-reduced-motion`. |
| `src/components/bots/bot-avatar.tsx` | Ghost or uploaded photo | **ADAPT** | Image source becomes a `file://`/asset URL from Rust, not a data URL; keep the ghost fallback. |
| `src/lib/chat/markdown.ts` | Dependency-free streaming markdown parser (tables, math, code) | **REUSE** | Pure and already tested. This is the single biggest UI reuse win. |
| `src/components/chat/markdown.tsx` | Renderer for the parser | **EXTRACT + ADAPT** | Keep headings/lists/code/tables/math/links. Strip the `eclipse-response` fence: `ResponseFenceLazy` pulls `next/dynamic` (`src/components/response/response-view.tsx`). Optional later: replace with `React.lazy`. |
| `src/lib/chat/math.tsx` + `katex` | Lazy KaTeX formula renderer | **REUSE** | Portable; ship `katex.css`. |
| `src/components/chat/copy-button.tsx` | Clipboard copy | **REUSE** | Pure React; clipboard API exists in the WebView. |
| `src/components/chat/approval-card.tsx` | Portal card anchored to the composer | **ADAPT** | Logic (risk, cooling-off, remember) is good; the geometry is desktop. Rebuild as a bottom sheet / inline card. |
| `src/components/chat/clarification-card.tsx` | Options + free text + "let Eclipse decide" | **ADAPT** | Same; bottom sheet. |
| `src/components/chat/parallel-agents-panel.tsx` | Delegation progress UI | **ADAPT (optional)** | Only useful if group/delegation ships in v1; otherwise defer. Its pure status helpers are worth lifting. |
| `src/components/bots/status-pill.tsx` + `state.ts` labels | Lifecycle/execution/breaker pills | **ADAPT** | Keep labels/tones; restyle with mobile tokens. Breaker may be hidden in v1. |
| `src/lib/icons/index.ts` | Phosphor re-exported under Lucide names | **REUSE** | Ship `@phosphor-icons/react`; `optimizePackageImports` behaviour must be reproduced by direct imports. |
| `src/lib/i18n/translate.ts`, `locales.ts` | 22-locale translator, RTL metadata | **REUSE** | Framework-free. Ship only the mobile namespace subset; English fallback is built in. |
| `src/lib/i18n/store.ts`, `use-t.ts` | Zustand locale store + `useT` | **ADAPT** | Replace `document.documentElement` writes with a mobile settings store; keep `dir` for RTL. |
| `src/app/globals.css` | 1,988-line app stylesheet with tokens, glass, ghost, sidebar, charts | **EXTRACT** | Copy only `:root`, `.dark`, `@theme inline`, ghost keyframes/moods, `glass-*`, and a reduced `safe-area` layer. Do not copy screen-specific selectors. |
| `src/lib/theme/tokens.ts` | Serializable theme + `themeCssVars` | **ADAPT** | `themeCssVars` is pure but imports background/aurora types; copy the function and trim. |
| `src/app/fonts.css` + `public/fonts/*` | Self-hosted fonts | **REUSE** | Copy the `@font-face` block and files. |
| `src/components/layout/mobile-bottom-nav.tsx` | Responsive in-app nav for the desktop app | **DESKTOP-ONLY** | It navigates AppTabs, not the mobile IA. Build native-feeling mobile routing instead. |
| `src/components/layout/desktop-tab-bar.tsx` | Frameless window title bar with tab instances | **DESKTOP-ONLY** | No place on mobile. |
| `src/components/bots/scheduler-dock.tsx`, `scheduled-jobs-panel.tsx` | Right-docked desktop workspace slot | **DESKTOP-ONLY** | Replace with a mobile Schedules screen and a bot detail section. |
| `src/components/bots/create-bot-dialog.tsx`, `bot-detail.tsx`, `bots-sidebar-panel.tsx`, `group-chat-room.tsx`, `bot-chat.tsx` | The desktop workspace | **REBUILD (structure), EXTRACT (sub-behaviours)** | Keep the information architecture and behaviour; rebuild layout, navigation and sheets. Extract reusable bits listed above. |
| Monaco, xterm, Plotly/ECharts GL, `ogl` 3D, Graph Studio, Canvas Tiptap | Heavy desktop surfaces | **DESKTOP-ONLY** | Not shipped. |

## 5. Shell, platform and tests

| Path | What it is | Verdict | Mobile action / why |
| --- | --- | --- | --- |
| `desktop/src-tauri/src/main.rs` | Window, tray, prefs, Node supervisor, injected notification shim | **DESKTOP-ONLY** | None of it applies. The mobile crate is a new lib + `mobile_entry_point`. |
| `desktop/src-tauri/Cargo.toml` | Tauri 2 binary crate + tray/single-instance/vibrancy | **REBUILD** | New mobile Cargo manifest; remove tray/single-instance/vibrancy. |
| `desktop/src-tauri/capabilities/default.json` | Remote-origin capability for `http://127.0.0.1:3100` | **DESKTOP-ONLY** | Bundled UI is a local origin; new minimal capability set. |
| `desktop/src-tauri/src/main.rs` notification bridge (`be-notify` events) | Events-not-commands workaround for remote origin | **DESKTOP-ONLY** | Bundled mobile UI can call the notification plugin directly. |
| `desktop/ui/index.html` | Splash screen | **ADAPT** | A splash is still useful; reimplement mobile-first. |
| `scripts/desktop-*.js` | Payload/package/installer/self-test | **DESKTOP-ONLY** | Mobile has its own build scripts and store pipelines. |
| `src/lib/bots/state.test.ts` | Schedule, draft, pin, formatting tests | **REUSE** | Move with `state.ts`; keep as the regression net for extracted logic. |
| `src/lib/bots/ghost.test.ts`, `ghost-mood.test.ts`, `mentions.test.ts`, `run-error-help.test.ts`, `chat-store.test.ts` | Pure unit tests | **REUSE / ADAPT** | `chat-store.test.ts` asserts the old persistence; rewrite for SQLite. |
| `src/lib/bots/invoke.test.ts` | Asserts provider call options and persona messages | **ADAPT** | Split: prompt builders keep the test; the run call becomes a Rust test. |
| `src/lib/bots/state-sync.test.ts` | Envelope/timestamp semantics | **DESKTOP-ONLY** | No mirror in v1. |
| `vitest.config.ts` | Node environment, `@` alias, `oxc: false` | **ADAPT** | Mobile gets its own config; add jsdom/happy-dom for sheets and keyboard flows. |
| Tauri bridge tests | **None exist** | **REBUILD** | Add command/event integration tests; the desktop shell has only `desktop:selftest`. |

## 6. What must not be reused, even though it looks tempting

1. **`state-sync.ts`** — a newest-wins merge engine is the wrong answer for one
   device; it adds a conflict rule with no conflict.
2. **`registry.ts` recovery** — `sessionStorage` + a 1.5 s poll for 10 minutes is a
   browser workaround. Mobile uses durable events and explicit resume.
3. **`bot-chat.tsx` / `group-chat-room.tsx`** — 48 KB and 44 KB desktop screens
   with Next stores, relative fetches and desktop dialogs. Copying them would
   import the whole coupling problem.
4. **The Python automation engine** — leases, breakers and an asyncio loop are
   correct for a server and wrong for a suspended phone.
5. **`python/harness/mcp/approvals.py`** — reuse the *invariants*, not the code.
6. **Desktop capabilities** — a bundled-origin mobile WebView does not need
   `remote.urls`; copying it would grant network origins IPC for no reason.

## 7. Reuse contract for the build

- Reused files keep their tests. A moved module that loses its test is treated as
  a regression.
- Extracted modules go to `packages/` with **no** `next/*`, `react`, `window` or
  `@/lib/harness` imports. A lint rule enforces this.
- `src/` in `Black-Eclipse-site` is not edited in Phase 0. Extraction that would
  require touching the desktop app is deferred until the mobile app proves it
  needs it.
