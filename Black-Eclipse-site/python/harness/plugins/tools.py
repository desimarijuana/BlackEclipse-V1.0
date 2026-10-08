"""Agent-facing Plugin Platform tools.

Read-only discovery + on-demand invocation, so a plugin's capabilities are
reachable by the agent through capability search rather than by loading every
plugin tool into every prompt. Management operations (install/enable/disable/
update/rollback/uninstall) are deliberately NOT agent tools — they are operator
actions on the CLI/API surface.

`plugin_invoke` executes the target through the ONE `ToolRegistry`, so the
target tool's own permission and effect authorizer apply unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from ..tools import ToolContext, ToolRegistry

# A tool contributed by a plugin is registered as `plug_<id>_<name>`; the agent
# discovers them through these tools (and, for the eclipse agent, the `plug_`
# prefix allowlist expansion).
PLUGIN_TOOLS = [
    "plugin_list",
    "plugin_inspect",
    "plugin_capabilities",
    "plugin_health",
    "plugin_invoke",
    "plugin_run_command",
]


def _manager(ctx: ToolContext) -> Any:
    manager = getattr(ctx, "plugin_manager", None)
    if manager is None:
        from .bootstrap import get_plugin_manager

        manager = get_plugin_manager()
    return manager


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, indent=2)


async def _plugin_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    plugins = manager.list()
    return _dumps({"plugins": plugins}), {"status": "OK", "plugins": plugins}


async def _plugin_inspect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    plugin_id = str(args.get("pluginId") or "")
    try:
        data = manager.inspect(plugin_id)
    except Exception as exc:  # noqa: BLE001 - a missing plugin is data
        return f"Could not inspect plugin {plugin_id!r}: {exc}", {"status": "ERROR", "error": str(exc)}
    return _dumps(data), {"status": "OK", **data}


async def _plugin_capabilities(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    query = str(args.get("query") or "").strip().lower()
    caps = manager.capabilities()
    if query:
        caps = [c for c in caps if query in c["capability"].lower() or query in c["plugin_id"].lower()]
    return _dumps({"capabilities": caps}), {"status": "OK", "capabilities": caps}


async def _plugin_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    plugin_id = args.get("pluginId")
    if plugin_id:
        data = manager.health_report(str(plugin_id))
        return _dumps(data), {"status": "OK", **data}
    from . import health

    data = health.summarize(manager.store, manager.store.list_plugins())
    return _dumps(data), {"status": "OK", **data}


async def _plugin_invoke(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    capability = str(args.get("capability") or "")
    payload = args.get("arguments") or {}
    if not isinstance(payload, dict):
        return "arguments must be an object", {"status": "ERROR", "error": "arguments must be an object"}
    try:
        result = await manager.invoke_capability(capability, payload, ctx)
    except Exception as exc:  # noqa: BLE001 - a capability error is data
        return f"Plugin capability {capability!r} failed: {exc}", {"status": "ERROR", "error": str(exc)}
    return result.text, {"status": "OK", "result": result.data}


async def _plugin_run_command(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager(ctx)
    if manager is None:
        return "The plugin platform is unavailable.", {"status": "UNAVAILABLE"}
    plugin_id = str(args.get("pluginId") or "")
    command = str(args.get("command") or "")
    payload = args.get("arguments") or {}
    try:
        data = await manager.run_command(plugin_id, command, payload if isinstance(payload, dict) else {})
    except Exception as exc:  # noqa: BLE001
        return f"Plugin command {command!r} failed: {exc}", {"status": "ERROR", "error": str(exc)}
    return _dumps(data), {"status": "OK", **data}


_HANDLERS = {
    "plugin_list": _plugin_list,
    "plugin_inspect": _plugin_inspect,
    "plugin_capabilities": _plugin_capabilities,
    "plugin_health": _plugin_health,
    "plugin_invoke": _plugin_invoke,
    "plugin_run_command": _plugin_run_command,
}


def register_plugin_tools(registry: ToolRegistry) -> None:
    from ..tools import ToolDefinition

    definitions = [
        ToolDefinition(
            name="plugin_list",
            description="List every installed plugin with its state, version, trust and permissions.",
            input_schema={"type": "object", "properties": {}},
            handler=_plugin_list,
            permission="read",
            risk="low",
        ),
        ToolDefinition(
            name="plugin_inspect",
            description="Inspect one plugin: state, health, contributions, config, dependencies and logs.",
            input_schema={
                "type": "object",
                "properties": {"pluginId": {"type": "string", "description": "the plugin id"}},
                "required": ["pluginId"],
            },
            handler=_plugin_inspect,
            permission="read",
            risk="low",
        ),
        ToolDefinition(
            name="plugin_capabilities",
            description=(
                "List capabilities contributed by plugins (tool names, plugin id/version provenance). "
                "Use this to discover a plugin capability before invoking it."
            ),
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "optional substring filter"}},
            },
            handler=_plugin_capabilities,
            permission="read",
            risk="low",
        ),
        ToolDefinition(
            name="plugin_health",
            description="Health of one plugin, or a summary across all plugins (measured counters, never fabricated).",
            input_schema={
                "type": "object",
                "properties": {"pluginId": {"type": "string", "description": "optional plugin id"}},
            },
            handler=_plugin_health,
            permission="read",
            risk="low",
        ),
        ToolDefinition(
            name="plugin_invoke",
            description=(
                "Invoke a capability provided by an enabled plugin. Use `plugin_capabilities` first. "
                "The target's own permission and approval rules apply."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "bare name, plugin.name, or full plug_* name"},
                    "arguments": {"type": "object", "description": "arguments for the capability"},
                },
                "required": ["capability"],
            },
            handler=_plugin_invoke,
            permission="read",
            risk="low",
        ),
        ToolDefinition(
            name="plugin_run_command",
            description="Run a command contributed by an enabled plugin.",
            input_schema={
                "type": "object",
                "properties": {
                    "pluginId": {"type": "string"},
                    "command": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["pluginId", "command"],
            },
            handler=_plugin_run_command,
            permission="read",
            risk="low",
        ),
    ]
    for definition in definitions:
        if registry.get(definition.name) is None:
            registry.register(definition)


__all__ = ["PLUGIN_TOOLS", "register_plugin_tools"]
