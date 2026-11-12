---
title: Eclipse Mobile — iOS and Android Compatibility
status: Proposed
last-verified: 2026-11-12
---

# iOS and Android compatibility

This document is the platform contract. It separates what Tauri 2 provides, what
must be verified on a physical device, and what the app must do differently on
each OS.

## 1. Tauri 2 mobile shape

Tauri 2 mobile requires the Rust crate to produce a **library**, not only a binary:

```
mobile/src-tauri/
  Cargo.toml
    [lib]
    name = "eclipse_mobile_lib"
    crate-type = ["staticlib", "cdylib", "rlib"]

  src/lib.rs
    #[cfg_attr(mobile, tauri::mobile_entry_point)]
    pub fn run() { /* builder, plugins, state, commands */ }

  src/main.rs
    fn main() { eclipse_mobile_lib::run() }
```

Initialisation and run commands:

```
npm run tauri android init
npm run tauri ios init          # macOS only
npm run tauri android dev
npm run tauri ios dev           # macOS only
npm run tauri android build
npm run tauri ios build         # macOS only
```

`tauri.conf.json` points `build.frontendDist` at the Vite output (`../dist`). The
WebView loads bundled assets; it is a **local origin**, so the desktop
`remote.urls` capability workaround does not apply and must not be copied.

## 2. Development and CI reality

| Task | Windows 11 | macOS | CI |
| --- | --- | --- | --- |
| Android build + device run | **Yes** (Android Studio + SDK/NDK + Rust targets) | Yes | `ubuntu-latest` or `windows-latest` |
| iOS build + device run | **No** | **Yes** (Xcode, CocoaPods) | `macos-latest` |
| iOS simulator | No | Yes | `macos-latest` |
| Store upload | Android yes | iOS yes | Manual, secrets-gated |

Consequences:

- The current machine can build and test **Android** end to end.
- iOS must be exercised through a Mac or the existing `macos-latest` CI pattern
  already used by `docs/desktop-cross-platform-plan.md`.
- **Do not defer iOS to the end.** Phase 2 runs the proof of concept on a real
  iPhone via CI/TestFlight. If iOS fails, the architecture changes while it is
  still cheap.

## 3. WebView differences that matter

| Concern | iOS WKWebView | Android WebView | Rule for this app |
| --- | --- | --- | --- |
| Engine | Safari/WebKit, tied to OS | Chromium, updatable but fragmented | Test both; no Chromium-only CSS |
| `backdrop-filter` | Supported, can be expensive | Supported on modern versions | Use the "glass off" fallback; never blur a scrolling transcript |
| `position: fixed` + keyboard | Keyboard overlays; layout viewport does not resize | Usually resizes with `adjustResize` | Use `visualViewport` and anchor the composer to it |
| Safe areas | Notch/Dynamic Island/home indicator | Gesture nav/cutouts | Use `env(safe-area-inset-*)` on every edge |
| Viewport height | `100vh` is unreliable | Same | Use `100dvh` with a `100vh` fallback |
| Text zoom | Automatic text autosizing | Font boosting | Set `-webkit-text-size-adjust: 100%`; inputs ≥ 16 px |
| Momentum scroll | Native | Native | `-webkit-overflow-scrolling: touch`; avoid nested scroll traps |
| Memory pressure | **WebView can be recreated/killed** | Process may be killed | State lives in SQLite; UI rehydrates on mount |
| Pull-to-refresh | Browser gesture can interfere | Same | `overscroll-behavior: none` inside the chat scroller |
| File input | Needs usage strings + picker | Needs permissions | Use `tauri-plugin-dialog`, copy into sandbox |
| `localStorage` | May be evicted | May be cleared | Never the source of truth |

### Mandatory UI behaviours

1. **Composer above the keyboard.** Bind to `window.visualViewport` `resize`/`scroll`;
   compute `bottom = innerHeight - visualViewport.height - offsetTop`. Do not rely
   on `position: fixed; bottom: 0`.
2. **Safe areas.** Shell padding: `padding-top: env(safe-area-inset-top)`, bottom
   inset on the composer and sheets. The chat scroller gets the remaining height.
3. **No nested scroll.** One vertical scroller for the transcript; the composer and
   header are outside it. Sheets have their own scroller.
4. **Tap targets ≥ 44 px** (iOS HIG) and **48 dp** (Material).
5. **Reduced motion.** `prefers-reduced-motion` disables the ghost animation and
   message fade, exactly as `globals.css` already does on desktop.
6. **No hover-only affordances.** Every action reachable by tap; long-press is
   additive, never the only path.
7. **Back behaviour.** Android hardware back closes a sheet, then returns to the
   bot list. iOS uses an in-app back button and the edge swipe gesture.

## 4. Plugin and native capability matrix

