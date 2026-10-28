"""SpreadsheetML edits that preserve charts, pivots, media and styles."""

from __future__ import annotations

import copy
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .package import OoxmlPackage
from .plan import EditError
from .xmlutil import attr, direct_children, find_local, iter_local, local, parse, q, serialize

X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

_BUILTIN_FORMATS = {
    "General": 0, "0": 1, "0.00": 2, "#,##0": 3, "#,##0.00": 4,
    "0%": 9, "0.00%": 10, "0.00E+00": 11, "@": 49,
}

_REL_RE = re.compile(r"^(?P<col>[A-Z]+)(?P<row>\d+)$")
_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_$])"
    r"(?P<sheet>(?:'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!)?"
    r"(?P<c1>\$?[A-Z]{1,3})(?P<r1>\$?\d+)"
    r"(?::(?P<c2>\$?[A-Z]{1,3})(?P<r2>\$?\d+))?"
    r"(?![A-Za-z0-9_])"
)


def _sheet_ref_pattern(name: str) -> re.Pattern[str]:
    escaped = re.escape(name)
    return re.compile(rf"(?:'{escaped}'|{escaped})!", re.IGNORECASE)


def _relationships(package: OoxmlPackage, part: str) -> dict[str, str]:
    directory, _, base = part.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    raw = package.read(rels_name)
    if raw is None:
        return {}
    root = parse(raw)
    out: dict[str, str] = {}
    for relation in iter_local(root, "Relationship"):
        rid = attr(relation, "Id")
        target = attr(relation, "Target")
        if rid and target:
            out[rid] = target
    return out


def _resolve_target(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    directory = base_part.rpartition("/")[0]
    stack = directory.split("/") if directory else []
    for piece in target.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if stack:
                stack.pop()
        else:
            stack.append(piece)
    return "/".join(stack)


def _sheet_entries(package: OoxmlPackage) -> list[tuple[str, str]]:
    root = parse(package.require("xl/workbook.xml"))
    relations = _relationships(package, "xl/workbook.xml")
    sheets: list[tuple[str, str]] = []
    sheets_element = find_local(root, "sheets")
    if sheets_element is None:
        return sheets
    for sheet in direct_children(sheets_element, "sheet"):
        name = attr(sheet, "name")
        rid = ""
        for key, value in sheet.attrib.items():
            if local(key) == "id" and "}" in key:
                rid = value
                break
        target = relations.get(rid)
        if name and target:
            sheets.append((name, _resolve_target("xl/workbook.xml", target)))
    return sheets


def _sheet_part(package: OoxmlPackage, name: str) -> str:
    for sheet_name, part in _sheet_entries(package):
        if sheet_name == name:
            return part
    raise EditError("EDIT_SHEET_NOT_FOUND", f"the workbook has no sheet named {name!r}")


def _col_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - 64)
    return index


