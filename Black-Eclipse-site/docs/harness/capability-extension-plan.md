---
title: Capability Extension Plan (author pages, widgets, tools, skills)
status: Draft
last-verified: 2026-10-19
---

# Capability Extension Plan

**Who this is for:** anyone extending Eclipse so the agent — and the user
through the agent — can **author new pages, widgets/components, tools, skills
and integrations** from natural language, and see the results live in the app.

This is the plan behind the request: *"it should be able to create new pages,
new things, new tools — like the plugin philosophy / SDK."* It is grounded in
what already exists, names the exact gaps, and sequences the work.

## What already exists (the three engines)

Eclipse already has the hard parts. The work is **connective tissue**, not new
engines.

1. **UI Engineering** — compose pages/workspaces from registered widgets.
   - Contract: `UiComponentSpec` + declarative `UiBlueprint` (wraps the existing
     `WorkspaceLayout`) — `src/lib/ui-engineering/`, `python/harness/ui/`.
   - Agent tools: `ui_*` (`ui/tools.py`) — create page, add/move/resize/config
     widget, save layout, revisions, preview, `ui_classify_request`,
     `ui_start_engineering`.
   - Surfaces: the **UI Builder** screen and `/api/ui/**` (proxied to Python).

2. **Plugin SDK** — author tools, skills, hooks, commands, workers, webhooks,
   UI panels, data/research providers, agents, workflows.
   - `python/harness/plugins/sdk.py` (decorators), `manager.py` (lifecycle),
     `manifest.py` (validation), sandbox, secrets, HTTP, OAuth, marketplace.
   - Reference plugins under `plugins/bundled/`. CLI `eclipse plugin create`.

3. **Skills + Scaffold Kits** — versioned procedures and ready-made finance
   tool shapes (`scaffold_kit`, operator-gated skill lifecycle).

The `ui_*` tools are the **Compose** half; the code/plugin path is the
**Engineer** half. `mode.py::classify_request` chooses between them.

## The gaps (why "it wasn't able to do it")

1. **The blueprint store is disconnected from the live dashboard.** The Command
   Center and fund workspaces render from client `localStorage`
   (`be_ws_dashboard_v8_*`), while `ui_*` mutates blueprints in `agent-memory.db`.
   There is no bridge, so an agent-created page/widget is invisible.
2. **The agent does not know the `ui_*` tools exist.** `ECLIPSE_AGENT` includes
   `*UI_TOOLS` in its allowlist, but `ECLIPSE_AGENT_SYSTEM_PROMPT` never mentions
   them.
3. **No page context reaches the run.** `ui_get_current_page` needs a
   `blueprintId`/`path`; the chat never supplies one.
4. **"New widget" misclassifies as Compose.** The classifier has no
   `new widget`/`new page`/`new tool` engineer signal, so a genuinely-new
   request degrades to "add an existing widget."
5. **Engineer mode is asynchronous and not surfaced.** `ui_start_engineering`
   only creates a durable Task/Plan for `code-agent`; nothing in the chat turn
   builds the component, and the result is not shown anywhere the user looks.

## Target experience

> "Make me a page called Rates Desk with a 5y/10y spread chart and a rate table,
> then build me a widget that shows real-time swap spreads."
> → Eclipse classifies (compose + engineer), creates the page with existing
> widgets immediately (visible in **Pages**), files a durable engineering task
> for the new widget, and when the code path registers it, it joins the catalog
> and can be added to the page.

One coherent loop: **classify → compose now (visible) → engineer in the
background (tracked) → register → compose again.**

## Phased plan

### Phase A — Live pages (compose actually shows up)  ← started this change
- **A new `Pages` surface** that lists blueprints and renders the selected
  blueprint through the **real** `CustomizableWorkspace` +
  `renderDashboardWidget` — so an agent-created page is a real, visible page.
- Layout edits can be written back to the blueprint (`ui_save_layout`), closing
  the local↔durable gap for pages.
- Reuses the workspace kernel, widget registry and blueprint store. No second
  layout engine, no second widget library.

### Phase B — The agent knows and is told "where"
- Add a **UI authoring section** to `ECLIPSE_AGENT_SYSTEM_PROMPT` documenting the
  `ui_*` tools and the Compose/Engineer flow (start with
  `ui_classify_request`).
- Pass the **current page context** (`blueprintId`/`path`) into the run so
  `ui_get_current_page` resolves "my widgets" to the page the user is on.
