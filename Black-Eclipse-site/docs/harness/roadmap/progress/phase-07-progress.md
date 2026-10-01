---
title: "Phase 7 — Progress log (delegation and child runs)"
phase: 7
status: Done
last-verified: 2026-10-01
---

# Phase 7 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-07-delegation.md`.

Baseline before Phase 7 (Phase 6 close): vitest 172 / 1975; pytest 2038;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — narrowing: a child can never widen (negatives first)
- [x] G2 — fan-out + aggregation
- [x] G3 — the caps, proven not asserted (width / depth / unheld tool / budget)
- [x] G4 — a child's unbacked claim never reaches the parent's answer
- [x] G5 — no orphan child after a cancel; no second execution path
- [x] G6 — `npm run test` && `npm run check:all`
- [x] G7 — plain language: progress and summary strings
- [x] G8 — `git status --short` (jdds.db absent; no unexpected artefact)

## Raw gate output

G1 — narrowing negatives:
```
python/tests/test_delegation_narrowing.py  ..............  [100%]
14 passed in 0.07s
```

G2 — fan-out + aggregation:
```
python/tests/test_delegation.py + test_delegation_aggregation.py  ....................  [100%]
20 passed in 1.16s
```

G3 — the caps:
```
python/tests/test_delegation.py -k "width or depth or budget"  ...  [100%]
3 passed, 7 deselected  (width → DELEGATION_WIDTH_EXCEEDED;
                         depth → DELEGATION_DEPTH_EXCEEDED;
                         budget → DELEGATION_BUDGET_EXHAUSTED)
```
(The unheld-tool refusal is asserted in `test_delegation.py::
test_unheld_tool_is_refused_for_the_child_not_the_whole_delegation` and
`test_delegation_tool.py::test_delegate_narrowing_uses_the_parents_allowlist`.)

G4 — a child's unbacked claim never reaches the answer:
```
python/tests/test_delegation_aggregation.py -k dropped_claims -v
  test_dropped_claims_a_pass_claim_with_no_handle_is_dropped PASSED
  test_dropped_claims_a_pass_claim_with_a_nonexistent_ledger_row_is_dropped PASSED
  test_lying_child_claim_lands_in_dropped_claims_and_not_the_answer PASSED
3 passed, 7 deselected
```

G5 — cancel safety:
```
python/tests/test_delegation.py -k cancel -q
1 passed, 9 deselected
```

G6 — release gate:
```
 Test Files  172 passed (172)
      Tests  1975 passed (1975)
python: 2080 passed, 1 warning
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```
Vitest 172/1975 (no new vitest nodes — Phase 7 is runtime-only; no new UI
strings beyond i18n-free runtime copy). Pytest 2038 → 2080 (the four new
`test_delegation*` files: 14 + 20 + 6 + 2 plain-language = 42, plus the two
`test_code_agent.py` assertions updated to admit `delegate`).

G7 — plain language:
```
src/lib/i18n/plain-language.test.ts  4 passed
python/tests/test_plain_language.py -k delegation  2 passed, 10 deselected
```

G8 — `git status --short`: no `*.db`; new files are the delegation modules,
their tests, and the progress doc only.

```
?? python/harness/delegation.py
?? python/harness/delegation_tools.py
?? python/tests/test_delegation.py
?? python/tests/test_delegation_aggregation.py
?? python/tests/test_delegation_narrowing.py
?? python/tests/test_delegation_tool.py
 M docs/CHANGELOG.md  docs/NAVIGATION.md  docs/harness/decisions.md
 M docs/harness/roadmap/README.md  docs/harness/roadmap/phase-07-delegation.md
 M python/harness/{agents,code/tools,graph,prompts,tools}.py
 M python/tests/{test_memory_tools,test_plain_language}.py
```

## Recon findings / deviations (reported, not silent)

- **Tool-name reality.** The phase file names a `delegate` tool and a
  `VerifiableHandle`/`child_actor`/aggregation surface; those are exactly what
  landed. The `required_permissions=("skill.invoke",)` idea was dropped: the
  `ToolDefinition` contract has no such field, and every child already re-checks
  permissions through `execute_run`/`execute_skill` on its NARROWED actor, so the
  delegation seam itself is `permission="read"`.
- **Size ceiling.** `code/tools.py` would have crossed 1200 lines (the Python
  hard ceiling) with the handler inline, so the handler + schema were extracted
  into the new `python/harness/delegation_tools.py` — the same "new logic in new
  modules" rule that keeps `code/tools.py` under its ceiling. Registration stays
  in `code/tools.py` (one line importing the handler).
- **Depth propagation.** A child's `RunInput.context["delegationDepth"]` is set to
  `parent_depth + 1`, so a grandchild cannot reset depth to 0 and bypass
  `MAX_DEPTH`. The graph reads it into `ToolContext.delegation_depth`.
- **Prompt ratchet.** `ECLIPSE_AGENT_SYSTEM_PROMPT` gained one capability
  paragraph ("Working on several things at once"); the `test_prompt_char_ceiling`
  ratchet was raised 17500 → 18000 deliberately (still a 500-char allowance).
- **Aggregation strictness.** `partition_claims` admits a check-claim ONLY with a
  verified `check_record_id`; a `run_id` handle does not back a pass-claim, so a
  child cannot launder one by attaching an unrelated handle.
- **One execution path.** `delegate_handler` calls `execute_run` (patched in tests
  to prove it) with `parentRunId` set; there is no second loop, registry or model
  adapter. `run_lineage.py` remains the ONE linkage.
