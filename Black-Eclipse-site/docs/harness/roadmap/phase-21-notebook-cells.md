---
title: "Phase 21 — Editable Notebook Cells in Chat"
status: Done
phase: 21
depends_on: [14, 18]
unlocks: []
last-verified: 2026-10-22
---

# Phase 21 — Editable Notebook Cells in Chat

> **Shipped 2026-10-22.** The cell document, the notebook run/restart routes, the
> opt-in persistent namespace, chart-spec codegen and the Monaco surface are in
> place. Gates: `python/tests/test_{chart_codegen,notebook_kernel,notebook_route}.py`,
> the TS notebook store/client/i18n tests, `npx tsc --noEmit`, the full Python
> suite (8160 passed) and the full Vitest suite (3824 passed). The remaining
> follow-up is `.ipynb` export, which stays out of scope.

| | |
|---|---|
| **Depends on** | Phase 14 (code reachable from chat) and Phase 18 (figures in the analysis sandbox). |
| **Unlocks** | A conversation that can be worked in, not only read. |
| **Estimated work** | 14–20 h of agent time. |
| **Deliverable type** | a per-chat cell document + one execution route + a Monaco cell + a chart-to-cell bridge. |
| **Decision records** | ADR-H323 (the notebook is a sidecar document over the existing sandbox; a chart's code is a linked alternate view) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Non-goals (do not do these)](#4-non-goals-do-not-do-these)
- [5. The shape (read this before the contracts)](#5-the-shape-read-this-before-the-contracts)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

A user asks Eclipse for a chart. Today they get a picture they can zoom, export
and share — but not change. This phase lets them **open the code behind the
chart, edit it, and run it**, and lets any conversation hold a small notebook of
such cells: code in, outputs out, state kept while the conversation's kernel is
alive.

The unit is a **cell attached to a conversation**, not a replacement for chat
messages. A chart block can *link* to a cell; the chart block stays the canonical
declarative answer.

## 2. Why this phase exists

**(a) A chat chart is data, not code.** `chartBlock` (`src/lib/response/contract.ts:372`)
carries `chartType`, `series`/`panels` and an optional `dataSource`.
`chartBlockToSpec` (`src/lib/response/chart-spec.ts:328`) turns it into the
shared `ChartSpec` (`src/lib/harness/charts.ts`), which the browser renders with
ECharts and the Python chart engine also understands; `python_chart` accepts
only that spec (`python/harness/charts/tools.py:236`). Nothing stores a
program, so there is nothing to edit.

**(b) The runtime can already execute and plot, but only the agent can start it.**
`analysis_run` (`python/harness/analysis_tools.py:421`) runs a program in the
Phase 3 sandbox and records artifacts. The figure recipes widen the import
allowlist by a **named** tuple, `extra_imports=("io", "matplotlib")`
(`python/harness/code/recipes.py:371`), and a figure is always `computed`, never
evidence (`python/harness/code/execution.py:205`). There is no operator-driven
surface for the same capability.

**(c) The kernel is warm but not stateful in the Jupyter sense.** A kernel is
kept per conversation (`python/harness/code/kernel.py:1`), but every round builds
a fresh globals dict in `_run`, so variables do not survive from one cell to the
next. A notebook needs an **opt-in** persistent namespace; `analysis_run` must
keep its fresh-namespace semantics.

**(d) A run records a digest, not the source.** `AnalysisResult` carries
`source_digest` and `input_digests` (`python/harness/code/execution.py:248`), so
an edit cannot be recovered after the fact. The cell document must store the
source verbatim; the trace remains the reproducibility record.

**(e) The only notebook today is operator-only and dataset-bound.**
`src/components/screens/research-data/research-data-screen.tsx:406` runs a
textarea against a materialized dataset. It is the right sandbox, not the right
surface: it is not per-conversation and it cannot be reached from a chart.

**(f) Honesty has to survive editing.** A chart is persuasive and its provenance
is easy to lose. Edited code is still a computation: it must be labelled
`computed`, must not become evidence, and must not write back into the chart
block, a research claim, or `jdds.db`.

## 3. In scope

1. A per-conversation **cell document** stored beside the transcript.
2. One **notebook run route** over the existing `run_analysis` and sandbox.
3. A **Monaco cell** with Run/Stop/Restart and text/table/image/figure outputs.
4. A **chart-to-cell bridge**: generate a starting Python script from a chart's
   resolved data, link the cell to the chart, and allow a revert.
5. An **opt-in persistent namespace** for notebook cells, with a reset.
6. Tests, i18n keys and docs for all of the above.

## 4. Non-goals (do not do these)

- **No second agent loop or tool registry.** Cells are user-driven; the model
  does not get a tool to run them in this phase.
- **No code in the `chart` contract.** The spec stays data-only. The program
  lives in the cell document.
- **No second renderer.** Cell figures use the existing artifact + `ArtifactView`
  path; a chart's editable output is a PNG/figure, not a new chart widget.
- **No network, no `jdds.db` access, no writes outside the cell's output folder.**
  The sandbox's existing guard is the boundary.
- **No silent promotion.** A cell output never becomes a research claim.
- **No `.ipynb` round-trip in the first slice.** Export is a later slice.
- **No replacing the Research Data notebook.** It keeps its dataset workflow.

## 5. The shape (read this before the contracts)

```
chat transcript                         notebook sidecar
───────────────                         ────────────────
chart block (canonical)  ──link──▶     cell { chartBlockId, source }
                                              │
                                              ▼
                                    POST /notebook/cells/:id/run
                                              │
                              host sets extra_imports=("io","matplotlib")
                                              │
                                              ▼
                         run_analysis (existing sandbox + kernel + artifacts)
                                              │
                                              ▼
                              { outputs, artifacts, figure, provenance }
                                              │
                                              ▼
                         ArtifactView / figure panel (computed label)
```

Rules that fall out of this shape:

1. The transcript stays the record of the **conversation**; the sidecar is the
   record of the **working document**.
2. The chart block is never mutated by an edit. The cell is an alternate view.
3. The browser never sends an import allowlist or a purpose; the route fixes both.
4. The chart's data reaches the program as `inputs`, never as source text.

## 6. Exact contracts to create

### 6.1 The cell document

Store at `.black-eclipse/sessions/<chatId>/notebook.json` (the sessions root is
already gitignored). Reuse the session-id validation from
`src/lib/chat/session-store.ts`.

```ts
interface NotebookCell {
  id: string;                 // nb_<hex>
  chatId: string;
  source: string;             // 1..20_000 chars (the analysis limit)
  language: 'python';
  status: 'idle' | 'running' | 'ok' | 'failed' | 'refused' | 'timed_out';
  outputs: Record<string, unknown>;
  artifacts: ArtifactRef[];
  figure?: FigurePayload;
  provenance: 'computed';
  chartBlockId?: string;      // set only when the cell started from a chart
  createdAt: string;
  updatedAt: string;
}

interface NotebookDocument {
  chatId: string;
  version: 1;
  cells: NotebookCell[];      // bounded: 100 cells
  updatedAt: string;
}
```

The source is stored verbatim. The response/run result keeps the digest; the
document is what makes an edit visible after a reload.

### 6.2 The execution route

New `python/harness/routers/notebook.py`, included by `main.py`, operator-gated
like the chart route.

```text
POST /notebook/cells/{cell_id}/run
  body: { chatId, source, timeout_s? }
  → { status, outputs, artifacts, figure, provenance, durationMs, error? }

POST /notebook/kernel/restart
  body: { chatId }
  → { restarted: true }
```

The route constructs the analysis request itself:

- `extra_imports=("io", "matplotlib")` — a **host constant**, never from the body;
- `allow_tools=False`;
- `purpose="a notebook cell the user ran"`;
- `persist_namespace=True`;
- `timeout_s` clamped to the existing analysis bounds;
- `output_dir` scoped to the cell, not the project tree.

Refusals reuse the analysis codes (`SANDBOX_UNAVAILABLE`, `IMPORT_NOT_ALLOWED`,
`OUTPUT_TOO_LARGE`, `TIMED_OUT`) and fail honestly. A missing sandbox never
falls back to running in the FastAPI process.

Front door mirror: `src/lib/harness/notebook-client.ts` and
`src/app/api/harness/notebook/**`, following `src/lib/harness/charts.ts`.

### 6.3 Chart code generation

Add `python/harness/charts/codegen.py`:

```text
POST /charts/code
  body: a ChartSpec
  → { source, unsupported: string[] }
```

It resolves `dataSource` first (same `resolve_data_sources` as rendering), then
emits a **matplotlib** program that reads the resolved data from `inputs["chart"]`
and writes a PNG with `write_artifact`. The spec never gains a `code` field.

- Simple kinds (`line`, `area`, `bar`, `scatter`, `pie`, `donut`, `histogram`,
  `candlestick`) are generated faithfully.
- Scene marks are generated best-effort; anything that cannot be reproduced is
  named in `unsupported`, and the UI says so in plain words.
- The generated script is a **starting point**, not a promise of pixel parity.

The chart card calls this route only when the user chooses "Edit code".

### 6.4 The kernel's opt-in namespace

Add an internal `AnalysisRequest.persist_namespace: bool = False` (never exposed
through `analysis_run`'s tool schema). The kernel command carries
`"persist": true`; the worker reuses one module-level globals dict for persistent
commands and keeps the current fresh-dict behaviour otherwise.

- `analysis_run` stays fresh: no cross-run leakage between agent analyses.
- Notebook cells share state until the kernel is evicted or restarted.
- Restart clears the namespace through the existing
  `reset_kernel_for_context` path.
- State is process-local; a kernel crash is reported, never silently re-run.

### 6.5 The surface

- `ResponseChart` gains an "Edit code" action (`src/components/response/response-chart.tsx`).
- A new `src/components/chat/notebook-cell.tsx`:
  - Monaco (`@monaco-editor/react` is already a dependency);
  - Run / Stop / Restart;
  - status + duration;
  - outputs rendered through `ArtifactView` / the computed-result figure branch;
  - the always-visible `computed` label and the "worked out" method line.
- A small "Notebook" list in the chat surface (drawer or side panel) showing the
  cells for this conversation. Cells can be inserted and deleted; a cell from a
  chart shows a link back to that chart.
- All new copy is an i18n key under `notebook.*` in `src/lib/i18n/`.

## 7. Work items (ordered)

1. ADR-H323 in `docs/harness/decisions.md` (this change).
2. This phase file + the roadmap index row + the NAVIGATION triggers.
3. `NotebookDocument` store + client (`src/lib/harness/notebook-*`) with tests.
4. `charts/codegen.py` + `POST /charts/code` + tests (simple kinds first).
5. `routers/notebook.py` + front-door proxy + tests (sandbox unavailable, import
   refusal, timeout, artifact, provenance).
6. `NotebookCell` UI + Monaco + output rendering + i18n keys.
7. Chart "Edit code" + link + revert in `ResponseChart`.
8. `persist_namespace` in the kernel + restart route + tests.
9. Update `docs/harness/python-runtime.md`, `docs/chart-engine.md`,
   `docs/NAVIGATION.md`, `docs/CHANGELOG.md`; add a progress file under
   `docs/harness/roadmap/progress/`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/routers/notebook.py` | new — cell run + kernel restart |
| `python/harness/charts/codegen.py` | new — chart spec → matplotlib source |
| `python/harness/code/execution.py` | internal `persist_namespace` (default false) |
| `python/harness/code/kernel.py` | opt-in persistent globals |
| `src/lib/harness/notebook-client.ts` (+ tests) | new — typed browser client |
| `src/lib/chat/notebook-store.ts` (+ tests) | new — per-chat cell document |
| `src/app/api/harness/notebook/**` | new — front-door proxy |
| `src/components/chat/notebook-cell.tsx` | new — Monaco cell + outputs |
| `src/components/response/response-chart.tsx` | add "Edit code" + link/revert |
| `src/lib/i18n/dictionaries/en.ts` (+ index) | `notebook.*` keys |
| `python/tests/test_notebook_route.py`, `test_chart_codegen.py`, `test_notebook_kernel.py` | new |
| `docs/harness/roadmap/progress/phase-21-progress.md` | new — gate output |

## 9. Acceptance gates

```bash
# G1 — the route uses the sandbox and refuses honestly when it is unavailable
./scripts/vendor/python/python.exe -m pytest python/tests/test_notebook_route.py -v

# G2 — the import allowlist is the host constant; a body cannot widen it
./scripts/vendor/python/python.exe -m pytest python/tests/test_notebook_route.py -k "import or allowlist" -q

# G3 — a run records computed provenance and its artifacts are collected
./scripts/vendor/python/python.exe -m pytest python/tests/test_notebook_route.py -k "provenance or artifact" -v

# G4 — chart codegen reproduces the simple kinds and names the unsupported ones
./scripts/vendor/python/python.exe -m pytest python/tests/test_chart_codegen.py -v

# G5 — analysis_run keeps a fresh namespace; a notebook cell persists one
./scripts/vendor/python/python.exe -m pytest python/tests/test_notebook_kernel.py -v

# G6 — the front door + UI
npm run test
npx tsc --noEmit
npx vitest run src/lib/harness/notebook-client.test.ts src/lib/chat/notebook-store.test.ts
npx vitest run src/lib/i18n/plain-language.test.ts

# G7 — nothing else moved
git status --short        # jdds.db must NOT appear
```

| Gate | Assertion |
|---|---|
| G1 | No sandbox ⇒ `SANDBOX_UNAVAILABLE`; no in-process fallback. |
| G2 | `extra_imports` is fixed by the route; a body field cannot add modules. |
| G3 | Every result is `computed`; the PNG is an artifact with a digest. |
| G4 | Simple charts generate a runnable script; scenes report `unsupported`. |
| G5 | Variables survive between notebook cells and do not leak into `analysis_run`. |
| G6 | Typecheck + suite green; new strings pass the plain-language gate. |
| G7 | No `*.db` change; cell files stay under the gitignored sessions root. |

## 10. Definition of done

- A user can open a chart, edit the generated Python, run it, and see the result
  without losing the original chart.
- A user can add a cell to a conversation, run it twice, and use a variable from
  the first run in the second.
- Restarting the kernel is explicit and honest; a crashed kernel is not silently
  re-run.
- Every cell output is labelled `computed` and never appears as evidence.
- The gates above run, with raw output pasted into the progress file.
- ADR-H323, this file, `NAVIGATION.md` and `CHANGELOG.md` are updated.

## 11. Implementation prompt

```text
Task: Phase 21 — editable notebook cells in chat (with editable chart code).

Read first, in full:
- docs/harness/roadmap/phase-21-notebook-cells.md (this file, verbatim)
- docs/harness/decisions.md ADR-H323
- docs/harness/roadmap/phase-18-visual-output.md (the figure path and the
  named extra_imports rule)
- python/harness/charts/{spec,render,service,source,tools}.py
- python/harness/routers/charts.py
- python/harness/analysis_tools.py, code/execution.py, code/kernel.py
- python/harness/code/recipes.py (the figure recipes)
- src/lib/response/chart-spec.ts, src/components/response/response-chart.tsx,
  src/lib/harness/charts.ts, src/lib/chat/session-store.ts
- AGENTS.md ("Never fabricate financial data..."; the Python runtime rule)
- docs/NAVIGATION.md trigger table

Goal: a per-conversation notebook of runnable cells, and an "Edit code" path from
a chart into one of those cells. Chat stays chat; the chart block stays canonical.

Do:
1. A cell document at .black-eclipse/sessions/<chatId>/notebook.json
   (bounded, schema-versioned, source stored verbatim).
2. POST /notebook/cells/{id}/run and POST /notebook/kernel/restart on a new
   operator-gated router. The runtime sets extra_imports=("io","matplotlib"),
   allow_tools=False, a fixed purpose and the analysis timeout bounds. The body
   cannot widen the allowlist.
3. POST /charts/code that resolves the chart's data sources and returns a
   matplotlib starting script + unsupported list. Never put code in ChartSpec.
4. Monaco cell UI with Run/Stop/Restart and text/table/image/figure outputs.
5. Chart "Edit code" action: create/link a cell, show the computed label, allow
   revert to the declarative chart.
6. An internal AnalysisRequest.persist_namespace (default false). Notebook cells
   persist one namespace; analysis_run must stay fresh. Restart clears it.
7. Tests and docs per §8/§9. New strings are i18n keys under notebook.*.

Do not:
- Add code to the chart contract or a second renderer/execution engine.
- Give the model a tool to run notebook cells.
- Allow network, jdds.db reads, or writes outside the cell output folder.
- Promote a cell output into a research claim.
- Commit, push, or open a PR. Do not commit jdds.db.

Acceptance gates: see §9; paste the raw output into
docs/harness/roadmap/progress/phase-21-progress.md.

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```
