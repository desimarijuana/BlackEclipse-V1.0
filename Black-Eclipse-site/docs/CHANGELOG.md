# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-15

- **`npm run setup:hostname` — one-command, self-elevating local hostname.**
  Added `scripts/setup-hostname.ps1` (re-launches itself via UAC, appends
  `127.0.0.1 blackeclipse` to the Windows hosts file only when missing, flushes
  DNS) and the npm script `setup:hostname`. Root cause of "cannot see
  `blackeclipse`": the hosts entry is required for the name to resolve and a
  normal shell cannot write the protected file. Verified on this machine: entry
  added, `ping blackeclipse` → `127.0.0.1`, and `http://blackeclipse/` →
  `200` (`x-powered-by: Next.js`) with `localhost:3000` still `200`.
  docs updated: `docs/local-hostname.md`, `docs/QUICKSTART.md`,
  `docs/NAVIGATION.md`, this file.

- **Redesigned the global crash screen (`ErrorBoundary`).** The full-page
  "Something went wrong" fallback dropped its ⚠️ emoji and flat layout for a
  frosted `.glass-card` with a rose wash, an `AlertTriangle` icon badge, and
  primary "Try again" + secondary "Reload" actions; the panel is centred over a
  `min-h-[100dvh]` region. Same treatment as the chat error card.
  no doc change — visual/UI only, no contract change.

