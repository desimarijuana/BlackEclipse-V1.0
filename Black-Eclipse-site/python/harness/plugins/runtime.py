"""The plugin runtime context — the permission-checked surface a plugin sees.

A plugin never receives a raw store, bus, registry, model or database handle.
It receives a `PluginContext` whose every sensitive accessor checks the plugin's
granted permissions first. This is where "declaration alone is not enforcement"
becomes true: the check is at the call site, in this object.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .config import PluginConfig
from .manifest import PluginManifest
from .permissions import GrantedPermissions
from .secrets import PluginSecrets
from .storage import PluginStorage


class _SecretsFacade:
    def __init__(self, plugin_id: str, permissions: GrantedPermissions, secrets: PluginSecrets) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._secrets = secrets

    def get(self, name: str) -> Optional[str]:
        self._permissions.require("secrets", "secrets.get")
        return self._secrets.get(self._plugin_id, name)

    def require(self, name: str) -> str:
        self._permissions.require("secrets", "secrets.get")
        return self._secrets.require(self._plugin_id, name)

    def set(self, name: str, value: str) -> None:
        self._permissions.require("secrets", "secrets.set")
        self._secrets.set(self._plugin_id, name, value)

    def names(self) -> list[str]:
        self._permissions.require("secrets", "secrets.list")
        return self._secrets.names(self._plugin_id)

    def has(self, name: str) -> bool:
        self._permissions.require("secrets", "secrets.list")
        return self._secrets.has(self._plugin_id, name)


class _EventsFacade:
    def __init__(self, plugin_id: str, permissions: GrantedPermissions, host: Any) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._host = host

    def publish(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        self._permissions.require("events.publish", "events.publish")
        self._host.publish_plugin_event(self._plugin_id, event_type, data or {})

    emit = publish


class _AuthFacade:
    """Token access for the plugin. The host owns the lifecycle; the plugin only
    reads a valid access token (permission: `secrets`)."""

    def __init__(self, plugin_id: str, permissions: GrantedPermissions, client: Any) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._client = client

    async def token(self) -> str:
        self._permissions.require("secrets", "auth.token")
        if self._client is None:
            from .errors import PluginError

            raise PluginError("PLUGIN_AUTH_NOT_CONFIGURED", "this plugin declares no oauth2 authentication")
        return await self._client.token()

    def status(self) -> dict:
        self._permissions.require("secrets", "auth.status")
        if self._client is None:
            return {"pluginId": self._plugin_id, "configured": False}
        return {"configured": True, **self._client.status()}


class _WebhooksFacade:
    """Outbound webhook delivery (permission: `webhooks`). Inbound delivery is
    handled by the host route; this is the plugin-initiated direction."""

    def __init__(self, plugin_id: str, permissions: GrantedPermissions, host: Any) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._host = host

    async def deliver(self, webhook_id: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._permissions.require("webhooks", "webhooks.deliver")
        return await self._host.deliver_webhook(self._plugin_id, webhook_id, payload or {})

    def targets(self) -> list[dict[str, Any]]:
        self._permissions.require("webhooks", "webhooks.list")
        return self._host.webhook_targets(self._plugin_id)


class _Logger:
    def __init__(self, plugin_id: str, store: Any, host: Any) -> None:
        self._plugin_id = plugin_id
        self._store = store
        self._host = host

    def _write(self, level: str, message: str) -> None:
        self._store.log(self._plugin_id, level, message)
        if self._host is not None:
            try:
                self._host.log_plugin(self._plugin_id, level, message)
            except Exception:  # noqa: BLE001 - logging must never raise into a plugin
                pass

    def debug(self, message: str) -> None:
        self._write("debug", message)

    def info(self, message: str) -> None:
        self._write("info", message)

    def warning(self, message: str) -> None:
        self._write("warning", message)

    def error(self, message: str) -> None:
        self._write("error", message)


class PluginContext:
    """What a plugin receives. Constructed by the manager for one plugin instance."""

    def __init__(
        self,
        *,
        manifest: PluginManifest,
        permissions: GrantedPermissions,
        config: PluginConfig,
        storage: PluginStorage,
        secrets: PluginSecrets,
        http: Any,
        host: Any,
        store: Any,
        auth: Any = None,
    ) -> None:
        self.plugin_id = manifest.id
        self.version = manifest.version
        self.manifest = manifest
        self.config = config
        self.storage = storage
        self.http = http
        self.secrets = _SecretsFacade(manifest.id, permissions, secrets)
        self.auth = _AuthFacade(manifest.id, permissions, auth)
        self.events = _EventsFacade(manifest.id, permissions, host)
        self.webhooks = _WebhooksFacade(manifest.id, permissions, host)
        self.logger = _Logger(manifest.id, store, host)
        self.log = self.logger
        self._permissions = permissions
        self._host = host
        self._store = store

    # ── capability gates for host-mediated actions ──────────────────────────

    def require(self, permission: str, action: str = "") -> None:
        self._permissions.require(permission, action)

    def has_permission(self, permission: str) -> bool:
        return self._permissions.has(permission)

    async def create_task(self, title: str, *, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._permissions.require("task.create", "task.create")
        return await self._host.create_task(self.plugin_id, title, details or {})

    async def invoke_agent(self, agent_id: str, objective: str) -> dict[str, Any]:
        self._permissions.require("agent.invoke", "agent.invoke")
        return await self._host.invoke_agent(self.plugin_id, agent_id, objective)

    async def run_workflow(self, workflow_id: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._permissions.require("workflow.execute", "workflow.execute")
        return await self._host.run_workflow(self.plugin_id, workflow_id, payload or {})

    def remember(self, **kwargs: Any) -> dict[str, Any]:
        self._permissions.require("memory.write", "memory.write")
        return self._host.remember(self.plugin_id, **kwargs)

    def recall(self, **kwargs: Any) -> list[dict[str, Any]]:
        self._permissions.require("memory.read", "memory.read")
        return self._host.recall(self.plugin_id, **kwargs)

    def add_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Attach a research result to the Evidence engine. The host stamps
        provenance; arbitrary plugin data cannot bypass the evidence layer."""
        self._permissions.require("research.execute", "research.evidence")
        return self._host.add_plugin_evidence(self.plugin_id, evidence)

    def telemetry(self, name: str, data: Optional[dict[str, Any]] = None) -> None:
        self._host.plugin_telemetry(self.plugin_id, name, data or {})

    async def fetch_secret(self, name: str) -> Optional[str]:
        return self.secrets.get(name)


__all__ = ["PluginContext"]
