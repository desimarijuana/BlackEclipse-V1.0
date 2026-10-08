"""ODF adapter — OpenDocument Text (.odt), Presentation (.odp) and Spreadsheet (.ods).

An ODF file is a ZIP whose `content.xml` holds the document. Structure is
preserved (headings with outline levels, paragraphs, lists, tables with cells);
spreadsheets become `Sheet`s with a sparse cell model and a preview, matching the
XLSX adapter's shape so downstream code is uniform.
"""

from __future__ import annotations

from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import Block, DocumentIR, Page, Provenance, Sheet, Table, TableCell
from .docx import _sha
from .office import (
    attr, clean_text, find_local, iter_local, local, open_container,
    parse_xml, read_part, safe_names, text_of,
)


class OdfAdapter:
    name = "odf"
    kinds = ("odt", "odp", "ods")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            pages=True, text=True, structure=True, tables=True, images=False,
            links=True, sheets=True, formulas=True, render=False,
        )

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        with open_container(data) as zf:
            safe_names(zf)
            content = parse_xml(read_part(zf, "content.xml"))
            if content is None:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the ODF has no content.xml")
            ir = DocumentIR(kind=kind, mime_type=_odf_mime(kind), file_name=name, byte_size=len(data))
            ir.metadata = self._metadata(zf)
            ir.title = ir.metadata.get("title")
            if kind == "ods":
                self._spreadsheet(content, ir)
            else:
                self._text_like(content, ir)
            return finalize_ir(ir, parser="odf", sha256=_sha(data), data=data)

    def _text_like(self, content: Any, ir: DocumentIR) -> None:
        body = find_local(content, "body")
        if body is None:
            body = content
        page = Page(index=0, unit="points", label="body", text_method="native")
        order = 0
        for el in body.iter():
            lname = local(el.tag)
            if lname == "h":
                text = clean_text(text_of(el))
                if text:
                    level = int(attr(el, "outline-level", "1") or "1")
                    page.blocks.append(Block(kind="heading", text=text, level=level, block_id=f"b{order}", order=order,
                                             provenance=Provenance(method="native", status="extracted", confidence=0.96, engine="odf")))
                    order += 1
            elif lname == "p":
                # Only top-level paragraphs (inside text:p, not table cells handled below).
                text = clean_text(text_of(el))
                if text and find_local(el, "span") is None or text:
                    page.blocks.append(Block(kind="paragraph", text=text, block_id=f"b{order}", order=order,
                                             provenance=Provenance(method="native", status="extracted", confidence=0.9, engine="odf")))
                    order += 1
            elif lname == "table":
                table = self._table(el, len(page.tables))
                if table:
                    page.tables.append(table)
                    page.blocks.append(Block(kind="table", text="", table_id=table.table_id, order=order,
                                             provenance=table.provenance))
                    order += 1
        page.text = "\n".join(b.text for b in page.blocks if b.text).strip()
        page.has_text_layer = bool(page.text)
        ir.pages.append(page)

    def _table(self, el: Any, index: int) -> Optional[Table]:
        rows: list[list[str]] = []
        cells: list[TableCell] = []
        for r, row in enumerate([c for c in el if local(c.tag) == "table-row"]):
            values: list[str] = []
            for c, cell in enumerate([c for c in row if local(c.tag) == "table-cell"]):
                text = clean_text(" ".join(text_of(p) for p in iter_local(cell, "p")))
                repeat = int(attr(cell, "number-columns-repeated", "1") or "1")
                for _ in range(min(repeat, 50)):
                    values.append(text)
                    cells.append(TableCell(text=text, row=r, column=c,
                                           provenance=Provenance(method="native", status="extracted", confidence=0.9, engine="odf")))
            if values:
                rows.append(values)
        if not rows:
            return None
        return Table(table_id=f"table_{index}", rows=rows, cells=cells, headers=rows[0] if rows else [],
                     provenance=Provenance(method="native", status="extracted", confidence=0.9, engine="odf"))

    def _spreadsheet(self, content: Any, ir: DocumentIR) -> None:
        body = find_local(content, "body") or content
        for index, table_el in enumerate(iter_local(body, "table")):
            sheet = Sheet(index=index, name=attr(table_el, "name", f"Sheet{index + 1}"), text_method="native")
            max_r = max_c = 0
            for r, row in enumerate([c for c in table_el if local(c.tag) == "table-row"]):
                for c, cell in enumerate([c for c in row if local(c.tag) == "table-cell"]):
                    text = clean_text(text_of(cell))
                    formula = attr(cell, "formula", "") or None
                    if text or formula:
                        sheet.cells.append(TableCell(
                            text=text, row=r, column=c, formula=formula,
                            value=attr(cell, "value", None),
                            provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="odf"),
                        ))
                    max_r = max(max_r, r); max_c = max(max_c, c)
                    repeat_c = int(attr(cell, "number-columns-repeated", "1") or "1")
                    max_c = max(max_c, c + repeat_c - 1)
            sheet.rows, sheet.columns = max_r + 1, max_c + 1
            sheet.preview, sheet.preview_rows, sheet.preview_columns = _sheet_preview(
                sheet.cells, sheet.rows, sheet.columns, ir.metadata.get("previewRows", 50), ir.metadata.get("previewColumns", 30),
            )
            ir.sheets.append(sheet)

    def _metadata(self, zf: Any) -> dict[str, Any]:
        meta = parse_xml(read_part(zf, "meta.xml"))
        out: dict[str, Any] = {}
        if meta is not None:
            for el in meta.iter():
                name = local(el.tag)
                if name in ("title", "creator", "creation-date", "date", "subject") and el.text:
                    out[name] = el.text.strip()
        return out


def _sheet_preview(cells: list[TableCell], rows: int, columns: int, pr: int, pc: int) -> tuple[list[list[Any]], int, int]:
    r = min(rows, pr); c = min(columns, pc)
    grid: list[list[Any]] = [[None] * c for _ in range(r)]
    for cell in cells:
        if cell.row < r and cell.column < c:
            grid[cell.row][cell.column] = cell.text or (f"={cell.formula}" if cell.formula else None)
    return grid, r, c


def _odf_mime(kind: str) -> str:
    return {
        "odt": "application/vnd.oasis.opendocument.text",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
    }.get(kind, "application/octet-stream")


__all__ = ["OdfAdapter"]
