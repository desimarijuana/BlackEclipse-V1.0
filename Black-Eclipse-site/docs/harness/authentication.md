---
title: Authentication & multi-user mode
status: Current
last-verified: 2026-11-15
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

`HARNESS_AUTH=off` is a **local-development escape hatch**, not a deployment
mode. (The container that used to force `required` was deleted with the browser
lane on 2026-11-13, so nothing overrides the variable any more — the desktop app
is loopback-only and relies on that.)

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
   redirect to `/login`. When mode is off it is a no-op. When auth is required
   but no usable signing secret exists, every request fails closed with `503`.
   Independently of the auth mode, a **central cross-site gate** runs first: a
   browser-declared `Sec-Fetch-Site: cross-site` request is refused, and a
   mutating API call must pass the same-origin / loopback / operator-secret
   policy (`src/lib/api-guard.ts`). Public HMAC webhooks are exempt. This is what
   protects the default desktop (`HARNESS_AUTH=off`) from drive-by CSRF.
2. **`requireApiAuth(request)` / `getAuthContext(request)` (Node)** — the
   *authoritative* check. A route that needs a real identity resolves the cookie
   to a live session row and an active user; a deleted session is refused
   immediately. **Only routes that call it get that guarantee** — middleware
   checks the signature, not the database. The privileged route families
   (command execution, workspace files/roots, artifacts, terminal, security
   admin, runtime restart) call it; read-only routes may still accept a signed
   token until its 7-day expiry.

The desktop app runs accountless (`HARNESS_AUTH=off`, no sign-in screen). The
login/setup endpoints exist only for an operator who explicitly enables auth for
a non-loopback deployment.

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

The runtime's tenant requirement is the SAME decision, not a second one: it calls
`security/identity.py:front_door_requires_auth()` (the Python mirror of
`config.ts`), so `HARNESS_AUTH=off` means single-tenant even under
`NODE_ENV=production`, and the `/health` posture and the enforcement can never
disagree. Setting `NODE_ENV=production` alone must never turn tenancy on — that
combination is exactly the documented `npm run start` local mode.

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

## Boot-time posture (the startup log)

The Python harness logs ONE posture line at boot and warns BEFORE serving when
the deployment is unsafe: `deps.deployment_guard()` composes the runtime bind
with the front door's mode (the same signals as `config.ts`), and warns when

- a public bind has no `CRON_SECRET`,
- a public bind runs with `HARNESS_AUTH=off` — the combination neither side used
  to flag (a configured operator secret used to silence every warning while the
  front door stayed wide open),
- auth is required but `HARNESS_AUTH_SECRET` is missing/short (every request
  fails closed with `503 AUTH_MISCONFIGURED`).

A public bind behind front-door auth with both secrets is an informational
notice, not a warning — that is a legitimate single-operator deployment
(`docs/DEPLOYMENT.md`). Tests: `python/tests/test_identity_tenancy_boundary.py`.

## What is still true (do not over-claim)

- With `HARNESS_AUTH=off`, there is **no** authentication and **no** tenancy
  isolation. That configuration must stay on a trusted, local-only machine.
- The Python runtime is still reached only by the Next.js front door over loopback
  or the operator token (`require_operator`); this feature protects the *front
  door*, which is what an external caller hits.
- There are no roles beyond `operator`, and no per-resource ACLs. Isolation is by
  user `scope`; it is a real boundary only when auth is on.

## Configuration

Turn it on with the supported one-line setup (it never rotates a live secret):

```bash
npm run auth:setup            # HARNESS_AUTH=required + a generated secret
npm run auth:setup -- --dry-run
```

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
