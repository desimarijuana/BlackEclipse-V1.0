# OpenCode Prompt — Prompt follow-up: correctness, honesty and guard coverage

You are continuing work in the BlackEclipse repository. A prompt pass just landed
(`docs/harness/prompt-v2-finance-harness-progress.md`, ADR-H104,
`ECLIPSE_AGENT_SYSTEM_PROMPT` = 17,443 chars / ~4,361 est. tokens, under the
17,500 ceiling). It is good work. These are the residual defects it left behind —
one of them a real correctness bug in a *different* prompt.

Small, surgical change. Four edits to two prompt strings plus tests. No new
module, no new tool, no permission change, no capability claim.

## Reproduce first (before any edit)

Run these and record the output verbatim in the progress doc:

```bash
cd Black-Eclipse-site
./scripts/vendor/python/python.exe -c "
import sys; sys.path.insert(0,'python')
from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as A, CODE_NAVIGATOR_SYSTEM_PROMPT as N
from harness.agents import CODE_NAVIGATOR
print('ECLIPSE_AGENT chars:', len(A), 'headroom to 17500:', 17500-len(A))
print('NAVIGATOR allowlist:', CODE_NAVIGATOR.tools)
print('prompt claims exactly 5 read tools:', 'workspace_read\` and \`workspace_docs' in N)
print('prompt says cannot run commands:', 'You cannot run any command' in N)
print('prompt also documents command_run:', 'command_run' in N)
"
```

## Gap 1 (HIGH — real bug) — the Repository Navigator prompt contradicts its own allowlist

`CODE_NAVIGATOR_SYSTEM_PROMPT` (`python/harness/prompts.py`) tells the model two
things that are false about the runtime it describes, and then contradicts
itself:

1. `## What you can do` — *"Your tools are exactly `workspace_status`,
   `workspace_list`, `workspace_search`, `workspace_read` and `workspace_docs`."*
   That is 5 tools. `CODE_NAVIGATOR_TOOLS` (`python/harness/agents.py`) has **9**:
   the five read tools **plus** `workspace_patch_apply`, `workspace_diff`,
   `workspace_revert`, `command_run`.
2. `## What you cannot do — say so plainly` — *"You cannot run any command,
   install anything, or reach the network. There is no tool for it."* But
   `command_run` **is** in the allowlist and **is** registered
   (`python/harness/code/tools.py:233`), and the prompt's own later section
   `## Running checks` documents it in detail.

So the model is told, in one prompt, that it has exactly five read tools, that it
cannot run any command, and that it can run allowlisted checks with
`command_run`. A user asking "can you run the tests?" or "can you fix this?" gets
an answer derived from whichever of those three statements the model weights
most. There is **no test** asserting the navigator prompt matches its preset
(`grep -rn CODE_NAVIGATOR_SYSTEM_PROMPT python/tests/` returns nothing).

**Fix.**

1. Rewrite `## What you can do` to name the real surface — list all nine, or
   better, state the capability by group and let the bound schemas be
   authoritative (the pattern `## Your tools` already uses for the finance
   agent).
2. Rewrite `## What you cannot do` to be true. What is genuinely unavailable is
   now narrower: **no arbitrary shell or program**, **no package install**, and
   **no network reach**. `command_run` only runs a fixed, allowlisted set of
   checks that the model selects by name — it never supplies a program or a
   command. Say that. Keep the honest "say so plainly and offer what you can do"
   instruction — it is good and it is the section's real value.
