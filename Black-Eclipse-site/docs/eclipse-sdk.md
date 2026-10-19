---
status: Active
last-verified: 2026-10-19
---

# Eclipse SDK

The Eclipse SDK is the user-facing **composition and control surface**. It gives
one typed API for the things a user should be able to change without editing the
source: widgets, pages, fund portfolios, design tokens and locks. It does not
reimplement any subsystem — every operation delegates to the UI Engineering or
Portfolio service, and the front door merges in the app-wide theme.

## What it can do

| Capability | API | Backing store / engine |
|---|---|---|
| Create a widget | `eclipseSdk.widgets.create({ slug, label, primitive, source })` | `SdkWidget` row + a `sdk.<slug>` component in the UI catalog |
| Create / compose a page | `eclipseSdk.pages.create({ title, path, widgets })` | UI blueprint on `agent-memory.db` |
| Control the Command Center | `eclipseSdk.dashboards.{list,active,get,addWidget,moveWidget,setColumns,setZones,restore}` | durable dashboard mirror blueprint (`/dashboard/<id>`) |
| Create a fund portfolio | `eclipseSdk.portfolio.createFund({ name, goal })` | `Portfolio` row with `kind='fund'` + metadata |
| Add stock to a portfolio | `eclipseSdk.portfolio.addStock(id, { symbol, quantity, price })` | Portfolio transaction ledger (BUY/TRANSFER_IN) |
| Change the design | `eclipseSdk.design.apply({ colors: { primary } })` | app-wide theme in JDDS `SystemConfig` |
| Lock a resource | `eclipseSdk.locks.create({ resourceType, resourceId, passphrase })` | `SdkLock` on `agent-memory.db` |
| Unlock | `eclipseSdk.locks.unlock(lockId, passphrase)` | short-lived HMAC token (15 min) |
| List everything | `eclipseSdk.capabilities()` | runtime manifest + design presets |

Import it from any client module:

```ts
import { eclipseSdk } from '@/lib/sdk';
```

It is also exposed as `window.eclipseSdk` for browser-console testing, and the
`Eclipse SDK` tab (`?tab=sdk`) is a thin UI over the same methods.

## Declarative widgets (no code execution)

A user widget is **data**, not JavaScript. It names a closed primitive —
`data-table`, `metric-card`, `line-chart`, `area-chart`, `bar-chart`,
`pie-chart`, `list`, `markdown`, `status-indicator`, `empty-state`,
`error-state`, `clock` - plus an allow-listed source string and config.
`clock` carries only presentation config (`timezone`, `format`, `showSeconds`,
`showDate`, `label`) and renders the host's live clock; an invalid timezone
renders `UNAVAILABLE`, never a guessed time. The Python runtime registers the
component id (`sdk.<slug>`) so the UI engine can place it on a page; the host
turns the record into a real `WidgetDefinition` whose renderer delegates to the
existing generic widgets.

Source strings use the same allow-listed grammar as UI Engineering:

```
portfolio:<portfolioId>:<view>[.<field>]
market:quote:<SYMBOLS>
market:indices:<MARKET>
market:price:<SYMBOL>
news:latest
agent:activity
tasks:list
artifacts:list
research:list
jdds:search:<QUERY>
```

A missing/unresolvable source renders `UNAVAILABLE`; the SDK never fabricates a
value. New widget records are hydrated on app boot and after every create/delete,
so the Pages widget library and page renderer see them immediately.

## Pages are real destinations

`pages.create` creates a blueprint, adds each widget, and optionally sets a
`path`. Open it with:

```
/?tab=pages&page=<blueprintId>
/?tab=pages&page=<path>
```

Saved pages render as normal entries in the main sidebar navigation
(`src/components/layout/saved-pages-nav.tsx`) and open the same deep link - there
is no separate "SDK pages" section. The list refreshes from `/api/ui/stream`, so
a page the agent just created appears without a reload. Command Center mirror
blueprints (`/dashboard/dash-*`) are excluded - they are agent-readable board
snapshots, not user pages. Pages are not Next.js routes; they render inside the
Pages tab through `CustomizableWorkspace` + `renderDashboardWidget`.

## The Command Center is a first-class SDK surface

The dashboard's arrangement lives in a **mirror blueprint** at
`/dashboard/<dashboardId>`. The blueprint is the durable source of truth;
browser `localStorage` is a cache for instant paint and offline editing.
`DashboardScreen` publishes its layout (debounced) and applies a foreign
revision from the SSE stream (`/api/ui/stream`), so an SDK/agent mutation lands
on the live board without a reload. The active dashboard id is stored in
`SdkMeta` (`eclipse_active_dashboard`), written by the screen on switch and read
by `dashboards.active()`.

