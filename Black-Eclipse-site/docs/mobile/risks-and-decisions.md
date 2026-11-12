---
title: Eclipse Mobile — Risks and Decisions
status: Proposed
last-verified: 2026-11-12
---

# Risks and decisions

These are **proposed** decisions for review. They are not yet ADRs in
`docs/DECISIONS.md`; if implementation is approved, the accepted ones move to
`skills/ARCHITECT.md` first and mirror into `DECISIONS.md` with the next free
`ADR-NNN`, per `AGENTS.md`.

## 1. Decision record

### D1 — Mobile is a second product, not a build target

**Decision:** a new `mobile/` project with its own `package.json`, `src-tauri`, UI
and release pipeline. `Black-Eclipse-site/src`, `desktop/` and `python/` are not
modified.
**Why:** the desktop runtime is Node + Python + loopback; none of it exists on a
phone. A "mobile target" of the existing app would be a lie until every layer is
replaced.
**Consequence:** duplicated UI patterns are accepted; shared logic is extracted
only when it is provably pure.
**Revisit if:** a future hosted runner makes sharing a server worthwhile.

### D2 — Rust owns execution; React is a projection

**Decision:** run lifecycle, provider I/O, tools, approvals, persistence and
scheduling decisions live in Rust. The WebView holds no authoritative run state.
**Why:** WKWebView/Android WebView can be destroyed; a suspended process can be
killed. A JS-owned run loses work and can duplicate a submit.
**Consequence:** every UI feature needs a command/event; no "just fetch it in the
component".
**Revisit if:** never for this product; this is the load-bearing decision.

### D3 — No Node, Python, Next or JDdS on device

**Decision:** the mobile app bundles none of them. Bot Mode is reimplemented as a
small Rust runtime.
**Why:** Tauri mobile does not support sidecars; iOS 2.5.2 forbids the interpreter
model; the payload and databases do not fit.
**Consequence:** no quant/research/analysis tools, no Graph Studio, no MCP in v1.
**Revisit if:** Tauri adds supported mobile sidecars **and** Apple changes 2.5.2 —
neither is expected.

### D4 — Execution targets are a contract; v1 implements `local_mobile` only

**Decision:** bots carry `target` (`local_mobile`, `local_desktop`,
`remote_worker`). Unknown or unavailable targets fail honestly.
**Why:** it preserves a path to always-on agents without building cloud
infrastructure now.
**Consequence:** no target switcher in the v1 UI; the field exists in the schema.
**Revisit at:** the first hosted-runner proposal.

### D5 — Custom provider layer, not Rig

**Decision:** four adapters (`openai`, `anthropic`, `google`, `openrouter`) over
`reqwest` + `rustls`, behind a `Provider` trait. Rig is not a dependency.
**Why:** our hard problems are durability, approvals and mobile lifecycle, which
Rig does not solve; its mobile support is unverified and it is pre-1.0.
**Consequence:** we own SSE parsing and provider drift; fixtures are mandatory.
**Revisit triggers:** > 6 providers, embeddings/RAG as a first-class feature, or a
successful `rig-core` mobile spike plus a team preference for its breadth.

### D6 — SQLite in Rust (`rusqlite`), not the SQL plugin

**Decision:** `rusqlite` with bundled SQLite (and SQLCipher if the spike passes);
migrations and all queries in Rust.
**Why:** the UI must not hold SQL; transactions and recovery belong to the runtime;
`tauri-plugin-sql` exposes execute/select to the WebView.
**Consequence:** every list/query needs a command; no ad-hoc UI queries.
**Fallback:** plaintext SQLite + OS file protection if SQLCipher fails to build,
stated honestly in Settings.

### D7 — Keys in the OS keychain via a small custom plugin

**Decision:** iOS Keychain, Android Keystore-wrapped AES-GCM; Rust-only reads.
Stronghold is the fallback.
**Why:** no official Tauri plugin exposes the keychain directly; a key in SQLite is
unacceptable; the WebView must never see it.
**Consequence:** one native bridge per platform (Phase 1) and a hard invariant that
no command returns a key.

### D8 — Scheduling is best-effort and notification-first

