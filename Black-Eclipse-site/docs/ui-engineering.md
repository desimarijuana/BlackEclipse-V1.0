---
title: UI Engineering Foundation
status: Current
last-verified: 2026-10-15
---

# UI Engineering Foundation

**Who this is for:** anyone building the AI-native UI layer — the component
catalog the agent composes from, and the durable blueprint it produces.

This is the **UI-Engineering system**: a framework-pure frontend foundation
(`src/lib/ui-engineering/`) **and** a Python runtime
(`python/harness/ui/`) that gives the agent real `ui_*` tools and backs the
blueprint store with the ONE `agent-memory.db`. The two halves share one
contract (the component spec + declarative blueprint), so a blueprint validated
by the runtime renders through the existing workspace engine unchanged.

## The two ideas

1. **Component Catalog** (`catalog.ts`) — the authoritative, queryable answer to
   "what can be composed, and how may it be configured?". It does **not** fork
   the component library: `adaptWidgetDefinition` projects the existing
   `WidgetDefinition` registry into `UiComponentSpec`s, so there is exactly one
   source of truth. The agent discovers component ids, config fields and data
   sources here instead of hallucinating them.

2. **Blueprint** (`blueprint.ts`) — the durable, versioned description of a
   page/workspace. It **wraps** the existing `WorkspaceLayout` tree (so the
   proven track-board renderer draws it) with identity, ownership, scope,
   revision and timestamps. A blueprint is pure data: no field ever executes
   code. Configuration is validated against the catalog before it can render.

## Invariants (what the code guarantees)

- **Validation is strict and truthful.** Unlike the lenient storage reader
  (`workspace/ops.ts` `normalizeLayout`, which silently drops unknown widgets),
  `validateBlueprint`/`validateLayout` *report* every problem — unknown
  component, duplicate instance/column/section id, bad column count, config
  type errors, unsupported schema version — so the agent is told the real
  reason a blueprint is rejected. Unknown config keys are warnings, not errors
  (some widgets accept dynamic config).
- **Mutations are atomic.** `applyBlueprintOps` validates the whole batch
  against the live catalog and current layout, then applies it in a single
  Immer transaction. One bad op leaves the blueprint byte-for-byte unchanged.
  Layout math is delegated to `workspace/ops.ts` — there is no second layout
  engine.
- **History is append-only; restore never rewrites.** `BlueprintHistory`
  snapshots are bounded (`maxHistory`). `restoreRevision` appends the restored
  state as a revision **above the latest**, so a restore can never collide with
  an existing revision number.
- **Concurrency is optimistic.** `save({ expectedRevision })` returns an
  explicit `RevisionConflict` when the stored revision moved past the writer's
  base, rather than silently clobbering a newer edit.
- **Corrupt persistence is never overwritten.** A blueprint store payload that
  fails to parse is ignored (empty store); the raw bytes are left in place.

## Layout

| File | Owns |
|---|---|
| `catalog.ts` | `UiComponentSpec`, `ComponentCatalog` (register/get/list/search), `adaptWidgetDefinition`, `validateComponentConfig` |
| `blueprint.ts` | `UiBlueprint`, `createBlueprint`/`touchBlueprint`, `validateLayout`, `validateBlueprint`, `BLUEPRINT_SCHEMA_VERSION` |
| `patches.ts` | `BlueprintOp` union + `applyBlueprintOps` (atomic, validated) |
| `revisions.ts` | `diffBlueprints`, `BlueprintHistory`, `restoreRevision`, `detectConflict` |
| `store.ts` | `BlueprintStore`, `createMemoryBlueprintStore`, `createLocalBlueprintStore` |
| `registry-catalog.ts` | `buildDashboardCatalog` — the bridge from the live widget registry (client-only; kept out of the pure core) |
| `index.ts` | the pure public API |

Tests: `src/lib/ui-engineering/*.test.ts` (catalog, blueprint, patches,
revisions, store) — 38 cases, `npx vitest run src/lib/ui-engineering`.

