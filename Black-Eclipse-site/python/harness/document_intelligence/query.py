"""Deterministic tabular query engine (spec §12/§13/§58).

Spreadsheets and CSVs are queried as data, never dumped into the LLM context.
Rows are materialized to a temporary CSV *outside* the workspace (read-only, no
network) and queried with SQL through DuckDB when available, falling back to an
in-process pandas expression when only pandas is present. Only a single read-only
`SELECT`/`WITH` statement is accepted; DDL/DML and multiple statements are
refused. Numerical questions therefore get a deterministic answer with
cell/range provenance, not model arithmetic.
"""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import DocumentConfig, document_config

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|import|install|load|"
    r"pragma|call|set|truncate|replace|merge|grant|revoke|vacuum|begin|commit|rollback)\b",
    re.IGNORECASE,
)
_SELECT_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


@dataclass
class QueryResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    sql: str = ""
    engine: str = "none"
    error: Optional[str] = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "document_query_result", "ok": self.ok, "columns": self.columns,
            "rows": self.rows[:1000], "rowCount": self.row_count, "sql": self.sql,
            "engine": self.engine, "truncated": self.truncated, "error": self.error,
        }


def engine_available(cfg: Optional[DocumentConfig] = None) -> str:
    cfg = cfg or document_config()
    if cfg.query_engine == "none":
        return "none"
    if cfg.query_engine == "duckdb":
        try:
            import duckdb  # noqa: F401,PLC0415

            return "duckdb"
        except Exception:  # noqa: BLE001
            pass
    try:
        import pandas  # noqa: F401,PLC0415

        return "pandas"
    except Exception:  # noqa: BLE001
        return "none"


def validate_sql(sql: str) -> Optional[str]:
    """Return an error message when `sql` is not a single read-only query."""
    text = (sql or "").strip().rstrip(";")
    if not text:
        return "a SQL query is required"
    if ";" in text:
        return "only a single statement is allowed"
    if not _SELECT_ONLY.match(text):
        return "only SELECT/WITH queries are allowed"
    match = _FORBIDDEN.search(text)
    if match:
        return f"the keyword {match.group(0)!r} is not allowed in a query"
    return None


def query_rows(
    rows: list[list[str]],
    columns: list[str],
    sql: str,
    *,
    cfg: Optional[DocumentConfig] = None,
    table_name: str = "data",
) -> QueryResult:
    """Materialize `rows` and run a read-only SQL query over them."""
    cfg = cfg or document_config()
    invalid = validate_sql(sql)
    if invalid:
        return QueryResult(ok=False, sql=sql, error=invalid)
    engine = engine_available(cfg)
    if engine == "none":
        return QueryResult(ok=False, sql=sql, engine="none",
                           error="no query engine is available (install duckdb or pandas)")

    workdir = tempfile.mkdtemp(prefix="eclipse-doc-query-")
    try:
        csv_path = os.path.join(workdir, f"{_safe_name(table_name)}.csv")
        _write_csv(csv_path, rows, columns)
        if engine == "duckdb":
            return _run_duckdb(csv_path, table_name, sql, cfg)
        return _run_pandas(csv_path, table_name, sql, cfg)
    finally:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)


def _write_csv(path: str, rows: list[list[str]], columns: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if columns:
            writer.writerow(columns)
        for row in rows:
            writer.writerow(row)


def _run_duckdb(csv_path: str, table_name: str, sql: str, cfg: DocumentConfig) -> QueryResult:
    import duckdb  # noqa: PLC0415

    table = _safe_name(table_name)
    literal_path = csv_path.replace("'", "''")
    try:
        con = duckdb.connect(database=":memory:", read_only=False)
        try:
            con.execute(
                f'CREATE VIEW "{table}" AS SELECT * FROM read_csv_auto(\'{literal_path}\', header=true, sample_size=-1)'
            )
            cursor = con.execute(sql)
            columns = [d[0] for d in (cursor.description or [])]
            fetched = cursor.fetchmany(1000)
            rows = [[_jsonable(v) for v in row] for row in fetched]
            return QueryResult(ok=True, columns=columns, rows=rows, row_count=len(rows), sql=sql, engine="duckdb",
                               truncated=len(rows) >= 1000)
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 - a bad query is a reported failure
        return QueryResult(ok=False, sql=sql, engine="duckdb", error=str(exc))


def _run_pandas(csv_path: str, table_name: str, sql: str, cfg: DocumentConfig) -> QueryResult:
    import pandas as pd  # noqa: PLC0415

    try:
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        # pandas has no SQL engine; support a `df.query("...")` form only.
        match = re.search(r'query\(\s*("|\')(.*?)\1\s*\)', sql, re.DOTALL)
        if not match:
            return QueryResult(ok=False, sql=sql, engine="pandas",
                               error="the pandas engine supports only `df.query(\"...\")` expressions")
        result = frame.query(match.group(2))
        columns = list(result.columns)
        rows = [[None if pd.isna(v) else v for v in row] for row in result.values.tolist()[:1000]]
        return QueryResult(ok=True, columns=[str(c) for c in columns], rows=rows, row_count=len(rows),
                           sql=sql, engine="pandas", truncated=len(rows) >= 1000)
    except Exception as exc:  # noqa: BLE001
        return QueryResult(ok=False, sql=sql, engine="pandas", error=str(exc))


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name or "data")[:64] or "data"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


__all__ = ["QueryResult", "query_rows", "engine_available", "validate_sql"]
