"""The SQL runtime adapter — read-only by default, destructive ops policy-controlled.

SQL execution is special: it runs an embedded Python runner against a chosen
database, enforces a row limit, and refuses potentially destructive statements
unless the request explicitly allows writes.

Supported backends:

  * **SQLite** — the stdlib `sqlite3`, always present.
  * **PostgreSQL** — any installed PEP-249 driver: `psycopg` (v3), `psycopg2`, or
    `pg8000` (pure Python). When none is installed the runtime refuses with a
    plain sentence naming the missing driver — it never pretends to connect.
  * **MySQL** (`pymysql`/`mysqlclient`) and **DuckDB** (`duckdb`) are wired the same
    way and refuse honestly when their driver is absent.

The database and policy live in `request.metadata`:

    {"database": "path/or/host", "dialect": "sqlite"|"postgres"|"mysql"|"duckdb",
     "read_only": true, "row_limit": 1000, "format": "json"}

Default SQL execution is READ-ONLY. `read_only: false` still requires the run's
autonomy profile to permit `code.write` (enforced by the policy engine upstream).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
from .base import BaseRuntime, PreparedCommand
from .python_rt import PythonRuntime

# Statements that change data or schema. Used only for the read-only guard; the
# real protection is the database account's own privileges.
_DESTRUCTIVE = (
    "drop", "delete", "truncate", "alter", "update", "insert", "create", "replace",
    "grant", "revoke", "attach", "vacuum",
)

# The runner is staged, never executed here. It reads `payload.json` and writes its
# result to stdout as JSON, mirroring the analysis sandbox's shape. It connects
# through whichever PEP-249 driver is installed and reports a MISSING DRIVER for
# the dialect honestly (a structured refusal, not a connection error).
_RUNNER_SOURCE = r'''
import json, sqlite3, sys

DESTRUCTIVE = {
    "drop","delete","truncate","alter","update","insert","create","replace",
    "grant","revoke","attach","vacuum",
}

def _first_keyword(sql):
    # Strip leading SQL comments and whitespace, then the first word.
    text = sql.lstrip()
    while text.startswith("--") or text.startswith("/*"):
        if text.startswith("--"):
            nl = text.find("\n")
            text = "" if nl == -1 else text[nl + 1:].lstrip()
        else:
            end = text.find("*/")
            text = "" if end == -1 else text[end + 2:].lstrip()
    head = text.split(None, 1)
    return head[0].casefold() if head else ""

def _destructive(sql):
    return _first_keyword(sql) in DESTRUCTIVE

def _split_statements(script):
    """Split on top-level semicolons, honoring single/double quotes and comments."""
    statements, buf = [], []
    quote = None
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and script[i + 1] == "-":
            nl = script.find("\n", i)
            if nl == -1:
                break
            buf.append(script[i:nl + 1])
            i = nl + 1
            continue
        if ch == "/" and i + 1 < n and script[i + 1] == "*":
            end = script.find("*/", i + 2)
            if end == -1:
                buf.append(script[i:])
                break
            buf.append(script[i:end + 2])
            i = end + 2
            continue
        if ch == ";":
            piece = "".join(buf).strip()
            if piece:
                statements.append(piece)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements

def _pg_kwargs(database):
    # Parse a libpq keyword string into pg8000's expected kwargs. libpq uses
    # `dbname`; pg8000 uses `database`. Only non-secret connection NAMES/values.
    aliases = {"dbname": "database", "hostaddr": "host", "sslmode": "ssl_context"}
    kwargs = {}
    for token in str(database).split():
        if "=" in token:
            key, _, value = token.partition("=")
            key = key.strip().lower()
            value = value.strip().strip("'\"")
            key = aliases.get(key, key)
            if key == "ssl_context":
                continue  # pg8000 wants an SSLContext object, not a string
            kwargs[key] = value
    return kwargs

def _connect_postgres(database):
    # Separate IMPORT failure (no driver) from CONNECT failure (driver present).
    # psycopg3 / psycopg2 accept a full libpq DSN string directly.
    for module_name in ("psycopg", "psycopg2"):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        return module.connect(str(database))  # connect errors propagate as-is

    try:
        import pg8000.dbapi as pg
    except Exception as exc:
        raise RuntimeError("NO_DRIVER:" + str(exc or "no PostgreSQL driver installed"))
    kwargs = _pg_kwargs(database)
    if kwargs:
        return pg.connect(**kwargs)
    return pg.connect(str(database))

def _connect_mysql(database):
    for module_name in ("pymysql", "MySQLdb"):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        if "=" in str(database):
            kwargs = dict(x.split("=", 1) for x in str(database).split() if "=" in x)
            return module.connect(**{k.strip(): v.strip().strip("'\"") for k, v in kwargs.items()})
        return module.connect(str(database))
    raise RuntimeError("NO_DRIVER:no MySQL driver installed")

def _connect_duckdb(database):
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        raise RuntimeError("NO_DRIVER:" + str(exc))
    return duckdb.connect(str(database) or ":memory:")

def _connect(dialect, database):
    if dialect in ("postgres", "postgresql"):
        return _connect_postgres(database)
    if dialect in ("mysql", "mariadb"):
        return _connect_mysql(database)
    if dialect == "duckdb":
        return _connect_duckdb(database)
    return sqlite3.connect(str(database) or ":memory:")

def main():
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    script = str(payload.get("sql") or "")
    read_only = bool(payload.get("read_only", True))
    row_limit = int(payload.get("row_limit") or 1000)
    statements = _split_statements(script)
    if read_only:
        for stmt in statements:
            if _destructive(stmt):
                print(json.dumps({"status": "refused", "code": "SQL_DESTRUCTIVE_BLOCKED"}))
                return 2
    dialect = str(payload.get("dialect") or "sqlite")
    try:
        conn = _connect(dialect, str(payload.get("database") or ""))
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("NO_DRIVER:"):
            print(json.dumps({"status": "refused", "code": "SQL_DRIVER_MISSING", "message": message[10:]}))
            return 4
        print(json.dumps({"status": "failed", "code": "SQL_CONNECT_FAILED", "message": message}))
        return 3
    except Exception as exc:
        print(json.dumps({"status": "failed", "code": "SQL_CONNECT_FAILED", "message": str(exc)}))
        return 3
    results = []
    try:
        cursor = conn.cursor()
        params = list(payload.get("params") or [])
        for index, stmt in enumerate(statements):
            # Bind parameters only to a single-statement script (one params list).
            bind = tuple(params) if params and len(statements) == 1 else ()
            cursor.execute(stmt, bind) if bind else cursor.execute(stmt)
            columns = [d[0] for d in (cursor.description or [])]
            rows = [list(r) for r in cursor.fetchmany(row_limit)] if columns else []
            results.append({"statement": index, "columns": columns, "rows": rows,
                            "rowCount": (cursor.rowcount if not columns else len(rows))})
        # Commit writes so DML persists (a prior bug silently rolled inserts back).
        try:
            conn.commit()
        except Exception:
            pass
        last = results[-1] if results else {"columns": [], "rows": []}
        print(json.dumps({
            "status": "ok",
            "columns": last.get("columns", []),
            "rows": last.get("rows", []),
            "statementCount": len(results),
            "results": results,
        }))
        return 0
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(json.dumps({"status": "failed", "code": "SQL_ERROR", "message": str(exc),
                          "completed": len(results)}))
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    sys.exit(main())
'''


class SqlRuntime(BaseRuntime):
    language = "sql"
    name = "SqlRuntime"
    aliases = ("sqlite", "sqlite3", "postgres", "postgresql", "mysql", "mariadb", "duckdb")

    def available(self) -> bool:
        return bool(PythonRuntime().resolve(None))

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return PythonRuntime().resolve(project)

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        interpreter = self.resolve(None)
        if not interpreter:
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("I need an available interpreter to run SQL here.")
        meta = dict(getattr(request, "metadata", {}) or {})
        dialect = str(meta.get("dialect") or "sqlite")
        if dialect == "postgresql":
            dialect = "postgres"
        database = str(meta.get("database") or "")
        if dialect in ("sqlite", "duckdb") and database:
            from ...code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

            try:
                # `allow_ignored`: a database file (`.db`/`.sqlite`) is an explicit,
                # operator-named file the index ignore-globs exist to skip — not a
                # tree walk. Traversal/symlink/outside-root/protected still apply.
                resolved = resolve_within(root, database, allow_ignored=True)
            except PolicyDenial as denial:
                from .base import RuntimeUnavailable  # noqa: PLC0415

                raise RuntimeUnavailable(
                    "That database is outside the project folder.", code="SQL_DATABASE_OUTSIDE_WORKSPACE",
                ) from denial
            database = str(resolved)
        payload = {
            "sql": str(getattr(request, "code", "") or ""),
            "params": list(meta.get("params") or []),
            "read_only": bool(meta.get("read_only", True)),
            "row_limit": int(meta.get("row_limit") or 1000),
            "format": str(meta.get("format") or "json"),
            "dialect": dialect,
            "database": database,
        }
        runner = self._stage(workdir, "sql_runner.py", _RUNNER_SOURCE)
        payload_path = self._stage(workdir, "payload.json", json_dumps(payload))
        argv = [interpreter, str(runner), str(payload_path)]
        return PreparedCommand(argv=argv, cwd=workdir, env={}, description=f"sql ({dialect})", cleanup=[workdir])


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


__all__ = ["SqlRuntime"]
