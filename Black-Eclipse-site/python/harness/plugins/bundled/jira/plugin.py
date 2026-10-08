"""Reference plugin: Jira Cloud REST API (basic auth)."""

import base64

from harness.plugins.sdk import Plugin, tool


class JiraPlugin(Plugin):
    def _base(self, ctx):  # noqa: ANN001
        return (ctx.config.get("baseUrl") or "https://your-domain.atlassian.net").rstrip("/")

    def _headers(self, ctx):  # noqa: ANN001
        email = ctx.config.get("email") or ""
        token = ctx.secrets.require("apiToken")
        encoded = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}

    @tool(
        name="search_issues",
        description="Search issues with a JQL query.",
        schema={
            "type": "object",
            "properties": {"jql": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["jql"],
        },
    )
    async def search_issues(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get(
            f"{self._base(ctx)}/rest/api/3/search",
            headers=self._headers(ctx),
            params={"jql": args["jql"], "maxResults": min(int(args.get("limit", 20)), 100)},
        )
        data = response.json()
        return [{"key": i.get("key"), "summary": i.get("fields", {}).get("summary"),
                 "status": (i.get("fields", {}).get("status") or {}).get("name")}
                for i in data.get("issues", [])]


plugin = JiraPlugin
