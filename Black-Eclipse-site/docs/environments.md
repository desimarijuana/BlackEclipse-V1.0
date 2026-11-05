---
title: Development and production servers
status: Current
last-verified: 2026-11-04
---

# Development and production servers

BlackEclipse runs as **two independent servers**. They can run at the same time
without interfering with each other.

| | Development | Production |
|---|---|---|
| Start | `npm run dev` | `npm run up` (or `black eclipse`) |
| Server | `next dev --turbopack` | `next start` (prebuilt) |
| URL | <http://localhost:3000> | <http://blackeclipse> (proxy on `:80/:443`) |
| App port | `3000` (`BE_DEV_PORT`) | `3100` (`BE_PROD_PORT`) |
| Python harness | `http://127.0.0.1:8765` | `http://127.0.0.1:8766` |
| Next build dir | `.next-dev` | `.next` |
| Runtime state | `.black-eclipse/dev/` | repository root |
| Canonical-host redirect | off | on (`BE_CANONICAL_HOST`) |
| Reverse proxy / TLS | off | on |

The defaults live in `scripts/lib/profiles.js`. `scripts/local-host.js` applies
them: it sets `PORT`, `HARNESS_PY_URL`, `HARNESS_PY_PORT`,
`HARNESS_CALLBACK_URL` and `NEXT_DIST_DIR` on the child process, overriding any
generic `PORT` in `.env`. The dev profile also points
`AGENT_MEMORY_DB_PATH` and `ECLIPSE_MEMORY_DB_PATH` at `.black-eclipse/dev/`,
and sets `BE_DB_PATH` to the repository `jdds.db` so the market/journal data is
shared (see below).

**Why separate ports is the point.** `predev`/`prestart` free only their own
profile's ports (`scripts/kill-port.js dev|prod`). Before the split, both hooks
killed `3000` and the single harness port, so starting dev tore down the running
production server.

## What is shared, and what is not

Shared on purpose:

- `jdds.db` (market-data vault and settings). Dev reads the same snapshot as
  production instead of copying a large database. Mechanically: the dev profile
  sets `BE_DATA_DIR` only for the isolated runtime DBs, and pins
  `BE_DB_PATH=<repo>/jdds.db`, which `src/lib/db.ts` honours ahead of
  `BE_DATA_DIR/jdds.db` (as do `doctor.js` and `db-guard.js`). Without the pin,
  dev would open an empty `.black-eclipse/dev/jdds.db` with no schema and every
  Prisma-backed screen would fail with `P2021`.
- The workspace tree and artifacts under `.black-eclipse/` (other than `dev/`).
- `node_modules`, the Python interpreter, and the git worktree.

Isolated:

- Agent memory, evolution history, recovery ledger and other Python runtime
  databases (`.black-eclipse/dev/*.db`). Feature work cannot corrupt production
  memory.
- Next build output: dev writes `.next-dev`, production keeps `.next`, so a dev
  run never invalidates the cached production build.
- Ports, so both servers can be up simultaneously.

If you need a change to reach production, it must be built:
`npm run up` rebuilds only when source changed (`scripts/lib/server.js`
source hash). `npm run dev` never builds.

Production builds are **serialized**: `npm run build`, `npm run up`,
`black eclipse` and the desktop launcher all take `.next-build.lock` before
running `next build`, and a second build waits for the first instead of wiping
the same `.next` directory underneath it. The lock lives outside `.next` because
the build deletes that directory; it is advisory, so a raw `npx next build`
bypasses it.

## Commands

| Command | Effect |
|---|---|
| `npm run dev` | Development server on `3000` (doctor + kill-port `dev` first) |
| `npm run up` | Production server on `3100` behind the proxy (rebuilds if needed) |
| `npm start` | Same production launcher, without the build check |
| `black eclipse` / `black dev` | The same two servers from anywhere after `npm link` |
| `black status` | Reports both servers |
| `black stop` | Stops production; `black stop --all` also stops development |
| `npm run dev:next` / `npm run dev:local` | Raw `next dev` escape hatches: no profile env, no isolation |

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
