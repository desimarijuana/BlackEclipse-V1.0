"""PPTX adapter — slides, titles, text boxes, speaker notes, tables, charts, images.

Each slide becomes a `Page` (a page and a slide are both a "unit" of a document),
so a presentation is analyzable through BOTH structural extraction (here) and
visual analysis (the vision subsystem renders a slide via the shared PDF/vision
path where a raster backend exists). Charts are recorded as data; images are
extracted and passed to OCR/vision when available (spec §11).
"""

from __future__ import annotations

from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import BBox, Block, DocumentImage, DocumentIR, Page, Provenance, Table, TableCell
from .docx import analyze_embedded_image, _content_type, _sha
from .office import (
    attr, clean_text, find_local, iter_local, local, open_container,
    parse_xml, read_part, rel_attr, rels_map, resolve_target, safe_names, text_of,
)


class PptxAdapter:
    name = "pptx"
    kinds = ("pptx",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            pages=True, text=True, structure=True, tables=True, images=True,
            links=True, annotations=False, entities=True, render=True,
            charts=True, ocr=True, vision=True,
        )

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        with open_container(data) as zf:
            safe_names(zf)
            presentation = parse_xml(read_part(zf, "ppt/presentation.xml"))
            if presentation is None:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the .pptx has no ppt/presentation.xml")
            pres_rels = rels_map(zf, "ppt/presentation.xml")
            ir = DocumentIR(kind="pptx",
                            mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            file_name=name, byte_size=len(data))
            ir.title = self._core_property(zf, "title")
            ir.metadata = self._metadata(zf)

            slide_order = self._slide_order(presentation, pres_rels)
            for slide_index, slide_part in enumerate(slide_order):
                slide_root = parse_xml(read_part(zf, slide_part))
                if slide_root is None:
                    continue
                rels = rels_map(zf, slide_part)
                page = Page(index=slide_index, unit="emu", label=f"slide {slide_index + 1}")
                self._extract_slide(slide_root, rels, page)
                # Speaker notes.
                notes_part = self._notes_part(zf, slide_part)
                if notes_part:
                    notes_root = parse_xml(read_part(zf, notes_part))
                    note_text = clean_text(text_of(notes_root))
                    if note_text:
                        page.notes.append(note_text)
                        page.blocks.append(Block(
                            kind="speaker_note", text=note_text, block_id=f"note{slide_index}", order=len(page.blocks),
                            provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="pptx-ooxml"),
                        ))
                page.text = "\n".join(b.text for b in page.blocks if b.text).strip()
                page.has_text_layer = bool(page.text)
                page.text_method = "native"
                ir.pages.append(page)

            await self._process_media(zf, ir, ctx)
            for i, page in enumerate(ir.pages):
                for image in page.images:
                    image.slide = i
            return finalize_ir(ir, parser="pptx-ooxml", sha256=_sha(data), data=data)

    # ── structure ────────────────────────────────────────────────────────────────

    def _slide_order(self, presentation: Any, rels: dict[str, str]) -> list[str]:
        order: list[str] = []
        id_list = find_local(presentation, "sldIdLst")
        if id_list is not None:
            for sld in iter_local(id_list, "sldId"):
                rid = rel_attr(sld, "id")
                target = rels.get(rid)
                if target:
                    order.append(resolve_target("ppt/presentation.xml", target))
        return order

    def _extract_slide(self, slide: Any, rels: dict[str, str], page: Page) -> None:
        order = 0
        tree = find_local(slide, "cSld")
        if tree is None:
            tree = slide
        for sp in iter_local(tree, "sp"):
            ph = find_local(sp, "ph")
            ph_type = attr(ph, "type") if ph is not None else ""
            text = clean_text(text_of(sp))
            links = self._sp_links(sp, rels)
            if not text and not links:
                continue
            if ph_type in ("title", "ctrTitle"):
                kind = "slide_title"
            elif ph_type in ("ftr", "sldNum", "dt"):
                kind = "footer"
            else:
                kind = "paragraph"
            page.blocks.append(Block(
                kind=kind, text=text, block_id=f"b{order}", order=order, links=links,
                provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="pptx-ooxml"),
                details={"placeholder": ph_type} if ph_type else {},
            ))
            order += 1
        # Tables.
        for i, graphic in enumerate(iter_local(slide, "graphicFrame")):
            table_el = find_local(graphic, "tbl")
            if table_el is not None:
                table = self._table(table_el, i)
                if table:
                    page.tables.append(table)
                    page.blocks.append(Block(kind="table", text="", table_id=table.table_id, order=order,
                                             provenance=table.provenance))
                    order += 1
            chart = find_local(graphic, "chart")
            if chart is not None:
                rid = attr(chart, "id")
                target = rels.get(rid)
                page.blocks.append(Block(kind="chart", text="", block_id=f"chart{order}", order=order,
                                         details={"target": target} if target else {},
                                         provenance=Provenance(method="native", status="observed",
                                                               confidence=0.9, engine="pptx-ooxml")))
                order += 1

    def _sp_links(self, sp: Any, rels: dict[str, str]) -> list[str]:
        links: list[str] = []
        for hlink in iter_local(sp, "hlinkClick"):
            rid = attr(hlink, "id")
            target = rels.get(rid)
            if target and not target.startswith("#"):
                links.append(target)
        return links

    def _table(self, tbl: Any, index: int) -> Optional[Table]:
        rows: list[list[str]] = []
        cells: list[TableCell] = []
        for r_index, tr in enumerate([t for t in tbl if local(t.tag) == "tr"]):
            row: list[str] = []
            for c_index, tc in enumerate([c for c in tr if local(c.tag) == "tc"]):
                text = clean_text(text_of(tc))
                row.append(text)
                span = attr(tc, "gridSpan", "1")
                cells.append(TableCell(text=text, row=r_index, column=c_index,
                                       col_span=int(span or "1"),
                                       provenance=Provenance(method="native", status="extracted",
                                                             confidence=0.95, engine="pptx-ooxml")))
            if row:
                rows.append(row)
        if not rows:
            return None
        return Table(table_id=f"table_{index}", rows=rows, cells=cells, headers=rows[0] if rows else [],
                     provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="pptx-ooxml"))

    # ── notes / metadata ──────────────────────────────────────────────────────────

    def _notes_part(self, zf: Any, slide_part: str) -> Optional[str]:
        rels = rels_map(zf, slide_part)
        for target in rels.values():
            if "notesSlide" in target:
                return resolve_target(slide_part, target)
        return None

    def _core_property(self, zf: Any, key: str) -> Optional[str]:
        core = parse_xml(read_part(zf, "docProps/core.xml"))
        if core is None:
            return None
        for el in core.iter():
            if local(el.tag) == key and el.text:
                return el.text.strip()
        return None

    def _metadata(self, zf: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for part, keys in (("docProps/core.xml", ("title", "creator", "created", "modified", "subject")),
                           ("docProps/app.xml", ("Application", "Company", "Slides", "Words"))):
            root = parse_xml(read_part(zf, part))
            if root is None:
                continue
            for el in root.iter():
                name = local(el.tag)
                if name in keys and el.text:
                    out[name] = el.text.strip()
        return out

    # ── media ─────────────────────────────────────────────────────────────────────

    async def _process_media(self, zf: Any, ir: DocumentIR, ctx: ParseContext) -> None:
        media = sorted(n for n in safe_names(zf) if n.startswith("ppt/media/"))
        for i, part_name in enumerate(media):
            raw = read_part(zf, part_name)
            if not raw:
                continue
            image = DocumentImage(
                image_id=f"img_{i}", content_type=_content_type(part_name), byte_size=len(raw),
                sha256=_sha(raw), data=raw,
                provenance=Provenance(method="native", status="observed", confidence=0.9, engine="pptx-ooxml"),
            )
            await analyze_embedded_image(image, ctx)
            ir.images.append(image)


__all__ = ["PptxAdapter"]
