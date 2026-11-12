---
title: Eclipse Mobile — Dependency Evaluation
status: Proposed
last-verified: 2026-11-12
---

# Dependency evaluation

The goal is the **smallest reliable stack** that satisfies the runtime contract:
durable runs, streaming, tool calls, bound approvals, cancellation, SQLite, secure
key custody, and mobile compilation.

Nothing here is added to the repository yet. Every uncertain mobile claim is marked
**unverified** and has a Phase 0 spike in `implementation-roadmap.md`.

## 1. Agent runtime: Rig vs custom

### What Rig is (checked 2026-11-12)

- `rig` 0.46.0, MIT, pre-1.0 with breaking releases (`README`, `MIGRATING.md`).
- 20+ providers under one interface; agents with tools, streaming, typed hooks;
  conversation memory (windows/compaction); `rig-cassette` record/replay;
  `rig-sqlite` vector/session store; WASM support for core + agent runtime.
- Explicit target claims cover WASM; **no iOS/Android statement** was found in the
  README, FAQ or installation docs. Mobile compilation is therefore **unverified**.
- The `rig` coding agent is a Bevy/TUI application and runs on Linux/macOS; that is
  not the library.

### Criteria

| Criterion | Weight | Rig | Custom Rust runtime |
| --- | ---: | --- | --- |
| Mobile (iOS/Android) compile evidence | 5 | **Unverified** | Controlled: tokio + reqwest/rustls + rusqlite are widely used on both |
| Durable run + event log + resume by seq | 5 | Partial (`AgentRun` serializable; not our event log) | **Designed for it** |
| Approval bound to exact action digest | 5 | Not provided | **Owned** |
| Streaming text + tool-call deltas | 4 | Strong | Straightforward SSE/JSON work |
| Provider coverage | 3 | **20+** | 4 in v1 (OpenAI, Anthropic, Gemini, OpenRouter) |
| Dependency footprint / binary size | 3 | Large facade, feature-gated | Small, explicit |
| API stability | 3 | Pre-1.0, breaking | We own it; internal churn is cheap |
| Maintenance | 2 | Active, funded community | Ours |
| Record/replay + mock models | 2 | **`rig-cassette`** | Golden fixtures + a local mock server |
| Error/retry/cancellation control | 4 | Generic | Exact per provider |

### Decision

**Build a custom provider + run loop for v1. Do not depend on Rig.**

Reasons:

1. The hard problems in this app are **durability, approvals and mobile lifecycle**,
   not provider abstraction. Rig does not solve the first two, and its mobile
   support is unproven.
2. Four providers are enough for v1. Each is a bounded adapter (< 250 lines) with
   its own SSE quirks; owning them gives precise control over tool-call deltas,
   usage, retry classes and cancellation.
3. A pre-1.0 dependency with breaking releases is a poor fit for an app whose data
   model must stay stable across store releases.

**Revisit triggers** (any one):
- more than six providers are required;
- embeddings/RAG becomes a first-class mobile feature;
- `rig-core` passes the Phase 0 mobile spike on both platforms *and* the team wants
  its provider breadth;
- the custom adapter surface exceeds ~1,500 lines of provider-specific code.

If adopted later, it goes **behind the `Provider` trait**, never in the run loop.
`rig-cassette` is worth borrowing as a *pattern*: record real provider streams as
fixtures and replay them in CI.

### Rejected alternatives

| Option | Why rejected |
| --- | --- |
| `async-openai` | OpenAI only; tool-call streaming and error mapping still need wrapping |
| `llm` crate | Provider coverage is useful but the abstraction is text-first; tool loops and cancellation need custom code anyway |
| `kalosm` | Local-model oriented; irrelevant and large |
| LangChain-style graph in Rust | No need for a graph runtime; a bounded tool loop is simpler and testable |
| A Node agent runtime | Same sidecar/App Store blocker as the current app |

## 2. Core runtime crates

