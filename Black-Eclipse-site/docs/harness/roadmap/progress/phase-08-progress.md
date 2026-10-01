---
title: "Phase 8 — Progress log (analysis sandbox: computing, not just retrieving)"
phase: 8
status: Done
last-verified: 2026-10-01
---

# Phase 8 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-08-analysis-sandbox.md`.

Baseline before Phase 8 (Phase 7 close): vitest 172 / 1975; pytest 2080;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — execution + limits
- [x] G2 — the provenance rule, including the fail-closed case
- [x] G3 — reproducibility: same source + inputs ⇒ same output digest
- [x] G4 — a computed number cannot become a research claim
- [x] G5 — an import outside the allowlist is refused; network still fails
- [x] G6 — recipes, each with its honest missing-input path
- [x] G7 — the suite, the gate, the plain-language gate
- [x] G8 — nothing else moved

## Raw gate output

G1 — execution + limits:
```
python/tests/test_analysis_execution.py  ............  [100%]
12 passed in 1.89s
```

G2 — the provenance rule (fail-closed: computed with no record ⇒ UNAVAILABLE;
no path yields retrieved):
```
python/tests/test_analysis_provenance.py  .............  [100%]
13 passed in 0.23s
```

G3 — reproducibility:
```
python/tests/test_analysis_execution.py -k reproducible  .  [100%]
1 passed, 11 deselected
```

G4 — a computed number cannot become a research claim:
```
python/tests/test_analysis_provenance.py -k "not_evidence or receipt"  ...  [100%]
3 passed, 10 deselected
```

G5 — imports + network:
```
python/tests/test_analysis_execution.py -k "import or network"  ....  [100%]
4 passed, 8 deselected
```

G6 — recipes:
```
python/tests/test_analysis_recipes.py  ......................  [100%]
22 passed in 1.35s
```

G7 — release gate:
```
 Test Files  173 passed (173)
      Tests  1981 passed (1981)
python: 2135 passed, 1 warning
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```
Vitest 172/1975 → 173/1981 (+1 file/+6: `analysis-types.test.ts`). Pytest
2080 → 2135 (the four new `test_analysis_*` files: 12 + 13 + 22 + 6 = 53, plus
2 plain-language nodes).
Plain language: `src/lib/i18n/plain-language.test.ts` 4 passed;
`python/tests/test_plain_language.py` 14 passed (2 new analysis nodes).

G8 — `git status --short`: no `*.db`; artefacts confined to the gitignored
`.black-eclipse/artifacts/`; new files are the analysis modules, their tests, the
front door, and the progress doc only.

## Recon findings / deviations (reported, not silent)

- **AST import check.** `check_imports` walks the source with `ast`; there is no
  `eval`/`exec` on the source string and no regex-only guard. Dynamic imports
  (`__import__`, `importlib`) and `os`/`sys`/`socket`/`subprocess` are flagged by
  name. The runner `compile`s the source INSIDE the isolated child — the parent
  never executes it.
- **Isolated cwd.** The program runs in a temp staging dir (never the repo), and
  the ONLY way it writes a deliverable is the injected `write_artifact(name, data)`
  helper into a declared `output/` folder; nothing else is collected. Raw `open`
  in user source is refused by the import inspection (it is on the flagged list).
- **Size ceiling.** `code/tools.py` would have crossed 1200 lines with the handler
  inline, so the `analysis_run` handler + schema live in the new
  `analysis_tools.py` — the same extraction rule Phase 7 used. Registration stays
  in `code/tools.py`.
- **Permission gate.** The phase names
  `required_permissions=("analysis.execute","code.execute")`; the `ToolDefinition`
  contract has no such field. The enforced gate is `analysis.execute` (held by the
  default SAFE actor, the permission the phase says is the analysis grant) plus
  the Phase 3 sandbox itself; the tool is additionally OFF per run.
- **`RunRequest.analysisEnabled`** plus `ToolContext.analysis_enabled` (default
  False) gate the tool; the graph passes it through one additive line.
- **Finance-agent tool count.** `test_code_agent.py` moved 24 → 26 across Phases 7
  and 8 (`delegate`, then `analysis_run`); both are shared capabilities with no
  finance permission of their own, and both are gated.
- **Concurrent edit.** `python/harness/prompts.py` carried an uncommitted
  one-word copy change ("financial intelligence agent" → "financial intelligence
  Harness") not made by this phase. It is included in the tree the gates ran
  green against and is committed alongside; it is not a Phase 8 deliverable.
- **Prompt ratchet.** No new prompt paragraph was needed for Phase 8 (the tool
  description carries the guidance), so the Phase 7 ceiling of 18000 is unchanged.
