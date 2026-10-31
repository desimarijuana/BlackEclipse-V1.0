# Change Log

## 2026-10-31
- **fix(bots): workflow bots show their workflow, not an agent id.** The bot
  Overview and Capabilities sections display the linked workflow name (or id)
  for an `execute_workflow` bot instead of the irrelevant default agent.
  No doc change — the workflow-bot behaviour is already documented in
  `docs/graph-studio.md`.
- **feat(bots): use a saved workflow as the brain of a bot.** The New-bot dialog
  gained a **Brain** choice (Agent / Workflow) and a saved-workflow picker. A
  workflow bot answers chat turns by running its graph with
  `runInput = { message, botId, context }` and replying with the terminal output
  (string or pretty JSON). Scheduled workflow bots use the automation
  `execute_workflow` action with `action.config.graphWorkflowId`; because the
  Python runtime cannot read JDDS, the dispatcher starts the run through the
  front door (`/api/workflows/{id}/runs`) and polls `/api/graph-runs/{id}` to a
  terminal state. Both paths stay in the read-only TEST envelope. A workflow that
  is a bot shows that bot's avatar in the Graph Studio header and a **Workflow**
  badge in chat.
- **fix(graph/ui): Ctrl+Tab add-node shortcut and calmer add-node affordances.**
  The canvas add-node shortcut and its hint are now `Ctrl/Cmd+Tab` (plain Tab
  did not fire reliably), and the small `+` on a node output is a larger neutral
  frosted button instead of a tiny accent circle.
  Docs updated: `docs/graph-studio.md`, `docs/harness/automation-engine.md`,
  `docs/CHANGELOG.md`.

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-30
- **fix(graph): production hardening for schedules + a stable perf guard.** A
  schedule linked to a `trigger.schedule` node is now paused (with a visible
  reason) on the next tick if that node no longer exists in the persisted
  workflow, so deleting a trigger cannot leave an orphaned schedule firing the
  graph. Added coverage for the deleted-node and still-present-node paths. The
  observability span-overhead perf test now measures the **median of five warmed
  batches** instead of one run, so a scheduling hiccup under load cannot fail a
  guard that still requires < 1 ms per span.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): schedule details directly on the Schedule node.** The
  `trigger.schedule` card now shows an Active/Paused dot, a human schedule
  summary (`Weekdays at 09:00 · Asia/Karachi`), the next fire in the schedule's
  timezone, and the last error when a fire fails; a node with no linked schedule
  says so. The canvas loads schedules for the open workflow, refreshes after any
  schedule mutation (a small `eclipse:schedules-changed` event) and once a minute
  as the tick advances `nextRunAt`. The Schedule tab remains the editor.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): black in-node input wells + double-click for details.** Inline
  text/number/select/JSON widgets use the original black field fill again
  (`bg-background/60`) while keeping the compact 28px rows and borders. A single
  click on a node now only selects it, so clicking into a widget never opens the
  right inspector; double-click opens the inspector as the shortcuts panel
  already documented. Widgets stop double-click propagation, so editing a value
  cannot accidentally open the panel.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **style(graph): compact two-column node controls.** Inline parameters are now
  Blender-style rows — small label on the left, widget on the right — instead of
  stacked labels, which had made the cards tall and cramped. JSON parameters use
  a single-line value box on the card (the inspector keeps the full editor), and
  node width is 264 px so labels and dropdowns fit. No doc change — visual
  refinement of the in-node controls.
- **style(ui): filled Test glyph, lock for the broker, broom for “Tidy up”, and
  a calmer Add-node control.** The node hover Test button uses Phosphor's filled
  Play glyph (still a neutral solid-grey button). The sidebar broker launcher now
  uses the shared Lock icon so it matches the other sidebar icons instead of a
  brand mark. The graph canvas “Tidy up layout” action (toolbar and context menu)
  uses the Phosphor Broom icon. The canvas **Add node** affordance is now a
  frosted control with a neutral plus tile, the label and a `Tab` key hint —
  no green pill — and the empty-state “Add first step” uses the same treatment.
  No doc change — visual identity only.
- **style(graph): neutral solid-grey Test button.** The node hover toolbar's
  Test play button now uses the solid `muted` surface with a neutral foreground
  hover instead of green; the result dots keep their semantic colours.
  No doc change — visual tweak.
- **feat(graph): Blender/ComfyUI-style controls inside every node + one-click
  node Test.** Parameters are edited directly on the node: two priority fields
  always visible, a “+N more parameters” toggle expands the rest in place
  (Show less collapses). Number fields are drag-to-scrub widgets (Shift fine,
  Ctrl/Cmd coarse, click to type), selects are dropdowns, booleans are
  checkboxes, text is an input and JSON is a compact textarea. Every control
  dispatches the same `update_node_config` patch as the inspector; clicking the
  node still opens the full advanced inspector. `ConfigFieldDef.quick` chooses
  the two priority slots (logic.condition now surfaces compareTo,
  agent.research surfaces agent). The hover toolbar's play button — next to
  Duplicate — runs the node; the result renders inside the node body with
  running/succeeded/failed, duration, error and an expandable output preview.
  Side-effecting nodes show a lock and require an authorized run. Test state is
  ephemeral and nothing is persisted. Registry-driven, so it covers every node
  type without per-node UI code.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): schedule triggers now have real time controls and cannot
  double-fire.** `trigger.schedule` is zero-config; its cron/timezone/enabled
  state is a `WorkflowSchedule` linked by a new `nodeId` column (Prisma db push),
  edited in the node inspector's **Schedule** tab: repeat presets, a time picker,
  weekday chips, IANA timezone select, catch-up policy, version pin, next-three-
  fires preview, Run now, pause and delete. The 60 s ticker now starts early in
  the boot pipeline, holds a process-level overlap lock, and **claims each due
  fire atomically** (compare-and-set on `nextRunAt`) so two ticks/processes
  cannot start the same run; missed fires keep the skip/coalesce policy and a
  later tick reconciles `lastStatus` from the run instead of leaving it at
  `started`. Zone names are validated with a clear error. Schedules still run in
  the read-only test envelope (the UI says so) and only while the server is up.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): zero-config manual trigger + per-node Test panel.** `trigger.manual`
  now has no config fields, like n8n: `Start` is the one-off run input (Execution
  dock or webhook body) or null; stored defaults belong in `data.value` /
  `data.set_variables`. Legacy `seed`/`payload` keys in already-saved graphs are
  still honoured at runtime but are no longer declared or shown, and the starter
  templates were moved onto visible data-node defaults. The inspector gained a
  **Test** tab that executes a single node through the new
  `POST /api/graph-runs/node-test` → Python `POST /graphs/nodes/test` surface:
  explicit per-port inputs, re-validated config, the node's hard timeout, and a
  safe envelope that refuses network/write/trading/model nodes (403). Tests cover
  the zero-config trigger, node tests, input validation and the safe envelope.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): n8n-style manual trigger — payload, run input and webhook body.**
  `trigger.manual` now has a `payload` (any JSON) plus `payloadType`
  (`auto`/`string`/`number`/`boolean`/`object`/`array`) in addition to the legacy
  `seed`; the executor resolves Start as run input → payload → seed → null, so
  existing graphs are unchanged. The runs route and the webhook-style trigger
  route now accept a bounded (64 KiB) `runInput` (webhook: the request body) and
  forward it to the Python runtime, which already supported it. The Execution
  dock gained a **Run input** JSON editor (one run only, never persisted), and the
  inspector shows Payload/Payload type with help text. Registry parity kept in
  both languages; `config_fields` gained an `any` kind for JSON values.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(ui): provider logos replace the sparkle in the model picker.** The
  composer's model selector and the Provider submenu now show the actual
  provider's brand mark (OpenAI, Anthropic, Gemini, Mistral, DeepSeek, Groq,
  Ollama, LM Studio, xAI, OpenRouter, Perplexity, Together, Fireworks, OpenCode,
  or the Eclipse mark) instead of the generic sparkle; unknown/custom providers
  get a neutral CPU glyph. Marks are vendored under `public/providers/` and
  rendered as a `currentColor` mask so they work in both themes and never call
  a CDN. The Manage-models dialog header shows the provider's mark too.
  No doc change — visual identity only.
- **feat(voice): dictation — speak prompts into the composer.** The dead mic in
  both composers is now a real voice-input control: Whisper through an
  OpenAI-compatible `/audio/transcriptions` endpoint (OpenAI, Groq, or a keyless
  local whisper.cpp server), with browser SpeechRecognition as the zero-config
  fallback. Audio is bounded, validated, transcribed once and discarded — never
  stored or logged — and the transcript is inserted at the caret without
  replacing typed text. Settings › Voice gained engine/language/vocabulary/max
  length/provider config plus an honest readiness report. A new Settings › Voice
  provider readiness route (`/api/voice/config`), transcription front door
  (`/api/voice/transcribe`), Python `/voice/transcribe` runtime route, and the
  optional `TRANSCRIBE_API_KEY` vault entry keep the key server-side.
  Docs updated: `docs/voice.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.
- **feat(graph): n8n-style node parameter editing.** A single click now opens the
  inspector (drag still moves the node). The Parameters tab shows the node
  description/docs, friendly labels, one-line help, required markers, and an
  “Advanced: edit config as JSON” editor for any field the form does not expose.
  The Settings tab gained saved node **Notes** (`update_node_notes`; notes are
  copied on duplicate/paste and never executed). Added shared help text and
  required-field metadata in `config-fields.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **test(graph): verified `trading.broker_order` on a real MT5 demo fill.** A
  graph `trigger → data.value(intent) → trading.broker_order → result` submitted
  a 0.01 lot EURUSD buy (SL 1.11000, TP 1.12500) under a one-order demo mandate:
  ticket `11183814415` filled at 1.11676, then closed/verified at 1.11677
  (`positions=0`). A first attempt without a stop was correctly refused by the
  connection's 0.5% risk-per-trade policy, proving the preflight gate. The
  configured connection is a demo account, so the live two-key path still needs
  an armed live connection to be exercised.
  no doc change — verification run; no contract changed.

- **feat(graph): MT5 live execution under a workflow-pinned mandate.** Phase 6
  adds LIVE broker nodes: `trading.broker_order` (armed live connection + live
  mandate; a mandate replaces the per-order typed phrase), read nodes
  `broker_account` / `broker_quote` / `broker_bars`, and risk-reducing
  `broker_close` / `broker_modify` / `broker_cancel` (no arm/approval/mandate).
  Live mandates pin `workflowId@version`, are capped at a 24 h TTL and require
  the connection arm before creation; `RunGrants`/`RunRequest`/the front door
  carry `allowLiveTrading`, the compiler refuses paper-only nodes in live mode
  and requires pinned `connectionId`/`mandateId`, and the execution context now
  carries the workflow id for the mandate check. The editor gained a broker
  connection/mandate picker and the Settings mandate form supports live + a
  workflow pin. Tests: live mandate/submit, pinned workflow mismatch, compiler
  live grant. Docs updated: `docs/trading.md`, `docs/graph-studio.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): scoped external file writes.** Added `file.write` (Phase 5):
  a named operator-configured scope (`HARNESS_GRAPH_WRITE_ROOTS`, default
  `workspace` → `.black-eclipse/workspace`), relative paths only, `..`/absolute/
  symlink escapes refused, 8 MB cap, atomic replacement or append. A test run
  never writes; an operator run is granted only the exact scopes it confirms
  (`allowedWriteScopes`, carried through the front door to `RunGrants`). The
  authorization dialog lists the scopes; the editor marks file writes as an
  effect. Tests: node confinement/caps, compiler envelope, TS authorization.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): bounded loop nodes.** Added `flow.for_each`, `flow.repeat` and
  `flow.while`: a pinned body workflow run under a hard `maxIterations`/`count`
  and optional `maxDurationMs` cap. The compiler still refuses graph cycles; a
  loop is an orchestrated node. Each iteration is a durable child run
  (`<parent>:<node>:i<N>`) and doubles as its checkpoint — a resumed parent
  reuses a succeeded iteration. `flow.while` evaluates the safe formula language
  over `value`/`index`/`iterations`; `flow.for_each` can continue on a failed
  item and records the error in `results`. The editor treats loop bodies like
  subworkflows (pinned workflow picker) and the front-door bundle walks them.
  Tests: compile/execute/cap/reuse and parity.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): resumable agent runs.** Durable graph jobs now persist the
  front-door callback URL and re-resolve model credentials on resume through the
  operator-gated `POST /api/graph-runs/{id}/credentials` route — the key is held
  in worker memory only, never in the job payload. The agent adapter re-enters
  the same agent-plane run when a durable checkpoint exists
  (`agent_run_identity`), so a crashed turn continues instead of replaying; a
  run without a checkpoint restarts under a fresh id (model calls have no world
  effect). Added credential-resolution and identity tests. Docs updated:
  `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): dry-run agent nodes in a test run.** Added the `model` side
  effect (tokens, not a world effect), separate from `network`. Agent nodes are
  now `model`, so a test/dry run may execute them; the front door resolves model
  credentials for any graph with `agent.run`, and the runtime narrows the agent's
  declared allowlist DOWN to `DRY_RUN_TOOLS` (read-only finance, local evidence,
  response helpers) — web, browser, MCP, plugins, code and broker tools are
  removed. Operator runs keep the preset's surface. Added `requiresModel` /
  `modelNodes` to run authorization and the dialog, plus dry-run surface tests.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): operator-authored agent presets from Settings.** New Settings ›
  Agents CRUD for a custom agent preset (prompt, max steps, explicit tool
  allowlist, MCP/plugin expansion). Presets live on `agent-memory.db` in
  `AgentPreset` + immutable `AgentPresetVersion`; every edit appends a version
  and an agent node pins `agent@version`. Tool names are validated against the
  live registry and a write/external tool requires the explicit “Allow effectful
  tools” acknowledgement. The Next front door is a thin proxy; the runtime owns
  resolution. Agent nodes gained `agentVersion` and the inspector gained a
  built-in/custom picker; the manifest was regenerated.
  Docs updated: `docs/graph-studio.md`, `docs/harness/decisions.md`
  (ADR-H342), `docs/CHANGELOG.md`.
- **fix(docs): rotate-changelog archives the oldest sections, not the newest.**
  The script read the newest-first file backwards (`marks[length - KEEP]`) and
  sliced the archive block with a dead identity check, so `--write` moved the
  newest section out and dropped the older ones. It now keeps the first 7
  newest sections and archives the contiguous oldest tail; 2026-10-23 moved to
  `docs/changelog/2026-10.md`.
  Docs updated: `docs/CHANGELOG.md`, `docs/changelog/2026-10.md`.
- **fix(graph): record the repro + root cause for failing agent nodes.** A
  trigger → `agent.research` → result graph run as an operator run returns a
  complete answer from the agent plane but the node is marked failed with
  `agent run completed: <output>`; downstream nodes are skipped. Cause: the
  bootstrap adapter accepts only `succeeded` while the run plane's terminal
  success status is `completed` (`RunStatus` in `python/harness/schemas.py`).
  Also found adjacent defects: run history is keyed by `ir.id` while the API
  lists by the JDDS row id, and subworkflow bundles fail the same identity
  equality check. Analysis only, no code changed in this pass.
  no doc change — investigation for a fix plan; `docs/graph-studio.md` will be
  updated with the fix, not the audit.
- **fix(graph): make agent nodes and run history work.** Extracted the agent
  result projection into `agent_nodes.agent_result_payload`, which now accepts
  the run plane's `completed` terminal status as success (and `failed`/
  `cancelled` report their own message, not the transcript). Run dispatch now
  aligns the IR id to the persisted JDDS workflow id (and bundled subworkflow
  IRs to their pinned row ids), so `/api/workflows/[id]/runs` and nested runs
  share one identity. `agent.research.query` / `agent.plan.objective` are
  optional ports backed by a compile-time "wire or config objective" rule, and
  the canvas "From wire" state maps a config field to its real port. The editor
  Start action now opens the authorization dialog for graphs with network /
  trading / write effects instead of firing a test run that must be refused.
  Added agent adapter, config-only objective and every-node-executable tests;
  regenerated `registry.manifest.json`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.

## 2026-10-29
- **feat(voice): read assistant replies aloud with browser-native TTS.** Added a
  Speak/Stop control to the chat footer, structured-response header and bot
  messages, plus a Settings › Voice pane (voice, rate, pitch, volume, opt-in
  auto-speak). Uses the Web Speech API only — no dependency, key, server
  round-trip or transcript upload; unavailable browsers hide the control and say
  why. `src/lib/tts/text.ts` projects Markdown/structured replies to prose
  (drops code/JSON, keeps link labels, reads tables as rows, strips citations)
  and `speech.ts` chunks utterances and guards cancelled runs. Prefs persist in
  `be_tts_v1`; auto-speak primes on mount so history never replays.
  Docs updated: `docs/voice.md` (new), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.
