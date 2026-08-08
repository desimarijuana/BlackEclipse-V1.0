---
name: blackeclipse-remember
description: Load persistent project memory and context for BlackEclipse before major work. Use when starting a task on BlackEclipse to recall decisions, conventions, constraints, and things that must not change.
---

Read the persistent project memory at `skills/REMEMBER.md` before major work. It records:

- Product context and current priorities
- Important decisions (zero-config, agentic-scraper-primary, agent abstraction, RSS news)
- Established conventions (folder structure, client components, barrel exports)
- Known constraints (memory, @base-ui/react SSR quirks, fonts, no DB)
- Known problems
- Things that must not change (Aurora, dark identity, zero-config, getTradingViewSymbol)
- Lessons learned and important discoveries

Rules:
- Update `skills/REMEMBER.md` when you discover meaningful project knowledge.
- Mark outdated info as `[DEPRECATED]` rather than silently deleting it.
- Never store useless noise; keep entries concise and actionable.
- Test after every change (`npm run test` + `npx tsc --noEmit`).
- Never commit, push, or create branches/PRs unless the user explicitly asks.
