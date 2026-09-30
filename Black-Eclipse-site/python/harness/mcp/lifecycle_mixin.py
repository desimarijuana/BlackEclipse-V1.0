"""Manager lifecycle loop (continuation extraction, pure move).

Extracted from `manager.py` so the facade stays under its size ratchet. Owns the
ONE per-manager keepalive/recycle task and the pure recycle decision.
`MCPManager` inherits `LifecycleMixin`; behavior is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .client import MCPError
from .lifecycle import should_recycle
from .runtime import _ServerRuntime

log = logging.getLogger("harness.mcp.lifecycle_mixin")


class LifecycleMixin:
    """The manager's keepalive / recycle loop and its pure decision helper."""

    async def _lifecycle_loop(self) -> None:
        try:
            while self._started:
                interval = self._lifecycle_interval()
                await asyncio.sleep(interval)
                if not self._started:
                    return
                try:
                    await self._lifecycle_tick()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - a tick failure must not kill the loop
                    log.warning("MCP lifecycle tick failed", exc_info=True)
        except asyncio.CancelledError:
            return

    def _lifecycle_interval(self) -> float:
        """How often the loop wakes: the smallest configured keepalive/recycle gap."""
        candidates: list[float] = []
        for rt in self._runtimes.values():
            if rt.config.keepalive_interval:
                candidates.append(float(rt.config.keepalive_interval))
            if rt.config.idle_timeout_seconds:
                candidates.append(float(rt.config.idle_timeout_seconds) / 2)
            if rt.config.max_lifetime_seconds:
                candidates.append(float(rt.config.max_lifetime_seconds) / 2)
        if not candidates:
            return 30.0
        return max(5.0, min(candidates))

    async def _lifecycle_tick(self) -> None:
        """One keepalive/recycle pass. Stdio recycle never fires mid-call."""
        now = asyncio.get_event_loop().time()
        for rt in list(self._runtimes.values()):
            if rt.state != "connected" or rt.connection is None:
                continue
            action = self.due_lifecycle_action(rt, now)
            if action is None:
                continue
            if action == "keepalive":
                await self._keepalive_probe(rt)
            elif action.startswith("recycle:") and rt.in_flight == 0:
                await self._recycle(rt, action.split(":", 1)[1])

    async def _keepalive_probe(self, rt: _ServerRuntime) -> None:
        try:
            ok = await rt.connection.ping(timeout_ms=rt.limits["callTimeoutMs"])
        except (MCPError, Exception):  # noqa: BLE001 - a failed ping routes to reconnect
            ok = False
        if ok:
            return
        rt.keepalive_failures += 1
        rt.diagnostic = rt.redact("keepalive probe failed; reconnecting")
        log.info("MCP server %s keepalive failed; reconnecting", rt.config.id)
        await self._close_runtime(rt)
        await self._reconnect_on_call(rt)

    async def _recycle(self, rt: _ServerRuntime, reason: str) -> None:
        """Recycle a stdio child: fresh process, same config, tools re-registered.

        The catalog digest and cache are preserved; the old child is closed first
        so it cannot leak. Never fires mid-call (checked by the caller).
        """
        digest = rt.catalog_digest
        rt.recycled_reason = reason
        await self._close_runtime(rt)
        await self._connect(rt)
        if rt.state == "connected":
            rt.catalog_digest = digest or rt.catalog_digest
            if self._registry is not None:
                self._register_all(self._registry)
            log.info("MCP server %s recycled (%s)", rt.config.id, reason)

    def due_lifecycle_action(self, rt: _ServerRuntime, now: float) -> Optional[str]:
        """A recycle/keepalive action this server is due, or None.

        Pure decision so `/mcp/diagnostics` (or a test) can ask without acting.
        """
        if rt.state != "connected" or rt.connection is None:
            return None
        reason = should_recycle(
            transport=rt.config.transport,
            now=now,
            connected_at=rt.connection.connected_at,
            last_call_at=rt.connection.last_activity,
            idle_timeout_s=rt.config.idle_timeout_seconds,
            max_lifetime_s=rt.config.max_lifetime_seconds,
        )
        if reason:
            return f"recycle:{reason}"
        interval = rt.config.keepalive_interval
        if interval and rt.connection.last_activity is not None:
            if now - rt.connection.last_activity >= interval:
                return "keepalive"
        return None


__all__ = ["LifecycleMixin"]