- **Local hostname front door: reach the app at `http://blackeclipse`.** Added a
  zero-dependency, loopback-only reverse proxy (`scripts/local-proxy.js`; Node's
  built-in `http`/`net`) that listens on `127.0.0.1:80` and forwards to the
  unchanged Next.js server on `:3000`, preserving the original `Host` and adding
  `X-Forwarded-*`, and forwarding WebSocket/HMR upgrades. Paired with a
  `scripts/local-proxy-stop.js`, the npm scripts `proxy` / `proxy:stop`, and a
  LAN-safe `dev:local` (`next dev -H 127.0.0.1`); `dev` is unchanged. Because the
  new hostname changes the browser origin, three small code points were made
  hostname-aware: `src/lib/api-guard.ts` treats `blackeclipse` as a loopback
  alias AND resolves the request host from the `Host`/`x-forwarded-host` header
  instead of `request.url` (which Next rebuilds from its own bind address in dev,
  so a fronted same-origin POST otherwise 403'd); `src/lib/auth/handlers.ts` uses
  the shared `isLocalRequest` so the session cookie is not marked `Secure` over
  plain http; `next.config.ts` lists `allowedDevOrigins` so Next dev does not flag
  `/_next/*`/HMR as cross-origin. Verified live (homepage 200, `/api/news` 200,
  same-origin POST 200, cross-site 403, HMR `101`, localhost:3000 still 200). docs
  updated: `docs/local-hostname.md` (new), `docs/NAVIGATION.md`,
  `docs/QUICKSTART.md`, this file.

- **Redesigned the chat error/warning surface.** The assistant error card in
  `chat-history.tsx` is now a frosted `.glass-card` with a rose wash, an icon
  badge, a heading, an optional error-code chip and a clearer Retry action; the
  separate "Something went wrong" status line is suppressed when the card shows,
  and a new `restatesError` guard stops a failed command from printing the same
  sentence twice (the router streams both a readable `output` and an
  `error.message`). no doc change — visual/UI only, no contract change.

- **Global "New chat" shortcut (Ctrl/Cmd+Alt+N).** Replaces the ChatBot-tab-only
  `mod+n` page shortcut (`usePageShortcuts(chatRootRef, …)` in `stock-chat.tsx`)
  with a shell-wide keydown handler: it switches to the ChatBot tab, clears the
  transcript, and drops the caret in the composer via the existing `be:focus-chat`
  event. `Ctrl/Cmd+N` was unusable for this — browsers reserve it for "new window".
  The shortcuts overlay gained the row; the shell's size-budget pin was re-pinned
  1441→1455 with justification.
  no doc change — keybinding/UX only, no architecture or contract change.

- **Search: embeddings are stored at boot, not only after a query.** The boot
  warm-index now resolves the embedding provider from the front-door environment
  (`HARNESS_JOB_*`, via `SearchService._boot_settings`) and EMBEDS at index time,
  so `vectors` is non-zero as soon as the runtime boots with a provider —
  previously the boot ran `configure(None)`, so every document stayed `vectors: 0`
  until a later query re-configured a provider and triggered the backfill. A bare
  runtime (no front-door env) still indexes honestly keyword-only. Tests:
  `python/tests/test_search_code_source.py` (+2). docs updated:
  `docs/harness/search-retrieval.md`.

- **Plain `/` now focuses the chat composer; global search stays on Ctrl/Cmd+K.**
  `useCommandCenterKeybind` dropped its `slashShortcut` handling so the command
  center is toggled by `Ctrl/Cmd+K` alone; a new `useChatFocusKeybind`
  (`src/hooks/use-chat-focus-keybind.ts`) broadcasts a `be:focus-chat` window
  event on `/`, which the visible composer answers (`ChatInput` guards with
  `isKeyboardScopeVisible`, `ChatDock` ignores while suppressed and restores from
  the minimized pill first). Mounted once with `GlobalSearch`, so it covers every
  route. The shortcuts overlay row was relabeled accordingly.
  no doc change — keybinding/UX only, no architecture or contract change.

- **Focus mode (Ctrl/Cmd+Alt+X) now fills the page instead of a centered
  column.** The chat tab's focus branch dropped its `max-w-[860px]` caps, so the
  transcript, follow-up composer and the landing composer (`empty-state.tsx`)
  use `max-w-none` and span the full main panel; the shortcuts-overlay
  description was corrected to say "full-width focus view".
  no doc change — layout/UX only, no architecture or contract change.

- **Focus mode now also tucks away the right-docked Agent Workspace.** With the
  left sidebar, header and terminal already hidden there, the still-docked
  workspace was the last column splitting the page in two; it now unmounts in
  focus mode (state lives in its store, so it returns on exit), giving the chat
  the whole width. Same change scope as above.
  no doc change — layout/UX only, no architecture or contract change.

- **Startup hardening: stop the spurious "runtime unavailable" 503 loop and the
  dev chunk-load overlay.** The Python runtime is now pre-started (non-blocking)
  by `src/instrumentation.ts` instead of only lazily on the first harness
  request, and the cold-start readiness budget is configurable via
  `HARNESS_PY_START_TIMEOUT_MS` with the default raised 30s → 120s
  (`src/lib/harness/python-runtime.ts` + pure `resolveStartTimeoutMs` /
  `DEFAULT_START_TIMEOUT_MS` in `src/lib/harness/runtime-supervision.ts`). A cold
  start imports the whole agent stack; the old 30s budget let the front door kill
  a still-starting process and respawn it forever under load, so every route
  503'd. Separately, the dev-only webpack `output.chunkLoadTimeout` is raised to
  300s in `next.config.ts` so a slow `next dev` first compile no longer surfaces
  as a `ChunkLoadError` / "Invalid or unexpected token" overlay (a slow compile,
  not a syntax error — `tsc`/`next build` pass; `npm run up` serves prebuilt
  chunks). Tests: `src/lib/harness/runtime-supervision.test.ts` (+4 cases).
  docs updated: `docs/harness/architecture.md`, `docs/QUICKSTART.md`, this file.

- **Bot Team Orchestration: run a team of Bots on one objective.** A new
  composition layer (`python/harness/team/`) gives the existing Bot system five
  native multi-agent capabilities without forking anything: capability-routed
  Bot-to-Bot delegation through the A2A layer (least privilege + budgets +
  durable messages), dependency-aware concurrent execution on the existing
  `TaskScheduler` (new per-Bot `task.metadata.maxConcurrency` /
  `HARNESS_TASK_MAX_PER_AGENT` and per-plan `plan.metadata.maxConcurrency` caps),
  a validated task graph (cycle/unknown-dependency detection), deterministic
  evidence-based conflict reconciliation (never voting or averaging; benign
  causes classified, genuine conflicts disclosed), and an independent reviewer
  with bounded targeted repair + re-verification (a producing Bot can never
  approve its own work). Also fixed a real A2A dispatch gap: `delegate_task` now
  starts the plan so a delegated task is actually picked up (additive
  `autostart`/`plan_id`/`dependencies` params, defaults preserve old behaviour).
  Reachable from the chatbot via `TEAM_TOOLS` (on the default agent allowlist) and
  from `POST /team/runs`; front door `src/lib/harness/team-client.ts` +
  `src/app/api/team/[[...path]]/route.ts`. Tests:
  `python/tests/test_team_{graph,conflicts,review,service,e2e}.py` (43 cases incl.
  measured concurrency, cancellation, restart durability, review→repair,
  `requireApproval` gate, budget usage accounting). Also enforced the documented
  gaps: `TeamPolicy.requireApproval` is now a hard gate against the A2A approval
  store, and the task executor meters/limits A2A token+tool-call usage
  (`tasks/bootstrap.py`). docs updated: `docs/harness/bot-team-orchestration.md`
  (new), `docs/NAVIGATION.md`, this file.

- **Chat: `@`-mention a bot or group chat from the main composer to delegate the
  turn.** Typing `@` in the main chat opens a palette of the user's bots and group
  rooms (`src/components/chat/chat-input.tsx`); selecting one inserts `@Name ` and
  shows a chip. On send the message is DELEGATED to each mentioned target over the
  SAME runtime path the Bots workspace uses — a bot answers as itself (persona +
  private `bot-<id>` memory), and a mentioned room has every member answer in its
  own voice. Replies stream into the transcript attributed to their author
  (`Message.author`, rendered in `chat-history.tsx`). A completed exchange is
  MIRRORED into the bot's/room's own Bots-tab thread (`useBotChatStore` /
  `useBotGroupsStore`), and a mid-run approval is surfaced on the message and
  decided by the delegation hook — the invoker now forwards typed harness events
  via `onEvent`, and `stock-chat.tsx` routes the ApprovalCard decision to the
  delegated run when the pending approval belongs to it. Pure mention
  registry/parser `src/lib/bots/mentions.ts` (+ `mentions.test.ts`); shared turn
  invoker `src/lib/bots/invoke.ts` (extracted from `bot-chat.tsx` /
  `group-chat-room.tsx`, which now call it); lifecycle hook
  `src/lib/bots/use-bot-delegation.ts`; routing through `dispatchTurn` in
  `stock-chat.tsx` (send / follow-up / edit / injected prompts). `stock-chat.tsx`
  re-pinned 1399→1441 in the size ratchet (the bulk was extracted to the hook).
  docs updated: `docs/harness/mentions.md` (new),
  `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.

## 2026-10-14

- **Slash commands: fix the wired commands found broken end-to-end.**
  `/market` was calling the browser-only `market-client` (relative fetch) from
  the server — it now goes through the router's loopback `frontDoor`
  (`/api/harness/market/{providers,health}`). `/research`, `/deep-research`,
  `/web`, `/read` used a double-prefixed path (`/api/research/web/run`); the
  research front door already prepends `/research/web/`, so the path is now
  `/api/research/run`. `/code` was broken for everyone: the `/api/code/tasks`
  route never supplied the required `callbackBaseUrl`/callback token to Python
  (now injected server-side, like a chat run), and `code-client` crashed
  redacting a non-string `detail` (now handled). `/code` now defaults to
  `plan_only` (fast) with `--autonomy edit_verify` opt-in. Verified every command
  end-to-end against the running server (all `completed`). docs updated:
  `docs/harness/slash-commands.md`.

- **Slash commands: every command is now real (the `soon` badge is gone).**
  Implemented the nine previously-unavailable commands against the SAME front-door
  APIs the UI uses, via a new loopback `frontDoor` dependency in the router:
  `/quote` (`/quotes`, JDdS quotes with honest freshness), `/research`,
  `/deep-research`, `/web`, `/read` (web research engine → answer + sources),
  `/backtest` (list strategies, or backtest one by id), `/code` (start a code
  task), `/terminal` (`/run`, `/sh` — run a shell command, operator- and
  effect-gated). No command re-implements an engine. Fixed a parser bug where
  argument tokens like `ls -la` were mis-read as unknown flags (a short `-x` is
  now a flag only when the command declares that alias). Split the dispatch table
  into `command-handlers.ts` so `command-router.ts` stays under the 1200-line hard
  ceiling. New registry/router tests for the wired commands + a synthetic
  unavailable-spec test; full vitest 3074 passed; `npx tsc --noEmit` clean;
  eslint clean; verified end-to-end (`/quote AAPL` → 200 with a quote table).
  docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.

- **Chat: the `/` palette no longer hides commands.** The palette capped its
  results at 12, so with ~29 registered commands (portfolio, memory, mcp, usage,
  backtest, …) later-alphabetical commands never appeared. Removed the cap; the
  list is scrollable, so every command is reachable and a prefix narrows it. Added
  a registry test asserting the catalog exposes more than 20 commands and a bare
  search returns them all. `chat-input.tsx` + `command-registry.test.ts`. UI-only;
  no doc change — `docs/CHANGELOG.md` only.

- **Chat: `/skill` now authors a skill for Eclipse (stored on the Skills page).**
  Repurposed `/skill <name> <what it should do>` from "execute a skill" to an
  AGENT-TURN command: the query is rewritten (`src/lib/harness/command-agent.ts`)
  into a skill-authoring directive and the normal chat turn runs, so the chatbot
  generates the skill and persists it with `skill_create` (single-use operator
  approval) — it then appears on the Skills Control Room to view/edit/enable/run.
  Running an existing skill moved to `/skills run <id>`. The agent-turn path runs
  under the default profile (no classifier narrowing) so write-capable tools stay
  bound. Updated the runtime prompt (`python/harness/prompts.py`) so the agent
  knows it MAY author skills; kept the prompt under its size ratchet (29205 <=
  29252). New `command-agent.ts` + tests; registry/parser/router/route tests
  updated. docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.

- **Chat: the `/` command palette uses the Command (⌘) icon.** Replaced the
  generic `Sparkles` glyph on the palette rows and the active-command badge with
  the `Command` icon (already mapped in `src/lib/icons`), so slash commands read
  as commands rather than as "AI magic". `chat-input.tsx` only. UI-only; no doc
  change — `docs/CHANGELOG.md` only.

- **Chat: the `/` command palette is now background-less frosted glass.** The
  popup's solid tint was removed in favour of a near-transparent tint + strong
  backdrop blur (new `.glass-command-popover` class, with light-mode + glass
  on/off + high-contrast overrides). The palette is now portaled to `<body>` and
  anchored to the composer so the blur samples the real page instead of a scoped
  backdrop root (which would flatten the frost). `chat-input.tsx` +
  `globals.css`. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: Aurora glow shows on the ChatBot landing only.** Restrict the local
  in-panel `AuroraGlow` to the empty-transcript landing (not the conversation
  view, which keeps its calm chat surface). `stock-chat.tsx` only. UI-only; no
  doc change — `docs/CHANGELOG.md` only.

- **Slash commands: wire the remaining high-value commands + close the gaps.**
  Promoted `/tools`, `/usage` (`/cost`), `/market`, `/portfolio`, `/memory` and
  `/mcp` from declared-unavailable to real handlers backed by their existing TS
  clients (runtime health/tools, usage summary, market gateway providers+health,
  Portfolio Accounting Engine, Eclipse-Memory overview, MCP server list). Wired
  `/skill-create --from-workflow` through the learning engine and made
  `/skill-create`'s name optional when a source id is given. Confirmed automatic
  skill selection in normal chat is already provided by the runtime's
  `skill_list`/`skill_view`/`skill_invoke` tools (documented, not re-implemented).
  Added a route-level test for `/api/harness/command`. Tests: 62 command/route
  cases; full vitest 3040 passed; `npx tsc --noEmit` clean; eslint clean.
  Re-pinned the size-budget ratchet for `stock-chat.tsx` (1391->1399) to the
  measured tree after the concurrent "Aurora glow" chat-shell commit grew it
  (unrelated to this work). docs updated: `docs/harness/slash-commands.md`.

- **Fix: Aurora glow was missing on the ChatBot page.** The shell's `AuroraGlow`
  sits at the root `z-0`, but the chat panel (`z-10`) now paints an opaque chat
  surface / wallpaper over it, so the glow was covered. Mounted a local
  `AuroraGlow` inside the chat panel — above the surface, below the transcript —
  when the chat tab is active (mirrors the fullscreen Command Center overlay).
  `stock-chat.tsx` only. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: message action buttons are icon-only.** Copy / Redirect / Regenerate /
  Edit dropped their text labels (the word "Copied" shows via the check icon and
  tooltip instead) to save space in the compact action row. `chat-history.tsx`
  only. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Slash command system: canonical registry + shared execution router + real
  skill integration.** Added a canonical `CommandSpec` registry
  (`src/lib/harness/command-registry.ts`) consumed by both the chat composer
  palette and a shared router (`command-router.ts`), plus a real tokenizer/parser
  (`command-parser.ts`) supporting quoted args, Unicode, filenames with spaces,
  and pass-through `--key value` flags. The router runs Parse -> Resolve ->
  Validate -> Authorize -> Execute -> Render -> Audit and dispatches only to
  existing systems (skills-client, tasks-client, workflows-client, the Python
  runtime); unavailable commands return an explicit unsupported error and are
  never advertised as functional. Implemented `/help`, `/status`, `/tasks`,
  `/workflows`, `/agents`, `/models`, the skill family (`/skills`,
  `/skill`, `/skill-explain`, `/skill-test`, `/skill-enable`, `/skill-disable`,
  `/skill-create`) and kept `/eclipsesdk` as a profile switch. Wired into
  `/api/harness/chat` and `/api/harness/chat/stream` (synthetic terminal frame)
  and a direct `/api/harness/command` route. Tests: 52 new vitest cases across
  `command-{registry,parser,router}.test.ts`; `npx tsc --noEmit` clean; full
  vitest suite 3025 passed. docs updated: `docs/harness/slash-commands.md`,
  `docs/NAVIGATION.md`.

- **Self-editing harness — release gate green.** `npx tsc --noEmit` reports 0
  errors and `npm run test` passes end-to-end (vitest 2981, python 6227 passed /
  16 skipped, eval gates ALL PASS). Gate hardening in this pass: journal null
  guards + LF normalization, size-budget re-pins, and a self-contained
  automation-tools fixture (the shared store is closed by a prior app shutdown).
  docs updated: `docs/CHANGELOG.md`.

- **Chat: scrollbar is hidden by default and appears only on user scroll/drag.**
  It no longer shows on load or during auto-follow of streamed messages
  (programmatic scrolls are flagged so they don't reveal it); it appears while
  the user scrolls or drags the thumb, then fades out when idle.
  `chat-history.tsx` only. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: no hover reveal on the scrollbar.** Hovering (including the thumb) no
  longer shows it — the thumb appears only while scrolling or dragging and fades
  when idle. `chat-history.tsx` only. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat: scrollbar only shows while actually in use.** The previous pass also
  revealed the thumb on hovering the whole transcript, so it never hid (the
  pointer is usually over the chat). It now appears only while scrolling or
  dragging (and lingers briefly on the thumb itself), then fades out otherwise.
  `chat-history.tsx` only. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: the scrollbar auto-hides and reappears when in use.** The transcript
  thumb is now an overlay: it reveals while scrolling, hovering the transcript or
  dragging, then fades out when idle. `chat-history.tsx` only. UI-only; no doc
  change — `docs/CHANGELOG.md` only.

- **Chat: the transcript scrollbar is now draggable.** The native bar is hidden
  (`scrollbar-hide`) and the short custom thumb was `pointer-events-none`, so it
  looked like a scrollbar you couldn't grab — "not working". It's now an
  interactive, grabbable thumb (`onBarPointerDown` drags `scrollTop`, wider hit
  area, hover/active states). `chat-history.tsx` only. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **ChatBot Page settings: added a Prompt bubble color control.** The user's own
  message bubble can now be colored from Customization › ChatBot Page › Chat
  background › Prompt bubble (dark + light, "Default" = neutral tint). Backed by
  `chatBubbleColor`/`chatBubbleColorLight` + `resolveChatBubbleCss` in
  `backgrounds.ts` → `--chat-bubble-bg-light/-dark`, consumed by a new
  `.chat-bubble` class on the `ChatHistory` prompt bubble. docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`; plus `docs/CHANGELOG.md`.

- **Chat: fixed invisible prompt bubbles.** The pure-white bubble was invisible on
  the near-white light chat surface. The bubble is now a soft foreground tint
  (`bg-foreground/10`, i.e. a light grey in light mode) with `dark:bg-white/10`
  (a lighter translucent white in dark), so it reads clearly in both schemes.
  `chat-history.tsx` only. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: prompt bubble is now lighter in light mode too.** Follow-up to the
  dark-mode fix: the bubble is an elevated lighter surface in both schemes now —
  pure `bg-white` + soft shadow in light (over the matte `#f4f4f5` surface),
  `dark:bg-white/10` in dark (over `#0a0b0b`). `chat-history.tsx` only. UI-only;
  no doc change — `docs/CHANGELOG.md` only.

- **Chat: prompt bubble no longer disappears on the dark chat surface.** With the
  new `#0a0b0b` conversation background, the bubble's `var(--card)` fill blended
  in. Swapped it to a scheme-aware translucent foreground tint (`bg-foreground/10`)
  — slightly lighter in dark, slightly darker in light — so it stays distinct and
  still border-free. `chat-history.tsx` only. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat background is now on by default with a dark/light pair.** The
  conversation surface defaults to `#0a0b0b` in **dark** and a matte `#f4f4f5`
  in **light**. Made it scheme-aware: added `chatSurfaceColorLight` and changed
  `resolveChatSurfaceCss` to return per-scheme `background` values, applied as
  `--chat-surface-bg-light/-dark` and consumed by `.chat-surface-layer`
  (light base + `html.dark` override). Panel gains a light color control. The
  layer renders only once a conversation exists so the landing wallpaper still
  shows. docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`; plus
  `docs/CHANGELOG.md`.

- **B2 — the real restart seam (front door owns it).** A change under
  `python/harness/**` only takes effect after a restart, and the runtime cannot
  restart itself, so the front door now owns it: `restartPythonRuntime()`
  (`src/lib/harness/python-runtime.ts`) kills the runtime listener, clears the
  health cache, re-spawns and waits for `/health`; exposed at
  `POST /api/harness/runtime/restart`. The chat promotion panel shows a
  **"Restart Eclipse now"** button when the landing verdict requires it
  (`restartHarnessRuntime` in `code-browser.ts`, i18n
  `code.promote.restart{Now,ing,ed,Failed}`). The front door also auto-restarts
  on a stale runtime (`ensurePythonRuntime` replaces a process started before the
  newest harness source), so a landed self-edit takes effect on the next call.
  Docs updated: `docs/harness/self-editing-harness-plan.md`,
  `docs/harness/architecture.md`; plus `docs/CHANGELOG.md`.

- **Self-edit end-to-end acceptance test (the original failure, measured).** New
  `python/tests/test_self_edit_e2e.py` drives the WHOLE path with REAL components:
  the `edit_verify` chat surface binds the write tools; `portfolio_create` (the
  first reported failure) is admitted by the composed chain and requires a
  single-use `portfolio_write` approval through a real `ApprovalStore`
  (PENDING → APPROVED → consumed; one approval authorizes exactly one call; a
  changed payload needs a new one). Program doc updated with the final status.
  Docs updated: `docs/harness/self-editing-harness-plan.md`; plus
  `docs/CHANGELOG.md`.

- **Rollback + self-hosting verdict are now in the chat UI.** The promotion panel
  (`src/components/chat/promote-change.tsx`) shows a **"Put the previous version
  back"** control after a change lands (calling the new front-door route
  `src/app/api/code/promotions/[rollbackId]/rollback/route.ts` →
  `rollbackPromotion`), and surfaces the self-hosting verdict ("Eclipse will
  restart/rebuild to apply this") from the new `landing` field on the
  promotion preview/apply responses. New i18n keys `code.promote.{rollback,
  rollingBack,rolledBack,restartNote,buildNote}`. Client types extended in
  `code-client.ts`/`code-browser.ts` (`PromotionLanding`, `rollbackId`). tsc clean
  on touched files; 375 TS tests pass. Docs updated:
  `docs/harness/roadmap/phase-15-attachments-and-artifacts.md`; plus
  `docs/CHANGELOG.md`.

- **Self-edit hardening batch: the general advertised-but-dead guard, three dead
  tools fixed, the terminal floor proven, and i18n.** (1) New
  `python/tests/test_advertised_tool_admission_all.py` enumerates EVERY advertised
  non-read tool across all agent allowlists + the chat code profile and asserts
  each is admitted by the real chain with a permissive store — pinning only the
  deliberately-deferred infra/cloud mutations. On first run it caught three real
  bugs, now fixed: `code_rename_symbol` was mis-routed to the action authorizer
  when a workspace was bound (`code/authorizers.py`); `image_generate` (paid
  external) had no layer (new `vision/authorizers.py`, kind `vision_external`);
  `learning_progress_update` had no layer (benign local-write admission). (2) New
  `python/tests/test_terminal_floor.py` proves a `deny` command is refused before
  any grant/approval — the hard floor below "always allow". (3) The `/eclipsesdk`
  palette/badge strings are now i18n keys (`code.command.*`, wired via `useT`,
  covered by `plain-language.test.ts`). (4) New program doc
  `docs/harness/self-editing-harness-plan.md` + a NAVIGATION row. Tests added:
  `test_advertised_tool_admission_all.py`, `test_terminal_floor.py`. Docs updated:
  `docs/harness/self-editing-harness-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/architecture.md`; plus `docs/CHANGELOG.md`.

- **Self-hosting safety (Track B): a change to Eclipse's own live code is
  health-gated.** New `python/harness/code/selfhost.py`. `classify_landing(paths)`
  (pure) flags a `python/harness/**` change as needing a RUNTIME RESTART, a
  `src/**` change as needing a BUILD gate, and a change to an AUTHORITY path
  (`code/policy.py`, `code/authorizers.py`, `mcp/approvals.py`,
  `skills/permissions.py`) as REFUSED (never hot-swapped — it could alter
  Eclipse's own permissions). `guarded_land(preview, verify=, restart=, ...)`
  orchestrates apply → (restart) → verify → rollback: a failed verify calls the
  new `rollback_promotion` and refuses `SELFHOST_VERIFY_FAILED`. All side effects
  are injected (the process restart is the one seam); the promote routes now
  return a `landing` verdict. Tests: `python/tests/test_selfhost_landing.py`.
  Docs updated: `docs/harness/architecture.md`; plus `docs/CHANGELOG.md`.

- **Landing a change is now reversible: promotion rollback.** `apply_promotion`
  (`python/harness/code/promotion.py`) captures the ORIGINAL contents of every
  touched file under `.black-eclipse/promotions/<previewDigest>/` before it writes
  and returns a `rollbackId`. New `rollback_promotion(rollback_id)` is the exact
  inverse — a file the promotion CREATED is removed, an EDITED file restored, a
  DELETED file recreated; a file changed after the promotion is refused
  (`PROMOTION_BASE_CHANGED`), never clobbered; both versions survive (the backup
  is kept). Reuses `code/patch.py` (confinement/protected-path/atomicity); a
  failed apply discards its backup. Route:
  `POST /code/promotions/{rollback_id}/rollback` (operator-gated). Tests:
  `python/tests/test_code_promotion_rollback.py`. Docs updated:
  `docs/harness/roadmap/phase-15-attachments-and-artifacts.md`; plus
  `docs/CHANGELOG.md`.

- **The extension layer: the agent can author its own skills (Track 4).** New
  `python/harness/skills/manage_tools.py` — `skill_create` / `skill_update` /
  `skill_delete`, Eclipse's `skill_manage` analogue. A skill is DECLARATIVE (a
  validated manifest + bounded instructions), authored through the SAME
  `SkillRegistry.create_user_skill`/`update_user_skill`/`delete_user_skill` a
  person uses; `authoring.build_user_manifest` refuses any permission outside
  `SAFE_PERMISSIONS` and editing makes a NEW version, so an agent-authored skill
  can never widen its own authority. Gated by `make_skill_manage_authorizer`
  (composed in `code/authorizers.py`): a single-use, digest-bound operator
  approval per call (kinds `skill_create`/`skill_update`/`skill_delete`,
  pause-in-card-mode included). The three names joined
  `code.policy.ACQUISITION_WRITE_TOOLS` (removed at `plan_only`), the code agent +
  chat profile, and are registered from `skills/install_tools.py` (kept off the
  ratcheted `service.py`). Tests: `test_skill_manage_tools.py` (+ new admission
  rows). Docs updated: `docs/harness/architecture.md`; plus `docs/CHANGELOG.md`.

- **`/eclipsesdk` is a real composer command; the advertised-but-dead guard now
  covers the whole portfolio family.** Follow-up to the portfolio fix. (1) The
  chat composer (`src/components/chat/chat-input.tsx`) shows a slash-command
  palette while a bare `/word` is typed (arrows navigate, Enter/Tab completes,
  Escape clears) and an active-command badge once an instruction follows, driven
  by `CHAT_COMMANDS` from `src/lib/harness/commands.ts` (client-safe). (2) The
  synchronous path (`chatWithAgent`) now parses the command too, so
  `/eclipsesdk` works on `/api/harness/chat` as well as the streaming path;
  `StartRunOptions.command` carries the marker. (3) New
  `python/tests/test_advertised_tool_admission.py` composes the REAL authorizer
  chain with a permissive store and asserts every advertised mutation family
  (execution/runtime, acquire, bot, git, skill/mcp install) and the ENTIRE
  portfolio write+consequential set is admitted, while unknown and
  deliberately-operator-only tools (k8s/helm/terraform/deploy) still fall through
  — the regression guard for the `TOOL_FORBIDDEN`-while-advertised defect class.
  Added classifier regression cases for "create an application within eclipse".
  Tests: +34 admission, +42 vitest. Docs updated: `docs/harness/architecture.md`;
  plus `docs/CHANGELOG.md`.

- **Portfolio mutations are reachable again + Eclipse's first chat command
  `/eclipsesdk`.** Two fixes. (1) `python/harness/portfolio/authorizers.py`
  (`make_portfolio_authorizer`) is composed into the ONE effect chain
  (`code/authorizers.py`), so every `portfolio_*` mutation is admitted and gated
  by a single-use, digest-bound operator approval (kind `portfolio_write`) instead
  of falling through to the MCP authorizer and returning `TOOL_FORBIDDEN` while
  advertised — the same defect class `_admit_runtime_tools` fixed for the
  execution family (measured before: `portfolio_create` refused). Admission is
  conditional (grant / claim / request-then-pause), never a bypass. (2) A leading
  `/command` in chat is parsed by the front door (`src/lib/harness/commands.ts`,
  `parseChatCommand`): `/eclipsesdk` (alias `/esdk`, case-insensitive) forces the
  chat code profile (`edit_verify`) + analysis sandbox and sends an additive
  `RunRequest.command` marker (`schemas.py`), which the runtime never treats as
  trivial (`graph_context.py`); the token is stripped before the run. Tests:
  `python/tests/test_portfolio_authorizer.py` (+57), `test_run_command.py`,
  `src/lib/harness/commands.test.ts`, `run-service.test.ts`. Docs updated:
  `docs/harness/architecture.md` (authorizer chain + command),
  `docs/portfolio-accounting.md`; plus `docs/CHANGELOG.md`.

- **Chat: assistant replies now show how long the turn took.** Added a small
  clock + duration badge on the LEFT of the hover action row (copy/regenerate/
  feedback), right before the model badge. Turn time is measured client-side in
  `stock-chat.tsx` / `chat-dock.tsx` (send → settled) and stored on the message as
  optional `durationMs` (`types/chat.ts`); persisted with the transcript. New
  `formatTurnDuration` helper. UI-only, additive message field — no doc change;
  `docs/CHANGELOG.md` only.

- **Customization: added a dedicated "Chat background" surface for the ChatBot
  conversation.** The page backdrop painted the whole ChatBot page, but the
  message/composer area had no separate color control. Added opt-in
  `chatSurface*` prefs to `backgrounds.ts` (`chatSurfaceEnabled/Fill/Color/
  Color2/Opacity` + `resolveChatSurfaceCss`), a `.chat-surface-layer` (globals.css)
  painted behind the chat tab in `stock-chat.tsx`, and a `ChatBackgroundCard` in
  Customization › ChatBot Page (flat/gradient, two colors, strength). Independent
  of the page backdrop; off by default. docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`; plus `docs/CHANGELOG.md`.

- **Aurora styles reworked for a proper look (anti-aliased, intentional).** The
  first pass overlaid a flat stencil on the ribbon (hard-edged `step` masks, an
  over-bright scanline `mix(…,1.2)`), which read as a screen door. Refactored
  the fragment shader around a shared `auroraField(uv)` + `fieldAlpha(f)` helper:
  Dot matrix and Blocks now sample the field once per **cell centre** (real LED/
  pixel grids, per-cell color), Pillars sample one field column per bar (true
  equaliser), and Scanlines are thin bright CRT lines with dark gaps instead of
  broad bands. Edges are smooth-stepped (no aliasing) and no style can exceed the
  field brightness. Verified by rendering the real shader in headless Chromium
  (Playwright) across all five styles. `src/components/ui/Aurora.tsx` only;
  `docs/CHANGELOG.md` only.

- **Aurora gained render styles: dot matrix, scanlines, pillars, blocks.** Added
  a `style` slice (`AuroraStyleId` + `grid` px) to `AuroraConfig`, a `uStyle`/`uGrid`
  uniform pair, and a style branch in the Aurora fragment shader. The sentiment
  color field is identical across styles; the branch only reshapes how it is
  drawn — `ribbon` (shipped), `dots` (LED dot matrix), `scanlines`, `pillars` and
  `blocks`. `aurora-settings.tsx` gets a Style card (chips + a cell/line size
  slider for non-ribbon modes); `Aurora.tsx` applies style per frame without
  rebuilding the WebGL context; `aurora-glow.tsx` passes it through;
  `AuroraConfig.style` is validated in `config.ts` and covered by
  `src/lib/aurora/config.test.ts`. Docs updated: `docs/ARCHITECTURE.md`
  (§ Aurora customization), `docs/NAVIGATION.md`.

- **Flow block: proper heading.** The heading was offset because the "Full page"
  button floated over the centered title (forced `pr-20`). The header is now a
  `grid-cols-[1fr_auto_1fr]` row — heading truly centered in the middle column,
  the button in its own right column — with the title as a centered `h3`
  (`text-base font-semibold`, wrapping, divider below) above the description, so
  it reads as a real section heading. UI-only. Docs: `docs/interactive-response-engine.md`.

- **Flow block: full page is now a PROPER full page (portaled overlay).** The
  overlay overlapped page elements because `position: fixed` was trapped inside a
  transformed/filtered chat ancestor. The viewer is now portaled to
  `document.body` (matching the app's `EventDossierOverlay`/`FullPageMap`
  pattern): `fixed inset-0 z-[100]`, a `bg-black/70 backdrop-blur-md` backdrop
  button, and a `h-[90vh] w-[94vw] max-w-6xl` card with a header bar — so it
  cleanly covers the true viewport. Body scroll is locked while open. UI-only;
  contract unchanged. Docs: `docs/interactive-response-engine.md` (flow entry).

- **Flow block: full page is for the WHOLE FLOW, not the icons.** Replaced the
  per-icon viewer with a visible **"Full page"** control on the block header that
  opens the entire flow in a full-screen overlay — larger cards, centered, on a
  frosted `backdrop-blur` over the page (the background behind it stays visible);
  Escape / backdrop / Close dismiss. Icons are now plain white glyphs (no
  click target, no badges). Kept the wider `max-w-3xl` layout and the proper
  centered heading. UI-only; contract unchanged. Docs:
  `docs/interactive-response-engine.md` (flow entry).

- **Flow block follow-up: wider, a visible expand affordance, and a proper
  heading.** Widened to `max-w-3xl` with more padding/step spacing (less
  cramped); each step icon now shows a persistent corner **expand badge**
  (`Maximize2`) so the full-screen icon view is discoverable rather than a hidden
  icon click; the block heading is a centered `h3` (`text-[15px] font-semibold`)
  with a divider and its description below. UI-only; contract unchanged. Docs:
  `docs/interactive-response-engine.md` (flow entry).

- **Flow block: centered + width-capped, white icons, and a full-screen icon
  viewer.** `flow-block.tsx` no longer renders full-bleed — the card is
  `mx-auto max-w-2xl` with its steps centered (`justify-center`, no stretching
  step cards) and each card's content centered. Semantic icons now render WHITE
  and uncoloured: the tone/status tint is removed from the glyph and its ring
  (status stays readable as the small dot/check beside the label). Clicking any
  step/path icon opens a full-screen frosted viewer (glass-card-strong) showing
  that icon large, with Escape / backdrop / Close to dismiss. UI-only; block
  contract unchanged. Docs: `docs/interactive-response-engine.md` (flow entry).

- **Settings › Aurora gained motion & shape controls.** The glow was only
  recolorable; the amplitude/speed/blend/noise-scale knobs were hardcoded in the
  shader. Introduced `src/lib/aurora/config.ts` (`AuroraConfig` = existing palette
  + `motion` intensity/speed/response + `shape` height/softness/noiseScale, with
  slider bounds, normalization and a v1-palette → v2-config migration under
  `be_aurora_config_v2`). The store now holds the three slices and persists one
  config; `Aurora.tsx` accepts `intensityScale`/`speedScale`/`softnessScale`/
  `noiseScale` props (multipliers on top of `resolveAuroraVisuals`, plus a new
  `uNoiseScale` uniform) so the sentiment→color model is untouched;
  `aurora-glow.tsx` applies the user height + scales, and `aurora-settings.tsx`
  renders a Motion & Shape card. Tests: `src/lib/aurora/config.test.ts`. Docs
  updated: `docs/ARCHITECTURE.md` (§ Aurora customization), `docs/NAVIGATION.md`.

- **Chat: prompt bubbles gained hover actions — Copy, Redirect, Edit.** The user
  message only had "Edit". Added a hover-revealed action row with a Copy icon and
  a "Redirect" (re-send the prompt) option. New optional `onResendMessage` prop on
  `ChatHistory`, wired in `stock-chat.tsx` (re-runs the prompt via the edit path)
  and `chat-dock.tsx` (truncates and refills the composer). `chat-history.tsx`,
  `stock-chat.tsx`, `chat-dock.tsx`. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat: activity steps are expanded by default.** `ActivityFeed` started
  collapsed and auto-collapsed when the run finished. It now defaults to open
  and stays open (auto-expand while working, but no auto-collapse); the header
  toggle still lets the user collapse it. `activity-feed.tsx` only. UI-only; no
  doc change — `docs/CHANGELOG.md` only.

- **Chat: activity steps are now unboxed (Hermes-style).** The `ActivityFeed`
  wrapped the tool/retrieval steps in a rounded, bordered, tinted card
  (`rounded-xl border border-border/40 bg-accent/[0.12]`) with an inner divider.
  Removed the surface, border and divider so the steps read as plain lines; kept
  the collapsed summary + expand toggle and behavior. `activity-feed.tsx` only.
  UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: opening the app now resumes the most recently active chat.** On load
  (and after deleting the active chat) it used `parsed[0]`/`updated[0]` — the
  first stored row, not the latest. Added `mostRecentConversation()` (by
  last-activity stamp, active scope only) to `chat-organization.ts` and used it
  in `stock-chat.tsx`. Covered by new unit tests. Internal behavior change, no
  data-shape/architecture change — no doc change; `docs/CHANGELOG.md` only.

- **Chat: model badge now hover-revealed on the right, like the other actions.**
  Rather than always-visible, the "answered by <model>" badge shares the
  copy/regenerate/feedback row's hover-reveal and sits flush right (`w-full`
  row + `ml-auto`), so it appears only on hover. `chat-history.tsx` only.
  UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat: moved the model badge next to the response actions.** The
  "answered by <model>" line used to sit above the output. It now shares the
  copy / regenerate / feedback row, right-aligned (`ml-auto`), while the action
  buttons stay hover-revealed. `chat-history.tsx` only. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat: removed the prompt-bubble border (real cause).** The earlier `border`
  removal had no effect because `globals.css` forces `border: 2px solid` +
  `border-radius: 24px` on **every** `.bg-card` element with `!important`. The
  bubble used `bg-card`, so it kept the outline. Swapped it to
  `bg-[var(--card)]` (same surface, escapes the global rule), so the bubble is
  now border-free with its own tighter radius. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Response engine, Phase 5/6 — de-duplicated the block vocabulary + parity &
  render-matrix CI.** Removed the last hand-copied block vocabularies so they can
  no longer drift from `src/lib/response/contract.ts`:
  (1) the static system prompt no longer enumerates block types — it points at the
  generated `eclipse-response block schema` digest, and that digest now emits the
  block-type menu GENERATED from the live contract (`response_tools.py`);
  (2) the stale `_CHART_TYPES` in `python/harness/evaluation/tools.py` (it carried
  `donut` and omitted `stacked_bar`/`grouped_bar`) is deleted — the offline smoke
  check now asserts only structure and defers every field name/enum to the TS
  contract. New CI guard `src/lib/response/contract-matrix.test.tsx`: it asserts
  the contract's block types, the renderer registry (`REGISTERED_BLOCK_TYPES`,
  newly exported) and a canonical sample per type are the SAME set, and renders
  EVERY block type from its canonical payload with no repair/degrade/error — a new
  block type cannot ship unrendered and a renamed field cannot silently break a
  figure. Docs updated: `docs/interactive-response-engine.md`.

- **Response engine, Phase 4 — the telemetry loop: the drift rate is now
  measurable.** The runtime measures each run's FINAL structured answer through
  the SAME render chokepoint the client uses and records the outcome. New bridge
  op `response_contract` `"finalize"` (`response-bridge.ts`) runs
  `finalizeFenceSource` and returns the render result (block count + repaired/
  degraded counts and block types). New `emit_response_telemetry`
  (`python/harness/response_tools.py`) is called once per run at the answer seam
  (`graph.execute_run`, beside `run.completed`); it emits the new observability
  hook `onResponseBlocks` (`observability/events.py`, `core.py`) which records
  `eclipse_response_blocks_total{outcome,type}`. A recurring `type` label is the
  closed-loop signal to add a normalization/repair rule. Best-effort and
  read-only: a bridge miss or a prose answer is a no-op and never breaks a run.
  Tests: `response-bridge.test.ts` (finalize op), `test_response_tools.py`
  (telemetry hook + metric). Docs updated: `docs/interactive-response-engine.md`,
  `docs/harness/observability.md`.

- **Response engine, Phase 3 — every producer route passes the chokepoint.**
  Audit found bots (`bot-chat.tsx`), group chat (`group-chat-room.tsx`) and the
  workspace document viewer (`agent-workspace/viewer.tsx`) already render through
  the same `Markdown` → `ResponseFence` path, so they inherit the guarantee with
  no change; two gaps were closed. (1) The deterministic planner
  (`planner.ts` `planMarkdown`) hand-builds blocks — it now re-validates them
  through `finalizeResponse`, so a future contract change can neither drop nor
  error a planner block. (2) Export (`export.ts` `responseToJson`/`responseToPdf`)
  now runs `finalizeParsed` defensively, so a downloaded JSON/PDF or a saved
  artifact can never contain an `unknown` block or an error diagnostic regardless
  of caller. New tests pin both (`export.test.ts`, `planner.test.ts`). Docs
  updated: `docs/interactive-response-engine.md`.

- **Response engine, Phase 2 — schema-driven repair: drifted blocks render as
  their intended visual, not degraded text.** Two new modules in
  `src/lib/response/`: `schema-meta.ts` introspects `ResponseBlockSchema` live into
  per-block metadata (required fields, kinds, enum values, array-item shapes), and
  `repair.ts` uses it to make ONE deterministic repair attempt per rejected block —
  generically, not per special case: a missing required field is rescued from a
  same-kind non-schema sibling (`title`→`name`, `datasets`→`series`,
  `headline`→`title`), an off enum value is aliased or nearest-matched
  (`bars`→`bar`, `vertical`→`TB`), a single value is wrapped into a required
  array, an object/array mismatch is unwrapped, and coercible scalars
  (`"true"`, `"12.4"`) are coerced. `finalize.ts` now runs repair before its
  Phase-1 degrade backstop and records the outcome (`BLOCK_REPAIRED` vs
  `BLOCK_DEGRADED`) on the telemetry seam. Because `schema-meta.ts` is derived
  from the contract, repair tracks the schema with no copy. New
  `repair.test.ts` pins enum nearest-match, sibling rescue, array wrap, scalar
  coercion, and repair-before-degrade end-to-end. Docs updated:
  `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`.

- **Response engine, Phase 1 — the render guarantee: a rejected block can no
  longer appear as an error, ever.** New chokepoint `src/lib/response/finalize.ts`
  (`finalizeResponse`/`finalizeParsed`/`finalizeFenceSource`) is now the single
  path to the renderer: it degrades every block the contract rejected to a
  `markdown` block carrying the block's REAL content (prose/title, else a JSON
  code fence) and downgrades every error diagnostic, so the renderer is a total
  function from any input to a proper render. `ResponseView` finalizes on render;
  `ResponseFence` degrades malformed settled JSON to a code fence instead of the
  red "could not be parsed" card; the per-block "Unsupported block type" card and
  the amber diagnostics panel are retired as user-visible states. Failures are
  retained on `response.diagnostics` and emitted through a degrade-telemetry seam
  (`setResponseDegradeReporter`) so the rate can be measured and driven to zero.
  This supersedes ADR-043's "unknown/malformed blocks become diagnostics" display
  behaviour (the fenced-block + registry decision itself is unchanged). New
  `finalize.test.ts` pins the invariant over an adversarial corpus; `render.test.tsx`
  updated at the three former error surfaces. Docs updated:
  `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`.

- **Chat: slimmed the user-message bubble and dropped its border.** The prompt
  bubble (`chat-history.tsx`) had a `border border-border` outline and generous
  padding. Removed the border (the `bg-card` fill defines it now) and tightened
  padding/type/radius (`px-3.5 py-2`, `text-[13px]`; compact `px-2.5 py-1.5`), so
  it reads lighter instead of like a large box. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat history: fixed the dropdown position.** The sort/filter popup used
  base-ui's `alignItemWithTrigger`, which jumped upward to overlay the selected
  option on the trigger. `HistorySelect` now opens as a normal dropdown directly
  below, right-aligned (`align="end"`, `alignItemWithTrigger={false}`), so it no
  longer covers the list awkwardly. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Document Authoring: Eclipse can now CREATE Word/Excel/PowerPoint documents.**
  New write-side subsystem `python/harness/documents/` + the `document_create`
  agent tool. It builds REAL `.docx` / `.xlsx` / `.pptx` files (and Markdown / CSV /
  JSON / `.txt`) from a neutral vocabulary (`blocks`/`sheets`/`slides`/`rows`) using
  `python-docx` / `openpyxl` / `python-pptx` (imported lazily per format, so a
  partial install reports an honest `DOCUMENT_LIBRARY_MISSING`), then registers the
  bytes through the ONE `ArtifactService` for preview/download (no arbitrary path,
  no macro). `document_create` joins `DOCUMENT_TOOLS` in `agents.py` (previously the
  runtime could only READ these formats). Also added the TS tool label. Native PDF
  is NOT added (chat responses already export to PDF client-side). Tests:
  `python/tests/test_documents_authoring.py` (9). docs updated:
  `docs/harness/document-intelligence.md` (Authoring section),
  `docs/harness/artifact-center.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H195); `test_size_budget.py` `service.py` pin
  ratcheted 1471→1479 for the boot wiring.

- **Chat history: widened the sort/filter dropdown.** It was sized to the tiny
  trigger (`w-(--anchor-width)`), so options looked cramped. `HistorySelect`'s
  popup is now a fixed `w-44` / `min-w-[176px]`. UI-only; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat history: decluttered the controls row.** The group-by toggle was two
  text buttons competing with the tag + sort selects in the narrow sidebar. It
  is now an icon-only segmented control (Clock / Folder, with tooltips +
  `aria-pressed`), and the tag/sort selects are grouped to the right, so the row
  no longer reads as cramped. UI-only; no doc change — `docs/CHANGELOG.md` only.

- **Chat history: replaced the native sort/filter `<select>`s with the shared
  frosted `Select`.** The `Recent` (and tag-filter) dropdown rendered the OS
  popup, which can't adopt the glass design language. Both now use
  `components/ui/select` (frosted `.glass-tooltip` popup) via a small local
  `HistorySelect`; tag filter uses an `__all__` sentinel. UI-only; no doc change
  — `docs/CHANGELOG.md` only.

- **Response engine: killed the recurring producer schema drift (chart/flow/
  citations vanishing as diagnostics).** Three faults were gaps in the
  consumer-side normalizer, not the renderer: `chart` accepted `labels`→
  `categories` but not Chart.js `datasets`→`series`; `citations` accepted
  `name`→`title` but not `label`→`title`; and `tone` was never normalized, so a
  semantic value (`trend-up`, `positive`) — correct for `icon`, invalid for
  `tone` — hard-failed the block because `tone`'s schema default is defeated by a
  PRESENT-but-invalid value. `normalize.ts` now aliases `datasets`→`series`,
  `label`→`title`, and rewrites every `tone` (including nested steps/paths/nodes/
  edges) to the status enum or drops it so the default applies. Root cause also
  attacked at the source: each run that may emit structured blocks now gets a
  live schema digest (exact field names + enum values, generated from the TS
  contract over the bridge) appended to its system prompt via
  `response_schema_prompt_block` composed in `graph.execute_run`, so the model no
  longer has to remember to call `response_block_schema` and cannot guess a
  drifted field. Regression tests pin the exact drifted payloads
  (`contract-blocks.test.ts`, `test_response_tools.py`). Docs updated:
  `docs/interactive-response-engine.md`.

- **Chat history: added a Date / Folders "Group by" toggle; date is now the
  default.** The sidebar chat list (`chat-history-panel.tsx`) previously grouped
  only by folder. Added `ChatGroupMode` + `groupConversationsByDate` /
  `dateBucket` to `chat-organization.ts`, bucketing by last-activity whole
  calendar day (today, yesterday, last week, last month, older); pinned stays a
  separate section. The choice persists in `localStorage`
  (`chat_group_by_v1`). New `sidebar.groupBy|groupDate|groupFolders|date*` i18n
  keys. Behavior/UI change, view contract extended additively (`bucket?` on
  `ChatHistoryGroup`) — no architecture/data-shape doc change —
  `docs/CHANGELOG.md` only.

- **Chat: removed the assistant avatar (sparkles) bubble from messages.** The
  `w-8 h-8` primary-tinted Sparkles badge above every non-compact assistant reply
  in `chat-history.tsx` is gone, decluttering the transcript; the now-unused
  `Sparkles` import was dropped. Layout-only change; no doc change —
  `docs/CHANGELOG.md` only.

- **Chat: computed-result and research-provenance panels now share a 50/50 row.**
  `ComputedResultPanel` ("This number has no record…") and
  `ResearchEvidencePanel` ("Sources consulted") were stacked full-width because
  the assistant message column stretches to the chat width (`chat-history.tsx`).
  Wrapped both in a `flex md:flex-row` row so each child is `md:w-1/2`, stacking
  on mobile; zeroed the panels' own top margins via `[&>div]:mt-0` so they align.
  Layout-only change; no doc change — `docs/CHANGELOG.md` only.

- **Fix: charts (and the whole client bundle) failed to render — repaired a
  non-UTF-8 source file.** `src/lib/journal/analytics/advanced.ts` contained stray
  Windows-1252 bytes (e.g. `0x97` for an em-dash) that are invalid UTF-8, so
  Next/SWC refused to build the module (`stream did not contain valid UTF-8`) and
  every route returned HTTP 500 — no client JS loaded, so response charts, which
  render client-side, showed nothing. Re-encoded the invalid bytes to their
  intended UTF-8 characters (no content loss; 0 replacement chars), verified the
  file is now valid UTF-8 and `/login` returns 200. A repo-wide scan found this as
  the only invalid-UTF-8 source file. no doc change — encoding repair of an
  untracked file; `docs/CHANGELOG.md` only.

- **Fix build: repaired invalid UTF-8 in `src/lib/journal/analytics/advanced.ts`.**
  Three lone Windows-1252 bytes (`0x97`, `0xD7`) made Webpack fail with "stream
  did not contain valid UTF-8". Replaced them with their proper UTF-8 equivalents
  (em dash `U+2014`, multiplication sign `U+00D7`); file now decodes cleanly.

- **Interactive response: new dependency-free `flow` block + route flows off
  Mermaid.** Added a branching HTML/CSS process block (`flow`: ordered `steps` as
  frosted cards joined by CSS connectors, each step optionally branching into
  parallel `paths` as smaller cards; `direction` `LR`/`TB`) — distinct from
  `workflow` (strictly linear) and `diagram`/`node_graph` (SVG graphs). Wired
  through `contract.ts` (schema + limits + union + types), a new
  `flow-block.tsx`, the `response-view.tsx` registry, and `normalize.ts`
  (`process_flow`/`pipeline`→`flow`, `process`→`workflow`, `flow_graph`→`diagram`;
  `stages`→`steps`, `branches`/`options`→`paths`, bare-string step coercion, nested
  icon canonicalization). The agent prompt (`prompts.py`) now reserves `mermaid`
  for sequence/ER/class/gantt and directs flow/flowchart answers to the native
  `diagram`/`flow`/`workflow` blocks, so the heavy `mermaid` bundle stays unloaded
  for ordinary process answers (prompt held at/under its ceiling). Tests:
  `contract-blocks.test.ts` + `render.test.tsx`; `npx tsc --noEmit` clean; TS suite
  2874 passing. docs updated: `docs/interactive-response-engine.md` (block
  catalogue, aliases/field/icon notes, Mermaid routing, BLOCK-010),
  `docs/CHANGELOG.md`.

- **Trading Journal: closed the biggest feature gaps (fees, accounts, filtering,
  export, depth analytics, journaling).** Additive schema work on `Trade`
  (`commission`, `fee`, `grossPnl`, `grade`, `checklist`) and `TradingAccount`
  (`broker`, `archived`); `pnl` is now NET (gross − commission − fee) via
  `computeTradeMath`. New APIs: `GET|POST /api/journal/accounts`,
  `PATCH|DELETE /api/journal/accounts/[id]`, `GET|PATCH /api/journal/profile`,
  `GET /api/journal/trades/[id]/executions`, `GET|POST /api/journal/entries`,
  `PATCH|DELETE /api/journal/entries/[id]`, `GET /api/journal/export` (CSV).
  UI: advanced Trades filters + column sort + pagination + CSV/PDF export;
  Journal **Settings** dialog (profile + trading-account CRUD); currency equity
  toggle on Overview; depth charts (monthly returns, rolling win-rate, MAE/MFE
  scatter, confidence scatter, holding-time buckets); free-form **Notebook** tab;
  per-trade grade + pre-trade checklist + inline tags in the trade form;
  execution-history panel in trade detail. The profile's
  `accountSize × riskPerTrade` now drives currency equity and the discipline risk
  rule. Tests: journal suite 50 passing; `npx tsc --noEmit` clean. Deferred
  (still open): true open-position/unrealized-P&L (needs nullable exit),
  partial-exit entry, live broker sync, watchlist/alerts. docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Bots now keep PRIVATE per-conversation long-term memory.** A bot chat and
  each group-room member turn own a durable-memory bucket keyed by the
  conversation id (`bot-<id>` / `group-<gid>-<botid>`), isolated from every other
  conversation/bot and from ordinary chat — the capability the Bots UI previously
  declared unavailable. Implemented as an additive `conversation` scope on the
  EXISTING `MemoryRecord` (no new database/table/column): a new
  `decision.resolve_owner_scope` normalizes the owner at the ONE write gate, and
  `retrieval._scope_authorized` lets a conversation read only its own bucket, the
  signed-in user's own rows and `general`. Opt-in is explicit via
  `memoryScope:'conversation'` → `RunRequest.conversationId`; ordinary chat is
  unchanged. Scheduled bot runs bind the same `bot-<id>` bucket, `bot_delete`
  archives it, and the bot Memory panel lists it with a "Forget this
  conversation's memory" control. Tests:
  `python/tests/test_memory_conversation.py` (+9). ADR-044 / ADR-H194.
  docs updated: `docs/harness/{memory-skills-evolution-plan,memory-maturity-baseline,automation-engine,decisions}.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.

- **Agent Workspace Context panel (right sidebar) shows its data properly.** Three
  fixes: (1) the panel body now scrolls, so the Context tab's gauge/stat
  grid/source list are no longer clipped by the docked column's
  `overflow-hidden` (`workspace.tsx`); (2) the default/open-panel fallback is
  `context` — the 2026-10-09 ordering change missed the localStorage fallback, so
  a fresh profile still opened on Output (`store.ts`); (3) the live store folds
  the front-door terminal `client.final` record into a `run_record` event
  (normalize → shared `applyRunRecordPatch` in `reducer.ts`, also now used by
  `history.applyRunRecord`) and the stream route forwards the record's
  token/step counts, so provider/model/tokens/steps/context window fill in after
  a live run instead of staying "Not available". Unreported (zero-only) token
  reports no longer render as a fabricated `0`. Tests:
  `agent-workspace.test.ts` (+5), `agent-workspace-reachability.test.ts` (+1).
  docs updated: `docs/agent-workspace.md`, `docs/CHANGELOG.md`.

- **Notifications now show red ON THE BROWSER TAB — the header bell and its
  panel are removed.** The operator asked for the signal on the real browser
  tabs, not an extra in-app icon, so the notification center's header UI is
  gone and a new root-mounted `src/lib/notifications/tab-indicator.tsx` turns
  the ledger into a browser-tab signal while anything is unread: (1) the
  document title carries the count (`(3) BlackEclipse — …`, `(99+)` cap; pure
  helpers in `title.ts`), (2) the favicon becomes a red-badged copy of the
  LIVE icon (canvas-composited, so a theme-customized favicon is respected;
  plain icon restored at zero), (3) `navigator.setAppBadge` where supported.
  The theme store now composes its branded title through `composeDocumentTitle`
  so an unread count is never silently dropped by a branding write. Removed as
  irrelevant: `components/layout/notification-center.tsx` (bell + glass panel,
  mark-all-read, per-entry dismiss) and the store's `markAllRead`/`remove`
  actions. Unchanged: sidebar tab badges, toasts, the loud `taskdone` alarm,
  and the task/bot-run watchers. Tests: `title.test.ts` (+7). Also rotated the
  `2026-10-07` section into `docs/changelog/2026-10.md` (rolling-window
  policy; the active file is back to 7 dated sections).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Notification sounds are now an explicit choice in Settings.** The
  notification cues (`taskdone`, `notification`) moved out of the generic cue
  list into a dedicated **Notifications & alarms** card in Settings › Sound —
  per-cue on/off, volume, test and custom clip, with honest copy that the
  task-done alarm plays even while UI sounds are off (`sound-settings.tsx`,
  `NOTIFICATION_CUES` split). The same two toggles are mirrored in
  Settings › Alerts › Notification sounds (same `useSoundStore` per-cue prefs,
  no new state), so the decision sits next to the channels it applies to.
  UI-only; no contract change. Verified: `npx tsc --noEmit` clean; vitest
  270 files / 2861 passed.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

## 2026-10-13

- **Production blocker fixed: the sign-in page now exists — enabling auth used
  to lock the operator out at a 404.** `HARNESS_AUTH=required` (or a
  public/production bind) redirects every page to `/login`, and
  `docs/harness/authentication.md` names `src/app/login/page.tsx` as the UI, but
  the page had never shipped. Shipped `src/app/login/`: a standalone
  frosted-glass page — server shell (`page.tsx`) + `login-form.tsx` (session
  resolution, submit, post-setup sign-in) + presentational `auth-panel.tsx`
  (setup / login / checking / secret-missing states) + pure `safeNext` for the
  middleware's `?next=` return path (rejects absolute, protocol-relative and
  `/login` loops). It shows first-run SETUP when no account exists, LOGIN
  otherwise, auto-redirects when auth is off or already signed in, and fails
  closed with operator guidance when `HARNESS_AUTH_SECRET` is missing. Verified
  end-to-end against a production `next start` with a throwaway auth DB:
  `setupRequired` → `POST /api/auth/setup` 200 → `POST /api/auth/login` 200
  (cookie) → authed `/api/stocks` 200, unauthed 401, `/login` 200. Tests:
  `src/app/login/next-path.test.ts` + `src/app/login/auth-panel.test.tsx`.
  no doc change — authentication.md and NAVIGATION.md already documented the
  page; the code now matches them.

- **Register closeout — market-data windows, series freshness, the stale vault,
  and a live P/E route (MKT-2/3/4, VAULT-1, DATA-1).** History windows are honored
  end-to-end: the Yahoo adapter sends `period1`/`period2` (bare dates padded to
  end-of-day) and picks the smallest covering `range` for the batched bridge,
  whose rows are filtered to the window, at BOTH the market gateway adapter
  (`market/providers/yahoo.ts`) and the `price_history` capability
  (`data-bridge.ts`); the retrieval path no longer lets the default `period`
  overwrite an explicit start (`retrieval_tools.py` gains `end`,
  `structured._params_for` passes the window through). Series freshness is
  judged by COVERAGE of an explicit window (7-day cadence otherwise; the 6h
  bar-timestamp ceiling rejected every daily series after the last close), and
  the misleading "WEB is not eligible" rejection is reported only when a WEB
  outcome actually ran (`authority.py`). `get_market_data` text now shows the
  latest bars inline and says how many `rows` carries (was a bare "11,551 bars,
  no rows"). The statements cache is refreshed when older than 7 days and a
  failed refresh serves the persisted payload with `stale: true` +
  `cacheAgeDays` (never a disguised fresh timestamp); AAPL was reseeded live
  (8 periods, P/E 39.09 — was FY2018/19). `fundamentals` now reports a
  `valuation` block (P/E, forward P/E) with LIVE/JDDS provenance, and
  `get_fundamentals(refresh=true)` is the live-ratio route. Tests:
  `market/providers/yahoo.test.ts` (new), `data-bridge-phase2.test.ts`,
  `phase4-routes.test.ts`, `data-bridge-history.test.ts`,
  `test_research_data_tools.py`, `test_source_authority.py`,
  `test_retrieval_scenarios.py`. The statement-cache shaping + live profile
  helpers were extracted to `data-bridge-statements.ts` (size ratchet;
  `data-bridge.ts` re-pinned 1379→1400 for the valuation block + imports).

- **Crypto identifiers and volumes are honest (CRYPTO-1/2).** A bare base
  (`BTC`, `SOL`) now classifies as the USD-quoted spot pair in BOTH classifiers —
  TS `instrument-identity.classifyIdentifier` (bare bases fell through to equity
  and the live path fetched the WRONG instrument: bare `BTC`/`ETH` are the
  Grayscale mini-trust ETFs on NYSE Arca, observed live at 36.77/23.91) and
  Python `retrieval/structured.is_crypto` (so routing sends bare bases to the
  crypto source and never to the vault). Binance's two 24h volumes are carried
  explicitly labelled — `volume` = quote notional, `volumeBase` = base-asset
  units — instead of one unlabelled "shares" number. Tests:
  `instrument-identity.test.ts`, `connectors.test.ts`,
  `data-bridge-gateway.test.ts`, `test_provider_gateway.py`.

- **Finance computation asks enable the analysis sandbox; search tools got more
  usable (CALC-1, TOOL-2/3).** The data-task vocabulary now covers computation
  asks — verbs `analyze/analyse/backtest/optimize/…`, metric objects `ytd`,
  `return`, `performance`, `cagr`, `exposure`, `holdings`, and the phrases `an
  analysis`, `analysis of`, `a report on|of` — so `analysis_run` is no longer
  refused with `ANALYSIS_NOT_ENABLED` for a YTD/report request (the fixtures that
  pinned "not_code" now assert "never code_change"; `run a report…` is a
  `data_task`). `search_text`/`workspace_search` accept a single FILE path
  (searching it directly instead of raising `NOT_A_DIRECTORY`), and
  `contextLines` accepts 0-20. Tests: `test_code_request_intent.py`,
  `test_fs_search_index_watch.py`, `test_code_tools.py`.
  docs updated: harness/market-data.md, harness/architecture.md,
  harness/code-filesystem.md.

- **The response-format read-back is reachable end-to-end again (BR-1), and it can
  no longer crash the route.** `response_contract` was dispatched
  (`data-bridge.ts`) and type-declared but missing from the HTTP capability
  allowlist (`src/app/api/harness/data/route.ts`), so every
  `response_block_schema` / `response_validate` call returned 400 → Python
  reported `bridge HTTP 400` / UNAVAILABLE and the agent could not verify the
  icon vocabulary. Two fixes: the allowlist entry, and a server/client split of
  the icon vocabulary — the schema read-back now imports
  `lib/response/icon-vocabulary.ts` (pure keys + `canonicalIconKey`), because
  importing `lib/response/icons.ts` pulls the Phosphor React set into the
  react-server bundle and crashes the route with `react.createContext is not a
  function` (found by probing the real dev server after allowlisting).
  `icons.ts` keeps the client component map, type-pinned to the vocabulary by
  `satisfies Record<ResponseIconKey, LucideIcon>`. The route also returns the
  caught error detail in development only. Verified against the running dev
  server: schema → 200 with exact fields + 42 `iconKeys`; validate → per-block
  verdicts (`TrendUp` + numeric-icon payload is ok; a bad gauge reports
  `gauges.0.value`). Tests: new `src/app/api/harness/data/route.test.ts`
  (allowlist + cross-origin + unknown-capability), `data-bridge.test.ts`
  dispatch case. Also TOOL-1: `search_text` summaries now name the match mode
  (literal/regex) and a literal zero-match says it is not proof of absence
  (`test_fs_search_index_watch.py`).
  docs updated: interactive-response-engine.md, NAVIGATION.md.

- **Agent `icon` fields now render: the vocabulary is taught, spellings are
  canonicalized, and a bad icon can no longer drop a block.** Three gaps closed.
  (1) The producer is told the vocabulary: the "Structured answers" prompt lists
  the 42 semantic keys, and `response_block_schema` now returns the LIVE
  `iconKeys` (derived from `lib/response/icons.ts`, cannot drift) which the
  Python formatter prints with each schema lookup. (2) `canonicalIconKey` in
  `icons.ts` resolves case/separator spellings (`TrendUp`, `trend_up`, `TREND
  UP`), common synonyms (`graph`, `money`, `alert`) and the emoji producers emit
  (`📈`, `⚠️`) to the canonical key; `normalize.ts` applies it to all six
  icon-bearing item arrays (infographic cards, workflow stages, action_group
  actions, stat_hero stats, ranked_list items, badge_row badges), including
  nested blocks. (3) A NON-STRING icon (number/object/array) now has the field
  dropped before validation instead of failing the whole block — a misspelled
  icon costs at most the glyph, never the card. Tests: `contract-blocks.test.ts`
  (+5), `response-bridge.test.ts` (+1), `test_response_tools.py` (+1).
  docs updated: interactive-response-engine.md, NAVIGATION.md.

- **Market Discover no longer surfaces a `Console TypeError: Failed to fetch`
  when the dev server is recycled mid-request.** Root cause: the Next dev-server
  child process was killed under memory pressure (6.6 GB RSS, ~0.8 GB free) while
  `/api/stocks` was in flight, so the request never got a response. New
  `src/lib/fetch-retry.ts` (`fetchWithRetry` + `logHandledFetchFailure`) retries
  transport-level failures twice with backoff (HTTP error statuses are returned
  as-is, aborts are never retried) and logs a handled outage as a warning instead
  of `console.error`, so the dev error overlay only fires for real bugs. Wired
  into the screener/dashboard fetches of `market-overview.tsx`,
  `use-market-tabs.ts` and `use-global-markets.ts`; tests
  `fetch-retry.test.ts` (+7). `python/harness/service.py` re-pinned 1469→1471 to
  the measured tree (pre-existing in-flight growth on the shared working tree;
  this change touches no Python file).
  no doc change — client-side resilience fix; no contract or architecture change.

- **The probe was answered from the real run record: the response FORMAT was
  never broken — one block shape was.** Validating every block of the labelled
  8-block probe run (`run_e24e0109…`) and the 22:00 Sazgar answer against the real
  contract: 7/8 probe blocks pass (markdown `body`, mermaid `code`, callout
  `variant`+`body`, key_value `items`, data_table string-columns were all already
  accepted), and the Sazgar answer's 9 blocks all pass. The single failure was
  `badge_row` with BARE STRINGS (`badges: ["PROBE-6 — badge_row"]`). A badge's only
  content is its label, so `normalize.ts` now coerces a bare-string badge to
  `{label}` (test in `contract-blocks.test.ts`). With this, all 152 blocks in the
  25 most recent fenced runs validate.
  docs updated: interactive-response-engine.md.

- **The model can now VERIFY the response format it writes: schema lookup +
  pre-send validation (read-back).** The agent's own diagnosis ("I am not given
  each block's field names… I can write into a format I cannot verify") is now
  closed by two read-only tools bound to Eclipse:
  `response_block_schema` (exact field names per type, derived LIVE from the zod
  contract — it cannot drift) and `response_validate` (runs the renderer's own
  parser over a drafted fence or bare JSON; returns per-block errors so a drifted
  block is fixed in-turn). Backed by a new `response_contract` bridge capability
  in `src/lib/harness/response-bridge.ts` (also exempted from the health ledger);
  Python side `python/harness/response_tools.py` + allowlist in `agents.py`;
  a missing bridge reports UNAVAILABLE. Tests `response-bridge.test.ts` +
  `test_response_tools.py`. `data-bridge.ts` re-pinned 1377→1379 for the two-line
  dispatch; `graph.py` re-pinned 2043→2049 for unrelated in-flight shared-tree
  growth (this change touches no part of graph.py).
  docs updated: interactive-response-engine.md, NAVIGATION.md.

- **Code changes are now visible as they happen (inline change cards).** The run
  stream is content-free except for one addition: `code.patch.applied` and every
  fs write event (`fs.*`, `previews[]`) now carry a bounded, redacted unified
  diff (`code/events.py::diff_event_payload`, 12k cap, secret-shaped spans
  scrubbed; `code/patch.py` computes per-op previews from before/after text).
  The chat maps them to per-file change cards with `+N/−M` and the colored diff
  (`src/components/chat/change-cards.tsx`, rendered from `chat-history.tsx`,
  carried on `AssistantTurn.changes` / `Message.changes`); the Agent Workspace
  Changes panel expands the same preview inline. A capped preview is flagged,
  never silent. Tests: `python/tests/test_change_event_previews.py` +
  `test_code_patch.py` + `events.test.ts` + `agent-workspace.test.ts`.
  docs updated: harness/architecture.md, agent-workspace.md.

- **A run can no longer hang forever at a model call or a tool call.** Live
  evidence: `run_23de73de…` emitted `model.requested` and then nothing for 10+
  minutes — `asyncio.wait_for` waits for cancellation to COMPLETE before
  raising, so a provider adapter that swallows `CancelledError` defeats the
  timeout entirely. New `python/harness/async_timeout.py` (`await_bounded`)
  races the work against a plain timer and raises at the deadline without
  waiting for cancellation; outer cancellation still cancels the inner task and
  abandoned work is drained. Wired into `model_stream.py` (the run now fails
  with `PROVIDER_TIMEOUT` at the declared budget; the abandoned stream is
  flagged so it stops emitting deltas) and `ToolRegistry.execute` (a
  cancellation-swallowing handler now returns `TOOL_TIMEOUT`). Tests
  `test_async_timeout.py` + a `test_tools.py` case — both hang with the old
  implementation.
  docs updated: harness/architecture.md.

- **A stalled run now always reaches a terminal state (watchdog).** Belt and
  suspenders beside the hard deadlines: `python/harness/run_watchdog.py` sweeps
  every 30s; any run in `created`/`running` silent past its own agent model
  budget (`runTimeoutMs` + 60s grace — 180s for Eclipse Agent, 660s for Code
  Agent) is marked failed (`RUN_STALLED`) with a durable `run.failed` event, its
  SSE stream is closed and its task cancelled, so the chat cannot spin forever
  even if a future subsystem strand misbehaves. Runs waiting on a user approval
  (`approval.requested`) are exempt. Wired in `boot.py` (start/stop). Test
  `test_run_watchdog.py`.
  docs updated: harness/architecture.md.

- **Bridge timeouts refined to per-class budgets (supersedes the earlier
  blanket-8s bridge entry in today's section).** 8s applies to structured/vault
  reads only; capabilities that
  fetch the public web (search/extract/education/image) keep a 20s class under
  the 30s research budget, so research quality is not cut to fix the fast path.
  Retry narrowed to `ConnectError` only (instant dev-server-restart refusal) — a
  timeout is never retried, so the worst-case wait is one per-class timeout and
  always fits the caller's tool budget. `test_bridge.py` pins both invariants.
  docs updated: harness/architecture.md (bridge.py row).

- **Eclipse answers no longer turn into parse errors: contract leniency for
  observed producer drift.** Live runs showed 18/233 recently produced
  `eclipse-response` blocks failing validation — every markdown/callout block
  whose prose field was named `body` (3rd observed spelling after
  `content`/`text`), `gauge`/`ranked_list` blocks that correctly said
  `"unavailable": true` with no data points, `key_value` values over the
  120-char numeric bound when a source/citation was attached, and one
  `chart_type` spelling. `src/lib/response/normalize.ts` (extracted from
  `contract.ts`, which was at its size ratchet; re-exported for callers) now
  accepts `body`→`markdown` (also the `mermaid` body), `chart_type`→`chartType`,
  and 500-char `key_value` values; the figure family (`stat_hero`, `gauge`,
  `comparison_grid`, `ranked_list`, `badge_row`) accepts a block-level
  `unavailable` with an absent/empty data array and
  `src/components/response/visual-blocks.tsx` renders an explicit UNAVAILABLE
  state with the producer's explanation instead of an empty figure. A settled
  malformed fence now also offers a "Show the raw content" disclosure
  (`response-fence.tsx`) so an unparseable body is never lost. Re-validated
  against the real 233-block sample from `agent-memory.db`: 0 failures (was 18).
  Tests `contract-blocks.test.ts` (+5). `npm run test` + `npx tsc --noEmit`
  pass. docs updated: interactive-response-engine.md.

- **Data-bridge failures fail fast instead of timing out tools.** `_HttpDataBridge`
  (now `python/harness/bridge.py`, extracted from `service.py` for its size
  ratchet and re-exported as `_HttpDataBridge`) drops the read timeout 20s→8s
  (below the market tools' own budgets) and retries ONCE on transient connection
  errors (dev-server restart → `All connection attempts failed` was the top
  recorded retrieval failure), so a tool returns a structured UNAVAILABLE
  instead of being killed as `TOOL_TIMEOUT`. docs updated:
  harness/architecture.md.

- **Orphaned runs no longer spin forever after a restart.** The runtime executes
  runs in-process, so runs left `created`/`running` by a dead process could never
  finish (11 such rows were live in `agent-memory.db`). `run_startup_maintenance`
  now calls `fail_orphaned_runs` (`python/harness/run_recovery.py`, a new module so
  `persistence.py` stays within its size ratchet): each orphan becomes `failed`
  with code `RUN_ORPHANED` plus a durable `run.failed` event, so every streaming
  client sees a terminal state. Test `python/tests/test_run_recovery.py`.
  docs updated: harness/architecture.md.

- **Bot-mode UI fixes (six issues).** `src/components/bots/bot-chat.tsx`:
  "Run now" now gives visible feedback (a run-status note that says the run was
  queued, auto-clearing) instead of silently enqueuing, and shows a reason in the
  tooltip when the bot is not active; the pencil edit button got a proper 24px
  hit target with cursor + press feedback; the composer no longer draws a
  focus-visible highlight ring; message date/time now appears only on hover or
  keyboard focus instead of always. `src/components/bots/bot-detail.tsx`: the
  Overview tab is regrouped into Identity and Activity & health cards, the header
  actions collapse behind a "More" menu (duplicate/disable/delete) leaving one
  primary Run now path, and Memory renders as a card.
  `src/components/screens/stock-chat.tsx`: the floating Assistant dock is now
  hidden on the bots tab (it already has its own composer) in addition to the
  chat tab. Added i18n keys (`bots.runQueued`, `bots.runNowBlocked`,
  `bots.detail.identity`, `bots.detail.activity`, `bots.successRate`).
  `npm run test` (vitest) and `npx tsc --noEmit` pass.
  no doc change — UI behavior/style fix with contracts intact.

- **Bot detail: purpose text no longer collapses into one blob.** A bot whose
  purpose/objective is a long multi-line brief rendered as a single run-on
  paragraph under the name (HTML whitespace collapsing). `bot-detail.tsx` now
  clamps the header description to two lines, and the Overview tab's Purpose is
  a full-width block with `whitespace-pre-wrap` so its line breaks survive.
  no doc change — UI formatting only.

- **Bot detail: tabs replaced by one scrollable column.** The drawer's seven
  tabs felt cramped, so `bot-detail.tsx` now stacks every section (Overview,
  Instructions, Schedule, Capabilities, Memory, Run history, Settings) in a
  single scrolling column with a titled divider between sections. Removed the
  `TabBar` usage and the tab state. no doc change — UI layout only.

- **Bot detail: sections are now collapsible; run-history text wraps.** Each
  `SectionBlock` in `bot-detail.tsx` is a dropdown (chevron header, Overview open
  by default). `run-history.tsx` gained `min-w-0` / `break-words` / `flex-wrap`
  on run labels, outcome reasons, timeline events and deliveries so long text no
  longer overflows or breaks mid-layout. `npx tsc --noEmit` clean.
  no doc change — UI layout only.

- **Run history reworked to a stacked layout.** The two-column run
  list + detail grid could crush text inside the narrow drawer. `run-history.tsx`
  now stacks the list above the detail, rows are full-width with plain borders
  (no nested glass blur), and every value wraps. `npx tsc --noEmit` clean.
  no doc change — UI layout only.

- **Bot chat bubble slimmer; timestamp moved below.** The user/error bubble had
  the timestamp inside it, reserving a second line and making the bubble tall.
  `bot-chat.tsx` `ChatBubble` now wraps the bubble in a column and puts the time
  below the bubble (aligned to its edge), revealed on hover/focus. The bubble
  hugs its text. `npx tsc --noEmit` clean. no doc change — UI layout only.

- **Editing a bot opens a proper dialog.** The bot-chat pencil used to swap the
  header into an inline name/purpose form; it now opens a modal `Dialog` (name +
  purpose fields, Save/Cancel) in `bot-chat.tsx`, and the header stays as the
  static identity banner. `npx tsc --noEmit` clean.
  no doc change — UI layout only.

- **Bot composer upgrade: stop / edit / regenerate / copy / auto-grow.**
  `bot-chat.tsx`'s bare textarea is now a real composer. While a reply streams,
  send becomes **Stop** (aborts via the run's AbortController, keeping the partial
  text). Hovering any message reveals actions: **Copy** everywhere, **Edit** on
  user messages (truncates the thread there and loads the text back into the
  composer), and **Regenerate** on the last bot reply. The textarea auto-grows to
  200px, sends on Enter (Shift+Enter for newline, IME-safe), and the footer shows
  a keyboard hint. Added i18n keys `bots.chat.{stop,hint,copy,copied,regenerate}`.
  `npx tsc --noEmit` clean; i18n + bots vitest pass.
  no doc change — UI behavior only.

- **Finance starter pack: six bots + a "Markets Desk" group room.** New
  `src/lib/bots/finance-bots.ts` defines six scheduled finance bots (Market
  Brief, Watchlist Sentinel, Portfolio Risk Review, Earnings Radar, Macro Pulse,
  Data Quality Auditor) with real instructions (cite sources / UNAVAILABLE, never
  fabricate). `seedFinancePack()` creates any missing bots through the real
  `/api/automations` API (idempotent by name) and writes a client-side group of
  all six; `useSeedFinancePack()` powers an "Add finance starter pack" button in
  the Bots empty workspace (`bots-screen.tsx`) and the Bots sidebar header.
  Added i18n keys `bots.finance.*` and a unit test (`finance-bots.test.ts`).
  `npx tsc --noEmit` clean; vitest pass. no doc change — new feature module, no
  contract/architecture change.

- **Finance starter pack: discoverability fix.** The labeled seed button only
  lived in the empty workspace, so once a user had any bot it never appeared and
  the pack looked broken. `bots-sidebar-panel.tsx` now shows a labeled "Add
  finance starter pack" button (both expanded and collapsed) that hides only once
  the group room exists. Also seeded the six finance bots into the local runtime
  so they appear on refresh. `npx tsc --noEmit` clean.
  no doc change — UI discoverability fix.

- **Group chat: each bot answers separately; composer gains stop + targeting.**
  `group-chat-room.tsx` no longer produces one merged "room" reply — a send now
  runs one agent turn PER targeted member with that bot's own persona/instructions
  (parallel, each streaming into its own message tagged with `authorId`/
  `authorName` and the member's own avatar), so replies are never combined.
  Composer: **Stop** aborts every in-flight member run, textarea auto-grows,
  Enter sends (Shift+Enter newline, IME-safe), and a **"Who answers"** dropdown
  targets Everyone or a single bot. Per-message Copy added; timestamps now
  hover-only. New i18n keys `bots.groups.{answering,stop,audience,audienceHint,everyone}`.
  `npx tsc --noEmit` clean; i18n + bots vitest pass.
  no doc change — UI behavior only.

- **Group chat header gains Run / Pause-All / Scheduler / Settings.** The group
  room only had Delete; the per-bot controls had no group equivalent. The header
  now mirrors BotChat: **Run now** runs every member's automation, a
  Pause-All/Resume-All toggle pauses or resumes all members (state-aware), a
  **Scheduler** button opens the right-docked scheduled-jobs rail (shared
  `useWorkspaceStore`), and **Settings** opens a new
  `group-settings-dialog.tsx` (rename, photo, add/remove members 2–6, each member
  showing its real state + schedule). Added `setMembers` to the groups store and
  i18n keys `bots.groups.{settings,settingsTitle,settingsHint,removeImage,pauseAll,resumeAll,ranAll,pausedAll,resumedAll}`.
  `npx tsc --noEmit` clean; i18n + bots vitest pass.
  no doc change — UI feature, no contract change.

- **Composer feature pass (frontend), benchmarked against Grok/Hermes-style
  chats.** Bot composer (`bot-chat.tsx`): added inline **model selector**
  (reuses `ModelSelector` + `useChatModel`, passes `model` to the run), thumbs
  **feedback**, and **retry** on error turns (alongside the existing stop/edit/
  regenerate/copy). Group room (`group-chat-room.tsx`): **@mention autocomplete**
  (typing `@` lists members; a mention routes the turn to exactly those bots over
  the audience selector), **edit/resend**, **regenerate** per reply, **retry**,
  thumbs **feedback**, and per-member avatars on replies. Stores gained
  `feedback` on messages and `setMessages` for group truncation; exported
  `ModelSelector`. New i18n keys `bots.chat.{retry,good,bad}`.
  `npx tsc --noEmit` clean; i18n + bots vitest pass.
  Deferred (next): attachments-as-context (needs provider file threading),
  context meter (no per-run usage surfaced to the bot path), voice (needs STT).
  no doc change — UI behavior only.

- **Construction benchmark R3-08 — the 16 master scenarios, with completion and
  recovery now gated (ADR-H183).** New
  `python/harness/evaluation/datasets/construction_v1.json` runs all 16
  construction scenarios (working API, alternative route, missing fields,
  alternative acquisition route, confirmed zero, fixable script error, missing
  dependency, dirty records, wrong calculation caught, stale conflict, invalid
  chart payload, delivery failure, unauthorized attempt, budget kill, partial
  completion, end-to-end chat) through the REAL `execute_run` graph as
  deterministic scripted traces. Five new graders — `recovery`, `honesty`,
  `provenance`, `artifact`, `response` — measure recovery success + redundant
  retries, false-success/unsupported claims + named gaps, source use+citation
  with `collected ≠ verified`, artifact delivered-or-honestly-failed, and a
  surviving answer with a decodable chart fence. `scoring.py` now gates
  `task_success >= 0.9` and `recovery_success >= 0.85` (safety/hallucination
  unchanged; measured offline: full gate tasks=47, `task_success=1.0`,
  `recovery_success=1.0`, `safety_score=1.0`, `hallucination_rate=0.0`; the
  construction suite alone 16/16). Eval tools now record an environment error as
  a FAILED tool call and add bounded `eval_run` (killed on timeout) +
  `eval_response_check`; `scripts/test-evals.js` runs the construction suite as
  a named gate. docs updated: `docs/harness/decisions.md` (ADR-H183),
  `docs/harness/agent-evaluation.md`, `docs/harness/construction-first-audit.md`
  (R3-08 ✅ with measured numbers), `docs/NAVIGATION.md`.

- **Registry-visibility scan — every registered tool is reachable or deliberately
  operator-only (ADR-H184).** New `python/tests/test_registry_visibility.py`
  builds the production registry (service constructor + boot-only
  recovery/orchestration/a2a/fabric registrations into a throwaway registry),
  mirrors the resolver's dynamic MCP/plugin expansion, and asserts the invisible
  set equals a pinned 36-name `DELIBERATE_INVISIBLE` set (recovery/artifact/fabric
  admin, parallel-execution primitives, operator context, cluster/infra
  mutations) with **zero ghosts** (no allowlisted-but-unregistered tool). The
  scan found 5 accidentally-invisible tools, now allowlisted beside their
  siblings: `git_tag_show` (`CODE_AGENT_TOOLS` + chat profile),
  `runtime_metrics_history` (`ECLIPSE_AGENT` + `CODE_AGENT_TOOLS` + chat),
  `workspace_graph`/`workspace_start`/`workspace_stop` (`CODE_AGENT_TOOLS` +
  chat, the writes narrowed at `plan_only` like `runtime_start/stop`). The exact
  `CHAT_CODE_TOOLS` pin in `test_chat_code_profile.py` was updated.
  docs updated: `docs/harness/decisions.md` (ADR-H184),
  `docs/harness/construction-first-audit.md` (R3-07/R3-08 statuses),
  `docs/CHANGELOG.md`.

- **Price history: direct-chart fallback + `data-bridge.ts` split (ADR-H185).**
  The bridge's deferred second transport landed: when the batched Python
  yfinance bridge is off or returns no series, `price_history` now falls back to
  the DIRECT Yahoo v8 chart request already used by `/api/price-history`
  (new `src/lib/harness/data-bridge-history.ts`, walking the per-market
  `yahooChartCandidates` chain, ≥2 real bars required — never a single point).
  Provider stays `yfinance`; a new `transport` field (`yfinance-bridge` |
  `yahoo-chart`) names the code path and `providerSymbol` echoes the ticker the
  direct transport answered for. To land it without growing the ratcheted
  dispatcher, `data-bridge.ts` was split: health/diagnostics →
  `data-bridge-health.ts`, education/media → `data-bridge-education.ts`, shared
  unavailable helpers → `data-bridge-result.ts`; ratchet re-pinned 1710 → 1377
  (may only shrink). Tests: `data-bridge-history.test.ts` (+3), extended
  `data-bridge-phase2.test.ts` (bridge-first / fallback / both-down); full
  vitest 262 files / 2773 tests, tsc clean.
  docs updated: `docs/harness/decisions.md` (ADR-H185),
  `docs/harness/construction-first-audit.md` (R3-04 status),
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Production readiness closed: end-to-end boot guard + preflight in the
  release gate (ADR-H186).** `deps.deployment_guard()` composes the Python
  bind with the front door's auth mode for the startup log; the harness now
  warns when a public bind is reachable without a login (`HARNESS_AUTH=off` with
  `CRON_SECRET` set — the one combination that used to be silent), when a public
  bind has no operator secret, or when required auth cannot work
  (`HARNESS_AUTH_SECRET` missing → every request 503s); a public bind behind
  front-door auth is an informational notice. The stale "this app has NO
  authentication" boot comment and the contradicting exposure warning text are
  corrected. `scripts/security-preflight.js` joined `check-all.js` and CI
  (advisory on loopback, failing on an exposed misconfiguration; verified:
  local WARN/exit 0, production-without-secrets FAIL/exit 1, production-with-
  secrets OK/exit 0). Verified on this tree: `npm run build` passes (Next.js
  production compile + type check). Tests:
  `test_identity_tenancy_boundary.py` (+4). Explicitly not included: cluster/infra
  deploy mutations stay refused by design, roadmap phases 16–20 remain features,
  container build unverified here (no Docker), live-model eval stays opt-in.
  docs updated: `docs/harness/decisions.md` (ADR-H186),
  `docs/harness/authentication.md`, `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md`.

- **Phase 20 — every capability class is measured or NAMED as not measured
  (W7 slice, ADR-H193).** New `python/harness/code/eval/capabilities.py`: the
  capability-class registry (17 classes — the seven code shapes, the classes
  this round added, and the four it did NOT grade, each unmeasured row stating
  its reason), a runner that grades only through NAMED evidence (in-module
  fixtures driving the REAL modules — acquire budget/writer, automation
  delivery, verify ledger, review rules; `pytest:`/`vitest:` test selectors the
  runner verifies exist; code-eval fixture ids checked against the labelled
  dataset), `MEASURED_BASELINE` + `check_capability_floors` (a measured class
  may not regress to unmeasured). The generated statement gained the "Every
  capability class" section with the published unmeasured count ("4 of 17
  classes are not measured yet") — and the generator's repo-root constant was
  fixed (it pointed one level short, at `python/docs/…`). `scripts/test-evals.js`
  gained the named `capability-class gate` step (`PASS measured=13
  unmeasured=4`; evals re-verified ALL PASS). en.ts gained the 17
  `capability.class.*` labels. Tests: `test_capability_classes.py` (7);
  `test_code_eval.py` statement tests still green. Recorded remaining:
  labelled fixtures for `price_authority`/`promotion`, the bootstrap/Monte-Carlo
  rule fixture, the adversarial safety cases for the new power, and per-class
  threshold tables.
  docs updated: `docs/harness/decisions.md` (ADR-H193),
  `docs/harness/roadmap/phase-20-measuring-all-of-it.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/capability-statement.md`
  (regenerated), `docs/CHANGELOG.md`.

- **Phase 18 — the first FIGURE recipe (W5 slice, ADR-H192).** `drawdown_figure`
  renders a real PNG in the analysis sandbox (Agg backend, no display, no
  network) and writes it through the existing `write_artifact` seam, which now
  accepts BYTES; the Phase-19 ledger then verifies it (exists, digest, size,
  opens as an image) end to end in a real-sandbox test. The allowlist widening
  is NAMED and narrow: `AnalysisRequest.extra_imports` is set only by the
  recipe table (`io`, `matplotlib` — present in the vendored interpreter,
  3.11.2); `check_imports` still refuses reflection, dunders and URL literals,
  and an undeclared source importing matplotlib is refused. A machine without
  matplotlib fails the recipe honestly. Tests:
  `test_analysis_recipes.py` (+1 real render + allowlist assertions; recipe
  count 7→8). Recorded remaining: the figure payload on the run blob, more
  figure recipes, the inline chat renderer. Verified: analysis suites 51 passed.
  docs updated: `docs/harness/decisions.md` (ADR-H192),
  `docs/harness/roadmap/phase-18-visual-output.md`,
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Phase 19 — a produced artifact is verified, and the repo's rules are reported
  (W6/ADR-H191).** `code/verify.py` gains `ArtifactCheck`/`ArtifactRecord`/
  `verify_artifacts` (exists, digest, size, readable, figure-inputs match — a
  check that cannot run is a FAILED record, never an omission), the ledger gains
  bounded artifact + review records (old-row-safe in `to_blob`/`from_blob`), and
  the two new claim classes `artifacts_verified`/`change_reviewed` join the
  existing narrow, negation-guarded patterns — an unbacked "the figure is
  intact" or "I reviewed the change" is marked `[UNVERIFIED …]` by the ONE
  enforcement path. `analysis_tools.py` records the artifact checks after an
  analysis. New `code/review.py` (the six-rule table: new-module-reachable,
  size-ratchet with pins read from BOTH ratchet files, string-is-key,
  protected-path BLOCKING and proven to agree with `policy.is_protected`,
  doc-obligation, test-touched; unevaluable rules land in `unevaluated`, never
  clean) + the read-only `review_change` tool (`code/review_tools.py`, wired
  from `service.py`, allowlisted on the code agent + chat profile, records the
  review on the ledger). `mistakes.py` gains the four categories the checks
  emit; the CODE-agent prompt states that artifact/review sentences are checked;
  the chat panel renders artifact rollups + review findings (`code.proof.*`
  keys). Tests: `test_claim_classes.py`, `test_artifact_verification.py`,
  `test_change_review.py` (24), updated `test_chat_code_profile.py`. Verified:
  targeted suites 468 + 24 passed; `npx tsc --noEmit` clean; panel/vitest green.
  Recorded: the figure payload itself is phase 18 (still open).
  docs updated: `docs/harness/decisions.md` (ADR-H191),
  `docs/harness/roadmap/phase-19-self-verification.md`,
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Bulk acquisition — first slice (W3/ADR-H190): declared sources, a Python
  budget, files with a manifest.** New `python/harness/acquire/`: a declared
  source registry (daily price history → `price_history`, economic series →
  `macro_series`, annual company statements → `sec_filings`; each row names its
  capability, CLOSED parameter set, CSV columns, licence and attribution — and
  `registry_issues()` fails an incomplete row), an `AcquisitionBudget` beside
  `ResearchBudget` (calls/rows/bytes/seconds, enforced in Python), a
  ceiling-enforcing CSV writer whose row count equals the real file, and the
  `acquire` tool over the ONE read-only bridge (no new egress; `research/`
  untouched). It writes `<source>_<stamp>.csv` + a manifest under the run's
  artifact directory; a partial pull is always marked partial with a plain
  reason. `data.collect` is a real noun (`skills/permissions.py`
  `DATA_PERMISSIONS`, `code/policy.acquisition_grants`) granted only by the
  operator switch `acquisition_enabled` (eclipse-memory policy, default OFF;
  surface-dropped when off; handler re-checks fail-closed; admitted by a new
  `_admit_collect_tools` seam). Policies tab gained "Let Eclipse collect
  datasets for you". Tests: `python/tests/test_acquire.py` (9, hermetic stub
  bridge). Verified: targeted Python suites 71 passed; vitest size ratchet held.
  Recorded as remaining (phase-16): more sources, cross-call budget, the chat
  manifest panel, the opt-in live smoke.
  docs updated: `docs/harness/decisions.md` (ADR-H190),
  `docs/harness/roadmap/phase-16-bulk-acquisition.md`,
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Execution tiers are enforced (W4/ADR-H189): the local runner refuses
  network; the container tier is real.** `RunSpec.network` was declarative with
  no consumer. Now `code/sandbox.py::run` refuses any spec that declares network
  (the local primitive cannot contain it), `code/backends.py::ContainerBackend`
  is implemented on the hardened `security/sandbox.py::docker_argv` flags
  (`--network none|bridge`, read-only rootfs, `no-new-privileges`, cap-drop ALL,
  tmpfs, non-root, memory/pids limits; only the task's folder mounted; scrubbed
  env only; container killed by name on timeout; image via
  `HARNESS_SANDBOX_IMAGE`, default `python:3.12-slim`), a new
  `select_for_spec` is the ONE tier rule (network ⇒ container, else local, no
  fallback), and `command_run` routes through it — `dependency_install` stays
  operator-gated OFF and now genuinely requires a container runtime when
  enabled. The `local` guarantees text was updated in the same change so the
  declaration cannot drift from the behavior. Tests:
  `python/tests/test_sandbox_backends.py` (+4: refusal-before-launch, tier
  routing, hardened argv for network, `--network none` when unasked). Verified:
  targeted Python suites 66 passed.
  docs updated: `docs/harness/decisions.md` (ADR-H189), `docs/CHANGELOG.md`.

- **Headless one-shot: `eclipse chat -z "…"` (scripting / CI surface).** New
  `python/harness/chat_cli.py` runs ONE question through the SAME runtime the web
  chat uses (in-process, like `eclipse eval` — no front door, no second agent
  loop): `eclipse chat -z "…"` prints the answer, `--json` prints
  `{success, runId, status, output, error}`, exit 0/1/2 for completed/failed/
  missing-question. Model settings resolve from the `HARNESS_JOB_*` environment
  (the same source a scheduled job uses) plus the callback bridge vars; the
  dispatch is wired in `harness/cli.py` before the shared parser. Tests:
  `python/tests/test_chat_cli.py` (4, hermetic). Documented in
  `docs/QUICKSTART.md` (Headless one-shot) with the CI note (`eclipse eval .`
  already runs the offline gate). Verified: pytest 4 passed.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **Phase 15 tail — document truncation is now visible in the run (honesty fix).**
  A shortened attachment was only noted at the front door; the run could not know
  it was reading the first part, so a question about page 30 could be answered
  confidently from page 1. Now `extract.ts` reports `originalChars`,
  `loadContextDocuments` and the TS validator carry `truncated`/`originalChars`
  through the run payload (`schemas.RunDocument` gained the fields with camel
  aliases), and `graph._user_message` marks the document
  (`<document … shortened="true">` plus a plain sentence) so the answer can state
  the limit. The phase-15 file's stale "extractors Not started" note is corrected
  (the docx/xlsx/pptx/odt/ods/odp/epub extractors already existed; the code wins).
  Caps stay deliberately bounded (20k/doc, 60k total) — raising them is a
  context-budget decision, recorded in the phase file. Tests:
  `src/lib/chat/session-store.test.ts` (+1), `src/lib/harness/validation.test.ts`
  (+2), `python/tests/test_graph.py` (+1). Verified: vitest 25 passed (2 files),
  pytest 3 passed, `npx tsc --noEmit` clean.
  docs updated: `docs/harness/roadmap/phase-15-attachments-and-artifacts.md`,
  `docs/CHANGELOG.md`.

- **Phase 17 — the agent can schedule its own work, from a fixed catalogue and
  behind an operator switch (repo-mapped onto the Automation engine; ADR-H187).**
  New `python/harness/automation/catalogue.py` (nine research/analysis shapes
  referencing the EXISTING `jobs.templates` — no code or deploy shape; a
  consistency check fails on drift) and `python/harness/automation/scheduling_tools.py`
  (`job_list`, `job_describe_template`, `job_create`, `job_run_now` on the ONE
  registry). `job_create` ALWAYS writes a DISABLED automation tagged `job`+shape
  and accepts only the shape's closed parameter set — the operator enables it
  under Scheduled Jobs; `job_run_now` refuses a switched-off job (mirrors
  `bot_run`). New policy key `agent_scheduling_enabled` (eclipse-memory policy,
  default OFF): `graph.surface_disabled_tools` drops the whole scheduling surface
  when off and every handler re-checks it fail-closed; a Policies-tab toggle
  ("Let Eclipse schedule work for you") surfaces it. The unattended answer
  contract now exists: `automation/delivery.py::render_run_report` puts the
  plain outcome on the FIRST line of every delivered report and names every
  limit a run hit. `job_create` is admitted via the new
  `SCHEDULING_EFFECT_TOOLS` class; the chat code profile carries the four tools.
  Tests: `python/tests/test_scheduling_tools.py` (9) + updated
  `test_chat_code_profile.py`. Verified: targeted Python suites 47 passed.
  docs updated: `docs/harness/decisions.md` (ADR-H187),
  `docs/harness/automation-engine.md`, `docs/harness/roadmap/phase-17-working-on-a-cadence.md`,
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **The acquire loop: Eclipse can now install skills from GitHub and install
  software, Hermes-style (ADR-H188).** New `python/harness/skills/install.py`
  (parse a https GitHub URL/`owner/repo`, fetch the codeload zipball with
  size/timeout caps, zip-slip/symlink-safe extraction, accept both `skill.json`
  and `SKILL.md`-frontmatter formats, staged pydantic validation + content scan,
  commit + `trust_root`, `uninstall_skill`, `list_installed_sources`,
  `discover_installed_skills`) and `python/harness/skills/install_tools.py`
  (`skill_install`/`skill_uninstall`/`skill_sources` + `make_skill_authorizer`:
  single-use digest-bound approval `skill_install`, pause-in-card-mode). The
  registry loads installs as the new **`external` tier**
  (`project > profile > external > bundled`) via `load_all(installed_home=)` /
  new `reload()`; boot records `<repo>/installed-skills`
  (`BLACK_ECLIPSE_SKILLS_DIR` override). `mcp/install_ops.py` extracts the
  preset-integration install so the operator route and the new approval-gated
  `mcp_install` tool (`mcp/install_tools.py`, plus read-only `mcp_integrations`)
  share ONE implementation — still DISABLED/nothing-selected. The chat
  classifier now treats acquisition as software work (`install`/`uninstall` are
  strong verbs; `download`/`set up` need a software object), so "install
  blender" reaches the code profile where `package_install`/`terminal_run` run;
  `ACQUISITION_WRITE_TOOLS` (`code/policy.py`) strips the five tools at
  `plan_only`. Prompt, `ECLIPSE_AGENT` and `CHAT_CODE_TOOLS` carry the new tools;
  `GET /skills/installed` + installed fields on `GET /skills`. Tests:
  `python/tests/test_skill_install.py` (28) + `test_mcp_install_tools.py` (8) +
  classifier cases; prompt ceiling re-pinned 27769→29162 (three guidance
  paragraphs); `python/conftest.py` anchors `HARNESS_MCP_CONFIG` to a temp file
  so a developer's real `mcp-servers.json` can never leak into the suite; the
  graph.py size pin re-pinned 2034→2043 for unrelated in-flight wiring. Verified:
  `npm run test` green — vitest 262 files passed, pytest 5973 passed / 16 skipped,
  eval gates ALL PASS; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/decisions.md` (ADR-H188),
  `docs/harness/phase-3-architecture.md`,
  `docs/harness/memory-skills-evolution-plan.md`,
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Notification center: red unread badges on sidebar tabs + a loud task-done
  alarm.** New `src/lib/notifications/` — `store.ts` (zustand ledger at
  `be_notifications_v1`, newest-first cap 100, per-`AppTab` unread counts, an
  item raised for the visible tab is read on arrival; `setActiveTab` clears a
  tab's badge), `task-diff.ts` (pure first-poll seeds, then announce exactly
  one transition per `task:<id>:<completedAt|updatedAt>`; completed → loud,
  failed → alert cue), `task-watcher.tsx` (mounted in `src/app/layout.tsx`,
  15s poll of `GET /api/tasks`, honest no-op on 503/offline). The
  `be:alert-notify` channel is now the single raise path for price alerts,
  agent approvals and task completions: `alert-notification-provider.tsx`
  parses `{ id, title, body, tab, kind, sound, alertId, test }` and always
  toasts + feeds the ledger (+ OS notification when opted in). The sidebar
  renders red per-tab badges (count, `9+` cap, dot when collapsed) and an
  aggregate badge on the Terminal/Agentic/Bots switcher for tabs the active
  menu hides; the sidebar's `activeTab` is the shell's visible-tab signal.
  New `taskdone` sound cue (8th cue) — genuinely loud by design: synthesized
  per-pack WAV assets in `public/sounds/<pack>/taskdone.wav`, `essential: true`,
  and a new optional `gainFloor` (0.75) in `SoundDefinition` so the deliberately
  subtle default master volume cannot render it inaudible (per-cue mute/volume
  and the master switch still apply). A chat reply that finishes while the
  operator is on another tab raises the same loud cue from `use-agent-run.ts`
  (watching the ChatBot keeps the soft `message` cue). Tests:
  `src/lib/notifications/store.test.ts` (8) + `task-diff.test.ts` (8).
  Verified: vitest 266 files / 2823 passed; `npx tsc --noEmit` clean; eval
  gates ALL PASS (one pre-existing, machine-specific
  `test_vision_tools.py` failure — `PRIVACY_REFUSED` on a desktop with a
  display — unrelated to this change; no Python file touched).
  docs updated: `docs/ARCHITECTURE.md` (notification center + `taskdone`/
  `gainFloor`/`be_sounds_v3` drift fix), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Notification center completed: bell panel, bot-run notifications, and a
  critical alarm that plays even with UI sounds off.** Follow-up to the entry
  above. (1) `taskdone` is now a declared critical cue: `SoundDefinition` gains
  `alwaysAudible`; `canPlay` lets such cues through while the master switch is
  off (per-cue mute remains the explicit opt-out), so a finished background task
  is heard without the operator hunting for the opt-in toggle. Settings › Sound
  states this honestly; the cue hint says it too. (2) Bot runs now notify:
  pure `src/lib/notifications/bots-run-diff.ts` diffs each bot's `lastExecution`
  (first sweep seeds; new-or-finished terminal runs announce once keyed
  `bot-run:<automationId>:<executionId>`; cancelled/skipped stay quiet) and
  `bots-run-watcher.tsx` (mounted in `src/app/layout.tsx`) sweeps
  `GET /api/automations` + one status call per active bot (cap 20, 30s) —
  failures keep their previous tracking entry so a transient status error cannot
  swallow a completion. Completed → `taskdone` cue, failed/timed out/blocked →
  the alert cue, all on the `bots` tab. (3) The top bar gains a notification
  bell + glass ledger panel (`src/components/layout/notification-center.tsx`):
  aggregate unread count, entry click → mark tab read + `be:navigate`, per-entry
  dismiss, "Mark all read" (store `markAllRead`/`remove` actions). New
  `NotificationKind` = `bot`. Tests: `bots-run-diff.test.ts` (9) + two store
  cases for `markAllRead`/`remove` — 27 total in `src/lib/notifications`.
  Verified: vitest 268
  files / 2838 passed; `npx tsc --noEmit` clean; `npm run dev` boot smoke check —
  `/` 200 (56 KB), `/api/alerts/live` 200, and the new watchers' first polls
  (`GET /api/automations`) reached the Python runtime with no compile or runtime
  errors. No Python file touched (the pre-existing machine-specific
  `test_vision_tools.py` failure is unchanged).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

## 2026-10-12

- **Scheduler button relocated to the BotChat header (follow-up).** The prior
  move put "Open scheduler" in the left sidebar footer; it belongs on the bot
  chat page itself, top-right beside the bot's Settings gear. Reverted
  `src/components/layout/sidebar.tsx` (and the earlier
  `bots-sidebar-panel.tsx` removal stands — no scheduler in the left nav).
  Added the toggle to `src/components/bots/bot-chat.tsx` header cluster,
  adjacent to Settings, sharing `useWorkspaceStore` with the top-bar toggle.
  no doc change — UI placement only.

- **Scheduler button moved next to Settings.** The Bots-mode "Open scheduler"
  control lived in the left nav panel (`BotsSidebarPanel`), competing with the
  bot list. It now sits in the sidebar footer directly beside the Settings gear,
  shown only while the Bots mode is active, in both the expanded and collapsed
  sidebar variants. Removed the button + now-unused `useWorkspaceStore`/
  `CalendarDays` wiring from `src/components/bots/bots-sidebar-panel.tsx`; added
  it to `src/components/layout/sidebar.tsx`, sharing the same
  `useWorkspaceStore.toggle` as the top-bar toggle and Ctrl/Cmd+Shift+E keybind.
  no doc change — UI placement only, no contract/architecture change.

- **Compact map tooltips.** Hover cards on the Investor Eye map were covering
  the map with text: long titles/summaries wrapped to several lines, and the
  aggregated-events card carried an Example headline, a Countries row and a
  two-sentence note. `tooltipFormatter` in
  `src/lib/investor-eye/map-echarts.ts` now clamps title (64) / subtitle (96) /
  row value (44) / note (140) to a single line with an ellipsis, narrows the
  card (160–250px) and tightens padding. In `src/lib/investor-eye/layers.ts` the
  cluster card drops the redundant Example row and shortens its note; the
  event, trade and heatmap notes are trimmed (kept the "potential"/"observed"
  provenance wording). no doc change — UI copy/style only, contracts intact.

- **Website-style visual blocks in chat.** Six new `eclipse-response` block
  types give an answer the rhythm of a data website: `stat_hero` (oversized
  headline numbers), `gauge` (progress meters), `comparison_grid`
  (option × attribute check/cross matrix), `ranked_list` (leaderboard bars scaled
  to the list's own max), `badge_row` (tag/pill clusters) and `carousel` (a slide
  deck of recursively-validated nested blocks). Added zod schemas + limits +
  type/field aliases (`stat`/`stats`, `progress`/`meter`, `comparison`,
  `leaderboard`/`ranking`, `badges`, `slides`) and carousel nesting in
  `src/lib/response/contract.ts`; new `src/components/response/visual-blocks.tsx`;
  registry entries in `response-view.tsx`; PDF fallbacks in
  `src/lib/response/export.ts`. Producer prompt updated with the new block names +
  one guidance clause (ceiling re-pinned 27445 → 27769). No fabricated data: bars
  clamp visually but always show the true value, and `unavailable` is honored.
  Tests: `contract-blocks.test.ts`, `render.test.tsx`. docs updated:
  `docs/interactive-response-engine.md`, `python/tests/test_memory_tools.py`,
  `python/tests/test_phase_s_stabilization.py`.

- **Diagrams and charts render instead of failing.** Three producer-vs-renderer
  mismatches were breaking real answers: (1) `key_value` items written with
  `key`, `chart` series written with `points` (`{x,y}` objects) and
  `financial_chart` written with `ticker`/`interval`/`90d` were rejected whole
  by the zod contract and degraded to "Unsupported block type"; (2) Mermaid
  definitions with unquoted labels holding `( ) → /`, HTML entities or a wrapped
  `Note over …:` line hit a parse error; (3) the layered SVG layout used a fixed
  200px LR column pitch narrower than its 240px max node width, so wide labels
  overlapped the next column. Fixes: expanded field/interval aliases in
  `src/lib/response/contract.ts` (`key`/`name`→item `label`, `points`/`values`→
  chart `data` + point-object coercion, `ticker`/`instrument`→`symbol`,
  `interval`/`range`→`timeframe`, day-count timeframes, chart-type synonyms,
  `source`→mermaid `diagram`, node `name`/`title`→`label`, edge
  `source`/`target`→`from`/`to`); new pure `src/lib/response/mermaid-repair.ts`
  (entity decode, quote unquoted flowchart labels, join wrapped sequence notes)
  wired into `mermaid-block.tsx`; per-layer column widths in
  `src/lib/response/diagram-layout.ts`. No new block types, no contract
  version bump, no producer-prompt change (the prompt is at its pinned
  ceiling). Tests: `mermaid-repair.test.ts`, `contract-blocks.test.ts`,
  `diagram-layout.test.ts`. docs updated: `docs/interactive-response-engine.md`,
  `docs/NAVIGATION.md`.

- **Internet image search with inline rendering.** "Show me images of X" now
  searches the real internet and renders actual images in the chat instead of
  listing links. New provider layer `src/lib/image-search.ts` (Brave Images when
  `BRAVE_API_KEY` is set, else keyless Openverse → Wikimedia Commons, all over the
  SSRF-hardened `safeGet`; per-query cache + in-flight coalescing + bounded
  retries). The `image_search` bridge capability returns the normalized
  `ImageSearchResult` contract (direct image URL, thumbnail, source page, domain,
  dimensions, provider, retrievedAt, attribution); the Python
  `image_search`/`validate_image_result`/`render_image_gallery` tools validate and
  collect results into a run `images` blob (`research/image_contracts.py`,
  `ImageCollector`, wired in `graph.py`; `RunResult.images` + a persisted
  `HarnessRun.images` column) surfaced on `client.final` and rendered inline by
  the new `ImageGallery`/`ImageGalleryPanel` (responsive grid, lazy loading,
  lightbox, source attribution, broken-image fallback) and a new `gallery`
  response block. Every image URL is http(s)-only. Tests: TS
  `image-search.test.ts`, `image-gallery-view.test.ts`, `contract-gallery.test.ts`,
  `gallery-render.test.tsx`; Python `test_image_search.py`. docs updated:
  `docs/interactive-response-engine.md`; no doc change — CHANGELOG only.

- **Added the icon-driven `workflow` block (connected process diagrams).** The
  engine already rendered markdown, callouts, metrics, charts, tables, diagrams,
  Mermaid, node graphs, timelines, steppers, infographics, reports, citations,
  actions and artifacts — but had no dedicated **icon-driven, connected process**
  block, so "explain how HFT works" could not produce the required staged flow.
  New `workflow` block: ordered `stages` (icon + title + description, optional
  `detail`/`inputs`/`outputs`/`status`/`tone`) joined by directional connectors,
  with `layout: vertical|horizontal|auto` (auto = horizontal for ≤4 stages,
  stacking to a column on narrow screens). `WorkflowBlock` (`rich-blocks.tsx`) is
  a real, keyboard-accessible disclosure (button + `aria-expanded`), offers
  Expand all / Collapse all and Copy, and an "Ask Eclipse about this stage"
  control that re-enters the EXISTING agent loop. Wired into the registry
  (`response-view.tsx`), the icon allowlist (`icons.ts`: `radio`,
  `brain-circuit`, `combined-chart`, `cpu`, `server`, `gears`), and the producer
  prompt (`prompts.py`, kept under its 26410-char ratchet at 26408; `steps`→`stages`
  field synonym added in `contract.ts`). Tests: +4 contract (`contract-blocks.test.ts`)
  and +4 render (`render.test.tsx`). Checks: `npx tsc --noEmit` clean; lint 0
  errors; response suites 106 passed; prompt-ceiling Python tests 30 passed.
  docs updated: `docs/interactive-response-engine.md`.

- **Response charts were broken and off-brand; now smooth, theme-aware and
  frosted.** The ECharts binding lost the design system entirely: `buildChartOption`
  returned its own bare `tooltip` object that **overwrote** the frosted-glass
  tooltip recipe from `baseChartOption()` (translucent tint, `appendTo: 'body'`,
  18px blur, rounded shadow), so charts showed a flat default tooltip. Extracted
  `mergeChartOption()` so the base chrome and the block's trigger/formatter are
  combined, never clobbered. Also made charts consistent with the app: theme-aware
  axis/legend ink via the new shared `hooks/use-dark-scheme.ts` (zrender can't parse
  `oklch`, so ink is concrete rgba for light/dark), `cubicOut` animation, smooth
  lines, rounded/capped bars, gradient area fills, soft dashed gridlines, rounded
  pie/heatmap cells, and no more `confine` (which fought `appendTo:'body'`).
  Every visual surface (chart canvas, Mermaid/diagram/node-graph SVGs, loading
  skeletons) now sits in a `.glass-card-subtle` container instead of a flat
  `border + bg-accent` fill, per the UI skill. Tests: +5 in
  `chart-option.test.ts` (tooltip-chrome survives the merge, theme ink differs,
  smooth/rounded/animated). Checks: `npx tsc --noEmit` clean; lint 0 errors;
  vitest 2676 passed; python 5749 passed (one earlier run had a flaky failure that
  reran green; no Python changed). docs updated: `docs/interactive-response-engine.md`.

- **"What influenced this run" moved from the chat turn into the right
  sidebar.** The memory/skill observability that rendered as a collapsed panel
  under every completed assistant answer is now a docked Agent Workspace tab
  (**Influences**, a 3-dots icon), so it reads like the other run panels
  (Context/Output/Changes/Approvals/History). It is offered **only while the
  ChatBot tab is in front** (`AgentWorkspace` gained a `showExplain` prop;
  `stock-chat.tsx` passes `activeTab === 'chat'`). The panel fetches
  `GET /api/harness/runs/{id}/explain` for the workspace's bound run and renders
  the same stat tiles, excluded-memory groups, memory budget, workflow/lineage
  and prompt-shaping sections using the workspace UI primitives. Selecting a
  past run in the History tab (which rebinds the workspace run) shows that
  run's explanation, so the per-run capability is preserved. New files:
  `src/components/agent-workspace/explain-panel.tsx`; retired
  `src/components/chat/run-explanation-panel.tsx` (no remaining importers).
  New store panel id `explain` + `workspace.panel.explain` copy. Checks:
  `npx tsc --noEmit` clean; vitest 2676 passed; Python 5749 passed; eval gates
  ALL PASS. docs updated: `docs/agent-workspace.md`, `docs/NAVIGATION.md`.

- **The Agent Workspace wraps at narrow widths instead of hiding elements.**
  Dragging the right sidebar to half its default width used to clip content; the
  panel-tab bar was `overflow-x-auto scrollbar-hide`, so tabs past the visible
  width were simply cut off. The nav is now `flex-wrap`, so the tabs flow onto a
  second row when they no longer fit, and the Influences panel keeps wrapping its
  chips and long lines (`break-words`) rather than truncating them. Nothing is
  hidden at narrow widths — elements move down. Checks: `npx tsc --noEmit` clean;
  vitest 2676 passed; lint 0 errors. no doc change — presentation-only responsive
  tweak (the panel is already described in `docs/agent-workspace.md`).

- **Real `eclipse-response` answers no longer lose blocks or show scary render
  errors.** A live "explain HFT visually" answer exposed two defects. (1) The
  model used `text` — the same word as the `text`→`markdown` *type* alias — as the
  body *field* on `markdown` and `callout` blocks; the normalizer only mapped
  `content`→`markdown`, so those blocks failed and rendered as "Unsupported block
  type". `normalizeBlockFields` now also maps a scalar `text`→`markdown` for the
  prose body types (`markdown`/`callout`/`details`), scoped so it never steals
  `heading`'s own `text` field. (2) Both `mermaid` blocks (correctly written with
  `code`, which already normalizes to `diagram`) validated but failed at *render*
  with "Could not render this mermaid block" — a `BlockBoundary` error caused by
  the **redundant** outer `next/dynamic` wrapper around `mermaid-block`, which
  already lazy-imports the heavy `mermaid` package inside its effect. Removed that
  wrapper in `response-view.tsx` and `markdown.tsx` (static import of the tiny
  component; the library stays lazy), and serialised Mermaid renders through one
  module-level chain so two diagrams in one answer can't clobber Mermaid's global
  config. All mermaid failures now degrade to the inline card, never the boundary.
  Tests: +3 synonym/regression cases in `contract-blocks.test.ts`, +1 end-to-end
  payload case in `render.test.tsx`. Checks: `npx tsc --noEmit` clean; response
  suites 94 passed. docs updated: `docs/interactive-response-engine.md`.

- **The bot-chat header is now a compact banner.** `bot-chat.tsx`'s identity
  row was too tall: `p-4` → `px-3 py-2`, avatar 52 → 36, name `text-base` →
  `text-sm`, description clamped to one line at `text-[11px]`, and the
  schedule/last-run meta row tightened to `text-[10px]`. Checks:
  `npx tsc --noEmit` clean; lint 0 errors; size budget passes. no doc change —
  presentation-only restyle.

- **Bots mode hides the app header on desktop, for a full-bleed chat.**
  `top-bar.tsx` now applies `md:hidden` to its own root when
  `activeTab === 'bots'` (it already receives the active tab), so the price
  ribbon / search / terminal bar no longer sits above the bot conversation. It
  stays visible on small screens, where its menu button is the only way to open
  the sidebar. Focus mode still hides it entirely. Implemented without growing
  `stock-chat.tsx` (a ratcheted file pinned at 1366 lines). Checks:
  `npx tsc --noEmit` clean; size-budget + lint pass. no doc change —
  presentation-only shell tweak.

- **Bot-mode replies now read as a full-width document, not a floating glass
  card.** In the Bots workspace (`bot-chat.tsx` and `group-chat-room.tsx`) a
  non-error bot reply dropped the `glass-card-subtle` surface and the
  `max-w-[80%]` bubble; it now spans the full width (avatar + name + Markdown +
  timestamp), so a long structured answer reads like the main chat transcript.
  User turns and honest error turns keep their framed bubbles. Checks:
  `npx tsc --noEmit` clean; lint 0 errors. no doc change — presentation-only
  restyle of the existing bot surfaces.

- **Rich-response blocks are now light/dark theme-aware, and `metadata` is
  bounded.** An audit of the Interactive Response Engine confirmed the feature is
  fully implemented (versioned contract, block registry, mermaid/ECharts/icons,
  auto-selection via the agent prompt, persistence, tests); three real gaps were
  closed. (1) `mermaid-block.tsx` hardcoded `theme: 'dark'`, so diagrams were
  unreadable in light mode — it now observes the app's `dark` class (same signal
  as `eclipse-provider.ts`) and re-renders with `'dark'`/`'default'`;
  `diagram-block.tsx` and `node-graph-block.tsx` now draw node text with
  `currentColor` instead of a hardcoded `#e5e7eb`. (2) The envelope `metadata`
  field was an uncapped `z.record` — it now has a `maxMetadataKeys` (40) + size
  ceiling and is *dropped, not fatal* on overflow (`.catch(undefined)`) so
  over-limit bookkeeping can never cost the user their answer; 3 new tests in
  `contract.test.ts`. (3) Corrected the doc's AGENT-001 traceability (it pointed
  at `test_prompt_segments.py`, which has no `eclipse-response` coverage; real
  coverage is the prompt-ceiling pins in `test_memory_tools.py` /
  `test_phase_s_stabilization.py`). Checks: `npx tsc --noEmit` clean; response
  suites 90 passed. docs updated: `docs/interactive-response-engine.md`.

- **Bot and group chat no longer die as "Failed to fetch" on a real research
  turn.** The Bots workspace (`bot-chat.tsx`, `group-chat-room.tsx`) sent each
  turn through the one-shot `POST /api/harness/chat`, whose front door aborts
  every run at a 180s cap (`python-client.ts` default `timeoutMs`); a
  tool-heavy turn (reproduced: "find me a good psx stock" → 8 model steps / 36
  tool calls / ~243s) was killed mid-run and surfaced as a raw browser
  "Failed to fetch". Both surfaces now run turns through the shared streaming
  agent provider (`getAgentProvider().chat`, background run + SSE) — the same
  path the main chat uses — so a run is observed live and survives its full
  duration, with per-token updates and abort-on-unmount. Replies are also
  rendered with the shared `Markdown` component instead of raw pre-wrapped
  text, so structured/`eclipse-response` answers read correctly. `chat-store.ts`
  and `groups-store.ts` gained an in-place `update`/`updateMessage` action to
  fill the streaming bubble. Checks: `npx tsc --noEmit` clean; targeted vitest
  (213 tests across bots/agent/response/chat-route) + lint pass. no doc change —
  bug fix reusing the existing streaming provider; contracts unchanged.

- **A structured `eclipse-response` answer now reads as one document instead of
  a stack of detached cards.** Every sibling block got the same `space-y-4` gap,
  so a valid five-block answer (callout + markdown + two tables + markdown)
  looked like five separate components. `response-view.tsx` now assigns the
  between-block gap by adjacency: two adjacent prose blocks (markdown, heading,
  callout, details, key_value, citations, timeline) get a tight `mt-2.5` so they
  flow, while a visual "surface" block (chart, table, metric grid, diagram, …)
  keeps a clear `mt-4` so it reads as its own figure; compact spacing stays
  tighter. The same helper drives the nested `renderBlocks` (tabs/report) path.
  The producer guidance in `python/harness/prompts.py` was also tightened to say
  the `blocks` array is ONE document, not separate cards — keep connected prose
  in a single markdown block and do not repeat the fence's text outside it
  (net-neutral rewrite; prompt stays under its 26410-char ratchet at 26406).
  Locked by the new "response layout cohesion" tests in `render.test.tsx` (prose
  flows tight, surfaces separate, five-block answer stays intact, nested report
  rhythm), and the invariant is documented in the engine doc's new "Layout
  cohesion" subsection. Checks: `npx tsc --noEmit` clean; `npm run test` all pass
  (5749 python + vitest + eval gates); lint 0 errors. docs updated:
  `docs/interactive-response-engine.md`.

- **The site no longer freezes / times out during startup or background
  refreshes.** Root causes found and fixed, all in the single Node web process
  (synchronous `better-sqlite3` writes block the event loop):
  - `investor-eye/graph-data.ts` `persistEventEntities` did a `findFirst` per
    entity reference — ~50 s for an ~800-event window. It now pre-loads the
    existing `(eventId, kind, entityId)` keys in one (chunked) query: 50,400 ms →
    231 ms; `refreshGraph` 51,273 ms → 1,214 ms.
  - The relationship-graph rebuild is now **fire-and-forget and throttled**
    (10 min) in `investor-eye/state.ts` instead of awaited on the world-state
    path.
  - `instrumentation.ts` now runs its boot pipeline **once per process** (Next
    invokes `register()` more than once), and the `db-guard` `VACUUM INTO`
    backup (hundreds of MB) runs **once per day** instead of on every boot — the
    old code re-ran a 200 MB+ write storm at each startup.
  - `scraper/price-scraper.ts` `seedUniverse` no longer aborts the whole seed on
    a transient SQLite lock (P1008) and yields between writes.
  - `cluster.ts` memoizes per-event title tokens, removing millions of redundant
    regex passes in `clusterEvents`.
  - `components/layout/ui-catalog-sync.tsx` lazy-loads its sync so the dashboard
    widget registry + full ECharts stay out of the root `/` bundle.
  Verified: production boot 0 request failures over 170 s (was ~20 s of timeouts
  mid-boot); `npx tsc --noEmit` clean; `npm run test` all pass (2661 vitest +
  python + eval gates). docs updated: `docs/investor-eye-architecture.md`,
  `docs/CHANGELOG.md`.

- **Task runs are now actively recovered, not merely observed.** Added
  `python/harness/recovery/execution.py` (`run_with_recovery` / `TaskRunFailed` /
  `classify_run_exception`), which drives a production run THROUGH the existing
  bounded recovery executor (`recover_operation`): a transient run failure is
  classified by the shared taxonomy, diagnosed, retried with the controller's
  backoff, and recorded as a durable incident before the scheduler's own retry
  policy applies. Wired into the ONE production seam
  (`tasks/bootstrap.build_task_executor`); each attempt gets a distinct run id, and
  the recovery trail rides the task execution metrics. A repair strategy with no
  caller handler is handed back as `strategy_requires_caller` (never invented). With
  the engine absent or `HARNESS_RECOVERY_ENABLED=0`, behavior is exactly as before:
  one attempt, exception propagates. The recovery import is guarded, so a degraded
  environment degrades to the single-attempt path rather than disabling the task
  layer. New tests
  `python/tests/test_recovery_task_execution.py` (10 cases: transient retry,
  auth no-retry, budget partial, verification failure, caller-handback, disabled
  no-op, production-executor integration). Checks: `pytest` recovery+tasks suites
  224 passed. docs updated: `docs/harness/failure-recovery.md`, `docs/CHANGELOG.md`.

- **Bots scheduler is now the right-docked Agent Workspace slot; page is pure chat.**
  In Bots mode the right dock renders a new `components/bots/scheduler-dock.tsx`
  (hosting `scheduled-jobs-panel.tsx`) instead of the run observability panels; it
  reuses the shared `useWorkspaceStore.open`, so the top-bar toggle, the
  Ctrl/Cmd+Shift+E chord and the new left-sidebar **Open scheduler** button
  (`bots-sidebar-panel.tsx`) are all one control. Removed the Bots page's own
  right rail, so the conversation truly fills the page. `agent-workspace.md`
  updated to document the Bots-mode content swap. Checks: `npx tsc --noEmit` clean;
  `vitest` 2661 passed. docs updated: `docs/NAVIGATION.md`, `docs/agent-workspace.md`,
  `docs/CHANGELOG.md`.

- **Bots page: full-page chat + collapsible right scheduler rail.** Dropped the
  page header (title/subtitle + New group/New bot buttons — creation now lives in
  the left sidebar panel). The conversation now fills the whole page, and the
  scheduled-jobs scheduler is a rail docked to the RIGHT: collapsed it is a thin
  clickable strip (`CalendarDays` + vertical "Scheduled jobs"), expanded it shows
  `scheduled-jobs-panel.tsx` with a chevron to tuck it away. The `stock-chat` Bots
  wrapper no longer adds padding/scroll so the page is truly full-height. Checks:
  `npx tsc --noEmit` clean; `vitest` 2661 passed. docs updated: `docs/NAVIGATION.md`
  (Bots trigger row), `docs/CHANGELOG.md`.

- **Bots page: bot list moved to the left sidebar; the conversation is the page.**
  The Bots page no longer renders its own bot list — the left app sidebar (Bots
  mode) is the ONE list, now covering bots AND group chats via
  `bots-sidebar-panel.tsx`. The page is just the full-height conversation
  (`bot-chat` / `group-chat-room`) with the scheduled-jobs rail on the right.
  Group selection/creation now flows through the shared `bots-store` (`selectGroup`
  / `openGroupCreate`, deep link `?tab=bots&group=<id>`). Checks: `npx tsc --noEmit`
  clean; lint 0 errors. docs updated: `docs/NAVIGATION.md` (Bots trigger row),
  `docs/CHANGELOG.md`.

- **Structured `eclipse-response` blocks no longer degrade to raw text on a
  plausible producer payload.** The contract now normalizes field-name synonyms
  (not just block `type` aliases) before per-block validation: `content`→
  `markdown` (markdown/callout/details) and `content`/`code`→`diagram` (mermaid),
  `variant`→`tone` (callout), `items`→`sources` + `name`→`title` (citations),
  string `columns` + positional array `rows`→typed table columns/records
  (`data_table`), `note`→`hint` (metric cards), and common intervals
  (`1Y`/`YTD`/`MAX`/`1D`…) onto a supported `financial_chart` timeframe. An
  observed answer that previously produced 15 `unknown` blocks out of 23 now
  validates with zero diagnostics. `normalizeBlockFields` in
  `src/lib/response/contract.ts`; tests in `contract-blocks.test.ts`. docs
  updated: `docs/interactive-response-engine.md`.
- **Fixed US-equity "no provider supports 'quote' for unknown".** Because
  provider routing is keyed on asset class, the bridge's `market_snapshot` now
  returns the resolved `identity.assetClass` (derived from `securityType` via
  `toAssetClass`) instead of the raw vault column, which is null for most equity
  rows (`assetClass = null`, `securityType = "Stock"`). The Python
  `_asset_type_from` fallback was hardened to classify a recognised
  `securityType` alone as that type (or `equity`), leaving only a fully
  unclassified request as `unknown`. `src/lib/harness/data-bridge.ts`,
  `python/harness/market/instruments.py`; test in `test_market_unit.py`. docs
  updated: `docs/harness/market-data.md`.
- **Assistant tables wrap their text and render inline Markdown.** Table cells
  were forced `whitespace-nowrap`, and `data_table` cells (which the
  deterministic planner fills verbatim from GFM table cells) were rendered as
  plain text, so `**bold**`/`*italic*` showed as literal markers. Markdown-table
  th/td and `DataTableBlock` th/td now wrap (`break-words`); `DataTableBlock`
  renders headers and cells through the shared `renderInline`, so bold/italic/
  code/links are real elements, while filter/sort/TSV use the stripped plain text.
  `src/components/chat/markdown.tsx` (exports `renderInline`),
  `src/components/response/data-table-block.tsx`; test in
  `src/components/response/render.test.tsx`. no doc change — bug fix (no
  contract/architecture change).

- **Learning Research Engine: internet learning-resource discovery + interactive
  roadmaps.** Eclipse can now search the live internet for YouTube videos,
  playlists, courses, GitHub repos, official docs and academic papers, and build
  a prerequisite-aware learning roadmap it renders inline in the chat. Adds the
  learning domain vocabulary (`ResearchIntent.LEARNING`, `SourceType.VIDEO/COURSE/
  REPOSITORY/DOCUMENTATION/DATASET/TUTORIAL/PODCAST` + a `learning` rank table);
  real front-door connectors (`src/lib/education-connectors.ts`: YouTube Data API
  v3 key-gated with a keyless media fallback, GitHub REST, an allowlisted course
  search, and a permitted-only transcript path) wired as bridge capabilities; a
  deterministic curriculum engine (`research/learning.py`: DAG validation,
  resource ranking/verification, path assembly); 10 learning tools
  (`research/education_tools.py`, in `WEB_RESEARCH_TOOLS`); durable progress in
  `eclipse-memory.db` (migration 30 + `LearningStore`); operator-gated
  `/learning/*` routes with an `/api/learning` proxy; and the interactive
  `learning_map` response block (completion controls persist via the SAME store
  the agent writes through). Tests: `test_learning_{engine,store,tools}.py`,
  `education-connectors.test.ts`, `contract-blocks.test.ts`. docs updated:
  `docs/harness/learning-research-engine.md`, `docs/NAVIGATION.md`.

- **Construction-First Audit — Phase 0 ground truth and repo-mapped phase plan.**
  Read-only audit of the real execution paths (six parallel sweeps: front-door
  routing, registry/allowlists, execution substrate, acquisition/retrieval,
  recovery/permissions/evals, response/rendering/artifacts) plus a full baseline
  run: `tsc` clean, vitest 259 files / 2749 tests pass, Python 5780 passed /
  16 opt-in skips / 0 failed, eval gates ALL PASS. New
  `docs/harness/construction-first-audit.md` records: the as-built architecture
  map, the capability inventory (≈886 registered tools; recovery/artifact/
  orchestration/fabric families registered but in no allowlist), eight verified
  root causes (classifier lexical gaps; the default agent cannot see code tools;
  the inert `RunSpec.network` + 17-module import allowlist; closed-capability
  acquisition; the "UNAVAILABLE is a complete answer" doctrine; diagnostics-panel
  visual errors; and a **verified streaming bug** — `service.run_background`
  drops the portfolio/quant/ui bundles that `service.run` passes, so advertised
  quant/portfolio tools fail at call time), the contradictions with existing
  records, the repo-mapped round-3 phase plan, and a risk register. docs updated:
  `docs/harness/construction-first-audit.md`, `docs/harness/roadmap/README.md`
  (stale claims marked, not deleted). no code change.

- **R3-01 construction-first routing.** "Scrape this site", "clean this CSV" and
  "run a Monte Carlo" no longer fall through the deterministic classifier to
  `not_code`: a new `data_task` verdict (a data verb + a data object in one
  clause, plus "run a Monte Carlo") sends NO autonomy and turns the analysis
  sandbox on, leaving the ordinary finance surface unchanged — so Eclipse
  computes/cleans/extracts instead of refusing. `python/harness/code/
  request_intent.py` (vocabularies + verdict union + follow-ups), front door
  `chat-capability.ts`/`code-client.ts` (`autonomy: null` handling) and
  `run-service.ts`; prompt doctrine rewritten construction-first in `prompts.py`
  (length-neutral; ceiling stays 27769). Also fixes the verified streaming bug:
  `AgenticService.run_background` dropped the portfolio/quant/ui bundles that
  `run` passes, so advertised quant/portfolio tools failed at call time
  (`StoreUnavailable`). Tests: 19 classifier cases, 2 payload cases
  (`run-service.test.ts`), new `test_service_background_parity.py`. docs
  updated: ADR-H177 in `docs/harness/decisions.md`, phase-14 §6.1/§6.3,
  `docs/harness/construction-first-audit.md`.

- **R3-02 execution substrate, honestly tiered.** Fixed the measured dead-gate:
  `execute_python` / `execute_code` / `build_project` / `start_service` /
  `package_install` were refused by the composed effect authorizer (they fell to
  the MCP authorizer, which has no server id for them) while still advertised to
  `edit_verify` profiles — the registry-level fix is
  `code/authorizers.py::_admit_runtime_tools`, which admits exactly
  `policy.EXECUTION_WRITE_TOOLS` + `APP_RUNTIME_WRITE_TOOLS` and leaves
  cluster/infra/remote actions on their approval path. The analysis sandbox now
  enforces its declared limits (cpu 600s total-burn guard, memory 2048 MB, 64
  processes). Its "no network" claim is true by construction: the exec namespace
  runs with a restricted builtin set and the AST guard refuses dunder attribute
  access, `__builtins__`, reflection call names and http(s) URL literals (which
  would let pandas fetch). Persistent shells no longer inherit the host
  environment (`terminal/session.py` now uses `sandbox.build_env`). The `local`
  backend's capability declaration in `code/backends.py` states the real posture
  (no OS filesystem/network isolation; policy + construction). New tests:
  `test_authorizer_runtime_admission.py`, analysis escape/limit cases in
  `test_analysis_execution.py`, the shell-secret case in
  `test_terminal_session.py`. docs updated: ADR-H178 in
  `docs/harness/decisions.md`, `docs/harness/execution-architecture.md`,
  `docs/harness/construction-first-audit.md` (R3-02 done; Q1 fixed, Q2 verified,
  Docker absent on this machine).

- **R3-03 bounded recovery in the run hot path.** The graph's tool loop now runs
  every call through `recovery/hotpath.py::run_tool_with_recovery`: on failure
  the recovery engine classifies and decides; a READ-ONLY tool with a
  retry/backoff decision is retried once (in-loop backoff capped at 1.5s), and
  every other failure gets the strategy appended to its result as a next-step
  directive ("do NOT repeat the same call; use a different route"). Per-run
  counters are supplied via `record_failure(recovery_state=…)`, so a failure
  seen in a past session cannot exhaust a fresh run; `max_total_ms` is enforced
  when elapsed is supplied; recovery approvals are now single-use
  (`consume_approval`, claimed by the executor rather than merely checked).
  Fail-open: no engine or any error returns the original result unchanged, and
  `graph.py` stays exactly at its size ratchet. Tests:
  `test_recovery_hotpath.py`, single-use approval in `test_recovery_executor.py`.
  docs updated: ADR-H179 in `docs/harness/decisions.md`,
  `docs/harness/failure-recovery.md`, `docs/harness/construction-first-audit.md`.

- **R3-04 bounded page collection (`web_scrape`).** The agent can now scrape one
  page deterministically: a new `web_collect` bridge capability fetches through
  the SAME SSRF-hardened transport as `web_fetch` (https-only, DNS-pinned,
  redirects re-validated, 4 MB / 8 s caps) and extracts repeated records with a
  CSS selector (optional field→sub-selector map or attribute) or the page's own
  tables (caps 500 rows / 5 tables / 40 columns / 20 k text). Exposed as the
  read-only `web_scrape` tool on the ONE registry and the default agent's
  allowlist; results are COLLECTED untrusted page data with the page as source.
  Honest zero-vs-unavailable: no selector matches is a confirmed zero on the
  delivered page (client-rendered pages point at the browser tools); a failed
  fetch is UNAVAILABLE. The retrieval layer's UNAVAILABLE text now names the
  eligible next routes before concluding. Tests: `data-bridge-collect.test.ts`
  (9), `test_web_collect.py` (6). docs updated: ADR-H180 in
  `docs/harness/decisions.md`,   `docs/harness/web-research-engine.md`,
  `docs/harness/construction-first-audit.md`.

- **R3-05 utility building — verified shipped; chat review-copy honesty clause.**
  Recon corrected the plan: the phase-15 promotion path already shipped
  (ADR-H176) and is chat-reachable (`PromoteChange` on `edit_verify` turns:
  preview → single-use digest-bound approval → apply), `scaffold_kit` enforces
  the worktree binding + `code.write`, and both `decide_write` call sites are fed
  the worktree-bound actor. The one real gap found: the chat prompt never said
  edits sit in a review copy, so the model could claim a file was in the user's
  project. `prompts.py` now states "build them in a review copy … never claim a
  file is there" (ceiling 27769 held; measured 27768) with a pinning test in
  `test_chat_code_profile.py`. docs updated:
  `docs/harness/construction-first-audit.md`.

- **R3-06 computed results surface in chat; diagnostics split by severity.**
  `analysis.completed` now carries the bounded result blob (outputs, artifacts,
  provenance), the client maps it to a first-class `analysis` turn field, and the
  (formerly dead) `ComputedResultPanel` renders it under the assistant message on
  both chat surfaces — a provenance-less value still shows UNAVAILABLE. The same
  change fixes a delivery bug: the main ChatBot surface was dropping
  `codeVerification`/`autonomy`/`capability`/`documents` from the turn, so the
  code-capability panel (with the promotion control) and the document panel never
  appeared there. Response diagnostics are now split by severity: only errors
  raise the amber panel; warning-only answers render quietly and an empty-but-
  valid envelope gets one muted line. Activity lines summarize `analysis_run`
  ("worked out N value(s), M saved") and `web_scrape` ("N record(s) collected")
  without leaking content. Tests: mapping cases in `events.test.ts`, severity
  cases in `render.test.tsx`, summary cases in `test_code_activity.py`. docs
  updated: ADR-H181 in `docs/harness/decisions.md`,
  `docs/interactive-response-engine.md`, `docs/harness/construction-first-audit.md`.

- **R3-07 permission hardening: schedules need a go-ahead; metadata states the
  real effect.** An agent can no longer put itself on a cadence unattended:
  `bot_create`/`bot_update` (autonomous trigger) and `bot_enable`/`bot_resume` are
  now `write` + `external_action`, admitted by the new bot authorizer, and the
  handler claims (or requests + pauses for) a single-use `bot_schedule` operator
  approval before creating/starting a schedule; the whole set is removed at
  `plan_only`. `computer_record_export` admits it writes a file
  (`effect="write"`, joined `COMPUTER_EFFECTFUL_TOOLS`); `git_lfs_fetch/pull`
  moved to `GIT_EXTERNAL_TOOLS` and out of the chat profile's declared set;
  `policy.TERMINAL_READ_TOOLS` now names the tools that exist. Deliberately
  ungated: `bot_run`, pause/disable/delete, manual bots. Tests:
  `test_automation_authorizer.py` (+7 cases), updated
  `test_chat_code_profile.py`. docs updated: ADR-H182 in
  `docs/harness/decisions.md`, `docs/harness/construction-first-audit.md`.

## 2026-10-11

- **Bots workspace: chat-first redesign.** Reworked the Bots page to read like the
  ChatBot page but for bots — the left admin panel (search box, filter pills,
  large collection cards, a boxed "Group chats" block) is gone. The left rail is
  now a compact conversation list (avatar + name + status/description subtitle +
  live dot, with a hover per-bot menu; group chats listed beneath), the
  conversation fills the centre, and the scheduled-jobs rail stays on the right.
  Removed the now-unused `components/bots/bot-card.tsx` and the superseded inline
  `components/bots/create-bot.tsx` (the New bot modal replaced it). Checks:
  `npx tsc --noEmit` clean; lint 0 errors (only image warnings). docs updated:
  `docs/NAVIGATION.md` (Bots trigger row), `docs/CHANGELOG.md`.

- **Bots workspace redesign + nav dropdown.** Turned the Bots workspace into a
  three-column layout — bot list + group chats (left), the conversation (centre,
  `bot-chat` or the new `group-chat-room`), and a scheduled-jobs rail (right,
  `scheduled-jobs-panel.tsx`, reading the SAME automation list). Replaced the
  inline two-step `create-bot.tsx` with a `create-bot-dialog.tsx` modal (face
  picker with Bot/Generate/Upload/Pet tabs, Randomize/Lock face, "face follows the
  name", Name/Title/Description, and a collapsed Advanced schedule builder). Added
  group chats (2–6 bots, `lib/bots/groups-store.ts`, `group-chat-dialog.tsx`) and
  uploaded-photo avatars (`lib/bots/image.ts` + the shared `bot-avatar.tsx`, used
  by the list, chat, sidebar panel and jobs rail). The sidebar's Terminal/Agentic/
  Bots switcher is now a glass **dropdown** instead of a three-tab pill. All new
  surfaces use the frosted-glass tiers; replies still come from the real harness
  (`/api/harness/chat`) and bots from the existing Automation API — nothing is
  fabricated. Checks: `npx tsc --noEmit` clean; `vitest run` 2655 passed. docs
  updated: `docs/NAVIGATION.md` (Bots trigger row), `docs/CHANGELOG.md`.

- **Interactive Response Engine: server-rendered DOM tests + lint hygiene.** Added
  `src/components/response/render.test.tsx` (21 tests) that server-render the real
  components via `react-dom/server` in the node test env — covering block content,
  mixed-response ordering, unknown-block isolation, `report` nesting, the
  streaming/malformed fences, action-group proposal semantics, safe citation
  links, and the `mermaid`-fence-vs-code-block classification. No new dependency
  (no jsdom/testing-library). `vitest.config.ts` disables the oxc transformer
  (`oxc: false`) and enables the automatic JSX runtime so TSX components transform
  under vitest, leaving the Next build (tsconfig `jsx: preserve`) untouched.
  `eslint.config.mjs` now ignores disposable root-level `_*.cjs`/`_*.mjs` scratch
  scripts (the recurring lint breakage). docs updated:
  `docs/interactive-response-engine.md` (§6), `docs/CHANGELOG.md`.

- **Interactive Response Engine: full rich-block family + link hardening.** Added
  the remaining structured block types — `stepper`, `infographic`, `report`,
  `node_graph` (selectable; reuses the deterministic `diagram-layout` engine
  rather than a second graph library), `action_group` (PROPOSED next steps that
  only compose a follow-up prompt into the existing agent loop), and `artifact`
  (a reference to the existing Artifact Center) — plus spec-name aliases
  (`text`→`markdown`, `table`→`data_table`, `source_list`→`citations`,
  `interactive_form`→`controls`, `execution_timeline`→`timeline`). Citation and
  artifact links are now **scheme-restricted to `http(s)`** — bare
  `z.string().url()` accepts `javascript:`/`data:`, which becomes an XSS vector
  once rendered as an anchor. Infographic/action icons resolve through a semantic
  allowlist (`src/lib/response/icons.ts`), so the model never names a component or
  import path. The agent "Structured answers" guidance in `prompts.py` was
  rewritten to be more directive and to list the new blocks, staying **within the
  unchanged 26410-char prompt ceiling**. Every new block renders through the same
  registry + `BlockBoundary` and is represented in PDF export. Tests:
  `src/lib/response/contract-blocks.test.ts` (17 new). docs updated:
  `docs/interactive-response-engine.md`, `docs/DECISIONS.md` +
  `skills/ARCHITECT.md` (ADR-043 amendment), `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **Chat: render ` ```mermaid ` fences as diagrams.** A model that emitted a
  plain fenced `mermaid` block (rather than an `eclipse-response` JSON block) got
  its raw source shown as a copyable code block — the chat Markdown renderer had
  no case for it, so diagrams never appeared. `components/chat/markdown.tsx` now
  routes a settled `mermaid` fence through the existing lazy `MermaidBlock`
  (`securityLevel: 'strict'`), while a streaming fence stays text so a
  half-written definition never flashes a parse error. Bug fix, contract
  unchanged. docs updated: `docs/interactive-response-engine.md` (DIAG-002 row),
  `docs/CHANGELOG.md`.
- **Deployment hardening: thread-safe `agent-memory.db` connections.** The store
  was one `sqlite3.Connection` shared across FastAPI's worker threads and async
  tasks (`check_same_thread=False`, no lock), which intermittently raised
  `SystemError: error return without exception set` on `commit` (seen as the
  flaky `test_jobs_api` failure). New `python/harness/sqlite_pool.py`
  (`ThreadLocalConnections`) gives each thread its own connection in autocommit
  mode with a `busy_timeout`, so WAL readers run alongside the single writer and
  a second writer waits rather than failing on a deferred read-to-write upgrade.
  `AgentMemoryStore` delegates to the pool; `close()` releases connections and is
  called on the last lifespan exit (`boot._shutdown`); `reset_memory` wraps its
  multi-table clear in an explicit `BEGIN IMMEDIATE`/`COMMIT`. Full Python suite:
  5722 passed, 16 skipped. docs updated: `docs/harness/architecture.md` (new
  persistence/connection contract), `docs/CHANGELOG.md`, `docs/NAVIGATION.md`;
  `persistence.py` ratchet re-pinned in `python/tests/test_size_budget.py`.
- **Quant research correctness audit: look-ahead, accounting and integration
  fixes.** Fixed independently-verified defects. (1) Volatility position sizing
  read the *tail of the whole series* — direct future-price leakage; `_realized_vol`
  now takes the decision bar and uses only bars up to and including it. (2) The
  event engine's trade P&L omitted the **entry** commission (it was accrued but
  never expensed), overstating `net_pnl`/`realized_pnl` and every trade metric;
  closes now allocate the attributable entry commission and reconcile with the
  cash ledger. Partial closes keep the original cost basis (previously the basis
  was reset to the exit price). (3) The factor covariance model mixed a
  short-window `B` with a full-history `F`; `estimate_factor_covariance` now uses
  the same trailing window as the loadings. (4) Shrinkage expected-return
  auto-intensity was `N/(N·T̄)` (~`N`× too weak); now `N/T̄`. (5)
  `_sample_covariance` now truncates unequal-length series instead of building a
  ragged array. (6) `historical_replay` reported the worst *cumulative* value as
  the worst period and a non-compounded drawdown; now reports the true worst
  period and a compounded-index `maxDrawdown`. (7) Trailing stops advanced on the
  same bar's favorable extreme before testing the bar's adverse extreme; the
  barrier is now tested first (no same-bar look-ahead). (8) Benchmark alpha/IR/TE
  and bootstrap Sharpe annualized daily equities at 365; they now follow the
  metrics engine (252, 365 only for crypto), via an `asset_class` argument. (9)
  MACD's signal line was zero-seeded across the warm-up; it now runs only over the
  valid MACD segment. (10) `Position.realizedPnl` is now maintained. (11)
  `ML_TOOLS` were registered but absent from every explicit allowlist (unreachable
  from the supervised agent); now spread into `ECLIPSE_AGENT`. (12) ATR-based
  protective brackets were sized from the fill bar's ATR (one bar of future
  range); now measured from the decision bar (`order.submitted_index`). (13)
  `portfolio/risk.py::sortino` downside deviation used the population denominator
  while `quant/metrics.py` used the sample one; both now use `n-1`. (14)
  `event_system.registry._spec` did not accept `namespace`, so
  `EventBus._observe` raised `TypeError` in a fire-and-forget task and **silently
  dropped every unregistered legacy event type**; `_spec` now supports
  `namespace`. Regression tests: `python/tests/test_quant_audit_fixes.py` (11),
  `test_events_bus.py::test_legacy_bridge_auto_observes_unknown_namespace`, and
  the corrected `test_quant_costs_validation.py`. Full Python suite: 5720 passed
  (1 intermittent `test_jobs_api` sqlite-teardown flake passes in isolation);
  eval gates: ALL PASS.
  TS: the `factors` and `ml` catch-all route `Ctx` now uses the optional
  `path?` form every other route uses (tsc was failing on 4 generated-validator
  errors). docs updated: `docs/CHANGELOG.md`, `docs/quant-engine.md`,
  `docs/NAVIGATION.md`, `docs/ml-lab/ARCHITECTURE.md`.
- **Portfolio Construction & Risk Engine - Round 3: factor risk model, risk
  caps, cardinality/lot, observability.** `estimation.estimate_factor_covariance`
  builds Σ = B·F·Bᵀ + D (OLS loadings × factor covariance + diagonal
  idiosyncratic variance) and `risk_engine.factor_risk` decomposes portfolio
  volatility into systematic/idiosyncratic parts with factor risk contributions
  (Σ reconciles to systematic volatility); selected via
  `covariance_method:"factor"` + `factor_returns`. The solver now enforces a
  convex `max_volatility` / parametric `max_var` cap (validated independently;
  an unreachable cap returns `INFEASIBLE`). Cardinality (`max_positions`),
  `min_position_weight` and `lot_size` are applied as a documented,
  independently-validated post-processing step (downgraded to
  `FEASIBLE_LIMIT_REACHED`). Structured construction logging with the run id.
  New tool `portfolio_factor_risk` (39 `portfolio_*` tools). Tests
  `python/tests/test_portfolio_construction_ext.py` extended (factor risk,
  vol/VaR caps, cardinality, lot). docs updated:
  `docs/portfolio-accounting.md`, `docs/NAVIGATION.md`.
- **Portfolio Construction & Risk Engine - Round 2: persistence, costs, factor
  models, simulation, comparison, routes, background jobs, E2E.** Closed the
  remaining gaps from the first slice. `estimation.estimate_factor_loadings` (OLS
  loadings/alpha/residual/R²; auto-used by `factor_constrained` when
  `factor_returns` are supplied). `construction.compare_allocations` (same-input
  multi-method comparison) and a linear transaction-cost term folded into the
  mean-variance/min-variance objective. `attribution.multi_period_attribution`
  with exact proportional geometric linking. `simulation.rebalancing_simulation`
  (point-in-time scheduled rebalancing/walk-forward with turnover+costs, no
  look-ahead). Immutable run persistence (`PortfolioConstructionRun` in
  `PortfolioStore`; `runId`/`dataVersion`/`engineVersion`). Execution-Fabric
  `portfolio` worker (`portfolio/fabric.py`) for cancellable, time-bounded
  background simulations. Five new tools (`portfolio_compare_allocations`,
  `portfolio_estimate_factor_loadings`, `portfolio_simulate_rebalancing`,
  `portfolio_list_runs`, `portfolio_get_run`) and REST routes (`…/construct`,
  `…/construction-runs`, `/portfolio/runs/{id}`, `/portfolio/estimate-inputs`,
  `…/stress-test`, `…/transaction-costs`, `…/compare`, `…/simulate-rebalancing`,
  `/portfolio/simulations/{id}`). E2E tests now drive the REAL chat run graph
  (`python/tests/test_portfolio_chat_e2e.py`) plus
  `test_portfolio_construction_ext.py`. Full Python suite 5705 passed / 16
  skipped. docs updated: `docs/portfolio-accounting.md`, `docs/NAVIGATION.md`.
- **ML Research Lab - production-hardening slice (reliability/isolation core of
  Phase 12 + Phases 13/18 gates).** Training now runs as a durable, cancellable,
  resource-bounded Execution Fabric job on a dedicated ML worker
  (`WorkerKind.ML`/`QueueName.ML`, `python/harness/ml/fabric.py`, wired in
  `fabric/{models,policies,builtin_workers}.py`): `background:true` on
  `POST /ml/v1/experiments` (or the `ml_run_experiment` tool) returns a job id
  immediately; the worker invokes the same `service.run_experiment_job` pipeline
  with a wall-clock timeout, hard cancellation (polled between folds; the
  `CancelledError` path never leaves a run stuck "running") and progress events.
  Job output is a compact summary - the full result stays a hash-addressed ML
  artifact (the Fabric output column is bounded). Added `HARNESS_ML_*` guardrails
  (`ml/config.py`: max rows/folds/seconds/concurrency/artifact-size/enabled) and a
  `TIME_BUDGET_EXCEEDED` stop. Installed and verified the real optional model
  backends - scikit-learn 1.6, LightGBM 4.7, XGBoost 3.4 (plus
  sklearn-forest/extra-trees) all train end-to-end, serialized with joblib and
  loaded only after SHA-256 verification. New surfaces: `GET /ml/v1/jobs`,
  `GET /ml/v1/jobs/{id}`, `POST /ml/v1/jobs/{id}/cancel`, tools `ml_job_status`
  /`ml_list_jobs`/`ml_cancel_job`; UI background toggle + job polling. New tests
  `test_ml_{models_ext,leakage,fabric,acceptance}.py` (leakage suite + E2E
  acceptance over SYNTHETIC fixtures); `tsc --noEmit` clean. Docs:
  `docs/ml-lab/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **Factor & Alpha Research Lab — production controls (point-in-time universe,
  multiple-testing, persisted validation, performance bound).** Added
  `python/harness/factors/universe.py` (`membership_mask`/`apply_membership`):
  factor evaluation and quantile portfolios now exclude non-member cells using
  the effective-dated universe history (`UniverseStore.members_as_of`), so a name
  that joined late or was delisted is never measured in cross-sections it did not
  belong to; `universeId` is accepted by the tools and `/factors/v1`. The
  validation gate now enforces the Deflated Sharpe Ratio and Probability of
  Backtest Overfitting (reusing `quant/multiple_testing.py`) when trial
  variance / candidate returns are supplied, and every gate run is persisted as a
  first-class `FactorValidation` row. The portfolio engine now also returns the
  net/gross long-short return series (needed for deflation without
  recomputation). Tests: `test_factors_universe.py`,
  `test_factors_performance.py` + gate/DSR/PBO additions — 44 factor tests pass.
  Docs: `docs/quant-research/FACTOR_LAB.md`.

- **Portfolio Construction & Risk Engine — native Eclipse capability.** Added the
  construction/risk vertical to the existing portfolio package (reusing the
  accounting core, the shared Market Data Gateway and the ONE tool registry).
  `estimation.py`: expected returns (arithmetic/geometric/EWMA/shrinkage/user) and
  covariance (sample/EWMA/shrinkage/diagonal) with symmetry/finite/PSD/condition
  diagnostics and a documented eigenvalue-floor regularizer; date-aligned returns
  that drop missing dates rather than zero-filling them. `construction.py`: a
  shared projected-gradient solver with an exact Dykstra projection onto the
  constraint polytope, an INDEPENDENT `validate_constraints`, a `SolverStatus`
  vocabulary, and all required methods (equal-weight, benchmark-weight,
  min-variance, mean-variance + efficient frontier, risk-parity via exact ERC
  cyclical coordinate descent, volatility-target, Black–Litterman, and
  factor-constrained). `risk_engine.py`: Euler risk contributions (asset- and
  group-level, sign-preserving) and hypothetical/factor/historical/seeded-
  Monte-Carlo stress testing. `costs.py`: one-way/gross turnover and a
  configurable transaction-cost model. Wired via `construct_service.py` +
  `PortfolioService.construct`; registered five tools (`portfolio_estimate_inputs`,
  `portfolio_construct`, `portfolio_risk_contributions`, `portfolio_stress_test`,
  `portfolio_transaction_costs`) and — fixing a real integration gap — added
  `*PORTFOLIO_TOOLS` to the Eclipse agent allowlist so the chatbot can reach the
  portfolio capability. Results are independently validated and proposal-only.
  Fixed a defect where the risk-parity log-barrier solver returned a non-ERC
  allocation (replaced by the exact CCD first-order solution) and corrected
  share-of-variance in the decomposition. Tests
  `python/tests/test_portfolio_construction.py` (28 deterministic numerical tests).
  Full Python suite 5664 passed / 16 skipped; `tsc --noEmit` clean.
  docs updated: `docs/portfolio-accounting.md`, `docs/NAVIGATION.md`.
- **ML Research Lab — foundation vertical slice (Phases 0–5).** Added a new
  quantitative ML research vertical built on the SAME NumPy core, persistence and
  market gateway as the stats/quant/factors engines. Backend
  `python/harness/ml/`: `models.py` (versioned contracts: `DatasetSpec`,
  `TargetSpec`, `SplitSpec`, `ExperimentConfig`), `datasets.py` (immutable dataset
  builder over `stats.datasets.resolve_frame` + built-in and registered Feature
  Registry features), `quality.py` (severity-graded quality engine),
  `targets.py` (forward-return/binary/multiclass/neutral-zone/volatility/
  cross-sectional-rank labels with explicit label start/end), `splits.py`
  (chronological / walk-forward / purged-K-fold with purge + embargo and an
  independent `assert_no_leakage` gate), `features.py` (fit-on-train-only
  selection), `metrics.py`, `adapters.py` (pure-NumPy dummy/ridge/logistic/CART
  random-forest + honest optional scikit-learn/LightGBM/XGBoost adapters that
  report `MODEL_UNAVAILABLE` when the wheel is absent), `training.py` (fold-fit
  preprocessing + selection, out-of-fold predictions, final holdout model),
  `store.py` (`MLStore` on `agent-memory.db`; datasets/splits/experiments/runs/
  folds/models/artifacts/predictions/approvals, SHA-256 artifact integrity),
  `service.py`, `tools.py` (12 `ml_*` agent tools), `bootstrap.py`. REST
  `python/harness/routers/ml.py` (`/ml/v1`, operator-gated) mounted in `main.py`;
  boot wiring `install_ml_layer` in `service.py`. Front door
  `src/app/api/ml/[[...path]]/route.ts` + `src/lib/ml-client.ts`; UI
  `src/components/screens/ml-lab/ml-lab-screen.tsx` (AppTab `ml-lab`, command-
  palette page). Tests `python/tests/test_ml_{core,store}.py` (29) +
  `src/lib/ml-client.test.ts` (4); `tsc --noEmit` clean. The heavy ML wheels
  could not be installed here (PyPI unreachable), so their adapters are honest
  and unit-tested for the unavailable path; install instructions are recorded in
  `python/requirements-ml.txt`. Docs: `docs/ml-lab/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

- **Factor & Alpha Research Lab — background execution, pluggable regimes and an
  end-to-end test.** Added durable background promotion through the Execution
  Fabric `quant` queue (`submit_factor_promotion` tool + `POST
  /factors/v1/promote/background`; the fabric tool context now carries the
  `quant_store`/`dataset_store` and the market `DataBridge`). Added the pluggable
  regime provider `engine.classify_regimes` (quantile buckets over any scalar
  driver, NaN-safe) wired into `analyze_factor_stability`
  (`regimeSeries`/`nRegimes`/`regimeMethod`). Added
  `python/tests/test_factors_e2e.py` (full create→evaluate→portfolio→validate→
  promote workflow through the real tool handlers) and
  `test_factors_background.py` (fabric job) — 99 factor/fabric tests pass. The
  factors router is now mounted through `routers/quant.py` (alongside the stats
  router) so `main.py` stays under its non-ratcheted hard ceiling; a duplicate
  `research_data_router` import in `main.py` was removed and the `service.py`
  size budget re-pinned for the concurrent ML Research Lab wiring. Docs:
  `docs/quant-research/FACTOR_LAB.md`.

- **Factor & Alpha Research Lab — Phase 10 promotion bridge + Phase 12
  hardening.** Added `python/harness/factors/promotion.py`
  (`promote_to_strategy`): a validated factor version is promoted into a
  first-class Eclipse strategy persisted through the ONE `QuantStore` (immutable
  version + the native `request_approval` governance), its cross-sectional
  portfolio executed by the Factor Lab quantile engine and persisted via
  `QuantStore.save_experiment` (kind `factor_portfolio`) so it sits beside native
  backtests, with factor-version → strategy-version → experiment lineage recorded
  in the Factor store. REST `POST /factors/v1/promote` + `GET /factors/v1/lineage`;
  the `promote_factor_to_strategy` tool now performs the real promotion.
  Hardening: added `python/tests/test_factors_{store,promotion,routes}.py` and
  engine invariants (rank-IC monotone-transform invariance, dollar-neutral
  long-short book, determinism) — 33 factor tests pass; full Python suite and
  Vitest suite remain green; `tsc --noEmit` clean. Docs:
  `docs/quant-research/FACTOR_LAB.md`.

- **Factor & Alpha Research Lab — new quant-research vertical (factor registry,
  IC/rank-IC/decay, quantile portfolios, alpha composition, validation gate).**
  Added `python/harness/factors/` (`engine.py` = the authoritative NumPy math for
  forward returns, cross-sectional Pearson IC + Spearman rank IC with
  Newey–West HAC inference, factor decay, cross-sectional rank/z-score/
  winsorize/demean/neutralize, quantile portfolios with turnover and
  cost-aware net/gross accounting, portfolio metrics, factor combination/
  correlation/redundancy, and the structured validation gate; `library.py` =
  built-in momentum/reversal/low-vol/trend/liquidity factors via the shared safe
  formula engine — fundamental/quality/carry factors are declared honestly
  unavailable rather than fabricated; `models.py`; `store.py` = `FactorStore` on
  `agent-memory.db` with immutable factor versions; `service.py`; `tools.py` =
  13 agent tools wired into the `ECLIPSE_AGENT` allowlist; `bootstrap.py`).
  REST surface `python/harness/routers/factors.py` (`/factors/v1`, operator-gated)
  mounted in `main.py`; boot wiring in `service.py`. Front door
  `src/app/api/factors/[[...path]]/route.ts` + `src/lib/factors-client.ts` + the
  Factor Lab screen (`AppTab 'factor-lab'`) registered through the shell,
  search registry and deep-link list. Tests: `python/tests/test_factors_engine.py`,
  `test_factors_service.py` (28) plus the full Python suite (5592 passed) and the
  full Vitest suite (2589 passed); `tsc --noEmit` clean. Docs:
  `docs/quant-research/FACTOR_LAB.md` (new tracker), `docs/NAVIGATION.md`.

- **Backtesting & Simulation Engine — options & futures asset-class support.**
  Closed the last advertised gaps. Added `quant/options.py` (reusing the market
  layer's `black_scholes` — no second pricing model): `price_option`,
  `implied_volatility` (bisection, refuses out-of-bounds prices), and
  `analyze_option_strategy` (multi-leg expiry payoff, break-evens, max
  profit/loss reported `null` when unbounded, position-level net Greeks). Added
  `quant/futures.py` `build_continuous_contract` (splice ordered contracts at a
  roll schedule with difference/ratio/none back-adjustment; newest contract
  unadjusted; result labelled a backtest proxy). Capability now advertises
  options/futures `partial` (analytics available; options backtesting /
  deliverable contracts not claimed) plus `optionAnalytics`/`continuousContracts`.
  REST: `POST /quant/{option-price,implied-volatility,option-strategy,
  continuous-contract}`. Quant tools now **68**. Docs: `docs/quant-engine.md`,
  `docs/backtesting-engine.md`, `docs/CHANGELOG.md`. Tests:
  `test_quant_options_futures.py` + additions to `test_quant_vector_advanced.py`
  and `test_quant_routes.py`.

- **Backtesting & Simulation Engine — production hardening: multiple-testing
  diagnostics, real OOS contamination detection, square-root market impact and
  REST routes.** Added `quant/multiple_testing.py` (Deflated Sharpe Ratio +
  Probability of Backtest Overfitting via CSCV, from first principles, no SciPy)
  and the `run_multiple_testing_diagnostics` tool (runs a real bounded parameter
  sweep or accepts explicit returns/Sharpe/matrix). `run_out_of_sample_test` now
  detects a prior optimization/walk-forward/sensitivity/robustness experiment
  overlapping the OOS window (`OOS_WINDOW_CONTAMINATED`, `contaminated` flag).
  Added the square-root market-impact law (`sqrt`, alongside `linear`).
  Registered REST endpoints `POST /quant/{vectorized-backtest,costs,out-of-sample,
  bootstrap,multiple-testing}` and added comparability warnings to `/quant/compare`.
  Capability map advertises `vectorizedBacktest`/`costDiagnostics`/`outOfSample`/
  `bootstrap`/`multipleTesting`. Quant tools now **64**. Docs: `docs/quant-engine.md`,
  `docs/backtesting-engine.md`, `docs/CHANGELOG.md`. Tests:
  `test_quant_multiple_testing.py`, `test_quant_routes.py`, plus additions to
  `test_quant_costs_validation.py` and `test_quant_vector_advanced.py` (quant+stats
  suite 343 passed; one pre-existing unrelated `test_artifacts_api` failure).

- **Backtesting & Simulation Engine — vectorized engine, standalone execution-cost
  diagnostics, out-of-sample + bootstrap validation, and comparison tools.** Closes
  the remaining gaps against the requested 16-tool capability surface, reusing the
  existing event engine (no second accounting path). Added `quant/vector_engine.py`
  (restricted causal-signal engine; `VECTOR_UNSUPPORTED` for anything else, exact
  equity parity with the event engine on the supported subset), `quant/costs.py`
  (`simulate_transaction_costs`/`simulate_slippage`/`simulate_spread`/
  `simulate_market_impact` over the SAME `ExecutionSimulator`, with honest
  missing-input warnings), `quant/validation.py` (percentile bootstrap — IID/block/
  stationary — and a chronological OOS split) and `quant/advanced_tools.py`
  (`run_event_driven_backtest`, `run_vectorized_backtest`, `run_out_of_sample_test`,
  `run_bootstrap_test`, `compare_backtests` + comparability cautions). `engine.py`
  now tags `metadata.engine`; quant tools total **63**. Docs: `docs/quant-engine.md`,
  `docs/NAVIGATION.md`, new `docs/backtesting-engine.md` (audit + 16-tool
  traceability + honest blockers). Tests: `test_quant_costs_validation.py`,
  `test_quant_vector_advanced.py` (full suite 331 passed; one pre-existing unrelated
  `test_artifacts_api` failure). No options/live-trading claims added.

- **Recovery repair-lease expiry boundary + doc line-ending normalization.** The
  repair lease reclaim at `RecoveryStore.acquire_lease` used a strict `<` on
  `expiresAt`, so an already-expired lease was not reclaimable whenever the
  millisecond clock landed exactly on `.000` (intermittent
  `test_repair_lease_is_exclusive_and_reclaims_on_expiry` failure); switched to
  `<=` (an expired lease is reclaimable, a held one is not). Also normalized
  `docs/harness/decisions.md` to LF so no tracked text file mixes CRLF and bare LF
  (`gitignore-guard` test). Also rotated the oldest active dated section
  (`2026-10-04`) into `docs/changelog/2026-10.md` to restore the 7-section window
  (`changelog-guard` test). Bug fixes + doc rotation — `docs/CHANGELOG.md`,
  `docs/changelog/2026-10.md`.

- **Bots tab: scheduled autonomous agents with ghost faces.** Added a `bots`
  AppTab to the Agentic menu (`src/lib/sidebar/config.ts`, `src/lib/app-tabs.ts`,
  `src/lib/i18n/nav.ts`, deep-link `APP_TABS`, command-palette page registration).
  The new `src/components/screens/bots/bots-screen.tsx` lists, creates, runs,
  pauses, resumes, enables, disables and deletes bots through the EXISTING
  Automation Engine (`/api/automations`; a bot is a `run_agent` automation on a
  manual/interval/cron/one-time trigger, so it runs in the persistent background
  engine with no browser open). Each bot gets a ghost face: `src/lib/bots/ghost.ts`
  (serializable `GhostSpec`, closed option sets, deterministic `ghostSpecFromId`,
  seeded `randomGhostSpec`), rendered by `src/components/bots/ghost-avatar.tsx`
  (parametric inline SVG) and edited by `src/components/bots/ghost-customizer.tsx`
  (per-part option strips + color pickers + randomize/reset). Faces persist
  client-side per bot id (`src/lib/bots/avatar-store.ts`, the repo's
  appearance-settings convention, mirroring `lib/sidebar/store.ts`). No new
  backend/agent runtime was introduced. Tests: `src/lib/bots/ghost.test.ts`;
  `src/lib/sidebar/config.test.ts` updated for the new section and the
  `stock-chat.tsx` size ratchet re-pinned. Verified: `npx tsc --noEmit` clean,
  vitest 2602 passed, `npm run test:smoke` reachable, `npm run build` and
  `npm run check:all` clean. Follow-up polish: the create form now uses the
  shared frosted `Select`/`Input`/`Button` primitives (dark-mode-correct
  dropdown popups) instead of native controls, and `GhostAvatar` uses a
  per-instance `useId` clip id so multiple ghosts never collide. Bots is
  `group: 'both'` so, like ChatBot, it stays visible in the sidebar regardless
  of the Terminal/Agentic toggle (it was agentic-only and therefore hidden for
  users parked on Terminal). docs updated:
  `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.

- **Proper Bot Workspace: discovery, guided creation, detail, execution
  visibility, and real chat tools.** Replaced the one-screen bot list with a
  cohesive workspace over the EXISTING Automation Engine (no new backend store or
  runtime). Nav: Bots is now a third tab beside Terminal/Agentic in the sidebar
  switcher (`src/components/layout/sidebar.tsx`), always one click away. UI split
  into focused modules under `src/components/bots/` (`status-pill`, `bot-card`,
  `schedule-editor`, `create-bot`, `run-history`, `bot-detail`) plus the
  orchestrator `src/components/screens/bots/bots-screen.tsx` and pure logic
  `src/lib/bots/state.ts` (backend→UI state mapping, real filters, search,
  human schedule summaries, draft→trigger translation, all unit-tested). The
  workspace has a compact header + search + status filters (All/Active/Paused/
  Running/Needs attention, all computed from real fields), a scannable bot
  collection with contextual menus, an honest empty state with example prompts,
  a master/detail layout with deep linking (`?tab=bots&bot=<id>`), and a detail
  view organized into Overview / Instructions / Schedule / Capabilities / Memory
  / Run history / Settings with inline edits that call the real API. Run history
  shows real executions, durations, errors, activity timeline and deliveries, and
  polls ONLY while a run is live (stopping at terminal). **Chat-first:** new
  Python agent tools `bot_*` (`python/harness/automation/tools.py`) register on
  the ONE tool registry, are wired in `service.py`, and are added to the Eclipse
  agent allowlist (`agents.py`), so chat can create/list/inspect/run/pause/
  resume/update/delete bots and inspect runs — the same objects the UI shows.
  Tests: `src/lib/bots/state.test.ts`, `python/tests/test_automation_tools.py`,
  updated `src/lib/sidebar/config.test.ts`. Verified: `npx tsc --noEmit` clean,
  `npx vitest run` 2616 passed, `npm run lint` 0 errors, `npm run build` clean,
  targeted Python suites (automation + code-agent + surface-honesty) 91 passed.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.

- **Bots mode now lists your bots in the sidebar (not a generic nav link).**
  When the Bots mode is active, the sidebar renders the user's actual bots in a
  panel (avatars, name, live/lifecycle status dot, active highlight) instead of a
  static "Bots" nav item — mirroring how chat history sits under ChatBot. Bots is
  now a first-class sidebar MODE (`NavGroup = 'terminal' | 'agentic' | 'bots'`)
  with no static section; the switcher's Bots tab selects it and opens the
  workspace. New shared `src/lib/bots/bots-store.ts` (zustand) is the single
  source of bots + selected bot for BOTH the sidebar panel and the workspace, so
  they never drift; selection is reflected in `?tab=bots&bot=<id>`. Added
  `src/components/bots/bots-sidebar-panel.tsx`; `src/components/layout/sidebar.tsx`
  renders it in Bots mode and syncs the mode on first mount (deep-link safe).
  Updated `src/lib/sidebar/config.ts` + `config.test.ts`. Verified: `npx tsc
  --noEmit` clean, `npx vitest run` 2617 passed, `npm run lint` 0 errors,
  `npm run build` clean (after clearing a stale `.next` from a concurrent dev
  server), dev server restarted and serving. docs updated: `docs/CHANGELOG.md`,
  `docs/NAVIGATION.md`.

- **Confirmed promotion: Eclipse can now put a reviewed change into its own
  code (Phase 15 promotion slice, ADR-H176).** Previously a code run's change
  lived in a disposable copy and nothing ever copied it back, so "Eclipse changed
  the API" was a diff in a scratch folder that got deleted. Added the ONE landing
  path: `python/harness/code/promotion.py` (preview → single-use `code_promote`
  approval → apply), two operator-gated routes (`POST /code/tasks/{id}/promote/
  preview` and `.../promote`) that reuse the existing `mcp/approvals.py` decision
  and the `code/patch.py` engine (base-hash + protected-path + atomic), and an
  additive `patch.py` `overwrite` op (whole-file, base-checked). A protected path
  (`code/policy.py` and the other frozen authorities, `.git`, `.env`, databases,
  keys, migrations) is refused in the preview and again at apply; the target is
  always the server-resolved checkout root; no git write happens in the runtime.
  Reached from the conversation via a "Put this change into my project" control on
  a coding turn (`src/components/chat/promote-change.tsx`, wired through
  `ChatCapabilityPanel` + `chat-history`) and from the Code Tasks screen
  (`task-detail.tsx`); front door `code-client.ts`/`code-browser.ts` + the two
  Next proxies. Tests `python/tests/test_code_promotion.py` (11 pass; unit + route
  seam) + full `-k code` sweep (393 pass); `npx tsc --noEmit` clean; the `code.promote.*`
  copy is under the plain-language gate. Also re-pinned the `test_size_budget.py`
  `service.py` ratchet 1444→1454 for the in-flight Bots/Automation wiring already
  in the tree (additive `bot_*` registration; not this change). docs updated:
  `docs/CHANGELOG.md`, `docs/harness/decisions.md` (ADR-H176), `docs/NAVIGATION.md`.

- **Bot page is now a conversation (Grok/Hermes-style).** Opening a bot no longer
  shows an admin tab panel; it opens a chat with the bot. New
  `src/components/bots/bot-chat.tsx`: header with the bot's avatar, inline-editable
  name + purpose, status pills, next/last run, and controls (Run now, Pause/Resume,
  Details); a real message thread; and a composer. Each message runs the REAL
  Eclipse agent via `POST /api/harness/chat`, with the bot's identity + standing
  instructions as leading context, so replies are grounded, not fabricated;
  failures render an honest error bubble. Threads persist per bot
  (`src/lib/bots/chat-store.ts`). The previous detail sections (Overview /
  Instructions / Schedule / Capabilities / Memory / Run history / Settings) are
  preserved behind a **Details** drawer (`BotDetail` in a `Sheet`), so no
  functionality was removed. Updated `bots-screen.tsx` to mount `BotChat`.
  Verified: `npx tsc --noEmit` clean, `npx vitest run` 2617 passed, `npm run
  lint` 0 errors, `npm run build` clean, dev server restarted and serving.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.

- **Fix: autonomous bot runs failed with "model not found".** A scheduled/`Run
  now` bot executes inside the Python runtime with no per-run model override, so
  it fell back to the runtime's env default (`HARNESS_JOB_MODEL`, historically
  `llama3.1`) — while interactive chat worked because the front door passes the
  operator's saved model per run. The launcher now resolves the saved LLM config
  (`getLLMConfig()`) and publishes it into the spawned runtime's env as
  `HARNESS_JOB_PROVIDER` / `HARNESS_JOB_MODEL` / `HARNESS_JOB_BASE_URL` /
  `HARNESS_JOB_API_KEY` (a real env var still wins), so automations, jobs, tasks
  and fabric use the same configured model as chat. Verified end-to-end: a
  `run_agent` bot that previously failed now completes (`state=completed`).
  `src/lib/harness/python-runtime.ts` only. Verified: `npx tsc --noEmit` clean,
  `npx vitest run` 2617 passed, `npm run lint` 0 errors, dev server restarted.
  docs updated: `docs/CHANGELOG.md`.

- **Fix: bot chat crashed with "Maximum update depth exceeded" + create never
  opened.** (1) `bot-chat.tsx` selected messages with
  `useBotChatStore((s) => s.byBot[bot.id] ?? [])`; the inline `?? []` returned a
  NEW array every render, breaking zustand/useSyncExternalStore snapshot caching
  and throwing an infinite render loop that the error boundary surfaced as
  "Something went wrong". Now uses a module-level `NO_MESSAGES` constant, so the
  snapshot is stable. (2) The header **Create bot** button and the sidebar **+**
  called `openBot(null)`, which forced `createOpen` back to false, so the guided
  creation flow never appeared. Creation state now lives in the shared
  `bots-store` (`createOpen` + `openCreate`), so both the header and the sidebar
  "+" open it. Verified in a real browser: sidebar "+" opens the create panel,
  a bot is created and persists, and sending a message returns an in-character
  reply from the real agent. (3) The recurring "Invalid or unexpected token"
  console error was a corrupt `next dev` chunk in `.next-dev`; clearing the dev
  cache resolved it (dev and prod already use separate dirs). Files:
  `src/components/bots/bot-chat.tsx`, `src/lib/bots/bots-store.ts`,
  `src/components/bots/bots-sidebar-panel.tsx`,
  `src/components/screens/bots/bots-screen.tsx`. Verified: `npx tsc --noEmit`
  clean, `npx vitest run` 2634 passed, `npm run lint` 0 errors, `npm run build`
  clean, dev server restarted and serving. docs updated: `docs/CHANGELOG.md`.

## 2026-10-10

- **Factor Lab, options and futures quant surfaces + advanced engine/route
  updates.** Added `python/harness/factors/` (engine/library/models/store) with
  `docs/quant-research/FACTOR_LAB.md`, and `quant/options.py` + `quant/futures.py`
  with `test_quant_options_futures.py`; extended `quant/advanced_tools.py`,
  `quant/tools.py` and `routers/quant.py` (engine selection, cost diagnostics,
  OOS/bootstrap, multiple-testing, factor/options/futures tools). Quant+factor
  test selection: 234 passed. `docs/quant-engine.md` and
  `docs/backtesting-engine.md` updated.

- **Production-readiness fixes for the Strategy SDK sandbox.** Added a shippable
  container image (`python/Dockerfile.quantsdk` + `python/requirements-quant-sdk.txt`
  — numpy/pydantic/PyYAML only) so the optional Docker isolation path
  (`HARNESS_QUANT_SDK_DOCKER_IMAGE`) is real, not aspirational; documented it in
  `docs/harness/quant-sdk-sandbox.md`. Added an end-to-end smoke test
  (`test_quant_e2e_smoke.py`) driving the full chatbot flow through the real tool
  registry (create → backtest → report → approve → deploy paper → paper shadow
  run). Re-ran the front-end gates: `vitest run` **2589 passed** and `next build`
  clean. `docs/harness/quant-sdk-sandbox.md` updated.

- **Strategy Development Engine (runtime hardening + paper shadow loop).** Added
  `quant/sdk_deps.py` (approved numerical dependency policy; `inspect_source`
  flags `UNAPPROVED_DEPENDENCY`; no on-demand installs). Hardened
  `quant/sdk_runtime.py`: POSIX `RLIMIT_CPU`/`RLIMIT_AS` preexec plus an optional
  **Docker** backend (`resolve_sandbox`/`docker_command`, `--network none
  --read-only --memory 512m --cpus 1 --pids-limit 256`) selected when
  `HARNESS_QUANT_SDK_DOCKER_IMAGE` is set and Docker is present, else the process
  worker. Added a **paper shadow loop** (`run_paper_session`, `list_paper_runs` +
  `QuantPaperRun` table): a deployed (approved, active) strategy is run as a REAL
  backtest over recent data and recorded — no orders, `liveExecution: false`.
  Quant tools now **54**. Docs updated: `docs/quant-engine.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H175). Tests: `test_quant_ops.py`,
  `test_quant_sdk_runtime.py`.

- **Strategy Development Engine (lifecycle close-out): governance, source
  inspection, multi-file projects, deeper validation.** Added
  `quant/ops_tools.py` and store tables on `agent-memory.db`:
  `QuantStrategyApproval` (review gate) and `QuantStrategyDeployment` (governed
  **paper-only** records — `live` raises `LIVE_TRADING_DISABLED`, no path routes
  an order); tools `inspect_python_strategy` (static AST inspection — advisory),
  `request/decide/list_strategy_approval`, `create/list/stop_strategy_deployment`,
  and `run_python_project` (multi-file strategy project in the isolated worker,
  sibling imports by name). Added static validation codes `AMBIGUOUS_FILL_TIMING`
  (warning) and `INDICATOR_TF_UNORDERED`. Quant tools now **52**. Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H174). Tests: `python/tests/test_quant_ops.py`. Honest remaining gap:
  container-grade isolation + pinned per-run dependencies (process isolation
  today).

- **Strategy Development Engine (chatbot-only): expression DSL, expanded
  indicators, benchmark metrics; the dedicated strategy UI was removed.** The
  feature is now driven entirely from the chatbot (agent tools) per direction —
  deleted `strategy-canvas.tsx`, `python-lab.tsx`, `src/lib/backtest/
  graph-editor.ts` (+ test) and reverted the Backtest screen/client to their
  prior form. Engine additions: **expression DSL** (`strategy.py`/`rules.py`:
  arithmetic `+ - * /`, `min/max`, `neg/abs`, causal `lag`; safe, causal, no
  `eval`; validation recurses with `UNKNOWN_REFERENCE`/`BAD_LAG`); **indicators**
  (`indicators.py`: Stochastic, ADX ±DI, Donchian, Keltner, OBV, MFI, Williams
  %R, CCI + node-registry entries); **benchmark metrics** (`quant/benchmark.py`:
  alpha/beta/correlation/tracking-error/IR/excess via the new
  `analyze_against_benchmark` tool — 44 `quant_*` tools total). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H170/H171 amended, ADR-H173). Tests: `test_quant_expressions.py`,
  `test_quant_indicators_ext.py`, `test_quant_copilot.py`.

- **Strategy Development Engine (Phase 7): AI Strategy Copilot support —
  grounded signals, research plans, reports and the remaining required tools.**
  Added `quant/copilot.py` (`calculate_signals` = the decision timeline with
  reason codes and NO orders; `build_research_plan` = an explicit hypothesis /
  split / benchmark / cost / parameter-search / acceptance-criteria / bias spec;
  `build_report` = Markdown grounded only in a stored experiment + artifact; plus
  rule/sizing/stop helpers) and `quant/copilot_tools.py` (12 tools:
  `calculate_signals`, `create_research_plan`, `generate_strategy_report`,
  `generate_entry_exit_rules`, `configure_position_sizing`,
  `configure_stops_and_targets`, `get_experiment_status`, `cancel_experiment`,
  `calculate_performance_metrics`, `analyze_trade_log`, `compare_strategies`,
  `run_parameter_sweep` — reusing existing handlers where one exists). Quant tools
  now total 43. Routes `/quant/signals`,
  `/quant/strategies/{id}/research-plan`, `/quant/experiments/{id}/report`.
  Grounding is carried by the tools (deterministic artifacts or typed errors);
  the agent system prompt is at its hard size ceiling, so no prompt text changed.
  `backtestClient` gains `researchPlan`/`report`/`signals`. Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H172). Tests: `python/tests/test_quant_copilot.py` (7).

- **Strategy Development Engine (Phase 3 backend): the Python Strategy SDK and
  managed, isolated runtime.** Added `quant/sdk.py` (typed `Strategy` base +
  `Context` + `run_user_strategy`; the driver *subclasses* `BacktestEngine`, so
  fills, protective legs, risk, portfolio accounting and metrics are the SAME
  code path as a declarative backtest), `quant/sdk_worker.py` +
  `quant/sdk_runtime.py` (the source runs in a **separate process** with
  `python -I`, a scrubbed environment — no PYTHONPATH/credentials — a wall-clock
  timeout, an output-size cap and POSIX rlimits where available; results are
  rehydrated into a typed `BacktestResult`), and reference strategies in
  `quant/examples/` (`ma_crossover`, `mean_reversion`, `vol_target_trend`). The
  `run_python_strategy` agent tool and `POST /quant/python/run` reuse the store;
  the Backtest screen gains a "Python lab" panel (`python-lab.tsx`) wired via
  `backtestClient.runPythonStrategy` + `useBacktestScreen.loadResult`. Capability
  is advertised `partial` for `pythonStrategies` (process isolation, not a
  container — stated honestly). Docs updated: `docs/quant-engine.md`,
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H171). Tests:
  `python/tests/test_quant_sdk.py`, `test_quant_sdk_runtime.py`.
  _(Multi-file project authoring + a syntax-highlighting editor remain; the lab
  v1 is a single source module.)_

- **Strategy Development Engine (Phase 4 UI): the dependency-free Visual
  Strategy Builder canvas.** Added `src/components/screens/backtest/
  strategy-canvas.tsx` (node palette grouped by category, drag-to-move,
  typed-port click-to-connect, config inspector from each node's schema,
  compile-with-diagnostics, and save-the-compiled-strategy) and its pure,
  unit-tested core `src/lib/backtest/graph-editor.ts` (node/edge mutation,
  connection rules, editor⇄`StrategyGraph` conversion, geometry, draft
  persistence). Mounted behind a "Visual builder" toggle in the Backtest screen;
  it calls `/quant/graph/*` and never computes signals itself. No new
  dependency (the repo had no graph/ELK library). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H170). Tests: `src/lib/backtest/graph-editor.test.ts` (9).

- **Strategy Development Engine (Phase 4 core): the Visual Strategy Builder's
  typed graph model, versioned node registry and graph→IR compiler.** Added
  `quant/graph_model.py` (validated `StrategyGraph`: identity + typed nodes +
  edges), `quant/nodes.py` (the versioned registry: data/universe, all catalog
  indicators incl. Bollinger/MACD output selectors, logic compare/cross/group/
  constant, trade entry/exit, sizing, stops/targets, risk limits — each with
  typed ports, config schema and a pure `compile`), and `quant/compiler.py`
  (parse → resolve types/versions → validate ports/types → deterministic topo
  order + cycle detection → assemble the canonical `StrategySpec` → shared
  `validate_strategy`; returns structured diagnostics and a spec-path→node-id
  source map). Three agent tools (`compile_strategy_graph`,
  `validate_strategy_graph`, `list_strategy_nodes`) and `/quant/graph/{nodes,
  compile,validate}` routes reuse the same registry/compiler; `backtestClient`
  gains `listGraphNodes`/`compileGraph`/`validateGraph`. The graph is an
  authoring front only — it compiles to the SAME IR the Python lab and AI copilot
  use, so it shares versions, bundles, validation and the whole engine. Docs
  updated: `docs/quant-engine.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H170). Tests:
  `python/tests/test_quant_graph_compiler.py` (15).
  _(The React canvas UI, Python Strategy Lab and AI copilot authoring remain —
  future phases on this same IR + compiler contract.)_

- **Strategy Development Engine (Phase 1–2 foundation): immutable
  content-addressed strategy versions, Strategy IR schema identity, structural
  version diff, and portable strategy bundles.** Added `quant/schema.py`
  (`STRATEGY_SCHEMA_VERSION`, same-major compatibility policy, a lossless
  migration registry, and `spec_content_hash` = sha256 over the canonical IR) and
  `quant/bundle.py` (self-describing zip — manifest + canonical IR + README —
  with size/member caps, path-traversal rejection, schema gating and a
  hash-mismatch warning; import re-validates through the normal schema path).
  `quant/store.py` now records `contentHash`/`schemaVersion` on every version
  (idempotent `ALTER` upgrade), **freezes** a version once an experiment
  references it (`STRATEGY_VERSION_IMMUTABLE`/409 when different content is
  re-saved under it), and adds `version_meta` + `diff_versions`. Three agent
  tools (`export_strategy`, `import_strategy`, `diff_strategy_versions`) and
  matching `/quant/strategies/{id}/export|import|diff` routes reuse the same
  store/engine; the Backtest UI gains a `StrategyPortability` panel
  (list versions, export/import JSON bundle, diff). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H169). Tests: `python/tests/test_quant_versioning.py`,
  `python/tests/test_quant_bundle.py`, `src/lib/backtest/backtest-client.test.ts`.
  _(Python Strategy Lab, visual strategy builder + compiler, and AI copilot
  authoring remain — future phases on the same IR + bundle contract.)_

- **Statistical engine — persistence, feature registry, market-data adapter,
  background jobs, caching and benchmarks (UI still pending).** Added to
  `python/harness/stats/`: `datasets.py` (gateway-backed series/frame resolution
  with honest errors) and `service.py` (cached, persistent, audited execution;
  `execute_with_data`; artifact spilling for >5000-point series); `store.py`
  (`StatsStore` on `agent-memory.db`: `StatsFeature`/`StatsFeatureVersion`
  immutable versions, `StatsAnalysis`, `StatsRun`, `StatsValidation`,
  `StatsAudit`, `StatsArtifact`, gzipped artifacts under `.black-eclipse/stats/`);
  `feature_registry.py` (semver versioning, clone/compare/rollback, dependency
  graph with cycle detection, real evaluate-based validate/preview, pipeline
  steps); `cache.py` (computation-identity LRU cache); `runner.py`
  (`StatsRunner` background jobs: submit/progress/cancel + durable mirror). Router
  `routers/stats.py` grew to 23 operator-gated routes (`/analyses[/run|/submit]`,
  `/jobs`, `/formulas/validate|execute`, `/features/*`, `/datasets/series`,
  `/artifacts/{id}`, `/audit`). Agent tools extended to 31 in `stats/tools.py`
  (registry + formula + data-driven analysis + jobs), allowlisted in `agents.py`.
  Tests: `test_stats_{store,features,datasets,service,runner,performance}.py`
  (40 new; 122 stats tests total). Benchmarks: returns 100k ~36 ms, corr 20×2000
  ~13 ms, 20 features/20k ~39 ms. docs updated: `docs/quant-research/
  IMPLEMENTATION_STATUS.md`, `API_CONTRACTS.md`, `FEATURES.md`,
  `DATA_AND_PROVENANCE.md`, `OPERATIONS.md`, `TESTING.md`, `docs/NAVIGATION.md`.
  _(Research Studio UI and per-workspace authorization remain.)_

- **Statistical Analysis & Feature Engineering Engine (backend): fourteen
  deterministic statistical tools, a safe formula language, agent tools, an
  HTTP surface and the Next.js front door.** New package
  `python/harness/stats/`: shared contract/provenance (`base.py`),
  first-principles distributions (`dist.py`), a dependency-free Nelder–Mead
  optimizer (`optim.py`), OLS/WLS/HC/HAC/ridge/lasso (`linreg.py`), a restricted
  expression parser + whitelist evaluator (`formula.py`), and the fourteen tools
  (`m_returns`, `m_volatility` [incl. EWMA/Parkinson/Garman–Klass/GARCH(1,1)],
  `m_correlation`, `m_beta`, `m_drawdown`, `m_stationarity` [ADF/KPSS],
  `m_cointegration` [Engle–Granger/Johansen], `m_autocorrelation` [ACF/PACF/
  Ljung–Box], `m_regression`, `m_regime` [vol/trend/changepoint/HMM],
  `m_features`, `m_outliers`, `m_leadlag`, `m_information`). Registry
  `registry.py`; agent tools `tools.py` (14 + `stats_capabilities`), allowlisted
  in `agents.py`; boot wiring `bootstrap.py` called from `service.py`; operator-
  gated routes `routers/stats.py` (`/stats/v1`) included by `main.py`; front door
  `src/app/api/stats/[...path]/route.ts` + `src/lib/stats-client.ts`. Tests:
  `python/tests/test_stats_{dist,core,relationships,inference,structure,formula,
  registry}.py` (82 passing). docs updated: `docs/quant-research/
  IMPLEMENTATION_STATUS.md`, `STATISTICAL_METHODS.md`, `API_CONTRACTS.md`,
  `FORMULA_LANGUAGE.md`, `docs/NAVIGATION.md`. _(UI studio, feature
  persistence/versioning, jobs and DB migrations remain — see the tracker.)_

- **Chat-history sidebar simplified: removed Import/Export, selection mode, and
  the Active/Archived/Trash scope tabs.** The panel now shows a single active
  view with search, sort, tag filter, folders (nested), drag, and the row options
  menu. Because the scope tabs were the only way to view archived/trashed chats,
  the row menu's Archive / Move-to-Trash / Restore actions were removed too —
  leaving a single confirmed permanent Delete so nothing can be hidden
  unrecoverably. The archive/trash data fields and pure logic remain (harmless,
  test-covered) for a future re-expose. docs updated: CHANGELOG.md only.

- **Research data: isolated notebook, fundamentals/macro endpoints, provider
  lineage, contract tests.** `research/notebook.py` executes operator analytical
  code in the ONE bounded sandbox against a read-only dataset CSV (no secrets/
  network; `/research-data/datasets/{id}/execute` + a Notebook tab in the
  Research Data screen). `POST /research-data/{fundamentals,macro}` exposes vault
  fundamentals and macro series. Provider descriptors declare an `upstream`
  lineage (shared upstream ≠ independent; unknown ⇒ unknown) consumed by
  verification. New tests: `test_research_notebook.py`,
  `test_market_provider_contract.py` (recorded fixtures; live keyed calls remain
  opt-in). Gateway `get_quote` gains provider pinning. docs updated:
  docs/harness/quant-research-data.md.

- **Chat history becomes a full client-side system: nested folders, tags,
  ranked search, archive, trash + undo, bulk actions, export/import, and
  mouse/touch drag.** Everything the earlier pass listed as missing is now built,
  except cross-device sync (deliberately out of scope — localStorage only, no
  auth). Data: `Conversation` gained `tags`/`archivedAt`/`deletedAt`;
  `ChatFolder` gained `parentId`/`order` for nesting + ordering. New pure logic in
  `chat-organization.ts` (folder forest with cycle safety, ranked AND-token search
  with body snippets, scope/tag filtering) and `chat-export.ts` (versioned JSON
  envelope, defensive parse, additive id-based merge). Hook gained tag/archive/
  trash/restore/purge/bulk/move-folder/import handlers. UI split into
  `chat-history-panel.tsx` (toolbar, scope tabs, tag filter, folder tree, bulk bar,
  undo toast, pointer-based drag working on touch) and `chat-history-menu.tsx`
  (options menu with tag editor). Legacy rows migrate on load. Tests: 21
  organization + 5 export. docs updated: ARCHITECTURE.md (Layer 0 persistence),
  CHANGELOG.md.

- **Interactive Response Engine — full build-out (planner, controls, exports,
  artifacts, financial charts, Mermaid).** Completes the engine's deferred
  capabilities, all reusing existing infrastructure: a deterministic **response
  planner** (`src/lib/response/planner.ts`) upgrades plain-Markdown GFM tables →
  interactive tables and link-only source lists → citations for **every** settled
  answer (no model call, byte-identical prose otherwise); **backend-driven
  controls** (`src/components/response/controls-block.tsx`) compose a validated
  prompt and re-enter the **existing** agent loop via a new `onFollowup` callback
  threaded through both chat surfaces; **export** (`src/lib/response/export.ts`)
  adds JSON / CSV / PNG (ECharts `getDataURL` via a new instance registry) / PDF
  (lazy `jspdf` + `jspdf-autotable`, embedding mounted charts and reporting
  anything it cannot embed in an appendix); **Artifact Center save** reuses the
  existing `registerArtifact` → `POST /api/artifacts`; a **`financial_chart`**
  block wraps the existing `ChartWidget` (live OHLCV, never embedded price data);
  a **`mermaid`** block renders sequence/ER/class/gantt diagrams with
  `securityLevel: 'strict'` (lazy-loaded; `mermaid` 12.1.0 added). Per-response
  export/save actions live in `src/components/response/response-actions.tsx`. New
  tests: `contract-extended.test.ts`, `planner.test.ts`, `export.test.ts`. docs
  updated: docs/interactive-response-engine.md, docs/NAVIGATION.md,
  docs/DECISIONS.md (ADR-043 amendment), skills/ARCHITECT.md (ADR-043 amendment).

- **Research data becomes a proper system: REST API, Dataset/Quality UI,
  point-in-time universes, dataset analytics.** `python/harness/routers/research_data.py`
  exposes the research services over HTTP (operator-gated, `/research-data/*`,
  included in `main.py`); `src/app/api/research-data/[...path]/route.ts` proxies
  it and `src/components/screens/research-data/research-data-screen.tsx` is a new
  `research-data` AppTab (Dataset Explorer + Builder + Data Quality Center +
  Provider view). Point-in-time universe membership lives in
  `python/harness/market/universe_store.py` (effective-dated, SCD-2) with
  `record_universe`/`list_universes` and `get_universe` as-of resolution. New
  `analyze_dataset` runs deterministic analytics (summary/returns/volatility/
  max_drawdown/sharpe/correlation) over an immutable version. New tests:
  `test_research_data_api.py` + universe/analyze tests in
  `test_research_data_tools.py`. Size pins updated (`main.py` kept ≤1200,
  `stock-chat.tsx` re-pinned). docs updated: docs/harness/quant-research-data.md,
  docs/NAVIGATION.md.

- **Chat history: drag a chat onto a folder to file it; folder options redesigned.**
  Chat rows are now HTML5-draggable and every folder group (plus "Unfiled") is a
  drop target that highlights while hovered and moves the chat on drop — a faster
  path than the menu's "Move to". The folder options popover was rebuilt: an
  identity header (color chip + name + chat count), a labelled color grid, and
  roomier action rows, with "Delete folder" now stating that its chats move to
  Unfiled. `docs updated: CHANGELOG.md only`.

- **Interactive Response Engine — structured, interactive assistant answers.**
  An assistant turn may now carry ONE fenced ```eclipse-response block whose JSON
  body is validated by a versioned zod contract and rendered through a registered
  component registry inline in chat: metric grids, sortable/filterable/paginated
  tables, ECharts charts (line/area/bar/stacked/grouped/pie/scatter/histogram/
  heatmap), dependency-free SVG diagrams (flow/dependency/state), timelines,
  citations, callouts, key-value panels, collapsible details and tabs. This closes
  the audit's documented gap (`docs/chat-ui-audit.md` §16, Risk R7 — "no
  structured wire contract"). New `src/lib/response/` (contract/parse/chart-option/
  diagram-layout + tests) and `src/components/response/`; `components/chat/
  markdown.tsx` intercepts the fence and gained a `streaming` prop (threaded from
  `chat-history.tsx`); per-block error boundaries; hard resource limits; unknown/
  malformed blocks degrade to diagnostics, never code. Charts lazy-load ECharts;
  persistence/reopen reuse the existing `Message.content` store. `zod` promoted to
  a direct dependency; `prompts.py` gained a "Structured answers" section.
  docs updated: docs/interactive-response-engine.md (new), docs/NAVIGATION.md,
  docs/DECISIONS.md (ADR-043), skills/ARCHITECT.md (ADR-043).
- **Research data: trading calendar, currency conversion, corporate actions,
  universe resolution, export/refresh, point-in-time and Artifact linkage.** Adds
  the tools the research surface previously lacked, all backend and credential-free:
  `get_trading_calendar` (`market/calendar.py` — deterministic US-equity sessions +
  holidays + DST, FX 24/5, crypto 24/7, no `tzdata` dependency; session-aware
  freshness integrated into `quality.check_freshness` so a closed market is
  `closed_recent`, never mislabelled `stale`); `get_currency_conversion` (direct
  FX + documented cross-via-USD, `derived` labelled); `get_corporate_actions`
  (provider-supplied, honest UNAVAILABLE when absent); `get_universe` (resolves
  current identities; an `as_of` is marked `asOfUnknown` — survivorship guard);
  `export_dataset` (CSV/JSON) and `refresh_dataset` (new immutable version);
  point-in-time `as_of` on `query_dataset`/`export_dataset` with `pitUnknown`
  honesty. New `market/series_store.py` persists normalized bars on
  `agent-memory.db`; built datasets are catalogued through the Artifact Center.
  Secondary handlers split into `market/research_tools_ext.py` to stay under the
  size budget. New tests: `test_market_calendar.py`, `test_market_series_store.py`
  + additions to `test_research_data_tools.py`. docs updated:
  docs/harness/quant-research-data.md, docs/NAVIGATION.md.

- **Mount the Quant Research workspace as the `backtest` AppTab.** The existing
  `BacktestScreen` was exported but never mounted; it is now the `backtest` AppTab
  (deep link `/?tab=backtest`, reachable from the command palette as "Quant
  Research"), following the Pages/UI-Builder pattern — deliberately not a sidebar
  section. Edits: `src/lib/app-tabs.ts` (+`backtest`), `src/lib/search/deep-link.ts`
  (`APP_TABS`), `src/lib/i18n/nav.ts` + `dictionaries/en.ts` (`nav.backtest`),
  `src/lib/search/registry.ts` (`page-backtest` search entry) and
  `src/components/screens/stock-chat.tsx` (lazy mount). docs updated:
  docs/harness/quant-research-data.md.

- **Fix chat-history follow-ups: empty folders now appear; the list scrolls
  instead of pushing the nav down; option menus no longer clip.** `groupConversations`
  was dropping empty groups, so a newly created folder was invisible — every
  folder now renders even with zero chats (the trailing "Unfiled" bucket still
  only appears when non-empty). The sidebar list is bounded again
  (`max-h-[45vh]` + its own scrollbar) so it never grows the sidebar and shoves
  the navigation below it. Row/folder option menus moved into a `createPortal`
  popover anchored to the opening button (with up-flip), so the scroll container
  can no longer clip them. docs updated: CHANGELOG.md only.

- **Quantitative research data infrastructure: independent verification, versioned
  datasets and a shared research tool surface.** The market layer gains five named
  verification policies (`cached_fast`, `fresh_preferred`, `cross_verified`,
  `historical_reproducible`, `strict_research`) and a deterministic cross-source
  verification engine that classifies an observation as verified/unverified/
  conflicted/failed, records material conflicts and never averages disagreeing
  sources (`python/harness/market/verification.py`). The Market Data Gateway gains
  provider pinning (`provider=`) and `candidate_providers()` so a caller can
  deliberately retrieve an INDEPENDENT source; the provider registry gains
  intervals, adjustment support, a timeliness taxonomy (realtime/delayed/eod/
  reference) and an entitlement field. Deterministic transforms
  (`python/harness/quant/transform.py`: OHLCV resampling with partial-bucket flags
  and explicit-only alignment) and an immutable, content-hashed, versioned dataset
  store with manifests (`python/harness/quant/dataset_store.py`) are added. A new
  shared research tool surface (`python/harness/market/research_tools.py`:
  `get_market_data`, `verify_market_data`, `resample_data`, `align_timeseries`,
  `build_research_dataset`, `query_dataset`, `compare_datasets`,
  `get_data_quality_report`, `get_data_provenance`, `resolve_instrument`,
  `list_providers`, `get_provider_health`, plus dataset version listing) is
  registered in `market/bootstrap.py` and added to the Eclipse agent allowlist
  (`agents.py`); the quant `run_backtest`/optimization tools are also now
  allowlisted. New tests: `test_market_verification.py`, `test_quant_transform.py`,
  `test_quant_dataset_store.py`, `test_research_data_tools.py`.
  docs updated: docs/harness/quant-research-data.md (new), docs/NAVIGATION.md.

- **Chat history gains folders, colors, pinning, rename and search.** The sidebar
  recent-chats list was a flat localStorage array with only delete. It now
  supports user-created folders (collapsible, colored), per-chat accent color,
  pin-to-top, inline rename, move-to-folder, and a search box filtering across
  titles and message bodies with recent/created/alpha sort. New organization
  layer: `src/lib/chat/chat-organization.ts` (conversation + folder types, color
  palette, localStorage helpers, pure filter/sort/group view logic) and
  `src/lib/chat/use-chat-organization.ts` (the state/handlers hook); UI extracted
  to `src/components/layout/chat-history-panel.tsx`; `sidebar.tsx` takes one
  bundled `organization` prop instead of a dozen callbacks. Legacy transcripts
  are migrated on load (backfilled `createdAt`/`folderId`/`color`/`pinned`); the
  new `chat_folders_v1` key is additive so no existing history is lost.
  docs updated: ARCHITECTURE.md (Layer 0 persistence bullet).

- **Re-pin the system-prompt size ratchet for the Eclipse UI authoring capability.**
  `prompts.py` gained a "Pages, widgets and tools" paragraph for the `ui_*` tools
  (compose pages/widgets, file engineering tasks), growing the prompt from 23725
  to 25217 chars. The size-ratchet tests in `test_memory_tools.py` and
  `test_phase_s_stabilization.py` were re-pinned to 25217 with updated rationale,
  matching the established convention (raise only for a genuinely new capability).
  no doc change — test-only ratchet update; the capability itself is already
  documented.

- **Investor Eye: event click opens the dossier popup; dossier reads vertically;
  lens filters match type OR channel; window-switch feedback.** (1) Clicking an
  event — a map pin or a Live Event Stream row (or Enter on a focused row) — now
  opens the full `EventDossierOverlay` directly via a new `handleOpenEvent`;
  keyboard j/k stepping still only peeks the right rail, so arrowing never
  throws a modal. (2) The wide dossier no longer flows into two `lg:columns-2`
  columns (which read left-to-right); `EventPanel` in `wide` mode is now a
  single vertical column that spans the (wide, `max-w-6xl`) overlay, and the
  duplicate close button in the panel header is suppressed in `wide` mode — it
  stacked a second cross under the overlay's own, giving two crosses. (3) `LiveFeed` lenses and the dashboard
  `InvestorEyeWidget` lens now match on event TYPE **or** economic CHANNEL (the
  same rule the map layers use), so an event classified under a neighbouring
  type but transmitting through Energy/Trade/Shipping is no longer dropped. (4)
  A "Loading <window> window — still showing <old>h" chip appears while a
  time-range change is assembling (a cold window takes ~15s and previously
  showed the old window's data with no feedback, so the range filter looked
  inert). (5) The main screen's detail section no longer uses `lg:columns-3`
  multi-column flow (which packed What Changed / Alerts / Risk / Transmissions /
  Conflict research / Portfolio / Source health left-to-right); it is now a
  single vertical stack, matching the dossier. (6) The event **heatmap** layer is
  on by default and its wide cells were the pointer target for much of the map,
  but it had no click handler — clicking a hotspot silently did nothing. It now
  selects the cell's representative event (`buildEventHeatmapLayer` takes the
  `onSelect` callback), so a hotspot opens that event's dossier. (7) The
  dashboard `InvestorEyeMapWidget` — which deliberately embedded no dossier —
  now opens the same `EventDossierOverlay` (lazy-loaded) on pin/hotspot click.
  `npx tsc --noEmit` clean; `vitest` 2524 pass.
  no doc change — UI/UX behavior fixes within the existing contract; no data
  shape, setup, or architecture change.

- **Remove the `/login` page.** Deleted `src/app/login/`; `HARNESS_AUTH=off` in the
  local `.env` (gitignored) — no sign-in. The `/api/auth/*` API and middleware
  remain but are inert while auth is off. no doc change — page removal; auth is
  local env only.

- **Agentic sidebar trimmed: Tasks, Pages and UI Builder removed from the nav.**
  Dropped the `tasks`, `pages` and `ui-builder` entries from
  `DEFAULT_SIDEBAR_SECTIONS` (`src/lib/sidebar/config.ts`) and the now-unused
  icon imports; updated the Agentic-list and shortcut-count guards in
  `config.test.ts`. The screens still mount via keep-alive and remain reachable
  by deep-link (`/?tab=…`) — only the sidebar entries are gone.
  no doc change — nav list edit only (no contract/architecture change).

- **Assistant now shows the model that answered, and the floating dock renders
  the full turn.** Two gaps behind "it doesn't show the model / output is wrong".
  (1) **Model display**: the run record's `provider`/`model` now ride on the
  `client.final` frame (`api/harness/chat/stream/route.ts`), are normalized into
  the `final` UI event (`lib/agent/events.ts`), carried on `AssistantTurn.model`
  (`use-agent-run.ts` / `response-model.ts`) and on `Message.model`
  (`types/chat.ts`), and rendered as a quiet `Cpu` model chip above each finished
  assistant reply (`chat-history.tsx`). The dock's pill now shows the **real**
  model that answered (falling back to the configured provider label until one is
  known), never a fabricated name. (2) **Dock output completeness**: the dock's
  turn sink (`chat-dock.tsx`) dropped `memory`, `documents`, `codeVerification`,
  `autonomy`, `capability` and `runId`, so the memory/document panels, the code
  capability panel and the run-explanation panel never rendered in the floating
  assistant even though they do in the ChatBot tab; it now forwards every field,
  matching the Chat tab. Additive and honest — a run that reports no model simply
  shows no chip. `npx tsc --noEmit` clean.
  docs updated: `docs/chat-ui-audit.md` (`client.final` frame), `docs/CHANGELOG.md`.

- **Fundamentals P2–P4: filings framework, cross-source reconciliation,
  persistence hooks.** (P2) Official-filings **adapter registry**
  (`src/lib/fundamentals/filings/registry.ts`) — the `eclipse-filings` provider now
  dispatches through it, so adding a market is one adapter; PSX (PK) registered.
  (P3) `src/lib/fundamentals/reconcile.ts` (`reconcilePeriods`) deterministically
  compares the SAME metric/period across every source that returned periods and
  surfaces material disagreements (>threshold) — wired into `buildSnapshot` as
  `cross-source disagreement` insights (never averaged away), plus `PeriodConflict`
  on `AssembleInputs`. (P4) The provider order/registry is the coverage surface
  (eclipse-filings before yahoo; keyless). Tests: `filings/registry.test.ts` (5),
  `reconcile.test.ts` (6), `filings/psx.test.ts` (3). Known blocker: India's
  official portals (BSE/NSE) return 403 to server-side fetches — a real
  anti-bot limit that needs the browser runtime (documented, not faked). Full
  `vitest` 2524 (2 failures are a concurrent sidebar-guard change, not this work),
  `next build` + `tsc` + `eslint` clean; server restarted.
  docs updated: `docs/CHANGELOG.md`.

- **Capability Extension Phase A: live Pages — the UI-Engineering bridge.** The
  agent/UI-authored blueprints (UI-Engineering runtime, `agent-memory.db`) are no
  longer stranded in a separate store: a new **Pages** app tab
  (`src/components/screens/pages/pages-screen.tsx`, `AppTab 'pages'`) lists the
  saved blueprints and renders the selected one through the REAL
  `CustomizableWorkspace` + `renderDashboardWidget`, so an agent-composed page is
  a visible, usable page (add/rearrange widgets like the Command Center; "Save to
  page" writes the arrangement back as a new blueprint revision via
  `ui_save_layout`; "Revert" discards the local cache). New pure, tested bridge
  `src/lib/ui-engineering/live-page.ts` (`blueprintLayoutToKernel` /
  `kernelLayoutToWire` / `pageStorageKey`) is the ONE wire↔kernel layout
  translator. Tab wired through `app-tabs.ts`, `sidebar/config.ts`,
  `i18n/nav.ts` + `en.ts` (`nav.pages`), `search/deep-link.ts`, and
  `stock-chat.tsx`.
- **Agent glue: Eclipse now knows the `ui_*` tools exist.** Added a "Pages,
  widgets and tools" section to `ECLIPSE_AGENT_SYSTEM_PROMPT`
  (`python/harness/prompts.py`) documenting the Compose/Engineer flow and
  `ui_classify_request`. Fixed the Compose/Engineer classifier
  (`python/harness/ui/mode.py`): "new widget"/"create a widget"/"widget that" and
  "new tool" now signal **Engineer** (a genuinely new capability), while
  restyling an existing widget ("change the design"/"restyle") stays **Compose**.
  This is why "create a new widget" previously degraded to adding an existing one.
- Plan: `docs/harness/capability-extension-plan.md` (Phases A–E). Tests:
  `live-page.test.ts` (6), `test_ui_mode.py` (+4). Full `vitest` 239 files /
  2524 tests + UI `pytest` 31 + `tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/capability-extension-plan.md`,
  `docs/ui-engineering.md`.

- **Capability Extension Phase B-rest: the run learns the page the user is on.**
  The chat forwards the focused page with the run — a client focus store
  (`src/lib/ui-engineering/ui-focus.ts`, set by Pages/UI Builder, read by
  `use-agent-run`) → `ChatOptions.uiContext` → `buildPayload` → the
  `/api/harness/chat[/stream]` routes sanitize it → `startChatRun`/`chatWithAgent`
  put it in `input.context.ui` → `graph.py::_ui_focus_block` renders a per-run
  "Current UI page" prompt note (cache-key excluded) naming the blueprint. So
  "change my widgets" resolves to the actual page. Tests `test_ui_focus.py`.
- **Phase C: Engineer requests actually run.** `UiEngineering.start` left the plan
  in `PLANNING`, which the task scheduler skips — the root cause of "create a new
  widget" finishing with nothing. It now starts the plan (RUNNING) so the
  existing scheduler dispatches the task, and pins the invoking run's model on the
  plan metadata (`ctx.model_settings`) so the task uses the operator's provider.
  Tests `test_ui_engineering.py`.
- **Phase D (started): engineering-task visibility.** The UI Builder now polls
  `GET /ui/engineering/{planId}` and shows a live status card (plan + task
  statuses) after filing an engineering task.
- **Phase E (started, one-way): the Command Center mirrors to a blueprint.**
  `CustomizableWorkspace` gained `onLayoutChange`; the dashboard debounce-publishes
  its board into a per-dashboard UI blueprint (`dashboard-blueprint.ts`,
  localStorage id map + idempotent create), so Eclipse can see and edit the board
  the user actually has and it appears as a page. The reverse (agent edit → live
  dashboard) is the documented follow-up.
  Full `vitest` 239/2524 + UI `pytest` 62 + `tsc`/`eslint` clean.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/capability-extension-plan.md`.

## 2026-10-09

- **Fundamentals P1: first-party official-exchange provider (PSX / Pakistan).**
  New `src/lib/fundamentals/filings/psx.ts` parses the PSX data-portal company
  page (`dps.psx.com.pk/company/<SYM>`) — the exchange's OWN annual key financials
  table (Sales, Profit after Taxation, EPS; "in thousands except EPS") —
  deterministically with cheerio into real periods (thousands → base, PK fiscal
  year end, sorted oldest→newest). New provider
  `src/lib/fundamentals/providers/eclipse-filings.ts` (`id: eclipse-filings`,
  keyless, `supports` PK) is registered in `PROVIDER_ORDER` before Yahoo, with
  `FundamentalProviderId`/`PROVIDER_LABELS`/`SOURCE_LABEL` extended. So PK stocks
  that had NO filings-backed fundamentals now show official exchange statements
  (`primarySource: eclipse-filings`), reducing third-party reliance. Verified
  live: OGDC, LUCK, ENGRO, HUBC, MCB, MARI, SYS each → 4 real periods. Tests
  `filings/psx.test.ts` (3, incl. the page's malformed `<tbody>`-in-`<thead>`).
  Full `vitest` 2508 + `next build` + `tsc` + `eslint` clean; server restarted.
  docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: readable rail, full dossier overlay, AI-setup CTAs, agent world-events tool.**
  Right rail widened to 440/460px and retyped (11–13px) for readability, with
  the event dossier prioritised over the country panel; a wide, two-column
  **full event dossier overlay** opens via "Open dossier"/double-click (Esc/back,
  `store.dossierOpen`); the Explain/Research panels now offer an actionable
  "Open AI settings" deep link (`be:navigate` → Settings modal at the AI
  section); and the authoritative Python runtime gains `get_world_events` over a
  new `world_events` JDdS bridge capability. Bundles in-flight ChatBot-page
  customization. Full `vitest` 235 files / 2505 tests green, `tsc` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5s).

- **Fundamentals: first-party web-extraction fallback (parse research into
  figures).** New deterministic `src/lib/fundamentals/research-parse.ts`
  (`parseFinancialFacts`/`parseNumber`) pulls standard line items (revenue, gross/
  operating/net income, EBITDA, EPS, margins, OCF/FCF, capex, debt, cash, assets,
  equity, ROE, market cap, P/E …) out of the web-research engine's verified text
  into `{key,label,value,unit,raw}` — conservatively (metric keyword + number in
  the same sentence, word/suffix rescaling, percent requires a `%`), never
  inventing a value. `companyBriefQuestion` now explicitly requests those figures
  with period + currency, and `ResearchedFinancialsSection` renders them as a
  metric grid (with the source sentence as the tooltip) above the findings and
  collapsible sources. This is P0 of the first-party fundamentals plan (reduce
  third-party API reliance); full official-filings extraction (P1/P2) remains.
  Tests `research-parse.test.ts` (8). Full `vitest` 2505 + `next build` + `tsc`
  + `eslint` clean. docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: readable right rail (was too narrow / too small).** The hero's
  right rail was 360px with 8–10px type, so events/countries were unreadable.
  Widened to `440px` (lg) / `460px` (xl) and taller (`62vh`); the Live Event
  Stream and Country panel now use 11–13px type, larger markers, more row
  padding and 3-line titles (was 2). The event dossier is prioritised over the
  country panel in the rail (clicking a conflict shows the event, not a stale
  country). `Block`/`Row` dossier primitives bumped 9–10px → 11–12px.
  Presentation only; no data change. Full `vitest` **235 files / 2505 tests
  green**, `tsc` clean. docs updated: `docs/investor-eye-architecture.md` (§5s).

- **ChatBot landing wordmark default → Michroma; Background "Type" order
  Solid-first.** `DEFAULT_WORDMARK_FONT` in `src/lib/backgrounds.ts` now defaults
  to Michroma (`var(--font-michroma), system-ui, sans-serif`) instead of Bodoni,
  matching the shipped preset wordmark face; existing saved prefs keep their
  stored font. The backdrop "Type" options are reordered so **Solid** reads first,
  then **Image** (default mode is unchanged). New users/reset now get the
  Michroma wordmark. `backgrounds.test.ts` + `tsc` clean. no doc change — default
  value + option order only, no contract or architecture change.

- **Company detail: AI overview moved to the top-right (visible without
  scrolling).** The AI brief card is now the first card in the at-a-glance rail
  beside the chart, so it renders on the first screen instead of below technical
  /risk. Presentation only. `tsc`/`eslint` clean, `next build` green.
  no doc change — layout only.

- **Investor Eye: full event dossier + actionable AI-setup.** Clicking an event
  keeps the compact right-rail peek, but an **"Open dossier"** button
  (or double-click) now opens a wide, two-column, Esc-dismissible **full event
  dossier overlay** (`event-dossier-overlay.tsx`, portaled like `FullPageMap`;
  `EventPanel` gained `onOpen`/`wide`). The dead "AI not configured" states are
  now **actionable**: Explain/Evidence/Conflict-research panels show an
  "Open AI settings" button that deep-links to Settings → AI Agent via a new
  SSR-safe `navigation.ts` (`be:navigate {tab:'settings', section:'ai'}`; the
  shell's handler now opens the Settings modal at a section). Escape ownership
  handed to the dossier while open. Tests: `navigation.test.ts` (+2). Full
  `vitest` **234 files / 2497 tests green**, `tsc` clean. docs updated:
  `docs/investor-eye-architecture.md` (§5s).

- **ChatBot Page customization tab + working conversation font.** New
  **Customization › ChatBot Page** tab (`src/components/screens/chatbot-page-settings.tsx`):
  the backdrop/landing-wordmark controls move here out of Settings › General
  (General now links nowhere — the tab owns the whole ChatBot-page look),
  alongside a new **conversation font** picker. New store
  `src/lib/chat/appearance.ts` (`be_chat_appearance_v1`) offers the self-hosted
  wordmark typefaces + an "App font" default, applies the pick as `--chat-font`
  on `<html>`, and `ChatHistory`/the chat shell read it via
  `var(--chat-font, var(--font-sans))` — so choosing a face really changes the
  messages and composer instead of a system-only stack that silently fell back
  to the app font. Verified live: `--chat-font` → Orbitron on the chat
  container; the ChatBot Page tab renders the font grid + moved backdrop card.
  `tsc` + targeted `eslint` clean; `vitest` green (the only size-budget failure
  is the pre-existing concurrent `data-bridge.ts` growth). docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **Investor Eye: AI conflict search + `get_world_events` Python tool.** (1) New
  "Conflict research (AI, cited)" panel in the analysis row drives the shared
  Evidence & Research Engine for a cited conflict situation report over the
  window (shared `research-findings.tsx`); it does NOT fabricate map pins —
  findings are labelled research. Pure `windowConflictQuestion` mandate (+3
  tests). (2) New read-only JDdS bridge capability `world_events` (own module
  `src/lib/harness/world-events.ts`, so ratcheted `data-bridge.ts` does not grow)
  + Python tool `get_world_events` (`python/harness/world_tools.py`, registered
  in `service.py`) exposing geopolitical events to the authoritative agent
  runtime, with source-failure/no-match honesty. Full `vitest` green
  (233 files/2495 tests; one unrelated concurrent edit to
  `customization-settings.tsx` trips the size-budget ratchet), `tsc` clean,
  targeted Python tool tests 625 passed. docs updated:
  `docs/investor-eye-architecture.md` (§5r).

- **Asset detail: load ALL assets — indices + on-demand resolution.** Two gaps
  closed in `/api/asset-details`: (1) **indices** (`^GSPC`, `^IXIC`, …) now
  resolve from `IndexQuote` (canonical ticker + aliases) → real name + level;
  (2) **symbols the vault never ingested** (e.g. `SPY`, `SGOV`) now resolve
  **on-demand** through the shared Yahoo chart fetch (`yahooChartCandidates` +
  `fetchYahooChartSeries`, extended to carry `longName`/`shortName`/`exchangeName`/
  `instrumentType`). Result: any Yahoo-resolvable instrument opens a detail page
  instead of a dead "not found". Verified live: `^GSPC`→S&P 500 7811.54,
  `^IXIC`→Nasdaq Composite, `SGOV`→iShares 0-3 Month Treasury ETF 100.51,
  `SPY`→State Street SPDR S&P 500 ETF Trust 778.57, `GC=F`→Gold. Full `vitest`
  2492 + `next build` + `tsc` + `eslint` clean. docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: shared Evidence & Research Engine in the event dossier.** New
  `components/investor-eye/event-research.tsx` + `use-event-research.ts` drive the
  SAME Python web-research engine (via `/api/research/*`) used by the Research
  screen and company brief. LAZY (no auto-run on dossier open), cached per event,
  renders sources/claims(status)/citations/conflicts + the run's deterministic
  answer; 503-honest when the runtime is absent. Mandate built by pure, tested
  `research-question.ts` (+4 tests). This is the concrete "use AI to corroborate
  a conflict" path. Map-level promotion of AI findings to `AI-INTERPRETED` events
  and Python-native world tools remain (documented). Full `vitest` **233 files /
  2492 tests green**, `tsc` clean. docs updated:
  `docs/investor-eye-architecture.md` (§5q, Phase 4 event level).

- **Company detail: commodities/FX identity, market qualifier, AI overview moved
  below.** `/api/asset-details` now resolves catalog symbols (gold `GC=F`,
  `EURUSD=X`, …) → a synthetic asset (`found: true`, name/sector/marketId
  `COMMODITY`/`FX`), so clicking a commodity/FX row (already wired via
  `handleSymbolClick`) opens a detail page with a proper identity instead of "not
  found". Header now shows a market/exchange qualifier chip next to the symbol
  (disambiguates cross-market collisions like BNB CRYPTO vs DE). AI overview row
  moved below the technical/risk row (bottom of the page). Verified live:
  `/api/asset-details?symbol=GC=F` and `EURUSD=X` return `found:true`. Full
  `vitest` + `next build` + `tsc` + `eslint` clean. docs updated:
  `docs/CHANGELOG.md`.

- **Investor Eye: fix intermittent/missing conflicts + honest coverage.** Root
  causes audited: (1) GDELT only fetched the newest 15-minute bulk file, (2)
  `assembleState` never replayed persisted events, (3) the relevance gate
  silently dropped low-signal material conflicts, (4) no GDELT retry, (5) no way
  to see *why* the Conflict layer was empty. Fixes: rolling GDELT window over the
  last N 15-min slots with bounded concurrency + provider-id dedup + transient
  retry; persisted-event replay into the window (flagged `replayed`, never
  re-persisted); a material-conflict relevance floor (`quadClass===4` /
  `goldstein<=-5`); and a new pure `coverage.ts` (`observed|quiet|degraded|
  unavailable`) surfaced as a `retained` badge in the dossier, a `N retained`
  count in the map footer, and an amber explanation under the map when no
  conflicts are plotted. Tests: `gdelt-window.test.ts` (8), `coverage.test.ts`
  (7), relevance +2; full `vitest` **232 files / 2488 tests green**, `tsc` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5q). ReliefWeb was
  evaluated and rejected as a zero-config source (v2 now needs a pre-approved
  `appname`).

- **Company detail: web-research fundamentals fallback + shared sources
  disclosure.** When a filings-backed fundamentals snapshot has **no statement
  periods** (all providers missed, or the instrument has none — e.g. crypto BNB
  returns a quote-only profile with 0 periods), the page no longer dead-ends:
  it renders `ResearchedFinancialsSection`, which reuses the SAME research run as
  the AI brief (no duplicate search) and shows the engine's verified findings as
  clearly-labelled "Researched financials (web) — not filings-backed", with the
  collapsible sources dropdown. Extracted the shared `SourcesDisclosure` used by
  both AI and researched-financials sections. `useCompanyResearch` already runs
  per symbol, so this adds sourced figures without a second request. Verified:
  `/api/fundamentals?symbol=BNB&market=CRYPTO` → available but 0 periods (now
  falls back); AAPL → 8 periods (unchanged). Presentation + reuse only; no new
  backend. Full `vitest` 2473 + `next build` + `tsc` + `eslint` clean.
  docs updated: `docs/CHANGELOG.md`.

- **Company detail UI: proper AI brief formatting, collapsible sources, layout
  polish.** The AI brief now parses the engine's structured synthesis
  (`Research:`/`Coverage:` meta + titled sections `Findings`, `Partially
  supported`, `Not established / conflicting`, `Conflicts`, `Gaps`, `Excluded`,
  `Citation issues`) and renders each as a real heading + bulleted list with
  severity tones — previously only `FACT:`-prefixed lines matched, so the whole
  answer rendered as flat text. Sources are now a collapsed native `<details>`
  dropdown ("Sources (N) — view") instead of an always-visible list. The AI
  overview is a full-width row below the data (no narrow-column gaps), the section
  icon is neutral (`BookOpen`), and the detailed claims list + inline citation
  clutter were removed. Price-history chart raised to 300px. Presentation only.
  docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: NASA EONET hazard source + per-source ingestion circuit
  breaker.** (1) New keyless source adapter `sources/eonet.ts` adds the missing
  storm/flood/volcano/drought/ice coverage (before: earthquakes + fires only),
  normalizing EONET's observation history to a current position, mapping its
  categories onto the shared hazard vocabulary, scaling severity from the
  provider magnitude only where the unit is known (earthquake magnitude, storm
  wind knots), and using the EONET event id as the stable cluster signature.
  Registered in `sources/registry.ts`, licensed in `SOURCE_CATALOG` (governance
  invariant intact), quality added to `SOURCE_QUALITY`. (2) New
  `circuit-breaker.ts` short-circuits a source after 3 consecutive failures for a
  5-minute cooldown (half-open probe, success closes), wired into `runSource`;
  an open breaker reports the real reason — never a fake healthy-but-quiet
  result. Tests: `sources/eonet.test.ts` (19), `circuit-breaker.test.ts` (6);
  full `vitest` **230 files / 2473 tests green**, `tsc --noEmit` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5p, last-verified bumped).

- **Company detail: wide side-by-side layout; AI overview moved below.** The
  overlay now uses a full-width `max-w-[1760px]` multi-column grid instead of a
  single narrow `max-w-5xl` stack: Row 1 = interactive chart (2/3) beside the
  at-a-glance rail (core metrics, 52-week range, session, risk & income,
  tokenomics, profile, leadership); Row 2 = filings financials (2/3) beside the
  AI brief (moved below the top row); Row 3 = technical + risk side by side;
  Row 4 = news (2/3) beside the AI conclusion. Chart raised to 420px; removed the
  now-orphaned right-pane divider. Presentation only — no contract change.
  no doc change — layout/visual change. Full `vitest` 2448 + `next build` + `tsc` clean.

- **Live quote: reject Yahoo's stale/bogus `regularMarketPrice` (real OGDC root
  cause).** Reproduced live: Yahoo's chart `meta.regularMarketPrice` for
  `OGDC.KA` is **131.87** while the actual latest bar close is **315.91** (and
  `chartPreviousClose` 310.34), so the read-through produced a bogus
  −57.5%/−57.5% quote. `fetchYahooChartSeries` now uses `selectChartPrice()`,
  which trusts the meta price **only when it agrees with the newest real bar**
  (≤5%), else the bar is authoritative. Applies to every instrument that uses
  the shared chart fetch (quotes, ribbon, portfolio, header). Verified live:
  `/api/quote?symbols=OGDC&market=PK` → **315.91 / +1.79%** (was 131.87).
  Test `src/lib/scraper/yahoo-chart.test.ts` (+5). no doc change — bug fix; the
  freshness/provenance contracts are unchanged.

- **Company detail: close the gaps (canonical quote, persisted AI answer,
  leadership).** (1) The overlay now fetches ONE canonical `/api/quote` and uses
  it for the header **and** the metric cards (with source + freshness), so the
  header can never show a different price than the chart/metrics — the structural
  form of the OGDC 306.12-vs-131.87 class (live checks: real PSX OGDC ≈ 306–316
  PKR; 131.87 exists nowhere in JDDS). (2) The web-research engine's deterministic
  `answer` is now persisted (`WebResearchRun.answer`, additive migration;
  `answer=COALESCE(...)` so state-only writes don't clobber it) and returned by
  `GET /research/web/{id}`; the AI brief/conclusion render the typed
  FACT/CALCULATION/INFERENCE/UNCERTAINTY synthesis + claims/citations/sources.
  (3) Leadership is now a real provider integration: the yfinance bridge extracts
  `companyOfficers`, the Yahoo provider normalizes `Officer[]` into
  `CompanyProfile.leadership`, and `LeadershipSection` renders it with an
  "verify against the latest filing" caveat (live: AAPL returned 10 officers incl.
  CEO/CFO). Python tests added (`test_web_research_store.py`, +3); TS
  `fundamentals.test.ts` (+1). Full `vitest` 2443, `next build`, `tsc`, `eslint`
  clean. docs updated: `docs/NAVIGATION.md`, `docs/harness/web-research-engine.md`,
  `docs/CHANGELOG.md`.

- **Company Intelligence: single-page stock detail (no Fundamentals/Technical
  tabs).** The Market Discovery stock overlay is now one continuous, vertically
  scrollable page: quote header (A), AI company brief (B, driven by the existing
  web-research engine via `/api/research/*` with per-symbol caching and honest
  unavailable/retry states), interactive chart (C), inline filings fundamentals —
  overview/statements/valuation/timeline via the new non-tabbed `FundamentalsFull`
  (D/E/F/H), JDDS news feed (G), deterministic technical analysis (I), deterministic
  risk synthesis (J) and an AI conclusion (K). New pure engines
  `src/lib/company/technical.ts` (reuses `chart/indicators/registry`) and
  `src/lib/company/risk.ts` (documented thresholds, evidence-backed), hooks
  `use-company-news`/`use-company-research`, and `src/components/screens/company/sections.tsx`.
  The duplicative right sidebar was removed. Tests `technical.test.ts` (6) +
  `risk.test.ts` (6); full `vitest` 2442, `tsc` and `eslint` clean.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Chore: de-emphasize the ticker example in the freshness guard.** Reworded the
  comments/docs so the guard is described as symbol- and market-agnostic (it is:
  every instrument on both endpoints flows through the same path). No behaviour
  change. docs updated: `docs/harness/market-data.md`.

- **Thesis store: fix revision-versioning collision + real-DB integration test.**
  `updateThesis` recorded a revision at the *prior* version, colliding with the
  origin revision written at creation (`@@unique([thesisId, version])`). It now
  records the resulting version's snapshot, so the full history is preserved and
  the original hypothesis is never rewritten. Added
  `src/lib/theses/store.integration.test.ts` (self-skips when the Thesis tables
  are absent, unique symbol, cleans up). Full `vitest` (2430) + `tsc` clean.
  no doc change — bug fix + test; the contracts in `docs/NAVIGATION.md` are unchanged.

- **Fix: normalize `prisma/schema.prisma` line endings + drop an unused import.**
  The appended Thesis models introduced one CRLF into an LF-only file, which the
  `gitignore-guard` test correctly flagged; normalized back to LF. Removed the
  pre-existing unused `DAILY_HISTORY_TTL_MS` import in
  `/api/price-history`. Full `vitest` (2427), `tsc`, and `eslint` now clean.
  no doc change — regression fix + lint cleanup.

- **Docs: navigation + market-data sync.** `NAVIGATION.md` gains trigger rows for
  the Investment Thesis Tracker and observation freshness, and
  `docs/harness/market-data.md` documents the observation-freshness envelope; both
  `last-verified` bumped to 2026-10-09. docs updated: `docs/NAVIGATION.md`,
  `docs/harness/market-data.md`, `docs/CHANGELOG.md`.

- **Investment Thesis Tracker: API route tests (WIP).** Adds
  `src/app/api/theses/route.test.ts` (5 cases). no doc change — test-only change.

- **Investment Thesis Tracker: analysis tests (WIP).** Adds
  `src/lib/theses/analysis.test.ts` (11 cases). no doc change — test-only change.

- **Investment Thesis Tracker: API + screen (WIP).** `/api/theses` (list/create),
  `/api/theses/[id]`, `/api/theses/[id]/evidence`, `/api/theses/[id]/revisions`
  routes and the `src/app/theses/` screen over the versioned thesis models/lib.
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Investment Thesis Tracker (workstream, WIP).** New Prisma models `Thesis` /
  `ThesisEvidence` / `ThesisRevision` (a thesis is versioned; every edit appends a
  revision so the original hypothesis is never silently rewritten, and evidence is a
  first-class relation with provenance) and a `src/lib/theses/` library
  (`types.ts`/`store.ts`/`analysis.ts`). `npx tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`.

- **Market data: observation freshness guard.** New `src/lib/chart/observation-freshness.ts`
  (metric-and-interval-aware freshness: `live`/`delayed`/`stale`/`historical`/
  `unavailable`/`unknown`, never inventing a timestamp) + tests; `/api/price-history`
  and `/api/quote` now carry observation time/age/freshness so a stale series is
  labelled rather than drawn as current, and the chart surfaces it.
  docs updated: `docs/CHANGELOG.md`.

- **Recovery: test hardening.** `python/conftest.py` now isolates the process-global
  recovery service singleton (`set_recovery_service`) in the autouse fixture, and the
  approve-route API test uses a unique incident per run so it cannot collide with a
  shared database. no doc change — test-only change.

- **Agent Workspace: Context panel leads the right sidebar.** The Agent Workspace
  panel order now lists Context first (plus Output/Changes/Permissions/History) and
  the default/open panel is Context. Presentation only.
  no doc change — UI panel ordering; no architecture, contract or setup change.

- **UI Engineering foundation (TS): component catalog + declarative blueprint
  engine.** New framework-pure module `src/lib/ui-engineering/`: `catalog.ts`
  projects the existing `WidgetDefinition` registry into queryable
  `UiComponentSpec`s (`adaptWidgetDefinition`, `ComponentCatalog.search`,
  `validateComponentConfig`); `blueprint.ts` wraps the existing `WorkspaceLayout`
  in a versioned `UiBlueprint` with strict, truthful validation (unknown
  component / duplicate instance / bad config are reported, not silently
  dropped); `patches.ts` applies a closed set of atomic, catalog-validated
  `BlueprintOp`s in one Immer transaction (delegating layout math to
  `workspace/ops.ts`); `revisions.ts` adds `diffBlueprints`, a bounded
  append-only `BlueprintHistory`, `restoreRevision` and optimistic-concurrency
  `detectConflict`; `store.ts` provides in-memory + localStorage
  `BlueprintStore`s that never overwrite a corrupt payload. 38 vitest cases pass
  and `npx tsc --noEmit` is clean. **Boundary:** frontend foundation only — the
  `ui.*` agent tools, the Python `agent-memory.db` blueprint store, Compose/
  Engineer mode selection and the UI Builder workspace are the next phases.
  docs updated: `docs/ui-engineering.md` (new), `docs/NAVIGATION.md`, this file.

- **UI Engineering runtime (Phases 4–5): server-side blueprint store + `ui_*`
  agent tools.** New `python/harness/ui/` on the ONE `agent-memory.db` and the
  ONE event system: `model.py` (pydantic contracts — `UiComponentSpec`,
  `UiBlueprint`, the workspace layout tree, closed vocabularies; camelCase on
  the wire), `catalog.py` (`UiCatalog` seeded with the foundational component
  kinds + `validate_component_config` with TS-identical semantics), `engine.py`
  (`validate_blueprint` strict/truthful + atomic `apply_ops` with revision bump
  + `diff_blueprints`), `store.py` (`UiStore`: `UiBlueprint`,
  `UiBlueprintRevision`, `UiComponent`, `UiOperation`, `UiIdempotency`), and
  `service.py` (`UiService` = catalog + blueprints + widget ops + optimistic
  concurrency `UI_CONFLICT` + operation audit + `ui.*` events). Registered 24
  `ui_*` tools on the shared `ToolRegistry` (introspection `ui_get_*` +
  `ui_create_page`/`ui_add_widget`/`ui_move_widget`/`ui_resize_widget`/
  `ui_update_widget_config`/`ui_save_layout`/`ui_restore_revision`/
  `ui_preview_change`) and added them to the default agent allowlist; new
  operator-gated routes `routers/ui.py` (`/ui/*`) included by `main.py`; boot
  wiring `install_ui_layer` in `service.py` + the `ui_service` `ToolContext`
  seam in `graph.py`/`tools.py`; Next.js front door
  `src/lib/harness/ui-client.ts` + `src/app/api/ui/[[...path]]/route.ts`; `ui`
  event namespace. Tests `python/tests/test_ui_{engine,store,service,tools,api}.py`
  (38 cases). All UI tools are `permission="read"` — they change only Eclipse's
  own owner-scoped UI config, never filesystem/network/shell/secrets. **Boundary:**
  the runtime seeds the foundational component kinds; syncing the real dashboard
  widget registry into the runtime catalog, the two-mode Compose/Engineer flow
  (Phase 6) and the UI Builder workspace (Phase 8) remain. Verified: pytest
  5086+ passed (16 opt-in skips), `npx tsc --noEmit` clean. docs updated:
  `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Failure Intelligence & Adaptive Recovery — the one cross-subsystem failure
  layer.** New `python/harness/recovery/`: `taxonomy.py` (the shared
  `FailureKind`/`Retryability` vocabulary + pure `normalize_failure`),
  `signature.py` (stable 16-hex signatures + `RecurrenceTracker`), `policy.py`
  (ordered `select_strategies` + `reject_reason`; never retries a deterministic
  failure unchanged, never provider-swaps an auth denial), `controller.py`
  (bounded `RecoveryDecision` + exponential backoff), `store.py`
  (`RecoveryIncident`/`RecoveryAttempt` on **`eclipse-memory.db`**, migration 26),
  `service.py` (classify+decide+persist), `bootstrap.py` (idempotent install +
  Event System failure subscription), `tools.py` (read-only `recovery_*` tools),
  and operator routes `routers/recovery.py` (`/recovery/*`). Wired in `boot.py`
  (not `service.py`/`graph.py`, which are ratcheted) and `main.py`. It composes
  existing taxonomies/diagnostics/retry/routing — it is NOT a second execution
  loop and never runs a tool or mutates task state. 40 new pytest cases pass,
  including a live `tool.failed` → incident end-to-end case. Full suite
  `5129 passed, 16 skipped`; vitest 2375; `npx tsc --noEmit` clean; eval gates
  ALL PASS. The `test_size_budget` ratchet is re-pinned for the pre-existing
  in-flight drift in `graph.py`/`service.py` and `main.py` is held at 1200.
  **Boundary:** the UI panel, automatic strategy execution and feeding incidents
  into skill promotion remain. docs updated: `docs/harness/failure-recovery.md`
  (new), `docs/harness/decisions.md` (ADR-H163), `docs/NAVIGATION.md`, this file.

- **Recovery engine completes the loop: diagnosis, automatic execution, capability
  discovery, incident→skill promotion, and a `/recovery` console.** New in
  `python/harness/recovery/`: `diagnosis.py` (evidence-ranked `DiagnosisEngine` +
  `Hypothesis`; decisive only with strong evidence, otherwise names the gap),
  `executor.py` (`recover_operation` — a bounded async retry/verify loop driving the
  controller, with caller-registered repair handlers and verify-gated success),
  `discovery.py` (`CapabilityIndex` over tools/providers/skills + approval-flagged
  `acquisition_plan`), `learning.py` (`promote_incidents` — inert `LearningCandidate`s
  through the existing learning store). Persistence: migration 27 adds the
  idempotent `RecoveryDiagnosis` table. New read tools `recovery_diagnose` /
  `recovery_discover`; operator routes `POST /recovery/incidents/{id}/diagnose`,
  `POST /recovery/promote`, `GET /recovery/discover`. Standalone front door:
  `src/app/recovery/` console (mirrors `/events`), `src/app/api/recovery/[[...path]]`,
  and `src/lib/harness/recovery-view.ts`. 64 pytest cases + `recovery-view.test.ts`;
  full suite `5161 passed, 16 skipped`; vitest 2389; `npx tsc --noEmit` clean; eval
  gates ALL PASS. docs updated: `docs/harness/failure-recovery.md`,
  `docs/harness/decisions.md` (ADR-H164), `docs/NAVIGATION.md`, this file.

- **Autonomy Envelope + deterministic probes + operation/compensation ledger.** New
  in `python/harness/recovery/`: `envelope.py` (`AutonomyEnvelope`/`ActionClass` —
  pre-committed, scoped, expiring permission by action class with risk/reversibility/
  cost/file/network caps and a `HARNESS_AUTONOMY` kill switch; default is
  conservative, effectful classes opt-in), `probes.py` (read-only dependency/provider
  probes registered at boot), `operations.py` (`OperationLedger` — idempotency-keyed
  side-effect tracking + compensation bookkeeping; migration 28 `RecoveryOperation`).
  The executor now acts unattended ONLY inside the envelope (else returns
  `outside_autonomy_envelope`). New operator routes `GET/PUT /recovery/envelope` and
  `GET /recovery/operations`; console gains an "Autonomy & operations" tab. Fixed a
  variable-shadowing bug in the executor found by the new tests. 87 pytest cases;
  full suite `5190 passed, 16 skipped`; vitest 2392; `npx tsc --noEmit` clean; eval
  gates ALL PASS. docs updated: `docs/harness/failure-recovery.md`,
  `docs/harness/decisions.md` (ADR-H165), `docs/NAVIGATION.md`, this file.

- **Autonomy made durable + coordinated: persisted envelope, per-signature repair
  lease, one-off operator approvals, and compensating actions.** Migration 29 adds
  `AutonomyEnvelope` (a `PUT /recovery/envelope` now persists and survives restart),
  `RecoveryLease` (two workers never repair the same root cause at once; the executor
  returns `repair_lease_held`), and `RecoveryApproval` (`POST
  /recovery/incidents/{id}/approve` authorizes exactly one out-of-envelope strategy
  for one incident). New `recovery/compensation.py` `compensate_pending()` runs
  caller-registered compensation handlers, envelope-gated under `COMPENSATE`. The
  console gains a decision + "Approve strategy" control in the incident detail. 99
  recovery pytest cases; full suite `5202 passed, 16 skipped`; vitest 2394;
  `npx tsc --noEmit` clean; eval gates ALL PASS. docs updated:
  `docs/harness/failure-recovery.md`, `docs/harness/decisions.md` (ADR-H166),
  `docs/NAVIGATION.md`, this file.

- **Auto-reproduction + hard safety invariants (production hardening).** New
  `recovery/reproduction.py` (`ReproducerRegistry`/`reproduce` — a caller-registered
  reproducer per failure kind, run under a hard timeout; a successful reproduction
  becomes evidence and makes the diagnosis decisive) with operator route
  `POST /recovery/incidents/{id}/reproduce`. New tests pin the trust properties:
  `test_recovery_safety.py` (envelope cannot be bypassed, kill switch, non-retryable
  never retried, bounded recovery, scoped one-off approval, no secret persisted) and
  `test_recovery_concurrency.py` (repair-lease exclusivity under thread contention).
  `docs/harness/failure-recovery.md` gains a Production & operations section. 115
  recovery pytest cases; full suite `5202+ passed, 16 skipped`; vitest 2394;
  `npx tsc --noEmit` clean; eval gates ALL PASS. docs updated:
  `docs/harness/failure-recovery.md`, `docs/harness/decisions.md` (ADR-H167),
  `docs/NAVIGATION.md`, this file.

- **Agent Workspace: new Context tab (session-context gauge).** The right sidebar
  gains a fifth tab showing how full the model's context window is, mirroring the
  OpenCode session sidebar: usage % + a segmented breakdown gauge, plus tiles for
  window / total / input / output tokens, remaining, turns kept-dropped, memories
  and estimated cost, and a per-source legend. It reuses the already-normalized
  store (`state.context`, `state.contextSources`, `state.telemetry`) — no harness
  change — and resolves the window from the declared model catalog. New pure
  module `src/lib/agent-workspace/context-usage.ts` (+9 tests) keeps the math
  testable and honest (unknown window → "Not available", never a faked full bar);
  `totalTokens` is run-cumulative per step, as documented. docs updated:
  `docs/agent-workspace.md`.

- **Agent Workspace tabs gain icons.** The sidebar nav was text-only, so the new
  Context tab had no visual affordance. Each tab now renders its `PANEL_ICONS`
  glyph before the label (Output=Bot, Context=SlidersHorizontal, Changes=FileText,
  Approvals=ShieldAlert, History=Bot); `PANEL_ICONS.output` was added. No behavior
  change — labels, order and attention dots unchanged. no doc change — visual
  affordance only, contracts unchanged.

- **UI Engineering Phases 6 & 8 + event-system shutdown fix.** Two-mode
  generation: `python/harness/ui/mode.py::classify_request` is a deterministic,
  model-free Compose/Engineer/both selector (errs toward Compose so a
  configuration change is never silently turned into a source-code release),
  exposed as the `ui_classify_request` tool and `POST /ui/classify`. UI Builder:
  new `src/components/screens/ui-builder/ui-builder-screen.tsx` (AppTab
  `ui-builder`) — page navigator, component catalog, structural preview,
  properties inspector (config validated against each component's schema),
  AI command panel (classify + add matched component), revision history/restore
  and a diagnostics log — wired via `ui-client.ts` + the `/api/ui` proxy; added
  `POST /ui/blueprints/{id}/widgets/{instance_id}/reorder` (+ client and
  sidebar/nav/i18n entries; sidebar shortcut tests updated). **Defect fixed
  (pre-existing, order-dependent):** `event_system/bus.py::shutdown` awaited
  `asyncio.gather` across worker tasks created on a PREVIOUS loop, raising
  `ValueError: The future belongs to a different loop`, which aborted
  `EventSystem.stop()` before `_started=False`; the next boot's `start()` then
  no-opped and the bus stayed `_closed`, so `publish()` silently dropped events
  (the intermittent `test_recovery_api` live-event failure — reproduced with the
  UI layer disabled). Shutdown is now loop-safe (drains only same-loop workers,
  clears subscriptions) and `stop()` resets `_started` in a `finally`; `start()`
  clears stale subscriptions. Tests: `python/tests/test_ui_mode.py` + reorder/
  classify API cases + `test_events_bus.py` drain case; vitest 220 files / 2389
  tests, pytest green. docs updated: `docs/ui-engineering.md`,
  `docs/NAVIGATION.md`, this file.

- **UI Engineering Agent (Phase 7): Engineer-mode orchestration over the existing
  Task/Plan runtime.** New `python/harness/ui/engineering.py` (`UiEngineering`)
  turns an Engineer/Both-mode request (`mode.classify_request`) into a DURABLE
  plan + task on the EXISTING `python/harness/tasks/` manager (assigned to
  `code-agent` at `edit_verify`, with UI acceptance criteria) — no parallel agent
  loop is introduced; the existing scheduler + code capability execute it. The
  loop closes via `ui_register_engineered_component`, which registers the new
  component in the ONE catalog (so a later Compose request can use it), satisfies
  the "registered in the UI catalog" criterion with evidence, and attaches a
  `ui-component` artifact. Compose-mode requests create no task (`start` says so
  honestly). `UiService` gains an `engineering` collaborator (built from
  `service.tasks` in `bootstrap.install_ui_layer`); four tools
  (`ui_start_engineering`, `ui_engineering_status`,
  `ui_register_engineered_component`, `ui_link_engineering_artifact`) and four
  operator-gated routes (`POST /ui/engineering`, `GET
  /ui/engineering/{plan_id}`, `POST /ui/engineering/{task_id}/components`,
  `POST /ui/engineering/{task_id}/artifacts`); the UI Builder AI panel gains a
  "Create engineering task" action. Tests: `test_ui_engineering.py` +
  engineering API cases (51 UI pytest cases total). docs updated:
  `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Agent Workspace: reopening a past chat restores its run; Context tiles use the
  glass system.** Opening an existing conversation now repoints the workspace at
  that chat's most recent run instead of leaving the last live run's data on
  screen: new `src/lib/agent-workspace/restore.ts` resolves the run id (last
  `Message.runId`, else the runtime's `/api/sessions/{chatId}` run list), rebuilds
  it via new `history.loadRunSnapshot` (replayed event trace **plus** the
  authoritative run record — tokens, model, context window), and commits it with
  the new `store.loadRun` action; a new chat / run-less chat calls `store.clear()`.
  The History tab's reopen uses the same snapshot path. Also fixed the Context
  stat tiles to the design language: `StatTile` now uses `.glass-card-subtle`
  (frosted) instead of a flat fill + `border border-white/8`. New
  `history.applyRunRecord` (+3 tests). docs updated: `docs/agent-workspace.md`.

- **UI Engineering: host-registry ↔ runtime-catalog sync bridge + live-render
  preview.** The UI Builder now pushes the REAL dashboard widget specs into the
  runtime catalog via `syncCoreCatalog()` (`src/lib/harness/ui-sync.ts`,
  adapting `dashboardComponentSpecs()` and POSTing `POST /ui/components`), so the
  agent can Compose with the actual widgets and the specs persist on
  agent-memory.db across restarts — no second hand-maintained widget list in
  Python. Its "live render" toggle draws a widget through the SAME host
  implementation the published dashboard uses (`renderDashboardWidget`) wrapped
  in an error boundary (`ui-builder/live-boundary.tsx`); ids with no host
  renderer fall back to the structural card. `registerComponent` now accepts a
  loose spec (the runtime validates). Tests: `src/lib/harness/ui-sync.test.ts`.
  docs updated: `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Production deployment kit (container).** New `Dockerfile` (Node 20 + Python 3;
  installs Node + Python deps, `prisma generate`, `next build`),
  `docker-entrypoint.sh` (links `jdds.db` / `agent-memory.db` /
  `eclipse-memory.db` / `.black-eclipse/` into a mounted `/data` volume so state
  survives restarts — needed because `src/lib/db.ts` hard-codes `cwd/jdds.db`),
  `docker-compose.yml` (single service, `.env`, `be-data` volume, healthcheck,
  `restart: unless-stopped`), `.dockerignore`, and `.env.example` (all required
  production vars). One container runs both services: the app spawns the Python
  harness as a child, so only port 3000 is exposed. Guide: `docs/DEPLOYMENT.md`
  (new). docs updated: `docs/DEPLOYMENT.md`, `docs/NAVIGATION.md`, this file.

- **UI Engineering production-readiness: boot sync, export/import, CLI, and an
  end-to-end agent proof.** (1) `UiCatalogSync` (mounted in `src/app/page.tsx`)
  seeds the runtime catalog with the real dashboard widgets on first app load,
  so the agent can Compose without opening the Builder. (2) Blueprint
  portability: `GET /ui/blueprints/{id}/export` (self-describing snapshot) and
  `POST /ui/blueprints/import` (validated, stored as a NEW blueprint), surfaced
  as Builder Export/Import buttons. (3) `eclipse ui
  {components|capabilities|blueprints|show|history|create|classify|export|import|restore}`
  CLI group over the runtime's own store. (4) `test_ui_agent_e2e.py` drives the
  REAL `execute_run` graph with a scripted model emitting `ui_*` tool calls and
  asserts a durable page + metric card — the natural-language → tools → state
  path proven without a live provider (removing the "needs credentials to
  verify" blocker). `npm run build` (production) also passes cleanly. Tests:
  `test_ui_cli.py`, export/import API case, `test_ui_agent_e2e.py`. docs
  updated: `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.
