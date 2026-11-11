# `desktop/` — native shell

A Tauri 2 window around the existing application. **Nothing here is required for
the browser front door.** Deleting this folder and reverting the five
`desktop:*` script lines in `package.json` restores the previous state exactly.

Plan and rationale: `docs/desktop-app-plan.md`.

## Layout

| Path | What it is |
| --- | --- |
| `src-tauri/src/main.rs` | Window, tray, prefs, and lifecycle of the one child process |
| `src-tauri/tauri.conf.json` | Bundle/app config; `frontendDist` is `../ui` |
| `src-tauri/capabilities/default.json` | Grants the splash page core window/event access only |
| `src-tauri/icons/` | Copies of `public/branding` so the binary carries the app icon |
| `ui/index.html` | The boot screen, embedded into the binary at compile time |
| `../scripts/desktop-server.js` | Server bootstrap; prints `@@BE:*@@` markers the shell reads |

## How it boots

```
window shows instantly (bundled splash, no network)
  └─ scripts/desktop-server.js
      ├─ server already there?  → verify IDENTITY (/api/updates)
      │     ├─ ours      → @@BE:ATTACH@@   (never owned, never killed)
      │     ├─ next-shaped → @@BE:ATTACH@@ (unverified, warns)
      │     └─ anything else → @@BE:CONFLICT@@ (stop, explain, kill nothing)
      └─ nothing there
            ├─ canonical BE_DATA_DIR resolved (absolute)
            ├─ start lock acquired (pid + TTL)
            ├─ next start -H 127.0.0.1 -p 3100
            └─ @@BE:READY@@ → window navigates to
                              http://127.0.0.1:3100/
```

`127.0.0.1` is a secure context, so notifications, camera and microphone work
without the TLS reverse proxy the browser path uses for `https://blackeclipse`.

## Window chrome

The window is **frameless** (`decorations(false)`): the app's
`DesktopTabBar` (`src/components/layout/desktop-tab-bar.tsx`) is the title bar.
It shows the open top-level pages as tabs, remembers them in
`localStorage`, and provides the drag region plus minimize/maximize/close. The
remote app origin reaches Rust through `be-window` events (the same
events-not-commands rule as notifications); the bundled splash invokes
`desktop_window_action` directly. In a browser the bar renders nothing.

## Commands
```
npm run desktop:dev        # cargo run (debug, keeps a console for logs)
npm run desktop:check      # cargo check only
npm run desktop:build      # cargo build --release
npm run desktop:run        # launch the release binary
npm run desktop:server     # the bootstrap alone, in a terminal
npm run desktop:selftest   # prove the OS-toast path end to end (fires a real toast)
npm run desktop:payload    # standalone Next payload -> .next-desktop
npm run desktop:package    # assemble dist/BlackEclipse (app + bundled Node + shell)
npm run desktop:installer  # NSIS installer + SHA256SUMS + winget manifests
```

Full release chain:

```
npm run desktop:payload && npm run desktop:build && npm run desktop:package && npm run desktop:installer
```

CI runs exactly this in `.github/workflows/desktop-release.yml` on a `v*` tag.

## Install layout

```
%LOCALAPPDATA%\Programs\BlackEclipse\     app (per-user, no admin, no prerequisites)
  Black Eclipse.exe
  runtime\node.exe
  app\            server.js, .next-desktop\, node_modules\, python\, scripts\, config\
  Uninstall.exe

%LOCALAPPDATA%\BlackEclipse\data\         user data — SURVIVES uninstall
  jdds.db  harness-auth.secret  ...
```

Per-user is not a style choice: the app resolves `python/harness` and its
`.black-eclipse` locks from `process.cwd()`, so the install directory must be
writable. Program Files is not.

## Distribution

`npm run desktop:installer` writes:

| Output | Purpose |
| --- | --- |
| `dist/BlackEclipse-Setup-<version>.exe` | NSIS installer, per-user, ~450–500 MB |
| `dist/SHA256SUMS.txt` | Checksum, published beside the asset |
| `dist/winget/BlackEclipse.BlackEclipse/<version>/*.yaml` | Three winget manifests with the real hash |

