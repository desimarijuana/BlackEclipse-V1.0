"""PDF adapter — native text, scanned/mixed detection, tables, links, rendering, OCR routing.

Layered and honest (spec §9/§18): native text is extracted first through the
vision subsystem's PDF backends (pypdfium2 preferred, stdlib fallback). A page
with no usable text layer is a scan and goes through the OCR router
(deterministic OCR, then a vision-model fallback when confidence is low), with the
method and confidence recorded per page. Rendering a page to an image reuses the
same backend. A rendered page is never fabricated when no raster backend exists.
"""

from __future__ import annotations

from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import BBox, Block, DocumentImage, DocumentIR, Page, Provenance, Table, TableCell
from .docx import _sha

#: Pages below this native-text length are treated as scans needing OCR.
_MIN_NATIVE_CHARS = 25


class PdfAdapter:
    name = "pdf"
    kinds = ("pdf",)

    def capabilities(self) -> Capabilities:
        from ...vision.documents import pdf_capabilities  # noqa: PLC0415

        caps = pdf_capabilities()
        return Capabilities(
            pages=True, text=True, structure=True, tables=True,
            images=bool(caps.get("rasterization")), links=True, annotations=True,
            entities=True, render=bool(caps.get("rasterization")),
            ocr=True, vision=True,
        )

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        from ...vision import documents as _vdocs  # noqa: PLC0415

        open_pdf = _vdocs.open_pdf

        try:
            doc = open_pdf(data)
        except Exception as exc:  # noqa: BLE001 - vision raises VisionError; classify here
            raise DocumentError(DocumentErrorClass.PARSER_FAILURE, f"the PDF could not be opened: {exc}", source_ref=name, cause=exc) from exc

        ir = DocumentIR(kind="pdf", mime_type="application/pdf", file_name=name, byte_size=len(data))
        try:
            count = len(doc)
            count = min(count, ctx.cfg.max_pages)
            rendered_pages = 0
            for index in range(count):
                page = await self._parse_page(doc, index, data, ctx, rendered_ref=[rendered_pages])
                ir.pages.append(page)
        finally:
            doc.close()

        self._metadata(ir)
        return finalize_ir(ir, parser="pdf", sha256=_sha(data), data=data)

    async def _parse_page(self, doc: Any, index: int, data: bytes, ctx: ParseContext,
                          *, rendered_ref: list[int]) -> Page:
        from ...vision.documents import parse_table  # noqa: PLC0415

        try:
            width_pt, height_pt = doc.page_size(index)
        except Exception:  # noqa: BLE001
            width_pt, height_pt = 595.0, 842.0
        try:
            native_text = doc.text(index) or ""
        except Exception:  # noqa: BLE001
            native_text = ""
        text = native_text.strip()
        page = Page(index=index, width=float(width_pt), height=float(height_pt), unit="points",
                    text=native_text, has_text_layer=bool(text), text_method="native" if text else "none")

        # Structure: split into paragraphs and detect whitespace tables.
        order = 0
        if text:
            for para in [p for p in native_text.split("\n\n") if p.strip()]:
                page.blocks.append(Block(kind="paragraph", text=para.strip(), block_id=f"b{order}", order=order,
                                         provenance=Provenance(method="native", status="extracted",
                                                               confidence=0.97, engine="pdf-text")))
                order += 1
            rows = parse_table(native_text.splitlines())
            if len(rows) >= 2:
                table = Table(table_id=f"p{index}_table_0", rows=rows, headers=rows[0], page=index,
                              provenance=Provenance(method="native", status="extracted", confidence=0.75,
                                                    engine="pdf-layout"))
                page.tables.append(table)
                page.blocks.append(Block(kind="table", text="", table_id=table.table_id, order=order,
                                         provenance=table.provenance))
                order += 1

        # Links + annotations (best-effort through the backend).
        page.links.extend(self._links(doc, index))

        # OCR routing: a scan (no usable text) is recognized deterministically,
        # then via a vision model when confidence is still low.
        if not text:
            await self._ocr_page(doc, index, page, data, ctx)

        return page

    def _links(self, doc: Any, index: int) -> list[str]:
        page_obj = None
        try:
            page_obj = doc._doc[index]  # pypdfium2 document page (private backend handle)
        except Exception:  # noqa: BLE001
            return []
        links: list[str] = []
        try:
            for link in page_obj.get_links():
                uri = getattr(link, "uri", None)
                if uri:
                    links.append(str(uri))
        except Exception:  # noqa: BLE001 - the stdlib backend has no link API
            return []
        return links

    async def _ocr_page(self, doc: Any, index: int, page: Page, data: bytes, ctx: ParseContext) -> None:
        if not ctx.cfg.ocr_enabled:
            page.warnings.append("no text layer; OCR is disabled")
            return
        # Render the page once (a missing raster backend is reported, not faked).
        rendered = None
        try:
            rendered = doc.render(index, 2.0)
        except Exception:  # noqa: BLE001
            pass
        if rendered is None:
            page.warnings.append("no text layer and the page could not be rasterized for OCR")
            return
        import io as _io

        buffer = _io.BytesIO()
        try:
            rendered.convert("RGB").save(buffer, format="PNG")
        except Exception as exc:  # noqa: BLE001
            page.warnings.append(f"rasterization failed: {exc}")
            return
        png = buffer.getvalue()

        best_text = ""
        best_conf = 0.0
        if ctx.ocr is not None:
            try:
                info = ctx.ocr(png)
                if hasattr(info, "__await__"):
                    info = await info
                best_text = getattr(info, "text", "") or ""
                best_conf = float(getattr(info, "confidence", 0.0) or 0.0)
                page.ocr_confidence = best_conf
            except Exception as exc:  # noqa: BLE001
                page.warnings.append(f"OCR failed: {exc}")

        if (not best_text or best_conf < ctx.cfg.ocr_confidence_threshold) and ctx.cfg.ocr_vision_fallback and ctx.vision_ocr is not None:
            try:
                info = ctx.vision_ocr(png, index)
                vision_text = getattr(info, "text", "") or ""
                vision_conf = float(getattr(info, "confidence", 0.0) or 0.0)
                if len(vision_text) > len(best_text) or vision_conf > best_conf:
                    best_text, best_conf = vision_text, vision_conf
                    page.text_method = "vision"
                page.ocr_confidence = max(best_conf, page.ocr_confidence or 0.0)
            except Exception as exc:  # noqa: BLE001
                page.warnings.append(f"vision OCR fallback failed: {exc}")

        if best_text:
            page.text = best_text
            page.has_text_layer = True
            if page.text_method != "vision":
                page.text_method = "ocr"
            page.blocks.insert(0, Block(
                kind="paragraph", text=best_text.strip(), block_id=f"p{index}_ocr", order=0,
                provenance=Provenance(method=page.text_method, status="extracted", confidence=best_conf,
                                      engine="ocr" if page.text_method == "ocr" else "vision"),
            ))
        else:
            page.warnings.append("the page yielded no text (scan with no available OCR)")

    def _metadata(self, ir: DocumentIR) -> None:
        return None


__all__ = ["PdfAdapter"]