## Where this is going

The UI-Engineering system now spans the pure TS foundation, the Python runtime
(Phases 4–5), the two-mode Compose/Engineer selector (Phase 6), the UI
Engineering Agent (Phase 7) and the UI Builder workspace (Phase 8), plus the
host-registry ↔ runtime-catalog sync bridge and the live-render preview. The
Engineer path delegates execution to the existing code capability; the platform
adds no second agent loop.

## The Python runtime (Phases 4–5)

`python/harness/ui/` is the authoritative runtime. It reuses the ONE
`agent-memory.db` connection and the ONE event system; it adds no second store
and no second layout engine.

| File | Owns |
|---|---|
| `model.py` | The pydantic contracts: `UiComponentSpec`, `UiBlueprint`, the `WorkspaceLayout` tree, the operation inputs and the closed vocabularies. camelCase on the wire. |
| `catalog.py` | `UiCatalog` (register/get/list/search) seeded with the foundational component kinds (Phase 2.3), plus `validate_component_config` — identical semantics to the TS catalog. |
| `engine.py` | `validate_blueprint` (strict, truthful) + `apply_ops` (atomic Immer-equivalent batch, revision bump) + `diff_blueprints`. |
| `mode.py` | `classify_request` — the deterministic Compose/Engineer selector (Phase 6). |
| `engineering.py` | `UiEngineering` — the Engineer-mode orchestration (Phase 7): turns an Engineer/Both request into a durable Task/Plan with UI acceptance criteria, and closes the engineer→compose loop by registering the new component into the catalog. |
| `store.py` | `UiStore` on agent-memory.db: `UiBlueprint`/`UiBlueprintRevision`/`UiComponent`/`UiOperation`/`UiIdempotency`. Bounded history. |
| `service.py` | `UiService` — the ONE authority: catalog + blueprint + widget ops, `classify_request`, `engineering`, optimistic concurrency (a stale `expectedRevision` is `UI_CONFLICT`), an operation audit record, and best-effort `ui.*` events. |
| `tools.py` | The `ui_*` agent tools on the shared `ToolRegistry` (`ui_get_*` introspection, `ui_classify_request`, `ui_start_engineering`/`ui_engineering_status`/`ui_register_engineered_component`, and `ui_create_page`/`ui_add_widget`/…/`ui_restore_revision`/`ui_preview_change` mutations). |
| `bootstrap.py` | `install_ui_layer(service)` — best-effort, idempotent boot wiring + a process-wide singleton the tools fall back to. |

Operator routes (`/ui/*`, operator-gated) live in `routers/ui.py`; the Next.js
front door proxies them at `/api/ui/[[...path]]` and exposes a client-safe
`src/lib/harness/ui-client.ts`. The **UI Builder** screen
(`src/components/screens/ui-builder/ui-builder-screen.tsx`, AppTab `ui-builder`)
is the visible surface: navigator, component catalog, structural preview,
properties inspector, AI command panel, revision history and diagnostics.

**Tool naming:** the ToolRegistry rejects `.` in tool names, so the conceptual
`ui.get_application_map` is registered as `ui_get_application_map` (and so on).

**Naming a page from the agent surface:** `ui_list_blueprints` and
`ui_get_application_map` print each page's `id` + title in their text line (the
`id` is what every mutation tool requires). `BlueprintSummary` now also carries
`path` and `componentIds`, so pages that share a title are distinguishable from
the list alone, and `ui_get_current_page` can resolve `path` against the full
blueprint.

