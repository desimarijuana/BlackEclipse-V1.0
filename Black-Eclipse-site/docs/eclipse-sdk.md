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
| Update / delete a page | `eclipseSdk.pages.update/remove` | same UI blueprint |
| Control the Command Center | `eclipseSdk.dashboards.{list,active,get,addWidget,moveWidget,setColumns,setZones,restore,templates,applyTemplate,reset}` | durable dashboard mirror blueprint (`/dashboard/<id>`) |
| Control the app shell | `eclipseSdk.app.{get,update,reset,open,navigate}` | JDDS `SystemConfig` key `eclipse_app_shell_nav` + `/api/sdk/app/stream` SSE |
| Create a fund portfolio | `eclipseSdk.portfolio.createFund({ name, goal })` | `Portfolio` row with `kind='fund'` + metadata |
| Add stock to a portfolio | `eclipseSdk.portfolio.addStock(id, { symbol, quantity, price })` | Portfolio transaction ledger (BUY/TRANSFER_IN) |
| Create / apply a theme | `eclipseSdk.theme.create(spec)` / `applyPreset(idOrName)` | app-wide theme in JDDS `SystemConfig` |
| Save named themes | `eclipseSdk.theme.savePreset(name, spec)` | `SystemConfig` key `eclipse_theme_presets` |
| Change the design | `eclipseSdk.design.apply({ colors: { primary } })` | compatibility path into the same app-wide theme |
| Lock a resource | `eclipseSdk.locks.create({ resourceType, resourceId, passphrase })` | `SdkLock` on `agent-memory.db` |
| Unlock | `eclipseSdk.locks.unlock(lockId, passphrase)` | short-lived HMAC token (15 min) |
| Inspect activity | `eclipseSdk.audit.list({ limit, action, resourceType })` | `SdkAudit` on `agent-memory.db` (bounded) |
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

## The app shell is controllable

The sidebar's fixed sections have an **app-wide** configuration: order and
visibility. The active nav mode (`terminal`, `agentic`, `bots`, `graph`) is
**per shell**: each browser tab/window owns its mode in `sessionStorage`, and a
remote nav event updates the sections without overriding an open shell's mode.
The shared mode in JDDS `SystemConfig` under `eclipse_app_shell_nav` is the
seed a newly opened shell starts from. `localStorage` remains the instant-paint
cache and still owns per-browser keyboard shortcuts (they are not app-wide).

```ts
await eclipseSdk.app.get();                 // nav + manifest (nav.mode is the shared seed)
await eclipseSdk.app.update({                // reorder/hide/show; mode seeds new shells
  sections: [{ id: 'chat', enabled: true }, { id: 'news', enabled: false }],
  mode: 'terminal',
});
await eclipseSdk.app.reset();                 // shipped order, every section shown

eclipseSdk.app.open({ tab: 'dashboard', dashboardId: 'main' }); // this shell
await eclipseSdk.app.navigate({ tab: 'pages', page: 'uibp_...' }); // every shell
```

Missing sections are appended in canonical order, so a patch can never make a
nav entry disappear by omission. Unknown ids are dropped. `app.open` drives the
existing deep-link/popstate path in the current tab; `app.navigate` publishes a
command on `/api/sdk/app/stream`, which every connected shell applies (that is
how chat/Python opens a surface). A `dashboardId` is also written as a pending
selection so the Command Center switches boards even if it mounts afterwards.

Local sidebar **section** edits are mirrored up (debounced) once the remote
state has been read; the server's own `nav` event is applied without echoing
back. A local mode change updates the shared seed but deliberately does not
change another open shell's mode. The first browser to run after upgrading
migrates its existing `localStorage` arrangement into the app-wide row, matching
the theme's one-time local→server migration.

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

Persona templates stay in the ONE TypeScript registry
(`src/lib/dashboard/templates.ts`): `dashboards.templates()` lists them and
`dashboards.applyTemplate(id, templateId, { market })` builds the centre bands
plus the left Watchlist and market right rail, then writes the layout through
the revision-guarded `/sdk/dashboards/<id>/layout` API. `dashboards.reset(id)`
uses the shipped default board when configured, else the first persona.
Concurrent edits are retried once with the fresh revision; an explicit
`expectedRevision` is never retried. There is no Python copy of the templates.

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

The SDK screen's lock manager covers every resource type (`page`, `widget`,
`portfolio`, `design`, `dashboard`, `theme`), filters by resource type and
search, shows the hint/updated time, and marks resources unlocked in this tab.
Unlocking is per-tab for 15 minutes; removing a lock still requires that token
or the passphrase.

