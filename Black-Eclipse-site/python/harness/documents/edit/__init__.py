"""Preservation-first Office/PDF editing.

Public surface:

    OoxmlPackage          — read/mutate/write a ZIP package, preserving parts
    EditPlan / EditError  — validated declarative edit plans
    apply_edit_plan       — execute a plan and prove preservation
    register_document_edit_tools — the `document_edit` agent tool
"""

from __future__ import annotations

from .apply import EditOutcome, apply_edit_plan, detect_format
from .package import OoxmlError, OoxmlPackage, sha256_hex
from .plan import EditError, EditPlan
from .tools import register_document_edit_tools
from .verify import verify_ooxml

__all__ = [
    "EditError",
    "EditOutcome",
    "EditPlan",
    "OoxmlError",
    "OoxmlPackage",
    "apply_edit_plan",
    "detect_format",
    "register_document_edit_tools",
    "sha256_hex",
    "verify_ooxml",
]
