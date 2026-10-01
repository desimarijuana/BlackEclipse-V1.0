---
title: Prompt follow-up — correctness, honesty and guard coverage (progress)
status: Current
last-verified: 2026-10-01
---

# Prompt follow-up (progress log)

Follow-up to `prompt-v2-finance-harness-progress.md` / ADR-H104. Four surgical
edits to two prompt strings (`python/harness/prompts.py`) plus guards. No tool,
permission, capability or module added.

## Gap 1 reproduction (verbatim, before)

```
ECLIPSE_AGENT chars: 17443 headroom to 17500: 57
NAVIGATOR allowlist: ['workspace_status', 'workspace_list', 'workspace_search', 'workspace_read', 'workspace_docs', 'workspace_patch_apply', 'workspace_diff', 'workspace_revert', 'command_run']
prompt claims exactly 5 read tools: False
prompt says cannot run commands: True
prompt also documents command_run: True
```

(`prompt claims exactly 5 read tools` is False because the marker sentence is
split across the code block; the literal five-tool claim was present in the
prompt text — "Your tools are exactly `workspace_status`, …, `workspace_read`
and `workspace_docs`.")

## What changed

- **Gap 1 (HIGH).** `## What you can do` now states the capability **by group**
  and defers to the bound schemas instead of naming a false count. `## What you
  cannot do` now says the genuinely-unavailable set: no arbitrary program or
  shell command, no install, no network — `command_run` only runs a fixed
  allowlisted set the model selects by name. `## Running checks` untouched.
- **Gap 2 (MED).** Removed the phantom `run instructions` authority: the rank
  row was deleted and the table renumbered 1–6. Decision: **remove, not wire**
  (reasoning below). Also removed the `run_instructions` prompt segment.
- **Gap 3 (LOW-MED).** Identity no longer hardcodes a surface enumeration
  ("today a finance retrieval, memory and skill toolset"); it says it acts only
  through the bound tools. "valuation and modelling" → "valuation", with
  models/analytics framed as subject matter explained, not executed.
- **Gap 4 (LOW).** Deleted the duplicated "Keep answers decision-focused and
  cite the evidence you used." (owned by `# Answer contract`) — the markdown
  sentence remains. The bound-schemas statement is now owned by `## Your tools`
  alone.
- **Gap 5 (MED).** Generalised guards in `test_memory_tools.py` across both
  presets.

## Gap 2 decision — remove, not wire

Removed. There is no producer for `run_instructions` anywhere in the runtime
(no `schemas.py` field, no TS bridge field, and the sole `build_prompt_plan`
caller in `graph.py` never passed it), so ranking it #2 elevated a source that
never arrives while profile context — which does arrive every run — sat below
it. Wiring a real producer would add a new input surface, which the task's
constraints forbid ("no new module, no new capability"). This matches the
session_summary precedent from the prior pass.

## Final numbers (measured)

- `ECLIPSE_AGENT_SYSTEM_PROMPT`: **17,294 chars / 2,615 words / ~4,324 est.
  tokens** (from 17,443), headroom 206 under the 17,500 ceiling.
- `CODE_NAVIGATOR_SYSTEM_PROMPT`: **2,947 chars** (new ceiling 3,000).

Section table after (finance agent): identity 1,500; Operating principles 501;
Inputs and authority 906; Research 1,029; Market data semantics 1,217;
Investment Analysis 1,560; Financial Engineering 410; Finishing the job 391;
Answer contract 843; MCP tools 1,059; Tool calls 1,190; Prior sessions 513;
Skills 799; Skill Safety Rule 272; Mid-turn steering 656; Tool-use enforcement
501; Execution discipline 2,129; Runtime awareness 623; Your tools 720; Memory &
self-improvement 475.

## Tests added

- `test_prompt_may_not_deny_a_capability_its_allowlist_contains`
- `test_every_prompt_tool_name_is_in_its_allowlist`
- `test_prompt_does_not_enumerate_only_a_subset_of_its_allowlist`
- `test_has_no_duplicated_rule_sentences` (both presets; supersedes/extends the
  finance-only version)
- `test_navigator_prompt_char_ceiling`
- `test_navigator_prompt_matches_its_real_surface`
- `test_run_instructions_segment_is_removed` (`test_prompt_segments.py`)
- extended `test_prompt_inputs_authority_and_attachments_present`
- extended `test_every_prompt_tool_name...` uses a per-prompt allowlist join.

Imprecision noted: `test_prompt_does_not_enumerate_only_a_subset_of_its_allowlist`
fires only when a prompt contains the phrase "tools are exactly"; the navigator
no longer does, so for it the check is structurally enforced by
`test_every_prompt_tool_name_is_in_its_allowlist` (names ⊆ allowlist) rather than
the stronger set-equality. That is the honest state.

## Checks (real)

- `./scripts/vendor/python/python.exe -m pytest python/tests -q` (full suite,
  green run at 1:14 PM before the concurrent writes) → **1940 passed, 1 warning
  in 165.21s**.
- `./scripts/vendor/python/python.exe -m pytest python/tests/test_memory_tools.py
  python/tests/test_prompt_segments.py python/tests/test_surface_honesty.py -q`
  (this change's suites) → **50 passed in 1.42s**.
- `npm run check:all` → **EXIT=1**. prisma generate, tsc and eslint passed;
  vitest **1969 passed (170 files)**; python **1961 passed, 1 failed**.
  - The one failure is `test_code_approvals.py::test_mcp_approval_still_single_use`
    (`KeyError: 'kind'`), in the concurrent code-broker agent's in-flight test
    file (`test_code_approvals.py` mtime 1:21:06). It contains no prompt
    references and is unrelated to this change.
  - An earlier attempt hit **EXIT=2** with 20 collection errors:
    `pydantic ValidationError: runTimeoutMs Input should be less than or equal to
    600000 [input_value=900000]` from the concurrent `CODE_AGENT` preset
    (`agents.py` 1:16:20) against `schemas.py`'s 600000 cap (1:15:53). The
    concurrent agent fixed `agents.py` at 1:19:49 — imports recovered.
  - **Both are contamination, not regressions from this change.** The failing
    files (`agents.py`, `schemas.py`, `test_code_approvals.py`, `tools.py`) are
    untouched by this work, and this change's own suites are green.

## Known limits / next action

- The release gate's single remaining failure lives in the concurrent code-agent
  work and is out of scope for this prompt pass.
- Next action: none pending for this change.
