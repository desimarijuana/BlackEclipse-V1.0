# GOALS.md — Current Phase Goals & Direction

> Read this file **before starting any feature work** to understand what we are building in this phase and why. It captures the current phase's intent, the data-flow decisions, and what is explicitly out of scope right now.
> This is a living document — update it when the phase changes or goals shift.

---

## Phase: Data Layer & Market Screener (built) → Agentic Research (current)

The **data + market screener phase is largely built** (JDDS, the scraper
scheduler, the screener, portfolio, journal, economics, alerts, and the command
palette all read from JDDS). The focus has shifted to **agentic research**: the
tool loop (`src/lib/agent/loop.ts` + `tools.ts`), the OpenAI-compatible provider,
and the multi-agent research pipeline (`research.ts`) that persists findings in
JDDS. Extend those; do not rebuild a parallel stack. The original phase intent is
kept below for the "why".

### The core problem we're solving
Users may not have an API, or their API may not cover a specific market (e.g. Hong Kong). We want users to always have data to look at and explore — whether it comes from their API or from Eclipse's built-in data.

### The two data paths (both feed JDDS → site)

**Path 1 — Eclipse built-in data (scraped universe)**
- We scrape stocks and lists from **all global markets** so users have data to explore even without an API.
- This is the "no API" path. Data may be **stale** — show a clear **warning that it is old**.
- Goal of Eclipse data: if the user has no API, they can still use built-in data, with a visible staleness warning.

**Path 2 — User API data**
- User's API data is fetched into **JDDS**, then flows to the site.
- Prices, changes, etc. update based on their API data.
- This is the "has API" path — live, accurate.

### Data flow (both paths)
```
User API  ──┐
            ├──► JDDS (SQLite vault) ──► Site screens (screener, bubbles, portfolio)
Eclipse data ┘
```
- JDDS is the single source of truth. All screens read from it.
- Source priority: **user API → Eclipse built-in data (stale warning) → demo**.

---

## Feature-by-feature goals (this phase)

### 1. Market Screener (primary focus)
- Scrape stocks + lists from **all global markets** (US, Pakistan, India, China/HK, Crypto, etc.) so users can explore.
- If a user has an API, their data populates JDDS and the screener reflects it.
- If no API, Eclipse built-in data is shown **with a staleness warning**.
- **On-demand research:** if a stock in the table is missing price data, the user clicks an **"AI analyze"** button on that row to get the information from the research agent. (This replaces the idea of scraping every price on load — see "Self-healing scraper" below.)

### 2. Crypto Bubble → Market Bubble
- The crypto bubble view becomes a **market bubble** for any market.
- Visually show which asset has the **most volume**, based on data in JDDS (from API or Eclipse built-in data).

### 3. Portfolio Tracking
- Users track their portfolio and check performance.
- Portfolio data also comes from **JDDS**.

### 4. AI Chat (agentic side) — NOW ACTIVE
- **This is the current phase.** `src/lib/agent/` ships a tool loop, an
  OpenAI-compatible server provider, and a multi-agent research pipeline that
  persists `ResearchReport` / `AgentRun` / `ResearchFinding` into JDDS. Extend
  these rather than building new agents from scratch.

### 5. Self-healing scraper — REDIRECTED
- **Original idea:** scrape the internet for any stock price on demand.
- **Problem:** scraping everything on load just increases load for little value.
- **Better approach (this phase):** on the market screener, if a stock is missing price data, the user clicks **"AI analyze"** on that row → the research agent fetches the information on demand.
- So the self-healing scraper's role shifts from "scrape everything" to "fetch on demand via the research agent when the user asks."

---

## What is IN scope (this phase)
- Scraping stock lists/universes for all global markets into JDDS.
- Wiring user API data into JDDS → site.
- Market bubble (volume-based) for any market.
- Portfolio tracking reading from JDDS.
- Staleness warnings on Eclipse built-in data.
- "AI analyze" per-row button on the screener (on-demand research trigger).

## What is OUT of scope (this phase)
- Building the Tool-Builder Agent (later phase).
- PDF export / report card UI (later phase).
- Broker / paper-trading integration (trading widgets stay `UNAVAILABLE` stubs).

---

## Guardrails (carry over from mission)
- **Finance-domain-only** — Eclipse only does finance stuff.
- **JDDS-first** — pre-store data once, distribute to all screens; agents read from JDDS.
- **Zero-config** — the app must always run with no setup; demo data is the baseline.
- **Staleness honesty** — Eclipse built-in data must be clearly marked as old, never presented as live.
- **On-demand over scrape-everything** — avoid loading the scraper with unnecessary work; fetch on demand when the user asks.
- **Simple, fast, light** — the website must be simple, fast, and light to give the best user experience. This is a standing goal, not a one-time task. Every feature, component, and data path should be evaluated against it. See the "Performance & Simplicity" section below.

---

## Performance & Simplicity (STANDING GOAL)

> This is a **permanent** goal, not a phase goal. It applies to every change, forever. When in doubt, choose the simpler, lighter, faster option.

### What "simple, fast, light" means here
- **Simple** — minimal moving parts, few concepts, easy to understand and maintain. Prefer the existing pattern over a new abstraction.
- **Fast** — snappy interactions, low latency, no wasted work. Server-side filtering/pagination so we never pull the whole universe into memory.
- **Light** — small bundle, few dependencies, low memory/RAM footprint, no heavy libraries when a lighter one suffices.

### Rules to follow on every task
1. **Reuse before rebuild** — use existing hooks, ui primitives, and services instead of adding new ones.
2. **No unnecessary dependencies** — if a new dependency is needed, justify it in `REMEMBER.md`; prefer lighter alternatives.
3. **Server-side filtering & pagination** — the screener already filters/paginates on the server (`/api/stocks`); keep it that way. Never fetch the full universe client-side.
4. **Split large files** — keep components small (this machine has 7.9GB RAM; `market-overview.tsx` is already ~1900 lines). Extract logic into hooks/modules.
5. **Avoid re-renders & memory leaks** — use `useMemo`/`useCallback` where appropriate; clear intervals/timeouts.
6. **No N+1 / excessive DB calls** — batch queries, use `Promise.all`, avoid sequential awaits that could be concurrent.
7. **Light payloads** — don't ship data the screen doesn't use; keep API responses lean.
8. **Measure before optimizing** — don't prematurely optimize; but when adding something heavy, ask "is there a lighter way?"

### When to apply
- **Every new feature** — ask: does this make the site simpler, faster, or lighter? If it makes it heavier, justify it.
- **Every refactor** — prefer the change that reduces complexity.
- **Every dependency add** — prefer the lighter package or no package at all.

---

## Build order (this phase)
1. Scrape stock universes for all global markets into JDDS.
2. Wire user API data into JDDS → site.
3. Market bubble (volume-based) for any market.
4. Portfolio tracking from JDDS.
5. Staleness warnings on built-in data.
6. "AI analyze" per-row button on the screener (on-demand research trigger).

---

## How to update this file
- When the phase changes (e.g. we move to the agentic AI phase), update the **Phase** line and the IN/OUT of scope sections.
- Keep the "why" — the reasoning behind decisions — so future agents don't re-litigate them.
- Mark superseded goals as `[SUPERSEDED]` rather than deleting them.
