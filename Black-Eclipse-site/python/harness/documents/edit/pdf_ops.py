"""PDF edits with an honest preservation mode.

PDF is not an OOXML package. The ``pypdf`` backend copies the document and
rewrites it, so the report states ``preservationMode: rewrite`` rather than
pretending the original byte layout survived. When ``pypdf`` is absent the
operation refuses with ``PDF_LIBRARY_MISSING``.
"""

from __future__ import annotations

import io
import os
import tempfile
from typing import Any

from .plan import EditError


def _pypdf() -> tuple[Any, Any, Any]:
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: PLC0415
        from pypdf.annotations import FreeText  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise EditError(
            "PDF_LIBRARY_MISSING",
            "pypdf is not installed, so PDF editing is unavailable",
        ) from exc
    return PdfReader, PdfWriter, FreeText


def _reader_writer(data: bytes) -> tuple[Any, Any]:
    PdfReader, PdfWriter, _ = _pypdf()
    reader = PdfReader(io.BytesIO(data))
    try:
        writer = PdfWriter(clone_from=reader)
    except TypeError:
        writer = PdfWriter()
        writer.append(reader)
    return reader, writer


def _render_redacted_page(current: bytes, index: int, rect: dict[str, float], *, scale: float = 2.0) -> tuple[Any, float, float]:
    try:
        import pypdfium2 as pdfium  # noqa: PLC0415
        from PIL import ImageDraw  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise EditError(
            "PDF_REDACT_UNAVAILABLE",
            "PDF redaction needs pypdfium2 and Pillow to rasterize the page",
        ) from exc
    document = pdfium.PdfDocument(current)
    page = document[index]
    width, height = page.get_size()
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil().convert("RGB")
    left = max(0.0, rect["x"]) * scale
    right = min(width, rect["x"] + rect["width"]) * scale
    top = max(0.0, height - (rect["y"] + rect["height"])) * scale
    bottom = min(height, height - rect["y"]) * scale
    ImageDraw.Draw(image).rectangle([left, top, right, bottom], fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=scale * 72)
    PdfReader, _, _ = _pypdf()
    redacted = PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
    return redacted, width, height


def _fitz() -> Any:
    try:
        import pymupdf as fitz  # noqa: PLC0415
        return fitz
    except Exception:  # noqa: BLE001
        pass
    try:
        import fitz  # noqa: PLC0415
        return fitz
    except Exception:  # noqa: BLE001
        return None