## Activity and undo

Every SDK mutation appends one row to `SdkAudit` on `agent-memory.db`:
`actor`, `action`, `resourceType`, `resourceId`, a human summary, bounded JSON
detail and a timestamp. Passphrases, hashes and hints are never stored.
Front-door-owned surfaces (themes, app-shell nav, dashboard templates) call
`POST /sdk/audit` over the loopback callback after a successful write; a runtime
that is down never turns a successful edit into a failure. The table is capped
at the newest 2,000 rows; `GET /sdk/audit?limit=&action=&resourceType=` reads
it, and the SDK screen's Activity panel filters/searches the same rows.
`sdk_audit_list` is the read-only chat tool (for "what changed recently?").
Local Command Center drag/drop publishes go through `/api/ui/...`, not the SDK,
so they appear in the board's **History** rather than Activity; Activity is the
SDK/agent control trail.

The Command Center's **Undo** button (Ctrl/Cmd+Z) restores the newest retained
mirror revision older than the current one; **History** lists the retained
revisions with summaries/timestamps and a Restore action. A restore is recorded
as a NEW revision, so an undo is itself undoable. Both use
`dashboards.history`/`dashboards.restore`; the browser applies the restored
layout immediately and the normal SSE reverse-sync keeps other tabs current.

## Themes

`theme.create(spec)` accepts a **closed ThemeSpec**, builds it with the existing
`themeFromBrandColor` + `normalizeTheme`, validates it, and saves the result as
the app-wide theme. No CSS, HTML or arbitrary code is accepted. The spec is:

```ts
{
  name?, basePreset?, brand?, scheme?: 'dark' | 'light',
  density?: 'compact' | 'comfortable' | 'spacious',
  radius?, shadow?: 'none' | 'soft' | 'medium' | 'dramatic',
  background?: 'solid' | 'gradient' | 'grid',
  glass?: { enabled?, blur?, opacity?, tint? },
  sidebar?: { tint?, opacity?, blur? },
  fontUi?, fontHeading?, fontMono?,
  appName?, logoText?, logoUrl?
}
```

A request like "cyberpunk neon magenta dark, tight radius" maps to
`{ basePreset: 'eclipse', brand: '#ff2bd6', scheme: 'dark', density: 'compact',
radius: 0.25, shadow: 'dramatic', glass: { blur: 28, opacity: 0.4 } }`.
`theme.savePreset(name, spec)` stores a named app-wide preset under
`eclipse_theme_presets`; `theme.applyPreset` accepts either a shipped id
(`eclipse`, `midnight`, `white`, ...) or a saved name. `theme.deletePreset`
deletes only saved presets; shipped presets are immutable. Settings →
Customization → Theme now lists these app-wide presets beside the browser-local
ones; saving there projects the live theme onto the closed spec with
`themeToSpec` (chart palette/backdrop/favicon stay browser-local).

`design.apply` remains a compatibility path for a deep partial patch. All theme
writes check the `theme:global` and `design:global` locks. The SDK client emits
`eclipse:theme-changed`; `useThemeStore` re-reads `/api/theme` on that event,
window focus, and a 15s fallback, so every tab converges on the same theme.

## Routes and files

