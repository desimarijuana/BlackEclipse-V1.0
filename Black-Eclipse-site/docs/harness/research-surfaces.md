---
title: Which surface answers which question
status: Current
last-verified: 2026-10-07
---

# Which surface answers which question

**Who this is for:** anyone deciding whether a task belongs to the web-research
engine, the browser, or computer-use — and anyone changing one of the three.

Eclipse has **three surfaces** that can obtain information or act, plus the
retrieval/JDdS layer beneath them. They are deliberately separate: each is best at
something the others cannot do. This is the ONE page that says which to reach for;
each engine's own doc (linked below) explains *how* it works.

## The rule

> **search finds → browser reads behind a login → computer-use reads a desktop app.**

| Surface | Answers | Reaches | Cannot |
|---|---|---|---|
| **Web-research engine** (`web_*`, `research_*`) | Ordinary web questions: facts, news, filings, comparisons, verified claims | The whole public web via search + SSRF-hardened fetch; it turns a fetched page into provenance-carrying *evidence* and verifies *claims* | Login-gated pages, JS/canvas the fetch cannot render, native desktop apps |
| **Browser** (`browser_*`) | A page that must be *interacted with*: a form, a search portal, a tab flow, a login, a JS-rendered page | Interactive pages, behind a sign-in (with a vault reference), local test apps | Native desktop apps; it does not itself verify a claim |
| **Computer-use** (`computer_*`) | Anything that lives in a *native desktop app*: Excel, VS Code, a terminal, a PDF reader, a trading client, OS dialogs | The real screen/accessibility state of a desktop app or terminal | Web pages reachable by fetch/browser (prefer those); it never bypasses the finance firewall |

## The hand-off rules

- **Search finds, then fetch.** A search result is a *pointer*, never evidence. Use
  the web-research engine to search and to fetch a page into evidence.
- **The browser reads behind a login.** When a page needs interaction or a
  sign-in, the browser opens it. The value it reads is a **candidate** — see the
  verification rule below.
- **Computer-use reads a desktop app.** When the information is only on a native
  screen (a terminal, a proprietary client), computer-use reads it.
- **One evidence store.** All three feed the run's ONE `source_sink` /
  `EvidenceStore`. No surface keeps a second provenance shape. A browser- or
  screen-derived value is marked as such; it is never dressed as verified evidence.
- **One verification path.** Only the web-research engine's `claim_verify` can turn
  a candidate value into a *verified claim*. A browser number enters a verified
  claim **only** through `browser/bridge.py` (which builds evidence, then runs the
  engine's `verify_claim`). A screen-derived value follows the same rule.

The deterministic implementation of `route(SurfaceRequest)` and the
machine-readable `routing_policy()` live in
[`python/harness/research/coordination.py`](../../python/harness/research/coordination.py)
(ADR-H139).

## Why the three are separate

A browser is one of the highest-authority capabilities an agent can hold
(untrusted input, credentials, external actions); a desktop can move the mouse and
type into a trading terminal. Modelling either as a set of functions under one
"web" tool would leak authority, scatter policy, and couple the runtime to one
backend. Keeping the surfaces distinct lets the *policy* (permissions, domains,
the finance firewall) be structural, and lets the *verification* stay in one place.

## The docs

- **Web-research engine:** [`web-research-engine.md`](./web-research-engine.md) — search/extract/evidence/claims/citations.
- **Browser:** [`browser-runtime.md`](./browser-runtime.md) — interactive pages, providers, sessions, tracing.
- **Computer-use:** [`computer-use.md`](./computer-use.md) — native desktop, the finance firewall.
- **Decisions:** [`decisions.md`](./decisions.md) — ADR-H134 (browser), ADR-H135 (research), ADR-H139 (cross-engine coordination), ADR-H140 (computer-use).