3. Do not weaken the `## Running checks` honesty rules ("Only report a check as
   passing if you actually ran it and it exited cleanly") — that section is
   correct as written; the other two are what is wrong.
4. Do not widen the navigator's allowlist. This is a prompt-accuracy fix, not a
   capability change.

## Gap 2 (MED) — precedence rank 2 is a phantom

`# Inputs and authority` ranks **`run instructions` #2**, above attached
documents, tool evidence and profile context. No caller ever populates it:
`grep -rn "run_instructions" python/harness/` finds it only in
`prompt_segments.py` (declared as a segment with an empty default), there is no
field for it in `schemas.py` or the TS bridge, and `graph.py:821` — the only
caller of `build_prompt_plan` — does not pass it.

So the prompt elevates a source that never arrives, while the block that arrives
every run (profile context) is ranked 5th. This is the same defect class the last
pass correctly fixed for `session_summary` by removing it.

**Fix — pick one and say which and why:**
- **Remove** the `run instructions` row and its `prompt_segments.py` segment
  (the honest option, and consistent with the `session_summary` precedent), or
- **Wire a real producer** and document where it comes from. Do not leave a
  ranked authority with no source.

If you remove the row, renumber the table.

## Gap 3 (LOW-MED) — identity sentence over-claims and is wrong for other surfaces

The identity opens: *"Your whole action surface is exactly the tools bound to
this run — **today a finance retrieval, memory and skill toolset** — and nothing
else."*

The parenthetical is a hardcoded claim about the surface. `agents.py` supports
other surfaces: the `code-navigator` preset (9 workspace/command tools), custom
agents, and skill child-runs each carry their own allowlist. If this prompt ever
runs with one of those, the sentence is false — the exact defect class the M5
identity fix set out to eliminate.

Separately, the domain list still contains **"valuation and modelling"** while
the allowlist has no modelling tool, and only capability *beyond* the surface is
disclaimed ("beyond it"). Under M5's own standard — state action capability as
exactly the bound surface — "and modelling" is ambiguous between domain and
action.

**Fix.** Drop the "today a finance retrieval, memory and skill toolset"
enumeration; the existing sentence "the bound tool schemas are authoritative and
can drift from any prose description" (in `## Your tools`) already carries this
correctly. Resolve "valuation and modelling" to something unambiguous (domain
competence, not a tool), or drop "modelling" from the capability clause and keep
it in the domain list only if it reads as subject matter.

## Gap 4 (LOW — efficiency) — two redundant restatements

Both verified verbatim:

1. Line 125: *"Keep answers decision-focused and cite the evidence you used."* —
   duplicates the whole `# Answer contract` section, which specifies the shape,
   the citation format and the numeric conventions.
2. Identity vs `## Your tools`: "exactly the tools bound to this run" appears
   twice (identity preamble and `## Your tools`).

The char ceiling is a **ratchet with only 57 chars of headroom** (17,443 of
17,500), so any net growth breaks `test_prompt_char_ceiling`. Removing these two
duplications both improves the prompt and buys room.

**Fix.** Delete the redundant restatements. Keep `# Answer contract` as the one
owner of the output spec, and `## Your tools` as the one owner of the
bound-schemas statement. Keep the markdown/GitHub-flavor sentence — that one is
not duplicated anywhere.

## Gap 5 (MED — process) — guard coverage does not extend to the second prompt

The last pass added real guard tests, but they cover only the finance agent:
- `test_prompt_char_ceiling`, `test_prompt_market_data_semantics_present`,
  `test_prompt_inputs_authority_and_attachments_present`,
  `test_prompt_has_no_duplicated_rule_sentences` all read
  `ECLIPSE_AGENT_SYSTEM_PROMPT`.
- Nothing asserts `CODE_NAVIGATOR_SYSTEM_PROMPT` agrees with
  `CODE_NAVIGATOR.tools` — which is exactly why Gap 1 went unnoticed.

**Fix.** Add guard tests that apply to **both** presets:
1. Every tool a prompt names as one of its own must be in that preset's
   allowlist, and every allowlist entry that the prompt claims to enumerate must
   be named (the test that would have caught Gap 1).
2. A prompt may not assert it *cannot* do something its allowlist contains, and
   vice versa ("you cannot run any command" + `command_run` in the allowlist).
3. A char ceiling for `CODE_NAVIGATOR_SYSTEM_PROMPT` (it has no ceiling today).
4. The duplicate-sentence check extended to the navigator prompt.

If any part of a generalised check is impractical, say which and why rather than
skipping it silently.

## Constraints

- **Net-shrink or hold**: after the edits `ECLIPSE_AGENT_SYSTEM_PROMPT` must
  still be ≤ 17,500 chars. Report the exact final number.
- Do not add, widen, or imply any tool, permission or capability. Gap 1 changes
  the prompt to match the allowlist — never the allowlist to match the prompt.
- Keep `filter_system_prompt` behaviour intact (memory/session guidance still
  drops when those stores are off; base constants stay byte-stable).
- No new dependency, no TS prompt assembly, no new module.
- Never fabricate a number, a test result or a doc claim.

## Checks (run these and report real output)

```bash
cd Black-Eclipse-site
./scripts/vendor/python/python.exe -m pytest python/tests -q
npm run check:all
```

Report the real exit status. If a failure is pre-existing or contamination from
the concurrent agent, say so with the evidence — compare the failing file's mtime
against the start of your run before calling it a regression, and never write to
a file modified in the last few seconds.

Then per root `AGENTS.md`: append a dated `docs/CHANGELOG.md` entry, update
`docs/harness/architecture.md` (the owning doc for `prompts.py`), add an ADR-H to
`docs/harness/decisions.md` only if a real decision was made (Gap 2's
remove-vs-wire choice likely qualifies), and update the
`docs/NAVIGATION.md` rows at lines 128 / 335 if the prompt's described contract
changed. Maintain `docs/harness/prompt-followup-progress.md`.

## Explicit non-goals

- No prompt-evaluation harness and no scoring set (a separate, user-decided
  phase).
- No change to the roadmap's code-broker work (`code/commands.py`,
  `code/sandbox.py`, `code/verify.py`, `code/repair.py`) — Gap 1 edits the
  navigator *prompt* to describe that work accurately, nothing else.
- No change to the memory gate, retrieval ranking, skill lifecycle, MCP trust
  model, or any operator gate.
- No re-litigation of the finance-agent contract itself (M1-M4) — those landed
  and are correct.

## Final report

- The verbatim Gap 1 reproduction (before), and the two rewritten sections
  (after).
- Gap 2's decision (remove vs wire) with reasoning.
- The exact edits for Gaps 3 and 4, and the final
  `ECLIPSE_AGENT_SYSTEM_PROMPT` char count against the ceiling.
- Test names added, real pass counts, and the `npm run check:all` result.
- `docs updated: <file(s)>` or `no doc change — <reason>`.