- **feat(trading): reveal the MT5 terminal after a fill.** A successful
  `filled`/`placed` order now focuses the running `terminal64.exe` (or starts the
  connection's `terminalPath`) so the operator sees the position immediately.
  Windows-only and best-effort; it cannot change the order result, is a no-op on
  a container/remote bridge, and can be disabled per connection with
  `openTerminalOnTrade: false`. Docs updated: `docs/trading.md`.
- **ops(deploy): server-side auto-deploy (`scripts/deploy.sh`).** Production had
  no update path beyond a manual pull + rebuild, so a pushed commit never reached
  a running container. The script fetches `origin/main`, exits immediately when
  the commit is unchanged, pulls `--ff-only`, rebuilds the compose image, and
  waits for `/login`; a lock prevents overlapping builds and tracked local edits
  make it refuse. `scripts/install-autodeploy.sh` writes and enables the timer in
  one command. `.github/workflows/deploy.yml` gives an optional push-to-deploy
  path (skips unless deploy secrets are set). Documented a 5-minute systemd timer
  (and cron equivalent).
  Docs updated: `docs/DEPLOYMENT.md` (new "Automatic updates" section).
- **feat(trading): live exits are arm-free; live entries are one-click in chat.**
  A live connection can now close/modify its own positions without an arm (the
  account mode must still match), so an expired arm cannot trap live risk. A live
  close-all is scoped to the connection's magic (the kill-switch boundary); explicit
  tickets can include others. Added a
  chat `TradeApprovalBanner`: `order_preview` leaves a single-use approval, the
  banner shows the exact order, and the operator types the LIVE phrase and clicks
  Confirm & send. The server list view now carries `connectionId`/`intent` so the
  card submits without re-entry. Settings › Broker connection gained an edit/switch
  mode control. Live mandates and Graph Studio live nodes remain out of scope.
  Docs updated: `docs/trading.md`, `docs/DECISIONS.md`, `skills/ARCHITECT.md`
  (ADR-056), `docs/harness/tool-registry.json`.
- **fix(ui): frosted-glass dropdowns in the broker + quick-trade surfaces.** Replaced
  the native `<select>` mode/side/type pickers in Settings › Broker connection, the
  sidebar broker dialog, and the Quick Trade widget with the shared Base UI
  `Select` (`glass-tooltip`). Native OS popups cannot be blurred; the portalled
  select can. No contract change.
  no doc change — visual-only component swap.
- **feat(trading): read-only broker connectivity, attach-first MetaTrader 5.**
  New `python/harness/trade/` package: a `BrokerAdapter` read contract, a kind
  registry with honest dependency availability, a durable
  `BrokerConnection`/`BrokerConnectionEvent` store on `agent-memory.db`, one
  `BrokerService`, and read-only `broker_*` agent tools. The first adapter attaches
  to a running, logged-in MT5 `terminal64.exe` over local IPC and reads account,
  positions, working orders and quotes with named failure codes
  (`PACKAGE_MISSING`, `TERMINAL_NOT_FOUND`, `NOT_LOGGED_IN`, `NO_IPC`, …). Config
  validation refuses password/token-shaped keys at write time; no credential is
  stored and the preferred path needs none. `/trading/*` routes are
  operator-gated; `POST /trading/orders` is an honest 501 and there is no order
  tool. Front door: `src/app/api/trading/[[...path]]/route.ts` + allowlist +
  client. Tests: `python/tests/test_broker_layer.py`,
  `src/lib/harness/trading-routes.test.ts`.
  Docs updated: `docs/trading.md` (new), `docs/ARCHITECTURE.md` (portfolio layer),
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H331).
- **feat(trading): demo order execution via preview → approval → submit.** P1
  adds `TradePolicy` (margin/volume/spread/open-position/allowlist), a
  `trade/authorizer.py` seam that evaluates the order as a `MoneyIntent` through
  the finance guardrails, creates a single-use `trade_order` approval bound to the
  exact `OrderIntent` digest, and consumes it atomically before `order_send`.
  Demo is enforced twice (connection record + `account_info().trade_mode`); live is
  refused with `LIVE_NOT_ENABLED`. MT5 gains `order_preview` (`order_check`),
  `submit_order` and `cancel_order` with retcode mapping, volume/stop/filling
  validation and a `BrokerOrder` ledger; an ambiguous send is `unknown` and never
  retried. Routes: connection-scoped `orders/preview`, `orders/submit`,
  `orders/{ticket}/cancel`, `orders/ledger`, plus trade approvals; the agent gets
  `order_preview`/`order_ledger` only, never submit. Tests:
  `python/tests/test_broker_orders.py`, `test_mt5_adapter.py`,
  `src/lib/harness/trading-routes.test.ts`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H332).
- **feat(trading): armed live execution and a magic-scoped kill switch.** P2 adds a
  time-boxed per-connection arm (typed `ARM LIVE <login>`, 60 s–8 h) that requires a
  real account, Algo Trading, a non-zero `magic`, and a positive `maxMargin`.
  Every live order still runs through `trade/policy.py`, the money guardrails, and
  the single-use `trade_order` approval, plus a mandatory per-order
  `LIVE <SIDE> <volume> <symbol>` phrase. The arm is cleared by mode/config changes,
  a failed probe, expiry, or the kill switch. `POST .../kill` cancels only working
  orders carrying the connection's magic and disarms; it never closes positions.
  `BrokerConnection` gains `armedUntil`/`armedAt`/`armedBy`; `TradingAdapter` gains
  `cancel_all(magic)`; MT5 gains a magic-filtered cancel-all. Routes: arm/disarm/
  kill. Tests: `test_broker_orders.py` (live arm, phrase, expiry, kill).
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H333).
- **feat(graph): demo broker orders under bounded mandates.** P3 adds a
  `TradingMandate` (demo-only; allowed symbols, per-order `maxMargin`, `maxOrders`,
  60 s–7 d expiry; typed `MANDATE DEMO <label>`; atomic usage; immediate revoke) and
  Graph Studio's `trading.broker_order` node. The node is paper-mode only and calls
  the SAME `BrokerService.submit_order` path, so policy, money guardrails, the
  demo/real account check and the no-retry rule still apply; the ledger records
  `mandateId`. Live trading nodes stay refused by the compiler and front door, and
  `create_mandate` refuses a live connection. Routes: mandate create/list/revoke.
  Tests: `test_broker_orders.py` (mandate lifecycle + node),
  `src/lib/graph-studio/run-authorization.test.ts`; `registry.manifest.json`
  regenerated (`npm run graph:manifest`).
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio.md`, `docs/harness/decisions.md` (ADR-H334).
- **feat(trading): durable fills/positions/order-state reconciliation.** P4 adds
  `trade/reconcile.py`: `BrokerFill` (deduped by connection + deal ticket),
  `BrokerPositionSnapshot` (atomic replace) and `BrokerSyncState` on
  `agent-memory.db`. A sync reads broker positions/working orders/deal history,
  updates in-flight ledger orders only from definitive history states, and records
  `error`/`unavailable` on failure without deleting the last good data. The
  background `ReconcilerLoop` is opt-in (`TRADING_RECONCILE_SECONDS`, default 0);
  manual `POST .../sync` always works. MT5 gains `deals_since`/`order_status`;
  routes for sync/reconciliation/fills; read-only `broker_reconciliation`/
  `broker_fills` tools. Tests: `python/tests/test_broker_reconcile.py`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H335), `.env.example`.
- **chore(trading): pin the MetaTrader 5 bridge for Windows x64.** `MetaTrader5`
  is now in `python/requirements.txt` with a `win32` + `AMD64` marker, so the
  runtime install keeps the bridge while Linux/macOS installs are unchanged. The
  terminal remains a separate operator install. Verified an attach to a local demo
  terminal (account/positions/quote reads + a reconciliation sync).
  Docs updated: `docs/trading.md`.
- **feat(settings): Trading › brokers panel.** Adds a Settings surface for
  connecting a MetaTrader 5 terminal, probing it, showing the account (login,
  balance/equity, margin, leverage, demo/real), sync/test/remove, and live
  arm/disarm/kill controls. It never places an order; orders stay on the existing
  operator routes, Graph Studio and the API. Wired into `settings.tsx` as the
  `trading` section.
  Docs updated: `docs/trading.md`, `docs/NAVIGATION.md`.
- **feat(dashboard): live MT5 trading widgets.** The five `trading` widgets are no
  longer `UNAVAILABLE` stubs. Quick Trade (preview → approve → submit, with the
  guardrail phrase), Open Positions, Working Orders (cancel), Margin Usage and
  Today P&L read the first saved broker connection and poll every 15 s. A missing
  connection renders a Settings → Broker connection setup note; every empty/error state is
  explicit and no number is fabricated. New `src/lib/dashboard/trading-widgets.tsx`,
  registered in `registry.tsx`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.
- **feat(shell): broker connection button next to Gateway/Graph.** Moves the
  MT5 entry point into the sidebar's quick-launcher row (handshake icon, with a
  status dot and an **MT5** badge in the popup) and keeps it in the collapsed
  footer. The popup now uses the same
  `rounded-2xl border border-white/10 glass-card-strong` recipe as the
  Gateway/Graph dialogs, and reads the connection's stored account snapshot
  immediately instead of blocking on a live read. No orders are placed from the
  dialog. New `src/components/layout/sidebar-broker-dialog.tsx`; wired in
  `sidebar.tsx`; `Handshake` added to the central icon set.
  Docs updated: `docs/trading.md`.
- **style(shell): widen the broker connection popup.** `sm:max-w-md` → `sm:max-w-lg`
  (448 → 512 px) so the two-column connection form and account figures have room.
  no doc change — presentation-only, no contract or setup change.
- **style(settings): use the handshake for the Broker connection section.** The Settings rail
  entry and the Broker connection panel header now use the same `Handshake` icon as the
  sidebar broker button, instead of the MCP-looking plug.
  no doc change — presentation-only.
- **fix(trading): preview refusals are outcomes; MT5 sessions are serialized.** A
  blocked preview now returns `allowed:false` + `error.code`
  (`ALGO_TRADING_DISABLED`, `DEMO_ACCOUNT_REQUIRED`, `LIVE_NOT_ARMED`, …) instead of
  raising, and the front door preserves the runtime status instead of mapping 403
  to 502. The `order_preview` tool text names the code; `broker_account` includes
  margin mode/flags; `broker_quote` includes digits, point, volume step/min/max and
  stops level; `broker_positions` includes SL/TP. MT5 `initialize`/`shutdown` is
  guarded by a process-wide lock so concurrent agent tool calls cannot collide.
  Tests: `test_broker_orders.py` updated.
  Docs updated: `docs/trading.md`.
- **fix(reconciliation): server-time-safe deal window.** `history_deals_get`
  expects server time; the local clock was 2h behind the demo server, so the newest
  deal was outside the query window and a real fill produced `fillsAdded: 0`. Sync
  now queries 7 days back with a 2-day future margin and relies on deal-ticket
  dedupe; the cursor is advisory. Verified with a real demo fill (0.01 EURUSD,
  ticket 11164486049): `fillsAdded: 1`, position and ledger reconciled.
  Docs updated: `docs/trading.md`.
- **feat(trading): `order_submit` may omit the mandate id when exactly one is active.**
  The agent resolves the sole active demo mandate; with several active mandates it
  must name one from `broker_mandates` (or the handler returns the available ids).
  Docs updated: `docs/trading.md`.
- **feat(trading): agent-driven demo execution under a mandate.** Adds
  `order_submit` (the one effectful agent broker tool) and `broker_mandates`, plus
  a Settings panel to create/revoke bounded demo mandates. `order_submit` is
  admitted by an active mandate, not the generic approval card, and still runs the
  SAME service path (demo account check, policy, money guardrails, symbol/margin
  cap, order count). Live remains unreachable. Prompt guidance: keep analysis
  brief, call `order_submit` directly. Verified end-to-end: Eclipse analyzed
  EURUSD and filled **ticket 11164809214** (BUY 0.01, SL 1.11125, TP 1.12260)
  under mandate `mnd_c82ba003d785`; two earlier demo tickets were also filled.
  Tests: `test_broker_agent_trade.py`, updated broker tool test.
  Docs updated: `docs/trading.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H336).
- **fix(trading): subscribe an unlisted symbol on demand.** `XAUUSD` existed on
  the demo but returned an all-zero tick until it was in Market Watch; the adapter
  now calls `symbol_select` and retries the tick for up to ~2 s (a local
  subscription, not an order). Verified live: XAUUSD bid 4010.87 / ask 4011.16,
  spread 29 points, 0.01–100 lots. Docs updated: `docs/trading.md`.
- **fix(trading): a plain "analyze gold and place a trade" prompt now executes.** Three
  fixes for a user who never types a mandate id: (1) `order_submit` and its
  authorizer resolve the one active mandate whose symbols cover the intent symbol
  (the sole active mandate when it is the only one) and the only saved connection,
  returning `MANDATE_REQUIRED` with the active ids only on real ambiguity;
  (2) `graph.py` adds a per-run `# Trading request` block when the turn asks to
  place/buy/sell an order — skip web/news/scrape, read the quote (plus at most one
  bar source), call `order_submit` once, never ask for ids — while a refusal or a
  question keeps the block out; (3) the mandate cap now sees the order's own margin
  (`order_check().margin − account.margin`, floored at zero) instead of the
  account total after the trade, which had refused a valid 0.01 XAUUSD lot at
  113.74 vs a 100 cap when it only needed 40.00. Verified live with the bare prompt
  “Analyze XAUUSD and place a small demo trade with a stop loss and take profit”:
  4 model steps, one `order_submit`, ticket **11165187813** (XAUUSD BUY 0.01 @
  4014.13, SL 3988.99, TP 4063.99) under mandate `mnd_c405bf889119`. Tests:
  `test_trading_intent.py` (new), `test_broker_agent_trade.py`,
  `test_mt5_adapter.py`. Docs updated: `docs/trading.md`.
- **feat(trading): close a demo position (or every one) so a user can step out.**
  Adds `TradingAdapter.close_position` (MT5 sends the exact opposite market deal,
  position ticket as `position`, position magic, once, ambiguity reported not
  retried), `BrokerService.close_position` / `close_positions`, routes
  `POST .../positions/{ticket}/close` and `POST .../positions/close`, the agent tool
  `position_close` (`ticket`, `tickets` or `all: true`), and Close / Close-all in the
  Open Positions dashboard widget (both confirm first). Closing is risk-reducing, so
  it needs no mandate and no approval and does not consume a mandate order; the
  service refuses a live connection (`LIVE_NOT_ENABLED`) and a real account
  (`DEMO_ACCOUNT_REQUIRED`). The per-run trading directive now has a
  `# Close request` variant (`python/harness/trading_intent.py`, extracted from
  `graph.py`) so “close my trade” never turns into research or a hedge. Tests:
  `test_broker_orders.py` (close one/all/targeted/live-refused),
  `test_broker_agent_trade.py` (no mandate, target required),
  `test_trading_intent.py`, `trading-routes.test.ts`. Regenerated
  `docs/harness/tool-registry.json` (981 tools) and the graph manifest; re-pinned
  the `graph.py`/`service.py` and prompt-size ceilings to their measured values.
  Docs updated: `docs/trading.md`, `docs/harness/decisions.md` (ADR-H337).
- **fix(trading): a stale/missing connection id no longer hides a valid mandate.**
  A remembered `connectionId` from another profile or database made the mandate
  list for that id empty, so `order_submit` answered "no active mandate" on an
  account that had one. Both the handler and the authorizer now drop an id that is
  not a saved connection and resolve the single existing one (they still refuse
  when several exist). Verified with the bare prompt “Analyze gold and place a
  small demo trade with a stop loss and take profit”: one `order_submit`, ticket
  **11165863645** (XAUUSD BUY 0.01 @ 4031.99, SL 4007.30, TP 4057.30). Tests:
  `test_broker_agent_trade.py` (stale id resolves; unknown id with two connections
  still refuses). Docs updated: `docs/trading.md`.
- **feat(trading): broker-native bars and ATR for uncovered symbols.** Adds
  `broker_bars` (and the `TradingAdapter.bars` / `BrokerService.bars` seam): MT5
  `copy_rates_from_pos` on `M1…W1`, clamped to 500 bars, server time, with the
  symbol's contract/tick size; a pure `trade/analysis.py` computes TR/ATR(14) and
  the 20-bar range. This replaces the proxy-ETF workaround for XAUUSD, whose
  history route returns `UNAVAILABLE`. Quote now also exposes `contractSize` and
  `tickSize`, so "$ at risk" is exact. The per-run directive and the system prompt
  prefer `broker_bars` for a broker symbol. Fixed the advisory gate's table-row
  false positive (`| Take profit | … |` became a "sell" claim) and its indicator
  acronyms (`ATR`, `SL`, `TP`, …). Verified live: XAUUSD H1 120 bars, contract
  100, ATR(14) 14.82; the bare prompt filled ticket **11166047327** (BUY 0.01 @
  4025.10, SL 4003.50 ≈ 1.46 ATR, TP 4055.00 ≈ 2.02 ATR) under mandate
  `mnd_dc9477f30067`. Tests: `test_analysis.py` (new), `test_mt5_adapter.py`,
  `test_advisory_gate.py`. Regenerated the graph manifest and tool registry (982
  tools); re-pinned the prompt ceiling to its measured size.
  Docs updated: `docs/trading.md`.
- **feat(trading): partial close, SL/TP modify, and read-back verification.** Adds
  `position_modify` (`TRADE_ACTION_SLTP`, 0 removes a level), a `volume` on
  `position_close` for partial exits, close-by-`symbol`, and a `verified` flag on
  every close/modify/market fill: the broker's stored position is read back and a
  mismatch is reported (`verifyNote`), never assumed. The lifecycle moved to a new
  `trade/positions.py` (the broker service was at its size ceiling) and keeps the
  identical demo-only rule: no live connection (`LIVE_NOT_ENABLED`), no real account
  (`DEMO_ACCOUNT_REQUIRED`), no mandate or approval for an exit. Adds routes
  `.../positions/{ticket}/modify` and `volume` on close, the client calls, the
  authorizer admission, and per-run `# Modify request` / partial-close guidance; the
  positions text now includes the ticket. Verified live on ticket 11166047327: TP
  moved to 4060.00, SL to 4010.00, both read back as stored. Tests:
  `test_broker_orders.py` (partial, modify, live refusal, invalid stops),
  `test_broker_agent_trade.py`, `test_trading_intent.py`, `trading-routes.test.ts`.
  Ratcheted `trade/adapters/mt5.py` (bars + lifecycle in one wire bridge; split
  candidate), regenerated registry (983 tools) and manifest, re-pinned the prompt
  ceiling. Docs updated: `docs/trading.md`, `docs/harness/decisions.md` (ADR-H339).
- **feat(trading): risk engine on the connection (per-trade risk, notional, 24 h
  brake).** Adds `riskPerTradePct`, `maxDailyLossPct` and `maxSymbolNotional` to
  the connection config (0 = off). Per-trade risk is `|entry − stop| × volume ×
  contractSize` against a percentage of equity; with the cap set, an order without
  a stop is refused. The daily brake sums the broker's realised deals over 24 h
  and open P&L, blocks new entries and never blocks a close. A per-order symbol
  notional cap and the existing spread/open-position caps round it out. Settings →
  Broker connection gains a **Risk limits** editor. Verified live: at 0.02% a 0.01
  XAUUSD order with a 100-point stop was refused (121.76 risk vs a 20.00 cap); at
  0.5% with a 120-point spread cap the shape previews as allowed. Tests:
  `test_trade_policy.py` (new), `test_broker_orders.py`. Docs updated:
  `docs/trading.md`, `docs/harness/decisions.md` (ADR-H340).
- **test(trading): a scripted MT5 terminal and wire-level chaos tests.** New
  `python/tests/mt5_sim.py` implements the adapter's slice of the MetaTrader API
  (account/symbols/ticks/positions/orders/`order_check`/`order_send`/deals/bars)
  with knobs for a lost send reply, a disconnected terminal, a dropped bracket, a
  partial fill and a modify the broker accepts but does not store. New
  `test_mt5_simulated.py` proves: a fill is verified against the stored bracket; a
  dropped stop is `verified:false` with a `verifyNote`; a lost reply raises and is
  **not retried**; a disconnect is a named error; a partial close reports the
  remaining volume; an ignored modify is unverified; bars normalize; deals read.
  This closes the gap between request-builder unit tests and a live terminal.
  no doc change — test-only (no contract or setup change).
- **feat(chat): a trade turn binds the trade surface, not ~700 tools.** A run whose
  prompt is a trade/close/modify request now narrows policy's allowlist to
  `TRADE_SURFACE_TOOLS` (~18 broker/trade + response helpers). It runs after
  surface resolution and can only remove; a run without an effect tool is
  untouched. Measured live on a refused gold order: `allowedTools` 721 → **18**,
  prompt tokens **47k** for 3 steps instead of ~228k, with exactly
  `broker_quote` → `broker_bars` → `order_submit`. Tests:
  `test_trading_intent.py`. Docs updated: `docs/trading.md`.
