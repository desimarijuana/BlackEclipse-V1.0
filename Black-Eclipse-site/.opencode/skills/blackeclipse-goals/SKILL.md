---
name: blackeclipse-goals
description: Load the current phase goals and direction for BlackEclipse before starting feature work. Use when starting a task to understand what is in scope this phase (data layer + market screener), the two data paths (user API vs Eclipse built-in data), and what is explicitly out of scope (agentic AI chat).
---

Read the current phase goals at `skills/GOALS.md` before starting feature work. It captures:

- The current phase (data layer + market screener) and its intent
- The two data paths: user API → JDDS, and Eclipse built-in (scraped) data → JDDS
- Feature-by-feature goals (market screener, market bubble, portfolio, on-demand research)
- What is IN scope and OUT of scope this phase (agentic AI chat is deferred)
- The redirected role of the self-healing scraper (on-demand "AI analyze" instead of scrape-everything)
- Guardrails (finance-only, JDDS-first, zero-config, staleness honesty, on-demand over scrape-everything)
- **The standing "simple, fast, light" goal** — the site must be simple, fast, and light for the best user experience. Applies to every change, forever. See the "Performance & Simplicity" section.

Rules:
- Update `skills/GOALS.md` when the phase changes or goals shift.
- Mark superseded goals as `[SUPERSEDED]` rather than deleting them.
- Keep the "why" behind decisions so future agents don't re-litigate them.
- Test after every change (`npm run test` + `npx tsc --noEmit`).
- Never commit, push, or create branches/PRs unless the user explicitly asks.
