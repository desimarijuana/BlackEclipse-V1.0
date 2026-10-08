"""CSV / TSV adapter — tabular data with schema inference and type detection.

Large tabular files are handled as DATA, not prose: the parser streams rows with
the stdlib `csv` reader (bounded by `max_csv_rows`), infers a column schema and
types, profiles nulls/uniques, and builds a bounded preview. The full dataset is
queried through the query engine (DuckDB when present) rather than loaded into
model context (spec §13).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import DocumentIR, Provenance, Sheet, Table, TableCell
from .docx import _sha

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")


def sniff_delimiter(sample: str, default: str = ",") -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:  # noqa: BLE001
        return default


def detect_value(raw: str) -> tuple[Any, str]:
    text = raw.strip()
    if text == "":
        return None, "empty"
    if _INT_RE.match(text):
        try:
            return int(text), "integer"
        except ValueError:
            return text, "string"
    if _FLOAT_RE.match(text):
        try:
            return float(text), "number"
        except ValueError:
            return text, "string"
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true", "boolean"
    if _DATE_RE.match(text):
        return text, "date"
    return text, "string"


class TabularAdapter:
    name = "tabular"
    kinds = ("csv", "tsv")

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=True, tables=True, sheets=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        text = _decode(data)
        if not text.strip():
            raise DocumentError(DocumentErrorClass.INVALID_INPUT, "the file has no rows", source_ref=name)
        delimiter = "\t" if kind == "tsv" else sniff_delimiter(text[:8192])
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        cap = ctx.cfg.max_csv_rows
        header: list[str] = []
        rows: list[list[str]] = []
        truncated = False
        for i, row in enumerate(reader):
            if i == 0:
                header = [c.strip() for c in row]
                continue
            if i > cap:
                truncated = True
                break
            rows.append(row)

        ncols = max([len(header)] + [len(r) for r in rows[:1000]] or [0])
        header = header + [f"col_{j + 1}" for j in range(len(header), ncols)]
        columns = _profile_columns(rows, ncols)

        sheet = Sheet(index=0, name=(name.rsplit(".", 1)[0] or "data"), rows=len(rows), columns=ncols,
                      text_method="native")
        sheet.tables.append(Table(
            table_id="table_0", rows=rows, headers=header,
            provenance=Provenance(method="native", status="extracted", confidence=0.95, engine="csv"),
        ))
        sheet.preview, sheet.preview_rows, sheet.preview_columns = _preview(
            rows, header, ctx.cfg.preview_rows, ctx.cfg.preview_columns,
        )
        if truncated:
            sheet.warnings.append(f"the file was truncated at {cap} rows")
        sheet.named_ranges = [{"name": c, "type": columns[i]["type"]} for i, c in enumerate(header)]

        ir = DocumentIR(kind=kind, mime_type="text/csv" if kind == "csv" else "text/tab-separated-values",
                        file_name=name, byte_size=len(data))
        ir.metadata["columns"] = columns
        ir.metadata["rowCount"] = len(rows)
        ir.metadata["columnCount"] = ncols
        ir.metadata["delimiter"] = delimiter
        ir.sheets.append(sheet)
        return finalize_ir(ir, parser=f"{kind}-stream", sha256=_sha(data), data=data)


def _profile_columns(rows: list[list[str]], ncols: int) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    sample = rows[:5000]
    for col in range(ncols):
        types: dict[str, int] = {}
        nulls = 0
        uniques: set[str] = set()
        for row in sample:
            value, typ = detect_value(row[col] if col < len(row) else "")
            types[typ] = types.get(typ, 0) + 1
            if typ == "empty":
                nulls += 1
            elif len(uniques) < 1000:
                uniques.add(str(value))
        dominant = max(types.items(), key=lambda kv: kv[1])[0] if types else "string"
        profiles.append({
            "type": dominant, "nulls": nulls, "sampleSize": len(sample),
            "approxUniques": len(uniques), "typeCounts": types,
        })
    return profiles


def _preview(rows: list[list[str]], header: list[str], preview_rows: int, preview_cols: int) -> tuple[list[list[Any]], int, int]:
    out = [header[:preview_cols]]
    for row in rows[:preview_rows]:
        out.append([(row[i] if i < len(row) else None) for i in range(preview_cols)])
    return out, len(out), min(len(header), preview_cols)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


__all__ = ["TabularAdapter", "sniff_delimiter", "detect_value"]
