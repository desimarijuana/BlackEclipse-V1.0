---
title: "Phase 9 — Progress log (finance application scaffold kits)"
phase: 9
status: Done
last-verified: 2026-10-01
---

# Phase 9 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-09-scaffold-kits.md`.

Baseline before Phase 9 (Phase 8 close): vitest 173 / 1981; pytest 2135;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — the kit contract validates; a kit without its acceptance test fails to load
- [x] G2 — scaffolding into a worktree, then the area's own check
- [x] G3 — every kit's acceptance test
- [x] G4 — the UNAVAILABLE path is exercised for every generated artefact
- [x] G5 — the mcp_server kit validates as an MCP config
- [x] G6 — a generated research workflow loads and stays INERT
- [x] G7 — no scaffold escapes its declared output set; the checkout is untouched
- [x] G8 — the suite, the gate, the plain-language gate
- [x] G9 — nothing else moved

## Raw gate output

G1 — the kit contract:
```
python/tests/test_kits_contract.py  .......  [100%]
7 passed in 0.54s
```

G2 — scaffolding into a worktree:
```
python/tests/test_kits_scaffold.py  ......  [100%]
6 passed in 2.69s
```

G3 — every kit's acceptance test:
```
python/tests/test_kit_market_data_adapter.py  ...
python/tests/test_kit_ratio_calculator.py     .....
python/tests/test_kit_backtest_strategy.py    ..
python/tests/test_kit_portfolio_module.py     ..
python/tests/test_kit_data_ingestion_pipeline.py  ..
python/tests/test_kit_mcp_server.py           ...
python/tests/test_kit_chart_indicator.py      ..
python/tests/test_kit_research_workflow.py    ...
22 passed in 0.96s
```

G4 — the UNAVAILABLE path for every generated artefact:
```
python/tests -k unavailability -q
5 passed, 2169 deselected
```

G5 — the mcp_server kit validates as an MCP config:
```
python/tests/test_kit_mcp_server.py  ...  [100%]
3 passed
```

G6 — a generated workflow loads and stays INERT:
```
python/tests/test_kit_research_workflow.py  ...  [100%]
3 passed in 0.52s
```

G7 — no escape from the declared set; the checkout is untouched:
```
python/tests/test_kits_scaffold.py -k "outside or checkout"  .  [100%]
1 passed, 5 deselected
```

G8 — release gate:
```
 Test Files  173 passed (173)
      Tests  1981 passed (1981)
python: 2178 passed, 1 warning
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```
Vitest 173/1981 (unchanged — the i18n additions extend existing test files).
Pytest 2135 → 2178 (the new kit tests: 7 + 6 + 5 + 22 + 2 + 2 = 44, plus the
updated `test_code_agent`/`test_skills_api`/plain-language nodes).
Plain language: `src/lib/i18n/plain-language.test.ts` 4 passed;
`python/tests/test_plain_language.py` 16 passed (2 new kit nodes).

G9 — `git status --short`: no `*.db`; new files are the kit library, the eight
skill wrappers, the scaffold handler, the kit tests, and the progress doc.

## Recon findings / deviations (reported, not silent)

- **Kit folder layout.** A kit's templates mirror the repo path under
  `templates/` (e.g. `templates/python/harness/retrieval/<name>.py.tmpl`), so a
  rendered file lands at its real location. A declared `produces` path carries a
  `{{module_name}}` token substituted at render time; the closed-set check
  compares against the RENDERED declared paths.
- **`checks` may be empty.** The contract's `checks` run through the Phase 3
  broker. Two kits (`chart_indicator`, `research_workflow`, `data_ingestion_
  pipeline`'s workflow siblings) verify instead by their shipped acceptance test,
  so `checks` is optional (the required `acceptance` string and the shipped
  `test_kit_<id>.py` are the guarantee). Kits with a runnable check declare it.
- **Acceptance test is the load gate.** `load_kit` refuses a kit with no
  `python/tests/test_kit_<id>.py` (`KIT_NO_ACCEPTANCE_TEST`) — the test is
  authored with the kit, not after it.
- **Skill wrappers under `system`.** The eight wrappers live in
  `skills/library/system/` (category `system`) rather than `research`, because a
  Phase-3 test asserts the exact `research`-category id set. They are all
  `status: draft` and inert, and declare only `analysis.execute` + the scaffold
  tools — never an operator permission.
- **Size ceiling.** The `scaffold_kit` handler lives in the new
  `scaffold_tools.py` (imported lazily by `code/tools.py` to avoid a cycle), so
  `code/tools.py` stays under 1200 lines.
- **`policy.WRITE_TOOLS` gained `scaffold_kit`**, so the autonomy boundary removes
  it structurally at `plan_only` (the allowlist is the boundary, not a prompt).
- **Installed-skill count.** `test_skills_api.py` moved 5 → 13 (the eight draft
  wrappers now ship in the library).
- **Prompt ratchet.** `ECLIPSE_AGENT_SYSTEM_PROMPT` gained one "Building a tool"
  paragraph; `test_prompt_char_ceiling` raised 18000 → 18600 deliberately.
- **Line-ending sweep.** A `Add-Content` appended text introduced CRLF; all
  touched text files were normalized to LF. Several pre-existing CRLF docs and
  generated Prisma files that the sweep also touched were restored to HEAD so
  only intended files are in this change.
- **Flaky sandbox test.** `test_code_sandbox.py::test_kill_leaves_no_orphan_python_process`
  failed once under full-suite load and passed in isolation and on the re-run —
  a pre-existing timing sensitivity, not a Phase 9 regression.
