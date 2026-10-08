"""Reference plugin: Slack Web API (bearer token). `post_message` is an external
action and is routed through Eclipse's effect authorizer."""

from harness.plugins.sdk import Plugin, tool


class SlackPlugin(Plugin):
    def _base(self, ctx):  # noqa: ANN001
        return (ctx.config.get("apiBase") or "https://slack.com/api").rstrip("/")

    async def _headers(self, ctx):  # noqa: ANN001
        return {"Authorization": f"Bearer {ctx.secrets.require('token')}"}

    @tool(name="list_channels", description="List public channels in the workspace.", schema={"type": "object", "properties": {}})
    async def list_channels(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get(f"{self._base(ctx)}/conversations.list",
                                      headers=await self._headers(ctx), params={"limit": 100})
        data = response.json()
        return [{"id": c.get("id"), "name": c.get("name")} for c in data.get("channels", [])]

    @tool(
        name="post_message",
        description="Post a message to a channel.",
        schema={"type": "object", "properties": {
            "channel": {"type": "string"}, "text": {"type": "string"}},
            "required": ["channel", "text"]},
        permission="external_action",
    )
    async def post_message(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.post(f"{self._base(ctx)}/chat.postMessage",
                                       headers=await self._headers(ctx),
                                       json={"channel": args["channel"], "text": args["text"]})
        data = response.json()
        return {"ok": data.get("ok", False), "ts": data.get("ts")}


plugin = SlackPlugin
