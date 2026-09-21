# AGENTS.md — Always-On Rules for BlackEclipse

These rules apply to **every task in this repository**, regardless of size or
topic. They are loaded on every session. Read them before you start, and satisfy
them before you report a task complete.

---

## Documentation obligation (applies to every change)

The canonical system documentation lives in
`Black-Eclipse-site/docs/`. The rule that governs it:

> **Document what the code cannot tell you — intent, "why", invariants, and how
> to navigate. Do not re-document what you can read from the source.**

### Before you finish ANY task, do this

0. **Record the change in `Black-Eclipse-site/docs/CHANGELOG.md`.** This is
   required for **every** change — including ones that need no doc edit. Append
   an entry under today's date: a terse bullet describing what changed and why,
   ending with either the doc files updated or `no doc change — <reason>`. Append
   only; never rewrite past entries.

1. **Decide whether this change also affects documentation.** A doc update is
   **required** when the change alters:
   - architecture (a layer, module, worker, engine, or a retired subsystem),
   - a data shape or contract (API response, JDDS model, topic vocabulary,
     widget/ops signature),
   - setup or operations (prereqs, npm scripts, env vars, boot sequence),
   - a top-level folder or major module, or
   - an architectural decision.

   It is **NOT** required for bug fixes, internal refactors that keep contracts
   intact, style/copy changes, or test-only changes.

2. **Find the owning doc** using the trigger table in
   `Black-Eclipse-site/docs/NAVIGATION.md`, then update it.

3. **Bump `last-verified`** only on docs you actually re-read against the code.
   Never as a side effect of an unrelated edit.

4. **Mark stale, never delete.** If a doc is now wrong, set `status: Stale` and
   note what changed. A doc that admits it is stale is useful; a deleted one
   loses history.

5. **State it in your final report** — one of:
   - `docs updated: <file(s)>`, or
   - `no doc change — <reason>`.

   Silence is not acceptable.

### Authority hierarchy (do not create competing copies)

- `Black-Eclipse-site/docs/` — **canonical**: how the system works.
- `Black-Eclipse-site/skills/ARCHITECT.md` — authoritative for ADRs and deep
  architecture. New ADRs go here first, then mirror into `docs/DECISIONS.md`.
- `Black-Eclipse-site/skills/DOCS.md` and
  `.opencode/skills/black-eclipse-docs/SKILL.md` — the method itself.
- `README.md` / `CONTRIBUTING.md` — point into `docs/`; do not restate it.

If docs and code disagree, **the code wins** — then fix the doc.

---

## Standing engineering rules

- **Run the checks after every change:** `npm run test` **and**
  `npx tsc --noEmit` (from `Black-Eclipse-site/`). Both must pass.
- **Never fabricate financial data.** Unavailable data renders an `UNAVAILABLE`
  state; simulated/stale data is always labeled. All market data is read through
  JDdS (`jdds.db`) — the agentic layer never queries a second data source.
- **The agentic runtime is Python.** Agents, tools, model providers, harness
  events and run persistence live in `Black-Eclipse-site/python/harness/`
  (FastAPI + LangChain + LangGraph). Next.js is the front door: it validates
  input, resolves LLM config from the settings vault, serves the read-only JDdS
  data bridge, and proxies. Do not rebuild an agent loop, tool registry, or
  model adapter in TypeScript.
- **Zero-config must keep working.** `npm install && npm run dev` must never
  require manual setup. `postinstall` installs the Python agent stack
  automatically; `doctor.js` repairs it on boot. If Python is genuinely
  unavailable, agent runs must fail honestly (503 "runtime unavailable") — never
  silently fall back to a fake agent.
- **Never commit, push, or open a PR unless the user explicitly asks.** When
  asked, inspect `git status`/`git diff` first and never commit secrets.
- **Do not commit `jdds.db` on routine changes** — it is a seed snapshot updated
  deliberately, rarely. See `.opencode/skills/black-eclipse-db/SKILL.md`.
- **Reuse before rebuild.** Prefer existing components, hooks, and services.
- **Keep files small.** Memory is the top constraint on this machine; do not
  re-bloat large files.
- **Do not add dependencies without justification**; prefer the lighter option.
- **UI surfaces use the frosted-glass system**
  (`.opencode/skills/black-eclipse-ui/SKILL.md`), not raw blur or flat fills.

---

## Repository layout

The app lives in `Black-Eclipse-site/` (Next.js + TypeScript + SQLite via
Prisma). Project skills live in `.opencode/skills/`. Documentation lives in
`Black-Eclipse-site/docs/`. Full navigation: `Black-Eclipse-site/docs/NAVIGATION.md`.
