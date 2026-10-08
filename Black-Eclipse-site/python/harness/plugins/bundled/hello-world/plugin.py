"""The Hello World reference plugin.

It demonstrates the whole SDK: tools, a skill, an event handler, a hook, a
command, a UI panel and a worker — all permission-checked through the context.
"""

from harness.plugins.sdk import (
    Plugin,
    command,
    event_handler,
    hook,
    skill,
    tool,
    ui_panel,
    worker,
)


class HelloPlugin(Plugin):
    async def on_enable(self, ctx):  # noqa: ANN001
        ctx.log.info("hello-world enabled")
        ctx.storage.set("enable_count", ctx.storage.get("enable_count", 0) + 1)

    @tool(
        name="greet",
        description="Greet someone using the configured greeting.",
        schema={"type": "object", "properties": {"name": {"type": "string"}}},
    )
    async def greet(self, args, ctx):  # noqa: ANN001
        word = ctx.config.get("greeting", "Hello")
        suffix = "!!!" if ctx.config.get("excited") else "."
        name = args.get("name") or "world"
        ctx.storage.set("last_greeted", name)
        return f"{word}, {name}{suffix}"

    @tool(
        name="echo",
        description="Echo a value back.",
        schema={"type": "object", "properties": {"value": {"type": "string"}}},
    )
    async def echo(self, args, ctx):  # noqa: ANN001
        return {"echo": args.get("value")}

    @tool(
        name="fetch_status",
        description="Reach the network (requires the `network` permission).",
        schema={"type": "object", "properties": {}},
    )
    async def fetch_status(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get("https://example.com")
        return {"status": response.status}

    @skill("hello-skill", description="A minimal reference skill.")
    def hello_skill(self):
        return "# Hello Skill\n\nSay hello, then confirm the greeting matches configuration."

    @hook("before_tool_call", order=10, on_error="continue")
    async def observe_tool(self, payload, ctx):  # noqa: ANN001
        # Observational only: record that a tool is about to run.
        ctx.storage.set("last_tool", payload.get("tool"))
        return None

    @event_handler("hello.ping")
    async def on_ping(self, event, ctx):  # noqa: ANN001
        ctx.log.info(f"received ping: {event.get('data')}")
        ctx.events.publish("hello.pong", {"echo": event.get("data")})

    @command("status", description="Return the plugin's own status.", schema={"type": "object", "properties": {}})
    async def status_command(self, args, ctx):  # noqa: ANN001
        return {
            "plugin": ctx.plugin_id,
            "version": ctx.version,
            "greeting": ctx.config.get("greeting"),
            "greets": ctx.storage.get("enable_count", 0),
        }

    @ui_panel("panel", "hello-panel", title="Hello")
    def hello_panel(self, ctx):  # noqa: ANN001
        return {
            "type": "keyvalue",
            "items": [
                {"label": "Plugin", "value": ctx.plugin_id},
                {"label": "Version", "value": ctx.version},
                {"label": "Greeting", "value": ctx.config.get("greeting")},
                {"label": "Enable count", "value": ctx.storage.get("enable_count", 0)},
            ],
        }

    @worker("heartbeat", interval_seconds=0)
    async def heartbeat(self, ctx):  # noqa: ANN001
        ctx.storage.set("last_heartbeat", "ok")


plugin = HelloPlugin
