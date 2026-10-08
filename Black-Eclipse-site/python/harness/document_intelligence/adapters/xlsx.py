"""XLSX/ODS adapter — spreadsheets treated as structured data, not documents.

Parses the workbook in memory: worksheets (including hidden), a sparse cell model
that keeps **formulas separate from cached values** (spec §12), merged cells,
named ranges, comments, conditional formatting, tables and charts. A bounded
top-left preview plus a per-sheet `Table` give the agent a cheap view; large
sheets are handled by the query engine, never dumped into model context.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import BBox, DocumentIR, Provenance, Sheet, Table, TableCell
from .docx import _sha
from .office import (
    attr, find_local, iter_local, local, open_container, parse_xml,
    read_part, rel_attr, rels_map, resolve_target, safe_names, text_of,
)

_CELL_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def column_index(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def split_ref(ref: str) -> Optional[tuple[int, int]]:
    """`"B12"` -> (row_zero_based=11, col_zero_based=1)."""
    match = _CELL_RE.match(ref or "")
    if not match:
        return None
    col = column_index(match.group(1))
    row = int(match.group(2)) - 1
    return row, col


class XlsxAdapter:
    name = "xlsx"
    kinds = ("xlsx",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            pages=False, text=True, structure=True, tables=True, images=True,
            links=True, annotations=True, sheets=True, formulas=True, charts=True,
            render=False, ocr=False, vision=False,
        )

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        with open_container(data) as zf:
            safe_names(zf)
            workbook = parse_xml(read_part(zf, "xl/workbook.xml"))
            if workbook is None:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the .xlsx has no xl/workbook.xml")
            rels = rels_map(zf, "xl/workbook.xml")
            shared = self._shared_strings(zf)

            ir = DocumentIR(kind="xlsx",
                            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            file_name=name, byte_size=len(data))
            ir.title = self._core_property(zf, "title")
            ir.metadata = self._metadata(zf)
            ir.metadata["namedRanges"] = self._named_ranges(workbook)

            for index, sheet_el in enumerate(iter_local(workbook, "sheet")):
                sheet_name = attr(sheet_el, "name", f"Sheet{index + 1}")
                state = attr(sheet_el, "state", "visible")
                rid = rel_attr(sheet_el, "id")
                target = rels.get(rid)
                if not target:
                    continue
                part = resolve_target("xl/workbook.xml", target)
                sheet_root = parse_xml(read_part(zf, part))
                if sheet_root is None:
                    continue
                sheet = self._parse_sheet(zf, part, sheet_root, sheet_name, hidden=(state == "hidden" or state == "veryHidden"),
                                          ctx=ctx, shared=shared)
                ir.sheets.append(sheet)
            return finalize_ir(ir, parser="xlsx-ooxml", sha256=_sha(data), data=data)

    # ── parts ─────────────────────────────────────────────────────────────────────

    def _shared_strings(self, zf: Any) -> list[str]:
        root = parse_xml(read_part(zf, "xl/sharedStrings.xml"))
        if root is None:
            return []
        return [text_of(si) for si in iter_local(root, "si")]

    def _named_ranges(self, workbook: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for dn in iter_local(workbook, "definedName"):
            out.append({"name": attr(dn, "name"), "value": (dn.text or "").strip(),
                        "localSheetId": attr(dn, "localSheetId", "") or None})
        return out

    def _parse_sheet(self, zf: Any, part: str, root: Any, name: str, *, hidden: bool,
                     ctx: ParseContext, shared: list[str]) -> Sheet:
        sheet = Sheet(index=0, name=name, hidden=hidden)
        cells: list[TableCell] = []
        max_row = 0
        max_col = 0
        cell_cap = ctx.cfg.max_table_cells
        truncated = False
        for c_el in iter_local(root, "c"):
            ref = attr(c_el, "r")
            pos = split_ref(ref)
            if pos is None:
                continue
            row, col = pos
            max_row = max(max_row, row)
            max_col = max(max_col, col)
            if len(cells) >= cell_cap:
                truncated = True
                break
            cell_type = attr(c_el, "t", "")
            formula_el = find_local(c_el, "f")
            formula = (formula_el.text or "").strip() if formula_el is not None and formula_el.text else None
            value_el = find_local(c_el, "v")
            raw_value = value_el.text if value_el is not None and value_el.text is not None else None
            display = ""
            value: Any = None
            if cell_type == "s" and raw_value is not None:
                try:
                    display = shared[int(raw_value)]
                    value = display
                except (ValueError, IndexError):
                    display = ""
            elif cell_type == "inlineStr":
                display = text_of(c_el)
                value = display
            elif cell_type in ("str",):
                display = raw_value or ""
                value = display
            elif cell_type == "b":
                display = "TRUE" if raw_value == "1" else "FALSE"
                value = raw_value == "1"
            elif cell_type == "e":
                display = raw_value or "#ERROR"
                value = display
            else:
                display = raw_value or ""
                try:
                    value = float(display) if "." in display or "e" in display.lower() else int(display)
                except (ValueError, TypeError):
                    value = display if display else None
            if not display and formula is None:
                continue
            cells.append(TableCell(
                text=display, row=row, column=col, formula=formula, value=value,
                provenance=Provenance(method="native", status="extracted", confidence=0.98, engine="xlsx-ooxml"),
            ))
        sheet.rows = max_row + 1
        sheet.columns = max_col + 1
        sheet.cells = cells

        merges = find_local(root, "mergeCells")
        if merges is not None:
            sheet.merges = [attr(m, "ref") for m in iter_local(merges, "mergeCell") if attr(m, "ref")]

        for row_el in iter_local(root, "row"):
            if attr(row_el, "hidden") == "1":
                r = attr(row_el, "r")
                if r.isdigit():
                    sheet.hidden_rows.append(int(r) - 1)
        cols_el = find_local(root, "cols")
        if cols_el is not None:
            for col_el in iter_local(cols_el, "col"):
                if attr(col_el, "hidden") == "1":
                    try:
                        lo = int(attr(col_el, "min", "1")); hi = int(attr(col_el, "max", str(lo)))
                    except ValueError:
                        continue
                    sheet.hidden_columns.extend(range(lo - 1, hi))

        cf = find_local(root, "conditionalFormatting")
        if cf is not None:
            for block in iter_local(root, "conditionalFormatting"):
                sheet.conditional_formats.append({"range": attr(block, "sqref")})

        # Comments, tables, charts and hyperlinks via the sheet's rels.
        sheet_rels = rels_map(zf, part)
        for rid, target in sheet_rels.items():
            resolved = resolve_target(part, target)
            if "comments" in target and target.endswith(".xml") and resolved.startswith("xl/"):
                self._comments(zf, resolved, sheet)
            elif "/tables/" in target or target.startswith("tables/"):
                table = self._table_part(zf, resolved)
                if table is not None:
                    sheet.tables.append(table)
            elif "/drawings/" in target or "drawings/" in target:
                self._drawing(zf, resolved, sheet)
        # Hyperlinks inside the sheet.
        for link in iter_local(root, "hyperlink"):
            ref = attr(link, "ref")
            target = attr(link, "location") or attr(link, "id")
            if target:
                sheet.links.append(f"{ref}: {target}")

        sheet.preview, sheet.preview_rows, sheet.preview_columns = self._build_preview(
            cells, max_row + 1, max_col + 1, ctx.cfg.preview_rows, ctx.cfg.preview_columns,
        )
        if cells:
            sheet.tables.append(self._used_range_table(name, cells, max_col))
        if truncated:
            sheet.warnings.append(f"the sheet was truncated at {cell_cap} cells")
        if not cells:
            sheet.text_method = "native"
        return sheet

    def _used_range_table(self, name: str, cells: list[TableCell], max_col: int) -> Table:
        """Materialize the sheet's used range into row arrays for retrieval/query."""
        by_row: dict[int, list[str | None]] = {}
        for cell in cells:
            row = by_row.setdefault(cell.row, [None] * (max_col + 1))
            while len(row) <= cell.column:
                row.append(None)
            row[cell.column] = cell.text if cell.text else (f"={cell.formula}" if cell.formula else "")
        rows: list[list[str]] = []
        for r in sorted(by_row):
            values = [("" if v is None else v) for v in by_row[r]]
            rows.append(values)
        headers = [f"col_{i + 1}" for i in range(max_col + 1)]
        if rows:
            headers = [c if c else f"col_{i + 1}" for i, c in enumerate(rows[0])]
            rows = rows[1:]
        return Table(table_id=f"used:{name}", rows=rows, headers=headers, sheet=name,
                     provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="xlsx-ooxml"))

    def _build_preview(self, cells: list[TableCell], rows: int, cols: int,
                       preview_rows: int, preview_cols: int) -> tuple[list[list[Any]], int, int]:
        r = min(rows, preview_rows)
        c = min(cols, preview_cols)
        grid: list[list[Any]] = [[None] * c for _ in range(r)]
        for cell in cells:
            if cell.row < r and cell.column < c:
                grid[cell.row][cell.column] = cell.text if cell.text else (f"={cell.formula}" if cell.formula else None)
        return grid, r, c

    def _comments(self, zf: Any, part: str, sheet: Sheet) -> None:
        root = parse_xml(read_part(zf, part))
        if root is None:
            return
        for comment in iter_local(root, "comment"):
            ref = attr(comment, "ref")
            text = text_of(comment)
            if text:
                sheet.comments.append({"cell": ref, "text": text})

    def _table_part(self, zf: Any, part: str) -> Optional[Table]:
        root = parse_xml(read_part(zf, part))
        if root is None:
            return None
        name = attr(root, "name", "table")
        ref = attr(root, "ref", "")
        columns = [attr(c, "name") for c in iter_local(root, "tableColumn")]
        return Table(table_id=f"table:{name}", headers=columns, rows=[], sheet=name,
                     provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="xlsx-ooxml"),
                     caption=ref or None)

    def _drawing(self, zf: Any, part: str, sheet: Sheet) -> None:
        root = parse_xml(read_part(zf, part))
        if root is None:
            return
        rels = rels_map(zf, part)
        for chart_ref in iter_local(root, "chart"):
            rid = attr(chart_ref, "id")
            target = rels.get(rid)
            title = None
            chart_part = None
            if target:
                chart_part = resolve_target(part, target)
                chart_root = parse_xml(read_part(zf, chart_part))
                title_el = find_local(chart_root, "title")
                if title_el is not None:
                    title = text_of(title_el) or None
            sheet.charts.append({"part": chart_part, "title": title})

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
        for part, keys in (("docProps/core.xml", ("title", "creator", "created", "modified")),
                           ("docProps/app.xml", ("Application", "Company"))):
            root = parse_xml(read_part(zf, part))
            if root is None:
                continue
            for el in root.iter():
                name = local(el.tag)
                if name in keys and el.text:
                    out[name] = el.text.strip()
        return out


__all__ = ["XlsxAdapter", "split_ref", "column_index"]