- **feat(dashboard): modify/partial close and a Recent Trades card.** The Open
  Positions widget now shows each ticket, an **SL/TP** action (prompts for the new
  levels, calls `positions/{ticket}/modify`) and a **Close** action that accepts a
  partial volume; an inline notice reports the verified result. A new
  **Recent Trades** widget reads the ledger (`orders/ledger`) and lists the last
  eight orders with ticket, fill and status. TypeScript clean; dashboard
  registry/size tests pass. Docs updated: `docs/trading.md`.
- **feat(trading): the sidebar broker popup becomes a full control center.** The
  handshake popup now has a connection switcher and five tabs. **Overview** shows
  every live `BrokerAccount` field (used/free margin, margin level, floating P/L,
  leverage, margin mode, trade/algo flags), bridge health, connection timestamps
  and a bid/ask quote lookup. **Positions** closes one or all positions;
  **Orders** cancels a working ticket; **Activity** lists broker deals with an
  `eclipse`/`manual` owner badge plus the Eclipse order ledger. **Settings**
  edits label/mode/terminal path/magic/max-margin, carries the typed **arm**,
  **disarm** and **kill switch** controls for live connections, and adds/removes
  connections. All calls reuse `src/lib/harness/trading-client.ts`; no new
  routes. Presentational panels split into
  `src/components/layout/sidebar-broker-panels.tsx`. The popup still cannot place
  an entry order, and mandates/approvals stay in Settings. Tests: `npm run test`
  (425 files / 4094) + `npx tsc --noEmit` + broker Python tests (56) pass.
  Docs updated: `docs/trading.md`.
- **perf(settings): the Settings modal opens instantly.** Three changes remove the
  cold-open wait. (1) The shell no longer blocks on a full skeleton: it paints the
  real nav + section immediately with the last-known snapshot and shows a slim
  "Loading settings…" line while `/api/settings` revalidates. (2) A new
  dependency-free `src/lib/settings-cache.ts` persists the non-secret payload
  (`hasApiKey` only, never a key) to localStorage, so even a fresh page load has
  values before the request starts; `src/hooks/use-settings-prefetch.ts` fetches
  them 2.5 s after first paint and warms the lazy Settings chunk on gear
  hover/focus or after 12 s (skipped on metered connections). (3) `/api/markets`
  now starts only after the settings read, so JDDS/Prisma work cannot queue
  ahead of the critical path; the Market tab shows "Loading markets…" instead of
  a false empty state. `stock-chat.tsx` stayed at its pinned size budget.
  Docs: no doc change — internal performance/UX only (contracts unchanged).

## 2026-10-28
- **fix(desktop): one launcher at a time, so repeated icon clicks cannot break boot.**
  `scripts/start-desktop.js` now takes an exclusive lock
  (`.black-eclipse/desktop-launcher.lock`, stale locks recovered by PID
  liveness). Before this, clicking the icon again during a cold build started
  another launcher that killed the port and ran its own `next build`; concurrent
  builds rewrote the same `.next` folder, failed with exit 1, and left the
  desktop log spinning for ~18 minutes. Extra clicks now no-op (and reopen the
  tab once the owner is up) instead of starting competing builds.
  Docs updated: `docs/QUICKSTART.md`.
- **fix(modeling): integrated DCF detection, aliases and honest check counts.**
  `integrated` now builds a DCF when `wacc`/`waccInputs`/`dcf.wacc` is present
  (snake_case or camelCase), merges DCF/LBO/comps metadata into the audit summary,
  deduplicates statement checks, counts WARN checks in the audit text, and accepts
  camelCase comps target/peer fields (`netDebt`, `totalDebt`, `sharesOutstanding`,
  `netIncome`). Preservation reports now count targeted parts separately from
  changed/untouched parts.
- **fix(verification): read back generated artifacts and audit values.** Document
  tools accept `artifactId`, so a generated XLSX/PPTX can be opened and queried
  without a filesystem path. `integrated` models now merge DCF/LBO/comps meta, so
  `financial_model_audit` returns `enterpriseValue`/`equityValue`/`valuePerShare`
  etc. instead of only PASS/FAIL. The edit result now spells out “N total /
  M targeted / K untouched” parts so the preservation count cannot be misread.
  Docs: `docs/harness/document-intelligence.md`,
  `docs/harness/financial-modeling.md`.
- **fix(institution): keep the run dialog polling when review queues repairs.**
  `finalize` can return `status: "repairing"` after queueing bounded repairs; the
  dialog now resumes polling instead of stopping on the first terminal task state.
  no doc change — behaviour fix covered by `docs/harness/institution-preset.md`.
