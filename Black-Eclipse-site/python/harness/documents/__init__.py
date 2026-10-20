"""Eclipse Document Authoring — the write side of the document capability.

Document Intelligence reads office documents; this subsystem AUTHORS them. It
provides pure builders for Word (.docx), Excel (.xlsx), PowerPoint (.pptx) and the
plain text formats (Markdown, CSV, JSON, .txt), plus the `document_create` agent
tool that writes the produced file into the ONE Artifact Center for preview and
download.

Public surface:

    build / build_docx / build_xlsx / build_pptx / ...   — pure bytes builders
    DocumentError                                        — coded failure
    register_document_authoring_tools                    — the agent tool

Nothing here builds a second store, a second provider stack or an Office runtime;
the bytes go straight into the confined artifact store through the existing
`ArtifactService`.
"""

from __future__ import annotations

from .authoring import (
    FORMAT_EXTENSION,
    FORMAT_MIME,
    DocumentError,
    blocks_to_markdown,
    build,
    build_csv,
    build_docx,
    build_json,
    build_markdown,
    build_pptx,
    build_txt,
    build_xlsx,
    canonical_format,
    slug_filename,
)
from .report_tools import register_report_tools
from .reporting import PDF_MIME, REPORT_FORMATS, build_pdf, build_report
from .tools import register_document_authoring_tools

__all__ = [
    "DocumentError",
    "FORMAT_EXTENSION",
    "FORMAT_MIME",
    "PDF_MIME",
    "REPORT_FORMATS",
    "blocks_to_markdown",
    "build",
    "build_csv",
    "build_docx",
    "build_json",
    "build_markdown",
    "build_pdf",
    "build_pptx",
    "build_report",
    "build_txt",
    "build_xlsx",
    "canonical_format",
    "register_document_authoring_tools",
    "register_report_tools",
    "slug_filename",
]
