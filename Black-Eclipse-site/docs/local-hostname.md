---
title: Local Hostname — blackeclipse (http/https)
status: Current
last-verified: 2026-10-15
---

# Local Hostname — `blackeclipse`

**Who this is for:** an operator who wants to reach the app at
`blackeclipse` instead of `http://localhost:3000`, on this machine only, without
a domain, a deployment, or moving the server.

## What it is (architecture)

```
browser  ──►  https://blackeclipse (:443)  ──►  scripts/local-proxy.js
               (or http://… :80)                 (Node, 127.0.0.1 only)
                                                     │
                                                     ▼
                                           http://127.0.0.1:3000  (Next.js, unchanged)
```

Two pieces, both local:

1. **A hosts-file alias.** `127.0.0.1 blackeclipse` makes the name resolve to
   this computer. A hosts file only maps a *name to an IP* — it cannot change the
   port, which is why the second piece is needed.
2. **A tiny reverse proxy** (`scripts/local-proxy.js`) that listens on
   `127.0.0.1` and forwards to the existing Next.js server on `:3000`. It has
   **zero dependencies** (Node's built-in `http`/`https`/`net` only) and is the
   lightest maintainable option on a machine that already has Node.

The proxy serves **HTTPS when a certificate is provisioned**, and plain HTTP
otherwise. HTTPS matters beyond appearance: it makes the origin a **secure
context**, which the browser's Web Notification API (desktop notifications),
service workers, clipboard and other powerful features require. `http://…` is
not a secure context even though the name resolves to loopback.

### Why this design

| Alternative | Why not chosen |
|---|---|
| Move Next.js to port 80 (`next dev -p 80`) | Changes the dev command; on some setups conflicts with system services; ties hot-reload tooling to a privileged port for no benefit. The task keeps Next on 3000. |
| hosts file alone | Maps a name to an IP, never a port. `http://blackeclipse` would still try port 80. |
| `netsh interface portproxy` | A kernel TCP forwarder: needs admin, is system-wide state (not a per-project script), is TCP-only with no header control, and is awkward to inspect/undo. |
| Caddy / nginx | Perfectly capable, but a new install + service to maintain for a two-line forward. Kept as the documented fallback below. |

### What the proxy preserves (so nothing else breaks)

- The original **`Host`** header is forwarded unchanged, so Next.js reconstructs
  `request.url` as `http://blackeclipse/...`. The app's same-origin mutation guard
  (`src/lib/api-guard.ts`) therefore keeps passing, and session cookies keep
  working.
- **`X-Forwarded-For` / `X-Forwarded-Host` / `X-Forwarded-Proto`** are added for
  code that keys off forwarded information (rate-limit `clientKey`, etc.).
- **WebSocket upgrades** (Next dev HMR at `/_next/webpack-hmr`) are forwarded on
  a raw TCP socket, so hot module replacement works through the hostname.

### Code touchpoints for the new hostname

The hostname changes the browser's origin from `localhost` to `blackeclipse`.
Three small changes make that a no-op for the app:

- `src/lib/api-guard.ts` — `LOCAL_HOSTS` now also contains `blackeclipse` (it is a
  loopback alias), so no-Origin programmatic calls through the proxy are still
  treated as local and cross-site requests are still blocked. Its same-origin
  check is now **proxy-aware**: it compares the `Origin` against the request's
  real `Host`/`x-forwarded-host` header rather than `request.url` (which Next
  rebuilds from its own bind address in dev), so a hostname-fronted request is
  correctly judged same-origin.
- `src/lib/auth/handlers.ts` — the session cookie is **not** marked `Secure` on
  the plain-HTTP local hostname (a `Secure` cookie would be dropped by the
  browser and break login), but **is** `Secure` when the local front door serves
  HTTPS (`x-forwarded-proto: https`).
- `next.config.ts` — `allowedDevOrigins` lists the hostname so Next dev does not
  flag `/_next/*` / HMR requests as cross-origin. Dev-only; production ignores it.

## 1. Configure the Windows hosts file (needs Administrator)

The Windows hosts file lives at
`C:\Windows\System32\drivers\etc\hosts`. It is a protected system file, so the
edit needs Administrator rights.

### Option A — one command (self-elevating)

```powershell
npm run setup:hostname     # UAC prompt → appends the line → flushes DNS
```

`scripts/setup-hostname.ps1` appends `127.0.0.1 blackeclipse` **only if it is
missing** and touches nothing else. It re-launches itself elevated, so you run it
from a normal shell and click *Yes* on the UAC prompt.

### Option B — by hand

1. Open **Notepad as Administrator** (Start → type "Notepad" → right-click →
   *Run as administrator*).
2. **File → Open**, paste `C:\Windows\System32\drivers\etc\hosts`, and open it
   (change the file filter to "All Files" if it is not shown).
3. Add this line at the end (IPv4 is the safest; add the IPv6 line only if you
   want `::1` to work too):

   ```
   127.0.0.1 blackeclipse
   ```

4. Save. No reboot needed.

Verify resolution (any of these):

```powershell
ping blackeclipse                  # must show 127.0.0.1
Resolve-DnsName blackeclipse       # or: nslookup blackeclipse
```

> If `ping` still shows a public IP after editing, you have a typo or a stale DNS
> cache: `ipconfig /flushdns`. Some browsers use their own DNS ("Secure DNS"),
> but hosts-file entries are always honored for `127.0.0.1`.

## 2. Start it (one command → `http://blackeclipse`)

By default, `npm run dev` (and `npm run up`, and the `black` CLI) now start **both**
the app and the proxy, with the app bound to `127.0.0.1` so it is never on the LAN,
and the output rewritten so the only address shown is `http://blackeclipse`:

```powershell
npm run dev          # dev + hot reload; proxy on :80  →  open http://blackeclipse
npm run up           # production (builds once, then instant)
black                # the same, via the global CLI
```

Open **<http://blackeclipse>** (or **<https://blackeclipse>** after section 2b).
The underlying server is still on `http://127.0.0.1:3000`; `http://localhost:3000`
and `http://127.0.0.1:3000` now **redirect** to the hostname (one canonical
origin — see below), so origin-scoped browser storage never diverges.

Prefer to run the two processes yourself? They are independent:

```powershell
npm run dev:next     # the ORIGINAL, unchanged `next dev` (all interfaces, no proxy)
npm run dev:local    # `next dev -H 127.0.0.1` (loopback, no proxy)
npm run proxy        # the front door on 127.0.0.1:80
```

`Ctrl+C` once stops the app and the proxy together.

### One canonical origin

The launcher sets `BE_CANONICAL_HOST` to the hostname, so the app enforces a
single origin: a request on `http://localhost:3000` or `http://127.0.0.1:3000`
is redirected (**307**, path + query preserved) to `http://blackeclipse`
(`https://` once TLS is on). This matters because browser storage — `localStorage`
— is scoped to the origin: without it, the theme, sidebar and chat caches would be
three separate sets depending on which URL you typed. With it, every URL is the
same app with the same storage. (The centralized **theme** is additionally
app-wide on the server in JDDS `SystemConfig`, so it is shared across devices and
browsers too — see `docs/ARCHITECTURE.md`.) The redirect is applied by
`src/middleware.ts` before the auth gate; **page navigations only** — `/api/*` is
deliberately left on the loopback server so the Python harness's callbacks
(`HARNESS_CALLBACK_URL`, which do not follow redirects) keep working. Set
`BE_CANONICAL_HOST=""` to disable it (e.g. when running the raw `next dev` server
alongside the proxy).

**No Administrator rights are required to run the proxy.** Windows does not treat
ports below 1024 as privileged (unlike Unix), and `127.0.0.1:80` is free on this
machine. Administrator is needed **only** for the one-time hosts-file edit.

## 2b. Enable HTTPS — a secure context (desktop notifications)

The launcher serves **plain HTTP** until a certificate exists. To turn on HTTPS
(and thus the browser's desktop notifications), run **once**:

```powershell
npm run setup:tls        # ~1s, NO Administrator prompt
```

That (`scripts/setup-tls.ps1`) creates a self-signed certificate for
`blackeclipse`, stores it in the **current user's** certificate stores
(`My` + trusted `Root` — no machine-wide/admin change), and exports a
`PKCS#12` bundle + passphrase under `.black-eclipse/certs/` (gitignored) for the
Node proxy. Then restart and open **<https://blackeclipse>**:

- `scripts/local-host.js` detects the certificate and starts the proxy in TLS
  mode on `127.0.0.1:443`; the banner shows `https://blackeclipse`.
- Plain `http://blackeclipse` (port 80) now answers `301 → https://blackeclipse`.
- Settings › Alerts/Notifications › **Desktop notifications → Enable** →
  **Send test notification** now works.

`npm run tls:remove` removes the certificate and its files and reverts to HTTP.

Notes:

- **No Administrator rights** are needed for any of this (the current-user cert
  stores are writable by the user; the proxy binds `:443` like it did `:80`).
- Chrome and Edge validate against the Windows trust store, so they trust the
  certificate with no warning. **Firefox** keeps its own store — set
  `security.enterprise_roots.enabled = true` in `about:config`, or use
  Chrome/Edge for notifications.
- If `:80` is taken by another service, the proxy logs the conflict and serves
  `https://blackeclipse` on `:443` anyway (only the auto-redirect is lost).
- The certificate is valid 5 years; re-run `npm run setup:tls` to refresh it if
  it expires (idempotent — it reuses an existing one).

## 3. Stop it

- `Ctrl+C` in the terminal running `npm run dev` / `npm run up` / `black` — that
  launcher stops the app **and** the proxy together.
- If a proxy is ever left behind (e.g. you ran it separately): `npm run proxy:stop`.

The proxy is **not** installed as a Windows service or scheduled task — it runs
only while that terminal stays open. Nothing starts automatically on boot.

## 4. Keep it private (local machine only)

- The proxy binds **`127.0.0.1` only** (not `0.0.0.0`), so no other machine on the
  LAN or internet can reach port 80 even though the Windows Firewall is
  currently **off** on all profiles. The firewall is not modified by this setup.
- The Next dev server, however, binds **all interfaces by default**. To keep port
  3000 on this machine too, use the hardened dev command added for this setup:

  ```powershell
  npm run dev:local    # next dev -H 127.0.0.1
  ```

  `npm run dev` is left exactly as it was; `dev:local` is the recommended variant
  while the proxy is running. Both still serve `http://localhost:3000` and
  hot-reload identically.

## 5. Troubleshooting

**`blackeclipse` does not resolve.** The hosts entry is missing/mistyped, or the
DNS cache is stale. Re-check the line is `127.0.0.1 blackeclipse`, then
`ipconfig /flushdns`.

**Port 80 is already in use.** The proxy prints the conflict on start. Find and
free the owner:

```powershell
Get-NetTCPConnection -LocalPort 80 -State Listen      # shows OwningProcess (PID)
Get-Process -Id <PID>                                  # identify it
```

Common owners: an IIS/W3SVC site, a `docker`/`nginx`/`caddy` container. If you
cannot free it, move the proxy to another port — but then the URL needs the port
back (`http://blackeclipse:8080`), which defeats the goal, so prefer freeing 80.
Then `npm run proxy:stop` and `npm run proxy` again.

**`502 upstream ... not reachable`.** The app on `:3000` is not running (or not
ready yet after a cold compile). Start it / wait for it, then reload.

**Browser cached the old host.** Hard-reload (`Ctrl+Shift+R`).

**Fallback if you would rather not run Node on port 80:** install [Caddy]
(`winget install Caddy.Caddy`) and run it with a one-line Caddyfile:

```caddyfile
blackeclipse {
    reverse_proxy 127.0.0.1:3000
}
```

Caddy also binds `:80`, needs the same hosts entry, and is a heavier dependency —
the Node script exists so this repo needs no extra install.

## 6. Validation results

Recorded when this setup was added (against a **live Next.js 15.5.18 dev server**),
except where a step needs your hands on the Windows box:

| Check | Result |
|---|---|
| `blackeclipse` → `127.0.0.1` | **Verified on this machine** — the entry was added (was absent before) and `ping blackeclipse` now returns `127.0.0.1`. Reproduce with `npm run setup:hostname`. |
| Proxy listens on port 80, loopback only | **Verified** — `127.0.0.1:80` LISTENING; bound with **no admin**. |
| Default launcher (`npm run dev`) shows only `blackeclipse` | **Verified live** — the launcher starts app + proxy together; its banner and Next's own `Local:`/`Network:` lines read `http://blackeclipse` (no `:3000`). |
| Default launcher serves `http://blackeclipse` | **Verified live** — `curl http://blackeclipse/` → `200` (after the documented cold-compile; `Ready` → route compiled → `200`). |
| `http://blackeclipse` reaches Next.js | **Verified live** — homepage `200` (58 KB HTML), `/api/news` `200` (JSON). |
| Host + forwarding headers | **Verified live** — upstream saw `Host: blackeclipse`; `X-Forwarded-Host/Proto/For` present; path + query intact. |
| Same-origin API mutation through the hostname | **Verified live** — `POST /api/settings` from `Origin: http://blackeclipse` → `200`. |
| CSRF still blocked | **Verified live** — `POST` from `Origin: https://evil.example` → `403`. |
| `http://localhost:3000` still works | **Verified live** — direct `POST` to `:3000` → `200`. |
| WebSocket / HMR through the hostname | **Verified live** — `/_next/webpack-hmr` completed the `101 Switching Protocols` handshake via `http://blackeclipse`. |
| Dev log cross-origin warnings | **Verified** — none after requests through the hostname. |
| Proxy is local-only | **Verified** — binds `127.0.0.1` only (never `0.0.0.0`). |
| `npm run setup:tls` idempotent + non-blocking | **Verified on this machine** — created a cert (thumbprint `3E28F384…`) and added it to `Cert:\CurrentUser\Root` via the .NET store API (the `Import-Certificate` cmdlet hung on the Windows trust dialog; the script no longer uses it). Re-run reports "already configured / already trusted". |
| `https://blackeclipse` is a secure context | **Verified live (headless Chromium)** — `200`, `window.isSecureContext === true`, `typeof window.Notification === "function"` (was `undefined` over plain http). |
| `http://blackeclipse` redirects to https | **Verified live** — `curl http://blackeclipse/` → `301` `Location: https://blackeclipse/`. |
| HTTPS proxy listens on `127.0.0.1:443` | **Verified live** — `[proxy] listening on https://blackeclipse (127.0.0.1:443)`; TLS handshake completed. |

See also: [`QUICKSTART.md`](./QUICKSTART.md), [`DEPLOYMENT.md`](./DEPLOYMENT.md).
