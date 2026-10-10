---
title: Capability Extension Plan (author pages, widgets, tools, skills)
status: Draft
last-verified: 2026-10-10
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

## Implementation status (2026-10-10)

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
- **Phase D — started.** The UI Builder shows a live engineering-task status card
  (polls `GET /ui/engineering/{planId}`). The full Capability Studio (tools /
  plugins / skills in one place) remains.
- **Phase E — started (one-way).** `CustomizableWorkspace` gained
  `onLayoutChange`; the Command Center mirrors its board into a per-dashboard
  blueprint (`dashboard-blueprint.ts`), so Eclipse can see/edit the board the
  user actually has and it appears as a page. The reverse (agent edit → live
  dashboard) is the deliberate follow-up.

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