- Fix `mode.py` classifier: `new widget` / `new page` / `new tool` / a named
  component that is not in the catalog → Engineer (or Both when mixed).

### Phase C — Engineer actually produces artifacts
- Make `ui_start_engineering` dispatch (or inline-run) the code task so the
  turn yields a real component, then `ui_register_engineered_component` joins it
  to the catalog (loop already implemented; wire the trigger).
- Surface engineering-task status in the UI Builder / Pages (progress, failure).

### Phase D — One authoring studio
- Extend the UI Builder / Pages into a **Capability Studio**: pages, widgets,
  tools (plugins), skills and integrations in one navigable place, each with
  create/edit/enable/health, backed by the existing managers.
- Add an agent tool to **scaffold and install a plugin** (Engineer-gated), so
  "make me a tool that …" ends with a real, enabled `plug_*` tool.

### Phase E — Persistence unification (decide, do not fork)
- Make the Command Center/fund workspaces **blueprint-backed** (or sync their
  localStorage layouts) so agent edits to *existing* dashboards are visible too.
  This is the deepest change and is deliberately last; Phase A already proves
  the render path.

### Phase F — Python Capability Builder (started 2026-10-19)
- Detect a missing capability with `capability_request`; search static recipes,
  active generated capabilities and the live tool registry before building.
- Classify one-off vs reusable and route effectful surfaces to their existing
  approval-gated owner.
- Build a pure reusable recipe: versioned manifest, implementation, contract
  test and README under `.black-eclipse/capabilities/`.
- Verify through the existing analysis sandbox; auto-activate a passing pure
  workspace recipe and keep everything else `approval_required`/`unverified`.
- Load active generated recipes into the existing `code/recipes.py` registry so
  `analysis_run` uses them immediately; record usage and auto-disable after
  repeated failures.
- Rollback/retire are versioned; no generated code can write core harness files.
- The chat `CapabilityCard` and Settings › Capability Studio › Generated list
  consume the same records; activation/rollback/retire are operator routes, not
  agent routes (`src/components/chat/capability-card.tsx`,
  `src/components/screens/capability-studio/generated-section.tsx`,
  `src/lib/harness/capabilities-client.ts`).
