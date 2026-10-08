---
title: Authentication & multi-user mode
status: Current
last-verified: 2026-10-07
---

# Authentication & multi-user mode

**Who this is for:** an operator exposing BlackEclipse beyond their own machine,
or a developer changing how a request's identity is resolved.

BlackEclipse is a zero-config, single-user local app. Authentication is therefore
**opt-in** and engages **automatically** at the moment the app could be reached
by another machine. `npm run dev` on localhost is unchanged: no login, no setup.

## The mode (the whole design)

`src/lib/auth/config.ts` resolves one decision from the environment:

| Signal | Mode | Why |
|---|---|---|
| `HARNESS_AUTH=required` | **required** | Explicit opt-in. |
| `HARNESS_AUTH=off` | **off** | Explicit opt-out (trusted local machine). |
| unset, bound to a non-loopback host | **required** (`auto-public`) | Reachable by another machine → must not be open. |
| unset, `NODE_ENV=production` | **required** (`auto-public`) | Often behind a proxy; fail safe. |
| unset, local dev bind | **off** (`auto-local`) | Zero-config preserved. |

When mode is **required**, a signing secret is also required:

```
HARNESS_AUTH_SECRET=<random, >= 16 chars>
```

If auth is required but the secret is missing, **every request fails closed**
(`503 AUTH_MISCONFIGURED`) with a clear instruction — the app is never silently
open, and never silently locks you out without saying why. `scripts/doctor.js`
prints the current auth posture at boot.

## How a request is authenticated

Two layers, because the Edge middleware cannot open SQLite:

1. **`src/middleware.ts` (Edge)** — the app-wide *coarse* gate. It requires a
   validly **signed** session cookie for every page and every `/api/**` call,
   except `/login` and `/api/auth/**`. API calls get `401 AUTH_REQUIRED`; pages
   redirect to `/login`. When mode is off it is a no-op.
2. **`requireApiAuth(request)` / `getAuthContext(request)` (Node)** — the
   *authoritative* check. A route that needs a real identity resolves the cookie
   to a live session row and an active user; a deleted session is refused
   immediately. Every mutation route should call `requireApiAuth` after the
   middleware gate.

Sessions are opaque server-side ids stored in `.black-eclipse/auth.db` (gitignored,
never JDdS, never committed). The cookie carries only the signed id — `HttpOnly`,
`SameSite=Lax`, and `Secure` whenever the request is not loopback.

## Tenancy

When auth is **on**, identity and scope come from the **session**, never the
request body: a signed-in user cannot widen their scope by sending a different
`scopeId`. `resolveScope(request, requested)` returns the session scope when auth
is on, and passes the caller's label through unchanged when it is off (so local
behaviour is identical to before). When auth is **off**, `userId`/`scopeId` remain
self-asserted scope *filter* labels — a correctness boundary, not a trust boundary.

## Endpoints

| Route | Purpose |
|---|---|
| `GET  /api/auth/me` | `{authRequired, authenticated, setupRequired, user}` |
| `POST /api/auth/setup` | First-run: create the first account (refused once one exists) |
| `POST /api/auth/login` | `{username, password}` → sets the session cookie |
| `POST /api/auth/logout` | Clears the cookie + deletes the session |

The UI is `src/app/login/page.tsx`: it shows **setup** when no account exists and
**login** otherwise, then returns the user to where they were going.

## What this changes in `/health`

`identity` now reports the *real* posture instead of a hardcoded "not
implemented": `authentication` is `true` only when the front door actually
requires a signed-in user, plus a `frontDoorAuth` block
(`required`/`source`/`secretConfigured`/`misconfigured`). The app is never
presented as multi-user secure unless it is.

## What is still true (do not over-claim)

- With `HARNESS_AUTH=off`, there is **no** authentication and **no** tenancy
  isolation. That configuration must stay on a trusted, local-only machine.
- The Python runtime is still reached only by the Next.js front door over loopback
  or the operator token (`require_operator`); this feature protects the *front
  door*, which is what an external caller hits.
- There are no roles beyond `operator`, and no per-resource ACLs. Isolation is by
  user `scope`; it is a real boundary only when auth is on.

## Configuration

| Env var | Meaning |
|---|---|
| `HARNESS_AUTH` | `required` / `off` (unset = auto) |
| `HARNESS_AUTH_SECRET` | Session signing secret, ≥ 16 chars (required when auth is on) |
| `HARNESS_AUTH_DB` | Optional override for the auth DB path (default `.black-eclipse/auth.db`) |
| `HOST` / `NODE_ENV` | Drive the auto decision |

## Tests

- `src/lib/auth/config.test.ts` — the mode resolver (zero-config preserved, auto-on beyond loopback).
- `src/lib/auth/store.test.ts` — scrypt hashing + session lifecycle (in-memory).
- `src/lib/auth/session.test.ts` — token sign/verify + identity resolution.
- `src/lib/auth/handlers.test.ts` — setup/login/logout/me + the tenancy rule.
- `src/middleware.test.ts` — the gate (401 APIs, redirect pages, allow login/auth).
- `python/tests/test_identity_tenancy_boundary.py` — `/health` reports the real mode.
