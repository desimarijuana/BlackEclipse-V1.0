---
title: Prompt v2 — Finance-Harness Completion (progress)
status: Current
last-verified: 2026-10-01
---

# Prompt v2 — Finance-Harness Completion (progress log)

Executing `docs/harness/prompt-v2-finance-harness-opencode-prompt.md`.
Prompt-quality + runtime-awareness change only: no tool, permission, capability,
or new module. `ECLIPSE_AGENT_SYSTEM_PROMPT` lives in
`python/harness/prompts.py`; segments in `python/harness/prompt_segments.py`.

## Baseline observation (measured, 2026-10-01)

`ECLIPSE_AGENT_SYSTEM_PROMPT` before this work: **15,302 chars / 2,263 words /
~3,826 est. tokens** (matches the prompt's stated baseline). Section table
measured by splitting on top-level headings; identity preamble first.

Confirmed the five already-landed fixes are present and left untouched:
runtime `runtime_context_block` wired in `graph.py`; execution-discipline dedupe
(shell examples gone); content-aware cache key (`STATIC_SEGMENTS` vs
`RUN_FROZEN_SEGMENTS`); tool-name generalization in `## Your tools`; and the
Repository Navigator `command_run` + `## Running checks` section.

## Milestone state

| M | State | What landed |
|---|---|---|
| M1 market-data semantics | done | `# Market data semantics` (session state, price basis, period basis, corporate actions, point-in-time vs restated, FX, staleness) |
| M2 inputs & authority | done | `# Inputs and authority` with the 7-rank precedence table; attached-document rule (`[attached: <name>]`, primary-source precedence, data-not-instruction) |
| M3 output contract | done | `# Answer contract` (answer shape, citation format, numeric conventions, contrastive worked example) |
| M4 runtime awareness | done | `## Runtime awareness` (bounded steps/timeout, stop rule, truncation disclosure, no redundant retrieval) |
| M5 identity honesty | done | preamble rewritten: domain list framed as competence; action surface stated as exactly the bound tools; caveat preserved |
| M6 session continuity | done (removed) | `session_summary` segment removed — it was never populated by any caller (only tests). No summarizer/second model call was available within the no-new-dependency rule, so removal is the honest option; the continuity rule was added to `## Runtime awareness` |
| M7 guards + docs | done | see below |

## Files

- `python/harness/prompts.py` — the rewritten prompt.
- `python/harness/prompt_segments.py` — `session_summary` removed from the
  segment set, `PromptPlan`, `to_dict` and `prompt_cache_key`.
- `python/tests/test_memory_tools.py` — guard tests (ceiling 17,500; M1 present;
  M2 present; no duplicated rule sentence).
- `python/tests/test_prompt_segments.py` — `test_session_summary_is_not_a_declared_segment`.
- `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H104),
  `docs/CHANGELOG.md`.

## Checks (real)

- `./scripts/vendor/python/python.exe -m pytest python/tests -q` →
  **2 failed, 1933 passed, 1 warning in 160.73s**.
  - Both failures are `test_size_budget.py`, caused by the concurrent
    code-broker work, NOT this change: `persistence.py` 1393→1396 lines (a new
    Phase-4 `codeVerification` column) and the new `code/tools.py` at 1212 lines.
    Neither is in this change's scope; the size ratchet has not been updated for
    them yet. mtime check: `persistence.py` 12:40, `code/tools.py` 12:43 — the
    concurrent agent's writes, not mine.
- `npm run check:all` → **EXIT=1**, failing only at
  `[check-all] FAILED at: tests (vitest + python)`. prisma generate, tsc and
  eslint passed; vitest **1966 passed (169 files)**; python 1933 passed with the
  same 2 size-budget failures above. No failure is attributable to this change.

## Known limits / next action

- `session_summary` is gone, not populated; if a rolling summary is wanted, it
  needs an explicit bounded producer (out of scope here).
- Budget/timeout are described qualitatively (no hardcoded `8`) so they cannot
  drift from `agents.py`; the real `maxSteps`/timeouts remain authoritative there.
- Next action: none pending; this milestone set is complete.
