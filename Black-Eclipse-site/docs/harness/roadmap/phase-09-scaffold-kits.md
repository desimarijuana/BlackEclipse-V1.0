---
title: "Phase 9 — Finance Application Scaffold Kits"
status: Not started
phase: 9
depends_on: [5, 7, 8]
unlocks: [10]
last-verified: 2026-09-30
---

# Phase 9 — Finance Application Scaffold Kits

| | |
|---|---|
| **Depends on** | Phase 5 (the task surface), Phase 7 (delegation), Phase 8 (the compute sandbox) |
| **Unlocks** | Phase 10 (self-improvement has something to improve) |
| **Estimated work** | 8–12 h of agent time — the largest content phase |
| **Deliverable type** | a kit library (data) + a scaffold tool + skill wrappers |
| **New ADRs** | ADR-H111 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the real gap)](#2-why-this-phase-exists-the-real-gap)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The kit contract — `python/harness/code/kits/kit.json`](#61-the-kit-contract--pythonharnesscodekitskitjson)
  - [6.2 The kit library](#62-the-kit-library)
  - [6.3 The scaffold tool](#63-the-scaffold-tool)
  - [6.4 Skill wrappers](#64-skill-wrappers)
  - [6.5 The anti-fabrication rule for generated code](#65-the-anti-fabrication-rule-for-generated-code)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Make **"build me X"** produce a real, working, *verified* thing — not prose about
it. A data adapter, a ratio calculator, a backtest, a chart indicator, an ingestion
pipeline, a research workflow, an MCP server.

This is the user-visible payoff of Phases 1–8, and it is the capability the root
plan names as the whole point of a coding agent: *"You want an agent that can build
actual financial software."*

## 2. Why this phase exists (the real gap)

`agentic-plan-implementaion.md` §15 lists the target artefacts by name — *a new
market data adapter, an MCP server, a financial ratio calculator, a backtesting
strategy, a chart indicator, a portfolio analysis module, a data ingestion
pipeline, a test suite, a research workflow, a new agent skill*. Today each of
those means **a human writes it**, because the harness cannot write code at all.

And the repo already contains, for every one of those shapes, the **exact
convention** the artefact must follow. That is what makes scaffolds honest instead
of boilerplate:

| Kit | The convention it must satisfy (already in the repo) |
|---|---|
| Market-data adapter | `retrieval/sources.py` (`RetrievalSource`), a `DataType` in `retrieval/contract.py`, a row in `retrieval/planner.py` `_PLAN`, entries in `retrieval/policies.py` |
| Ratio calculator | `research/calculations.py` — formula/version/input provenance + hard input guards |
| MCP server | `mcp/config.py`'s server contract (argv, no shell, per-server env allowlist, effect classes) |
| Portfolio module | `src/lib/portfolio/` (`matrix.ts` date-aligned correlation, `risk.ts`) |
| Chart indicator | the chart conventions in `src/lib/` + vitest |
| Ingestion pipeline | `scripts/import-*.js` conventions (idempotency, universe handling) |
| Research workflow | `python/harness/skills/library/<category>/<name>/` (`skill.json` + `SKILL.md` + optional `tests/cases.json`) |
| Test suite | the repo's own gate conventions (`npm run check:all`) |

A kit is therefore **not** a code snippet. It is *the shape the repo already
demands*, plus the tests that prove a generated instance satisfies it.

## 3. In scope

1. The kit contract (`kit.json`) and the eight kits of §6.2.
2. `scaffold_kit` — writes into the **worktree**, never in place.
3. Verification: the generated instance is checked by the **repo's own gate** for
   that area (§9).
4. Skill wrappers so a scaffold is reachable through the existing `skill_invoke`
   path under the existing permission model.
5. The anti-fabrication rule for generated code.

## 4. Who can use it (the non-expert obligation)

**This is the phase where the audience rule pays off or fails.** An analyst who has
never written Python must be able to get a working screener; an accountant must be
able to get a reconciliation tool.

1. **The ask is the feature.** *"I want to compare any two companies' margins side
   by side"* → Eclipse picks the kit, fills it in, checks it, and reports. The user
   never chooses a kit by name, never sees a file tree, never types a parameter
   name.
2. **Questions, not forms.** When a kit needs a value, Eclipse asks in words: *"How
   far back should it look by default — 1 year, 5 years, or as far as the data
   goes?"* Never "set `default_period`".
3. **The result is stated as a job done, with proof.** *"Done — you can now compare
   margins for any two companies. I checked it with 3 tests and it works."* Not
   "scaffolded 4 files, applied patch a3f…".
4. **"Show me what you made" is always available and always readable** — the files,
   in plain terms, with a one-line explanation of what each does. For the expert,
   the diff and the checks are there too.
5. **Nothing is enabled behind the user's back.** A generated research workflow
   arrives as a *draft*, exactly like every other skill (ADR-025): it is inert until
   evaluated and the user turns it on. Say so plainly: *"I've prepared it — review
   it and switch it on when you're happy."*
6. **Failure is a sentence with a next step.** *"I built it, but one check failed —
   it can't read one of the data fields. Want me to fix it?"* Never a stack trace.
7. **The words *scaffold*, *kit*, *template*, *worktree*, *diff*, *patch* and
   *manifest* stay off the surface.** They live here and in the trace.
8. **All new copy is an i18n key** in `src/lib/i18n/` (`dictionaries/en.ts`,
   `dictionaries/index.ts`, `translate.ts`, `use-t.ts`).
9. **The plain-language gate** (§9 G8) covers every kit's user-facing name,
   description, question and result line.

## 5. Non-goals (do not do these)

- **No arbitrary system generation.** Eight named shapes, no "build me anything".
- **No trading, order, or broker code — ever.** A kit that would touch an order
  path does not ship.
- No deployment, publishing or packaging kit.
- A kit never writes outside the task's worktree.
- A generated artefact never self-activates (no auto-enabled skill, no auto-registered
  tool).
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 The kit contract — `python/harness/code/kits/kit.json`

Mirrors the discipline of `skills/manifest.py`: a small, validated, reviewable
manifest.

```json
{
  "id": "market_data_adapter",
  "version": "1.0.0",
  "title": "A new market-data source",
  "summary_key": "kit.market_data_adapter.summary",
  "produces": ["python/harness/retrieval/my_source.py", "python/tests/test_my_source.py"],
  "requires": {
    "inputs": [
      { "name": "source_name", "kind": "identifier", "prompt_key": "kit.market_data_adapter.q.source_name" },
      { "name": "data_types", "kind": "choice", "choices": ["quote", "ohlcv", "financial_statements"], "prompt_key": "kit.market_data_adapter.q.data_types" }
    ]
  },
  "conventions": [
    "implement RetrievalSource from retrieval/sources.py",
    "add the DataType to retrieval/contract.py",
    "add a row to retrieval/planner.py _PLAN and to retrieval/policies.py"
  ],
  "checks": ["python -m pytest python/tests/test_my_source.py -q", "npx tsc --noEmit"],
  "acceptance": "the source is selected by the planner for its data type and returns UNAVAILABLE (never a guess) when it has no data"
}
```

Rules the contract enforces:

- `produces` is an **explicit closed list** — the scaffold tool writes nothing
  outside it (the Phase 2 patch engine enforces this at the file level).
- `checks` are **command classes** from Phase 3, not free-form shell.
- `inputs` are typed and carry **prompt keys**, so the question is translatable and
  plain (never a raw parameter name on the surface).
- `acceptance` is prose in the manifest because it becomes the **test** the kit must
  ship — a kit without its acceptance test does not load.

### 6.2 The kit library

| Kit id | Shape | The check that must pass |
|---|---|---|
| `market_data_adapter` | a `RetrievalSource` | its own test + `npx tsc --noEmit` (the bridge) |
| `mcp_server` | a stdio MCP server | it starts, lists tools, and validates as an MCP config (`test_mcp_example_config.py` conventions) |
| `ratio_calculator` | a metric in `research/calculations.py` | its formula/version/input-guard tests |
| `backtest_strategy` | a strategy + walk-forward harness | its own test; honest metrics (no in-sample claims) |
| `chart_indicator` | a pure TS indicator | vitest |
| `portfolio_module` | analytics using `src/lib/portfolio/` contracts | vitest + its own test |
| `data_ingestion_pipeline` | an importer following `scripts/import-*.js` | an idempotency test (run twice ⇒ same state) |
| `research_workflow` | a skill (`skill.json` + `SKILL.md` + cases) | `skills/loader.py` loads it; `evaluation.py` runs deterministically; it stays **inert** |

Each kit ships: the template files, the manifest, the generated test (including the
`UNAVAILABLE` path — §6.5), and a docstring explaining *why* the shape is what it is
(the repo's own documentation rule: *document what the code cannot tell you*).

### 6.3 The scaffold tool

`ToolDefinition`: `name="scaffold_kit"`, `read_only=False`,
`required_permissions=("code.write",)`. It accepts a kit id + the declared inputs,
renders into the **task's worktree** (never the user's checkout — Phase 2's rule),
then runs the kit's `checks` through Phase 3's `command_run` and records them in the
Phase 4 ledger.

Refusals, structured: `KIT_UNKNOWN`, `KIT_INPUT_MISSING` /
`KIT_INPUT_INVALID`, `SANDBOX_UNAVAILABLE` (no isolation ⇒ no run ⇒ refuse),
`CHECK_FAILED` (the scaffold is **kept** for inspection, never silently deleted),
`OUTPUT_OUTSIDE_DECLARED_SET`.

### 6.4 Skill wrappers

Each kit gets a thin skill so it is reachable through the **existing** `skill_invoke`
path, with the **existing** permission model — `requiredTools: ["scaffold_kit"]` and
`SKILL.md` describing the finance job in plain language. The permission check, the
allowlist and the budget are unchanged: a kit wrapper cannot grant anything.

### 6.5 The anti-fabrication rule for generated code

This is the phase-9 version of `AGENTS.md`'s *"Never fabricate financial data"*, and
it is a **generation rule**, enforced by the kit templates themselves:

1. Every generated adapter, backtest or ingestion path **must** declare what it does
   when its data is absent: return `UNAVAILABLE` (the existing convention), never a
   default, never a synthetic series, never an extrapolation.
2. Every generated test **must** exercise that path. A kit whose generated test does
   not cover its `UNAVAILABLE` branch fails its own acceptance gate.
3. A generated backtest must state its period and its inputs on its result, and must
   not present an in-sample metric as predictive.
4. A generated ingestion pipeline is **idempotent**: running it twice must not
   duplicate state, and the test proves it.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-09-progress.md` with §9's gates.
2. The kit contract loader + validation (`code/kits/__init__.py`, a pydantic model,
   a manifest self-check) — before any kit content.
3. Kit 1 (`ratio_calculator`) end to end, as the reference: manifest → template →
   generated test → checks → ledger. Get the shape right on the smallest kit.
4. The remaining seven kits, one at a time, each with its acceptance test.
5. `scaffold_kit` tool (§6.3) + refusal codes.
6. Skill wrappers (§6.4) as draft skills.
7. Plain-language strings for every kit's title/summary/question/result as i18n keys.
8. Tests: `test_kits_contract.py`, `test_kits_scaffold.py`, one
   `test_kit_<id>.py` per kit (the acceptance test), `test_plain_language.py`
   extended.
9. ADR-H111; `docs/CHANGELOG.md`; `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/kits/__init__.py` + `loader.py` | new — the kit contract + validation |
| `python/harness/code/kits/<kit-id>/` (×8) | new — manifest + templates + generated test |
| `python/harness/code/tools.py` | register `scaffold_kit` |
| `python/harness/skills/library/**/<kit>/` | new — the eight draft skill wrappers |
| `python/tests/test_kits_*.py`, `test_kit_<id>.py` | new |
| `src/lib/i18n/dictionaries/en.ts` (+ index) | new keys (8 titles, summaries, questions, results) |
| `docs/harness/decisions.md` | ADR-H111 |
| `docs/harness/roadmap/progress/phase-09-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — the kit contract validates, and a kit without its acceptance test fails to load
./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_contract.py -v

# G2 — scaffolding into a worktree, then the AREA'S OWN CHECK
./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_scaffold.py -v

# G3 — every kit's acceptance test (this is the real gate)
./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_market_data_adapter.py \
    python/tests/test_kit_ratio_calculator.py python/tests/test_kit_backtest_strategy.py \
    python/tests/test_kit_portfolio_module.py python/tests/test_kit_data_ingestion_pipeline.py -v

# G4 — the UNAVAILABLE path is exercised for every generated artefact
./scripts/vendor/python/python.exe -m pytest -k unavailability -q

# G5 — the mcp_server kit starts, lists its tools, and passes config validation
./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_mcp_server.py python/tests/test_mcp_example_config.py -v

# G6 — a generated research workflow loads and stays INERT
./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_research_workflow.py -v
# expected: loader loads it; evaluation runs; enabled is still false

# G7 — no scaffold escapes its declared output set, and the user's checkout is untouched
./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_scaffold.py -k "outside or checkout" -v

# G8 — the suite, the gate, and the plain-language gate
npm run test && npm run check:all
npx vitest run src/lib/i18n/plain-language.test.ts

# G9 — nothing else moved
git status --short        # jdds.db must NOT appear; the user's checkout unchanged
```

| Gate | Assertion |
|---|---|
| G1 | Every kit manifest validates; a missing acceptance test or an undeclared `produces` entry fails the load. |
| G2/G3 | Each scaffolded kit passes the check the **repo** would run for that area — not a kit-local stub. |
| G4 | Every generated artefact returns `UNAVAILABLE` (never a default or synthetic series) when its data is absent, and its generated test proves it. |
| G6 | A generated workflow is inert: loaded, evaluable, **not enabled**. |
| G7 | Nothing is written outside `produces`; a pre-existing dirty file in the user's checkout is hash-identical afterwards. |
| G8 | Full suite + gate green; every kit string passes the plain-language gate. |
| G9 | No `*.db` change. |

## 10. Definition of done

- All eight kits scaffold and pass their area's own check in a worktree.
- Every kit has an acceptance test that ships **with** it and fails if it is missing.
- The `UNAVAILABLE` path is covered for every generated artefact.
- A generated workflow is provably inert until the user enables it.
- `scaffold_kit` writes nothing outside `produces` (tested).
- ADR-H111 written; CHANGELOG + NAVIGATION updated; `status:` flipped.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 9 — Finance application scaffold kits (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-09-scaffold-kits.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3 incl. 3.3 inert artefacts and 3.4 never fabricate)
- agentic-plan-implementaion.md §15 (the target artefact list this phase delivers)
- python/harness/skills/manifest.py + loader.py ← the manifest discipline to mirror
- python/harness/retrieval/{sources,contract,planner,policies}.py ← the adapter convention
- python/harness/research/calculations.py ← the calculator convention
- python/harness/mcp/config.py ← the MCP server convention
- src/lib/portfolio/matrix.ts ← the portfolio convention
- scripts/import-*.js ← the ingestion convention
- python/harness/code/{patch,worktree,commands,tools}.py (Phases 2–3) ← how a write
  lands and how checks run
- python/harness/code/verify.py (Phase 4) ← where the checks are recorded

Goal: make "build me X" produce a real, working, VERIFIED artefact, not prose.

In scope:
1. The kit contract per §6.1 (kit.json: id, version, title, summary_key, produces
   (CLOSED list), requires.inputs (typed + prompt_key), conventions, checks
   (command classes — never free shell), acceptance) + a loader that validates it
   and REFUSES to load a kit with no acceptance test or an undeclared produces entry.
2. Eight kits per §6.2, each satisfying the repo convention named in the table:
   market_data_adapter, mcp_server, ratio_calculator, backtest_strategy,
   chart_indicator, portfolio_module, data_ingestion_pipeline, research_workflow.
   Each ships template files + manifest + the generated test + a docstring explaining
   WHY the shape is what it is.
3. scaffold_kit tool: read_only=False, required_permissions=("code.write",); renders
   into the TASK'S WORKTREE (never the user's checkout); runs the kit's checks via
   Phase 3 command_run; records them in the Phase 4 ledger. Refusals KIT_UNKNOWN /
   KIT_INPUT_MISSING / KIT_INPUT_INVALID / SANDBOX_UNAVAILABLE / CHECK_FAILED (keep
   the scaffold for inspection) / OUTPUT_OUTSIDE_DECLARED_SET.
4. Thin draft skill wrappers so each kit is reachable through the EXISTING
   skill_invoke path with the EXISTING permission model (requiredTools:
   ["scaffold_kit"]) — a wrapper can never grant anything.
5. The anti-fabrication generation rule per §6.5: every generated adapter/backtest/
   ingestion path MUST return UNAVAILABLE when its data is absent (never a default,
   never a synthetic series, never an extrapolation); every generated test MUST
   exercise that branch; a generated backtest states its period and inputs and never
   presents an in-sample metric as predictive; a generated ingestion pipeline is
   IDEMPOTENT (running it twice does not duplicate state) and its test proves it.
6. Every kit's user-facing title/summary/question/result as i18n KEYS in
   src/lib/i18n/ (dictionaries/en.ts canonical, dictionaries/index.ts, translate.ts,
   use-t.ts). The user asks in words and answers in words ("How far back should it
   look — 1 year, 5 years, or as far as the data goes?"), never a parameter name.
7. Tests: test_kits_contract.py, test_kits_scaffold.py, one test_kit_<id>.py per kit
   (the acceptance test), plus extend python/tests/test_plain_language.py.
8. ADR-H111 in docs/harness/decisions.md (Decision / Why / Consequences; use H111).
9. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No arbitrary system generation — exactly the eight named shapes.
- NO trading, order or broker code, ever. A kit touching an order path does not ship.
- No deployment/publishing/packaging kit.
- A kit never writes outside its declared produces set; a generated artefact NEVER
  self-activates (no auto-enabled skill, no auto-registered tool).
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: scaffold_kit registers on the existing ToolRegistry and runs through
  the existing graph; checks run through the existing command broker.
- Policy and permissions stay in code.
- New logic in new modules; keep graph.py/persistence.py/main.py under their ratchets.
- Build the SMALLEST kit (ratio_calculator) end to end first as the reference shape,
  then the rest.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-09-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_contract.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_scaffold.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_market_data_adapter.py python/tests/test_kit_ratio_calculator.py python/tests/test_kit_backtest_strategy.py python/tests/test_kit_portfolio_module.py python/tests/test_kit_data_ingestion_pipeline.py -v
  ./scripts/vendor/python/python.exe -m pytest -k unavailability -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_mcp_server.py python/tests/test_mcp_example_config.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_research_workflow.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_kits_scaffold.py -k "outside or checkout" -v
  npm run test && npm run check:all
  npx vitest run src/lib/i18n/plain-language.test.ts
  git status --short

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 10 — Self-improvement v2](./phase-10-self-improvement.md)
