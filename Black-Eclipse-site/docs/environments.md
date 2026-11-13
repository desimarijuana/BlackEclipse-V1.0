---
title: Development and production servers
status: Current
last-verified: 2026-11-13
---

# Desktop channels — Stable and Dev

BlackEclipse is a **desktop product**. There is no browser/website runtime in
the daily loop. Two independent desktop channels can run at the same time:

| | **Stable** | **Dev** |
|---|---|---|
| Start | installed `Black Eclipse.exe` (or `npm run desktop:refresh`) | `npm run desktop:dev` |
| Window | `Black Eclipse.exe` | `black-eclipse-desktop.exe` (`target-dev`, own identifier) |
| URL | `http://127.0.0.1:3100` | `http://127.0.0.1:3101` |
| Python harness | `http://127.0.0.1:8767` | `http://127.0.0.1:8768` |
| Build | `.next` → versioned release | `.next-desktop-dev` |
| Served artifact | `releases/stable/<buildId>/.next` (immutable) | `releases/dev/<buildId>/.next` or its pin |
| Data | repository root (checkout) / `%LOCALAPPDATA%\BlackEclipse\data` (install) | `.black-eclipse/desktop-dev/` (isolated) |
| Changes | only via `npm run desktop:promote` | every `npm run desktop:dev` |
| Rollback | `npm run desktop:rollback` | re-run `desktop:dev` |

The channel table lives in **one file**: `scripts/lib/channels.js`. Ports are
fixed because Tauri's IPC capability allowlist cannot wildcard a port; moving a
channel would silently disable notifications.

**Why this split exists.** A build/test used to share `.next`, port 3100 and the
harness port with the app the user was working in. That is why "I built it, then
it broke" kept happening. Now a Dev build cannot rewrite Stable's artifact, the
two harnesses are independent, and killing Dev cannot touch Stable.

**Promotion is the only way Stable changes.** `npm run desktop:promote` copies
the completed `.next` into `releases/stable/<buildId>/`, validates the copy,
writes `current.json` (keeping `previous.json`), then restarts the Stable
window. A build that fails validation never becomes current. `npm run
desktop:rollback` flips back. `npm run desktop:refresh` is build-if-needed +
promote + reopen.

**Health is cheap.** The harness serves `/health/live` (constant time) for the
supervisor's readiness probe; `/health` remains the diagnostic document. The
probe budget is 30 s, because the full document was measured at 20+ s under a
concurrent build and used to be mistaken for a dead runtime.

**The website lane is retired, not deleted.** `npm run dev`, `npm run up`,
`npm run start`, the proxy/TLS/hosts tooling and the browser shortcut all exit
with a "desktop-only" message unless `BE_ALLOW_WEB=1`. The code is kept for a
future browser release. Validation is `npm test`, `npx tsc --noEmit` and a
build — no server.

`scripts/lib/profiles.js` still defines the legacy web profiles for that future
lane; the desktop no longer reads them. `scripts/local-host.js`,
`scripts/start-desktop.js` and `scripts/local-proxy.js` are gated.

## What is shared, and what is not

Shared on purpose:

- `node_modules`, the vendored Python interpreter, the source tree and the git
  worktree.
- The build lock (`.next-build.lock`), so only one build runs at a time on the
  checkout even across channels.

Isolated:

- **Everything a channel serves.** Stable reads a versioned release or its pin;
  Dev reads `.next-desktop-dev` / its own pin. Neither reads the other's build
  while it is being written.
- **Data.** Stable uses the real data directory. Dev uses
  `.black-eclipse/desktop-dev/`, seeded once with a consistent `VACUUM INTO`
  snapshot of `jdds.db`. A dev experiment can never write the real journals or
  memory.
- **Processes and ports.** App 3100/3101, harness 8767/8768, owner markers and
  start locks live under each channel's data directory.

Builds are **serialized**: `npm run build`, `desktop:build:dev`,
`desktop:refresh`, `desktop:promote`, `black eclipse` and the desktop launcher
all take `.next-build.lock` before running `next build`. A second build waits
instead of wiping the same directory underneath it. The lock lives outside
`.next` because the build deletes that directory; it is advisory, so a raw
`npx next build` bypasses it.

Reaching Stable requires **promotion**, never an in-place rewrite:
`desktop:promote` validates the staged copy, moves `current.json` (keeping
`previous.json`), and restarts the window. See
[`desktop/README.md`](../desktop/README.md#channels-stable-and-dev).

## Commands

| Command | Effect |
|---|---|
| `npm run desktop:dev` | Build/pin the Dev payload and launch the Dev window (3101) |
| `npm run desktop:refresh` | Build if needed, promote, reopen Stable |
| `npm run desktop:promote` | Stage + validate the current build, make it Stable, restart |
| `npm run desktop:rollback` | Flip Stable back to the previous release |
| `npm run desktop:doctor` | One-screen health: window, ports, build, harness, provider |
| `npm run desktop:build:dev` | Build `.next-desktop-dev` only (no launch) |
| `npm run desktop:build:dev-shell` | Build the separate Dev Tauri binary |
| `npm run build` | Build Stable's `.next` (still the source for promotion) |
| `npm run dev` / `npm run up` / `npm start` / `npm run proxy` | **Retired**; print a desktop-only message unless `BE_ALLOW_WEB=1` |

## Dev chunk caching, and the "module factory is not available" overlay

A Turbopack **dev** chunk is named after the MODULE it serves
(`src_components_screens_a6343f43._.js`), not after the bytes it holds. Edit,
rename or delete a module and the bytes behind that same URL change while the
URL stays put. So dev chunks must never be served `immutable`: the browser
would keep the OLD bytes, ask the runtime for a module factory the server no
longer has, and the page would die behind "the module factory is not available.
It might have been deleted in an HMR update".

Dev chunks therefore **revalidate** (`public, max-age=0, must-revalidate`, see
`next.config.ts`). The dev server already sends `ETag`/`Last-Modified`, so a
second tab still gets a cheap `304` instead of re-downloading the whole client
graph, and a changed chunk is always fetched fresh. Production is unaffected:
a real build is content-hashed and immutable.

A browser that already cached the old immutable copies needs one repair:
`GET /api/dev/cache-reset` (dev only) answers with `Clear-Site-Data: "cache"`
— the HTTP cache only, never cookies or localStorage, so the operator stays
signed in. Then reload the app.

## Docker

The container is a single production deployment: it runs `next start` on
`PORT=3000` and spawns the harness inside the container
(`src/lib/harness/python-runtime.ts`). The two-profile split is for the local
developer machine; a container has one environment.
