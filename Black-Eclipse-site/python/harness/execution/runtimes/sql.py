"""The SQL runtime adapter — read-only by default, destructive ops policy-controlled.

SQL execution is special: it runs an embedded Python runner (the stdlib `sqlite3`
is always present) against a chosen database, enforces a row limit, and refuses
potentially destructive statements unless the request explicitly allows writes.
PostgreSQL is supported when a driver (`psycopg`/`psycopg2`) is installed; when it
is not, the runtime refuses honestly rather than pretending.

The database and policy live in `request.metadata`:

    {"database": "path/or/host", "dialect": "sqlite"|"postgres",
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

# The runner is staged, never executed here. It reads `payload.json` and writes
# `out.json`, mirroring the analysis sandbox's shape.
_RUNNER_SOURCE = r'''
import json, sqlite3, sys

def _destructive(sql):
    head = sql.lstrip().split(None, 1)
    return bool(head) and head[0].casefold() in {
        "drop","delete","truncate","alter","update","insert","create","replace",
        "grant","revoke","attach","vacuum",
    }

def main():
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    sql = str(payload.get("sql") or "")
    read_only = bool(payload.get("read_only", True))
    row_limit = int(payload.get("row_limit") or 1000)
    if read_only and _destructive(sql):
        print(json.dumps({"status": "refused", "code": "SQL_DESTRUCTIVE_BLOCKED"}))
        return 2
    dialect = str(payload.get("dialect") or "sqlite")
    try:
        if dialect == "postgres":
            import psycopg2  # type: ignore
            conn = psycopg2.connect(str(payload.get("database") or ""))
        else:
            conn = sqlite3.connect(str(payload.get("database") or ":memory:"))
    except Exception as exc:
        print(json.dumps({"status": "failed", "code": "SQL_CONNECT_FAILED", "message": str(exc)}))
        return 3
    try:
        cursor = conn.cursor()
        params = payload.get("params") or []
        cursor.execute(sql, tuple(params)) if params else cursor.execute(sql)
        columns = [d[0] for d in (cursor.description or [])]
        rows = cursor.fetchmany(row_limit) if columns else []
        print(json.dumps({"status": "ok", "columns": columns, "rows": [list(r) for r in rows]}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "code": "SQL_ERROR", "message": str(exc)}))
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(main())
'''


class SqlRuntime(BaseRuntime):
    language = "sql"
    name = "SqlRuntime"
    aliases = ("sqlite", "sqlite3", "postgres", "postgresql", "mysql", "duckdb")

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
        database = str(meta.get("database") or "")
        if dialect == "sqlite" and database:
            from ...code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

            try:
                resolved = resolve_within(root, database)
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
