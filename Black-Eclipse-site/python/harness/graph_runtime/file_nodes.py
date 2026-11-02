"""File nodes: upload a local file, parse it, and export a result.

These are thin adapters over the bounded graph asset store (`assets.py`). They
never reach the network and never invent data:

* `data.file.attach` turns an uploaded asset into `file`/`text`/`rows`.
* `data.file.parse` parses a file reference produced by another node.
* `data.file.export` writes rows into a downloadable local asset (CSV/JSON/XLSX).

Bytes live in the asset store, never in the Workflow IR. A missing or expired
reference fails by name.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Optional

from .assets import AssetError, require_asset_store
from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

#: Hard ceilings. A workflow must opt into more rows explicitly.
MAX_ROWS = 20_000
MAX_CELLS = 200_000
PARSE_KINDS = ("auto", "text", "json", "csv", "tsv", "xlsx", "binary")
EXPORT_FORMATS = ("csv", "json", "xlsx")

_TEXT_EXTENSIONS = {".txt", ".md", ".log", ".yaml", ".yml", ".xml", ".html", ".htm"}
_JSON_EXTENSIONS = {".json", ".ndjson", ".jsonl"}
_CSV_EXTENSIONS = {".csv"}
_TSV_EXTENSIONS = {".tsv", ".tab"}
_XLSX_EXTENSIONS = {".xlsx", ".xlsm"}
_IMAGE_MIME_PREFIX = "image/"


def _file_ref(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("assetId", "ref", "asset_id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _config_ref(context: NodeExecContext) -> str:
    value = context.config.get("assetId")
    return value.strip() if isinstance(value, str) else ""


def _resolve_ref(context: NodeExecContext) -> str:
    ref = _file_ref(context.inputs.get("file")) or _config_ref(context)
    if not ref:
        raise ValueError(
            "no file is attached: upload one in the inspector or wire a File input"
        )
    if ref.startswith("gas:"):
        return ref[4:]
    return ref


def _load(context: NodeExecContext) -> tuple[bytes, dict[str, Any]]:
    store = require_asset_store()
    ref = _resolve_ref(context)
    try:
        data = store.open_bytes(ref, owner=context.user_id)
        meta = store.get(ref, owner=context.user_id)
    except AssetError as exc:
        raise ValueError(str(exc)) from exc
    return data, meta


def _max_rows(context: NodeExecContext) -> int:
    try:
        value = int(context.config.get("maxRows", 5_000))
    except (TypeError, ValueError) as exc:
        raise ValueError("Max rows must be a whole number") from exc
    return max(1, min(value, MAX_ROWS))


def _kind_for(name: str, mime: str, requested: str) -> str:
    kind = (requested or "auto").strip().lower()
    if kind != "auto":
        if kind not in PARSE_KINDS:
            raise ValueError(f"unknown parse format {kind!r}")
        return kind
    lowered = (name or "").lower()
    for ext in _JSON_EXTENSIONS:
        if lowered.endswith(ext):
            return "json"
    for ext in _CSV_EXTENSIONS:
        if lowered.endswith(ext):
            return "csv"
    for ext in _TSV_EXTENSIONS:
        if lowered.endswith(ext):
            return "tsv"
    for ext in _XLSX_EXTENSIONS:
        if lowered.endswith(ext):
            return "xlsx"
    for ext in _TEXT_EXTENSIONS:
        if lowered.endswith(ext):
            return "text"
    if mime == "application/json" or mime.endswith("+json"):
        return "json"
    if mime in ("text/csv", "application/csv"):
        return "csv"
    if mime.startswith("text/"):
        return "text"
    return "binary"


def _decode(data: bytes, encoding: str) -> str:
    try:
        return data.decode(encoding or "utf-8-sig")
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"file is not valid {encoding or 'utf-8'} text: {exc}. "
            "Set Encoding to the file's real encoding."
        ) from exc


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _csv_rows(text: str, *, delimiter: str, header: bool, limit: int) -> tuple[list[Any], list[str], bool]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter or ",")
    rows: list[Any] = []
    columns: list[str] = []
    truncated = False
    try:
        first = next(reader)
    except StopIteration:
        return [], [], False
    if header:
        columns = [str(cell).strip() or f"column_{idx + 1}" for idx, cell in enumerate(first)]
        for record in reader:
            if len(rows) >= limit:
                truncated = True
                break
            row = {
                columns[idx] if idx < len(columns) else f"column_{idx + 1}": value
                for idx, value in enumerate(record)
            }
            rows.append(row)
    else:
        columns = [f"column_{idx + 1}" for idx in range(len(first))]
        rows.append(dict(zip(columns, first)))
        for record in reader:
            if len(rows) >= limit:
                truncated = True
                break
            rows.append(dict(zip(columns, record)))
    return rows, columns, truncated


def _json_rows(text: str, *, limit: int) -> tuple[Any, list[Any], list[str], bool]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc
    if isinstance(value, list):
        rows = value[:limit]
        truncated = len(value) > len(rows)
        if rows and all(isinstance(item, dict) for item in rows):
            columns = list(dict.fromkeys(key for item in rows for key in item.keys()))
        else:
            columns = []
        return value, rows, columns, truncated
    return value, [value], list(value.keys()) if isinstance(value, dict) else [], False


def _xlsx_rows(data: bytes, *, sheet: str, header: bool, limit: int) -> tuple[list[Any], list[str], bool]:
    try:
        from openpyxl import load_workbook  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - installed in the agent runtime
        raise ValueError("Excel parsing is unavailable: openpyxl is not installed") from exc
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - the library reason is the honest one
        raise ValueError(f"file is not a readable Excel workbook: {exc}") from exc
    try:
        worksheet = workbook[sheet] if sheet and sheet in workbook.sheetnames else workbook[workbook.sheetnames[0]]
        iterator = worksheet.iter_rows(values_only=True)
        rows: list[Any] = []
        columns: list[str] = []
        truncated = False
        first = next(iterator, None)
        if first is None:
            return [], [], False
        if header:
            columns = [
                str(cell).strip() if cell is not None and str(cell).strip() else f"column_{idx + 1}"
                for idx, cell in enumerate(first)
            ]
            for record in iterator:
                if len(rows) >= limit:
                    truncated = True
                    break
                rows.append({
                    columns[idx] if idx < len(columns) else f"column_{idx + 1}": value
                    for idx, value in enumerate(record)
                })
        else:
            columns = [f"column_{idx + 1}" for idx in range(len(first))]
            rows.append(dict(zip(columns, first)))
            for record in iterator:
                if len(rows) >= limit:
                    truncated = True
                    break
                rows.append(dict(zip(columns, record)))
        return rows, columns, truncated
    finally:
        workbook.close()


def _parse(
    context: NodeExecContext,
    data: bytes,
    meta: dict[str, Any],
) -> dict[str, Any]:
    requested = str(context.config.get("parseAs") or "auto")
    kind = _kind_for(str(meta.get("name") or ""), str(meta.get("mime") or ""), requested)
    limit = _max_rows(context)
    encoding = str(context.config.get("encoding") or "utf-8-sig")
    header = bool(context.config.get("header", True))

    text: Optional[str] = None
    rows: Optional[list[Any]] = None
    columns: list[str] = []
    truncated = False
    value: Any = None

    if kind == "binary":
        pass
    elif kind == "json":
        text = _decode(data, encoding)
        value, rows, columns, truncated = _json_rows(text, limit=limit)
    elif kind in ("csv", "tsv"):
        text = _decode(data, encoding)
        default_delimiter = "\t" if kind == "tsv" else ","
        delimiter = str(context.config.get("delimiter") or default_delimiter)
        rows, columns, truncated = _csv_rows(
            text, delimiter=delimiter, header=header, limit=limit,
        )
    elif kind == "xlsx":
        rows, columns, truncated = _xlsx_rows(
            data,
            sheet=str(context.config.get("sheet") or ""),
            header=header,
            limit=limit,
        )
    else:  # text
        text = _decode(data, encoding)

    if rows is not None:
        cells = sum(len(row) if isinstance(row, (dict, list)) else 0 for row in rows)
        if cells > MAX_CELLS:
            raise ValueError(
                f"file has {cells} cells; the limit is {MAX_CELLS}. Raise maxRows only if you mean it."
            )
    return {
        "kind": kind,
        "text": text,
        "rows": rows,
        "columns": columns,
        "truncated": truncated,
        "value": value,
    }


def _file_object(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "assetId": meta["assetId"],
        "ref": meta["ref"],
        "name": meta["name"],
        "mime": meta["mime"],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "createdAt": meta["createdAt"],
    }


def exec_file_attach(context: NodeExecContext) -> dict[str, Any]:
    data, meta = _load(context)
    parsed = _parse(context, data, meta)
    context.emit(
        f"file {meta['name']} · {meta['bytes']} bytes · {parsed['kind']}"
        + (f" · {len(parsed['rows'])} row(s)" if parsed["rows"] is not None else "")
        + (" · truncated" if parsed["truncated"] else "")
    )
    return {
        "file": _file_object(meta),
        "text": parsed["text"],
        "rows": parsed["rows"],
        "meta": {
            **_file_object(meta),
            "parseAs": parsed["kind"],
            "columns": parsed["columns"],
            "truncated": parsed["truncated"],
        },
    }


def exec_file_parse(context: NodeExecContext) -> dict[str, Any]:
    data, meta = _load(context)
    parsed = _parse(context, data, meta)
    context.emit(
        f"parsed {meta['name']} as {parsed['kind']}"
        + (f" · {len(parsed['rows'])} row(s)" if parsed["rows"] is not None else "")
    )
    return {
        "rows": parsed["rows"],
        "columns": parsed["columns"],
        "text": parsed["text"],
        "meta": {
            "name": meta["name"],
            "mime": meta["mime"],
            "bytes": meta["bytes"],
            "parseAs": parsed["kind"],
            "truncated": parsed["truncated"],
        },
    }


def _export_rows(context: NodeExecContext) -> tuple[list[Any], list[str]]:
    raw = context.inputs.get("rows")
    if raw is None:
        text = str(context.config.get("rowsJson") or "").strip()
        if text:
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"rowsJson is not valid JSON: {exc}") from exc
    if raw is None:
        raise ValueError("no rows to export: wire Rows or fill Rows (JSON)")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("rows must be an array of objects or arrays")
    limit = _max_rows(context)
    rows = raw[:limit]
    if rows and all(isinstance(row, dict) for row in rows):
        columns = list(dict.fromkeys(key for row in rows for key in row.keys()))
    elif rows and all(isinstance(row, (list, tuple)) for row in rows):
        width = max(len(row) for row in rows)
        columns = [f"column_{idx + 1}" for idx in range(width)]
    else:
        raise ValueError("rows must be all objects or all arrays")
    return rows, columns


def _write_csv(rows: list[Any], columns: list[str], *, include_header: bool) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if include_header:
        writer.writerow(columns)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([_stringify(row.get(column)) for column in columns])
        else:
            writer.writerow([_stringify(value) for value in row])
    return buffer.getvalue().encode("utf-8")


def _write_xlsx(rows: list[Any], columns: list[str], *, include_header: bool) -> bytes:
    try:
        from openpyxl import Workbook  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - installed in the agent runtime
        raise ValueError("Excel export is unavailable: openpyxl is not installed") from exc
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet("Data")
    if include_header:
        worksheet.append(columns)
    for row in rows:
        if isinstance(row, dict):
            worksheet.append([row.get(column) for column in columns])
        else:
            worksheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def exec_file_export(context: NodeExecContext) -> dict[str, Any]:
    rows, columns = _export_rows(context)
    fmt = str(context.config.get("format") or "csv").strip().lower()
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"unknown export format {fmt!r}")
    include_header = bool(context.config.get("includeHeader", True))
    name = str(context.config.get("name") or "").strip()
    if not name:
        name = f"export.{fmt}"
    elif not name.lower().endswith(f".{fmt}"):
        name = f"{name}.{fmt}"

    if fmt == "csv":
        data = _write_csv(rows, columns, include_header=include_header)
        mime = "text/csv"
    elif fmt == "xlsx":
        data = _write_xlsx(rows, columns, include_header=include_header)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
        mime = "application/json"

    store = require_asset_store()
    try:
        meta = store.save(name, data, mime=mime, owner=context.user_id)
    except AssetError as exc:
        raise ValueError(str(exc)) from exc
    context.emit(f"exported {len(rows)} row(s) to {meta['name']} ({meta['bytes']} bytes)")
    return {
        "artifact": {
            "assetId": meta["assetId"],
            "ref": meta["ref"],
            "name": meta["name"],
            "mime": meta["mime"],
            "bytes": meta["bytes"],
            "sha256": meta["sha256"],
        },
        "name": meta["name"],
        "bytes": meta["bytes"],
    }


def build_file_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="data.file.attach",
            version="1.0.0",
            label="File",
            category="data",
            inputs=(),
            outputs=(
                PortDef(id="file", name="File", type=PortType.FILE),
                PortDef(id="text", name="Text", type=PortType.STRING, nullable=True),
                PortDef(id="rows", name="Rows", type=PortType.ARRAY, nullable=True),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("parseAs", "enum", "auto", enum=PARSE_KINDS),
                ConfigField("delimiter", "string", ",", max_length=4),
                ConfigField("header", "boolean", True),
                ConfigField("maxRows", "integer", 5_000, minimum=1, maximum=MAX_ROWS),
                ConfigField("encoding", "string", "utf-8-sig", max_length=40),
            ),
            capabilities=("asset.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_file_attach,
            metadata={
                "docs": (
                    "An uploaded local file becomes a graph input. Bytes live in the "
                    "bounded graph asset store; config carries only the ref and metadata. "
                    "CSV/TSV/JSON/XLSX are parsed into rows; text is returned as-is; a "
                    "missing or expired file fails by name."
                ),
            },
        ),
        NodeDef(
            type="data.file.parse",
            version="1.0.0",
            label="Parse file",
            category="data",
            inputs=(PortDef(id="file", name="File", type=PortType.FILE, optional=True),),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY, nullable=True),
                PortDef(id="columns", name="Columns", type=PortType.ARRAY),
                PortDef(id="text", name="Text", type=PortType.STRING, nullable=True),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("parseAs", "enum", "auto", enum=PARSE_KINDS),
                ConfigField("delimiter", "string", ",", max_length=4),
                ConfigField("header", "boolean", True),
                ConfigField("maxRows", "integer", 5_000, minimum=1, maximum=MAX_ROWS),
                ConfigField("encoding", "string", "utf-8-sig", max_length=40),
                ConfigField("sheet", "string", "", max_length=120),
            ),
            capabilities=("asset.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_file_parse,
            metadata={
                "docs": (
                    "Parses a File reference produced by another node (or a pinned "
                    "asset). Same parser as data.file.attach: CSV/TSV/JSON/XLSX to "
                    "rows, text as-is, binary metadata only. Rows and the cell count "
                    "are capped; truncation is reported."
                ),
            },
        ),
        NodeDef(
            type="data.file.export",
            version="1.0.0",
            label="Export file",
            category="data",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="rows", name="Rows", type=PortType.ANY, optional=True),
            ),
            outputs=(
                PortDef(id="artifact", name="Artifact", type=PortType.OBJECT),
                PortDef(id="name", name="Name", type=PortType.STRING),
                PortDef(id="bytes", name="Bytes", type=PortType.NUMBER),
            ),
            config_fields=(
                ConfigField("format", "enum", "csv", enum=EXPORT_FORMATS),
                ConfigField("name", "string", "export", max_length=200),
                ConfigField("includeHeader", "boolean", True),
                ConfigField("rowsJson", "string", "", max_length=1_000_000),
                ConfigField("maxRows", "integer", 5_000, minimum=1, maximum=MAX_ROWS),
            ),
            capabilities=("asset.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_file_export,
            metadata={
                "docs": (
                    "Exports rows to a downloadable local asset (CSV/JSON/XLSX). "
                    "This is a local_write: a test run may perform it. It is distinct "
                    "from file.write, which writes into an operator-granted scope."
                ),
            },
        ),
    ]


__all__ = [
    "EXPORT_FORMATS",
    "MAX_ROWS",
    "PARSE_KINDS",
    "build_file_nodes",
    "exec_file_attach",
    "exec_file_export",
    "exec_file_parse",
]
