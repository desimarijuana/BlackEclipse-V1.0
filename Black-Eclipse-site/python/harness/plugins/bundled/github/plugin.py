"""Reference plugin: GitHub (REST API via the controlled HTTP client)."""

from harness.plugins.sdk import Plugin, event_handler, skill, tool


class GitHubPlugin(Plugin):
    async def _headers(self, ctx):  # noqa: ANN001
        token = ctx.secrets.get("token")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _base(self, ctx):  # noqa: ANN001
        return (ctx.config.get("apiBase") or "https://api.github.com").rstrip("/")

    @tool(
        name="get_repo",
        description="Fetch a repository's metadata.",
        schema={"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
    )
    async def get_repo(self, args, ctx):  # noqa: ANN001
        repo = args["repo"]
        response = await ctx.http.get(f"{self._base(ctx)}/repos/{repo}", headers=await self._headers(ctx))
        if response.status == 404:
            return {"error": "repository not found", "repo": repo}
        data = response.json()
        return {"fullName": data.get("full_name"), "stars": data.get("stargazers_count"),
                "openIssues": data.get("open_issues_count")}

    @tool(
        name="list_issues",
        description="List open issues for a repository.",
        schema={"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
    )
    async def list_issues(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get(
            f"{self._base(ctx)}/repos/{args['repo']}/issues",
            headers=await self._headers(ctx),
            params={"state": "open", "per_page": 20},
        )
        return [{"number": i.get("number"), "title": i.get("title")} for i in response.json()]

    @skill("github-research", description="Research a repository's activity and open issues.")
    def github_research(self):
        return "# GitHub Research\n\n1. `get_repo` for metadata.\n2. `list_issues` for open work.\n3. Summarize."

    @event_handler("github.push")
    async def on_push(self, event, ctx):  # noqa: ANN001
        ctx.log.info(f"github push received: {event.get('data')}")


plugin = GitHubPlugin
