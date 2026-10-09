"""Preview & thumbnail generation — bounded, asynchronous-safe, never executes.

The preview engine classifies content into a renderer kind and, where it can do
so safely and cheaply, produces (a) a bounded text extract for text-like formats
and (b) a PNG thumbnail for images / the first PDF page. It NEVER runs the file:
office documents are read as ZIP+XML text, not through an office runtime.

Heavy or unsupported formats are reported honestly (`UNSUPPORTED`), and the
original bytes always remain downloadable.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Optional

from .content import preview_kind
from .model import Artifact, PreviewStatus

#: how many source bytes a text preview may read
MAX_PREVIEW_BYTES = 512 * 1024
MAX_PREVIEW_CHARS = 20_000
THUMBNAIL_MAX = 512
XML_TAG = re.compile(rb"<[^>]+>")


def _text_extract(data: bytes) -> Optional[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError:
            return None
    return text[:MAX_PREVIEW_CHARS]


def _office_text(data: bytes) -> Optional[str]:
    """Extract text from a docx/xlsx/pptx (a ZIP of XML) without running office.

    Bounded: reads at most the first few XML parts and caps the result.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            parts: list[str] = []
            names = archive.namelist()
            wanted = [
                n for n in names
                if n.endswith(("word/document.xml", "xl/sharedStrings.xml"))
                or re.match(r"ppt/slides/slide\d+\.xml$", n)
                or n.endswith("xl/worksheets/sheet1.xml")
            ]
            for name in wanted[:12]:
                try:
                    raw = archive.read(name)
                except KeyError:
                    continue
                text = XML_TAG.sub(b" ", raw).decode("utf-8", "ignore")
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    parts.append(text)
            if not parts:
                return None
            return "\n\n".join(parts)[:MAX_PREVIEW_CHARS]
    except (zipfile.BadZipFile, OSError, ValueError):
        return None


def generate_text_preview(
    data: bytes, *, mime: str, kind: str, name: str = ""
) -> Optional[str]:
    if kind in ("text", "code", "markdown"):
        return _text_extract(data)
    if kind == "json":
        text = _text_extract(data)
        return text
    if kind == "table":
        return _text_extract(data)
    if kind == "html":
        text = _text_extract(data)
        return text
    if name.casefold().endswith((".docx", ".xlsx", ".pptx")):
        return _office_text(data)
    return None


def make_thumbnail(data: bytes) -> Optional[bytes]:
    """Produce a bounded PNG thumbnail for an image. None when unsupported."""
    try:
        from PIL import Image  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - Pillow absent is a supported state
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGBA")
            image.thumbnail((THUMBNAIL_MAX, THUMBNAIL_MAX))
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except Exception:  # noqa: BLE001 - a malformed image is a preview failure, not a crash
        return None


def make_pdf_thumbnail(data: bytes) -> Optional[bytes]:
    try:
        import pypdfium2 as pdfium  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        pdf = pdfium.PdfDocument(data)
        page = pdf[0]
        bitmap = page.render(scale=1.5)
        image = bitmap.to_pil().convert("RGB")
        image.thumbnail((THUMBNAIL_MAX, THUMBNAIL_MAX))
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def classify(artifact: Artifact) -> str:
    return preview_kind(artifact.mime_type, artifact.category, artifact.name)


def build(
    storage: Any, artifact: Artifact, *, limit: int = MAX_PREVIEW_BYTES
) -> dict[str, Any]:
    """Produce preview metadata for an artifact.

    Returns a dict with:
      kind          — the renderer
      status        — READY | UNSUPPORTED | FAILED
      text          — bounded text extract (optional)
      thumbnailKey  — storage key of a generated thumbnail (optional)
    The caller persists the result; this function performs the storage write for
    a thumbnail and reports its key. It never mutates the artifact row.
    """
    kind = classify(artifact)
    result: dict[str, Any] = {"kind": kind, "status": PreviewStatus.READY.value}
    if artifact.storage_key is None:
        return {"kind": kind, "status": PreviewStatus.UNSUPPORTED.value}
    try:
        data = storage.read_bytes(artifact.storage_key, limit=limit)
    except Exception:  # noqa: BLE001 - a missing/unreadable object is a preview failure
        return {"kind": kind, "status": PreviewStatus.FAILED.value}

    if kind == "image":
        thumb = make_thumbnail(data)
        if thumb is not None:
            thumb_key = f"{artifact.storage_key}.thumb.png"
            try:
                storage.save_bytes_at(thumb_key, thumb)
                result["thumbnailKey"] = thumb_key
            except Exception:  # noqa: BLE001
                pass
        return result
    if kind == "pdf":
        thumb = make_pdf_thumbnail(data)
        if thumb is not None:
            thumb_key = f"{artifact.storage_key}.thumb.png"
            try:
                storage.save_bytes_at(thumb_key, thumb)
                result["thumbnailKey"] = thumb_key
            except Exception:  # noqa: BLE001
                pass
        return result
    if kind in ("unsupported", "audio", "video"):
        result["status"] = PreviewStatus.UNSUPPORTED.value
        return result
    text = generate_text_preview(data, mime=artifact.mime_type, kind=kind, name=artifact.name)
    if text is None:
        result["status"] = PreviewStatus.UNSUPPORTED.value
        return result
    result["text"] = text
    return result


__all__ = [
    "build",
    "classify",
    "generate_text_preview",
    "make_pdf_thumbnail",
    "make_thumbnail",
    "MAX_PREVIEW_CHARS",
]
