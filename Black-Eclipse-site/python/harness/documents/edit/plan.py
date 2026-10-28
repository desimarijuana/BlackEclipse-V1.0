"""Declarative edit plans for Office/PDF files.

The model never writes XML or Python. It selects a small, closed set of
operations and supplies their arguments; this module validates the plan before
any byte is touched. Every operation is deterministic and bounded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

MAX_EDITS = 500
MAX_TEXT = 200_000
MAX_CELLS = 50_000
MAX_IMAGE_BASE64 = 40_000_000

DOCX_OPS = frozenset({
    "docx.replace_text",
    "docx.set_paragraph_text",
    "docx.set_table_cell",
    "docx.set_core_property",
    "docx.insert_image",
    "docx.accept_revisions",
    "docx.reject_revisions",
})
XLSX_OPS = frozenset({
    "xlsx.set_cell",
    "xlsx.set_formula",
    "xlsx.set_number_format",
    "xlsx.rename_sheet",
    "xlsx.append_rows",
    "xlsx.insert_rows",
    "xlsx.delete_rows",
    "xlsx.insert_columns",
    "xlsx.delete_columns",
})
PPTX_OPS = frozenset({
    "pptx.set_slide_title",
    "pptx.replace_text",
    "pptx.set_notes",
    "pptx.set_shape_text",
    "pptx.delete_slide",
    "pptx.duplicate_slide",
    "pptx.replace_chart_data",
    "pptx.add_smartart_node",
    "pptx.remove_smartart_node",
    "pptx.set_smartart_node_text",
    "pptx.set_smartart_layout",
})
PDF_OPS = frozenset({
    "pdf.fill_form",
    "pdf.rotate_pages",
    "pdf.add_annotation",
    "pdf.set_metadata",
    "pdf.redact",
})
ALL_OPS = DOCX_OPS | XLSX_OPS | PPTX_OPS | PDF_OPS


class EditError(Exception):
    def __init__(self, code: str, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


def _text(value: Any, *, field_name: str, maximum: int = MAX_TEXT) -> str:
    if value is None:
        raise EditError("EDIT_INVALID_PLAN", f"{field_name} is required")
    if not isinstance(value, str):
        raise EditError("EDIT_INVALID_PLAN", f"{field_name} must be a string")
    if len(value) > maximum:
        raise EditError("EDIT_LIMIT", f"{field_name} exceeds {maximum} characters")
    return value


def _int(value: Any, *, field_name: str, low: int = 0, high: int = 1_000_000) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise EditError("EDIT_INVALID_PLAN", f"{field_name} must be an integer") from None
    if number < low or number > high:
        raise EditError("EDIT_INVALID_PLAN", f"{field_name} must be between {low} and {high}")
    return number


def _optional_str(value: Any, *, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EditError("EDIT_INVALID_PLAN", f"{field_name} must be a string")
    return value


def validate_edit(edit: Any, index: int) -> dict[str, Any]:
    if not isinstance(edit, dict):
        raise EditError("EDIT_INVALID_PLAN", f"edit {index} must be an object")
    op = str(edit.get("op") or "").strip()
    if op not in ALL_OPS:
        raise EditError("EDIT_OP_UNSUPPORTED", f"unknown edit operation {op!r}")
    clean: dict[str, Any] = {"op": op}

    if op in ("docx.replace_text", "pptx.replace_text"):
        clean["find"] = _text(edit.get("find"), field_name=f"edits[{index}].find")
        clean["replace"] = _text(edit.get("replace", ""), field_name=f"edits[{index}].replace")
        match = str(edit.get("match") or "all").casefold()
        if match not in ("all", "first"):
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].match must be 'all' or 'first'")
        clean["match"] = match
        parts = edit.get("parts")
        if parts is not None:
            if not isinstance(parts, list) or any(not isinstance(p, str) for p in parts):
                raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].parts must be a list of strings")
            clean["parts"] = parts
        if op.startswith("pptx") and edit.get("include_notes") is not None:
            clean["include_notes"] = bool(edit.get("include_notes"))
        if op.startswith("pptx") and edit.get("include_diagrams") is not None:
            clean["include_diagrams"] = bool(edit.get("include_diagrams"))
        return clean

    if op == "docx.set_paragraph_text":
        clean["index"] = _int(edit.get("index"), field_name=f"edits[{index}].index")
        clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        clean["part"] = _optional_str(edit.get("part"), field_name=f"edits[{index}].part") or "word/document.xml"
        return clean

    if op == "docx.set_table_cell":
        clean["table"] = _int(edit.get("table"), field_name=f"edits[{index}].table")
        clean["row"] = _int(edit.get("row"), field_name=f"edits[{index}].row")
        clean["col"] = _int(edit.get("col"), field_name=f"edits[{index}].col")
        clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        clean["part"] = _optional_str(edit.get("part"), field_name=f"edits[{index}].part") or "word/document.xml"
        return clean

    if op == "docx.set_core_property":
        name = str(edit.get("name") or "").strip()
        if name not in ("title", "subject", "creator", "description", "keywords", "lastModifiedBy"):
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].name is not an editable core property")
        clean["name"] = name
        clean["value"] = _text(edit.get("value", ""), field_name=f"edits[{index}].value")
        return clean

    if op == "docx.insert_image":
        clean["imageBase64"] = _text(
            edit.get("imageBase64"), field_name=f"edits[{index}].imageBase64",
            maximum=MAX_IMAGE_BASE64,
        )
        extension = str(edit.get("extension") or "").strip().casefold()
        if extension and extension not in ("png", "jpg", "jpeg", "gif"):
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].extension must be png, jpg, jpeg or gif")
        clean["extension"] = extension
        clean["altText"] = str(edit.get("altText") or "Inserted image")
        clean["widthInches"] = float(edit.get("widthInches", 4.0))
        if clean["widthInches"] <= 0:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].widthInches must be positive")
        if edit.get("heightInches") is not None:
            clean["heightInches"] = float(edit["heightInches"])
            if clean["heightInches"] <= 0:
                raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].heightInches must be positive")
        if edit.get("afterParagraph") is not None:
            clean["afterParagraph"] = _int(
                edit["afterParagraph"], field_name=f"edits[{index}].afterParagraph",
                low=0, high=1_000_000,
            )
        return clean

    if op in ("docx.accept_revisions", "docx.reject_revisions"):
        parts = edit.get("parts")
        if parts is not None:
            if not isinstance(parts, list) or any(not isinstance(p, str) for p in parts):
                raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].parts must be a list of strings")
            clean["parts"] = parts
        return clean

    if op in ("xlsx.set_cell", "xlsx.set_formula"):
        clean["sheet"] = _text(edit.get("sheet"), field_name=f"edits[{index}].sheet", maximum=31)
        clean["ref"] = _text(edit.get("ref"), field_name=f"edits[{index}].ref", maximum=32)
        if op == "xlsx.set_cell":
            if "value" not in edit:
                raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].value is required")
            clean["value"] = edit["value"]
        else:
            clean["formula"] = _text(edit.get("formula"), field_name=f"edits[{index}].formula")
        if edit.get("numberFormat") is not None:
            clean["numberFormat"] = _text(edit.get("numberFormat"), field_name=f"edits[{index}].numberFormat", maximum=120)
        return clean

    if op == "xlsx.set_number_format":
        clean["sheet"] = _text(edit.get("sheet"), field_name=f"edits[{index}].sheet", maximum=31)
        clean["ref"] = _text(edit.get("ref"), field_name=f"edits[{index}].ref", maximum=32)
        clean["numberFormat"] = _text(edit.get("numberFormat"), field_name=f"edits[{index}].numberFormat", maximum=120)
        return clean

    if op == "xlsx.rename_sheet":
        clean["sheet"] = _text(edit.get("sheet"), field_name=f"edits[{index}].sheet", maximum=31)
        clean["newName"] = _text(edit.get("newName"), field_name=f"edits[{index}].newName", maximum=31)
        return clean

    if op == "xlsx.append_rows":
        clean["sheet"] = _text(edit.get("sheet"), field_name=f"edits[{index}].sheet", maximum=31)
        rows = edit.get("rows")
        if not isinstance(rows, list) or not rows:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].rows must be a non-empty array")
        if len(rows) > MAX_CELLS:
            raise EditError("EDIT_LIMIT", f"edits[{index}].rows exceeds the row limit")
        clean["rows"] = rows
        return clean

    if op in ("xlsx.insert_rows", "xlsx.delete_rows", "xlsx.insert_columns", "xlsx.delete_columns"):
        clean["sheet"] = _text(edit.get("sheet"), field_name=f"edits[{index}].sheet", maximum=31)
        clean["at"] = _int(edit.get("at"), field_name=f"edits[{index}].at", low=1, high=1_048_575)
        clean["count"] = _int(edit.get("count", 1), field_name=f"edits[{index}].count", low=1, high=10_000)
        return clean

    if op in ("pptx.delete_slide", "pptx.duplicate_slide"):
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        return clean

    if op == "pptx.replace_chart_data":
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["chart"] = _int(edit.get("chart", 0), field_name=f"edits[{index}].chart", low=0, high=1_000)
        categories = edit.get("categories")
        if not isinstance(categories, list) or not categories or len(categories) > 10_000:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].categories must be a non-empty array (max 10000)")
        clean["categories"] = ["" if value is None else str(value) for value in categories]
        series = edit.get("series")
        if not isinstance(series, list) or not series:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].series must be a non-empty array")
        clean_series = []
        for s_index, item in enumerate(series):
            if isinstance(item, dict):
                values = item.get("values")
                name = item.get("name")
            else:
                values = item
                name = None
            if not isinstance(values, list) or len(values) != len(clean["categories"]):
                raise EditError(
                    "EDIT_INVALID_PLAN",
                    f"edits[{index}].series[{s_index}].values must match the category count",
                )
            numbers: list[float] = []
            for value in values:
                try:
                    numbers.append(float(value))
                except (TypeError, ValueError):
                    raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].series[{s_index}] contains a non-number") from None
            clean_series.append({"name": None if name is None else str(name), "values": numbers})
        clean["series"] = clean_series
        return clean

    if op in ("pptx.add_smartart_node", "pptx.remove_smartart_node", "pptx.set_smartart_node_text"):
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["diagram"] = _int(edit.get("diagram", 0), field_name=f"edits[{index}].diagram", low=0, high=1_000)
        if op == "pptx.add_smartart_node":
            clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
            clean["parent"] = _optional_str(edit.get("parent"), field_name=f"edits[{index}].parent")
            if edit.get("parentIndex") is not None:
                clean["parentIndex"] = _int(edit["parentIndex"], field_name=f"edits[{index}].parentIndex")
        else:
            clean["node"] = _text(edit.get("node"), field_name=f"edits[{index}].node", maximum=200)
            if op == "pptx.set_smartart_node_text":
                clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        return clean

    if op == "pptx.set_smartart_layout":
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["diagram"] = _int(edit.get("diagram", 0), field_name=f"edits[{index}].diagram", low=0, high=1_000)
        clean["fromSlide"] = _int(edit.get("fromSlide"), field_name=f"edits[{index}].fromSlide", low=1, high=10_000)
        clean["fromDiagram"] = _int(edit.get("fromDiagram", 0), field_name=f"edits[{index}].fromDiagram", low=0, high=1_000)
        return clean

    if op == "pptx.set_slide_title":
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        return clean

    if op == "pptx.set_notes":
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        return clean

    if op == "pptx.set_shape_text":
        clean["slide"] = _int(edit.get("slide"), field_name=f"edits[{index}].slide", low=1, high=10_000)
        clean["shape"] = _int(edit.get("shape"), field_name=f"edits[{index}].shape")
        clean["text"] = _text(edit.get("text", ""), field_name=f"edits[{index}].text")
        return clean

    if op == "pdf.fill_form":
        fields = edit.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].fields must be a non-empty object")
        clean["fields"] = {str(k): "" if v is None else str(v) for k, v in fields.items()}
        return clean

    if op == "pdf.rotate_pages":
        pages = edit.get("pages")
        if pages is None:
            clean["pages"] = None
        else:
            if not isinstance(pages, list) or any(not isinstance(p, int) for p in pages):
                raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].pages must be a list of page numbers")
            clean["pages"] = [p - 1 for p in pages if p > 0]
        clean["degrees"] = _int(edit.get("degrees", 90), field_name=f"edits[{index}].degrees", low=-360, high=360)
        return clean

    if op == "pdf.add_annotation":
        clean["page"] = _int(edit.get("page", 1), field_name=f"edits[{index}].page", low=1, high=100_000) - 1
        clean["text"] = _text(edit.get("text"), field_name=f"edits[{index}].text")
        clean["x"] = float(edit.get("x", 36))
        clean["y"] = float(edit.get("y", 36))
        clean["width"] = float(edit.get("width", 300))
        clean["height"] = float(edit.get("height", 80))
        return clean

    if op == "pdf.redact":
        clean["page"] = _int(edit.get("page", 1), field_name=f"edits[{index}].page", low=1, high=100_000) - 1
        clean["x"] = float(edit.get("x", 0))
        clean["y"] = float(edit.get("y", 0))
        clean["width"] = float(edit.get("width"))
        clean["height"] = float(edit.get("height"))
        if clean["width"] <= 0 or clean["height"] <= 0:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}] redaction width/height must be positive")
        return clean

    if op == "pdf.set_metadata":
        metadata = edit.get("metadata")
        if not isinstance(metadata, dict) or not metadata:
            raise EditError("EDIT_INVALID_PLAN", f"edits[{index}].metadata must be a non-empty object")
        clean["metadata"] = {str(k): str(v) for k, v in metadata.items()}
        return clean

    raise EditError("EDIT_OP_UNSUPPORTED", f"unknown edit operation {op!r}")


@dataclass
class EditPlan:
    edits: list[dict[str, Any]] = field(default_factory=list)
    source: Optional[str] = None
    expected_sha256: Optional[str] = None
    format: Optional[str] = None
    dry_run: bool = False
    deterministic: bool = True

    @classmethod
    def from_dict(cls, payload: Any) -> "EditPlan":
        if not isinstance(payload, dict):
            raise EditError("EDIT_INVALID_PLAN", "the edit plan must be an object")
        edits = payload.get("edits")
        if not isinstance(edits, list) or not edits:
            raise EditError("EDIT_INVALID_PLAN", "the plan needs a non-empty edits array")
        if len(edits) > MAX_EDITS:
            raise EditError("EDIT_LIMIT", f"a plan may contain at most {MAX_EDITS} edits")
        clean = [validate_edit(edit, index) for index, edit in enumerate(edits)]
        prefixes = {edit["op"].split(".", 1)[0] for edit in clean}
        if len(prefixes) > 1:
            raise EditError("EDIT_INVALID_PLAN", "a plan may target only one file format at a time")
        expected = payload.get("expectedSha256")
        if expected is not None and not isinstance(expected, str):
            raise EditError("EDIT_INVALID_PLAN", "expectedSha256 must be a string")
        fmt = payload.get("format")
        if fmt is not None and not isinstance(fmt, str):
            raise EditError("EDIT_INVALID_PLAN", "format must be a string")
        return cls(
            edits=clean,
            source=payload.get("source"),
            expected_sha256=expected,
            format=fmt,
            dry_run=bool(payload.get("dryRun", False)),
            deterministic=bool(payload.get("deterministic", True)),
        )

    @property
    def format_prefix(self) -> str:
        return self.edits[0]["op"].split(".", 1)[0]

    def stable_hash(self) -> str:
        payload = {
            "edits": self.edits,
            "format": self.format,
            "deterministic": self.deterministic,
            "expectedSha256": self.expected_sha256,
        }
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


__all__ = [
    "ALL_OPS",
    "DOCX_OPS",
    "EditError",
    "EditPlan",
    "MAX_EDITS",
    "PDF_OPS",
    "PPTX_OPS",
    "XLSX_OPS",
    "validate_edit",
]