def _col_letters(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _split_ref(ref: str) -> tuple[int, int]:
    match = _REL_RE.match((ref or "").strip().upper())
    if not match:
        raise EditError("EDIT_CELL_INVALID", f"invalid cell reference {ref!r}")
    return _col_index(match.group("col")), int(match.group("row"))


def _row_of(root: ET.Element, row_number: int) -> ET.Element:
    data = find_local(root, "sheetData")
    if data is None:
        data = ET.SubElement(root, q(X, "sheetData"))
    rows = direct_children(data, "row")
    for row in rows:
        if attr(row, "r") == str(row_number):
            return row
    row = ET.Element(q(X, "row"), {"r": str(row_number)})
    for index, existing in enumerate(rows):
        try:
            if int(attr(existing, "r") or 0) > row_number:
                data.insert(index, row)
                return row
        except ValueError:
            continue
    data.append(row)
    return row


def _cell_of(row: ET.Element, column: int, row_number: int) -> ET.Element:
    cells = direct_children(row, "c")
    ref = f"{_col_letters(column)}{row_number}"
    for cell in cells:
        if attr(cell, "r") == ref:
            return cell
    cell = ET.Element(q(X, "c"), {"r": ref})
    for index, existing in enumerate(cells):
        existing_ref = attr(existing, "r")
        match = _REL_RE.match(existing_ref or "")
        if match and _col_index(match.group("col")) > column:
            row.insert(index, cell)
            return cell
    row.append(cell)
    return cell


def _clear_children(cell: ET.Element) -> None:
    for child in list(cell):
        if local(child.tag) in ("v", "is", "f"):
            cell.remove(child)


def _set_inline_string(cell: ET.Element, value: str) -> None:
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, q(X, "is"))
    text = ET.SubElement(inline, q(X, "t"))
    text.text = value
    if value.startswith(" ") or value.endswith(" "):
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _write_value(cell: ET.Element, value: Any) -> None:
    _clear_children(cell)
    if value is None:
        if "t" in cell.attrib:
            del cell.attrib["t"]
        return
    if isinstance(value, bool):
        cell.set("t", "b")
        ET.SubElement(cell, q(X, "v")).text = "1" if value else "0"
        return
    if isinstance(value, (int, float)):
        if "t" in cell.attrib:
            del cell.attrib["t"]
        ET.SubElement(cell, q(X, "v")).text = repr(float(value)) if isinstance(value, float) else str(value)
        return
    _set_inline_string(cell, str(value))


def _write_formula(cell: ET.Element, formula: str) -> None:
    _clear_children(cell)
    if "t" in cell.attrib:
        del cell.attrib["t"]
    node = ET.SubElement(cell, q(X, "f"))
    node.text = formula[1:] if formula.startswith("=") else formula


def _num_fmt_id(styles: ET.Element, code: str) -> int:
    if code in _BUILTIN_FORMATS:
        return _BUILTIN_FORMATS[code]
    num_fmts = find_local(styles, "numFmts")
    if num_fmts is None:
        num_fmts = ET.Element(q(X, "numFmts"))
        styles.insert(0, num_fmts)
    highest = 163
    for entry in direct_children(num_fmts, "numFmt"):
        try:
            highest = max(highest, int(attr(entry, "numFmtId") or 0))
        except ValueError:
            continue
        if attr(entry, "formatCode") == code:
            return int(attr(entry, "numFmtId"))
    new_id = highest + 1
    ET.SubElement(num_fmts, q(X, "numFmt"), {
        "numFmtId": str(new_id),
        "formatCode": code,
    })
    num_fmts.set("count", str(len(direct_children(num_fmts, "numFmt"))))
    return new_id


def _apply_number_format(package: OoxmlPackage, cell: ET.Element, code: str) -> None:
    raw = package.read("xl/styles.xml")
    if raw is None:
        raise EditError("EDIT_PART_MISSING", "the workbook has no xl/styles.xml")
    styles = parse(raw)
    cell_xfs = find_local(styles, "cellXfs")
    if cell_xfs is None:
        raise EditError("EDIT_PART_MISSING", "the workbook stylesheet has no cellXfs")
    xfs = direct_children(cell_xfs, "xf")
    current = attr(cell, "s")
    try:
        base = copy.deepcopy(xfs[int(current)]) if current else copy.deepcopy(xfs[0])
    except (ValueError, IndexError):
        base = ET.Element(q(X, "xf"))
    base.set("numFmtId", str(_num_fmt_id(styles, code)))
    base.set("applyNumberFormat", "1")
    base.tail = None
    cell_xfs.append(base)
    cell_xfs.set("count", str(len(direct_children(cell_xfs, "xf"))))
    cell.set("s", str(len(direct_children(cell_xfs, "xf")) - 1))
    package.write("xl/styles.xml", serialize(styles))


def _update_dimension(root: ET.Element) -> None:
    data = find_local(root, "sheetData")
    if data is None:
        return
    max_row = 1
    max_col = 1
    for row in direct_children(data, "row"):
        try:
            row_number = int(attr(row, "r") or 0)
        except ValueError:
            continue
        max_row = max(max_row, row_number)
        for cell in direct_children(row, "c"):
            match = _REL_RE.match(attr(cell, "r") or "")
            if match:
                max_col = max(max_col, _col_index(match.group("col")))
    dimension = find_local(root, "dimension")
    if dimension is None:
        dimension = ET.Element(q(X, "dimension"))
        root.insert(0, dimension)
    dimension.set("ref", f"A1:{_col_letters(max_col)}{max_row}")


