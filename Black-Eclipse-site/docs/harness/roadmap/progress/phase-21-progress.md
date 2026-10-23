---
title: "Phase 21 — Editable Notebook Cells in Chat — Progress"
status: Done
last-verified: 2026-10-22
---

# Phase 21 — Progress

## Implemented

- **Cell document** — `.black-eclipse/sessions/<chatId>/notebook.json`, bounded
  (100 cells, 20k source chars), source stored verbatim, chart link + inputs.
  `src/lib/chat/notebook-types.ts`, `notebook-store.ts`, `/api/chat/notebook`.
- **Execution route** — `python/harness/routers/notebook.py`:
  `POST /notebook/cells/{id}/run` and `POST /notebook/kernel/restart`. The route
  fixes `extra_imports=("io", "matplotlib")`, `persist_namespace=True`, and
  `input_kinds` (a chart spec is `json`). It reuses `analysis_run` — the same
  sandbox, kernel, artifact registration and `computed` provenance.
- **Persistent namespace** — `AnalysisRequest.persist_namespace` (default
  false); the kernel worker keeps one globals dict only when the command carries
  `persist`. `analysis_run` never sets it.
- **Chart codegen** — `python/harness/charts/codegen.py`, `POST /charts/code`:
  a matplotlib starting script from a resolved spec + an `unsupported` list.
  The chart block is unchanged.
- **Surface** — `NotebookProvider` / `NotebookPanel` / `NotebookCellView`
  (Monaco, Run, Restart, outputs, artifacts, computed label), the composer
  "Notebook" action in the ChatBot tab and the dock, and the chart card's
  "Edit code" action.
- **i18n** — `notebook.*` slice; `plain-language.test.ts` covers the new prefix.

## Gates run

```text
node scripts/test-python.js python/tests/test_chart_codegen.py \
  python/tests/test_notebook_kernel.py python/tests/test_notebook_route.py
20 passed in 4.11s

npx vitest run src/lib/chat/notebook-store.test.ts \
  src/lib/harness/notebook-client.test.ts src/lib/i18n/plain-language.test.ts
Test Files  3 passed (3)
Tests       11 passed (11)

npx tsc --noEmit
(clean)

node scripts/test-python.js
8160 passed, 27 skipped (including the size-budget ratchet)

npx vitest run
Test Files  384 passed (384)
Tests       3824 passed (3824)
```

End-to-end smoke (real sandbox + Artifact Center):

```text
{'status': 'ok', 'outputs': {'points': 3}, 'durationMs': 563, 'error': None}
[{'id': 'art_…', 'name': 'smoke.png', 'mimeType': 'image/png',
  'downloadUrl': '/artifacts/art_…/download'}]
{'kind': 'computed', 'label': 'Worked out by Eclipse',
 'detail': 'a notebook cell the user ran', 'sourceDigest': '…'}
```

A generated script for every supported simple kind (line, area, bar,
stackedBar, pie, donut, scatter, histogram, candlestick) and a scene both ran
`status=ok` and produced `chart.png`; the scene named `violin` as unsupported.

## Remaining / follow-ups

- A true `.ipynb` export is still out of scope (Phase 21 §4).
- A chart cell's edited output is a new picture; it does not mutate the original
  chart block, by design.
- The full suite is green: 8160 Python tests and 3824 TS tests passed.
