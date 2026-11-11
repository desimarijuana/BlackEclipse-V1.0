---
title: Desktop Cross-Platform Plan
status: Proposed
last-verified: 2026-11-11
---

# Cross-platform plan

**Goal:** ship the desktop app on **Windows, macOS and Linux** from one codebase,
without forking the application or rewriting the UI.

**Reality check up front:** the *application* is already portable — it is a Next
server plus a Python harness, both cross-platform. What is Windows-bound is the
**shell, the bundled runtimes, and the installer**. That is a few hundred lines of
Rust and some packaging scripts, not a rewrite.

---

## 1. What is already portable (measured 2026-11-11)

| Layer | Portable? | Evidence |
| --- | --- | --- |
| Next.js application | **yes** | plain Node; no OS calls in the server |
| Python harness | **almost** | only 5 Windows imports in the whole tree: `msvcrt` ×2, `win32` ×2, `MetaTrader5` ×1 |
| Tauri 2 shell | **framework yes, code no** | 6 Windows-only call sites, listed in §2 |
| Shared UI | **yes** | 468k lines of React, no OS coupling |
| Optional packs | **no** | wheels are per-platform (see §4) |

## 2. The six Windows-only spots in the shell

| # | Where | Windows call | Replacement |
| --- | --- | --- | --- |
| 1 | `kill_tree` | `taskkill /PID /T /F` | `#[cfg]`: taskkill on Windows; `libc::kill(-pgid, SIGKILL)` on Unix, or the `sysinfo` crate for all three |
| 2 | `message_box` | `MessageBoxW` (user32) | `tauri-plugin-dialog` — cross-platform, smaller than a Win32 shim |
| 3 | `webview2_version` | registry read | `#[cfg(windows)]` only. macOS uses WKWebView, Linux WebKitGTK — both OS-provided, nothing to detect |
| 4 | `find_node` | `%ProgramFiles%\nodejs` | bundled runtime is always used in a packaged install; the PATH fallback is dev-only |
| 5 | `creation_flags(CREATE_NO_WINDOW)` | Win32 flag | already `#[cfg(windows)]`; Unix needs no equivalent |
| 6 | data dir | `%LOCALAPPDATA%\BlackEclipse\data` | `app.path().app_data_dir()` → `~/Library/Application Support/…`, `~/.local/share/…` |

**Nothing else in the shell is OS-specific.** Tray, single-instance, keep-warm,
window bounds, the crash panel and the boot screen are already cross-platform.

## 3. Bundled runtimes, per platform

| Runtime | Windows today | macOS / Linux needed |
| --- | --- | --- |
| Node | `node.exe` copied from the build machine | download the platform binary in `desktop-package.js` (`.tar.gz` for darwin/linux) |
| Python | `setup-embedded-python.js` provisions an embedded interpreter | same approach, different archive, or a venv created at package time |
| Vendored `.so`/`.dylib` deps | win32 wheels | per-platform wheels — the pack build must run **on** the target OS |

**Consequence:** the payload cannot be cross-built. Each platform's installer must
be produced on that platform (or in a matching CI runner).

## 4. Optional packs are per-platform

`playwright`, `scipy`, `xgboost`, `pymupdf`, `winsdk` all ship compiled wheels.
The pack archives must be built per target triple:

```
packs/darwin-arm64/ml.zip
packs/linux-x64/ml.zip
packs/win32-x64/ml.zip
```

`manifest.json` gains a `target` field; the downloader requests the matching one.

**Windows-only pack:** `computer` (`winsdk`). On macOS it would need
`pyobjc`/Accessibility APIs; on Linux, AT-SPI. Ship it **Windows-only** and mark
the feature unavailable elsewhere — do not pretend.

## 5. Packaging and distribution

| Platform | Artifact | Signing | Cost |
| --- | --- | --- | --- |
| Windows | NSIS `.exe` (done) | none (accepted) | $0 |
| **Linux** | `.deb` + `.AppImage` | none needed | **$0** |
| **macOS** | `.dmg` (arm64 + x64) | ad-hoc for dev; **notarisation for users** | **$99/yr** Apple Developer |

**macOS warning, plainly:** without an Apple Developer account, a downloaded `.dmg`
is blocked by Gatekeeper with "cannot be opened because the developer cannot be
verified". Users must right-click → Open, or `xattr -dr com.apple.quarantine`.
That is a much harsher wall than Windows' SmartScreen. There is no free
equivalent of "run anyway" on a modern Mac.

## 6. Phases

| Phase | Work | Outcome | Effort |
| --- | --- | --- | --- |
| **C0** | Replace the 6 Windows call sites; add `#[cfg]` guards; move data dir to `app_data_dir()` | shell compiles for all three targets | 1 session |
| **C1** | **Linux first** — `.deb` + AppImage, per-platform Node, venv-based Python | first non-Windows build; free, no signing | 2–3 sessions |
| **C2** | macOS arm64 `.dmg`, ad-hoc signed for local use | Mac users can run it (right-click to open) | 2–3 sessions |
| **C3** | Per-platform pack builds + `target` in the manifest | packs work everywhere they make sense | 1–2 sessions |
| **C4** | CI matrix (`windows-latest`, `ubuntu-latest`, `macos-latest`) building all artifacts | one tag → all releases | 1–2 sessions |
| **C5** | Apple Developer + notarisation | Mac download opens normally | $99/yr + 1 session |

**Why Linux first:** it costs nothing, it has no gatekeeper, and it is the fastest
way to prove the shell port is correct before paying Apple.

## 7. Feature availability matrix (honest)

| Feature | Windows | macOS | Linux |
| --- | --- | --- | --- |
| App, chat, agents, charts | ✅ | ✅ | ✅ |
| OS notifications | ✅ | ✅ | ✅ (libnotify) |
| Tray | ✅ | ✅ (menu bar) | ✅ (needs libappindicator) |
| Browser automation pack | ✅ | ✅ | ✅ |
| ML / documents / charts packs | ✅ | ✅ | ✅ |
| Computer control (OCR, UI automation) | ✅ | ❌ | ❌ |
| **MT5 integration** | ✅ | ❌ | ❌ |

MT5 and computer-control are **permanently Windows-only** — MetaTrader does not
exist on macOS/Linux. Everything else is portable.

## 8. Risks

| Risk | Handling |
| --- | --- |
| WebKitGTK (Linux) is older than Chromium | test the heavy screens (Monaco, ECharts, WebGL) early in C1; fall back to `softwarerendering` if needed |
| macOS notarisation fee | accepted cost, deferred to C5; C2 ships an unsigned build with instructions |
| Per-platform Python wheels missing for a package | the pack build fails loudly per target; drop that pack for that OS rather than ship a broken import |
| Three installers to test | one acceptance checklist (install → run → first-run DB → uninstall keeps data) per platform |
| Divergence over time | CI builds all three from the same tag; a platform that stops building is visible immediately |

## 9. Decisions needed

1. **Order:** Linux first (recommended, free) or macOS first (needs $99)?
2. **macOS without notarisation** — acceptable for v1 with right-click instructions, or wait until C5?
3. **Computer-control pack** — Windows-only forever, or invest in `pyobjc`/AT-SPI later?
4. **Universal macOS build** (arm64 + x64 in one `.dmg`, ~2× size) or separate downloads?

## 10. What does **not** change

- The application code, the UI, the harness logic, the data model
- The Windows release already shipped; C0–C1 must not regress it
- The browser front door stays cross-platform at zero cost, as it is today
