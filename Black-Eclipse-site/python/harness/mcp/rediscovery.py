"""Inbound MCP notification handling — catalog-change rediscovery (continuation).

A server may add, remove or rename tools mid-session by sending
`notifications/tools/list_changed` (and the analogous resource/prompt
notifications). Without handling it, a changed tool set is only noticed on
reconnect — so a tool the operator approved can keep running under a stale
catalog — and a changed resource/prompt listing is served stale from the
connect-time snapshot until a reconnect.

This mixin wires a per-server callback that, for ANY of the three list-changed
notifications, takes the per-server connect lock (so a notification landing while
a call is in flight cannot corrupt state) and re-runs the relevant listing through
the existing path. There is no second discovery mechanism.

  * `tools` — re-runs discovery for THAT ONE server
    (`MCPConnection.refresh_tools` -> `_build_descriptors`), recomputes the
    catalog digest (which no longer matches `confirmed_catalog_digest`, so
    annotation-sourced tools become inert until the operator re-confirms — the
    existing gate, never bypassed), deregisters tools that disappeared, and
    re-registers tools that still pass the same authority checks.
  * `resources` / `prompts` — re-runs the corresponding list so the utility tools
    serve the current listing rather than the connect-time snapshot. There is no
    digest/activation gate on these (they are read-only utility surfaces).

Every case emits a bounded, content-free `mcp.catalog.changed` event (server id,
kind, counts, and — for tools — the new digest; never a description).

Extracted so `manager.py` stays under its size ratchet; `MCPManager` inherits it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .runtime import _ServerRuntime

log = logging.getLogger("harness.mcp.rediscovery")


class RediscoveryMixin:
    """Handles inbound `list_changed` notifications by rediscovering one server."""

    def _wire_catalog_callback(self, rt: _ServerRuntime) -> None:
        """Attach the connection's catalog-change callback (called on connect)."""
        if rt.connection is None:
            return

        async def on_catalog_changed(kind: str) -> None:
            await self._on_catalog_changed(rt, kind)

        rt.connection._catalog_changed = on_catalog_changed

    async def _on_catalog_changed(self, rt: _ServerRuntime, kind: str) -> None:
        """Refresh one server's listing after a declared list-changed notification."""
        if kind not in ("tools", "resources", "prompts"):
            return
        connection = rt.connection
        if connection is None or rt.state != "connected":
            # A notification for an unknown/dead server is ignored safely.
            return
        if kind in ("resources", "prompts"):
            # A resource/prompt listing has no activation gate; just refresh the
            # snapshot the utility tools read from. A failure keeps the old list.
            async with rt.connect_lock:
                connection = rt.connection
                if connection is None or rt.state != "connected":
                    return
                try:
                    await connection.refresh_listing(kind)
                except Exception:  # noqa: BLE001 - keep the previous listing
                    log.warning(
                        "MCP %s refresh failed for %s; keeping the previous listing",
                        kind, rt.config.id, exc_info=True,
                    )
                    return
                rt.catalog_changes += 1
                rt.last_catalog_change_at = datetime.now(timezone.utc).isoformat()
            await self._emit_catalog_changed(rt, removed_count=0, kind=kind)
            return

        async with rt.connect_lock:
            # Re-check under the lock: the connection may have been replaced (a
            # reconnect) while we waited.
            connection = rt.connection
            if connection is None or rt.state != "connected":
                return
            digest_before = rt.catalog_digest
            before = set(rt.descriptors.keys())
            prev_registered = set(rt.registered_tools)
            try:
                await connection.refresh_tools()
            except Exception:  # noqa: BLE001 - a failed refresh keeps the old catalog
                log.warning(
                    "MCP catalog refresh failed for %s; keeping the previous catalog",
                    rt.config.id, exc_info=True,
                )
                return
            # Rebuild descriptors through the normal path. This recomputes the
            # digest and re-runs every activation gate, so a changed catalog
            # cannot keep a tool active.
            rt.descriptors.clear()
            self._build_descriptors(rt)
            if rt.config.lazy:
                self._write_cache(rt)
            after = set(rt.descriptors.keys())
            removed = sorted(before - after)
            rt.removed_tools = removed
            rt.catalog_changes += 1
            rt.last_catalog_change_at = datetime.now(timezone.utc).isoformat()
            # Deregister tools that vanished BEFORE re-registering, so a removed
            # tool is no longer callable even though `_register_all` only adds.
            if self._registry is not None:
                for eclipse_name in prev_registered - set(
                    d.eclipse_name for d in rt.descriptors.values()
                ):
                    self._registry.unregister(eclipse_name)
                    self._owned_names.discard(eclipse_name)
                # Re-register: keeps tools that still pass the same checks.
                self._register_all(self._registry)
                self._register_utilities(self._registry)
        # A server may send `list_changed` gratuitously. Emitting for an unchanged
        # catalog would create a stream of no-op "catalog changed" signals, so only
        # emit when the digest actually moved. The listing refresh above (and the
        # registry reconcile) still ran; only the EVENT is suppressed.
        digest_unchanged = (
            kind == "tools"
            and digest_before is not None
            and rt.catalog_digest == digest_before
        )
        if digest_unchanged:
            return
        await self._emit_catalog_changed(rt, removed_count=len(removed), kind=kind)

    async def _emit_catalog_changed(
        self, rt: _ServerRuntime, *, removed_count: int, kind: str
    ) -> None:
        """Emit a bounded, content-free `mcp.catalog.changed` event.

        Counts and identity only — never a tool description. Routed through the
        manager's event sink (set by the service) when present.
        """
        payload = {
            "serverId": rt.config.id,
            "kind": kind,
            "discovered": rt.tools_discovered,
            "kept": rt.tools_kept,
            "removed": removed_count,
            "catalogDigest": rt.catalog_digest,
        }
        sink = getattr(self, "_event_sink", None)
        if sink is None:
            return
        try:
            await sink("mcp.catalog.changed", payload)
        except Exception:  # noqa: BLE001 - an emit failure must not break the session
            log.debug("could not emit mcp.catalog.changed for %s", rt.config.id, exc_info=True)


__all__: list[str] = ["RediscoveryMixin"]
