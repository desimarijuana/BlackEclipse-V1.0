"""The capability statement generator (Phase 12 §6.7).

The per-shape "can Eclipse build X today" table is DERIVED from
`dataset_tasks_v1.json` and the eval report — never authored by hand. Regenerating
it from the dataset produces byte-identical markdown (the `test_code_eval.py`
byte-compare proves it cannot drift). A shape with no fixture reads
`not measured yet` — a different claim from `not yet`.

The user-facing strings are i18n keys (`capability.*` in
`src/lib/i18n/dictionaries/en.ts`); this generator only names the keys, so the
plain-language gate reads every word a finance user sees.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .tasks import capability_rows, load_task_dataset

# Where the generated statement lives (repo-relative, one level up from `python/`).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STATEMENT_PATH = os.path.join(_REPO_ROOT, "docs", "harness", "capability-statement.md")

# The i18n key for each shape's plain name.
SHAPE_KEY: dict[str, str] = {
    "one-file": "capability.shape.one-file",
    "cross-file": "capability.shape.cross-file",
    "test-first": "capability.shape.test-first",
    "repair": "capability.shape.repair",
    "kit": "capability.shape.kit",
    "job": "capability.shape.job",
    "refusal": "capability.shape.refusal",
}

_STATUS_KEY = {
    "yes": "capability.status.yes",
    "partial": "capability.status.partial",
    "not yet": "capability.status.notYet",
    "not measured yet": "capability.status.notMeasuredYet",
}


def render_statement(dataset: Optional[dict[str, Any]] = None) -> str:
    """Render the per-shape table. Deterministic: same input, same bytes."""
    dataset = dataset or load_task_dataset()
    rows = capability_rows(dataset)
    version = str(dataset.get("datasetVersion") or "unknown")
    reviewed = "yes" if dataset.get("reviewed") else "no"
    lines = [
        "---",
        "title: Capability Statement — what Eclipse can build today",
        "status: Current",
        "last-verified: 2026-10-01",
        "---",
        "",
        "# Capability Statement — what Eclipse can build today",
        "",
        "**Who this is for:** a finance professional asking *\"can you build X?\"*",
        "",
        "**This page is generated.** It is derived from the labelled task fixtures",
        "(`python/harness/code/eval/dataset_tasks_v1.json`) and the code eval report —",
        "never authored by hand. Regenerating it from the dataset produces identical",
        "bytes, so a claim cannot drift from the measurement without the gate noticing",
        "(ADR-H114).",
        "",
        f"Dataset: `{version}` (reviewed: {reviewed}).",
        "",
        "| What you can ask for | Can Eclipse do it today? | Proof | What is missing |",
        "|---|---|---|---|",
    ]
    for row in rows:
        shape_key = SHAPE_KEY.get(row["shape"], row["shape"])
        status_key = _STATUS_KEY.get(row["status"], row["status"])
        evidence = ", ".join(f"`{eid}`" for eid in row["evidence"]) or "—"
        missing = row.get("missing") or "—"
        # The table carries i18n KEYS, not sentences: the surface resolves them, and
        # the plain-language gate reads every word.
        lines.append(f"| `{shape_key}` | `{status_key}` | {evidence} | {missing} |")
    lines += [
        "",
        "**How to read this.** `yes` means fixtures ran and their gold outcome held; the",
        "Proof column names them. `partial` means a fixture exists but does not yet",
        "prove the whole shape. `not measured yet` means there is **no fixture** — a",
        "different, weaker claim than `not yet`, and never \"probably fine\".",
        "",
        "The safety properties (what Eclipse refuses) are proved by eleven adversarial",
        "cases in `python/tests/test_code_eval_safety.py`, each of which asserts both",
        "the block and the recorded reason. The eval report itself is engineering-facing",
        "and lives in the terminal and the progress log; it is never shown to a user.",
        "",
    ]
    return "\n".join(lines)


def write_statement(path: Optional[str] = None, dataset: Optional[dict[str, Any]] = None) -> str:
    target = path or STATEMENT_PATH
    text = render_statement(dataset)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return target


__all__ = ["SHAPE_KEY", "STATEMENT_PATH", "render_statement", "write_statement"]
