"""Adapter registry — map a document kind to the adapter that parses it.

One place decides which adapter handles which kind, so the orchestrator never
switches on a format. A kind with no adapter fails honestly with
`UNSUPPORTED_FORMAT` (no silent fallback, no format guessing).
"""

from __future__ import annotations

from typing import Optional

from ..base import DocumentAdapter
from .archive import ArchiveAdapter
from .docx import DocxAdapter
from .epub import EpubAdapter
from .image import ImageAdapter
from .legacy import LegacyOleAdapter, RtfAdapter
from .odf import OdfAdapter
from .pdf import PdfAdapter
from .pptx import PptxAdapter
from .tabular import TabularAdapter
from .text import DataAdapter, HtmlAdapter, MarkdownAdapter, TxtAdapter
from .xlsx import XlsxAdapter

_REGISTRY: dict[str, DocumentAdapter] = {}


def _register(adapter: DocumentAdapter) -> None:
    for kind in adapter.kinds:
        _REGISTRY[kind] = adapter


_register(PdfAdapter())
_register(DocxAdapter())
_register(PptxAdapter())
_register(XlsxAdapter())
_register(OdfAdapter())
_register(TabularAdapter())
_register(MarkdownAdapter())
_register(TxtAdapter())
_register(HtmlAdapter())
_register(DataAdapter())
_register(ImageAdapter())
_register(ArchiveAdapter())
_register(EpubAdapter())
_register(RtfAdapter())
_register(LegacyOleAdapter())


def get_adapter(kind: str) -> Optional[DocumentAdapter]:
    return _REGISTRY.get(kind)


def known_kinds() -> list[str]:
    return sorted(_REGISTRY.keys())


def all_adapters() -> dict[str, DocumentAdapter]:
    return dict(_REGISTRY)


__all__ = ["get_adapter", "known_kinds", "all_adapters"]
