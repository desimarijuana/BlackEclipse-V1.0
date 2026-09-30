"""Introspection mixin for `MCPManager` (Phase 6.1 pure extraction).

Status, summary, diagnostics and the secret-free public config view. Pure move
out of `manager.py` with no behavior change; `MCPManager` inherits this mixin so
its public API is unchanged. These methods read `self._runtimes` and call
`self._lifecycle_status` — they hold no state of their own.
"""

from __future__ import annotations

from typing import Any, Optional

from .runtime import MCPServerStatus, _ServerRuntime


class IntrospectionMixin:
    """Read-only status/introspection over the configured runtimes."""

    def statuses(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rt in self._runtimes.values():
            status = MCPServerStatus(
                id=rt.config.id,
                name=rt.config.name or rt.config.id,
                enabled=rt.config.enabled,
                state=rt.state,
                protocol_version=rt.connection.protocol_version if rt.connection else None,
                server_info=rt.connection.server_info if rt.connection else None,
                diagnostic=rt.diagnostic,
                registered_tools=list(rt.registered_tools),
                tools=[d.public() for d in rt.descriptors.values()],
            )
            entry = status.public()
            entry["lifecycle"] = self._lifecycle_status(rt)
            out.append(entry)
        return out

    def _lifecycle_status(self, rt: _ServerRuntime) -> dict[str, Any]:
        """Bounded, content-free lifecycle status for one server."""
        cached = len(rt.descriptors) if rt.lazy_active else 0
        truncated = (
            rt.tools_discovered is not None
            and rt.tools_kept is not None
            and rt.tools_discovered > rt.tools_kept
        )
        return {
            **rt.budget.public(),
            "lazy": bool(rt.config.lazy),
            "lazyActive": rt.lazy_active,
            "cachedTools": cached,
            "cacheStale": rt.cache_stale,
            "toolsDiscovered": rt.tools_discovered,
            "toolsKept": rt.tools_kept,
            "toolsTruncated": truncated,
            "connected": rt.state == "connected",
            "inFlight": rt.in_flight,
            "keepaliveInterval": rt.config.keepalive_interval,
            "keepaliveFailures": rt.keepalive_failures,
            "recycledReason": rt.recycled_reason,
            "lastErrorCode": rt.last_error_code,
            # Inbound-notification + circuit-breaker facts (content-free).
            "catalogChanges": rt.catalog_changes,
            "lastCatalogChangeAt": rt.last_catalog_change_at,
            "removedTools": list(rt.removed_tools),
            "circuit": rt.circuit.public(),
            "sampling": rt.sampling.public(),
            "interactions": rt.interactions.public(),
            "metrics": {
                "calls": rt.calls,
                "errors": rt.errors,
                "avgLatencyMs": int(rt.total_latency_ms / rt.calls) if rt.calls else 0,
            },
            # The last operator-triggered Verify verdict (content-free), or None.
            "verify": rt.verify_result,
        }

    def summary(self) -> dict[str, Any]:
        servers = self.statuses()
        return {
            "configured": len(servers),
            "connected": sum(1 for s in servers if s["state"] == "connected"),
            "lazy": sum(1 for s in servers if s.get("lifecycle", {}).get("lazyActive")),
            "registeredTools": sum(len(s["registeredTools"]) for s in servers),
            "loadDiagnostics": self.load_diagnostics,
        }

    def catalog_digest_for(self, server_id: str) -> Optional[str]:
        """The live catalog digest for a configured server (for confirmation)."""
        rt = self._runtimes.get(server_id)
        return rt.catalog_digest if rt is not None else None

    def diagnostics(
        self,
        resolved_secrets: Optional[dict[str, dict[str, bool]]] = None,
        token_status: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Setup diagnostics for every configured server + the environment.

        Pure inspection: never activates a server or runs a tool. `resolved_secrets`
        may map server_id → {secretName: bool} so the caller (which owns the vault)
        can report missing references without the manager resolving values.
        `token_status` maps server_id → an OAuth token status dict (the caller
        owns the vault).
        """
        from .diagnostics import check_server, environment_diagnostics

        resolved_secrets = resolved_secrets or {}
        token_status = token_status or {}
        servers = []
        for rt in self._runtimes.values():
            servers.append(check_server(
                rt.config,
                resolved_secrets=resolved_secrets.get(rt.config.id),
                connection_state=rt.state,
                discovered_tools=len(rt.descriptors),
                selected_tools=sum(1 for d in rt.descriptors.values() if d.selected),
                token_status=token_status.get(rt.config.id),
                verify=rt.verify_result,
                tools_discovered=rt.tools_discovered,
                tools_kept=rt.tools_kept,
            ).to_public())
        return {"environment": [c.to_public() for c in environment_diagnostics()], "servers": servers}

    def public_configs(self) -> list[dict[str, Any]]:
        """Every configured server with its non-secret config + live status.

        Merges the persisted config (secret-free: env KEYS only) with the live
        connection/discovery state, so the settings UI can render both what is
        configured and why a call is (or is not) available.
        """
        out: list[dict[str, Any]] = []
        for rt in self._runtimes.values():
            entry = rt.config.public_dict()
            # `public_dict()` names the capability-toggles map `tools`; here that
            # key holds the DISCOVERED tool array instead. Expose the toggles
            # under a distinct key so neither is lost.
            entry["capabilityToggles"] = entry.pop("tools", {})
            entry.update(
                {
                    "state": rt.state,
                    "diagnostic": rt.diagnostic,
                    "protocolVersion": rt.connection.protocol_version if rt.connection else None,
                    "serverInfo": rt.connection.server_info if rt.connection else None,
                    "catalogDigest": rt.catalog_digest,
                    "registeredTools": list(rt.registered_tools),
                    "tools": [d.public() for d in rt.descriptors.values()],
                    "capabilities": rt.connection.capabilities if rt.connection else {},
                    "resources": rt.connection.resources if rt.connection else [],
                    "prompts": rt.connection.prompts if rt.connection else [],
                    "lifecycle": self._lifecycle_status(rt),
                }
            )
            out.append(entry)
        return out


__all__ = ["IntrospectionMixin"]