- Owning doc: `docs/harness/capability-builder.md`; ADR-H225/H226.
- **Sprint 3 external lane (started 2026-10-19).** `capability_external` proposes
  a broker/API/MCP adapter through the existing MCP preset or plugin platform.
  Credentials are operator-supplied names only; the install consumes the existing
  single-use `mcp_install` approval (or the plugin platform's operator gate) and
  writes a DISABLED config. The proposal carries the recovery acquisition
  `install`/`enable` steps, and the recover handler accepts `integrationId`;
  nothing self-enables and the original task resumes from its checkpoint after
  the operator activates the adapter (ADR-H230).
- **Effectful hand-offs (2026-10-19).** `capability_build` no longer dead-ends an
  effectful kind at `approval_required`: `capabilities/handoff.py` returns one
  typed hand-off to the existing owner (`skill_create`, `scaffold_kit`,
  `ui_start_engineering`, `create_goal` for code/harness, or
  `capability_external` for plugin/MCP), carrying the arguments, acceptance,
  evidence and activation owner. The hand-off is stored on the same durable
  request; it executes nothing and needs no analysis sandbox (ADR-H231).
- **Retry + learning signal (2026-10-19).** Activation resumes the original
  parked task from its checkpoint (`capabilities/resume.py`, ADR-H232); a failed
  generated recipe records a `capability_failure` recurrence for the learning
  loop.
- **Close-out UI (2026-10-19).** The chat card offers Build / Show plan / Not now,
  the hand-off Continue, and Rebuild with RSL (prompt-only); the Studio row adds
  **Promote to global** (operator copy, ADR-H234) and **Rebuild with RSL**; the
  computed-result payload carries the recipe name. **Built-in + generated
  listing landed 2026-10-19:** `GET /capabilities/builtins` returns the static
  recipe catalogue (read-only, declared before `/{id}`) and the Studio Generated
  section renders it with a built-in badge next to the generated records.
- **Adapter authoring (2026-10-19).** `capability_adapter` +
  `capabilities/adapter.py` author a reviewable, DISABLED broker/API plugin
  draft (validated `PluginManifest`, `plugin.py`, README) under
  `.black-eclipse/adapters/`; HTTPS-only, credential names only, GET->read /
  POST->external_action, `network` permission, no install and no enable. The
  operator reviews the auth scheme, installs and enables (ADR-H238).
- **Sandbox tool RPC (2026-10-19).** The `analysis_run` sandbox can call three
  read-only `eclipse_tools` bindings (`market_snapshot`, `live_quote`,
  `price_history`) through deterministic replay: strict allowlist, no
  writes/network, no intermediate payloads in the model context, and only final
  outputs plus audit digests returned. The host resolves through the existing
  DataBridge; the generic terminal `execute_code` service is not changed
  (ADR-H235).
- Remaining phases:
  1. **Persistent kernel — landed 2026-10-19.** Session-scoped kernel reuse
     (`code/kernel.py`), eviction/idle sweep, crash/respawn and subagent
     isolation around the existing PTC sandbox; one-shot remains the fallback
     (ADR-H236, `docs/harness/python-runtime.md`).
  2. **UI intelligence — landed 2026-10-19.** Chart focus mode, series weights,
     weighted bands, the `auto` visual director, and loss-table
     alignment/formatting (ADR-H237).
  3. **Adapter + hardening — landed 2026-10-19.** Generic from-scratch
     broker/API adapter authoring, built-in + generated Studio listing,
     `docs/harness/python-runtime.md`, roadmap/bookkeeping (ADR-H238).

## Implementation status (2026-10-10; updated 2026-10-18)

- **Phase A — done.** Pages tab renders blueprints live; save/revert; `live-page.ts` bridge.
- **Phase B — done.** Prompt section; classifier signals; and the current page is
  forwarded with the run (`input.context.ui`) and rendered as a per-run prompt
  block (`graph.py::_ui_focus_block`). Client focus store:
  `src/lib/ui-engineering/ui-focus.ts` (set by Pages / UI Builder, read by
  `use-agent-run`).
- **Phase C — done.** `UiEngineering.start` now moves the plan to RUNNING so the
  existing scheduler dispatches the task (the bug: it stopped at PLANNING), and
  pins the invoking run's model on the plan metadata so the dispatched task uses
  the operator's provider.
- **Phase D — done (updated 2026-10-18).** The UI Builder shows a live
  engineering-task status card (polls `GET /ui/engineering/{planId}`). The
  **install half is real through the operator route, not an unattended agent
  tool**: the acquisition install handler performs a plugin install through the
  ONE plugin platform (`pluginPath` fact, `operator=true`, `enable=false` — never
  self-enables), a skill install through the single-use digest-bound
  `skill_install` approval, and a kit through a durable code task
  (`recovery/acquire_handlers.py`, `test_recovery_install_handlers.py`). Skills
  stay evaluation+promotion gated for enablement. The **Capability Studio**
  (`src/components/screens/capability-studio/`, AppTab `ui-builder`) is now the
  one navigable surface: pages & widgets (the embedded UI Builder), tools &
  plugins (`PluginsScreen`), skills (a read-only summary; enable stays in the
  Skills manager) and integrations (read-only data-sources + MCP summaries;
  edits stay in Settings). It is a navigation shell over the existing managers —
  no second registry, no enable path of its own; section deep link
  `?tab=ui-builder&sub=studio.<section>`; ADR-H216.
- **Phase E — done (updated 2026-10-18).** The one-way mirror had already landed
  (`onLayoutChange` → per-dashboard blueprint). The **reverse sync is now
  implemented**: `dashboard-blueprint.ts` fetches the mirrored layout
  (`fetchDashboardLayout`), tracks the revisions this client published
  (`isOwnPublish`) so it never fights the user, and the Command Center applies a
  REMOTE revision — persist into this dashboard's storage + remount — only when a
  key-order-insensitive comparison (`stableLayoutKey`) finds a real difference.
  Tests: `dashboard-blueprint.test.ts`.

Metrics: `vitest` 239 files / 2524 tests, UI `pytest` 62, `tsc` + `eslint` clean.

## Invariants this plan preserves

- **One of each:** one workspace/layout engine, one widget registry, one tool
  registry, one plugin platform, one blueprint store. Phase A–E compose them.
- **No fabricated data.** Widgets still render `UNAVAILABLE` when a source is
  absent.
- **Compose is safe by default.** The classifier errs toward Compose; only an
  explicit new-capability signal (or a missing named component) escalates.
- **Operator-gated escalation.** Engineer/code and plugin install remain
  privileged; the UI tools stay `permission="read"` (they touch only Eclipse's
  own UI config).
