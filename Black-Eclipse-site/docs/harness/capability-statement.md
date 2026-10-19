---
title: Capability Statement — what Eclipse can build today
status: Current
last-verified: 2026-10-01
---

# Capability Statement — what Eclipse can build today

**Who this is for:** a finance professional asking *"can you build X?"*

**This page is generated.** It is derived from the labelled task fixtures
(`python/harness/code/eval/dataset_tasks_v1.json`) and the code eval report —
never authored by hand. Regenerating it from the dataset produces identical
bytes, so a claim cannot drift from the measurement without the gate noticing
(ADR-H114).

Dataset: `code-tasks-v1` (reviewed: yes).

| What you can ask for | Can Eclipse do it today? | Proof | What is missing |
|---|---|---|---|
| `capability.shape.cross-file` | `capability.status.yes` | `cross-file-change` | verified end-to-end against a live model |
| `capability.shape.job` | `capability.status.yes` | `job-definition` | verified end-to-end against a live model |
| `capability.shape.kit` | `capability.status.yes` | `kit-scaffold` | verified end-to-end against a live model |
| `capability.shape.one-file` | `capability.status.yes` | `one-file-change` | verified end-to-end against a live model |
| `capability.shape.refusal` | `capability.status.yes` | `refusal-protected-write` | — |
| `capability.shape.repair` | `capability.status.yes` | `failing-check-repair` | verified end-to-end against a live model |
| `capability.shape.test-first` | `capability.status.yes` | `test-first` | verified end-to-end against a live model |

**How to read this.** `yes` means fixtures ran and their gold outcome held; the
Proof column names them. `partial` means a fixture exists but does not yet
prove the whole shape. `not measured yet` means there is **no fixture** — a
different, weaker claim than `not yet`, and never "probably fine".

The safety properties (what Eclipse refuses) are proved by eleven adversarial
cases in `python/tests/test_code_eval_safety.py`, each of which asserts both
the block and the recorded reason. The eval report itself is engineering-facing
and lives in the terminal and the progress log; it is never shown to a user.

## Every capability class

**This section is generated too** — from the capability-class registry in
`python/harness/code/eval/capabilities.py`. It covers every class a user can
ask for; a class with no fixture is published as `not measured yet` with its
reason, never omitted.

4 of 18 classes are not measured yet.

| What you can ask for | Can Eclipse do it today? | Proof | What is missing |
|---|---|---|---|
| `capability.class.oneFile` | `capability.status.yes` | `one-file-change` (graded by the code gate in this run) | — |
| `capability.class.crossFile` | `capability.status.yes` | `cross-file-change` (graded by the code gate in this run) | — |
| `capability.class.testFirst` | `capability.status.yes` | `test-first` (graded by the code gate in this run) | — |
| `capability.class.repair` | `capability.status.yes` | `failing-check-repair` (graded by the code gate in this run) | — |
| `capability.class.job` | `capability.status.yes` | `job-definition` (graded by the code gate in this run) | — |
| `capability.class.kit` | `capability.status.yes` | `kit-scaffold` (graded by the code gate in this run) | — |
| `capability.class.refusal` | `capability.status.yes` | `refusal-protected-write` (graded by the code gate in this run) | — |
| `capability.class.bulkCollection` | `capability.status.yes` | graded through `harness.acquire.budget` | — |
| `capability.class.unattendedReport` | `capability.status.yes` | graded through `harness.automation.delivery` | — |
| `capability.class.artifactVerification` | `capability.status.yes` | graded through `harness.code.verify` | — |
| `capability.class.changeReview` | `capability.status.yes` | graded through `harness.code.review` | — |
| `capability.class.documentAttachment` | `capability.status.yes` | `vitest:src/lib/chat/extract.test.ts`, `vitest:src/lib/chat/session-store.test.ts` | — |
| `capability.class.figureProvenance` | `capability.status.yes` | `pytest:python/tests/test_analysis_recipes.py::test_drawdown_figure_writes_a_real_png_artifact_that_verifies`, `pytest:python/tests/test_analysis_recipes.py::test_a_figure_run_carries_its_payload_on_the_run_blob`, `pytest:python/tests/test_analysis_recipes.py::test_monte_carlo_is_bounded_seeded_and_samples_the_supplied_returns`, `vitest:src/components/chat/artifact-view.test.tsx`, `vitest:src/lib/harness/analysis-types.test.ts`, `pytest:python/tests/test_analysis_execution.py` | — |
| `capability.class.advisoryVerification` | `capability.status.yes` | `pytest:python/tests/test_advisory_gate.py`, `pytest:python/tests/test_advisory_ledger.py` | — |
| `capability.class.priceAuthority` | `capability.status.notMeasuredYet` | `harness.retrieval.authority` | Not graded yet — the source-choice logic is tested in pieces, not end to end. |
| `capability.class.promotion` | `capability.status.notMeasuredYet` | `harness.code.actions` | Not graded yet — putting a change into your files is tested in pieces, not end to end. |
| `capability.class.scrapingBreadth` | `capability.status.notMeasuredYet` | `harness.acquire.registry` | Not graded yet — only a few kinds of data sources are set up. |
| `capability.class.messagingGateway` | `capability.status.notMeasuredYet` | `harness.gateway` | Not built yet. |
