---
title: Eclipse Mobile — Standalone Tauri 2 Bot Mode
status: Proposed
last-verified: 2026-11-12
---

# Eclipse Mobile

**Who this is for:** the engineer who will build or review the standalone mobile
app. Read this page first; it states the shape of the product and points at the
document that owns each question.

This folder is an **architecture package**, not an implementation. No production
application code was modified to produce it. Every claim about the repository was
checked against the code at `2026-11-12`.

## The product in one paragraph

A standalone iOS/Android app that ships **only Bots Mode** from Eclipse: create
bots, chat with one bot, run several bots in a group room, stream replies, call a
small set of tools, approve effectful actions, keep per-bot memory and history,
attach files, and receive local notifications. It uses Tauri 2 + React 19 + Rust
+ SQLite. It does **not** require the desktop app, the Next.js server, the Python
harness, JDdS, `agent-memory.db`, localhost networking, or an account. The user
brings their own model key. Internet access to model/search providers is the only
network dependency.

## What is and is not possible

| Claim | Verdict |
| --- | --- |
| A genuinely standalone Bot Mode app on a phone | **Yes.** Rust owns execution; SQLite owns state. |
| Reusing the existing desktop shell as-is | **No.** It spawns Node + Python and loads loopback. Both are desktop-only. |
| Reusing the existing Bot Mode UI unchanged | **No.** It is coupled to Next stores, relative `/api` routes and desktop layout. Pure logic and presentation can be extracted. |
| Always-on scheduled bots while the app is closed | **No, not without a server.** Local scheduling is best-effort and OS-controlled. See `scheduling-limitations.md`. |
| Running Python/quant/research tools on-device | **No.** Those stay on desktop. Mobile ships a deliberately small tool set. |
| App Store distribution | **Possible, with real risk.** Guideline 4.2 and 2.5.2 apply; see `risks-and-decisions.md`. |

## Documents

| Doc | Owns |
| --- | --- |
| [`architecture.md`](./architecture.md) | Topology, layers, execution-target model, process/lifecycle rules, module layout |
| [`repository-reuse-audit.md`](./repository-reuse-audit.md) | Every reusable/adapt/rebuild/desktop-only module, with evidence |
| [`dependency-evaluation.md`](./dependency-evaluation.md) | Rig vs a custom Rust runtime; DB, secrets, HTTP, scheduling choices |
| [`ios-android-compatibility.md`](./ios-android-compatibility.md) | Tauri mobile setup, plugin matrix, platform behaviour, physical-device PoC checklist |
| [`agent-runtime-design.md`](./agent-runtime-design.md) | Run lifecycle, events, durable resume, cancellation, retries, approvals, tools, providers, groups |
| [`data-model.md`](./data-model.md) | SQLite schema, migrations, FTS5, erasure, encryption, what is not migrated |
| [`security-model.md`](./security-model.md) | Threat model, key custody, redaction, SSRF, prompt injection, approvals, store privacy |
| [`scheduling-limitations.md`](./scheduling-limitations.md) | What Android/iOS actually allow; local vs app-open vs remote schedules |
| [`implementation-roadmap.md`](./implementation-roadmap.md) | Phases 0–8 with files, deps, tests, acceptance, effort |
| [`testing-strategy.md`](./testing-strategy.md) | Test pyramid, contract conformance, crash/stream fixtures, device matrix, CI |
| [`risks-and-decisions.md`](./risks-and-decisions.md) | Decision record (D1–D14), risk register, open questions |

## The five decisions that shape everything

1. **Mobile is a second product, not a build target.** It lives at the **repository
   root** in `mobile/` (a sibling of `Black-Eclipse-site/`, like `media/`), so the
   app's `tsconfig` does not compile it. The desktop app and the Python harness are
   not modified. (D1)
2. **Rust owns the run.** React renders; Rust persists and executes. The WebView
   may be destroyed at any time; state survives in SQLite. (D2)
3. **No port of the Python harness.** A small Rust agent loop replaces it for
   this surface only: provider streaming, tool calls, approvals, memory. (D3)
4. **Local scheduling is notification-first and best-effort.** No promise of
   exact-time or closed-app execution. (D8)
5. **Contracts are versioned and shared, but runtimes stay separate.** Desktop,
   mobile and a future worker share event/run/bot schemas, not an implementation.
   (D10)

## Non-goals for v1

- Monaco, xterm, 3D charts, Graph Studio, workspaces, MCP, skills, quant/RSL.
- Cloud accounts, sync, multi-device, remote workers.
- Reading or migrating `jdds.db` (361 MB) or `agent-memory.db` (1.6 GB).
- Arbitrary code, shell, Python or JavaScript execution as a tool.
- Remote push notifications (requires APNs/FCM and a server).

## Relationship to the existing docs

- Current Bot Mode behaviour: [`../bot-mode.md`](../bot-mode.md).
- Desktop shell contract: [`../../desktop/README.md`](../../desktop/README.md).
- Desktop packaging and runtime: [`../desktop-app-plan.md`](../desktop-app-plan.md),
  [`../desktop-cross-platform-plan.md`](../desktop-cross-platform-plan.md).
- Canonical navigation and ADRs: [`../NAVIGATION.md`](../NAVIGATION.md),
  [`../DECISIONS.md`](../DECISIONS.md).

This package does not add an ADR to `DECISIONS.md`. The decisions here are
**proposed** and become ADRs only when implementation is approved; the numbering
and mirroring rule in `AGENTS.md` still applies at that point.