- **feat(agents): Institution multi-agent preset (analyst → debate → trader → risk → PM).**
  Added one cast spec in `python/harness/institution/` that materialises into
  `AgentConfig` presets, A2A definitions, a validated `TeamDefinition` task graph
  and Bots-workspace bot specs. The debate produces a structured record (agreement,
  unresolved disagreements, missing facts) and never votes or averages; the
  read-only `read_run_output` tool hands a completed prerequisite memo to the next
  stage by run id. Added `/team/presets*` routes, the `run_team` automation action,
  a Bots-screen run dialog with a live stage timeline, and an idempotent bot seeder.
  Fixed `tasks.manager.recompute_plan` so a multi-level DAG stays `RUNNING` while
  queued work remains instead of being marked `BLOCKED` after its first stage.
  Tests: `test_institution_preset.py` (8), `preset-client.test.ts` (2).
  Docs updated: `docs/harness/institution-preset.md`,
  `docs/harness/bot-team-orchestration.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H330).
- **feat(hardening): production guards for edits and model builds.** Artifact
  versions now accept `expectedChecksum` and refuse a stale edit with
  `ARTIFACT_CONFLICT`; `document_edit` confines path sources to authorized roots,
  refuses XML DTD/entities (`EDIT_XML_UNSAFE`) and macro packages when policy is
  off (`EDIT_MACRO_REFUSED`), logs `document.edit`, and is idempotent per
  plan/source; `financial_model_build` is idempotent per spec hash/format and
  logs `financial_model.build`; chart data replacement requires an exact series
  count. Docs: `docs/harness/office-edit.md`,
  `docs/harness/financial-modeling.md`, `docs/harness/artifact-center.md`.
- **fix(memory): preference proposals are deduped and never conflict with an active dimension.**
  `preferences.learn` now treats a pending suggestion as already-asked (no
  duplicate on every scan), skips any dimension that already has an active
  preference, and records a gate-staged suggestion exactly once in auto mode.
  Tests cover double-scan dedupe, active-dimension conflict, auto+ask staging,
  and the memory-off floor. Docs updated: `docs/harness/personal-memory.md`.
- **feat(memory): Personal Memory — learned preferences with evidence, not guesses.**
  Added `python/harness/eclipse_memory/preferences.py`: a closed style/format
  vocabulary (answer format, length, tone, research depth), deterministic
  inference with bounded trigger-phrase evidence, and a learner that proposes a
  preference only after 3 consistent observations across 3 distinct runs.
  Migration 34 adds `PreferenceObservation` and `MemorySuggestion.structuredData`;
  proposals stay inert until accepted through the existing suggestion route and
  the ONE memory gate. Dismissals suppress the inference (30-day cooling-off);
  explicit preferences win; memory/preference-learning off collects no evidence;
  secrets and current financial facts are never inferred. Wired into every turn
  and post-run analysis, exposed as `memory action="preferences"`,
  `/eclipse-memory/preferences` + operator-gated `/preferences/learn`, and the
  Eclipse Memory → Preferences tab (pending, remembered, evidence, scan).
  Tests: `test_preference_learning.py` (14), `test_preference_api.py` (3),
  `test_memory_tools.py` preferences surface, and the browser client contract.
  docs updated: `docs/harness/personal-memory.md`, `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`.
- **feat(modeling): mid-year DCF, rollover returns and comps FX/calendarization.**
  `DcfInputs.mid_year` discounts explicit FCF at `t+0.5` (default unchanged);
  LBO management rollover is a separate equity contribution with sponsor/
  management exit split and sponsor-only IRR/MOIC; comps translate non-target
  currencies via `comps.fx`/`fxRate` and calendarize fiscal periods to the target
  year end with an explicit approximate warning. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): structural XLSX edits rewrite references.** Row/column
  insert/delete now rewrites formulas, defined names, merged ranges, conditional
  formats, data validations, hyperlinks, auto-filters and column ranges instead of
  refusing any formula workbook; tables/charts/pivots/OLE are still refused.
  Docs: `docs/harness/office-edit.md`.
- **feat(documents): full structural document edits.** PPTX now has
  `add_smartart_node` / `remove_smartart_node` / `set_smartart_node_text` and
  `set_smartart_layout` (donor diagram in the same deck); structural XLSX edits
  rewrite table/chart references, pivot table locations + cache sources
  (refresh-on-load), and OLE/legacy VML anchors. Docs:
  `docs/harness/office-edit.md`.
- **feat(modeling): exact quarterly comps calendarization.** A peer with
  `quarterly` periods is calendarized by a four-quarter TTM ending at the target
  fiscal year end (`quarterly_ttm`). Incomplete quarterly data now requires an
  explicit `calendarizationFactor`; otherwise the peer is excluded. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): editable PPTX chart data and SmartArt labels.**
  `pptx.replace_chart_data` replaces an embedded chart's categories and series
  caches while preserving chart type, axes and styling; `pptx.replace_text` also
  scans SmartArt diagram data so labels are editable without changing node
  structure. Docs: `docs/harness/office-edit.md`.
- **feat(pdf): optional incremental PDF editing.** When PyMuPDF is installed
  (`python/requirements-pdf-incremental.txt`, optional because AGPL/commercial),
  `document_edit` appends an incremental update and reports
  `preservationMode: "incremental"`; redaction then removes the text objects in
  place (`incremental_true_removal`). Without it, the pypdf rewrite/rasterized
  redaction path is used and labelled honestly. Docs: `docs/harness/office-edit.md`.
- **feat(modeling): comps peer auto-retrieval.** `financial_model_build` accepts
  `comps.peerSymbols` and resolves each through the same read-only
  `market_snapshot` + `financial_statements` bridge as every market tool; a peer
  with no usable price/share count is excluded with a note. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): the edit limits are now features.** Added DOCX image
  insertion and deterministic accept/reject tracked revisions; XLSX
  insert/delete rows and columns (conservatively refused on formula/merge/chart
  sheets rather than breaking references); PPTX slide duplicate/delete with
  relationship + notes remapping; and true PDF redaction that rasterizes the
  page so the covered text object is removed, not just painted over. Docs:
  `docs/harness/office-edit.md`.
- **feat(modeling): reports + LBO leverage.** `financial_model_build` now exports
  PDF/Word/PowerPoint deliverables alongside the workbook; LBO models support
  PIK tranches, a revolver with capacity/rate/minimum cash and a cash sweep that
  preserves the minimum. Docs: `docs/harness/financial-modeling.md`.
- **feat(guardrails): money-movement guardrails + confirm gate.** Added
  `python/harness/finance_guardrails/`: a deterministic, model-free layer that
  normalizes every money-shaped tool call into a `MoneyIntent` and evaluates
  scam/coercion markers (urgency, secrecy, impersonated authority, remote access,
  guaranteed returns, gift cards/wire-only), impaired spending (declared state +
  baseline/escalation signals), crisis mode + panic pause, aggregate
  per-transaction/daily/velocity limits, counterparty allow/block lists and
  novelty. A `confirm`/`escalate` routes the exact intent through the existing
  single-use approval store (`kind="money_guardrail"`, digest-bound) with a
  cooling-off + typed-confirmation challenge; a `deny` is terminal and explained.
  Enforced at the computer finance/click handlers, the browser click handler,
  the shell/terminal authorizer seam and the MCP effect authorizer (before
  grants), so a prompt or standing grant cannot bypass it. Operator routes `/finance-guardrails/*` + Settings › Money
  Guardrails; read-only agent tools `finance_guardrail_status`/`_check`.
  Docs updated: `docs/harness/money-guardrails.md` (new),
  `docs/harness/security.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md` +
  `skills/ARCHITECT.md` (ADR-055).
- **feat(documents): preservation-first Office/PDF editing.** Added
  `document_edit` (`python/harness/documents/edit/`): a closed `EditPlan`
  (DOCX text/table/core props, XLSX cells/formulas/rows/sheet rename, PPTX
  title/notes/text, PDF forms/rotate/annotate/metadata), an `OoxmlPackage` that
  copies untouched ZIP parts verbatim, `verify_ooxml` proving every non-target
  part is unchanged (and refusing on a relationship/XML/expected-text failure),
  and artifact-version publishing (originals are never edited in place). Adds
  `pypdf` for the PDF rewrite path (honest `PDF_LIBRARY_MISSING` when absent).
  Docs: `docs/harness/office-edit.md`, `docs/NAVIGATION.md`, ADR-054.
- **feat(modeling): deterministic 3-statement/DCF/LBO/comps + Excel model.**
  Added `python/harness/modeling/` and tools `financial_model_build` /
  `financial_model_audit`: validated `ModelSpec`, integrated IS/CF/BS/debt with
  balance and tie checks, DCF composed over `finance_facts.valuation`, LBO
  sources/uses/debt/IRR/MOIC, comps peer multiples/stats/implied ranges, and a
  formula-bearing workbook (Assumptions, Three Statement, Values, Checks).
  Docs: `docs/harness/financial-modeling.md`, `docs/NAVIGATION.md`, ADR-054.
- **feat(ui): crypto alt-data surfaces over the market pack.** Added the
  read-only `GET /api/crypto/alt-data` front door (same TS adapters as the agent,
  30s cache, honest UNAVAILABLE envelope), a `CryptoAltData` panel on Market
  Overview › Crypto (liquidations, long/short, TVL cards), and two catalog
  widgets `crypto-tvl` / `crypto-liquidations` in a dedicated
  `dashboard/crypto-widgets.tsx` (kept separate to respect the source-size
  budget; `market-overview.tsx` stays at its pinned 2760 lines). Docs:
  `docs/harness/market-data.md`.
- **feat(market): CoinGlass + Solscan adapters — the pack is now fully runnable.**
  Added `providers/coinglass.ts` (V4 liquidation coin-list + global long/short
  account ratio, `CG-API-KEY`) and `providers/solscan.ts` (V2 account detail,
  `token` header, Solana lamports). New records `LiquidationStats`/`LongShortRatio`,
  normalizers, gateway methods, and tools `get_liquidations`/`get_long_short_ratio`;
  `get_onchain_metric` now routes `etherscan → solscan` (EVM vs base58 address
  shape decides deterministically). Endpoints verified against official docs
  before implementation. Docs: `docs/harness/market-data.md`, ADR-053 in
  `docs/DECISIONS.md` + `skills/ARCHITECT.md`.
- **feat(market): Hyperliquid read-only perps adapter + hardened POST transport.**
  Added `safePost` to `connectors/security.ts` (https-only, DNS-pinned, timeout,
  response/request-size caps, no redirects) so the GET-only bridge can carry
  Hyperliquid's POST-only `info` endpoint. New `providers/hyperliquid.ts` serves
  perps funding/open-interest (keyless, read-only; funding is hourly and
  annualization stays labelled derived). Hyperliquid is now `implemented=True`;
  funding/OI priority falls back `binance → hyperliquid`. Docs updated:
  `docs/harness/market-data.md`, ADR-053 amendment in `docs/DECISIONS.md` +
  `skills/ARCHITECT.md`.
- **feat(market): crypto/on-chain/alt-data pack — TVL + on-chain capabilities.**
  Added `tvl` and `onchain` capabilities to the market layer with runnable
  DefiLlama (`providers/defillama.ts`, keyless protocol/chain TVL) and Etherscan
  (`providers/etherscan.ts`, keyed EVM account metrics) adapters, new
  `TvlSnapshot`/`OnchainMetric` records, `get_tvl`/`get_onchain_metric` tools, and
  catalogued-only descriptors for CoinGlass/Solscan/Hyperliquid (`implemented=False`,
  so the router never calls a provider without an adapter). Added
  Etherscan/CoinGlass/Solscan vault keys. Why: extend asset-class coverage through
  the ONE router/bridge/quality path instead of a second pipeline, and never fake
  data for sources that are keyed or POST-only. Docs: `docs/harness/market-data.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-053).
- **ui(sidebar): give the app list its own scroll pane while chat history is open.**
  The sidebar's single long scroll is now a fixed control strip (mode switcher
  and launchers) above two independently scrolling panes: a flexible chat
  history pane and a capped Apps strip. A long conversation list can no longer
  push the apps out of reach, and the history list fills its pane instead of a
  fixed `45vh` cap. Files: `src/components/layout/sidebar.tsx`,
  `src/components/layout/chat-history-panel.tsx` (`fill` prop),
  `src/lib/i18n/dictionaries/en.ts` (`sidebar.apps`, ratchet re-pinned).
  no doc change beyond this entry — presentation only; nav contracts unchanged.
- **fix(sidebar): put pages above chat history and stop the app rows shrinking.**
  Corrects the previous layout: on ChatBot only, the app list is the top
  scrollable strip and chat history fills the space below it, separated by a
  divider. Nav anchors are now `shrink-0` (also in `saved-pages-nav.tsx`) so rows
  keep their 32px height and spacing inside a constrained scroll pane instead of
  compressing. no doc change beyond this entry.
- **revert(sidebar): restore the original single-scroll navigation.**
  Reverted the two sidebar layout experiments (the split history/apps panes and
  the Apps strip above them). Chat history sits under the menu again, only on the
  ChatBot tab, in the original one-column scroll. Restored `sidebar.tsx`,
  `chat-history-panel.tsx`, `saved-pages-nav.tsx`, and the `en.ts` /
  `size-budget.test.ts` entries to their pre-change state. no doc change beyond
  this entry.
- **feat(learning): add class-authorized self-modification (Tier B).**
  `self_improvement/self_modification.py` auto-accepts contract-clean,
  evaluated candidates and auto-enables **read-only** learned skills under an
  operator-authored policy (`HARNESS_SELF_MODIFICATION` modes off/accept/enable),
  with TTL expiry, active-skill/daily caps, durable audit rows, revocation and
  pause/run/status routes under `/evolution/self-modification`. Effectful skills,
  tool widening, financial actions and policy edits remain operator-only. Tests:
  `test_self_modification.py`. Docs: `docs/self-improvement/SELF_MODIFICATION.md`.
- **feat(skills): port the Minara catalog into the bundled Eclipse skill library.**
  Added 74 skills under `python/harness/skills/library/<category>/<skill>/`
  (21 finance, 13 external finance references, 3 research, 2 quality, 35 system),
  each with a validated `skill.json` and an Eclipse-specific `SKILL.md` that uses
  only real registered tool names. Read-only analysis skills are enabled;
  execution, publishing, plugin-backed and iOS skills are inert drafts. Trading
  and fund-moving skills stop at an approval-gated plan because `trade.execute`
  is forbidden. Updated the research-category discovery assertion to a subset
  check so new research skills do not make the test brittle. Tests: 121 focused
  skills tests passed; `npx tsc --noEmit` passed. no doc change beyond this entry
  — the new skills are self-describing and registry behavior is unchanged.
- **docs(changelog): restore the 7-section window and normalize one stray CRLF.**
  Moved the oldest dated section (`2026-10-21`) into
  `docs/changelog/2026-10.md`, keeping the newest seven sections, and normalized
  a single CRLF in `docs/harness/roadmap/progress/phase-05-progress.md` so the
  tracked-file line-ending guard passes. no behavioral change.
- **test(harness): re-audit roadmap Phase 5 (coding agent/approvals).**
  Added `test_phase5_audit.py`: code-agent/finance separation, `allowMcpTools`
  false, all 389 `plan_only` tools read-only against the real registry,
  `edit_verify` external-action removal, unknown-autonomy fail-closed, shared
  `claim_guarded`, and `RunLineage` task checkpoints. Targeted gates: 38 passed.
  Correction recorded: the roadmap's literal "finance has no code tool" is stale
  after later phases (`scaffold_kit`, `capability_*`, `python_env_*` are now
  effect/approval-gated); no external code action reaches finance. Docs:
  `docs/harness/roadmap/progress/phase-05-progress.md` and the Phase 5 roadmap
  `last-verified`.
- **test(learning): pin the operator gates.**
  Added `test_learning_gates.py` and an accept-route 403 test: candidate
  acceptance, skill authoring, skill lifecycle writes, and effectful capability
  activation remain operator-gated; the advisory cadence writes only observed
  outcomes. These tests run in the default Python suite. Documentation:
  `docs/self-improvement/GATE_REGRESSION.md`.
- **feat(advisory): explain and honestly backfill legacy debt.**
  `GET /advisory/legacy` reports why each legacy recommendation is unscorable
  (`no_horizon`, `no_entry_price`, `no_symbol`, `no_method`).
  `POST /advisory/backfill-entry-prices` (operator-gated, dry-run first) fetches
  a real historical bar at the decision's creation time and stores it with
  source/as-of provenance; a missing bar is a named skip, and existing prices
  are never overwritten; dry-run is the default and applying requires an
  explicit `dryRun:false`. The live 14 legacy rows stay unscorable (no horizon,
  no price, non-tradable symbols). Tests: `test_advisory_backfill.py`.
- **feat(advisory): add a bounded unattended outcome-scoring cadence.**
  `advisory/cadence.py` scores due, priced recommendations on an interval,
  skips no-price/not-due rows with named counts, makes no market request when
  nothing is due, and is disabled by `HARNESS_ADVISORY_AUTO_EVALUATE=0`.
  Operator surfaces `GET /advisory/cadence` and `POST /advisory/cadence/run`
  expose the last tick; the runtime lifespan starts/stops the single bounded
  task. No approval gate is touched; no legacy score is invented. Tests:
  `test_advisory_cadence.py`.
- **fix(learning): reconcile advisory scoring and make lesson keys structural.**
  The advisory gate and scorecard now share one canonical definition
  (`advisory/scoring.py`: evaluated / scorable / no_entry_price / unscored /
  not_due); `auto_evaluate` scores only due rows with an entry price and counts
  the two skip reasons separately. Lesson recurrence is keyed by the recorded
  procedure/failure evidence, not the templated text or a stored signature;
  explicit corrections are eligible at recurrence 1. Memory promotion runs the
  recurrence + conflict gate before activating a proposed row. Legacy advisory
  rows get an additive `legacyUnscored` mark; no score is invented. Tests: 282
  related advisory/learning/skills/memory tests passed; `npx tsc --noEmit`
  passed. Docs: `docs/self-improvement/LOOP_MAP.md`,
  `SCORING_CHANGES.md`, `RECURRENCE_FIX.md`, `MEMORY_PROMOTION.md`.
- **feat(learning): close the candidate→draft→accept→score→retire loop.**
  The operator accept route now accepts `detected` and auto-drafted candidates,
  re-validates the contract, creates/keeps the inert skill and records
  `accepted` (never enables). Explicit corrections draft on the first
  occurrence; inferred procedures still require recurrence. Startup evaluates
  learned drafts and used learned skills, and deprecates a non-discriminating
  skill instead of keeping it. Proposed memory promotes after recurrence ≥2 with
  a clean conflict gate; conflicting proposals stay proposed. Legacy reviews are
  marked `legacyUnscored` without rewriting history. All approval gates are
  unchanged. Tests: 277 related learning/skills/memory/advisory tests passed;
  `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/LOOP_MAP.md`, `docs/self-improvement/CHANGES.md`,
  `docs/self-improvement/loop-closure.md`.
- **fix(chat): make the message rail legible when unselected.** Only the
  unselected ticks were lightened (`bg-muted-foreground/70`, was `/45`); their
  size and the active/hover states are unchanged, so the rail stays visible on
  both light and dark glass without getting heavier. no doc change — visual
  contrast fix.
- **feat(learning,graph): tool-widening safety case, boot-time recall, graph UI
  polish.** Added the evidence-gated `self_improvement/widening.py` ratification
  package (read/compute only, refusal by default) with its spec and tests; startup
  now consolidates duplicate automatic memories (contradictions left for review)
  and backfills completed runs into the session index; the self-improvement
  denylist now also covers the widening/capability/grant surfaces and can no
  longer be narrowed by a caller; graph node cards, canvas, home and globals
  styling were tightened. `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md`, `docs/self-improvement/tool-widening/`,
  `docs/graph-studio.md`, `docs/harness/tool-registry.json`.
- **feat(strategy-studio): make the studio a workspace you can come back to.**
  The tab was a JSON sandbox with amnesia: a refresh lost the thesis, spec,
  strategy and result, and saved strategies/experiments were never listed. It now
  has a saved-strategy library, schema-versioned `localStorage` persistence with
  `?strategy=&experiment=` deep links, this strategy's experiment history with
  `/quant/compare`, a data-coverage preflight against the stored-series catalogue
  (absent ≠ impossible; unreadable = unknown), debounced inline validation with
  copyable spec paths, and metric definitions from the runtime. Also fixed the
  strategy record's description being passed as its name, and the paper approval
  recording the same actor for request and decision. Shared `EquityChart`,
  `DrawdownChart`, `TradeTable` and `MetricGrid` were extracted to
  `src/components/screens/backtest/shared/` and the Backtest bench now imports
  them (net −118 lines there). Honest labelling: the paper button replays the
  research window and says so. Docs updated: `docs/strategy-studio.md` (new),
  `docs/NAVIGATION.md`.
- **feat(strategy-studio): research without hand-written JSON.** Robustness is
  now derived from the spec: `src/lib/strategy-studio/param-space.ts` proposes
  the engine-supported dotted paths (indicator params, sizing, stop/target and
  risk limits) and builds `paramSpace`/`paramRanges` from min/max/step rows. A
  "Run the robustness suite" button runs walk-forward → Monte-Carlo → robustness
  into one page, and `research-verdict.ts` calls it `robust` ONLY when the whole
  suite ran and every scored check passed (partial = inconclusive, any failure =
  fragile; every threshold is printed in its check label, and `info` rows are
  never scored). The Edge Report now renders in full through the shared
  `EdgeReportView` (grade, axes, flags, Artifact Center figures, markdown) used
  by both the Studio and the Backtest bench. Added six starter templates labelled
  as examples, not recommendations, and an on-demand runtime research plan
  (hypothesis, assumptions, acceptance criteria, potential biases). Tests:
  `param-space`, `research-verdict`, `templates`, `research-studio`,
  `edge-report-view`. Docs updated: `docs/strategy-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(strategy-studio): no-code builder, forward paper, versions and
  publishing.** The spec card now has a Builder view over the same JSON
  (`src/lib/strategy-studio/spec-edit.ts` deep-clones; unknown fields survive;
  nested/expression rules are marked `advanced` and left to the JSON tab instead
  of being silently rewritten). Paper got two explicit modes
  (`paper-window.ts`): **forward** from the day after the research window ends,
  or a **replay**; a forward window with no forward period is refused, never
  downgraded. Every paper run is listed in a track record with its window and
  drift against the latest backtest (never against another paper run). Added a
  versions panel with structural diff (`/quant/strategies/{id}/diff`) and JSON
  bundle export (`format=json`), plus a grade-gated publish into the local
  gallery. Tests: `spec-edit`, `paper-window`, `spec-builder`, `paper-panel`.
  Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **chore(test): green the JS suite after the studio work.** Normalised the one
  stray CRLF line in `mobile-bottom-nav.tsx`, `sidebar/config.ts` and
  `sidebar/config.test.ts`, and re-pinned the `stock-chat.tsx` line budget
  1584→1589 for the Strategy Studio keep-alive mount (the page lives in
  `components/screens/strategy-studio/`). Full Vitest run: 4065/4065.
  no doc change — test/hygiene only.
- **feat(strategy-studio): connect the studio to Projects, the dashboard and a
  share link.** `ProjectLink` attaches the current strategy to a project
  (`kind: "strategy"`, `ref: strategy.id`, version/symbols in `meta`) through a
  new `projectClient.addMember`; the dashboard gains a `strategy-studio` widget
  that lists saved strategies and deep-links each workspace; the header copies
  the exact `?strategy=&experiment=` link. Docs updated:
  `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **fix(harness): close eleven pre-existing Python suite failures; add paper
  health.** Advisory cadence/scoring now honour the caller's clock
  (`auto_evaluate(now=…)`, forwarded by `run_once`) instead of re-deriving
  `now_iso()`, so a not-yet-due row can no longer be scored after 00:00 UTC; a
  regression re-check no longer short-circuits to an unchanged-passed record
  with no dimensions; the migration-matrix test uses the production
  `add_column_already_present` guard (now a shared module helper); the four
  DeFi/derivatives tools are allowlisted for the finance agent; the graph API
  tests bind their own service instead of the process-wide singleton; the Python
  size ratchet is re-pinned to the measured tree and its duplicate `service.py`
  entry removed. The studio also gained a pure paper-health badge (fresh /
  stale >30 days / drifting ≥10 return points or ≥0.5 Sharpe, thresholds
  printed). Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **feat(strategy-studio): share card, portfolio runs, import, provider check,
  mobile summary.** The studio now exports/imports portable bundles (import
  validates before saving), offers an opt-in 30-day provider check beside the
  stored-catalogue preflight, runs two or more SAVED strategies through
  `/quant/portfolio-backtest` with the shared result panels, produces a
  read-only Markdown share card (identity, metrics, grade, paper state,
  disclaimer), and shows a compact read-only summary under `md`. The dashboard
  widget joins the local gallery so each strategy shows the grade its published
  version earned. Fixed the last two lint warnings (`withCosts` extracted,
  artifact `<img>` documented). Full Python suite: 8707 passed, 29 skipped, 0
  failed. Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **feat(strategy-studio): recursive rule builder + mobile summary.** The
  builder now edits nested rule groups (`rule-tree.tsx`) through the pure tree
  API in `spec-edit.ts` (`readTree`/`addTreeNode`/`updateTreeNode`/
  `removeTreeNode`/`setTreeCombine`); expression operands and nesting deeper
  than three levels stay read-only with a pointer to JSON. Added a compact
  read-only summary under `md`, a Markdown share card, bundle import, an opt-in
  provider check, portfolio backtests over saved strategies, and a dashboard
  widget that shows the grade a published version earned. Docs updated:
  `docs/strategy-studio.md`, `docs/NAVIGATION.md`.

## 2026-10-27
- **ui(graph): align the New workflow button with the shared menu system.** The
  template picker is now a real `DropdownMenu` (anchored, dismissable, keyboard
  navigable) instead of a hand-rolled floating panel, and the trigger uses the
  standard primary button sizing alongside Generate from prompt.
  no doc change — UI consistency only.
- **ui(graph): move Start workflow into the header toolbar.** The center-stage
  floating run button is gone; the same save-and-run control now sits inline in
  the editor header row and uses the standard black primary button style. Docs:
  `docs/graph-studio.md`.
- **fix(learning,rsl): finish the loop-closure and widening verification.** Migration
  32 no longer re-adds columns that the base schema already creates (a fresh or
  historical db now reopens), the published tool registry is regenerated, the
  chat-code profile declares `learning_candidate_validate` and
  `skill_discrimination_check`, and the two recovery tests now retry the same tool
  (a different tool that merely succeeds is not recovery evidence). A
  discrimination gap (named base, no outcome metrics) is reported on the
  dimension but is non-blocking, so an ordinary patch still activates; a
  mandatory regression/indistinguishability still blocks. Size ratchets re-pinned
  to the measured tree. Docs: `docs/self-improvement/loop-closure.md`.
- **feat(learning): close the skill, memory and recall loops.** Automatic
  memories now carry `authority=automatic` (source `automatic_learning`) instead
  of masquerading as explicit; gate-approved model preferences save under
  `automatic_selective`; recurring candidates update their occurrence count and
  auto-draft an inert `status=draft` skill; recorded user corrections become
  scoped candidates; startup consolidation merges duplicates but leaves
  contradictions for review; startup quarantines nonconforming legacy
  candidates and drafts the ready ones; startup also runs the deterministic
  evaluation for every `learned.*` draft (enabling stays operator-only); and
  startup backfills up to 200 historical runs into the session index. A preference inside a long prompt is
  stored as its own clause, not the whole prompt; a save proposed by the
  model-facing `memory` tool or post-run analysis is labelled
  `automatic_learning`/`automatic`, not explicit. `skill_list`/`skill_view` now
  expose store-only drafts, and `learning_candidate_list` prints the drafted
  skill id. `session_search` skips the local caller-id filter (indexed messages
  are unowned in single-user mode), retries a multi-token query with ANY terms,
  prints `matchMode`, and indexes an explicit `run_id` once before retrying.
  Migration 33 restores `LearningCandidate.occurrenceCount` on older stores.
  Nothing is auto-enabled: operator acceptance, evaluation and promotion remain
  the only activation path. The usage report now separates `automaticSaved` from
  explicit saves. Tests: 361 related memory / skills / learning / session tests
  passed; `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md` (Autonomy update).
- **feat(rsl): add an evidence-gated tool-widening safety-case builder and
  freeze the mechanism it protects.** `self_improvement/widening.py` assembles a
  pure, deterministic ratification package for adding one read/compute tool
  (need, holdout, replay, deny path, conclusion stability, blast radius, TTL,
  revocation); it never grants, auto-applies or self-renews. `security.py` now
  refuses RSL targets under `self_improvement/**`, `capabilities/**`,
  `grants.py` and `recovery/envelope.py`, and the frozen denylist can no longer
  be replaced by a caller. Tests: `python/tests/test_widening.py` (16 targeted
  tests passed with the related RSL/autonomy/capability suites). Docs:
  `docs/self-improvement/tool-widening/{corrections,diagnosis,safety-case-spec,design,risks}.md`.
- **feat(learning): expose the accept-route dry-run and the mandatory flag.**
  `learning_candidate_validate` is a read-only probe that returns the HTTP status
  the operator accept route would produce (404/409/422/200) without writing, so
  the negative paths are observable from chat. The discrimination probe prints
  `mandatory=True/False` in its text. Candidate rows already print procedure
  steps and occurrence count. Live: `gate.ok=true`, `accepted=2`, `detected=0`,
  typed 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(learning): add a read-only discrimination probe and close the remaining
  read gaps.** `skill_discrimination_check` lets a chat run prove
  identical→failed / better→passed / worse→failed with caller-supplied metrics
  without persisting an evaluation. `skill_reviews` now prints the
  discrimination detail. Candidate rows print `occurrenceCount` and the
  procedure step count; the queue line prints `quarantinable`; the scorecard
  prints `needsBackfill`; `learning_review_list(status="superseded")` is a valid
  filter. The app-API proxy is excluded from recoverable-tool lessons (a retry
  cannot fix a down front door), so the current typed lesson is the genuine
  `research_search` transient-`UNAVAILABLE` retry. Live: `gate.ok=true`,
  `accepted=2`, `detected=0`, current typed lessons 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): withdraw the false lessons and keep only a replayable one.**
  The gate now prints the memory domain too (duplicates/conflicts/residue/
  related), review rows print the evidence list, candidate rows print
  `occurrenceCount` and the procedure step count, and a re-review refreshes the
  review timestamp so a corrected lesson is current. The two `app_api_get`
  lessons were superseded and their candidates rejected; the sole current typed
  lesson is the genuine `research_search` transient-`UNAVAILABLE` retry, accepted
  as `cand_2a07300e`. The generic "record the working source preference" lesson
  is rejected as a generic action. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 1. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): only a genuine same-capability recovery becomes a lesson.**
  A later tool that happens to succeed is no longer treated as recovery
  evidence; the recovery must be the same tool or the same recorded capability,
  and its body must not itself report `UNAVAILABLE`/`TimeoutError`/`TOOL_FORBIDDEN`.
  The two accepted lessons whose `app_api_get` replay timed out were withdrawn
  (`rejected`, retained) and their reviews superseded; a genuine
  `research_search` retry from `run_615d7fce` was reviewed, encoded and accepted.
  Review rows now print the evidence list, and re-evaluating a version marks
  earlier same-version evaluations `superseded` so a self-referential pass is
  no longer presented as current. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 2. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): print the full candidate census and `relatedCount`.** The
  candidate list now reports the complete store counts by status (not only the
  page) and the number hidden by the 50-row cap, so a legacy row cannot vanish
  from the audit. Memory inventory prints `relatedCount` alongside the
  duplicate/conflict/residue dry-run counts. Gate remains `ok=true`, gaps empty,
  accepted 3, detected 0. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): make every gate domain readable from the bound tool.** The
  `learning_review_list` gate block now prints `contractSince`, current reviews
  (typed/justified/unjustified), legacy reviews, current and legacy advice
  (evaluated/unscored/overdue), and candidates (accepted/detected/nonconforming/
  stale). `learning_candidate_list` prints `staleDetected`/`nonconforming` and an
  accepted row's limitations; `memory(action="inventory")` reports the
  consolidation dry-run counts and cross-type `related` pairs. Accepted the last
  actionable candidate (`cand_421aa3c1`, with the recovery-tool-timeout
  limitation): live `accepted=3, detected=0, gate.ok=true`. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): expose the gate on the read tool; tighten discrimination.**
  `learning_review_list` now returns `gate` (ok, gaps, current/legacy windows) so
  a chat run can read `gate.ok` without HTTP-body permission. A version with a
  named base but no outcome metrics now reports `discrimination=needs_review`
  (explicit gap), not `not_applicable`; a root version stays
  `not_applicable`. Residue detection is limited to <=2 tokens or the known
  `loopback can save` fragment, so a real short preference is not mislabelled.
  Live: `system.anatomy-figure` v1.1.1 vs v1.1.0 is `needs_review`; gate remains
  `ok=true`, gaps empty. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): gate the current contract window, report legacy separately.**
  `gate_report` now counts reviews and advice created since
  `HARNESS_LEARNING_CONTRACT_SINCE` (default `2026-10-28T00:00:00Z`) for its pass
  criteria, and reports pre-contract rows under `legacyReviews` /
  `legacyAdvisory` instead of letting them keep the gate red forever. The advice
  gate is due-aware: an unscored recommendation is a defect only at its stated
  horizon, not before. Live result: `gate.ok=true`; current window 3 reviews
  with 0 unjustified nulls and 2 current recommendations not yet due; legacy
  window retains 197 bare nulls and 109 unscored rows for audit. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(advisory): record a basis method and a stated horizon at issue time.**
  Every recommendation now gets `method` (explicit, else the basis class
  `portfolio_computation`/`portfolio_read`/`model_advice`, never the action
  verb), `horizon` (explicit, else the policy default `30d`), and `dueAt`; both
  are recorded as basis entries. Quote tools (`market_get_quote`/`get_quote`)
  now contribute an entry price, so a later evaluation can compute a return.
  Backfill applied to the live ledger (111 rows); `advice_missing_horizon`
  cleared and the scorecard reports `byMethod`/hit rate/demotion. Also reports
  memory residue (`fragment: <=4 tokens, no subject`) without touching it, and
  diagnoses a generic-only all-fail route as a provider failure. Regression
  evaluation no longer compares a version against itself. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): persist the falsifiable method and unfreeze intake.** The
  `LearningCandidate` table now stores `condition`, `action`, `failedCall`,
  `recoveredCall`, `precondition`, `replayTest` and `occurrenceCount` (migration
  32), so the writer no longer drops the fields the contract requires. A
  previously-created detected candidate was repaired from its run draft and is
  now conforming; intake was re-enabled (`automatic_selective`), a conforming
  specimen was created and accepted (accepted=2, detected=0,
  nonconforming=0). `_regression_dimension` never compares a version against a
  later one (the 1.1.0-vs-1.1.1 inversion), a completed review updates its
  existing row instead of duplicating, and persisted nulls keep
  `justified`/`evidenceChecked`. Fresh `system.anatomy-figure` evaluations now
  carry the `discrimination` dimension (`not_applicable`, explicit gap). Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(harness): persist null justification, dedupe reviews, expose accept/eval.**
  `_bounded` now keeps `justified`/`evidenceChecked` at the outcome level, so a
  saved null no longer reads as bare; a completed review for one run updates the
  existing row instead of appending a duplicate. Adds operator
  `POST /learning/candidates/{id}/accept` (status only; never enables a skill),
  extends `POST /skills/{id}/evaluate` with `baseVersion`/`metrics`/`baseMetrics`
  so `discrimination` is reachable, reports `intake_disabled` when
  `skill_learning_mode=off`, and records a missing advisory method as
  `unclassified` rather than echoing the action verb. Live state: accepted 1,
  detected 0, duplicate review superseded, fresh evaluation includes
  `discrimination`. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(harness): make pre-contract learning rows visible and drainable.** The
  review list now prints every typed lesson and labels a bare null
  `UNJUSTIFIED`; the candidate list shows `failedCall`/`recoveredCall`/
  `precondition`/`replayTest` and a `CONTRACT VIOLATION` per stored row. The gate
  counts unjustified nulls and nonconforming candidates, not only typed lessons.
  Adds operator-gated quarantine (`POST /learning/candidates/quarantine`) and
  advisory backfill (`POST /advisory/backfill`) that exposes legacy
  method/horizon as `unscored` without inventing a result. Consolidation now
  resolves near-duplicates (containment/subject link) and the verbosity conflict
  ("straight to the facts" vs "detailed with sources"), still supersede-only.
  Applied to the live stores: 48 nonconforming candidates quarantined, 2 stale
  candidates expired, 2 memory records superseded, 109 advisory rows backfilled,
  and one real review produced a typed lesson (recurrence 1/2). Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(harness): close the learning loop, not just record it.** Reviews now emit
  a typed lesson (`condition -> action -> evidence`) or a justified `no_learning`
  null (reason + `evidenceChecked`), and carry a cross-review signal aggregate
  that requires two distinct runs before a lesson is eligible. Failure-recovery
  candidates must carry the failed call, recovered call, precondition, procedure
  and a replay test; templated titles and constant `0.55` confidence are rejected
  at creation. Skill evaluation adds a `discrimination` dimension against a named
  base on outcome metrics (identical results fail; repeated identical passes are
  flagged as a broken harness). Advisory decisions record `method` + `horizon` +
  `dueAt`, and the scorecard reports unscored/overdue/per-method calibration and
  demotes methods that do not score. Route health diagnoses generic-vs-market
  routing defects, active memory is consolidated (duplicates + contradictions
  supersede to the later statement, retained), and `gate_report` treats an
  unconsumed candidate queue as a design failure. Docs:
  `docs/self-improvement/loop-closure.md`; `docs/NAVIGATION.md` rows updated.
- **fix(harness): scope the candidate empty state and keep the read-only footer.**
  A status-filtered empty listing now says "No learning candidates captured with
  status 'accepted' yet." instead of implying the whole store is empty, and every
  empty response keeps the read-only footer. A request above the 50-row cap now
  says it was capped. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(harness): upgrade the graph-run schema before indexing `jobId`.**
  `GraphRunStore` created `idx_graph_run_job` inside the base schema script, so a
  legacy `HarnessGraphRun` table without `jobId` raised `no such column: jobId`
  and left the whole graph runtime unavailable at boot. The index is now created
  after the column upgrade; regression test covers the legacy table. no doc
  change - bug fix; no contract, setup, or architecture change.
- **fix(harness): report the true candidate total past the 50-row page.**
  `learning_candidate_list` now reads `count_candidates(status)` and says
  "Showing N of M" when the page is truncated, so an operator cannot mistake the
  tool's output cap for the queue size. Adds one read-only store count method and
  a regression test. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(graph): make the connection aurora actually visible.** The first pass
  was too faint (2px, blurred, 16–55% opacity). Now a 3px hot core with an
  accent box-shadow glow plus a wider blurred haze, breathing 45–100% on the
  same 8s loop. Still respects reduced motion and Glow-off.
  no doc change - tuning only.
- **fix(harness): `learning_candidate_list` resolves the Eclipse-Memory store by
  capability.** It now prefers `memory_service.store` and only accepts
  `learning_store` when it exposes `list_candidates`, so the research path store
  can no longer cause an `AttributeError`. The empty state reads
  `skill_learning_mode` and no longer promises automatic capture when detection
  is off (or unreadable); tests now use the production wiring. no doc change - bug
  fix; no contract, setup, or architecture change.
- **feat(graph): minimal live connection aurora on node edges.** Wired nodes show
  a small blurred accent light bar on the left (`hasIncoming`) and/or right
  (`hasOutgoing`) edge, breathing/bobbing on an 8s loop with the two sides
  phase-offset. Respects `prefers-reduced-motion` and the Glow-off preference.
  Rendered in `eclipse-node.tsx`; keyframes/classes in `globals.css`.
  no doc change - visual restyle only; uses existing node data fields.
- **feat(chat): show the Python program in the activity step.** `analysis_run`
  and `execute_python` now emit a bounded (`8 000` chars), secret-redacted
  `codePreview` on `tool.requested`, so the source appears inside the activity
  step's existing expandable details (not as a separate panel), with honest
  truncation. The preview is persisted with the run. Producer:
  `code/activity.py::tool_code_preview`;
  emitter `graph.py`; client `ActivityItem.codePreview` + `activity-item.tsx` /
  `output-panel.tsx`. docs updated: `docs/chat-ui-audit.md`, `docs/NAVIGATION.md`.
- **feat(graph): accent-aurora node restyle.** Graph nodes now use the frosted
  `node-card` material with a thick accent border, a plain foreground-coloured
  icon (no tinted tile), and a per-node **aurora** halo when wired. Wires and
  handles take the source node's category accent (with a gradient stroke + soft
  glow) instead of the neutral slate/sky hardcode. Category accents moved to
  `lib/graph-studio/port-style.ts` (`categoryAccent`) as the single source.
  no doc change - visual restyle; new node/edge data fields are internal to the
  canvas renderer and no contract changed.
- **fix(graph): aurora moved off the node body and onto its connected edge.**
  Follow-up to the node restyle: the accent halo no longer wraps the whole card
  (which read as background glow). It is now a thin drifting light bar on the
  node's **left** side when it has incoming wires and on its **right** side when
  it has outgoing wires (both sides when both). Node borders are near-black
  again, not accent-coloured; selection uses an accent outline offset outside
  the frame. Node glass was deepened (multi-layer tint, stronger blur, inset
  sheen). no doc change - visual restyle only.
- **fix(graph): n8n-style compact nodes, theme-driven colour.** Narrowed nodes
  from 244px to 184px and moved the icon to a centred top slot with the label and
  category stacked beneath. All glow (aurora, wire stroke/glow, handles, `+`
  affordance, selection outline) now reads `var(--primary)`, so it follows the
  active theme instead of a hardcoded per-category palette; the unused category
  accent table was removed from `port-style.ts`. no doc change - visual restyle
  and internal cleanup only.
- **fix(graph): remaining blue chrome moved to the theme accent.** The floating
  "Start workflow" button lost its blue glow and now uses a shared
  `.graph-accent` control (border/tint/text from `var(--primary)`, no box-shadow).
  Applied the same class to "Add node", "Add first step", the wire insert `+`, and
  the schedule action; focus rings, active toggles, inspector tabs/checkboxes and
  the editor icon now use primary tokens instead of `sky-*`. Running-status dots
  stay sky (semantic state, not chrome). no doc change - styling only.
- **feat(graph): black bezel nodes with an inner aurora.** Node body is now true
  black (not grey), framed by a wide 5px solid-black border with a larger radius.
  The identity block is centred with a bigger icon and a single label - the
  category kicker and the divider line above the ports were removed. When a node
  is connected, an accent aurora now drifts **inside** the card (radial sweep,
  gated by `data-incoming`/`data-outgoing`) instead of hugging the outside edge.
  Node border no longer changes colour for run status (the status badge remains).
  no doc change - visual restyle only.
- **fix(graph): side aurora, centred handles, glass matched to the system.** The
  aurora moved back out of the card to the connected **side** (left = incoming,
  right = outgoing) as a drifting light bar. Port handles are now centred on the
  node's vertical midline (fanned only for multi-port sides), so wires meet the
  middle of the card like the reference. `.node-card` now uses the exact
  `.glass-card` material recipe (black tint, 18px blur, saturate 1.35, inset
  highlights) instead of a bespoke grey gradient. no doc change - visual restyle
  only.
- **fix(graph): node icons tinted with the accent and heavier stroke.** Icons are
  now outline-style but rendered at `var(--primary)` with `strokeWidth 2.5`
  (was muted `text-foreground` at default weight), so they read solid rather
  than faint inside the black card. no doc change - visual restyle only.
- **fix(graph): 10px node bezel, solid white icons.** Node border widened from
  5px to 10px. Icons are now solid white filled glyphs (`fill=currentColor`,
  thin residual stroke) instead of accent outlines. Side aurora stays on the
  connected wire side and was nudged out to clear the thicker bezel. no doc
  change - visual restyle only.
- **fix(graph): solid white icons, inner animated aurora, graphite glass.** Icons
  render Phosphor `weight="fill"` (true solid glyphs) in white instead of light
  outline strokes. The accent aurora moved back inside the card as a diagonal
  sheen that continuously travels beneath the glass on connected nodes. Node body
  lifted from pure black to a graphite tint (`rgb(34 34 39 / 0.72)`) so the black
  bezel and white icon have contrast. no doc change - visual restyle only.
- **fix(graph): wider nodes and a dominant icon.** Node width restored to 244px
  (from 184px) so port labels and long titles fit again, and the filled icon
  grew to 34px in a 48px slot — clearly larger than the 12.5px label. Node body
  darkened to charcoal and the aurora is now a wave running along the connected
  side. no doc change - visual restyle only.
- **feat(graph): reference-accurate node card.** Nodes are now wide 244px cards
  (112px min height, 18px radius, 4px black bezel) with a **horizontal** identity
  block: solid white filled icon on the left, 16px white title over an 11px muted
  category subtitle on the right. Visible per-port label rows removed; handles
  sit on the edge midpoints (fanned per port) with names in the tooltip, and the
  add-next `+` follows each output handle on hover. Aurora is now a soft radial
  bloom anchored at each connected edge midpoint (left/right) that breathes
  in-place, spilling outside the bezel and washing into the body. no doc change -
  visual restyle only.
- **fix(graph): inner half-clipped live aurora + lighter glass.** Replaced pseudo
  blooms with an inner `.node-aurora-clip` layer (`overflow:hidden`) holding two
  glows centred on the card edges, so only the inner half is visible at the
  connected side (left incoming, right outgoing) and it drifts/breathes on a
  loop. Node tint lowered to `rgb(24 24 28 / 0.58)` so the 18px backdrop blur is
  actually visible. Content and handles sit above the clip layer. no doc change -
  visual restyle only.
- **fix(graph): smaller, visibly moving aurora.** Glow reduced to 110px / 104%
  and the animation now travels horizontally (translate 55% → 22% of its own
  width, plus scale/opacity) so the motion is obvious. Added a scoped
  `prefers-reduced-motion` override for `.node-aurora-glow`: the global reset was
  freezing it on machines with reduce-motion enabled. no doc change - visual
  restyle only.
- **fix(graph): aurora ripples in waves, smaller and lighter.** Glow shrunk to
  88px / 96%, gradient alphas lowered (55% → 22%), and the animation now follows
  a 5-stop undulating path (in/out + up/down) at 4.8s, so it ripples like an
  aurora. no doc change - visual restyle only.
- **fix(graph): real ribbon aurora instead of a moving blur.** Replaced the
  single radial glow with an inline SVG of three sine ribbons that drift
  horizontally at different speeds/directions (7/5/10px strokes, blurred,
  low opacity), faded away from the connected edge via `mask-image`. Renders a
  proper flowing wave, half-visible at the wire side, inside the clipped card.
  no doc change - visual restyle only.
- **fix(graph): aurora ribbons glow instead of reading as lines.** Layered three
  strokes as a wide soft curtain (14px / blur 12), a mid ribbon (7px / blur 7)
  and a thin bright crest (3px / blur 3), with `mix-blend-mode: screen` and an
  accent drop-shadow, on a 2-wave path loop. The strokes now fuse into a glowing
  band rather than separate lines.   no doc change - visual restyle only.
- **fix(graph): aurora is now pure blurred waves, no visible strokes.** Removed
  the thin bright crest and drop-shadow; all three layers are wide strokes with
  heavy blur (18/14/22px) and low opacity, screen-blended. Nothing resolves into
  a line — only soft flowing curtains. no doc change - visual restyle only.
- **fix(graph): aurora confined to a smaller side patch.** Wave canvas inset to
  18% top/bottom (64% height), mask fade tightened to ~48% of the width, and
  stroke widths reduced, so the glow is a compact patch at the connected edge
  instead of spanning the whole card. no doc change - visual restyle only.
- **fix(graph): aurora waves have real amplitude and show in light mode.** Wave
  paths now swing across most of the card height (control points near the
  viewBox edges) instead of tiny ripples that read as a flat line; canvas back to
  76% height with mask fade at 55%. Light mode switches the blend from `screen`
  to `multiply`, since screen-on-white was hiding the glow entirely. no doc
  change - visual restyle only.
- **fix(graph): aurora sized as a compact centred band.** Wave canvas reduced to
  48% height (inset 26% top/bottom) with `overflow: hidden` so blur can't bleed
  toward the card edges, and the side mask now fades out by ~42% of the width.
  Strokes tightened accordingly. no doc change - visual restyle only.
- **revert(graph): aurora removed from nodes entirely.** Deleted the inner
  aurora SVG, clip layer, wave CSS/keyframes and the `data-incoming`/
  `data-outgoing` hooks. Nodes are now just the black-bezel glass card with the
  icon/title/subtitle; wires carry the accent colour only. no doc change -
  visual restyle only.
- **feat(graph): compact node cards with inline parameter editing.** Node cards
  shrink from a 112px min-height / 4px bezel to a 46px identity header / 2px
  bezel (icon 48→32px, title 16→13px), with the run status folded into the header
  and the hover toolbar tightened. Up to two scalar config fields now render as
  inline editors on the card (text/number commit on blur or Enter, selects and
  booleans immediately, Escape reverts); fields supplied by an incoming edge show
  a read-only "From wire" chip. `config-fields.ts` adds presentation metadata
  (label/kind/options/inline) over the registry defaults, a shared
  `config-field.tsx` replaces the inspector's hand-rolled fields, and
  `dispatch(patch, { coalesceKey })` collapses a typing session into one undo
  entry. `buildNodes` reuses unchanged node objects so editing one node no longer
  re-renders the whole canvas. Docs: `docs/graph-studio.md`.
- **style(graph): node icons are plain outline glyphs.** Removed the filled
  Phosphor weight and the accent-tinted icon chip; nodes now use the same
  regular-weight, muted icon treatment as the rest of the site. no doc change —
  visual restyle only.
- **fix(graph): remove the node connection glow.** Deleted the side aurora spans,
  their CSS/keyframes, the handle glow and the now-unused incoming/outgoing
  flags. Nodes are a flat glass card; wires stay the accent colour. no doc change
  — visual restyle only.

## 2026-10-26
- **fix(customization): the "Custom theme" tile is now a real button.** It looked
  like the preset tiles but was a non-interactive `div`, so clicking it did
  nothing. It now commits an unsaved custom draft (same path as "Apply changes")
  or, while a preset is selected, returns to the saved custom theme. The tile
  shows the selected check once custom is active and previews the saved theme
  when a preset is being browsed. no doc change — UI interaction fix; token and
  preset contracts unchanged.
- **fix(dashboard): market dropdown options were white-on-white.** The global
  market `<select>` popup rendered on the native white background with light
  text; options now carry the repo-standard `bg-[#121212] text-foreground` so
  they are readable. No doc change — style fix only.
- **feat(graph): n8n-style Graph Studio workspace and canvas UX.** Replaced the
  cramped sidebar-tabs/right-rail layout with a full-bleed mode (app top bar and
  sidebar hidden while active), a **Workflows home** gallery (search, templates,
  prompt-to-graph, continue-editing), a slim editor header, and a collapsible
  execution dock. Nodes are compact icon-led cards with hover actions, typed
  ports, add-next/output "+" and run badges; edges expose insert-into-wire and
  delete on hover. Added a Tab/"+" node search overlay filtered by port
  compatibility, right-click menus, duplicate/copy/paste/select-all shortcuts,
  and a wider Parameters/Settings/Output inspector (last-run output is read-only
  from persisted runs). Compound edits are pure validated patches in the new
  `edit-ops.ts`; IR/compiler/runtime/authorization contracts are unchanged.
  Operator runs now use an explicit authorization dialog instead of
  `window.confirm`. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): keep the main sidebar and use the full workspace width.** The
  app sidebar is no longer hidden in Graph Studio; it stays as the Graph Studio
  mode panel. The workflow home is now a full-width n8n-style table (Workflows /
  Templates tabs, search, name/description/tags/owner/version/updated columns,
  row actions) instead of a constrained card grid. Docs:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(tables,graph): Tables page + workflow cards.** Added a top-level
  **Tables** tab (group `both`) that lists the existing `CustomDataset` tables and
  opens a read-only row grid with provenance/retrieved timestamps; creation stays
  in Settings → Market Data → Custom data sources. The Graph Studio mode panel now
  links directly to **ChatBot** and **Tables**, and the workflow home is back to
  the full-width **card gallery**. Docs: `docs/tables.md` (new),
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): restore the transparent frosted editor canvas.** The workflow
  editor no longer paints a solid canvas/header fill; the dot grid sits on the
  shell background again and nodes use the shared `.glass-card` surface. Hover
  toolbars/edge controls use semi-transparent theme backgrounds so they work in
  both light and dark. Docs: `docs/graph-studio.md`.
- **feat(tables): editable spreadsheet tables.** Tables is now a real data store,
  not a read-only dataset browser: create a table with typed columns, edit cells,
  add/rename/delete columns, add/delete rows and search. Stored in new
  `DataTable`/`DataTableRow` Prisma models (JDDS), exposed through
  `/api/tables` and `/api/tables/[id]`; connector-fed datasets remain under
  Settings → Data Sources. Docs: `docs/tables.md` (rewritten).
- **feat(overview): Agentic Overview workflow dashboard.** Added an **Overview**
  nav tab in Agentic mode with the workflow card gallery, New workflow / templates
  / prompt-to-graph, and continue-editing. Opening or creating a workflow switches
  to the Graph Studio editor. Docs: `docs/agentic-overview.md` (new), `docs/NAVIGATION.md`.
- **fix(nav): Graph Studio uses the standard sidebar.** Removed the dedicated
  Graph-mode Workflows panel: `graph-studio` is now a normal Agentic nav item,
  so the sidebar lists ChatBot / Overview / Graph Studio / Tables like every other
  page. `Alt+G` still opens Graph Studio (inside Agentic). Clicking Tables no
  longer forces a mode switch. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/tables.md`.
- **fix(nav,ui): Terminal boot fallback and consistent buttons.** A stored retired
  `graph` mode is ignored and hydration falls back to Terminal; the new Overview /
  Graph Studio / Tables surfaces now use the shared `Button` component (default /
  outline / ghost / destructive variants) instead of one-off button chrome.
  no doc change � retired-mode fallback + UI consistency only.
- **fix(shell): collapsed sidebar keeps its icons.** When the sidebar is
  collapsed, the Terminal / Agentic / Bots mode switcher becomes a compact icon
  rail instead of disappearing, and the standard nav list keeps every page icon
  reachable. no doc change � layout fix only.
- **fix(bots): bot and group chats read chronologically again.** Threads were
  rendered newest-first, so a question appeared below its own answer and new
  turns jumped to the top. Both the bot chat and group room now render oldest →
  newest, keep the thinking indicator at the bottom, and autoscroll the newest
  message (including streamed text) into view. no doc change � presentation fix.

- **fix(bots): QA hardening pass across Bots mode, deletion, delegation and scheduling.**
  Bots are now identified by the `bot` tag (monitors tagged `bot`/`monitor`), so
  jobs and event rules no longer appear in the Bots list, `bot_list`, the `@`
  palette or the run watcher. The Schedule editor preserves event/condition
  triggers instead of downgrading them to manual, and no longer wipes unsaved
  edits on the 20s background hydrate. Deleting a bot now purges its private
  memory through both the UI route and `bot_delete`, clears its thread/face and
  removes it from rooms; group deletion purges member buckets too. Streaming bot
  and group replies update memory only and persist once at the end. Switching
  bots/rooms mid-stream remounts and aborts the old turn; retry is limited to the
  latest failed reply; delegated turns no longer duplicate the prompt; parallel
  approvals are keyed per approval id; group delegation honours the chosen model;
  duplicate mention targets are collapsed; bots duplicate their model and run
  policies. Also fixed the bot composer's global-model leak (interactive turns
  use the bot's pinned model), group mentions using the shared parser, duplicate
  names resolving to all matches, the Details avatar ignoring uploaded photos,
  denied tools/tags rendering, mode-exit navigation, the missing sidebar
  scheduler button, the finance starter pack being unreachable, and the first-run
  unread seed. Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`.

- **fix(nav): final navigation shape.** Graph Studio is its own top-level mode
  again (mode switcher + `Alt+G` + mobile) but renders the STANDARD nav list, not
  a custom Workflows panel. A fresh shell boots Terminal; a tab that chose a mode
  keeps it for that session. Tables is Agentic-only (not shown in Terminal or
  Graph mode). The collapsed sidebar does not show a mode-icon rail. This
  supersedes the earlier same-day navigation notes above. Docs:
  `docs/graph-studio.md`, `docs/tables.md`, `docs/NAVIGATION.md`.

- **fix(nav): Overview and Tables are Graph-mode pages only.** Removed them
  from the Agentic and Terminal menus; each mode now shows only its own pages
  (plus the shared ChatBot). Docs: `docs/graph-studio.md`, `docs/tables.md`,
  `docs/agentic-overview.md`, `docs/NAVIGATION.md`.

- **fix(graph): cleaner workflow gallery.** The workflow gallery header is the
  same on Overview and Graph Studio home — the redundant Home button and the
  "Agentic workspace" eyebrow are gone. Workflow cards are rebuilt as taller
  frosted cards with a status-accented icon, hover arrow, aligned metadata and a
  separated action footer; template tiles match the same language. no doc change
  — presentation only (the gallery contract is unchanged).

- **refactor(graph): one Graph-mode page — Overview.** Retired the separate
  Graph Studio nav tab (desktop sidebar, mobile bar, SDK nav manifest). Overview
  now hosts the whole workspace: gallery in place, and opening/creating a
  workflow switches that same page into the editor (back returns to the gallery).
  Old `?tab=graph-studio` links alias to Overview. Overview is pinned directly
  below ChatBot in Graph mode (desktop + mobile), regardless of saved custom
  order. Docs: `docs/graph-studio.md`, `docs/agentic-overview.md`,
  `docs/NAVIGATION.md`.

- **fix(shell): stale chunks self-heal and Graph tabs preload.** Added a
  `ChunkReloadGuard` that reloads once when a lazily-imported screen's chunk is
  missing after a rebuild (this was why an old tab could open Graph Studio to a
  blank page), and warmed the Graph Studio / Overview / Tables chunks while the
  shell is idle so mode switches are immediate. no doc change — runtime
  robustness/perf only.

- **feat(graph): header on the gallery, full-bleed editor.** The app top bar is
  visible on Overview again and is hidden only while the in-place graph editor
  is open (the workspace reports its internal view to the shell). Docs:
  `docs/graph-studio.md`.

- **style(overview): use the theme accent for gallery icons and hover.**
  Workflow-card and template icon tiles, hover borders, top hairline, arrows,
  tag tints and “Open editor” now use the live `primary` (accent) token instead
  of hard-coded sky blue, so they follow the user's theme. no doc change — style
  only.

- **fix(graph): canvas interaction is now industry-standard.** Single click
  selects a node and **double-click opens the inspector** (n8n/Figma); box select
  is **Shift+drag only** (Alt/right-drag removed); the pane uses grab/grabbing
  and crosshair cursors; and the zoom controls include a **? Canvas shortcuts**
  panel. Left-drag/Space/middle pan and wheel zoom are unchanged. Docs:
  `docs/graph-studio.md`.

- **fix(graph): n8n-style canvas gestures.** Box selection now works with
  **Shift+drag** (React Flow's n8n default) in addition to Alt+drag and
  right-drag; left-drag on the pane pans, wheel zooms, Space/middle-drag pans,
  Ctrl/Cmd+click multi-selects. Docs: `docs/graph-studio.md`.

- **feat(graph,nav): right-side node library, Workflows mode, glass node
  material.** The add-node search now opens as a 400px right-side `glass-drawer`
  (portaled, search + categories + keyboard nav, closes after insertion). The
  mode formerly labelled Graph Studio is now **Workflows**; the editor header
  uses an **Overview** breadcrumb back to the gallery and the sidebar footer
  shows the active mode instead of always “Terminal”. Node cards use a new
  `.node-card` layered glass material (true page blur is impossible inside React
  Flow’s transformed viewport). Docs: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.

- **feat(graph): center-stage Start workflow button.** The editor now shows a
  prominent run control centered at the bottom of the canvas. It executes the
  saved version, and turns into **Save & run** when the graph has unsaved edits;
  it is disabled with a reason when unsaved/invalid. Docs: `docs/graph-studio.md`.

- **fix(graph): right-drag marquee + cleaner node cards.** Right-button drag on
  the pane now draws a marquee and selects overlapping nodes (a plain right-click
  still opens the pane context menu; Alt+drag remains). Removed the colored
  accent bar along the left edge of every node. Docs: `docs/graph-studio.md`.

- **feat(graph): port-row node cards.** Nodes are now 244px cards with an
  identity header (icon + name + category) and one always-visible 26px row per
  typed port, so multi-output nodes (If/else: Value / True / False / Result) grow
  in height with labels beside their handles instead of hiding them behind a
  hover overlay. Add-next stays a hover `+` clear of the port; wire drag still
  works. no doc change — node presentation only.

- **fix(graph): output handles are wireable again.** The invisible "add next
  step" `+` button sat on top of each output port and swallowed the pointer-down,
  so dragging a wire never started a connection. It is moved clear of the port
  (and still appears on hover). no doc change — interaction bug fix.

- **fix(theme): Custom theme tile is selectable again.** The unsaved/saved
  "Custom theme" tile is now a real button: it applies an unsaved draft, or
  returns to the saved custom theme after browsing a preset (instead of looking
  dead / committing the preset under the custom label). no doc change — UI fix.

- **feat(graph): editor affordances + roomier nodes.** Replaced the native
  execution-mode `<select>` with the shared glass dropdown (fixes the broken
  dark popup), surfaced **Tidy up layout** as a canvas-control button, added a
  persistent **Add node** button on the canvas's right edge, and widened node
  cards (214px) with an icon tile, tighter-but-roomier text hierarchy and larger
  hover actions. Docs: `docs/graph-studio.md`.

- **feat(graph): full-bleed Graph mode + redesigned editor header.** Graph mode
  (Overview and its in-place editor) hides the app top bar. The editor header is
  now 48px with a content-sized workflow name (no more stretched input), a dirty
  dot, version chip, labeled execution-mode pill, grouped undo/redo and
  issues/save/test actions. Docs: `docs/graph-studio.md`.

- **fix(graph): pan by default, Alt+drag to box-select.** Canvas drag now pans
  (the cursor stays in move mode); holding `Alt` while dragging draws the
  marquee selection box. Node click-vs-drag inspector behaviour is unchanged.
  Docs: `docs/graph-studio.md`.

- **fix(graph): card hit targets and canvas selection.** A workflow card is now
  one full-card click target (the footer/whitespace included; delete stays
  separate), with a pointer cursor. The canvas draws a marquee selection when
  dragging empty space (middle-mouse/Space pans). Clicking a node opens the
  inspector; dragging it no longer does. React Flow now owns selection during
  pointer interaction and the store mirror only applies programmatic changes,
  fixing a `Maximum update depth` crash during marquee. Docs:
  `docs/graph-studio.md`.

## 2026-10-25
- **feat(models): OpenCode Zen provider in AI / LLM.** Added `opencode` to the
  provider presets (Settings → AI/LLM and the composer), the Python catalog
  (`PROVIDER_CATALOG`/`PROVIDER_MODELS`, default `glm-5.3`), the key vault
  (`OPENCODE_API_KEY`, tested against `https://opencode.ai/inference/v1/models`)
  and `CATALOG_ENV_VARS`. Chat uses OpenCode's OpenAI-compatible endpoint
  (`https://opencode.ai/inference/openai/v1`); because the catalog is published
  one level up, `OpenCodeAdapter` rewrites discovery to
  `https://opencode.ai/inference/v1/models` (verified live, 85 models). Tests:
  `test_models.py`, `test_model_runtime.py` (URL rewrite + discovery wiring).
  Docs: `docs/ARCHITECTURE.md`.
- **feat(chat): shareable apps and a live preview while they stream.**
  The interactive toolbar now has **Share**, which copies
  `/app-view#<base64>` (the `/figure` encoding) and opens a standalone,
  `noindex` viewer that renders the block in the same sandbox with no server
  storage. A still-streaming ```` ```html ````/```` ```svg ````/```` ```eclipse-app ````
  fence renders a debounced (450 ms) sandboxed "Live preview · building" of the
  partial document; the settled block replaces it. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): resize, source/copy, off-screen pause and a real dialog.**
  The interactive card gains a drag/keyboard resize handle (double-click resets;
  the height is remembered per app in localStorage), a source view with Copy, and
  a focus-trapped full page that locks page scroll, restores scroll and focus on
  exit, and closes on Escape. `Eclipse.visible` / `Eclipse.onVisibility(fn)` report
  off-screen or hidden-tab state; while hidden the shell pauses CSS animations and
  holds `requestAnimationFrame` callbacks so an off-screen app stops burning CPU.
  Docs: `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps get host context, a skeleton, and a fix action.**
  `Eclipse.context = { theme, reducedMotion, locale }` is baked at mount and
  pushed live (the block observes the host `dark` class and the reduced-motion
  media query), so an app can match Eclipse's scheme instead of the OS. The card
  shows a skeleton until the app signals `eclipse:ready`, then fades the frame
  in. The "App error" banner now offers **Ask Eclipse to fix**, which re-enters
  the agent with the error and the app title. Docs:
  `docs/interactive-response-engine.md`.
- **feat(models): the picker shows newly released models first.** Model lists
  were static/catalog-ordered, discovery was manual and its snapshot merged
  forever, so a provider's new models stayed buried while decomissioned ids
  lingered. Probes now sort by provider `created` (OpenAI family, Anthropic);
  `src/lib/agent/model-recency.ts` ranks provider timestamp → version within a
  family → `-latest`, preserving incoming order otherwise; both catalog routes
  prefer the freshest `served` set and sort newest-first; `compactModels` keeps
  the newest 40 on truncation; the Settings picker auto-re-probes after a 6h
  throttle; the discovered snapshot now REPLACES each provider's set per probe;
  and `PROVIDER_MODELS` is refreshed. Tests: `src/lib/agent/model-recency.test.ts`,
  `enabled-models.test.ts`, Python `test_models.py`/`test_model_runtime*.py`.
  Docs: `docs/ARCHITECTURE.md` (model picker section).
- **ui(chat): a better interactive surface — scrollbar, auto-fit, error banner.**
  The sandbox document now has a thin scrollbar derived from the app's own
  `currentColor` (with a neutral fallback), transparent track and contained
  scroll chaining. The shell reports its content height through a
  `ResizeObserver`, so the card fits the app instead of showing a cramped inner
  scroll (clamped 240–900). Uncaught errors and unhandled rejections post
  `eclipse:error` to the host and appear as an "App error" banner. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps own their palette and get a full-page view.**
  The document shell now sets only structural defaults (box-sizing, margin, font,
  transparent background) — no forced text colour or `color-scheme` — so the model
  can choose any palette from the user's context. The interactive card is full
  width and its toolbar adds **Download** (the composed HTML) and **Full page**
  (a viewport-filling overlay, Escape/Exit to close; Reload stays available).
  Docs: `docs/interactive-response-engine.md`.
- **fix(advisory): the fiduciary gate reads prose, not code.** A model-authored
  app is full of directive words (`add`, `trim`, `exit`, `reduce`), CSS
  percentages and SHOUTING identifiers (`BARS`, `VOL`, `THR`, `HOVER`, `PIN`,
  `BASE`, `JSON`), so the gate invented "recommendations" for internal tokens and
  appended a nonsensical Advisory note. `claims.extract_claims` now strips fenced
  blocks and inline code before extracting sentences (the gate is a prose check),
  with a few format/tech tokens added to the symbol stop-list. Prose advice next
  to code is still disclosed. Tests: `python/tests/test_advisory_gate.py`.
  no doc change — bug fix.
- **feat(chat): a fenced app can request the dataset bridge.**
  A leading `<!--eclipse-dataset {"symbol":"AAPL","range":"6mo"}-->` comment in
  an ```html/```eclipse-app fence is parsed into the block's `dataset` and
  stripped before render, so a fence-rendered app gets the same host-injected
  series as the `interactive` block. The runtime also exposes `Eclipse.bars()`
  for the bars array directly. Docs: `docs/interactive-response-engine.md`.
- **ui(chat): parallel agents use the ChatBot nav glyph and sit with the activity.**
  Replaced the generated ghost "bot faces" in the fan-out card and its detail
  dialog with the same `Bot` icon the ChatBot nav item uses — a delegated part is
  one Eclipse agent working in parallel, not a distinct bot. Moved the fan-out
  card below `ActivityFeed` so it reads as runtime detail with the activity rows
  instead of a card above the answer.
  no doc change — presentation only.
- **fix(chat): an app-build request stays in chat instead of the code workspace.**
  The classifier recognized the block vocabulary ("return it as one interactive
  block") but not the same deliverable phrased as code: "one self-contained HTML
  document … return it as a single html code fence" was still `code_change`, so
  the code agent edited the repository (repo map, diff, "put this change into my
  project") instead of answering. `_INLINE_APP_RE` now recognizes
  self-contained/single-file HTML, SVG, mini-app and html/svg code-fence
  deliverables as inline content (before the directive+software-object rule),
  with a guard (renderer/component/codebase/desktop/install/deploy) that keeps a
  real source change on the code profile. Tests:
  `python/tests/test_code_request_intent.py`.
  no doc change — classifier bug fix; ADR-052 already documents the block.
- **perf(chat): a code-classified turn no longer stalls for minutes before its
  first model call.** A live "build me an interactive Candle Lab" turn recorded
  only `run.created` → `response.plan` and then sat silent; on the same repo the
  code-context seed (`CodeContextEngine.select`) measured **94 s**, synchronously
  on the runtime's event loop — which also froze every other API route. Three
  fixes: (1) `find_related_tests` resolved the reference set per TEST FILE
  instead of per NAME, re-running the same SQL query ~32 500 times — now once per
  name (94 s → ~2 s); (2) `call_edges(caller_name|callee_name)` indexes added so
  the `col=? OR name=?` call-path reads stop full-scanning; (3) the chat code
  classifier now treats "return it as one interactive block" as a `data_task`
  content deliverable rather than `code_change` (the word "file" in "single-file"
  used to trigger the code profile, ADR-H117 amendment). Also stopped
  `EmbeddingService.configure()` from re-arming a tripped provider circuit on
  every search (a 30 s cooldown), which was firing thousands of doomed
  `/v1/embeddings` 404s against Ollama. Tests:
  `test_intel.py` (one reference query per name), `test_search_embeddings.py`
  (circuit survives re-configure), `test_code_request_intent.py`
  (response-block vs renderer change). Docs updated:
  `docs/harness/decisions.md` (ADR-H117 amendment).
- **fix(chat): a pre-model step can no longer freeze a turn (invariant, not a
  one-off).** The stall above happened because the repo-map/context seed ran
  synchronously on the event loop with only COUNT bounds. `CodeContextEngine.select`
  and `build_repo_map` now also take a wall-clock deadline (default 5 s,
  `BLACK_ECLIPSE_CODE_CONTEXT_BUDGET_S`) and return partial results with
  `truncated: true`; the map gets half the budget and the seed the rest
  (`graph_context._repo_map_context` emits `elapsedMs`/`truncated`);
  `find_related_tests` accepts the deadline. Opening a large workspace index
  (seconds; 682 MB here) moved out of the run: `CodeIntelRuntime.warm` opens it
  at boot on a worker thread (`boot.py::_warm_code_index`;
  `BLACK_ECLIPSE_CODE_INTEL_WARM=0` disables), while the scan stays lazy
  (`start_watch(initial_index=False)`, `manager_for` still kicks the first
  incremental index). Tests: `test_intel.py` (budget cuts a slow index off),
  `test_repo_map.py` (deadline truncates the walk). Docs updated:
  `docs/harness/code-intelligence.md` (the budget invariant),
  `docs/harness/decisions.md` (ADR-H287 amendment), `docs/NAVIGATION.md`.
- **feat(chat): Eclipse can build and run interactive mini-apps in the conversation.**
  Added the `interactive` response block: the model authors self-contained
  HTML/CSS/JS/SVG (a price knob, a VWAP explorer, a doji figure) and it renders
  inline in a sandboxed iframe. The document is composed by
  `src/lib/interactive/document.ts` with an immutable CSP
  (`default-src 'none'; connect-src 'none'; ...`) plus a tiny
  `Eclipse.data()/onData()/resize()` runtime; the frame is
  `sandbox="allow-scripts"` with no `allow-same-origin`, so it has no access to
  the app DOM, cookies or network. Widgets that need market data declare a
  `dataset`; the HOST fetches the existing read-only `/api/price-history` route,
  normalizes up to 5000 bars with source/as-of/freshness and injects the snapshot
  over postMessage (validated by frame source + per-render nonce). The model never
  types prices, and an empty series renders an explicit unavailable
  state instead of a fabricated line. Wired through the contract union, registry,
  Markdown projection, PDF export, Canvas `REPORT_BLOCKS`, prompt guidance, and
  `contract-matrix` parity. New files: `src/lib/response/blocks/interactive.ts`,
  `src/lib/interactive/{document,dataset}.ts` (+ tests),
  `src/components/response/{interactive-block,interactive-frame}.tsx`.
  A settled ```` ```html ```` / ```` ```svg ```` / ```` ```eclipse-app ```` fence
  renders through the same sandbox too, so a model that answers with UI code
  still produces a live app; the composer preserves a full document's styles and
  scripts but strips any model-supplied CSP meta.
  Decision: ADR-052. docs updated: `docs/interactive-response-engine.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`.
- **ui(layout): slim the app header.** Top bar and sidebar brand row now use a
  single `h-12` (48px) at all breakpoints instead of `h-14 md:h-16` (56/64px),
  reclaiming vertical space while keeping the 40px inner controls comfortable.
  no doc change — style-only change, no contract or architecture impact.
- **feat(chat): Eclipse can ask ONE clarifying question instead of guessing.**
  Added a read-only `clarify` tool (`python/harness/clarify_tools.py`) that takes
  a question, optional context, 2–4 options and a recommended default, creates a
  `clarification` row in the existing `McpApproval` store (additive `answer`
  column), emits `clarification.requested`, and pauses on the SAME
  `wait_for_decision` gate approvals use. The operator picks an option, types a
  free-text answer, or chooses "Let Eclipse decide"; the answer returns as the
  tool result so the run resumes in place. An answer is explicitly NOT an
  authorization (`answer_clarification` refuses non-clarification rows). Without
  an interactive client the tool never blocks or fabricates: it returns
  `answered: false` so the model must state an assumption. Wired through
  `routers/mcp.py` (`POST /mcp/approvals/{id}/answer`), the Next proxy, the event
  parser/hook, a new `clarification-card.tsx` in both chat surfaces, prompt
  guidance, and a watchdog exemption. Tests: `python/tests/test_clarify.py`,
  `src/lib/agent/events.test.ts`. Decision: ADR-H328.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`,
  `docs/NAVIGATION.md`.

- **fix(delegation): make the budget, aggregation modes and handle checks real.**
  The fan-out budget was decorative: `token_budget` was only a minimum check and
  `consumedTokens` was always 0. Each part's REAL `totalTokens` now flows through
  `ChildOutcome.tokens` into `BudgetReport.consumedTokens`, and a part is refused
  before it starts once the remaining room drops below `MIN_TOKENS_PER_CHILD`.
  Added an overall `DEFAULT_TOTAL_TIMEOUT_S` deadline that stops running parts and
  gives every outcome a terminal status. `aggregate` now honors the request's
  `list`/`compare`/`merge_claims` mode (previously all rendered as a list). The
  `delegate` tool carries the parent's `workflowId` onto the fan-out, and handle
  verification is fail-closed: an `artifact_digest` is confirmed only when the
  Artifact Center holds it (never for being non-empty). The tool schema no longer
  calls working `agent_id`/`tool_subset` fields "Reserved", and the prompt states
  when delegation is worth its cost. Tests: `test_delegation.py`,
  `test_delegation_tool.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(chat): see parallel agents working, like a fan-out card.** A delegated
  child runs on its own run id, so its events never reached the parent stream.
  New `python/harness/delegation_progress.py` (`ChildProgressBridge`) bridges the
  child's bus stream into ONE throttled, content-free `delegation.progress`
  snapshot on the parent emitter (real `step`/`maxSteps`, real tokens, real price
  or `null` when unpriced, latest activity). `delegation.started` now names the
  parts (`agents[]`), and the terminal/aggregated events carry real tokens.
  The chat renders `src/components/chat/parallel-agents-panel.tsx` (bot icon,
  agent + sub-question, live activity, progress bar, cost per row; header with
  "N agents working · X of N done · total") fed by a pure
  `src/lib/agent/delegation-reducer.ts`. Percent is `step / maxSteps` and an
  unpriced model shows `—`, never `$0.00`. Tests:
  `python/tests/test_delegation_progress.py`,
  `src/lib/agent/delegation-reducer.test.ts`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`, `docs/chat-ui-audit.md` (R4 resolved).

- **feat(delegation): `best_of` — try the same task several ways, pick the
  strongest verified result.** `DelegationRequest.strategy` now accepts
  `best_of`; the `delegate` tool takes `goal` + `count` (2–4, optional
  `agent_ids`) instead of `children`, and refuses mixing the two. Selection is
  deterministic and evidence-based (`select_best`): only completed attempts
  qualify, confirmed claims/handles score positively, unconfirmed claims
  negatively, then non-empty output and fewer tokens break ties. Only the
  winner's prose/proven claims are repeated (`aggregate_best_of`); the rest are
  named as not repeated, and no attempt finishing yields `winner=None` rather
  than a fabricated best. `delegation.aggregated` carries `strategy`/`winner`;
  the chat header renders `Best of N` with a `Best` chip on the winning row.
  Tests: `python/tests/test_delegation_best_of.py`, `delegation-reducer.test.ts`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt model for `best_of`.** An attempt may name a
  `model` (`DelegationChild.model`; tool `models[]`), and the child runs with
  that model id copied onto the parent's `ModelSettings`. The **provider and its
  credential never change** — the Python service holds only this run's key, so a
  cross-provider attempt is deliberately not offered (it would have to invent a
  credential). The progress snapshot and the chat row show the model name.
  Tests: `test_delegation_best_of.py`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt temperature for `best_of`.** An attempt may
  carry `temperature` (`DelegationChild.temperature`; tool `temperatures[]`),
  applied by copying it onto the child's `ModelSettings`. This makes N attempts
  real samples instead of near-duplicates. It is a sampling hint only: a
  provider that ignores temperature is unaffected, and nothing is fabricated to
  compensate. Tests: `test_delegation_best_of.py`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(graph): enforce the TypeScript/Python node contract and add Set variables.**
  Added `src/lib/graph-studio/manifest.ts` + checked-in
  `registry.manifest.json`, generated by `npm run graph:manifest`. The new
  Python suite `test_graph_registry_parity.py` compares the runtime registry to
  the manifest node for node (ports, config field names, capabilities, side
  effects, modes, terminal), so an editor-only or runtime-only node now fails
  CI. Added the first new core node, `data.set_variables`, to BOTH registries:
  it merges configured named values over an optional input object (configured
  keys win). Also added the `fast`/`slow`/`signal` config fields the runtime
  already accepted to the TS `finance.indicator` contract so the editor can
  configure them. Tests: `manifest.test.ts`,
  `test_graph_registry_parity.py`; targeted graph suites 53 TS + 75 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): run and version history in Graph Studio.** Added a History tab
  to the workspace right rail. It lists a saved workflow's runs
  (`/api/workflows/[id]/runs`) with status/duration/error, and its immutable
  versions (`/api/workflows/[id]/versions`). Opening a run fetches the full
  record before drawing its node statuses on the canvas; opening a version loads
  it into the editor, with an unsaved-changes confirm, and saving still appends
  a new version. Formatting is deterministic UTC (`history-model.ts`, tested).
  Tests: `history-model.test.ts`, `execution-client.test.ts`,
  `persistence-client.test.ts`; targeted graph suite 11 files / 59 tests.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): bounded local datasets + a `local_write` effect class.**
  Added `data.dataset.save` / `data.dataset.load` in both registries and the
  Python runtime. A payload is JSON-encoded into `HarnessGraphDataset` on the
  runtime's own `agent-memory.db` and referenced by a small `gds:` ref; the
  store caps a payload at 8 MB, the table at 200 datasets, and supports a TTL
  (expired refs are purged and fail explicitly). No market data is fabricated
  and JDDS is untouched. Added `local_write` as a side-effect class: a test run
  may perform local scratch writes, while external write/network/trading stay
  denied; `dataset.read`/`dataset.write` join the test-run capability set.
  Tests: `test_graph_datasets.py` (roundtrip, expiry, size/serialization limits,
  end-to-end execution, capability denial), registry parity + manifest. Targeted
  graph suites 60 TS + 81 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): pinned subworkflows with input delivery and bounded recursion.**
  Added `flow.subworkflow` (both registries + Python runtime). A node runs a
  pinned `workflowId@version` as a nested run; the parent input becomes the
  child's run input and the child's terminal value becomes the node output
  (keyed by terminal id when there are several). The Next front door resolves
  the referenced IRs from JDDS (`subworkflow-bundle.ts`, with cycle/depth/
  missing-workflow refusal) and sends them with the run, so Python never reads
  JDDS. The runtime compiles every child with the SAME grants (authority can
  only narrow), enforces a depth limit of 5, and refuses cycles again. Also added
  `GraphRun.output` terminal capture and an output readout in the Run panel.
  Tests: `test_graph_subworkflows.py`, `subworkflow-bundle.test.ts`; targeted
  graph suites 65 TS + 87 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): durable execution on the Fabric + resumable checkpoints.**
  Graph runs now dispatch as `graph` DURABLE jobs on the existing Execution
  Fabric (new queue/worker/policy; no second queue). Added normalized
  `HarnessGraphNodeRun`/`HarnessGraphEvent` tables, a bounded 2 MB per-node
  output checkpoint, and `GraphRunStore.load_resume`. `GraphExecutor` seeds
  completed nodes/outputs/fired-control/terminal values and skips them, so a
  Fabric-requeued run resumes instead of restarting. A node failure stays a
  succeeded Fabric job (the run row is authoritative); worker/process crashes
  are recovered by the Fabric lease and resumed. Added `queued → running`
  status, terminal output persistence, Fabric cancellation (queued or running),
  and a legacy in-process fallback when the Fabric is disabled. Tests:
  `test_graph_durable.py` (normalized rows, resume skips a completed node,
  durable dispatch, worker bridge, cancel, orphan reconcile, real Fabric
  manager + worker). Targeted graph suites 65 TS + 94 Python. docs updated: `docs/graph-studio.md`,
  `docs/harness/execution-fabric.md`, `docs/NAVIGATION.md`.
- **feat(graph): live SSE run updates.** Added
  `GET /graphs/runs/{id}/stream` (Python) and
  `/api/graph-runs/[runId]/stream` (Next proxy). The stream replays the
  persisted `HarnessGraphEvent` log from `Last-Event-ID`, tails new events every
  250 ms, emits keep-alives, and ends with `stream.end` at a terminal run. The
  Graph Studio Run tab now consumes SSE: node statuses update in place and the
  full run record is fetched once at terminal (authoritative outputs/durations/
  errors). A disconnected stream falls back to the existing bounded polling.
  Tests: `test_run_event_stream_replays_and_ends` + client event-mapping tests.
  Targeted graph suites 67 TS + 95 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): gateway-backed quotes/history + tabular transform pack.**
  Added `finance.quote` and `finance.history` in both registries; both call the
  EXISTING `MarketDataGateway` (server bridge bound at boot) and return
  provenance, with explicit `MarketError` failures. History emits the standard
  OHLCV payload so it feeds indicators. Added `transform.select`,
  `transform.sort_limit`, `logic.aggregate` (sum/avg/min/max/count + groupBy),
  `logic.deduplicate` and `transform.join` (inner/left) over arrays of objects
  with dotted field paths and a 100 000-row bound. The node manifest is now 35
  types. Tests: `test_graph_tables.py` (8 cases incl. fake gateway/error paths)
  + registry parity. Targeted graph suites 67 TS + 103 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): quant backtest node over the existing engine.**
  Added `quant.backtest` in both registries. It adapts the graph OHLCV payload
  to `BarSeries`/`MarketDataset` and calls `run_backtest` in
  `harness/quant/engine.py` — no backtest math in the graph runtime. Supports
  the documented `ema_cross`/`rsi_reversion` presets and a full `StrategySpec`
  JSON; the input symbol is authoritative; `randomSeed` keeps runs deterministic
  and `maxBars` bounds work. Returns the result, metrics and trades; equity
  curves are optional (`includeSeries`). The manifest is now 36 types. Tests:
  `test_graph_quant_nodes.py` (preset determinism, RSI preset, curves, custom
  StrategySpec, explicit failures) + registry parity. Targeted graph suites
  67 TS + 108 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): walk-forward validation node.** Added `quant.walkforward` in
  both registries. It adapts the OHLCV payload and calls
  `harness/quant/walkforward.py`, optimizing only on each training window and
  reporting in-sample, out-of-sample and combined metrics plus IS/OOS
  divergence. Preset-derived default parameter spaces are provided; custom
  strategies supply `paramSpaceJson`. Insufficient history is an honest
  `INSUFFICIENT_HISTORY` result. The manifest is now 37 types. Tests:
  `test_graph_quant_nodes.py` (walk-forward windows + insufficient history) +
  registry parity. Targeted graph suites 67 TS + 110 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): local research & evidence nodes.** Added `research.evidence`,
  `research.citations`, `research.conflicts`, `research.completeness` and
  `research.report` in both registries. They read the EXISTING web-research
  `EvidenceStore` (no web request, no model call): evidence with a text filter,
  claims/citations, conflicts, a coverage summary, and a deterministic Markdown
  report. `research.read` is granted to test runs because it is a local read.
  The manifest is now 42 types. Tests: `test_graph_research_nodes.py`
  (filter, citations/claims, conflicts, completeness, deterministic report,
  missing id) + registry parity. Targeted graph suites 67 TS + 115 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): operator-run envelope + a real HTTP node.** The front door now
  derives a run's grants from the persisted IR and the node registry
  (`run-authorization.ts`): test run by default; an operator run grants exactly
  the declared capabilities, enables network only on explicit confirmation, and
  refuses trading and external write nodes. `integration.http` gained a real
  executor: SSRF-checked, loopback refused, 1 MB response cap, 60 s ceiling,
  JSON body support, no custom headers/credentials yet. The UI shows an
  `Operator run` button only when the graph needs network and asks for
  confirmation naming the network nodes. Tests: `run-authorization.test.ts` and
  `test_graph_http_operator.py` (envelope denial/grant, GET/POST, blocked and
  loopback URLs, size cap). Targeted graph suites 71 TS + 120 Python. docs
  updated: `docs/graph-studio.md`, `docs/harness/security.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): the research agent node runs on the existing agent plane.**
  `agent.research` now has an executor: it resolves a named agent preset, caps
  the turn at `maxSteps`, calls `AgenticService.run`, and returns a structured
  `finding` plus the run's research evidence. It is gated by the operator-run
  network envelope. The front door resolves model credentials from the vault
  and sends them in memory; `GraphService` excludes them from the durable
  Fabric job payload, so a restart before the node fails honestly instead of
  persisting a key. Tests: `test_graph_agent_node.py` (structured finding,
  objective required, bound-runtime required, envelope denial/grant) + registry
  parity. Targeted graph suites 71 TS + 124 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt approaches for `best_of`.** A best-of attempt
  may carry a short `approach` (tool `approaches[]`, e.g. "retry with backoff"
  or "mock the API"). It is prepended to that child's prompt as guidance and
  becomes the row label in the chat card (the full sub-question stays in the
  tooltip), matching the "each agent tries a different angle" presentation. It
  is guidance, never a claimed result. Starts/progress carry `approach`, so the
  label is live from the first frame. Tests: `test_delegation_best_of.py`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt context for `best_of`.** Attempts may carry
  their own bounded `contexts[]` (tool) / `DelegationChild.context`, so tries can
  work from different background evidence. Context is prompt input only — it is
  never placed in the progress snapshot or the card, so background material
  cannot leak into the transcript. Tests: `test_delegation_best_of.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(delegation): the fan-out survives a reload, and the card is tested.** The
  persisted `HarnessRun.delegation` blob now carries each row's bounded
  `goal`/`approach`/`model`/`tokens` (`ChildOutcome` gained those display
  fields), `_run_row` returns it old-row-safe, and `/runs/{id}/explain` includes
  a bounded, redacted `delegation` view (`_bounded_delegation`) without
  re-rendering the child's prose or claims. Added a server-render test for
  `src/components/chat/parallel-agents-panel.tsx` (best-of header + winner chip +
  real cost + `—` for an unpriced part + step/ceiling progress; split header;
  empty case). Tests: `test_run_observability.py`,
  `parallel-agents-panel.test.tsx`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`.

- **chore(delegation): stop advertising dead DAG tools, propagate stop, make
  concurrency configurable.** (1) `install_orchestration_layer` no longer
  registers the 11 model-facing orchestration tools — no built-in allowlist names
  them, so they only appeared as unreachable tools; the engine, operator routes
  and direct-registration tests are unchanged (`parallel-orchestration.md`
  updated). (2) Each delegated part now gets its own `cancel_event` passed to
  `execute_run` and set on timeout/cancel/failure, so cooperating tools stop.
  (3) `MAX_IN_FLIGHT` is operator-configurable via
  `HARNESS_DELEGATION_MAX_IN_FLIGHT` (clamped 1–8) because memory is the real
  constraint. Tests: `test_delegation.py`, `test_delegation_tool.py`,
  `test_orchestration_tools.py`. docs updated:
  `docs/harness/parallel-orchestration.md`,
  `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(team): opt-in per-member fan-out.** `TeamPolicy.memberFanout` (default
  off) adds the `delegate` tool to each member's declared surface so a Bot can
  run a split fan-out or `best_of` inside its own subtask. It adds only the tool
  NAME — delegation caps, narrowing and permissions still apply, and a member
  with no declared surface already inherits it. Tests:
  `test_team_service.py`. docs updated: `docs/harness/bot-team-orchestration.md`.

- **docs(roadmap): phases 15, 18 and 20 are Done in the code; the index was stale.**
  Re-read the modules and their tests against the phase files and corrected the
  status instead of re-implementing finished work: Phase 15 (promotion + rollback,
  document extractors, artifact serving, inline `ArtifactView`), Phase 18 (figure
  payload + 10 recipes + inline renderer, 2026-10-18) and Phase 20 (every
  capability class graded; `test_capability_classes` asserts no unmeasured row).
  Evidence run: `test_code_promotion*`, `test_analysis_recipes`,
  `test_artifacts_*`, `test_artifact_verification`, `test_capability_classes`,
  `artifact-view.test.tsx`, `analysis-types.test.ts` — all pass.
  docs updated: `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-{15,18,20}-*.md` (status + last-verified).

- **feat(eval): a measured adoption gate for the `delegate` fan-out.** New
  `python/harness/evaluation/delegate_benchmark.py` runs both variants on frozen
  tasks through the REAL `execute_run` graph and the REAL `delegate` handler:
  N sequential steps vs one fan-out with N parts. The model is a deterministic
  SIMULATOR with a fixed per-call latency, so the result answers whether the
  parts overlap — the report says `simulated: true` and never calls a simulated
  millisecond provider latency. Both variants cover every fact by construction;
  a coverage miss is `unmeasured` and vetoes adoption, and adoption needs equal
  coverage plus a ≥15% wall-clock gain (`ADOPTION_LATENCY_MARGIN`, ADR-H213).
  First frozen run: three parts save ~29%, two parts do not — the gate is a
  measurement, not a default. Tests: `test_delegation_benchmark.py`.
  docs updated: `docs/harness/agent-evaluation.md` (§13.2), `docs/NAVIGATION.md`.

- **fix(delegation): production polish for the fan-out surface.** A stopped part
  now finishes its live snapshot as `cancelled` (not `failed`) while still
  setting the child's stop signal; a completed but unpriced part makes the card's
  total unknown instead of silently understating it (a refused part does not);
  the card header exposes an `aria-live` status label for screen readers; and the
  new benchmark test file has consistent line endings. Tests:
  `delegation-reducer.test.ts`, `parallel-agents-panel.test.tsx`,
  `test_delegation_benchmark.py`. Full checks: `tsc` clean, 398 vitest files /
  3917 tests, 83 targeted Python tests.

- **feat(graph): live web-research nodes (Phase 7).** Added
  `research.web_search`, `research.web_fetch` and `research.claim_verify` to
  both registries. Search and fetch reuse the existing web-research engine
  (`web_providers`, `web_extract`) through the SSRF-hardened bridge capabilities
  - no second egress path. Results are pointers, extracted text is untrusted,
  and a fetch with a `researchId` saves the same `Evidence` the `web_extract`
  tool saves so the local research nodes can read it. Both live nodes are
  `network` side effects (test runs refuse them; an operator run must confirm
  network). `claim_verify` is a local read over the verifier. The manifest is
  now 45 types. Tests: `test_graph_research_nodes.py` (search/domain filter,
  fetch+evidence save, unknown evidence id, compiler network denial/grant) and
  `run-authorization.test.ts` (network vs local research nodes). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): optimizer, Monte Carlo and OOS holdout nodes (Phase 6 complete).**
  Added `quant.optimize`, `quant.montecarlo` and `quant.oos` to both registries.
  They reuse the tested quant engines instead of reimplementing research math:
  the optimizer returns best/leaderboard/stability, Monte Carlo returns the
  return distribution and loss/ruin probabilities, and the OOS node makes a
  chronological split (fraction or index), backtests both sides with the same
  deterministic engine, reports IS/OOS divergence and a block-bootstrap CI for
  the OOS mean return. A materially weaker OOS objective raises
  `IS_OOS_DIVERGENCE`. The manifest is now 48 types. Tests:
  `test_graph_quant_nodes.py` (optimizer leaderboard/no-axis refusal, Monte
  Carlo distribution, OOS split/index/invalid split). docs updated:
  `docs/graph-studio.md` (Phase 6 status + next milestone), no other contract
  changed.

- **feat(graph): paper trading and safety (Phase 8).** Added
  `trading.risk_check` (pure pre-trade gate over `harness/quant/risk.py`) and
  `trading.paper_order` (PAPER-only execution adapter) to both registries. The
  front door gains an explicit `allowPaperTrading` confirmation and grants
  `allowTrading` only for a `paper`-mode graph; the Python compiler refuses LIVE
  mode outright, refuses an ungranted trading node, and still refuses every
  trading node in a test run. Paper fills use the supplied reference price with
  explicit slippage/commission and never contact a broker. The UI shows the
  operator-run confirmation for paper-trading graphs. The manifest is now 50
  types. Tests: `test_graph_trading_nodes.py` (risk cap/rejection, simulated
  fill, rejected decision, price/intent validation, test-run/LIVE/ungranted
  refusals), `run-authorization.test.ts` (paper confirmation, research-mode
  refusal, LIVE refusal). docs updated: `docs/graph-studio.md`,
  `docs/harness/security.md`.

- **feat(graph): post-run step inspector and structural version diff (Phase 9).**
  Added `src/lib/graph-studio/run-debug.ts` and a Run-panel step inspector:
  ordered steps, status/attempts, bounded inputs/outputs, per-node events and
  checkpoint availability. The runtime's node-run read now exposes
  `resumable`, so the inspector never infers a checkpoint. Added
  `src/lib/graph-studio/ir-diff.ts` plus a History > Versions `Diff` action:
  added/removed/changed nodes and edges, changed settings and name, with a
  key-order-insensitive config comparison. Tests: `run-debug.test.ts`,
  `ir-diff.test.ts`, and a `resumable` assertion in `test_graph_durable.py`.
  docs updated: `docs/graph-studio.md` (Phase 9 + next milestone).

- **feat(graph): bounded run telemetry and a Health tab (Phase 10).** Added
  `GraphRunStore.health` / `GraphService.health` and operator-gated
  `GET /graphs/health?windowHours=N`: run counts by status, success/failure
  rate, duration p50/p95, queue wait (created → started), throughput,
  failed-node codes, slowest node types and checkpoint coverage. Reads are
  capped (1 000 runs / 5 000 node rows, 1–168 h) and report `truncated`; missing
  values stay `null`. Added the Next proxy, typed `getGraphHealth` and the Graph
  Studio **Health** tab (1 h / 24 h / 7 d). Tests:
  `python/tests/test_graph_health.py` (counts/percentiles/failure codes, window,
  queue wait, bounded read). docs updated: `docs/graph-studio.md` (Phase 10
  status, telemetry contract, next milestone).

- **feat(graph): chat-to-graph authoring (Phase 7).** Added
  `python/harness/graph_runtime/planner.py`: the model receives the runtime's
  real node catalog and returns a strict JSON proposal; the planner validates
  every node type, port, edge and config against the same registry the compiler
  uses, derives capabilities, selects `paper` when a trading node is present and
  dry-runs the compiler. Only a zero-error proposal becomes a `WorkflowIR`;
  nothing is saved or executed automatically. Added operator-gated
  `POST /graphs/plan`, the Next proxy `/api/graphs/plan` (model settings resolved
  from the vault, memory only), typed `plan-client.ts`, and a "Generate from
  prompt" flow in the workflow list that saves through the normal create path.
  Tests: `python/tests/test_graph_planner.py` (catalog, valid/trading plans,
  unknown type/port/config refusal, missing model/objective) and
  `plan-client.test.ts` (parsed IR, validation errors, refusal). docs updated:
  `docs/graph-studio.md` (Phase 7 + chat-to-graph contract).

- **feat(graph): planner and delegate agent nodes (Phase 7 complete).** Added
  `agent.plan` (one bounded structured-plan model call, 1–8 steps, stable ids
  and earlier-step dependencies, never executes them) and `agent.delegate` (1–6
  tasks, each one bounded turn on the existing agent plane, explicit per-task
  failure with a `PARTIAL` summary). The plan call reuses the in-memory model
  settings and a strict schema (`agent_plan.py`); delegation reuses the bound
  agent runner, so neither adds an agent loop. The manifest is now 52 types.
  Tests: `test_graph_agent_node.py` (plan/delegate, failed part, task cap,
  bound planner) and   `test_graph_agent_plan.py` (ids, dependencies, step cap).
  docs updated: `docs/graph-studio.md` (Phase 7 complete).

- **feat(graph): health watch and headless schedule guidance.** Added
  `graph_runtime/health_watch.py`: a bounded cadence reads the health telemetry,
  persists `unmeasured`/`insufficient`/`healthy`/`degraded` in
  `GraphHealthWatchState`, and publishes `graph.health_degraded` /
  `graph.health_recovered` only on a transition. Thresholds are env-tunable
  (`HARNESS_GRAPH_HEALTH_*`; `SECONDS=0` disables). `/graphs/health` now carries
  `watch`, and the Health tab renders the verdict/reasons. Boot starts/stops the
  watcher; it never creates or changes a run. Docs also document driving
  `/api/workflow-schedules/tick` from external cron with `CRON_SECRET` for a
  headless host. Tests: `test_graph_health_watch.py` (thin data, thresholds,
  transition-only events). docs updated: `docs/graph-studio.md`.

- **feat(fabric): same-host multi-process workers.** `FabricStore.claim_job` is
  now ONE `UPDATE ... RETURNING` statement, so two processes sharing
  `agent-memory.db` can never claim the same job; claim and lease renewal now use
  the same worker id (the old `id:slot` claim meant heartbeats did not renew the
  lease). Added `HARNESS_FABRIC_WORKERS` (kinds/queues, `none` =
  producer-only) and `python -m harness.fabric.standalone` for a dedicated worker
  process that starts only the Fabric consumers. Tests: two independent
  stores/connections claim exactly once; worker filter parsing; standalone CLI.
  A multi-machine fleet remains unsupported because the store is local SQLite.
  docs updated: `docs/harness/execution-fabric.md`, `docs/graph-studio.md`.

- **feat(graph): durable paper-trading accounts.** `trading.paper_order` now
  records each fill in `GraphPaperAccount`/`GraphPaperFill` on `agent-memory.db`
  by default: cash, signed position, average cost and realized PnL persist across
  runs, so a scheduled paper graph keeps its book. The write is one
  `BEGIN IMMEDIATE` transaction, safe alongside the multi-process workers.
  `accountId`, `initialCash` and `persist` are node settings; `persist: false`
  keeps a fill stateless. This is cost-basis accounting, not mark-to-market.
  Tests: `test_graph_trading_nodes.py` (persisted buy/sell + realized PnL,
  stateless fill, missing store). docs updated: `docs/graph-studio.md`.

- **feat(graph): durable subworkflow child runs and a workflow picker.**
  `GraphExecutor` now reports a finished nested run to the service, which stores
  it as its own durable row (`<parentRunId>:<nodeId>`) with node runs and events;
  the parent node returns that child `runId`. The inspector's subworkflow node
  now selects a saved workflow from the catalog and pins its version from a
  dropdown (with a self-reference warning), instead of typing ids. Tests:
  `test_graph_subworkflows.py` (child run row + nodes + events). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): owner-scoped datasets.** `HarnessGraphDataset` gains an
  `ownerId` column (existing rows migrate to `local`). Save/load/meta carry the
  run's user id; another owner's reference is reported as NOT FOUND, so a ref
  holder cannot probe another user's datasets. `delete`/`list` accept an optional
  owner filter; the expiry purge is unchanged. Tests:
  `test_graph_datasets.py` (cross-owner load/meta/list). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): HTTP headers/credential refs, browser escalation and object-row
  loops.** `integration.http` gains `headersJson` (plain headers; transport
  headers and secrets refused) and `credentialEnvJson` (header → environment
  variable NAME resolved by the runtime only; values are never stored). Headers
  may not come from both sources. `research.web_fetch` gains `allowBrowser`:
  a thin/failed page escalates to the existing Browser Runtime and reports
  `extraction: browser`; the default remains bridge-only. `logic.map/filter/
  reduce` now accept object rows, binding each row's numeric fields by name
  (plus `value`/`index`/`acc`). The per-node checkpoint size is operator-tunable
  (`HARNESS_GRAPH_CHECKPOINT_MAX_BYTES`, 2–16 MB). Tests:
  `test_graph_http_operator.py` (plain/credential headers, ambiguity, missing
  env), `test_graph_research_nodes.py` (browser escalation),
  `test_graph_control_flow.py` (object-row loop), `test_graph_durable.py`
  (checkpoint limit bounds). docs updated: `docs/graph-studio.md`.

- **feat(graph): bounded crawl and an opt-in real-provider e2e.** Added
  `research.web_crawl`: one start URL, 1–10 same-site pages, using the existing
  SSRF-hardened fetch plus the bridge's deterministic `web_collect` link pass.
  It is not a general crawler; each page is untrusted and failures are reported
  per page (`PARTIAL`). Added `test_graph_agent_e2e.py`, skipped unless
  `HARNESS_E2E=1` and provider/model/API-key env vars are set, covering
  chat-to-graph, step planning and an agent node against a REAL provider. Tests:
  `test_graph_research_nodes.py` (same-domain bound/dedupe). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): bounded graph-health alert history.** Every watch transition
  (`degraded`/`healthy`) is appended to `GraphHealthAlert`; `/graphs/health`
  returns the newest 20 with reasons, and the Health tab lists them. Tests:
  `test_graph_health.py` (order + reasons). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): executable `video.render` behind a local-write grant.** The
  node now builds a bound recap storyboard and runs the existing
  `VideoService.run_render_job` in the graph worker (project files + Artifact
  Center entry), with honest failure when the fframes worker is absent. The
  front door adds a whitelisted `allowLocalWrite` confirmation (only
  `video.render`; any other write node is still refused) and the compiler gains
  `RunGrants.allow_write`. Test runs still refuse it. Tests:
  `test_graph_video_nodes.py` (executor, symbols, compile grants) and
  `run-authorization.test.ts` (local-render confirmation). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): durable `logic.wait` via a deferred Fabric job.** A durable
  graph no longer blocks a worker thread on a long wait: the wait node
  checkpoints itself, the run is persisted as `queued`, the worker returns a
  `deferred` outcome and the Fabric requeues the job at the wake time (without
  consuming a retry), then resumes from the checkpoint. Waits are bounded to
  24 h; non-durable `run_sync` keeps the 30 s cap and test runs the 5 s cap.
  Tests: `test_graph_control_flow.py` (deferral), `test_graph_durable.py`
  (defer + resume), `test_fabric_workers.py` (deferred requeue). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): spill oversized checkpoints to confined files.** Above the
  DB checkpoint limit (default 2 MB, tunable to 16 MB), a node's output and
  terminal value now spill to
  `<db-dir>/graph-checkpoints/<runId>/<node>.{checkpoint,terminal}.json` with a
  path-confined `{"$file": ...}` marker, so the run stays resumable (up to a
  256 MB file cap). `load_resume` follows the marker; `delete_run` removes the
  files. Tests: `test_graph_durable.py` (spill, resume, cleanup). docs updated:
  `docs/graph-studio.md`.

- **fix(model,graph): real-provider e2e now runs.** Two defects surfaced when
  exercising a real Ollama model: `model_runtime/providers/base.py` imported a
  nonexistent `model_runtime.models` (now `harness.models`), and the planner
  rejected common model edge shapes (`from`/`to`, `sourcePort`/`targetPort`,
  `{node, port}` handles) plus a missing title. The planner now normalizes those
  aliases and defaults the workflow name. The opt-in e2e was run against the
  configured Ollama model and passed chat-to-graph, step planning and an agent
  node. Tests: `test_model_runtime.py`, `test_graph_planner.py`. docs updated:
  `docs/graph-studio.md`.

- **docs(graph): refresh the remaining-work list.** Known limitations now reflect
  the shipped planner/delegate nodes, the documented external-cron path and the
  health watch; "Next milestone" names multi-process Fabric workers as the main
  remaining item. no doc beyond `docs/graph-studio.md`; no runtime change.

- **fix(harness): code-context lookup, response-block routing and embedding
  circuit cooldown.** These pre-existing working-tree fixes landed with the
  crawl commit: `code/intel/context.py` resolves `find_references` ONCE per name
  (the old loop re-ran the same SQL per test file), `persistence/index.py` adds
  caller/callee-name indexes, `request_intent.py` routes "return it as an inline
  block" to a response deliverable (not a code-workspace edit), and
  `search/embeddings/service.py` keeps a tripped circuit open for 30 s instead of
  re-arming it on every `configure()`. Tests: `test_intel.py`,
  `test_code_request_intent.py`, `test_search_embeddings.py`. no doc change —
  internal performance/routing fixes; contracts unchanged.

- **feat(chat): the fan-out card now looks like a "best of N" panel and opens a
  live agent view.** Each part renders a deterministic **bot face** (from the
  agent id, never a vendor logo), the agent/model + its approach, the live
  activity and the runtime's `step/maxSteps` bar/percent. The card shows a short
  fan-out `title` (best_of defaults to its goal), `X of N done`, and **no cost**.
  Clicking the card opens a portaled frosted dialog
  (`parallel-agents-dialog.tsx`) with each agent's full sub-question, status,
  step counter, tokens and a `recent[]` activity timeline. A
  `tool.requested(delegate)` now paints a provisional "Agents starting" card
  until the real `delegation.started` arrives (and it is dropped if the call is
  refused). The same card is wired into the main chat, the floating dock, bot
  chats and group rooms. Tests: `parallel-agents-panel.test.tsx`,
  `delegation-reducer.test.ts`, `events.test.ts`, `test_delegation_progress.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`, `docs/NAVIGATION.md`;
  regenerated `docs/harness/tool-registry.json`.