def _finish_calculation(package: OoxmlPackage) -> set[str]:
    touched: set[str] = set()
    root = parse(package.require("xl/workbook.xml"))
    calc = find_local(root, "calcPr")
    if calc is None:
        calc = ET.Element(q(X, "calcPr"))
        ext = find_local(root, "extLst")
        if ext is not None:
            root.insert(list(root).index(ext), calc)
        else:
            root.append(calc)
    calc.set("fullCalcOnLoad", "1")
    calc.set("forceFullCalc", "1")
    package.write("xl/workbook.xml", serialize(root))
    touched.add("xl/workbook.xml")

    removed = package.remove("xl/calcChain.xml")
    if removed:
        raw = package.read("[Content_Types].xml")
        if raw is not None:
            types = parse(raw)
            for override in list(iter_local(types, "Override")):
                if attr(override, "PartName").casefold() == "/xl/calcchain.xml":
                    parent = _parent_of(types, override)
                    if parent is not None:
                        parent.remove(override)
            package.write("[Content_Types].xml", serialize(types))
            touched.add("[Content_Types].xml")
        rels_name = "xl/_rels/workbook.xml.rels"
        raw = package.read(rels_name)
        if raw is not None:
            rels = parse(raw)
            for relation in list(iter_local(rels, "Relationship")):
                if "calcchain.xml" in attr(relation, "Target").casefold():
                    parent = _parent_of(rels, relation)
                    if parent is not None:
                        parent.remove(relation)
            package.write(rels_name, serialize(rels))
            touched.add(rels_name)
    return touched