| Layer | Location |
|---|---|
| Contracts | `python/harness/sdk/model.py` |
| Durable rows | `python/harness/sdk/store.py` (`SdkWidget`, `SdkLock`, `SdkMeta`, `SdkAudit` on `agent-memory.db`) |
| Lock gate | `python/harness/sdk/locks.py` (`LockService`, `LockError`, token contextvar, audit) |
| Dashboard control | `python/harness/sdk/dashboards.py` (`DashboardService`) |
| Dashboard templates (tools) | `python/harness/sdk/dashboard_template_tools.py` (`sdk_dashboard_templates/apply_template/reset`) |
| App shell (tools) | `python/harness/sdk/app_tools.py` (`sdk_app_*`) |
| Loopback callback | `python/harness/sdk/callback.py` (shared base URL + operator header) |
| Orchestrator | `python/harness/sdk/service.py` (`EclipseSdk`) |
| Agent tools | `python/harness/sdk/tools.py` (`SDK_TOOLS`, read-permission config mutations) |
| Boot wiring | `python/harness/sdk/bootstrap.py` (`install_sdk_layer`) |
| Python routes | `python/harness/routers/sdk.py` (`/sdk/*`, operator-gated) |
| Next front door | `src/app/api/sdk/[[...path]]/route.ts` |
| Typed client | `src/lib/sdk/index.ts` |
| Audit writer | `src/lib/sdk/audit-server.ts` (front-door writes → loopback `/sdk/audit`) |
| Dashboard undo helper | `src/lib/sdk/dashboard-history.ts` |
| Widget host renderer | `src/lib/sdk/widgets.tsx` |
| Widget registry | `src/lib/workspace/widget-registry.ts` + `use-widgets.ts` |
| Clock renderer | `src/lib/dashboard/clock-widget.tsx` |
| Dashboard live bridge | `src/lib/ui-engineering/dashboard-blueprint.ts` |
| ThemeSpec builder | `src/lib/sdk/theme-spec.ts` |
| Named theme presets | `src/lib/sdk/theme-presets.ts` (server-only) |
| Theme routes | `src/lib/sdk/theme-server.ts` (`/api/sdk/theme*`) |
| Settings preset UI | `src/components/screens/app-wide-theme-presets.tsx` + `theme-preview.tsx` |
| Dashboard template builder | `src/lib/sdk/dashboard-templates.ts` (server-safe view of the TS registry) |
| Dashboard template routes | `src/lib/sdk/dashboard-server.ts` (`/api/sdk/dashboards/templates`, `<id>/template`, `<id>/reset`) |
| App shell contracts | `src/lib/sdk/app-shell-types.ts` (shared pure normalization) |
| App shell store/routes | `src/lib/sdk/app-shell.ts` + `app-server.ts` (`/api/sdk/app*`) |
| App shell live sync | `src/lib/sdk/app-shell-client.ts` (mounted by `ui-catalog-sync.tsx`) |
| Shell navigation helper | `src/lib/sdk/navigate.ts` (deep link + pending dashboard) |
| Design merge | `src/lib/sdk/design.ts` |
| SDK tab UI | `src/components/screens/sdk/sdk-screen.tsx` |
| Sidebar page links | `src/components/layout/sdk-pages-nav.tsx` |

Tests: `python/tests/test_sdk_service.py`, `python/tests/test_sdk_api.py`,
`python/tests/test_sdk_dashboards.py`, `python/tests/test_sdk_app_shell.py`,
`python/tests/test_sdk_audit.py`, `src/lib/sdk/design.test.ts`,
`src/lib/sdk/theme-spec.test.ts`, `src/lib/sdk/theme-presets.test.ts`,
`src/lib/sdk/theme-server.test.ts`, `src/lib/sdk/audit-server.test.ts`,
`src/lib/sdk/app-shell-types.test.ts`, `src/lib/sdk/app-server.test.ts`,
`src/lib/sdk/dashboard-templates.test.ts`, `src/lib/sdk/dashboard-server.test.ts`,
`src/lib/sdk/dashboard-history.test.ts`,
`src/lib/workspace/widget-registry.test.ts`,
`src/lib/dashboard/clock-widget.test.tsx`.

## Chat control

The deterministic chat classifier returns `app_control` for requests that
control an existing Eclipse surface - add/move widgets, change the dashboard
layout or apply a template, create/apply themes, hide/reorder the sidebar
navigation, open a tab, create a page in the nav, or lock/unlock a resource.
Those turns keep the standard `eclipse-agent` surface (which includes
`SDK_TOOLS`) and carry an `appControl` runtime note so the model prefers
`sdk_*` over the lower-level `ui_*` engine.

The app-shell tools are `sdk_app_get`, `sdk_app_nav_update`,
`sdk_app_nav_reset` and `sdk_app_open`; dashboard templates add
`sdk_dashboard_templates`, `sdk_dashboard_apply_template` and
`sdk_dashboard_reset`; page editing adds `sdk_page_update`/`sdk_page_delete`;
`sdk_audit_list` reads recent activity.

`/app` forces that surface explicitly (no autonomy, no code profile) and is the
recommended route for app-control work. `/eclipsesdk` remains the source-code
path: a new visual kind, a new renderer, a bug fix or a dependency change still
routes there, exactly as intended.

## Boundaries

- No arbitrary code execution: widgets are a closed primitive + data source;
  themes are a closed `ThemeSpec`, never CSS.
- No second store or engine: blueprints, portfolios and theme keep their owners.
- No secret exposure: lock responses never include the passphrase hash or salt.
- Locks are not authentication; they prevent accidental/agent changes. User
  authentication stays the front door's opt-in `HARNESS_AUTH` boundary.