**Resolving "the current page" (`get_current_page`).** The lookup takes an
explicit `blueprintId`, else `path`, else `title`; with **none** of them it
falls back to the owner's **most recently updated** page (`list_blueprints`
orders `updatedAt DESC, id ASC`). It never silently returns row 1: the response
carries `resolution` (`explicit_id` | `path` | `title` | `title_ambiguous` |
`default_most_recent`) and, when a choice was made among several candidates,
a `candidates` list of the others. Paths are normalised (trim, leading slash,
no trailing slash, case-insensitive); an unset path (`None`) never matches. A
lookup that matches nothing raises `UI_BLUEPRINT_PATH_UNASSIGNED` when pages
exist without a path (actionable: use id/title) and `UI_BLUEPRINT_NOT_FOUND`
otherwise. HTTP: `GET /ui/current-page?blueprintId=|path=|title=`
(the path-segment form `GET /ui/blueprints/{id}/current` still exists).

**One owner policy.** `get_blueprint` fetches unscoped and applies the owner
rule in the service, so `get_current_page` / `get_layout` / `preview` share it.
A mismatch is the distinct `UI_BLUEPRINT_OWNER_MISMATCH` (HTTP 403), never
`unknown blueprint`. The read tools (`ui_get_current_page`, `ui_get_layout`,
`ui_get_blueprint`, `ui_preview_change`) pass **no** owner scope, matching the
HTTP read routes; only mutations scope to the invoking owner.

**Data-source vocabulary.** Component configs accept a free-text `source`, but
the runtime advertises the valid structured strings via
`get_capabilities()["dataSourceRegistry"]` (also `ui_get_capabilities`). The
allow-listed families are:

| family | pattern | renders |
|---|---|---|
| portfolio | `portfolio:<id>:<view>` | table (positions, holdings, …) |
| portfolio metric | `portfolio:<id>:<view>.<field>` | a single value |
| market quote | `market:quote:<SYMBOLS>` | quote table (`market:quote:AAPL.price` = a value) |
| market indices | `market:indices:<MARKET>` | index table |
| market price | `market:price:<SYMBOL>` | a time series (charts) |
| news | `news:latest` | the latest news table |
| agent | `agent:activity` | recent agent runs |
| tasks | `tasks:list` / `tasks:plans` | task / plan tables |
| artifacts | `artifacts:list` | the Artifact Center table |
| research | `research:list` | recent web-research runs |
| jdds | `jdds:search:<QUERY>` | JDDS instrument search (rows or `.<field>`) |

Portfolio views: summary, positions, holdings, transactions, pnl, performance,
risk, allocation, tax-lots — see [`portfolio-accounting.md`](portfolio-accounting.md).
Helpers: `catalog.portfolio_source(id, view)` / `parse_portfolio_source(source)`.

**Source-driven widgets (the end-to-end render path).** A composed widget
actually renders because the host registers generic primitives whose ids match
the runtime catalog:
- `data-table`, `list` (row sources), `metric-card` (a `source`/`metric` + optional `.field`);
- `line-chart`, `area-chart`, `bar-chart`, `pie-chart` (series or rows);
- `markdown`, `status-indicator`, `empty-state`, `error-state` (config-only).

They live in `src/lib/workspace/generic-widgets.tsx` / `generic-charts.tsx` /
`generic-content.tsx` and are registered in `src/lib/dashboard/registry.tsx`, so
the workspace kernel keeps them. `src/lib/workspace/data-source.ts` is the ONE
resolver: it parses an allow-listed source (never an arbitrary URL), fetches
through the existing front door (`/api/portfolio/*` via
`src/lib/portfolio/engine-read.ts`, plus `/api/quote`, `/api/indices`,
`/api/price-history`, `/api/news`, `/api/agent/activity`), caches it on a
dynamic DataHub topic, and returns rows/value/series — or an explicit
UNAVAILABLE with the reason. So an agent can add a `data-table` with
`source: "portfolio:pf_…:positions"`, a `metric-card` with
`metric: "portfolio:pf_…:summary.totalValue"`, a `line-chart` with
`source: "market:price:AAPL"`, etc. to ANY page and it renders live data.