def _parent_of(root: ET.Element, target: ET.Element) -> Optional[ET.Element]:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def set_cell(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    root = parse(package.require(part))
    column, row_number = _split_ref(edit["ref"])
    cell = _cell_of(_row_of(root, row_number), column, row_number)
    _write_value(cell, edit.get("value"))
    touched = {part, *_finish_calculation(package)}
    if edit.get("numberFormat"):
        _apply_number_format(package, cell, edit["numberFormat"])
        touched.add("xl/styles.xml")
    _update_dimension(root)
    package.write(part, serialize(root))
    return touched


def set_formula(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    root = parse(package.require(part))
    column, row_number = _split_ref(edit["ref"])
    cell = _cell_of(_row_of(root, row_number), column, row_number)
    _write_formula(cell, edit["formula"])
    touched = {part, *_finish_calculation(package)}
    if edit.get("numberFormat"):
        _apply_number_format(package, cell, edit["numberFormat"])
        touched.add("xl/styles.xml")
    _update_dimension(root)
    package.write(part, serialize(root))
    return touched


def set_number_format(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    root = parse(package.require(part))
    column, row_number = _split_ref(edit["ref"])
    cell = _cell_of(_row_of(root, row_number), column, row_number)
    _apply_number_format(package, cell, edit["numberFormat"])
    package.write(part, serialize(root))
    return {part, "xl/styles.xml"}


def rename_sheet(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    old = edit["sheet"]
    new = edit["newName"].strip()
    if not new or len(new) > 31 or any(char in new for char in "[]:*?/\\"):
        raise EditError("EDIT_INVALID_PLAN", "the new sheet name is not a valid Excel sheet name")
    entries = _sheet_entries(package)
    if not any(name == old for name, _ in entries):
        raise EditError("EDIT_SHEET_NOT_FOUND", f"the workbook has no sheet named {old!r}")
    if any(name == new for name, _ in entries):
        raise EditError("EDIT_SHEET_EXISTS", f"a sheet named {new!r} already exists")
    pattern = _sheet_ref_pattern(old)
    for _name, part in entries:
        raw = package.read(part)
        if raw is None:
            continue
        for formula in iter_local(parse(raw), "f"):
            if formula.text and pattern.search(formula.text):
                raise EditError(
                    "EDIT_REFERENCES_EXIST",
                    f"cannot rename {old!r}: another sheet's formula references it",
                )
    root = parse(package.require("xl/workbook.xml"))
    for sheet in iter_local(root, "sheet"):
        if attr(sheet, "name") == old:
            sheet.set("name", new)
    for defined in iter_local(root, "definedName"):
        if defined.text and re.search(pattern, defined.text, re.IGNORECASE):
            defined.text = pattern.sub(f"'{new}'!", defined.text)
    package.write("xl/workbook.xml", serialize(root))
    return {"xl/workbook.xml"}


def append_rows(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    root = parse(package.require(part))
    data = find_local(root, "sheetData")
    if data is None:
        data = ET.SubElement(root, q(X, "sheetData"))
    rows = direct_children(data, "row")
    start = 1
    for row in rows:
        try:
            start = max(start, int(attr(row, "r") or 0) + 1)
        except ValueError:
            continue
    for offset, values in enumerate(edit["rows"]):
        if not isinstance(values, (list, tuple)):
            raise EditError("EDIT_INVALID_PLAN", "each appended row must be an array")
        row_number = start + offset
        row = ET.SubElement(data, q(X, "row"), {"r": str(row_number)})
        for column, value in enumerate(values, start=1):
            cell = ET.SubElement(row, q(X, "c"), {"r": f"{_col_letters(column)}{row_number}"})
            _write_value(cell, value)
    _update_dimension(root)
    package.write(part, serialize(root))
    touched = {part, *_finish_calculation(package)}
    return touched


def _structure_guard(package: OoxmlPackage, part: str, *, axis: str) -> None:
    # Pivot caches, OLE anchors and legacy VML anchors are handled by
    # `_rewrite_related_parts`; there is no blanket refusal here.
    return None


def _shift_cell_ref(cell: ET.Element, *, column: int, row_number: int) -> None:
    cell.set("r", f"{_col_letters(column)}{row_number}")


def _shift_number(text: str, *, at: int, count: int, delete: bool) -> str:
    absolute = text.startswith("$")
    raw = int(text.lstrip("$"))
    if delete:
        if raw >= at + count:
            raw -= count
        elif raw >= at:
            raw = at
    elif raw >= at:
        raw += count
    return ("$" if absolute else "") + str(max(1, raw))


def _shift_column(text: str, *, at: int, count: int, delete: bool) -> str:
    try:
        return _shift_number(text, at=at, count=count, delete=delete)
    except ValueError:
        return text


def _row_or_column(token: str, *, axis: str, at: int, count: int, delete: bool) -> str:
    if axis == "rows":
        return _shift_number(token, at=at, count=count, delete=delete)
    absolute = token.startswith("$")
    raw = _col_index(token.lstrip("$"))
    if delete:
        if raw >= at + count:
            raw -= count
        elif raw >= at:
            raw = at
    elif raw >= at:
        raw += count
    raw = max(1, raw)
    return ("$" if absolute else "") + _col_letters(raw)


def _shift_ref_match(match: re.Match[str], *, target_sheet: str, current_sheet: Optional[str], axis: str, at: int, count: int, delete: bool) -> str:
    sheet_group = match.group("sheet") or ""
    if sheet_group:
        sheet_name = sheet_group[:-1].strip("'")
        if sheet_name.casefold() != target_sheet.casefold():
            return match.group(0)
    elif not current_sheet or current_sheet.casefold() != target_sheet.casefold():
        return match.group(0)
    c1 = match.group("c1")
    r1 = match.group("r1")
    c2 = match.group("c2")
    r2 = match.group("r2")
    if axis == "rows":
        r1 = _row_or_column(r1, axis=axis, at=at, count=count, delete=delete)
        if r2:
            r2 = _row_or_column(r2, axis=axis, at=at, count=count, delete=delete)
    else:
        c1 = _row_or_column(c1, axis=axis, at=at, count=count, delete=delete)
        if c2:
            c2 = _row_or_column(c2, axis=axis, at=at, count=count, delete=delete)
    return f"{sheet_group}{c1}{r1}" + (f":{c2}{r2}" if c2 and r2 else "")


def _shift_formula_text(text: str, *, target_sheet: str, current_sheet: Optional[str], axis: str, at: int, count: int, delete: bool) -> str:
    if not text:
        return text
    parts = re.split(r'("(?:[^"]|"")*")', text)
    for index in range(0, len(parts), 2):
        parts[index] = _REF_RE.sub(
            lambda match: _shift_ref_match(
                match, target_sheet=target_sheet, current_sheet=current_sheet,
                axis=axis, at=at, count=count, delete=delete,
            ),
            parts[index],
        )
    return "".join(parts)


def _shift_ref_text(value: str, *, target_sheet: str, axis: str, at: int, count: int, delete: bool) -> str:
    pieces = []
    for piece in (value or "").split():
        pieces.append(_REF_RE.sub(
            lambda match: _shift_ref_match(
                match, target_sheet=target_sheet, current_sheet=target_sheet,
                axis=axis, at=at, count=count, delete=delete,
            ),
            piece,
        ))
    return " ".join(pieces)


def _shift_columns_element(root: ET.Element, *, at: int, count: int, delete: bool) -> None:
    cols = find_local(root, "cols")
    if cols is None:
        return
    for column in iter_local(cols, "col"):
        for key in ("min", "max"):
            value = attr(column, key)
            if value:
                try:
                    column.set(key, str(int(_shift_number(value, at=at, count=count, delete=delete).lstrip("$"))))
                except ValueError:
                    continue


def _rewrite_structural_refs(package: OoxmlPackage, *, target_sheet: str, target_part: str, axis: str, at: int, count: int, delete: bool) -> set[str]:
    touched: set[str] = set()
    for sheet_name, sheet_part in _sheet_entries(package):
        raw = package.read(sheet_part)
        if raw is None:
            continue
        root = parse(raw)
        changed = False
        for formula in list(iter_local(root, "f")) + list(iter_local(root, "formula")):
            if formula.text:
                new_text = _shift_formula_text(
                    formula.text, target_sheet=target_sheet, current_sheet=sheet_name,
                    axis=axis, at=at, count=count, delete=delete,
                )
                if new_text != formula.text:
                    formula.text = new_text
                    changed = True
        if sheet_part == target_part:
            for element in list(iter_local(root, "mergeCell")) + list(iter_local(root, "conditionalFormatting")) + list(iter_local(root, "dataValidation")) + list(iter_local(root, "hyperlink")) + list(iter_local(root, "autoFilter")):
                for key in ("ref", "sqref"):
                    value = attr(element, key)
                    if value:
                        new_value = _shift_ref_text(value, target_sheet=target_sheet, axis=axis, at=at, count=count, delete=delete)
                        if new_value != value:
                            element.set(key, new_value)
                            changed = True
            if axis == "columns":
                before = serialize(root)
                _shift_columns_element(root, at=at, count=count, delete=delete)
                if serialize(root) != before:
                    changed = True
        if changed:
            package.write(sheet_part, serialize(root))
            touched.add(sheet_part)
    workbook = parse(package.require("xl/workbook.xml"))
    changed = False
    for defined in iter_local(workbook, "definedName"):
        if defined.text:
            new_text = _shift_formula_text(
                defined.text, target_sheet=target_sheet, current_sheet=None,
                axis=axis, at=at, count=count, delete=delete,
            )
            if new_text != defined.text:
                defined.text = new_text
                changed = True
    if changed:
        package.write("xl/workbook.xml", serialize(workbook))
        touched.add("xl/workbook.xml")
    touched.update(_rewrite_related_parts(
        package, target_sheet=target_sheet, target_part=target_part,
        axis=axis, at=at, count=count, delete=delete,
    ))
    return touched


def _rels_entries(package: OoxmlPackage, part: str) -> list[dict[str, str]]:
    directory, _, base = part.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    raw = package.read(rels_name)
    if raw is None:
        return []
    root = parse(raw)
    return [
        {"id": attr(item, "Id"), "type": attr(item, "Type"), "target": attr(item, "Target")}
        for item in iter_local(root, "Relationship")
        if attr(item, "Id") and attr(item, "Target")
    ]


def _resolve_rel(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    directory = base_part.rpartition("/")[0]
    stack = directory.split("/") if directory else []
    for piece in target.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if stack:
                stack.pop()
        else:
            stack.append(piece)
    return "/".join(stack)


def _shift_anchor_text(value: str, *, axis: str, at: int, count: int, delete: bool) -> str:
    pieces = [piece.strip() for piece in value.split(",")]
    if len(pieces) != 8:
        return value
    for index in ((0, 4) if axis == "columns" else (2, 6)):
        try:
            pieces[index] = str(int(_shift_number(pieces[index], at=at, count=count, delete=delete).lstrip("$")))
        except (ValueError, IndexError):
            return value
    return ", ".join(pieces)


def _shift_drawing_anchors(package: OoxmlPackage, part: str, *, axis: str, at: int, count: int, delete: bool) -> bool:
    raw = package.read(part)
    if raw is None:
        return False
    root = parse(raw)
    changed = False
    for anchor in list(iter_local(root, "from")) + list(iter_local(root, "to")):
        node = find_local(anchor, "col" if axis == "columns" else "row")
        if node is not None and node.text:
            try:
                shifted = _shift_number(node.text.strip(), at=at, count=count, delete=delete).lstrip("$")
            except ValueError:
                continue
            if shifted != node.text:
                node.text = shifted
                changed = True
    for anchor in iter_local(root, "Anchor"):
        if anchor.text:
            shifted = _shift_anchor_text(anchor.text, axis=axis, at=at, count=count, delete=delete)
            if shifted != anchor.text:
                anchor.text = shifted
                changed = True
    if changed:
        package.write(part, serialize(root))
    return changed


def _rewrite_pivot(package: OoxmlPackage, pivot_part: str, *, target_sheet: str, axis: str, at: int, count: int, delete: bool) -> set[str]:
    touched: set[str] = set()
    root = parse(package.require(pivot_part))
    location = find_local(root, "location")
    if location is None or not attr(location, "ref"):
        raise EditError("EDIT_PIVOT_UNSAFE", "a pivot table has no location reference")
    location.set("ref", _shift_ref_text(
        attr(location, "ref"), target_sheet=target_sheet, axis=axis, at=at, count=count, delete=delete,
    ))
    package.write(pivot_part, serialize(root))
    touched.add(pivot_part)
    for entry in _rels_entries(package, pivot_part):
        if not entry["type"].casefold().endswith("/pivotcachedefinition"):
            continue
        cache_part = _resolve_rel(pivot_part, entry["target"])
        if not package.has(cache_part):
            raise EditError("EDIT_PIVOT_UNSAFE", "a pivot cache definition part is missing")
        cache = parse(package.require(cache_part))
        cache.set("refreshOnLoad", "1")
        source = find_local(cache, "cacheSource")
        worksheet = find_local(source, "worksheetSource") if source is not None else None
        if worksheet is not None and attr(worksheet, "ref"):
            sheet_name = attr(worksheet, "sheet")
            if not sheet_name or sheet_name.casefold() == target_sheet.casefold():
                worksheet.set("ref", _shift_ref_text(
                    attr(worksheet, "ref"), target_sheet=target_sheet,
                    axis=axis, at=at, count=count, delete=delete,
                ))
        package.write(cache_part, serialize(cache))
        touched.add(cache_part)
    return touched


def _shift_ole_and_legacy(package: OoxmlPackage, root: ET.Element, target_part: str, *, axis: str, at: int, count: int, delete: bool) -> set[str]:
    touched: set[str] = set()
    relations = {entry["id"]: entry for entry in _rels_entries(package, target_part)}
    for element_name in ("drawing", "legacyDrawing"):
        element = find_local(root, element_name)
        if element is None:
            continue
        relation = relations.get(attr(element, "id"))
        if relation is None:
            continue
        part = _resolve_rel(target_part, relation["target"])
        if package.has(part) and _shift_drawing_anchors(package, part, axis=axis, at=at, count=count, delete=delete):
            touched.add(part)
    return touched


def _rewrite_related_parts(package: OoxmlPackage, *, target_sheet: str, target_part: str, axis: str, at: int, count: int, delete: bool) -> set[str]:
    touched: set[str] = set()
    root = parse(package.require(target_part))
    relations = {entry["id"]: entry for entry in _rels_entries(package, target_part)}

    for table_part in iter_local(root, "tablePart"):
        relation = relations.get(attr(table_part, "id"))
        if relation is None:
            continue
        table_name = _resolve_rel(target_part, relation["target"])
        if not package.has(table_name):
            continue
        table = parse(package.require(table_name))
        changed = False
        for element in [table] + list(iter_local(table, "autoFilter")):
            value = attr(element, "ref")
            if value:
                new_value = _shift_ref_text(value, target_sheet=target_sheet, axis=axis, at=at, count=count, delete=delete)
                if new_value != value:
                    element.set("ref", new_value)
                    changed = True
        for formula in list(iter_local(table, "calculatedColumnFormula")) + list(iter_local(table, "totalsRowFormula")):
            if formula.text:
                new_text = _shift_formula_text(
                    formula.text, target_sheet=target_sheet, current_sheet=target_sheet,
                    axis=axis, at=at, count=count, delete=delete,
                )
                if new_text != formula.text:
                    formula.text = new_text
                    changed = True
        if changed:
            package.write(table_name, serialize(table))
            touched.add(table_name)

    for pivot_ref in iter_local(root, "pivotTablePart"):
        relation = relations.get(attr(pivot_ref, "id"))
        if relation is None:
            raise EditError("EDIT_PIVOT_UNSAFE", "a pivot table relationship is missing")
        pivot_part = _resolve_rel(target_part, relation["target"])
        if not package.has(pivot_part):
            raise EditError("EDIT_PIVOT_UNSAFE", "a pivot table part is missing")
        touched.update(_rewrite_pivot(
            package, pivot_part, target_sheet=target_sheet,
            axis=axis, at=at, count=count, delete=delete,
        ))

    drawing = find_local(root, "drawing")
    if drawing is not None:
        relation = relations.get(attr(drawing, "id"))
        if relation is not None:
            drawing_part = _resolve_rel(target_part, relation["target"])
            if package.has(drawing_part):
                for entry in _rels_entries(package, drawing_part):
                    if not entry["type"].casefold().endswith("/chart"):
                        continue
                    chart_part = _resolve_rel(drawing_part, entry["target"])
                    if not package.has(chart_part):
                        continue
                    chart = parse(package.require(chart_part))
                    changed = False
                    for formula in iter_local(chart, "f"):
                        if formula.text:
                            new_text = _shift_formula_text(
                                formula.text, target_sheet=target_sheet, current_sheet=target_sheet,
                                axis=axis, at=at, count=count, delete=delete,
                            )
                            if new_text != formula.text:
                                formula.text = new_text
                                changed = True
                    if changed:
                        package.write(chart_part, serialize(chart))
                        touched.add(chart_part)
    touched.update(_shift_ole_and_legacy(
        package, root, target_part, axis=axis, at=at, count=count, delete=delete,
    ))
    return touched


def insert_rows(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    _structure_guard(package, part, axis="rows")
    root = parse(package.require(part))
    data = find_local(root, "sheetData")
    if data is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the sheet has no cell data")
    at, count = edit["at"], edit["count"]
    for row in direct_children(data, "row"):
        try:
            row_number = int(attr(row, "r") or 0)
        except ValueError:
            continue
        if row_number >= at:
            new_row = row_number + count
            row.set("r", str(new_row))
            row.attrib.pop("spans", None)
            for cell in direct_children(row, "c"):
                match = _REL_RE.match(attr(cell, "r") or "")
                if match:
                    _shift_cell_ref(cell, column=_col_index(match.group("col")), row_number=new_row)
    _update_dimension(root)
    package.write(part, serialize(root))
    touched = {part}
    touched.update(_rewrite_structural_refs(
        package, target_sheet=edit["sheet"], target_part=part, axis="rows",
        at=at, count=count, delete=False,
    ))
    return touched


def delete_rows(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    _structure_guard(package, part, axis="rows")
    root = parse(package.require(part))
    data = find_local(root, "sheetData")
    if data is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the sheet has no cell data")
    at, count = edit["at"], edit["count"]
    affected = False
    for row in list(direct_children(data, "row")):
        try:
            row_number = int(attr(row, "r") or 0)
        except ValueError:
            continue
        if at <= row_number < at + count:
            data.remove(row)
            affected = True
            continue
        if row_number >= at + count:
            affected = True
            new_row = row_number - count
            row.set("r", str(new_row))
            row.attrib.pop("spans", None)
            for cell in direct_children(row, "c"):
                match = _REL_RE.match(attr(cell, "r") or "")
                if match:
                    _shift_cell_ref(cell, column=_col_index(match.group("col")), row_number=new_row)
    if not affected:
        raise EditError("EDIT_TARGET_NOT_FOUND", "no rows exist at or below the requested range")
    _update_dimension(root)
    package.write(part, serialize(root))
    touched = {part}
    touched.update(_rewrite_structural_refs(
        package, target_sheet=edit["sheet"], target_part=part, axis="rows",
        at=at, count=count, delete=True,
    ))
    return touched


def insert_columns(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    _structure_guard(package, part, axis="columns")
    root = parse(package.require(part))
    data = find_local(root, "sheetData")
    if data is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the sheet has no cell data")
    at, count = edit["at"], edit["count"]
    for row in direct_children(data, "row"):
        for cell in direct_children(row, "c"):
            match = _REL_RE.match(attr(cell, "r") or "")
            if not match:
                continue
            column = _col_index(match.group("col"))
            if column >= at:
                _shift_cell_ref(cell, column=column + count, row_number=int(match.group("row")))
    _update_dimension(root)
    package.write(part, serialize(root))
    touched = {part}
    touched.update(_rewrite_structural_refs(
        package, target_sheet=edit["sheet"], target_part=part, axis="columns",
        at=at, count=count, delete=False,
    ))
    return touched


def delete_columns(package: OoxmlPackage, edit: dict[str, Any]) -> set[str]:
    part = _sheet_part(package, edit["sheet"])
    _structure_guard(package, part, axis="columns")
    root = parse(package.require(part))
    data = find_local(root, "sheetData")
    if data is None:
        raise EditError("EDIT_TARGET_NOT_FOUND", "the sheet has no cell data")
    at, count = edit["at"], edit["count"]
    affected = False
    for row in direct_children(data, "row"):
        for cell in list(direct_children(row, "c")):
            match = _REL_RE.match(attr(cell, "r") or "")
            if not match:
                continue
            column = _col_index(match.group("col"))
            row_number = int(match.group("row"))
            if at <= column < at + count:
                row.remove(cell)
                affected = True
            elif column >= at + count:
                affected = True
                _shift_cell_ref(cell, column=column - count, row_number=row_number)
    if not affected:
        raise EditError("EDIT_TARGET_NOT_FOUND", "no cells exist at or right of the requested range")
    _update_dimension(root)
    package.write(part, serialize(root))
    touched = {part}
    touched.update(_rewrite_structural_refs(
        package, target_sheet=edit["sheet"], target_part=part, axis="columns",
        at=at, count=count, delete=True,
    ))
    return touched


__all__ = [
    "append_rows",
    "delete_columns",
    "delete_rows",
    "insert_columns",
    "insert_rows",
    "rename_sheet",
    "set_cell",
    "set_formula",
    "set_number_format",
]