| Concern | Choice | Why | Mobile risk |
| --- | --- | --- | --- |
| Async runtime | `tokio` (`rt-multi-thread`, `time`, `sync`, `macros`) | Tauri already runs on tokio; mature on both platforms | Low |
| HTTP + SSE | `reqwest` with `rustls-tls`, `stream` | Avoids OpenSSL cross-compilation; streaming bytes are enough to parse SSE | Low–medium; verify TLS roots on device |
| JSON | `serde`, `serde_json` | Required by Tauri anyway | Low |
| Errors | `thiserror` for typed errors; no `anyhow` in library code | Error classes are part of the contract and drive retry/UI | Low |
| IDs/time | `uuid` v4/v7, `time` (or `chrono`) | Sortable run/message ids; RFC 3339 timestamps | Low |
| Hashing | `sha2` | Approval argument digests | Low |
| Files | `std::fs` + Tauri path API | App-sandbox only | Low |
| Logging | `tracing` + `tracing-subscriber`, redacted | Structured logs without secrets | Low |
| Random | `getrandom`/`rand` | Idempotency keys and jitter | Low |

Do **not** add: `openssl`, `libgit2`, `portaudio`, `whisper`, `playwright`, `winsdk`.

## 3. Database

| Option | Verdict | Notes |
| --- | --- | --- |
| **`rusqlite` (`bundled`)** | **Chosen** | SQLite compiled in; no system dependency; Rust owns every query; FTS5 available; works on iOS/Android. |
| `rusqlite` + `bundled-sqlcipher` | **Chosen for encryption spike** | SQLCipher build feature; verify compile and key handling on both targets. |
| `sqlx` | Rejected for v1 | Async + compile-time macros add build complexity; the runtime already serializes DB work on a dedicated thread. Reconsider only if a server target appears. |
| `tauri-plugin-sql` | Rejected | It exposes `execute`/`select` to the WebView. The UI must never hold SQL or the schema. |
| `libsql`/Turso | Rejected | Network/replica features are not needed and increase size. |
| `redb`/`sled` | Rejected | No SQL, no FTS5, no relational integrity. |

Encryption policy:

1. Try `bundled-sqlcipher` in Phase 0.
2. Key is 32 random bytes generated in Rust and stored in the OS keychain (see §4).
3. If the SQLCipher build fails on a target, **ship unencrypted** with iOS Data
   Protection / Android app-sandbox protections and say so in the security model.
   Never claim encryption that is not active.

## 4. Secrets

| Option | Verdict | Notes |
| --- | --- | --- |
| **OS Keychain / Keystore via a small custom plugin** | **Chosen** | iOS `kSecClassGenericPassword`; Android Keystore-wrapped AES-GCM blob. Keys never enter JS. ~150–250 lines per platform. |
| `tauri-plugin-stronghold` | Fallback | Cross-platform and Rust-side, but password-based and adds an encrypted vault + argon2 cost. If used, the vault password is itself a keychain entry. |
| `keyring` crate | Investigate | Desktop-first; iOS/Android support unverified. |
| `tauri-plugin-store` | Rejected for secrets | Plain JSON; fine for preferences, never for keys. |
| Key in SQLite | Forbidden | A DB copy or backup leaks it. |

Provider configs in SQLite store only `key_ref` (an opaque identifier), never the
secret.

## 5. Platform plugins

Official plugin pages were checked on 2026-11-12. All listed plugins require Rust
≥ 1.90 and advertise Android/iOS support. "Verified" below means the page lists the
platform; it still needs a device test.

| Capability | Choice | Mobile | Notes |
| --- | --- | --- | --- |
| Local notifications | `tauri-plugin-notification` | Android/iOS listed | Actions API is mobile-only. Remote push is **not** included. |
| Biometrics | `tauri-plugin-biometric` | Android/iOS | iOS needs `NSFaceIDUsageDescription` in `Info.ios.plist`. |
| Haptics | `tauri-plugin-haptics` | Android/iOS | Cheap polish; optional. |
| Deep links | `tauri-plugin-deep-link` | Android/iOS | Universal links need a domain association; v1 can use a custom scheme. |
| File picker / save | `tauri-plugin-dialog` | Android/iOS listed | Copy picked files into the sandbox. |
| File access | `tauri-plugin-fs` | Android/iOS | Scope to the app data dir only. Prefer Rust `std::fs` for internal files. |
| Preferences | `tauri-plugin-store` | Android/iOS | Non-secret settings only. |
| HTTP | `reqwest` in Rust | — | Do not use `tauri-plugin-http`; provider calls belong to the runtime, not JS. |
| SQL | none | — | See §3. |

**Not available / not used:** tray, single-instance, `window-vibrancy`, updater
(store updates instead), global shortcut, positioner, window-state.

## 6. Background scheduling

No official Tauri plugin covers it. The app writes a small native bridge:

| Platform | API | Constraint |
| --- | --- | --- |
| Android | `WorkManager` (`PeriodicWorkRequest`) | Minimum 15 min; Doze may delay; force-stop cancels until the user opens the app |
| iOS | `BGAppRefreshTask` / `BGProcessingTask` | Opportunistic; system decides; force-quit prevents relaunch; no exact time guarantee |

The only honest V1 promise: **local notifications at the scheduled time, execution
when the OS allows or the app opens next**. See `scheduling-limitations.md`.

Rejected: keeping the app alive with an audio session, a foreground service that
pretends to be something else, or a hidden WebSocket. Those are policy violations
and battery abuse.

## 7. Frontend stack

| Concern | Choice | Why |
| --- | --- | --- |
| Framework | React 19 + TypeScript | Same mental model and reusable components |
| Build | Vite | Small, fast, no Next server; Tauri's standard mobile frontend |
| Styling | Tailwind v4 + copied token block | Reuse the visual identity; avoid the 1,988-line app stylesheet |
| State | `zustand` (already a dependency) | Small; mirrors the existing store style |
| Routing | `wouter` + a small back stack | ~2 KB; the app has 5–6 screens, not a web router |
| Markdown | In-house parser + adapted renderer | Already tested, dependency-free, streaming-safe |
| Math | `katex` | Existing renderer; lazy |
| Icons | `@phosphor-icons/react` | Existing icon surface |
| Sheets/dialogs | Custom CSS + a few `@base-ui/react` primitives | Native-feeling bottom sheets; avoid importing the desktop design system wholesale |
| Virtualization | `@tanstack/react-virtual` (if needed) | Long threads; measure before adding |
| Tests | Vitest + Testing Library + happy-dom | Matches repo tooling |

Do **not** add: Monaco, xterm, Mermaid, Plotly, ECharts, `ogl`, Tiptap, `pdfjs-dist`,
`jspdf`, `@xyflow/react`, `react-markdown`, `next/*`.

## 8. Testing and CI tools

| Concern | Choice |
| --- | --- |
| Rust unit/integration | `cargo test`; `tempfile` for DB; `tokio::test` |
| HTTP fixtures | A local `axum` mock provider or `wiremock`; recorded SSE fixtures |
| Snapshot tests | `insta` (event payloads, prompt assembly) |
| TS tests | Vitest + `@testing-library/react` + `happy-dom` |
| Contract conformance | Ajv (or `jsonschema` for Rust) against the JSON Schemas |
| Lint | `cargo clippy -D warnings`, `cargo fmt --check`, ESLint, `tsc --noEmit` |
| Supply chain | `cargo audit`, `cargo deny` (licences + advisories), `npm audit` |
| Android CI | `ubuntu-latest` (or Windows) + Android SDK/NDK + `tauri android build` |
| iOS CI | `macos-latest` + Xcode + `tauri ios build` |
| Release signing | Manual, secrets-gated; never in PR builds |

## 9. Version and licence policy

- Pin the Rust toolchain with `rust-toolchain.toml`; Tauri's plugin docs require
  **Rust 1.90+** at the time of writing, so use a recent stable.
- Commit `Cargo.lock` and `package-lock.json` for the app.
- Pin exact versions in `Cargo.toml` for provider/DB crates that affect wire or
  storage formats; allow patch updates elsewhere.
- `cargo deny` must allow: MIT, Apache-2.0, BSD-2/3, ISC, MPL-2.0. Reject
  copyleft-only licences and unknown licences.
- Every new dependency needs a one-line justification in the PR, per `AGENTS.md`.

## 10. Phase 0 dependency spikes (must pass before Phase 1)

| Spike | Pass condition |
| --- | --- |
| `tauri android init` + Vite app on a device | App installs and renders a page |
| `tauri ios init` on macOS + a device | App installs and renders a page |
| `reqwest` + `rustls` streaming SSE to OpenAI | Deltas arrive incrementally on both devices |
| `rusqlite` bundled + FTS5 | Create/insert/query FTS on both devices |
| `rusqlite` + SQLCipher | Open an encrypted DB with a 32-byte key on both devices |
| Keychain plugin | Write/read/delete a 32-byte secret; key never exposed to JS |
| Notification plugin | Permission prompt + a local notification on both devices |
| Background task bridge | A scheduled task/notification fires under the documented limits |
| App size | Release build under 40 MB before assets |

If a spike fails, the decision record must be amended **before** the dependent
phase starts. A failed SQLCipher spike does not block the app; a failed streaming
or SQLite spike does.