**Catalog ↔ host parity.** `builtin_specs()` in `catalog.py` advertises EXACTLY
`RENDERABLE_COMPONENTS` — the ids the host registry defines. A dead widget is
never advertised, so the agent cannot compose something that never appears.
Enforced by `python/tests/test_ui_service.py` and
`src/lib/workspace/generic-widgets.test.ts` (the same list on both sides).

**Read-back before claiming success.** `ui_verify_page` (the `ui_verify_page`
tool / `UiService.verify_page`, HTTP `GET /ui/blueprints/{id}/verify`) reads a
blueprint back and reports, per instance, whether its component id is in the
catalog and whether any declared source string is well-formed — ALL families,
via `catalog.validate_source` (portfolio, market, news, agent, tasks, artifacts,
research, jdds). So the agent verifies a page it composed rather than asserting
success. It does not fetch the data (the front door does); it names what it can
and cannot verify.

**No silent drops.** A blueprint may reference a widget id the host registry
does not render yet (an agent-added or engineered component). The Pages surface
passes the workspace a `knownWidgetIds` set that is the host registry PLUS every
id present in the blueprint, so the kernel keeps it, and `renderDashboardWidget`
draws an explicit "Needs a renderer" card for it — never a silent disappearance.

**Engineer → Compose closure (proven).** `POST /ui/engineering/{task_id}/components`
registers an engineered component in the ONE catalog; `test_ui_api.py`
(`test_engineering_workflow`) then discovers it via `GET /ui/components`, adds it
to a page, and `GET /ui/blueprints/{id}/verify` reports it renderable — the full
loop, end to end. (A genuinely new *visual* kind still needs the code path to add
its host renderer; the catalog/verify step is what the runtime owns.)

**Page-level icon.** `UiBlueprint` (and `BlueprintSummary`) carry an `icon`
field — an icon NAME resolved by the host registry (`widgetIcon`), never code
or a URL, and deliberately distinct from the chat response-block icon enum. It
is set via `ui_create_page`/`ui_update_page` (`icon`) or `POST`/`PATCH
/ui/blueprints`, stored (with an idempotent add-column migration), and shown in
the Pages list and header. Adding it did not touch `WidgetPlacement`.

**Pages refresh (live).** `GET /api/ui/stream` is a Server-Sent-Events stream
that watches the runtime's most-recently-updated blueprint (`id:revision:updatedAt`)
and emits a `changed` event when it moves. The Pages surface listens and reloads
the open blueprint ONLY when its durable revision actually changed — a no-op
otherwise, so a user's unsaved local arrangement is never yanked (no change → no
remount). Window focus and a slow 60s poll are fallbacks if the stream drops.

**Catalog source of truth:** the runtime seeds the *foundational* kinds so it is
usable standalone; the browser then pushes the REAL dashboard widget specs
(`src/lib/ui-engineering/registry-catalog.ts` → `dashboardComponentSpecs()`) into
the runtime via `syncCoreCatalog()` (`src/lib/harness/ui-sync.ts`) → `POST
/ui/components`. The runtime upserts them by id on `agent-memory.db`, so there is
never a second hand-maintained copy of the widget registry in Python and the
real widgets persist across restarts. The UI Builder syncs on mount (and via a
"Sync catalog" button).

**Preview:** the UI Builder's "live render" toggle draws a widget through the
SAME host implementation the published dashboard uses
(`renderDashboardWidget`), wrapped in an error boundary
(`ui-builder/live-boundary.tsx`) so a failing widget degrades instead of crashing
the builder; ids with no host renderer (the foundational catalog kinds) show the
structural card.

**Boot sync:** `UiCatalogSync` (mounted on the main app route) calls
`syncCoreCatalog()` once, so the catalog is seeded without opening the Builder.

