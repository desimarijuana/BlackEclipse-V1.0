"""Contribution registry — wire a plugin's contributions into Eclipse's systems.

Registration is strict and bidirectional: every contribution the manifest
declares MUST be provided by the runtime, and every contribution the runtime
provides MUST be declared. A mismatch is a validation failure, so a manifest can
never lie about what a plugin does.

Tools register on the ONE `ToolRegistry` (namespaced `plug_<id>_<name>`), events
on the ONE `PluginEventBridge` (which rides the process EventBus), hooks on the
`HookRegistry`. Commands, UI, workers, webhooks and provider descriptors are
kept as descriptors for the manager to drive. A contributed tool with a non-read
permission is routed through Eclipse's existing effect authorizer unchanged.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from ..tools import ToolDefinition
from .errors import PluginError
from .manifest import PluginManifest
from .model import PluginRecord
from .sdk import CONTRIB_ATTR

TOOL_PREFIX = "plug_"
_RISK_BY_PERMISSION = {"read": "low", "write": "medium", "external_action": "high"}


class ContributionError(PluginError):
    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__("PLUGIN_CONTRIBUTION_MISMATCH", message, detail=detail)


def _sanitize(value: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in (value or "").lower())


def tool_name_for(plugin_id: str, tool_name: str) -> str:
    return f"{TOOL_PREFIX}{_sanitize(plugin_id)}_{_sanitize(tool_name)}"


class ContributionRegistry:
    def __init__(
        self,
        *,
        tool_registry: Any,
        event_bridge: Any,
        hook_registry: Any,
        command_registry: dict[str, dict[str, Any]],
        telemetry: Optional[Callable[[str, str, dict[str, Any]], None]] = None,
    ) -> None:
        self._tools = tool_registry
        self._events = event_bridge
        self._hooks = hook_registry
        self._commands = command_registry
        self._telemetry = telemetry
        # plugin_id -> registered surface (for teardown)
        self._by_plugin: dict[str, dict[str, list[str]]] = {}
        self._descriptors: dict[str, list[dict[str, Any]]] = {}

    # ── registration ─────────────────────────────────────────────────────────

    def register_all(
        self, record: PluginRecord, manifest: PluginManifest, instance: Any, ctx: Any,
    ) -> list[dict[str, Any]]:
        contributions = instance.contributions() if hasattr(instance, "contributions") else []
        by_kind = self._group(contributions)
        self._assert_matches(manifest, by_kind)
        self._assert_event_permissions(manifest, by_kind)

        registered: list[dict[str, Any]] = []
        surface: dict[str, list[str]] = {"tools": [], "events": [], "hooks": [], "commands": [], "ui": [],
                                          "workers": [], "webhooks": [], "skills": [], "research_providers": [],
                                          "data_providers": [], "agents": [], "workflows": []}

        for item in by_kind.get("tool", []):
            namespaced = tool_name_for(manifest.id, item["name"])
            self._tools.register(self._make_tool(record, manifest, item, ctx))
            surface["tools"].append(namespaced)
            registered.append({"kind": "tool", "name": item["name"], "namespaced": namespaced})

        for item in by_kind.get("event", []):
            self._events.register(manifest.id, item["pattern"], item["handler"], order=item.get("order", 100))
            surface["events"].append(item["pattern"])
            registered.append({"kind": "event", "name": item["pattern"]})

        for item in by_kind.get("hook", []):
            self._hooks.register(
                manifest.id, item["name"], item["handler"], order=item.get("order", 100),
                on_error=item.get("on_error", "continue"), timeout_ms=item.get("timeout_ms", 5_000),
            )
            surface["hooks"].append(item["name"])
            registered.append({"kind": "hook", "name": item["name"]})

        commands = self._commands.setdefault(manifest.id, {})
        for item in by_kind.get("command", []):
            commands[item["name"]] = item
            surface["commands"].append(item["name"])
            registered.append({"kind": "command", "name": item["name"]})

        for item in by_kind.get("ui", []):
            surface["ui"].append(item["id"])
            registered.append({"kind": "ui", "name": item["id"], "meta": {"uiKind": item.get("ui_kind"),
                                                                          "title": item.get("title")}})
        for item in by_kind.get("worker", []):
            surface["workers"].append(item["name"])
            registered.append({"kind": "worker", "name": item["name"],
                               "meta": {"intervalSeconds": item.get("interval_seconds", 0)}})
        for item in by_kind.get("webhook", []):
            surface["webhooks"].append(item["id"])
            registered.append({"kind": "webhook", "name": item["id"],
                               "meta": {"direction": item.get("direction", "inbound")}})
        for item in by_kind.get("skill", []):
            surface["skills"].append(item["name"])
            registered.append({"kind": "skill", "name": item["name"],
                               "meta": {"description": item.get("description", ""), "path": item.get("path")}})

        for item in by_kind.get("research_provider", []):
            surface["research_providers"].append(item["name"])
            registered.append({"kind": "research_provider", "name": item["name"]})
        for item in by_kind.get("data_provider", []):
            surface["data_providers"].append(item["name"])
            registered.append({"kind": "data_provider", "name": item["name"]})
        for item in by_kind.get("agent", []):
            surface["agents"].append(item["id"])
            registered.append({"kind": "agent", "name": item["id"]})
        for item in by_kind.get("workflow", []):
            surface["workflows"].append(item["id"])
            registered.append({"kind": "workflow", "name": item["id"]})

        # Non-executable descriptors (skills/providers/agents/workers/webhooks/ui)
        # are exposed for discovery/UI; the executable ones are host-driven.
        self._by_plugin[manifest.id] = surface
        self._descriptors[manifest.id] = registered
        return registered

    def unregister_all(self, plugin_id: str) -> None:
        surface = self._by_plugin.pop(plugin_id, None)
        self._descriptors.pop(plugin_id, None)
        if not surface:
            self._commands.pop(plugin_id, None)
            return
        for name in surface.get("tools", []):
            self._tools.unregister(name)
        self._events.unregister_plugin(plugin_id)
        self._hooks.unregister_plugin(plugin_id)
        self._commands.pop(plugin_id, None)

    def descriptors(self, plugin_id: str) -> list[dict[str, Any]]:
        return self._descriptors.get(plugin_id, [])

    def all_tool_names(self) -> list[str]:
        names: list[str] = []
        for surface in self._by_plugin.values():
            names.extend(surface.get("tools", []))
        return names

    # ── tool construction ────────────────────────────────────────────────────

    def _make_tool(self, record: PluginRecord, manifest: PluginManifest, item: dict[str, Any], ctx: Any) -> ToolDefinition:
        method = item["handler"]
        namespaced = tool_name_for(manifest.id, item["name"])

        async def handler(args: dict[str, Any], run_ctx: Any) -> Any:
            emitter = getattr(run_ctx, "emitter", None)
            started = time.monotonic()
            if emitter is not None:
                await _safe_emit(emitter, "plugin.tool.started", {
                    "pluginId": manifest.id, "capability": item["name"], "tool": namespaced,
                })
            try:
                result = method(args, ctx)
                if asyncio.iscoroutine(result):
                    result = await result
                if emitter is not None:
                    await _safe_emit(emitter, "plugin.tool.completed", {
                        "pluginId": manifest.id, "capability": item["name"],
                        "durationMs": round((time.monotonic() - started) * 1000, 1),
                    })
                return result
            except Exception as exc:
                if emitter is not None:
                    await _safe_emit(emitter, "plugin.tool.failed", {
                        "pluginId": manifest.id, "capability": item["name"],
                        "error": type(exc).__name__,
                    })
                raise

        return ToolDefinition(
            name=namespaced,
            description=item.get("description") or f"Plugin capability {item['name']} from {manifest.name}",
            input_schema=item.get("schema") or {"type": "object", "properties": {}},
            handler=handler,
            permission=item.get("permission", "read"),
            risk=_RISK_BY_PERMISSION.get(item.get("permission", "read"), "low"),
            timeout_ms=int(item.get("timeout_ms", 20_000)),
            output_schema=item.get("output_schema"),
            effect=item.get("effect"),
            effect_metadata={
                "source_type": "plugin",
                "plugin_id": manifest.id,
                "plugin_version": manifest.version,
                "capability": item["name"],
            },
            version=manifest.version,
        )

    # ── validation ───────────────────────────────────────────────────────────

    def _group(self, contributions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for c in contributions:
            grouped.setdefault(c.get("kind", ""), []).append(c)
        return grouped

    def _assert_matches(self, manifest: PluginManifest, by_kind: dict[str, list[dict[str, Any]]]) -> None:
        declared = manifest.contributes.all_contribution_names()
        problems: list[str] = []

        def names(kind: str, key: str = "name") -> set[str]:
            return {str(i.get(key)) for i in by_kind.get(kind, [])}

        for kind, declared_names in declared.items():
            if kind == "hooks":
                continue  # hooks are cross-checked in their own block below
            impl = names(self._impl_kind(kind),
                         "id" if kind in ("ui", "agents", "webhooks", "workflows") else "name")
            missing = sorted(set(declared_names) - impl)
            extra = sorted(impl - set(declared_names))
            if missing:
                problems.append(f"declared {kind} not provided by runtime: {', '.join(missing)}")
            if extra:
                problems.append(f"{kind} provided by runtime but not declared: {', '.join(extra)}")

        hook_declared = {h.name for h in manifest.contributes.hooks}
        hook_impl = names("hook")
        for miss in sorted(hook_declared - hook_impl):
            problems.append(f"declared hook not provided: {miss}")
        for extra in sorted(hook_impl - hook_declared):
            problems.append(f"hook provided but not declared: {extra}")

        # events: declared subscribes must equal implemented patterns
        if manifest.contributes.events:
            declared_subs = set(manifest.contributes.events.subscribes)
            impl_subs = {str(e.get("pattern")) for e in by_kind.get("event", [])}
            for miss in sorted(declared_subs - impl_subs):
                problems.append(f"declared event subscription not provided: {miss}")
            for extra in sorted(impl_subs - declared_subs):
                problems.append(f"event subscription provided but not declared: {extra}")
        elif by_kind.get("event"):
            problems.append("runtime subscribes to events but the manifest declares none")

        if problems:
            raise ContributionError("; ".join(sorted(set(problems))), detail={"problems": problems})

    @staticmethod
    def _assert_event_permissions(manifest: PluginManifest, by_kind: dict[str, list[dict[str, Any]]]) -> None:
        if by_kind.get("event") and "events.subscribe" not in manifest.permissions:
            raise ContributionError(
                "plugin subscribes to events without the 'events.subscribe' permission",
                detail={"permission": "events.subscribe"},
            )
        publishes = manifest.contributes.events.publishes if manifest.contributes.events else []
        if publishes and "events.publish" not in manifest.permissions:
            raise ContributionError(
                "plugin declares published events without the 'events.publish' permission",
                detail={"permission": "events.publish"},
            )

    @staticmethod
    def _impl_kind(manifest_kind: str) -> str:
        return {
            "tools": "tool", "skills": "skill", "hooks": "hook", "commands": "command",
            "ui": "ui", "workers": "worker", "webhooks": "webhook", "agents": "agent",
            "research_providers": "research_provider", "data_providers": "data_provider",
        }.get(manifest_kind, manifest_kind)


async def _safe_emit(emitter: Any, event_type: str, data: dict[str, Any]) -> None:
    try:
        await emitter.emit(event_type, data)
    except Exception:  # noqa: BLE001 - telemetry must never break a tool
        pass


__all__ = ["ContributionRegistry", "ContributionError", "tool_name_for", "TOOL_PREFIX"]