`dashboards.addWidget` defaults to the active board and packs into the shortest
**main** column, so "add a clock" cannot land in a side rail. Every mutation is
validated and revisioned by the existing UI Engineering engine; `dashboards.
restore` is the undo. Dashboard mirrors are excluded from normal page lists and
are listed only through `dashboards.list()` (the `includeDashboardMirrors`
query flag).

## Fund portfolios

A fund is an **accounting portfolio with fund metadata**, never a second ledger.
`createFund` writes `kind='fund'` plus `{ goal, icon, accent, ... }` metadata.
The agent's `portfolio_create` tool creates the same `kind='fund'` shape (there
is no ledger-only portfolio option), so "create a portfolio" in chat produces a
fund. `addStock` records a
BUY/TRANSFER_IN through the existing Portfolio Accounting Engine, so tax lots,
positions, P&L and reporting stay correct. The engine's portfolio read model also
reports `kind` and `metadata`.

## Locks

Locks are enforced at the **service seam**, so every path obeys them:

- `UiService` checks the page lock and each touched widget instance
  (`<pageId>:<instanceId>`) before `update`, `delete`, `save_layout`,
  `restore_revision` and every widget operation.
- `DashboardService` checks `dashboard:<dashboardId>` before every layout
  mutation, in addition to the mirror blueprint's page lock.
- `PortfolioService` checks the portfolio lock before any ledger mutation
  (including SDK `addStock`). Theme writes use the existing `design:global`
  gate; the `theme` resource type is accepted for future named-theme locks.
- `/api/theme` and `/api/sdk/design` check the `design:global` lock, so the
  Settings theme editor is protected too.

Unlocking returns a token; clients send it as `X-Eclipse-Unlock`. The SDK client
stores it for the browser tab and attaches it automatically to SDK, `/api/ui`,
`/api/portfolio` and `/api/theme` calls. A token is bound to a lock id and
expires after 15 minutes (override with `HARNESS_SDK_UNLOCK_TTL`). Deleting the
lock invalidates every token. Agent tool
runs carry no request header, so a locked resource is read-only to agents until
the user unlocks it.

Passphrases are stored as PBKDF2-HMAC-SHA256 (200k iterations, per-lock salt);
hashes and salts are never returned by the API. Re-locking an already-locked
resource requires a valid unlock token, so a caller cannot replace the
passphrase and defeat the gate.

## Design

`design.apply` accepts a deep partial theme patch — top-level fields plus
`colors`, `glass`, `sidebar` groups — and merges it over the saved app-wide
theme. `design.reset` restores the shipped default. The response is the
normalized theme; the client then calls `useThemeStore.hydrateFromServer()` so
the live app recolors immediately.

## Routes and files

| Layer | Location |
|---|---|
| Contracts | `python/harness/sdk/model.py` |
| Durable rows | `python/harness/sdk/store.py` (`SdkWidget`, `SdkLock`, `SdkMeta` on `agent-memory.db`) |
| Lock gate | `python/harness/sdk/locks.py` (`LockService`, `LockError`, token contextvar) |
| Dashboard control | `python/harness/sdk/dashboards.py` (`DashboardService`) |
| Orchestrator | `python/harness/sdk/service.py` (`EclipseSdk`) |
| Agent tools | `python/harness/sdk/tools.py` (`SDK_TOOLS`, read-permission config mutations) |
| Boot wiring | `python/harness/sdk/bootstrap.py` (`install_sdk_layer`) |
| Python routes | `python/harness/routers/sdk.py` (`/sdk/*`, operator-gated) |
| Next front door | `src/app/api/sdk/[[...path]]/route.ts` |
| Typed client | `src/lib/sdk/index.ts` |
| Widget host renderer | `src/lib/sdk/widgets.tsx` |
| Widget registry | `src/lib/workspace/widget-registry.ts` + `use-widgets.ts` |
| Clock renderer | `src/lib/dashboard/clock-widget.tsx` |
| Dashboard live bridge | `src/lib/ui-engineering/dashboard-blueprint.ts` |
| Design merge | `src/lib/sdk/design.ts` |
| SDK tab UI | `src/components/screens/sdk/sdk-screen.tsx` |
| Sidebar page links | `src/components/layout/sdk-pages-nav.tsx` |

Tests: `python/tests/test_sdk_service.py`, `python/tests/test_sdk_api.py`,
`python/tests/test_sdk_dashboards.py`, `src/lib/sdk/design.test.ts`,
`src/lib/workspace/widget-registry.test.ts`,
`src/lib/dashboard/clock-widget.test.tsx`.

## Boundaries

- No arbitrary code execution: widgets are a closed primitive + data source.
- No second store or engine: blueprints, portfolios and theme keep their owners.
- No secret exposure: lock responses never include the passphrase hash or salt.
- Locks are not authentication; they prevent accidental/agent changes. User
  authentication stays the front door's opt-in `HARNESS_AUTH` boundary.