**Unsigned.** The first run shows "Windows protected your PC"; users verify the
checksum and choose *More info → Run anyway*. `winget install
BlackEclipse.BlackEclipse` strips the Mark-of-the-Web and usually skips that wall
entirely. `SHA256SUMS.txt` is published beside every asset.

## Updating

- **Check:** the app's existing signed update manifest + in-app banner
  (`config/updates.json`, `src/app/api/updates/route.ts`). No shell work needed.
- **Apply:** `winget upgrade BlackEclipse.BlackEclipse`, or run the newer
  installer. Both preserve `%LOCALAPPDATA%\BlackEclipse\data`.
- **Not implemented:** silent background self-replacement. That needs the release
  signing key wired into the shell, and it must never run migrations unattended.


## Notifications: why events, not commands

The window loads `http://127.0.0.1:3100`, which is a **remote origin** to Tauri's
ACL. Two consequences, both learned the hard way:

1. Without `remote.urls` in `capabilities/default.json`, IPC is denied entirely and
   `window.__TAURI__` is absent in the app.
2. Even with it, **app-defined commands are denied** to a remote origin —
   `invoke('desktop_notify')` fails with *"not allowed. Plugin not found"*. Core
   commands (events) **are** permitted.

So the injected `Notification` shim in `src-tauri/src/main.rs` emits
`be-notify` / `be-shortcut`, and Rust listens for both. That keeps
`src/lib/alerts/browser-notifier.ts` completely unchanged.

`npm run desktop:selftest` reports:

```
hn:1~perm:granted~sec:1~tauri:1~ctor:NativeNotification~shimcall:dispatched~direct:ok
```

## Guarantees

- **Identity before trust.** An existing listener is identified via
  `/api/updates` (`repository` + `currentVersion`) before the window attaches.
  Liveness alone is not treated as identity.
- **A usable build, not just an identity.** Before attaching, the bootstrap
  fetches an asset the served HTML actually references. A leftover server whose
  build directory was deleted still answers `/` and identifies itself, but every
  `/_next/static/*` request fails — the window would render without styles or
  working navigation. That state is reported as a conflict with instructions,
  and the server is still never killed.
- **A redirect is not a foreign process.** The browser-path server answers `/`
  with a 307 to the canonical TLS hostname, so it has no HTML to shape-check.
  The bootstrap skips that check for 3xx and relies on `/api/updates` (API routes
  are never canonical-redirected), letting the desktop attach to a healthy
  `npm start` instance instead of refusing it.
- **Loopback only.** The desktop path spawns
  `next start -H 127.0.0.1`; it deliberately does not use the shared
  `startServer()` helper, which binds every interface.
- **One data directory, by construction.** `BE_DATA_DIR` is resolved to an
  absolute path *before* any service starts and passed explicitly. The same
  variable is read by `src/lib/db.ts`, `python/harness/persistence.py` and
  `python/harness/eclipse_memory/config.py`.
- **Never kills what it did not start.** No `killPort` on this path. The owner
  flag is separate from attachment, and only an owned tree is terminated.
- **One starter at a time.** `.black-eclipse/desktop-server.lock` (pid + TTL)
  serializes concurrent launches; a stale lock is taken over.
- **Never builds at launch.** A missing build produces a readable error.
- **Failure is visible.** A server that dies after readiness swaps the page for
  a failure panel with Reload. A missing WebView2 runtime gets a message box with
  the download link and the browser fallback.
- **Keep-warm is a setting**, in the tray menu, persisted to
  `.black-eclipse/desktop-prefs.json` (window bounds live there too).
- **Logs:** `.black-eclipse/desktop-native.log`, truncated at 8 MB. Read
  byte-wise (lossy), so non-UTF-8 output from Python/Next cannot end the stream.

## Known limits (documented, not hidden)

- Code signing and an installer are not part of this shell yet.
- The app is loaded from the local server, so a stale `.next` build is served
  with a warning rather than rebuilt.
- Playwright/PDF features that expect a browser download are untested inside
  WebView2.
