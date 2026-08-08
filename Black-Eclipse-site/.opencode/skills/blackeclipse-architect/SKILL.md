---
name: blackeclipse-architect
description: Read before making significant architectural changes to BlackEclipse. Use when planning a new data source, agent, screen, API route, or any large structural change. Loads the full system architecture, technology stack, and architectural rules.
---

Read the full engineering reference at `skills/ARCHITECT.md` before making significant architectural changes. It documents:

- Product definition, vision, users, and what makes BlackEclipse different
- The actual system architecture (frontend, backend, API, agent layer, data sources)
- The current technology stack (what is CURRENT vs PLANNED vs DEPRECATED)
- Data architecture and market-data flow
- Important architectural rules (reuse before rebuild, no duplication, memory discipline)
- Architectural Decision Records (ADRs)

Key rules to remember:
- BlackEclipse is a **zero-configuration** product. Data source priority: **agentic scraper → user API → demo data**.
- Reuse existing hooks (`use-screener-filters.ts`, `use-portfolio-engine.ts`), ui primitives, and the agent layer.
- Keep large files split; the codebase has memory constraints on this machine.
- Where this file conflicts with the actual working code, the code is the source of truth.
