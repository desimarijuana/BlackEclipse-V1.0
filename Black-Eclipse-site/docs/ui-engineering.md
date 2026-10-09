---
title: UI Engineering Foundation
status: Current
last-verified: 2026-10-09
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