def _incremental_pdf(data: bytes, edits: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]] | None:
    if os.environ.get("HARNESS_PDF_INCREMENTAL", "auto").strip().lower() in ("0", "false", "off"):
        return None
    try:
        fitz = _fitz()
    except Exception:  # noqa: BLE001
        fitz = None
    if fitz is None:
        return None
    handle, path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    try:
        with open(path, "wb") as target:
            target.write(data)
        document = fitz.open(path)
        applied: list[str] = []
        warnings: list[str] = []
        for edit in edits:
            op = edit["op"]
            if op == "pdf.rotate_pages":
                indexes = edit.get("pages")
                if indexes is None:
                    indexes = list(range(document.page_count))
                for index in indexes:
                    if 0 <= index < document.page_count:
                        page = document[index]
                        page.set_rotation((page.rotation + int(edit["degrees"])) % 360)
                applied.append(f"rotated {len(indexes)} page(s)")
            elif op == "pdf.fill_form":
                fields = edit["fields"]
                updated = 0
                for page in document:
                    for widget in page.widgets() or []:
                        if widget.field_name in fields:
                            widget.field_value = fields[widget.field_name]
                            widget.update()
                            updated += 1
                if not updated:
                    raise EditError("EDIT_TARGET_NOT_FOUND", "the PDF has no writable form fields")
                applied.append(f"filled {updated} form field(s)")
            elif op == "pdf.add_annotation":
                page = document[edit["page"]]
                rect = fitz.Rect(edit["x"], edit["y"], edit["x"] + edit["width"], edit["y"] + edit["height"])
                page.add_freetext_annot(rect, edit["text"], fontsize=12)
                applied.append(f"added a free-text annotation to page {edit['page'] + 1}")
            elif op == "pdf.set_metadata":
                document.set_metadata({str(k): str(v) for k, v in edit["metadata"].items()})
                applied.append("updated document metadata")
            elif op == "pdf.redact":
                page = document[edit["page"]]
                rect = fitz.Rect(edit["x"], edit["y"], edit["x"] + edit["width"], edit["y"] + edit["height"])
                page.add_redact_annot(rect, fill=(0, 0, 0))
                page.apply_redactions()
                applied.append(f"redacted page {edit['page'] + 1}")
            else:
                raise EditError("EDIT_OP_UNSUPPORTED", f"unsupported PDF operation {op!r}")
        document.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        pages = document.page_count
        document.close()
        with open(path, "rb") as source:
            output = source.read()
        redacted = any(edit["op"] == "pdf.redact" for edit in edits)
        return output, {
            "preservationMode": "incremental",
            "redactionMode": "incremental_true_removal" if redacted else None,
            "pages": pages,
            "applied": applied,
            "warnings": [
                *warnings,
                "the PDF was appended incrementally; original objects and the xref chain are preserved",
                *(["covered text objects were removed by PyMuPDF's redaction filter"] if redacted else []),
            ],
        }
    except EditError:
        raise
    except Exception as exc:  # noqa: BLE001 - a failed incremental save falls back honestly
        raise EditError("PDF_INCREMENTAL_FAILED", f"incremental PDF editing failed: {exc}") from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def apply_pdf_ops(data: bytes, edits: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    try:
        incremental = _incremental_pdf(data, edits)
    except EditError as exc:
        if exc.code == "PDF_INCREMENTAL_FAILED":
            incremental = None
        else:
            raise
    if incremental is not None:
        return incremental
    _, writer = _reader_writer(data)
    applied: list[str] = []
    warnings: list[str] = []

    for edit in edits:
        op = edit["op"]
        if op == "pdf.fill_form":
            fields = edit["fields"]
            updated = 0
            for page in writer.pages:
                try:
                    writer.update_page_form_field_values(page, fields, auto_regenerate=False)
                    updated += 1
                except Exception:  # noqa: BLE001 - a page without these fields is not fatal
                    continue
            if not updated:
                raise EditError("EDIT_TARGET_NOT_FOUND", "the PDF has no writable form fields")
            applied.append(f"filled form fields on {updated} page(s)")
        elif op == "pdf.rotate_pages":
            indexes = edit.get("pages")
            if indexes is None:
                indexes = list(range(len(writer.pages)))
            for index in indexes:
                if 0 <= index < len(writer.pages):
                    writer.pages[index].rotate(edit["degrees"])
            applied.append(f"rotated {len(indexes)} page(s)")
        elif op == "pdf.add_annotation":
            _, _, FreeText = _pypdf()
            index = edit["page"]
            if index >= len(writer.pages):
                raise EditError("EDIT_TARGET_NOT_FOUND", f"page {index + 1} does not exist")
            x, y = edit["x"], edit["y"]
            rect = (x, y, x + edit["width"], y + edit["height"])
            annotation = FreeText(
                text=edit["text"], rect=rect, font="Helvetica",
                font_size="12", font_color="000000",
            )
            writer.add_annotation(page_number=index, annotation=annotation)
            applied.append(f"added a free-text annotation to page {index + 1}")
        elif op == "pdf.redact":
            index = edit["page"]
            if index >= len(writer.pages):
                raise EditError("EDIT_TARGET_NOT_FOUND", f"page {index + 1} does not exist")
            current = io.BytesIO()
            writer.write(current)
            redacted, page_width, page_height = _render_redacted_page(current.getvalue(), index, edit)
            writer.remove_page(index)
            writer.insert_page(redacted, index)
            applied.append(f"redacted page {index + 1} (rasterized)")
            warnings.append(
                f"page {index + 1} was rasterized; the original text objects behind the redaction are gone, "
                "but the page is now an image"
            )
        elif op == "pdf.set_metadata":
            writer.add_metadata(edit["metadata"])
            applied.append("updated document metadata")
        else:
            raise EditError("EDIT_OP_UNSUPPORTED", f"unsupported PDF operation {op!r}")

    buffer = io.BytesIO()
    writer.write(buffer)
    output = buffer.getvalue()

    PdfReader, _, _ = _pypdf()
    check = PdfReader(io.BytesIO(output))
    detail = {
        "preservationMode": "rewrite",
        "redactionMode": "rasterized_page" if any(edit["op"] == "pdf.redact" for edit in edits) else None,
        "pages": len(check.pages),
        "applied": applied,
        "warnings": [
            *warnings,
            "PDF editing rewrites the file; original objects are copied but the byte layout is not preserved",
        ],
    }
    return output, detail


__all__ = ["apply_pdf_ops"]
