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
