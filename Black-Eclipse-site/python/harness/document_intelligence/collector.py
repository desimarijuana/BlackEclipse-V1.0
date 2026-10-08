"""Run-level document-result collection (the right-sidebar read model).

Mirrors `vision/collector.py`: a DERIVED, bounded view over the documents a run
actually opened/processed, shaped into a blob the client reads to render the
document context panel (document, type, pages, status, capabilities, current
page/section, evidence counts, entities). It never fabricates a result.
"""

from __future__ import annotations

from typing import Any, Optional

MAX_DOCUMENTS = 10
MAX_PAGES = 40
MAX_TABLES = 20
MAX_ENTITIES = 60
MAX_WARNINGS = 20


class DocumentCollector:
    def __init__(self) -> None:
        self._documents: list[dict[str, Any]] = []
        self._failures: list[dict[str, Any]] = []

    def add(self, result: Any) -> None:
        try:
            payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        except Exception:  # noqa: BLE001 - collection must never break a run
            return
        if not isinstance(payload, dict):
            return
        if payload.get("ok") is False or payload.get("state") == "FAILED":
            if len(self._failures) < MAX_DOCUMENTS:
                self._failures.append({"kind": payload.get("kind"), "error": payload.get("error"),
                                       "warnings": payload.get("warnings", [])[:5]})
            return
        if len(self._documents) >= MAX_DOCUMENTS:
            return
        self._documents.append(_bounded(payload))

    def has_content(self) -> bool:
        return bool(self._documents or self._failures)

    def to_blob(self) -> Optional[dict[str, Any]]:
        if not self.has_content():
            return None
        return {
            "type": "documents",
            "status": "collected",
            "count": len(self._documents),
            "documents": self._documents,
            "failures": self._failures or None,
        }


def _bounded(payload: dict[str, Any]) -> dict[str, Any]:
    ir = payload.get("ir") or {}
    sections = ir.get("sections") or []
    pages = ir.get("pages") or []
    context = None
    if sections:
        section = sections[0]
        context = {"section": section.get("title"), "page": section.get("page"), "path": section.get("path")}
    return {
        "documentId": payload.get("documentId"),
        "kind": payload.get("kind"),
        "version": payload.get("version"),
        "title": payload.get("title") or ir.get("title"),
        "fileName": ir.get("fileName"),
        "state": payload.get("state"),
        "capabilities": payload.get("capabilities"),
        "pageCount": payload.get("pageCount"),
        "sheetCount": payload.get("sheetCount"),
        "confidence": payload.get("confidence"),
        "textMethod": payload.get("textMethod"),
        "chunkCount": payload.get("chunkCount"),
        "tableCount": payload.get("tableCount"),
        "imageCount": payload.get("imageCount"),
        "entityCount": payload.get("entityCount"),
        "evidenceCount": len(payload.get("evidenceIds") or []),
        "currentContext": context,
        "pages": [
            {"index": p.get("index"), "label": p.get("label"), "textMethod": p.get("textMethod")}
            for p in pages[:MAX_PAGES] if isinstance(p, dict)
        ],
        "entities": (ir.get("entities") or [])[:MAX_ENTITIES],
        "warnings": (payload.get("warnings") or [])[:MAX_WARNINGS],
    }


__all__ = ["DocumentCollector", "MAX_DOCUMENTS"]
