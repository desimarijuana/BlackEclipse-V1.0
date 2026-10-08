"""Reference plugin: PostgreSQL read queries (via pg8000, lazily imported).

This plugin declares the elevated `database` permission, so it can only be
enabled by an operator. `query` is an external action: it is gated by Eclipse's
effect authorizer at call time, independent of enablement.
"""

from harness.plugins.sdk import Plugin, tool

_READ_ONLY = ("select", "with", "explain", "show")


class PostgresPlugin(Plugin):
    @tool(
        name="query",
        description="Run a read-only SQL query.",
        schema={
            "type": "object",
            "properties": {"sql": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["sql"],
        },
        permission="external_action",
    )
    async def query(self, args, ctx):  # noqa: ANN001
        sql = str(args["sql"]).strip()
        if not sql.lower().startswith(_READ_ONLY):
            return {"error": "only read-only statements are permitted"}
        try:
            import pg8000.native  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return {"error": "pg8000 is not installed"}
        conn = pg8000.native.Connection(
            user=ctx.config.get("user"),
            password=ctx.secrets.require("password"),
            host=ctx.config.get("host") or "localhost",
            port=int(ctx.config.get("port") or 5432),
            database=ctx.config.get("database"),
        )
        try:
            rows = conn.run(sql)
            columns = [c["name"] for c in conn.columns] if conn.columns else []
            limit = int(args.get("limit", 100))
            return {"columns": columns, "rows": [list(r) for r in rows[:limit]]}
        finally:
            conn.close()


plugin = PostgresPlugin
