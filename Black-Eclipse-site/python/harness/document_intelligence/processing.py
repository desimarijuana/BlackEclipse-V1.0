"""Document processing states and per-stage results (spec §33/§34/§35).

A document moves through explicit states. A run that could not complete every
stage is `PARTIALLY_READY`, never `READY`; a document with no usable content is
`FAILED`. `StageResult`s record exactly which capabilities succeeded so the agent
and the UI never overstate what is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProcessingState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    INGESTING = "INGESTING"
    PARSING = "PARSING"
    OCR = "OCR"
    VISION = "VISION"
    STRUCTURING = "STRUCTURING"
    INDEXING = "INDEXING"
    READY = "READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: States that are terminal.
TERMINAL = frozenset({ProcessingState.READY, ProcessingState.PARTIALLY_READY,
                      ProcessingState.FAILED, ProcessingState.CANCELLED})


@dataclass
class StageResult:
    stage: str
    status: str                      # "PASS" | "FAIL" | "SKIPPED" | "UNAVAILABLE"
    detail: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "status": self.status, "detail": self.detail, "durationMs": self.duration_ms}


def assess_capabilities(ir: Any, stages: list[StageResult]) -> dict[str, str]:
    """Derive a per-capability status map from the IR and the stage results.

    Spreadsheets/tabular files have no pages but are perfectly well understood as
    structured data, so a populated sheet counts for text, structure and tables.
    """
    has_sheet_data = any(getattr(s, "rows", 0) or getattr(s, "cells", None) for s in getattr(ir, "sheets", []) or [])
    has_text = bool(ir.plain_text(limit=1)) or has_sheet_data
    has_tables = bool(getattr(ir, "tables", None)) or any(getattr(s, "tables", None) for s in getattr(ir, "sheets", []) or []) or has_sheet_data
    has_structure = any(p.blocks for p in ir.pages) or any(getattr(s, "columns", 0) or getattr(s, "cells", None) for s in getattr(ir, "sheets", []) or [])
    has_images = bool(ir.images)
    ocr_stage = next((s for s in stages if s.stage == "ocr"), None)
    vision_stage = next((s for s in stages if s.stage == "vision"), None)

    return {
        "text": "PASS" if has_text else "FAIL",
        "structure": "PASS" if has_structure else "FAIL",
        "tables": "PASS" if has_tables else "SKIPPED",
        "images": "PASS" if has_images else "SKIPPED",
        "ocr": ocr_stage.status if ocr_stage else "SKIPPED",
        "vision": vision_stage.status if vision_stage else "SKIPPED",
    }


def resolve_state(capabilities: dict[str, str], *, hard_failed: bool = False) -> ProcessingState:
    if hard_failed:
        return ProcessingState.FAILED
    essential_fail = capabilities.get("text") == "FAIL" and capabilities.get("tables") == "FAIL" \
        and capabilities.get("ocr") in ("FAIL", "UNAVAILABLE", "SKIPPED")
    if essential_fail:
        return ProcessingState.FAILED
    degraded = any(v in ("FAIL", "UNAVAILABLE") for v in capabilities.values())
    if capabilities.get("text") == "FAIL":
        degraded = True
    return ProcessingState.PARTIALLY_READY if degraded else ProcessingState.READY


__all__ = ["ProcessingState", "StageResult", "TERMINAL", "assess_capabilities", "resolve_state"]
