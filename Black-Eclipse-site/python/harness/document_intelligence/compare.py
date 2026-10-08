"""Document comparison — structured-first diffing (spec §26).

Two documents are compared through their DocumentIRs, never by asking a model to
read two raw files. The comparison reports text differences (via a deterministic
sequence diff), structural differences (sections/headings added, removed or moved),
table differences (rows added/removed/changed) and metadata/point-in-time changes.
An optional model pass may summarize the *already-computed* diff; it cannot invent
changes.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Optional

from .ir import DocumentIR


@dataclass
class ComparisonChange:
    change_type: str                 # text | structural | table | metadata
    kind: str                       # added | removed | changed
    summary: str
    page_a: Optional[int] = None
    page_b: Optional[int] = None
    locator: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"changeType": self.change_type, "kind": self.kind, "summary": self.summary,
                "pageA": self.page_a, "pageB": self.page_b, "locator": self.locator}


@dataclass
class ComparisonResult:
    document_a: str
    document_b: str
    version_a: int
    version_b: int
    identical: bool
    changes: list[ComparisonChange] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "document_comparison",
            "documentA": self.document_a, "documentB": self.document_b,
            "versionA": self.version_a, "versionB": self.version_b,
            "identical": self.identical, "changeCount": len(self.changes),
            "changes": [c.to_dict() for c in self.changes], "summary": self.summary,
            "warnings": self.warnings,
        }


def compare_documents(a: DocumentIR, b: DocumentIR) -> ComparisonResult:
    result = ComparisonResult(
        document_a=a.document_id, document_b=b.document_id, version_a=a.version, version_b=b.version,
        identical=False,
    )

    # Structural: headings / sections.
    headings_a = _headings(a)
    headings_b = _headings(b)
    matcher = difflib.SequenceMatcher(a=headings_a, b=headings_b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            result.changes.append(ComparisonChange("structural", "removed",
                                                     f"section removed: {', '.join(headings_a[i1:i2])}"))
        elif tag == "insert":
            result.changes.append(ComparisonChange("structural", "added",
                                                     f"section added: {', '.join(headings_b[j1:j2])}"))
        elif tag == "replace":
            result.changes.append(ComparisonChange("structural", "changed",
                                                     f"sections changed: {' -> '.join(headings_a[i1:i2])} → "
                                                     f"{' -> '.join(headings_b[j1:j2])}"))

    # Text: paragraph-level diff.
    paras_a = _paragraphs(a)
    paras_b = _paragraphs(b)
    matcher = difflib.SequenceMatcher(a=[p[0] for p in paras_a], b=[p[0] for p in paras_b], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for text, page in paras_a[i1:i2][:20]:
                result.changes.append(ComparisonChange("text", "removed", _clip(text), page_a=page))
        elif tag == "insert":
            for text, page in paras_b[j1:j2][:20]:
                result.changes.append(ComparisonChange("text", "added", _clip(text), page_b=page))
        else:
            for (ta, pa), (tb, pb) in zip(paras_a[i1:i2][:10], paras_b[j1:j2][:10]):
                result.changes.append(ComparisonChange("text", "changed", _inline_diff(ta, tb), page_a=pa, page_b=pb))

    # Tables: row-level diff per table index.
    _compare_tables(a, b, result)

    # Metadata / dates.
    for key in ("title", "publication_date"):
        va = a.title if key == "title" else a.dates.publication_date
        vb = b.title if key == "title" else b.dates.publication_date
        if va != vb:
            result.changes.append(ComparisonChange("metadata", "changed", f"{key}: {va!r} → {vb!r}"))

    result.identical = not result.changes
    result.summary = _summarize(result)
    return result


def _compare_tables(a: DocumentIR, b: DocumentIR, result: ComparisonResult) -> None:
    by_index_a = {i: t for i, t in enumerate(a.tables)}
    by_index_b = {i: t for i, t in enumerate(b.tables)}
    for index in sorted(set(by_index_a) | set(by_index_b)):
        ta = by_index_a.get(index)
        tb = by_index_b.get(index)
        if ta is None:
            result.changes.append(ComparisonChange("table", "added", f"table {index} added ({len(tb.rows)} rows)" if tb else f"table {index} added"))
            continue
        if tb is None:
            result.changes.append(ComparisonChange("table", "removed", f"table {index} removed ({len(ta.rows)} rows)"))
            continue
        rows_a = {tuple(r) for r in ta.rows}
        rows_b = {tuple(r) for r in tb.rows}
        added = rows_b - rows_a
        removed = rows_a - rows_b
        if added:
            result.changes.append(ComparisonChange("table", "added",
                                                     f"table {index}: {len(added)} row(s) added", locator={"tableId": ta.table_id}))
        if removed:
            result.changes.append(ComparisonChange("table", "removed",
                                                     f"table {index}: {len(removed)} row(s) removed", locator={"tableId": ta.table_id}))


def _headings(ir: DocumentIR) -> list[str]:
    out: list[str] = []
    for page in ir.pages:
        for block in page.blocks:
            if block.kind in ("heading", "slide_title"):
                out.append(block.text.strip())
    return out


def _paragraphs(ir: DocumentIR) -> list[tuple[str, Optional[int]]]:
    out: list[tuple[str, Optional[int]]] = []
    for page in ir.pages:
        for block in page.blocks:
            if block.text.strip() and block.kind not in ("heading", "slide_title"):
                out.append((block.text.strip(), page.index))
    return out


def _clip(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _inline_diff(a: str, b: str) -> str:
    a, b = " ".join(a.split()), " ".join(b.split())
    matcher = difflib.SequenceMatcher(a=a.split(), b=b.split(), autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(a.split()[i1:i2])
        elif tag in ("replace", "delete"):
            out.append("[-" + " ".join(a.split()[i1:i2]) + "-]")
            if tag == "replace":
                out.append("[+" + " ".join(b.split()[j1:j2]) + "+]")
        elif tag == "insert":
            out.append("[+" + " ".join(b.split()[j1:j2]) + "+]")
    return _clip(" ".join(out), 240)


def _summarize(result: ComparisonResult) -> str:
    if result.identical:
        return "The two document versions are identical in text, structure and tables."
    counts: dict[str, int] = {}
    for change in result.changes:
        counts[change.change_type] = counts.get(change.change_type, 0) + 1
    return "Differences: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + "."


__all__ = ["ComparisonChange", "ComparisonResult", "compare_documents"]
