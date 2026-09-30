"""OAuth login/logout mixin for `MCPManager` (Phase 6.1 pure extraction).

Device-code (RFC 8628) login and credential clearing. Pure move out of
`manager.py` with no behavior change; `MCPManager` inherits this mixin. The mixin
uses `self._runtimes`, `self._bridge_fetch` and `self._close_runtime`, which the
manager owns. Tokens are stored through the injected vault bridge and are never
returned by these methods.
"""

from __future__ import annotations

from typing import Any, Optional

from .runtime import _ServerRuntime


class OAuthFlowMixin:
    async def oauth_login(
        self,
        server_id: str,
        *,
        client_id: Optional[str] = None,
        scope: str = "",
        endpoints: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Run a device-code (RFC 8628) login and store the token in the vault.

        Offline-testable: `endpoints` may inject `metadata`, `device`, and
        `token` URLs (used by the fixture). A missing `bridge_fetch` or a token
        that cannot be encrypted is a hard error, never a plaintext fallback.
        """
        rt = self._runtimes.get(server_id)
        if rt is None:
            return {"success": False, "reason": "server not found"}
        if self._bridge_fetch is None:
            return {"success": False, "reason": "vault bridge is unavailable"}
        from .oauth import (
            OAuthError,
            device_authorization_request,
            poll_device_token,
        )

        client_id = client_id or f"black-eclipse-{server_id}"
        try:
            endpoints = endpoints or await self._discover_oauth_endpoints(rt)
            device = await device_authorization_request(
                device_authorization_endpoint=endpoints["device"],
                client_id=client_id,
                scope=scope,
                http_post=self._oauth_http_post,
            )
            token = await poll_device_token(
                token_endpoint=endpoints["token"],
                client_id=client_id,
                device_code=device.device_code,
                interval=device.interval,
                expires_in=device.expires_in,
                http_post=self._oauth_http_post,
            )
            await self._bridge_fetch("mcp_oauth_token_set", {
                "serverId": server_id,
                "accessToken": token.get("access_token"),
                "tokenType": token.get("token_type"),
                "refreshToken": token.get("refresh_token"),
                "scope": token.get("scope"),
                "clientId": client_id,
            })
        except OAuthError as exc:
            return {"success": False, "reason": str(exc), "code": exc.code}
        return {
            "success": True,
            "serverId": server_id,
            "verificationUri": device.verification_uri,
            "userCode": device.user_code,
        }

    async def _discover_oauth_endpoints(self, rt: _ServerRuntime) -> dict[str, str]:
        import httpx as _httpx

        base = (rt.config.url or "").rstrip("/")
        meta_url = f"{base}/.well-known/oauth-authorization-server"
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(meta_url)
            resp.raise_for_status()
            metadata = resp.json()
        return {
            "metadata": meta_url,
            "device": metadata["device_authorization_endpoint"],
            "token": metadata["token_endpoint"],
        }

    async def _oauth_http_post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST a form-encoded OAuth body; return JSON (error bodies included)."""
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=body)
            try:
                return resp.json()
            except Exception:  # noqa: BLE001
                return {"error": f"oauth_http_{resp.status_code}"}

    async def oauth_logout(self, server_id: str) -> dict[str, Any]:
        """Clear a server's stored credentials and disconnect it.

        The server stays configured; only its token is removed, so it is
        disconnected until a new login.
        """
        rt = self._runtimes.get(server_id)
        if rt is None:
            return {"success": False, "reason": "server not found"}
        removed = False
        if self._bridge_fetch is not None:
            try:
                payload = await self._bridge_fetch("mcp_oauth_token_clear", {"serverId": server_id})
                removed = bool((payload or {}).get("removed"))
            except Exception:  # noqa: BLE001
                removed = False
        await self._close_runtime(rt)
        if rt.config.enabled:
            rt.state = "pending"
            rt.diagnostic = rt.redact("credentials cleared; log in again to reconnect")
        return {"success": True, "serverId": server_id, "removed": removed}


__all__ = ["OAuthFlowMixin"]