Official plugin pages were checked on 2026-11-12; all listed plugins require Rust
≥ 1.90 and advertise Android/iOS. "Device test" is the remaining gate.

| Capability | Mechanism | Android | iOS | Device test |
| --- | --- | --- | --- | --- |
| Local notification | `tauri-plugin-notification` | Listed | Listed | Required |
| Notification actions | same plugin (mobile-only API) | Listed | Listed | Optional v1 |
| Biometric gate | `tauri-plugin-biometric` | Listed | Listed (`NSFaceIDUsageDescription`) | Required |
| Haptics | `tauri-plugin-haptics` | Listed | Listed | Optional |
| File picker | `tauri-plugin-dialog` | Listed | Listed | Required |
| App-sandbox files | Rust `std::fs` + path API | Yes | Yes | Required |
| Deep link (custom scheme) | `tauri-plugin-deep-link` | Listed | Listed | Phase 7 |
| Preferences | `tauri-plugin-store` | Listed | Listed | Yes |
| Keychain / Keystore | **custom plugin** (see below) | Kotlin | Swift | Required |
| Background refresh | **custom bridge** | WorkManager | BGTaskScheduler | Required |
| Remote push | APNs / FCM + server | — | — | **Out of scope v1** |
| Tray / single instance / vibrancy | desktop plugins | — | — | Do not add |

### Secure storage plugin

No official Tauri plugin exposes the OS keychain directly. Two acceptable designs:

**A. Custom plugin (recommended).**
A small `mobile/plugins/secure-store` crate with:

- iOS: `SecItemAdd` / `SecItemCopyMatching` / `SecItemDelete` for
  `kSecClassGenericPassword`, accessibility
  `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.
- Android: generate an AES-256-GCM key in the Android Keystore
  (`setUserAuthenticationRequired(false)` for background reads, or `true` if all
  reads are user-initiated), encrypt the secret blob, store ciphertext in
  `SharedPreferences`/app files.
- Rust API: `put(key, bytes)`, `get(key) -> Option<Vec<u8>>`, `delete(key)`,
  `available() -> bool`.

**B. `tauri-plugin-stronghold` (fallback).**
Rust-side encrypted vault; the vault password is itself stored in the OS keychain
(which still needs a small native call) or derived from a user passphrase on every
launch. Heavier and slower to unlock, but avoids writing two native bridges.

The **hard invariant** is the same either way: provider keys are readable only by
Rust, never serialized into commands, events, logs, crash reports or the WebView.

### Background bridge

- Android: a `CoroutineWorker` scheduled with `WorkManager`; it calls into Rust to
  run due schedules. A notification is posted at the intended time regardless of
  whether execution is allowed.
- iOS: register `BGAppRefreshTask` and `BGProcessingTask` identifiers in
  `Info.plist` (`UIBackgroundModes` = `fetch`, `processing`); on launch, submit a
  request for the next due schedule. The handler gets a bounded window and must
  call `setTaskCompleted`.
- Both: on every foreground, run catch-up and reconcile interrupted runs.

## 5. Platform lifecycle differences

| Event | iOS | Android | App response |
| --- | --- | --- | --- |
| Background | App suspends quickly; network/SSE stops | Process usually stays, may be killed | Checkpoint the run; do not assume the stream lives |
| Return to foreground | `scenePhase` active | `onResume` | Reconcile runs, replay events after `lastSeq`, refresh schedules |
| WebView recreation | Possible under memory pressure | Possible | React mounts from SQLite; no in-memory-only state |
| Force quit | No background relaunch | WorkManager cancelled until next open | Show "missed while away" on next open |
| Low power mode | Background work throttled | Doze/battery saver | Skip non-urgent catch-up; show the state |
| Time change / timezone | Recompute on resume | Same | Store the IANA zone; recompute `next_run_at` |

## 6. iOS-specific risks and mitigations

| Risk | Mitigation |
| --- | --- |
| WKWebView killed during a long stream | Run in Rust; persist deltas; resume by seq; never re-run automatically |
| Keyboard covers the composer | `visualViewport` binding; scroll the focused input into view |
| Safe-area regressions | Test on a notch device and an SE; use env() tokens, no hard-coded 0 |
| Face ID prompt loops | Gate only on explicit actions and app unlock setting; fall back to device passcode |
| ATS blocks plain HTTP | HTTPS only; no LAN hosts; no `NSAllowsArbitraryLoads` |
| Background task never fires in testing | Use Xcode debug launch + `_simulateLaunchForTaskWithIdentifier`; document that production timing is system-controlled |
| App Review 4.2 (thin wrapper) | Native capabilities (offline DB, notifications, biometrics, file attachments) and a real mobile IA; see `risks-and-decisions.md` |
| App Review 2.5.2 (executable code) | No downloaded code, no interpreter, no shell; only data + fixed tools |
| Keychain access after reboot before unlock | Use `AfterFirstUnlockThisDeviceOnly`; the app must handle `nil` keys gracefully |
| Large attachments in JS | Stream files in Rust; never base64 a PDF through the bridge |

## 7. Android-specific risks and mitigations

| Risk | Mitigation |
| --- | --- |
| WebView fragmentation | Avoid bleeding-edge CSS; feature-detect `backdrop-filter`; test on Android 12 and current |
| Notification permission (API 33+) | Request in context, explain before the system prompt, degrade silently |
| Battery optimisation kills background work | Use WorkManager, not a foreground service; show "last ran" and allow manual run |
| Force-stop cancels schedules | Re-register on every app open; state that schedules resume when the app is opened |
| Scoped storage | Use the app sandbox + Storage Access Framework via the dialog plugin; no broad permissions |
| Cleartext | `usesCleartextTraffic=false`; HTTPS only |
| Keystore key invalidated | Handle decrypt failure by asking the user to re-enter the key; never crash |
| Play target API level | Check the current requirement at release; it changes annually |

## 8. Physical-device proof of concept (gate before UI build-out)

The PoC is deliberately small. It must run on a **real iPhone** and a **real
Android phone**, not only simulators.

### Acceptance checklist

| # | Step | Pass condition |
| --- | --- | --- |
| 1 | Launch the app from a cold start | First screen in ≤ 2 s on a mid-range device; no blank WebView |
| 2 | Create one bot | Bot persists after force-quit and relaunch |
| 3 | Configure an API key | Key is accepted; the key string never appears in JS (`window` inspection), logs or crash output |
| 4 | Send a message | First token appears in ≤ 2 s after provider starts; text streams visibly |
| 5 | Receive streamed output | Markdown renders while streaming; no layout jump at completion |
| 6 | Persist the conversation | Kill the app mid-stream; relaunch; the partial reply is present and the run shows `interrupted` |
| 7 | Background the app during a run | Return: run is either continued or honestly interrupted; no duplicate assistant message |
| 8 | Recover run state | `get_run_events(run_id, after_seq)` reconstructs the transcript exactly once |
| 9 | Keyboard + scrolling | Composer stays above the keyboard; long thread scrolls at 60 fps; no nested scroll trap |
| 10 | Notification | A local notification fires; tapping it opens the right bot |
| 11 | Biometric gate (if enabled) | Face ID / fingerprint unlocks; cancel keeps the app locked |
| 12 | Attachment | Pick a file, attach, restart the app, and the attachment is still readable |

### Measured targets (record, do not invent)

| Metric | Target |
| --- | --- |
| Cold start to interactive | ≤ 2.0 s |
| JS heap after 200 messages | ≤ 120 MB |
| Rust RSS during a stream | ≤ 150 MB |
| Token-to-screen latency overhead | ≤ 100 ms p95 over provider latency |
| SQLite write of a 2 KB message | ≤ 5 ms p95 |
| Battery: 30 min text chat | ≤ 5% on a 4,000 mAh device |

If a target misses, record the device and number; do not silently relax it.

## 9. Device matrix

| Class | Example | Why |
| --- | --- | --- |
| iPhone small/low RAM | iPhone SE (3rd gen) | Keyboard, safe area, memory pressure |
| iPhone current | iPhone 15/16 class | Dynamic Island, Face ID, current iOS |
| Android mid-range | Pixel 6a / Samsung A5x | Realistic performance and WebView |
| Android current flagship | Pixel 8/9 class | Feature ceiling |
| Tablet (optional) | iPad / Android tablet | Layout at width ≥ 768 |

OS coverage: current and previous major iOS; Android 12 through current.

## 10. Store-readiness notes specific to mobile

- **Apple 2.5.2**: the app must be self-contained. Fixed tools are allowed; no
  shell, no downloaded executable code, no interpreter. Model output is data.
- **Apple 4.2**: the app must not look like a repackaged website. Native
  navigation, offline history, notifications, biometrics, file attachments and a
  focused Bot Mode IA are the answer — not a token camera button.
- **BYOK**: acceptable, but the app must explain that the user pays the provider
  and that the key stays on the device. Do not ship a shared key.
- **Privacy**: a model provider receives the conversation; the App Privacy label
  and the in-app disclosure must say so. No analytics by default.
- **Financial content**: the finance bot pack must keep the desktop's honest
  framing (citations, `UNAVAILABLE`, not advice) and carry a visible disclaimer.
- **Google Play**: Data safety form, notification permission rationale, no
  `SCHEDULE_EXACT_ALARM` (not needed), target API level at release.

Detailed rationale: `risks-and-decisions.md`.
