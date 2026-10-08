"""DOCX adapter — paragraph/heading/section/list/table/footnote/comment structure.

Parses the WordprocessingML parts in memory. Structure is preserved (headings,
lists, tables with per-cell provenance, hyperlinks, headers/footers, footnotes,
comments) rather than flattened to plain text (spec §10). Embedded images are
extracted and (when an asset store + OCR are available) analysed through the
vision subsystem; otherwise they are recorded with metadata only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import BBox, Block, DocumentImage, DocumentIR, Page, Provenance, Table, TableCell
from .office import (
    attr,
    clean_text,
    find_local,
    iter_local,
    local,
    open_container,
    parse_xml,
    read_part,
    rels_map,
    resolve_target,
    safe_names,
    text_of,
)

#: Word heading style names → level.
_HEADING_STYLE = {
    "heading1": 1, "heading2": 2, "heading3": 3, "heading4": 4, "heading5": 5, "heading6": 6,
    "title": 0, "subtitle": 0,
}


class DocxAdapter:
    name = "docx"
    kinds = ("docx",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            pages=True, text=True, structure=True, tables=True, images=True,
            links=True, annotations=True, entities=True, render=False,
            ocr=True, vision=True,
        )

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        zf = open_container(data)
        with zf:
            safe_names(zf)
            document_xml = read_part(zf, "word/document.xml")
            if document_xml is None:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the .docx has no word/document.xml")
            root = parse_xml(document_xml)
            rels = rels_map(zf, "word/document.xml")

            ir = DocumentIR(kind="docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            file_name=name, byte_size=len(data))
            title = self._core_property(zf, "title")
            if title:
                ir.title = title
            ir.metadata = self._metadata(zf)

            body = find_local(root, "body")
            page = Page(index=0, unit="points", label="body")
            self._walk_block_level(body, zf, rels, page)
            page.text = "\n".join(b.text for b in page.blocks if b.text).strip()
            page.has_text_layer = bool(page.text)
            page.text_method = "native"

            # Headers / footers become their own pseudo-pages so nothing is lost.
            for part_name in sorted(n for n in safe_names(zf) if n.startswith("word/header") or n.startswith("word/footer")):
                part_root = parse_xml(read_part(zf, part_name))
                hp = Page(index=len(ir.pages) + 1 if not ir.pages else len(ir.pages), unit="points",
                          label=part_name.rsplit("/", 1)[-1])
                self._walk_block_level(find_local(part_root, "body") or part_root, zf, rels, hp,
                                       default_kind="header" if "header" in part_name else "footer")
                if hp.text or hp.blocks:
                    hp.text = "\n".join(b.text for b in hp.blocks if b.text)
                    hp.has_text_layer = bool(hp.text)
                    hp.text_method = "native"
                    page.notes.append(part_name)
                    ir.pages.append(hp)

            self._collect_footnotes(zf, page)
            self._collect_comments(zf, page)

            ir.pages.insert(0, page)

            # Images: extract bytes; OCR/vision if services are present.
            await self._process_images(zf, page, ctx)

            return finalize_ir(ir, parser="docx-ooxml", sha256=_sha(data), data=data)

    # ── walking ────────────────────────────────────────────────────────────────

    def _walk_block_level(self, container: Optional[Any], zf: Any, rels: dict[str, str], page: Page,
                          *, default_kind: str = "paragraph") -> None:
        if container is None:
            return
        order = len(page.blocks)
        for child in list(container):
            lname = local(child.tag)
            if lname == "p":
                block = self._paragraph(child, rels, order)
                if block is not None:
                    if default_kind != "paragraph" and block.kind == "paragraph":
                        block.kind = default_kind  # type: ignore[assignment]
                    page.blocks.append(block)
                    for link in block.links:
                        page.links.append(link)
                    order += 1
            elif lname == "tbl":
                table = self._table(child, order)
                if table is not None:
                    page.tables.append(table)
                    page.blocks.append(Block(kind="table", text="", table_id=table.table_id, order=order,
                                             provenance=table.provenance,
                                             bbox=BBox(0, 0, 0, 0, "none")))
                    order += 1
                for extra_table in self._nested_tables(child, order):
                    page.tables.append(extra_table)
                    page.blocks.append(Block(kind="table", text="", table_id=extra_table.table_id, order=order,
                                             provenance=extra_table.provenance, bbox=BBox(0, 0, 0, 0, "none")))
                    order += 1
            elif lname == "sdt":  # structured document tag — recurse into content
                content = find_local(child, "sdtContent")
                self._walk_block_level(content, parent_rels(rels, zf, child), page, default_kind=default_kind)
            elif lname in ("sectPr",):
                continue

    def _paragraph(self, p: Any, rels: dict[str, str], order: int) -> Optional[Block]:
        text = clean_text(text_of(p))
        style = self._paragraph_style(p)
        links = self._paragraph_links(p, rels)
        if not text and not links:
            return None
        kind = "paragraph"
        level: Optional[int] = None
        num_pr = find_local(p, "numPr")
        if style and style in _HEADING_STYLE:
            kind = "heading"
            level = _HEADING_STYLE[style] or None
        elif style and style.lower().startswith("heading"):
            kind = "heading"
            digits = "".join(c for c in style if c.isdigit())
            level = int(digits) if digits else 1
        elif num_pr is not None:
            kind = "list_item"
        return Block(
            kind=kind, text=text, block_id=f"b{order}", level=level, order=order,
            provenance=Provenance(method="native", status="extracted", confidence=0.98, engine="docx-ooxml"),
            links=links, details={"style": style} if style else {},
        )

    def _paragraph_style(self, p: Any) -> str:
        ppr = find_local(p, "pPr")
        if ppr is None:
            return ""
        pstyle = find_local(ppr, "pStyle")
        return attr(pstyle, "val", "")

    def _paragraph_links(self, p: Any, rels: dict[str, str]) -> list[str]:
        links: list[str] = []
        for hyperlink in iter_local(p, "hyperlink"):
            rid = attr(hyperlink, "id")
            target = rels.get(rid)
            if target and not target.startswith("#"):
                links.append(target)
        return links

    def _table(self, tbl: Any, order: int) -> Optional[Table]:
        rows: list[list[str]] = []
        cells: list[TableCell] = []
        table_id = f"table_{order}"
        for r_index, tr in enumerate(iter_local(tbl, "tr")):
            row_text: list[str] = []
            for c_index, tc in enumerate([c for c in tr if local(c.tag) == "tc"]):
                cell_text = clean_text(" ".join(text_of(p) for p in iter_local(tc, "p")))
                row_text.append(cell_text)
                span = find_local(tc, "gridSpan")
                row_span = find_local(tc, "vMerge")
                cells.append(TableCell(
                    text=cell_text, row=r_index, column=c_index,
                    col_span=int(attr(span, "val", "1") or "1") if span is not None else 1,
                    row_span=1 if row_span is None else 1,
                    provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="docx-ooxml"),
                ))
            if row_text:
                rows.append(row_text)
        if not rows:
            return None
        table = Table(table_id=table_id, rows=rows, cells=cells,
                     headers=rows[0] if rows else [],
                     provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="docx-ooxml"))
        return table

    def _nested_tables(self, tbl: Any, order: int) -> list[Table]:
        nested: list[Table] = []
        for i, sub in enumerate(iter_local(tbl, "tbl")):
            if sub is tbl:
                continue
            t = self._table(sub, order + i + 1)
            if t is not None:
                nested.append(t)
        return nested

    # ── metadata / footnotes / comments ─────────────────────────────────────────

    def _core_property(self, zf: Any, key: str) -> Optional[str]:
        core = parse_xml(read_part(zf, "docProps/core.xml"))
        if core is None:
            return None
        for el in core.iter():
            if local(el.tag) == key and el.text:
                return el.text.strip()
        return None

    def _metadata(self, zf: Any) -> dict[str, Any]:
        core = parse_xml(read_part(zf, "docProps/core.xml"))
        app = parse_xml(read_part(zf, "docProps/app.xml"))
        out: dict[str, Any] = {}
        for source, keys in ((core, ("title", "creator", "subject", "created", "modified", "keywords")),
                             (app, ("Application", "Company", "Pages", "Words"))):
            if source is None:
                continue
            for el in source.iter():
                name = local(el.tag)
                if name in keys and el.text:
                    out[name] = el.text.strip()
        return out

    def _collect_footnotes(self, zf: Any, page: Page) -> None:
        root = parse_xml(read_part(zf, "word/footnotes.xml"))
        if root is None:
            return
        order = len(page.blocks)
        for fn in iter_local(root, "footnote"):
            text = clean_text(text_of(fn))
            if not text:
                continue
            page.blocks.append(Block(
                kind="footnote", text=text, block_id=f"fn{order}", order=order,
                provenance=Provenance(method="native", status="extracted", confidence=0.9, engine="docx-ooxml"),
            ))
            order += 1

    def _collect_comments(self, zf: Any, page: Page) -> None:
        root = parse_xml(read_part(zf, "word/comments.xml"))
        if root is None:
            return
        for comment in iter_local(root, "comment"):
            text = clean_text(text_of(comment))
            if text:
                page.notes.append(f"comment: {text}")

    # ── images ────────────────────────────────────────────────────────────────────

    async def _process_images(self, zf: Any, page: Page, ctx: ParseContext) -> None:
        media = sorted(n for n in safe_names(zf) if n.startswith("word/media/"))
        for i, part_name in enumerate(media):
            raw = read_part(zf, part_name)
            if not raw:
                continue
            content_type = _content_type(part_name)
            image = DocumentImage(
                image_id=f"img_{i}", content_type=content_type, byte_size=len(raw),
                sha256=_sha(raw), data=raw,
                provenance=Provenance(method="native", status="observed", confidence=0.9, engine="docx-ooxml"),
            )
            await analyze_embedded_image(image, ctx)
            page.images.append(image)


def parent_rels(rels: dict[str, str], zf: Any, el: Any) -> dict[str, str]:
    # SDTs share the document's relationship namespace; reuse the same map.
    return rels


def _content_type(part_name: str) -> str:
    ext = part_name.rsplit(".", 1)[-1].lower()
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
        "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff", "webp": "image/webp",
        "emf": "image/emf", "wmf": "image/wmf", "svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")


async def analyze_embedded_image(image: DocumentImage, ctx: ParseContext) -> None:
    """OCR/describe an embedded image with the available services (best-effort)."""
    if not image.data:
        return
    try:
        from ...vision.image import decode_bytes  # type: ignore

        decoded = decode_bytes(image.data, source=f"embedded:{image.image_id}")
        image.width, image.height = decoded.width, decoded.height
    except Exception:  # noqa: BLE001 - metadata is optional
        pass

    # Deterministic OCR first.
    if ctx.ocr is not None and image.data:
        try:
            info = ctx.ocr(image.data)
            if hasattr(info, "__await__"):
                info = await info
            if getattr(info, "text", ""):
                image.ocr_text = info.text
        except Exception:  # noqa: BLE001 - OCR is best-effort for embedded images
            pass
    # Vision description when a model is available and OCR produced nothing.
    if image.ocr_text is None and ctx.analyze_image is not None:
        try:
            result = await ctx.analyze_image(image.data, "Describe this embedded image and transcribe any text.", mode="describe")
            payload = result.to_dict() if hasattr(result, "to_dict") else result
            if isinstance(payload, dict) and payload.get("ok"):
                image.caption = str(payload.get("description") or "")[:2000] or None
        except Exception:  # noqa: BLE001
            pass


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


__all__ = ["DocxAdapter", "analyze_embedded_image"]
