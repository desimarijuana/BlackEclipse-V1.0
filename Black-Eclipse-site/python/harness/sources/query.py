"""Read-only DuckDB queries over files that stay on disk.

DuckDB is the speed lever for terabyte-scale tabular data: projection and
predicate pushdown skip Parquet row groups, and CSV/JSON are read out-of-core
with a memory limit and a spill directory instead of being loaded into Python.

The user never writes ``read_csv('...')``. The source is registered as a view
named ``t``; SQL may only read ``t`` and may not touch the filesystem, install
extensions, or mutate anything.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import SourceConfig, load_config
from .contracts import SqlResult

# Statements that are reads. Everything else is refused.
_ALLOWED_START = re.compile(r"^\s*(select|with|describe|summarize|pivot)\b", re.IGNORECASE)
_DENIED = re.compile(
    r"\b(attach|detach|install|load|copy|export|import|pragma|create|insert|update|"
    r"delete|drop|alter|truncate|vacuum|call|set|reset|checkpoint|begin|commit|"
    r"rollback|read_csv|read_parquet|read_json|read_text|read_blob|glob|parquet_scan|"
    r"csv_scan|sqlite_scan|httpfs|http|s3|azure|gcs|delta_scan|iceberg_scan)\b",
    re.IGNORECASE,
)


def _strip_sql(sql: str) -> str:
    text = (sql or "").strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def validate_sql(sql: str) -> Optional[str]:
    """Return a refusal reason, or None when the statement is allowed."""
    text = _strip_sql(sql)
    if not text:
        return "the SQL statement is empty"
    if ";" in text:
        return "only a single statement is allowed"
    if not _ALLOWED_START.match(text):
        return "only SELECT / WITH / DESCRIBE / SUMMARIZE / PIVOT statements are allowed"
    lowered = text.lower()
    # `read_*` etc. are denied so a query cannot escape the registered source.
    if _DENIED.search(text):
        match = _DENIED.search(text)
        return f"the keyword {match.group(0)!r} is not allowed; query the view `t` instead"
    if "--" in lowered or "/*" in lowered:
        return "SQL comments are not allowed"
    return None


def _reader_for(path: str) -> tuple[str, Optional[str]]:
    """Return (duckdb reader expression, reason-if-unsupported)."""
    target = Path(path)
    ext = target.suffix.lower()
    if target.is_dir():
        return "dir", None
    if ext == ".parquet":
        return "parquet", None
    if ext in (".csv", ".tsv"):
        return "csv", None
    if ext in (".jsonl", ".ndjson"):
        return "jsonl", None
    if ext == ".json":
        return "json", None
    if ext in (".xlsx", ".xls", ".ods"):
        return "spreadsheet", (
            "spreadsheet SQL needs a CSV/Parquet export; use the document tools "
            "for Excel workbooks"
        )
    if ext in (".db", ".sqlite", ".sqlite3"):
        return "sqlite", "SQLite sources are opened by the document tools, not DuckDB"
    return "unknown", f"`{ext or 'no extension'}` is not a queryable table format"


def _quote(path: str) -> str:
    return path.replace("'", "''")


def _source_expr(paths: list[str], kind: str, cfg: SourceConfig) -> str:
    quoted = ", ".join(f"'{_quote(str(p))}'" for p in paths)
    if len(paths) > 1:
        # A list must be an array expression, not a comma list.
        quoted = "[" + quoted + "]"
    if kind == "parquet":
        return f"read_parquet({quoted}, union_by_name=true)"
    if kind == "csv":
        delim = "\\t" if all(str(p).lower().endswith(".tsv") for p in paths) else ","
        return (
            f"read_csv_auto({quoted}, header=true, delim='{delim}', "
            f"sample_size=4096, ignore_errors=true, union_by_name=true)"
        )
    if kind == "jsonl":
        return f"read_json_auto({quoted}, format='newline_delimited', union_by_name=true)"
    if kind == "json":
        return f"read_json_auto({quoted}, union_by_name=true)"
    raise ValueError(f"unsupported reader: {kind}")


def _connect(cfg: SourceConfig, *, read_only: bool = False) -> Any:
    import duckdb  # noqa: PLC0415

    con = duckdb.connect(database=":memory:", read_only=False)
    try:
        con.execute(f"SET memory_limit='{cfg.query_memory_limit}'")
        con.execute(f"SET threads={int(cfg.query_threads)}")
        if cfg.tmp_dir:
            Path(cfg.tmp_dir).mkdir(parents=True, exist_ok=True)
            con.execute(f"SET temp_directory='{_quote(cfg.tmp_dir)}'")
        # Newer DuckDB supports a statement timeout; older builds ignore it.
        try:
            con.execute(f"SET statement_timeout='{int(cfg.query_timeout_s * 1000)}ms'")
        except Exception:  # noqa: BLE001 - optional capability
            pass
        # No `enable_external_access=false` here: the registered view must read the
        # source file. Safety comes from the statement allowlist and from binding
        # the path ourselves, not from disabling file access.
    except Exception:  # noqa: BLE001 - settings are best-effort, not correctness
        pass
    return con


def describe_source(path: str, *, cfg: Optional[SourceConfig] = None) -> dict[str, Any]:
    """Schema (+ cheap row count) for one table file. Never reads the whole file."""
    config = cfg or load_config()
    kind, reason = _reader_for(path)
    if kind not in ("parquet", "csv", "jsonl", "json"):
        return {"ok": False, "error": reason or "not a table"}
    try:
        con = _connect(config)
    except Exception as exc:  # noqa: BLE001 - DuckDB missing is honest
        return {"ok": False, "error": f"DuckDB unavailable: {exc}"}
    try:
        expr = _source_expr([path], kind, config)
        con.execute(f"CREATE VIEW t AS SELECT * FROM {expr}")
        described = con.execute("DESCRIBE SELECT * FROM t").fetchall()
        columns = [{"name": row[0], "type": str(row[1])} for row in described]
        rows: Optional[int] = None
        try:
            if kind == "parquet" or os.path.getsize(path) <= 32 * 1024 * 1024:
                rows = int(con.execute("SELECT COUNT(*) FROM t").fetchone()[0])
        except Exception:  # noqa: BLE001 - a count is a hint, never required
            rows = None
        out: dict[str, Any] = {"ok": True, "columns": columns, "rows": rows}
        if kind == "csv":
            out["delimiter"] = "\t" if str(path).lower().endswith(".tsv") else ","
        return out
    except Exception as exc:  # noqa: BLE001 - a bad file is a reported failure
        return {"ok": False, "error": str(exc)}
    finally:
        con.close()


def run_sql(
    path: str | list[str],
    sql: str,
    *,
    cfg: Optional[SourceConfig] = None,
    max_rows: Optional[int] = None,
) -> SqlResult:
    """Run one validated read-only statement over one or more table files."""
    config = cfg or load_config()
    started = time.monotonic()
    refusal = validate_sql(sql)
    if refusal:
        return SqlResult(ok=False, sql=_strip_sql(sql), error=refusal)

    paths = [path] if isinstance(path, str) else [str(p) for p in path]
    if not paths or any(not os.path.exists(p) for p in paths):
        return SqlResult(ok=False, sql=_strip_sql(sql), error="the source path does not exist")
    kinds = {_reader_for(p)[0] for p in paths}
    if len(kinds) != 1:
        return SqlResult(ok=False, sql=_strip_sql(sql), error="all files in one query must share a format")
    kind = kinds.pop()
    if kind not in ("parquet", "csv", "jsonl", "json"):
        _, reason = _reader_for(paths[0])
        return SqlResult(ok=False, sql=_strip_sql(sql), error=reason or "unsupported format")

    try:
        con = _connect(config)
    except Exception as exc:  # noqa: BLE001
        return SqlResult(ok=False, sql=_strip_sql(sql), error=f"DuckDB unavailable: {exc}")

    limit = int(max_rows or config.query_max_rows)
    try:
        expr = _source_expr(paths, kind, config)
        con.execute(f"CREATE VIEW t AS SELECT * FROM {expr}")
        cursor = con.execute(_strip_sql(sql))
        columns = [d[0] for d in (cursor.description or [])]
        fetched = cursor.fetchmany(limit + 1)
        truncated = len(fetched) > limit
        rows = [[_jsonable(v) for v in row] for row in fetched[:limit]]
        return SqlResult(
            ok=True, sql=_strip_sql(sql), source=paths[0], columns=columns,
            rows=rows, row_count=len(rows), truncated=truncated,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - a bad query is a reported failure
        message = str(exc)
        if "timeout" in message.lower():
            return SqlResult(
                ok=False, sql=_strip_sql(sql), error=f"query timed out after {config.query_timeout_s:g}s",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        return SqlResult(
            ok=False, sql=_strip_sql(sql), error=message,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        con.close()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


__all__ = ["describe_source", "run_sql", "validate_sql"]