**Decision:** local notifications at the intended time; execution on an OS-granted
background slot or the next app open; visible `ran`/`skipped`/`missed` states.
**Why:** Android enforces a 15-minute minimum and Doze; iOS background work is
opportunistic; force-quit stops both.
**Consequence:** no "always-on" marketing; a server is required for that promise.
**Revisit at:** a hosted worker.

### D9 — Static tool registry, no arbitrary code

**Decision:** seven compiled tools; no shell/Python/JS/dynamic downloads.
**Why:** App Store 2.5.2, mobile security, and the fact that a phone cannot safely
host the desktop sandbox.
**Consequence:** the mobile bot is less capable than the desktop agent by design.

### D10 — Versioned shared contracts, separate runtimes

**Decision:** JSON Schema in `packages/agent-contracts`; generated TS + Rust;
desktop conformance is a test, not a rewrite.
**Why:** "compatible contracts" is the only honest form of sharing when the
runtimes differ.
**Consequence:** two generators to keep current; version bumps are deliberate.

### D11 — Mobile-first UI, selective reuse

**Decision:** new navigation, chat layout, sheets and screens. Reuse only pure
modules and the visual identity (ghost SVG, markdown parser, icons, translator,
tokens).
**Why:** the desktop screens import Next stores, relative API routes and desktop
layout; copying them imports the coupling.
**Consequence:** some duplication; the desktop app is not refactored for mobile.

### D12 — iOS is a gate, not a final phase

**Decision:** Phase 2 runs the PoC on a real iPhone (via macOS CI/TestFlight), even
though development is on Windows.
**Why:** iOS is the highest-risk platform; discovering a WebView/lifecycle problem
in Phase 8 would invalidate the architecture.
**Consequence:** a Mac or CI minutes are a hard prerequisite from Phase 2.

### D13 — BYOK only in v1

**Decision:** the user supplies their own model key; no Eclipse proxy, no account,
no metering.
**Why:** keeps the app standalone and avoids operating a service; matches "no
pairing, no login".
**Consequence:** the user pays the provider; some users will not have a key; the
app needs a demo mode to pass review and to be usable before setup.

### D14 — No cloud, sync or push in v1

**Decision:** no backend, no multi-device sync, no remote push, no analytics.
**Why:** every one of them contradicts the standalone promise or adds a service to
operate.
**Consequence:** local notifications only; data lives and dies with the device
(export is explicit).

## 2. Risk register

Scale: probability P (L/M/H), impact I (L/M/H). Owner is the phase that must retire
the risk.

| # | Risk | P | I | Mitigation | Owner |
| --- | --- | --- | --- | --- | --- |
| R1 | iOS WKWebView is killed mid-stream or performs poorly | M | H | Rust-owned runs, checkpoints, resume by seq; Phase 2 device gate | Ph2 |
| R2 | App Review rejects under 4.2 (thin wrapper) | M | H | Native capabilities, offline history, notifications, biometrics, attachments, focused IA; review notes + demo mode | Ph8 |
| R3 | App Review cites 2.5.2 (executable code) | L | H | No interpreter/shell/downloads; static tools; documented capability list | Ph5/8 |
| R4 | Users expect always-on schedules | H | M | Explicit copy, `missed` states, a server is the only fix; product must not overpromise | Ph7 |
| R5 | Provider API drift breaks streaming/tools | M | M | Adapter isolation, recorded fixtures, weekly live drift check | Ph4 |
| R6 | SQLCipher fails to cross-compile | M | M | Phase 0 spike; plaintext + OS protection fallback, disclosed | Ph0 |
| R7 | Keychain/Keystore plugin takes longer than planned | M | M | Stronghold fallback; both are Rust-side | Ph1 |
| R8 | Group turns are slow/expensive (N bots per message) | M | M | Cap 6 members, concurrency 2, show per-member status, allow cancel, estimate cost before send | Ph6 |
| R9 | Attachment extraction is poor or unsafe | M | M | Text/PDF only in v1, size caps, label truncation, no execution | Ph5 |
| R10 | Low-end Android performance misses budgets | M | M | Measure in Phase 2, virtualize long threads, avoid heavy blur, lazy media | Ph2/8 |
| R11 | Financial content triggers extra review/legal scrutiny | M | M | Keep citations/UNAVAILABLE, visible disclaimer, no trade execution, optional finance pack | Ph8 |
| R12 | Data loss on uninstall or device loss | M | H | Explicit export, exclude from cloud backup by default, document that uninstall deletes data | Ph3/8 |
| R13 | Prompt injection via fetched pages | M | H | Untrusted labelling, capability minimisation, approvals, SSRF guards | Ph5 |
| R14 | Search provider ToS/cost blocks `web_search` | M | M | Make the provider pluggable; allow "no search" mode; document the choice | Ph5 |
| R15 | Tauri mobile plugin bug/gap | M | M | Phase 0 spikes; custom bridge only where needed; pin versions | Ph0/1 |
| R16 | Rig decision is reversed late | L | M | Provider trait boundary; adapters are swappable | Ph4 |
| R17 | Store review latency delays launch | H | L | TestFlight/Play internal first; submit early; keep the browser path as the fallback | Ph8 |
| R18 | Privacy label / Data Safety mismatch | M | H | Instrument network calls; a checklist before submission; no telemetry | Ph8 |
| R19 | User loses their API key and cannot recover | M | M | Explain it is device-only; allow re-entry; never claim account recovery | Ph8 |
| R20 | Accessibility/RTL regressions | M | M | Locale + font-scale tests; RTL from the start, not a retrofit | Ph8 |