**Live Pages (bridge to the app):** blueprints are rendered as real pages, not
only in the Builder. The **Pages** tab
(`src/components/screens/pages/pages-screen.tsx`, `AppTab 'pages'`) lists the
saved blueprints and draws the selected one through the SAME
`CustomizableWorkspace` + `renderDashboardWidget` the Command Center uses, with
`defaultLayout` mapped from the blueprint. The pure, tested
`src/lib/ui-engineering/live-page.ts` (`blueprintLayoutToKernel` /
`kernelLayoutToWire` / `pageStorageKey`) is the ONE translator between the wire
blueprint layout and the kernel layout; "Save to page" writes the user's
arrangement back via `ui_save_layout` and "Revert" clears the local cache. The
Command Center's own localStorage layouts are mirrored into a per-dashboard
blueprint on edit (`dashboard-blueprint.ts`, via `CustomizableWorkspace`'s
`onLayoutChange`) so the agent can read/edit the board the user actually has.

**Focus + dispatch:** the chat forwards the focused page with the run
(`uiContext` → `input.context.ui` → a per-run prompt block), and an Engineer
request now moves its task/plan to RUNNING so the existing scheduler dispatches
it (previously it stopped at PLANNING and silently did nothing). See
`docs/harness/capability-extension-plan.md` for the remaining Phase D/E work.

**Portability & CLI:** `GET /ui/blueprints/{id}/export` produces a
self-describing snapshot (`kind: eclipse.ui.blueprint`); `POST
/ui/blueprints/import` validates it and stores it as a NEW blueprint.
`eclipse ui {components|capabilities|blueprints|show|history|create|classify|
export|import|restore}` drives the same service over the runtime's store.

**Verification:** `python/tests/test_ui_agent_e2e.py` drives the REAL
`execute_run` graph — a scripted model emits `ui_*` tool calls — and asserts a
durable page with a metric card results, proving the natural-language → tools →
state path without a live provider.

**Permission model:** every `ui_*` tool is `permission="read"`, because a
blueprint mutation changes only Eclipse's OWN saved UI configuration (owner-
scoped) and grants no filesystem, network, shell, database or secret access —
exactly as the `artifact_*` catalog tools do. A genuinely new capability that
needs source code is the Engineer path (the privileged code surface), not a UI
tool.

## Two-mode generation (Phase 6)

`mode.py::classify_request` is a **deterministic, model-free** classifier that
decides how a UI request is satisfied:
- **Compose** — arrange/configure/lay out REGISTERED components over declarative
  blueprints (no source code). The default when there is no new-capability signal.
- **Engineer** — the request needs genuinely new functionality (a new component,
  plugin, route, API, entity or integration) → the privileged code path.
- **Both** — a mixed request; engineer the missing capability first, then compose.

It errs toward Compose so a misread can never silently turn a configuration
change into a source-code release. Exposed as the `ui_classify_request` tool and
`POST /ui/classify`.

## UI Engineering Agent (Phase 7)

When a request needs genuinely new functionality, Eclipse does **not** start a
parallel agent loop. `UiEngineering` (`engineering.py`) creates a **durable
engineering task** on the EXISTING Task / Plan runtime
(`python/harness/tasks/`): a plan + a task assigned to `code-agent` at
`edit_verify` autonomy, carrying UI acceptance criteria (source implemented and
type-checks; tests pass; registered in the UI catalog; renders in preview). The
existing task scheduler then dispatches it through the ordinary run path, where
the established code capability owns repository understanding, checks, preview
and the bounded repair loop — this module adds none of that.

The loop closes with `register_component`: after the code path adds a new
component, `ui_register_engineered_component` (or `POST
/ui/engineering/{task_id}/components`) registers it in the ONE catalog (so a
follow-up Compose request can use it), satisfies the "registered in the UI
catalog" criterion with evidence, and attaches a `ui-component` artifact to the
task. Compose-mode requests create **no** task — `start` reports that honestly.
Tools: `ui_start_engineering`, `ui_engineering_status`,
`ui_register_engineered_component`, `ui_link_engineering_artifact`; routes
`POST /ui/engineering`, `GET /ui/engineering/{plan_id}`, `POST
/ui/engineering/{task_id}/components|artifacts`.

