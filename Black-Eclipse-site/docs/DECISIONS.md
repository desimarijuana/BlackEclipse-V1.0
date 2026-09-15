---
title: Decisions (ADR log)
status: Current
last-verified: 2026-09-15
---

# Decisions — Architecture Decision Record

**Who this is for:** anyone about to re-litigate a choice, or wondering why
something is the way it is.

An ADR is a few lines recording *why* a significant decision was made — a commit
message for architecture. Write one when you make a meaningful choice. Keep it
short. Never delete an ADR; supersede it and mark the old one
`[SUPERSEDED by ADR-0XX]`.

> This is a readable mirror of the ADR section in
> [`../skills/ARCHITECT.md`](../skills/ARCHITECT.md). **That file is
> authoritative**; add new ADRs there first, then mirror them here.

---

## ADR-001 — Demo data + zero-config (2026)
**Decision:** Ship with demo data; no DB, no keys required to run.
**Why:** Zero-config policy + open-source friendliness.
**Impact:** All screens work immediately; real data is an opt-in. This is the
oldest and most load-bearing decision in the project.

## ADR-002 — RSS for news (2026)
**Decision:** Use free RSS feeds for news instead of a paid news API.
**Why:** No API key, no rate limits, open standard.
**Impact:** `/api/news` serves live news with an offline/mock fallback; ingestion
was later moved into JDDS (`NewsItem`) so requests do not re-fetch feeds.

## ADR-003 — Agent provider abstraction (2026)
**Decision:** Define an `AgentProvider` interface, default to the built-in mock,
and plug in real LLMs additively.
**Why:** Keeps chat functional with zero config while enabling real agents later.
**Impact:** The UI calls `getAgentProvider().chat(...)`. Adding a provider never
touches the UI.

## ADR-004 — Agentic scraper as the primary data source (2026)
**Decision:** The default market-data source is the free, built-in scraper; user
APIs are optional opt-ins; demo data is the fallback.
**Why:** Users should configure as little as possible.
**Impact:** Data-source priority is always scraper → user API → demo.

## ADR-005 — Workspace kernel supersedes `src/lib/customize/` (2026)
**Decision:** All page customization is driven by `src/lib/workspace/`
(sections → columns → widget cards, with relative column weights). Stored
layouts are validated and normalized on load; corrupt data falls back to
defaults **without overwriting** the stored payload. Pages get edit chrome
(drag/drop, add/remove, resize, templates) from the kernel only.
**Why:** The flat span model couldn't express free-form placement (multiple
widgets per column, individual widths). An earlier v3 "element model" in
`src/lib/customize/` was sketched but never shipped.
**Impact:** Adding a customizable page = a widget registry + the workspace
kernel. `src/lib/customize/` is **retired** — do not build on it.

## ADR-006 — Workspace stack: dnd-kit + Zustand + Immer (2026)
**Decision:** dnd-kit owns drag & drop; Zustand owns editor/layout/selection
state (one cached store per storage key); Immer owns layout mutations (every op
in `ops.ts` is a draft mutator applied via `produce`).
**Why:** Replaces hand-rolled pointer-drag DOM surgery, `useState` plumbing, and
manual structural clones. Ops become trivially testable.
**Impact:** New layout ops must follow the draft-mutator signature and get a unit
test. Persistence happens inside `commit()` — never call the save helper
elsewhere.

## ADR-007 — Page-header icon tiles (2026)
**Decision:** Every page header uses the portfolio-style icon tile: a 56px
rounded container (`border-primary/25 bg-primary/15`) wrapping a 30px
primary-colored lucide icon.
**Why:** Bare inline icons looked inconsistent next to the portfolio header.
**Impact:** New screens copy the tile; do not revert to bare small icons.

## ADR-008 — Two-click placement confirm (2026)
**Decision:** Widget placement is **preview-then-confirm**, not drop-to-commit.
Grab a card (click or drag-release), hover to preview the labeled ghost slot,
then click again (or the ghost/Confirm) to commit. **Escape or right-click
cancels** at any point.
**Why:** Drop-to-commit was unreliable across devices (touch pan gestures,
scroll-adjusted deltas, off-screen targets) and gave no chance to verify.
**Impact:** The drop target is projected from the **real pointer**
(`pointermove` + `elementFromPoint`), not dnd-kit's delta. Any new interaction
must respect the two-click contract.

---

## Decisions implied by the code (not yet formal ADRs)

These are real, load-bearing, and currently only documented in prose. Promote one
to an ADR if it gets challenged.

- **SQLite-only JDDS.** PostgreSQL was removed along with the old daemon.
  Reintroducing `DATABASE_URL`/pg tooling would be a new ADR.
- **Keep-alive tabs, single page.** Tabs mount on first visit and stay mounted;
  no URL routing for main screens.
- **In-process schedulers.** Cron runs inside the Next.js server (not Vercel-
  friendly by design; a `POST /api/cron/run` endpoint exists for hosted setups).
- **Synchronous-write discipline.** Bulk writers yield and sleep by design
  because better-sqlite3 blocks the event loop.
- **Separate market-workspace engine.** The Market Workspace tab has its own
  panel engine rather than reusing the widget workspace.