## 3. What would invalidate this plan

| Finding | Consequence |
| --- | --- |
| iOS cannot sustain a 60 s stream in WKWebView without being killed | Move to a shorter request/response or chunked polling; still no server |
| Keychain/Keystore cannot be bridged in reasonable time | Stronghold with a user passphrase; UX cost |
| App Review rejects 4.2 even with native features | Pivot to TestFlight/enterprise distribution or add a genuinely native capability (widgets/Live Activities) |
| Product requires always-on bots | Add a hosted worker; this is a **product** decision, not an engineering trick |
| SQLite+SQLCipher fails on iOS | Ship unencrypted with OS protection and disclose it; do not fake security |
| Tauri mobile cannot build the required plugins | Reduce v1 scope (no deep links/haptics) rather than add a flaky bridge |

## 4. Open questions (need product answers)

1. **Demo mode:** should the app ship with a bundled canned conversation so a
   reviewer can use it without a key? (Recommended: yes.)
2. **Search provider:** Brave, Tavily, Serper or Exa? Cost, ToS and result quality
   differ; the app should not hard-code one without a decision.
3. **Finance pack:** ship seeded by default, or offer it as an optional pack?
   Default seeding increases review/legal exposure.
4. **Minimum OS:** iOS current-1 (e.g. 17+), Android 8/API 26+? Tauri/plugin floors
   and device reach must be checked at Phase 1.
5. **Group size:** keep the desktop 2–6 rule? (Recommended: yes.)
6. **Image inputs:** support vision models in v1, or text/PDF only?
7. **App identity:** `com.blackeclipse.mobile`, display name "Eclipse Bots"? Must
   not collide with the desktop identifier.
8. **Data retention:** keep everything until the user deletes it, or auto-prune
   old runs? (Recommended: keep; warn at 500 MB.)
9. **Remote push:** explicitly out of scope for v1 — confirm.
10. **Localization:** ship English first with the existing 22-locale translator
    wired, or ship a translated subset at launch?

## 5. Assumptions that must be checked in Phase 0

1. Tauri 2 mobile builds this crate shape on both platforms with the chosen
   plugins.
2. `reqwest` + `rustls` streams SSE on both devices without a proxy.
3. `rusqlite` + FTS5 works; SQLCipher is optional.
4. The keychain bridge can be written and audited in days, not weeks.
5. A release build fits under 40 MB before user data.
6. A real iPhone can keep a 60-second streaming run alive in the foreground.
7. App Review accepts a BYOK agent app with no account (the demo mode is the
   mitigation).

If any of 1–6 fails, stop and amend the decision record before Phase 1.

## 6. Explicit non-decisions

Not chosen here, and deliberately left to a later proposal:

- cloud vendor, region, tenancy or pricing;
- account system, sync protocol, conflict resolution;
- remote push (APNs/FCM) and notification service;
- on-device embeddings or a local model;
- import of desktop bots/conversations;
- a shared React component library between desktop and mobile;
- an ADR number for any decision above.
