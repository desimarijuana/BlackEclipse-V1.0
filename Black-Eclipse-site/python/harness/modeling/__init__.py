"""Eclipse Financial Modeling — deterministic 3-statement, DCF, LBO and comps.

The engine composes the existing valuation/ratio calculators rather than
reimplementing them. It returns every input, formula, schedule and model check,
and exports a formula-bearing Excel workbook.
"""

from __future__ import annotations

from .comps import build_comps
from .contracts import Check, ModelError, ModelResult, normalize_spec, spec_hash
from .dcf import build_dcf
from .engine import build_model, build_summary
from .lbo import build_lbo
from .report_export import build_model_docx, build_model_pdf, build_model_pptx, build_model_report
from .three_statement import build_three_statement
from .tools import register_modeling_tools
from .xlsx_export import build_workbook_bytes

__all__ = [
    "Check",
    "ModelError",
    "ModelResult",
    "build_comps",
    "build_dcf",
    "build_lbo",
    "build_model",
    "build_model_docx",
    "build_model_pdf",
    "build_model_pptx",
    "build_model_report",
    "build_summary",
    "build_three_statement",
    "build_workbook_bytes",
    "normalize_spec",
    "register_modeling_tools",
    "spec_hash",
]
