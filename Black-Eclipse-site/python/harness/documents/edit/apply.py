"""Apply a validated edit plan and return proven bytes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from ...document_intelligence.config import document_config
from ...document_intelligence.security import macro_present
from . import docx_ops, pdf_ops, pptx_ops, xlsx_ops
from .package import OoxmlPackage
from .plan import EditError, EditPlan
from .verify import verify_ooxml


@dataclass
class EditOutcome:
    data: bytes
    report: dict[str, Any]
    format: str
    plan_hash: str
    source_sha256: str


_FORMAT_ALIASES = {
    "docx": "docx", "docm": "docx",
    "xlsx": "xlsx", "xlsm": "xlsx",
    "pptx": "pptx", "pptm": "pptx",
    "pdf": "pdf",
}


def detect_format(name: str, declared: Optional[str] = None) -> str:
    value = (declared or "").strip().casefold()
    if value in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[value]
    extension = (name or "").rsplit(".", 1)[-1].casefold()
    if extension in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[extension]
    raise EditError(
        "EDIT_FORMAT_UNSUPPORTED",
        "editing supports DOCX, XLSX, PPTX and PDF only; legacy or unknown formats must be converted first",
    )


def _needles_for(edit: dict[str, Any]) -> list[str]:
    op = edit["op"]
    if op in ("docx.replace_text", "pptx.replace_text"):
        return [edit.get("replace") or ""]
    if op in ("docx.set_paragraph_text", "docx.set_table_cell", "pptx.set_slide_title", "pptx.set_notes", "pptx.set_shape_text"):
        return [edit.get("text") or ""]
    if op == "docx.set_core_property":
        return [edit.get("value") or ""]
    if op == "xlsx.set_cell":
        return [str(edit.get("value"))]
    if op == "xlsx.set_formula":
        formula = edit.get("formula") or ""
        return [formula[1:] if formula.startswith("=") else formula]
    return []


def apply_edit_plan(
    source_bytes: bytes,
    source_name: str,
    plan: EditPlan,
) -> EditOutcome:
    fmt = detect_format(source_name, plan.format)
    expected_prefix = plan.format_prefix
    if expected_prefix != fmt:
        raise EditError(
            "EDIT_FORMAT_MISMATCH",
            f"the plan targets {expected_prefix} but the source is {fmt}",
        )
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if plan.expected_sha256 and plan.expected_sha256 != source_hash:
        raise EditError(
            "SOURCE_CHANGED",
            "the source no longer matches expectedSha256; re-read it and build a new plan",
            detail={"expected": plan.expected_sha256, "actual": source_hash},
        )

    if fmt == "pdf":
        output, detail = pdf_ops.apply_pdf_ops(source_bytes, plan.edits)
        report = {
            "ok": True,
            "preservationMode": "rewrite",
            "sourceSha256": source_hash,
            "outputSha256": hashlib.sha256(output).hexdigest(),
            "planHash": plan.stable_hash(),
            **detail,
        }
        return EditOutcome(output, report, fmt, plan.stable_hash(), source_hash)

    package = OoxmlPackage.from_bytes(source_bytes)
    if macro_present(source_bytes) and not document_config().allow_macros:
        raise EditError(
            "EDIT_MACRO_REFUSED",
            "this package contains a VBA macro project; editing macros is disabled by policy",
        )
    source_hashes = package.part_hashes()
    targeted: set[str] = set()
    needles: list[str] = []

    for edit in plan.edits:
        op = edit["op"]
        if op.startswith("docx."):
            handler = getattr(docx_ops, op.split(".", 1)[1])
            touched = handler(package, edit)
        elif op.startswith("xlsx."):
            handler = getattr(xlsx_ops, op.split(".", 1)[1])
            touched = handler(package, edit)
        elif op.startswith("pptx."):
            handler = getattr(pptx_ops, op.split(".", 1)[1])
            touched = handler(package, edit)
        else:
            raise EditError("EDIT_OP_UNSUPPORTED", f"unsupported operation {op!r}")
        targeted.update(touched)
        needles.extend(value for value in _needles_for(edit) if value)

    output = package.to_bytes(deterministic=plan.deterministic)
    edited = OoxmlPackage.from_bytes(output)
    allowed_removals: set[str] = set()
    if fmt == "xlsx":
        allowed_removals.add("xl/calcChain.xml")
    if fmt == "pptx" and any(edit["op"] == "pptx.delete_slide" for edit in plan.edits):
        allowed_removals.update(
            name for name in source_hashes
            if name.startswith(("ppt/slides/slide", "ppt/slides/_rels/slide", "ppt/notesSlides/"))
        )
    report = verify_ooxml(source_hashes, edited, targeted, allowed_removals=allowed_removals)
    decoded = {name: (edited.read(name) or b"").decode("utf-8", errors="replace") for name in targeted}
    missing_needles = [
        needle for needle in needles
        if not any(needle in text for text in decoded.values())
    ]
    if missing_needles:
        report["expectedMissing"] = [{"needle": needle} for needle in missing_needles]
        report["ok"] = False
    report["sourceSha256"] = source_hash
    report["outputSha256"] = hashlib.sha256(output).hexdigest()
    report["planHash"] = plan.stable_hash()
    if not report["ok"]:
        raise EditError(
            "EDIT_VERIFICATION_FAILED",
            "the edit did not preserve the package; no version was published",
            detail=report,
        )
    return EditOutcome(output, report, fmt, plan.stable_hash(), source_hash)


__all__ = ["EditOutcome", "apply_edit_plan", "detect_format"]
