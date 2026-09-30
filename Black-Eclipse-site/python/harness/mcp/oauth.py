"""OAuth 2.1 for remote MCP servers (Phase 6, Milestone 3).

Two paths, both offline-testable:

  * **Authorization code + PKCE** — delegated to the MCP SDK's own
    `mcp.client.auth.OAuthClientProvider` (which implements discovery, dynamic
    client registration, PKCE and refresh). We supply a `TokenStorage` that reads
    and writes through the authenticated vault bridge, so a token is never
    persisted in `mcp-servers.json`, a log, an event or a response.
  * **Device code (RFC 8628)** — the SDK does not implement it, so a minimal
    flow lives here: request a device code, poll the token endpoint handling
    `authorization_pending` / `slow_down`, bounded by the advertised expiry.

If neither path can store a token encrypted, the flow fails loudly rather than
falling back to plaintext.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

log = logging.getLogger("harness.mcp.oauth")

# The device-flow polling floor (RFC 8628 §3.5).
DEFAULT_POLL_INTERVAL_S = 5
SLOW_DOWN_BUMP_S = 5


class OAuthError(Exception):
    """A structured OAuth failure with an actionable code."""

    def __init__(self, message: str, *, code: str = "mcp_oauth_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: Optional[str]
    expires_in: int
    interval: int


class BridgeTokenStore:
    """A `TokenStorage` backed by the runtime's authenticated vault bridge.

    The bridge is an async `(capability, params) -> dict`. Tokens are written
    ENCRYPTED by the TS side (`mcp_oauth_token_set`) and read back
    (`mcp_oauth_token_get`). Nothing is cached in a log or a file.
    """

    def __init__(self, server_id: str, fetch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.server_id = server_id
        self._fetch = fetch

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        payload = await self._fetch("mcp_oauth_token_get", {"serverId": self.server_id})
        token = (payload or {}).get("token")
        if not isinstance(token, dict) or not token.get("accessToken"):
            return None
        return OAuthToken(
            access_token=token["accessToken"],
            token_type=token.get("tokenType") or "Bearer",
            refresh_token=token.get("refreshToken"),
            scope=token.get("scope"),
        )

    async def set_tokens(self, tokens) -> None:
        await self._fetch("mcp_oauth_token_set", {
            "serverId": self.server_id,
            "accessToken": tokens.access_token,
            "tokenType": getattr(tokens, "token_type", None),
            "refreshToken": getattr(tokens, "refresh_token", None),
            "expiresAt": _expiry_epoch(getattr(tokens, "expires_in", None)),
            "scope": getattr(tokens, "scope", None),
        })

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        payload = await self._fetch("mcp_oauth_token_get", {"serverId": self.server_id})
        token = (payload or {}).get("token") or {}
        if not token.get("clientId"):
            return None
        return OAuthClientInformationFull(client_id=token["clientId"])

    async def set_client_info(self, client_info) -> None:
        # Preserve the access token when recording only client info.
        existing = await self._fetch("mcp_oauth_token_get", {"serverId": self.server_id})
        token = (existing or {}).get("token") or {}
        await self._fetch("mcp_oauth_token_set", {
            "serverId": self.server_id,
            "accessToken": token.get("accessToken") or "",
            "refreshToken": token.get("refreshToken"),
            "clientId": getattr(client_info, "client_id", None),
            "issuer": getattr(client_info, "issuer", None),
        })


def _expiry_epoch(expires_in: Any) -> Optional[int]:
    try:
        if expires_in is None:
            return None
        return int(time.time()) + int(expires_in)
    except (TypeError, ValueError):
        return None


def build_oauth_provider(
    server_id: str,
    url: str,
    fetch: Any,
    redirect_uri: str,
    *,
    redirect_handler: Any = None,
    callback_handler: Any = None,
):
    """Build the SDK's OAuth provider with a bridge-backed token store.

    The redirect/callback handlers are supplied by the caller (a loopback
    callback server for the interactive path, or a test harness). The provider
    performs discovery, registration and refresh.
    """
    from mcp.shared.auth import OAuthClientMetadata
    from mcp.client.auth import OAuthClientProvider

    client_metadata = OAuthClientMetadata(
        client_name="BlackEclipse",
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    store = BridgeTokenStore(server_id, fetch)
    return OAuthClientProvider(
        url,
        client_metadata=client_metadata,
        storage=store,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )


async def discover_device_authorization_endpoints(
    fetch: Any, metadata_url: str
) -> dict[str, Any]:
    """Fetch OAuth authorization-server metadata and require a device endpoint."""
    response = await fetch(metadata_url)
    if not isinstance(response, dict):
        raise OAuthError("OAuth metadata was not an object", code="mcp_oauth_metadata_invalid")
    if not response.get("device_authorization_endpoint"):
        raise OAuthError(
            "the authorization server does not advertise device authorization",
            code="mcp_oauth_device_unsupported",
        )
    return response


async def device_authorization_request(
    *,
    device_authorization_endpoint: str,
    client_id: str,
    scope: str,
    http_post: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> DeviceCode:
    """RFC 8628 §3.1/3.2: request a device + user code."""
    body = {"client_id": client_id}
    if scope:
        body["scope"] = scope
    payload = await http_post(device_authorization_endpoint, body)
    if not payload.get("device_code") or not payload.get("user_code"):
        raise OAuthError("device authorization response was missing a code",
                         code="mcp_oauth_device_invalid")
    return DeviceCode(
        device_code=str(payload["device_code"]),
        user_code=str(payload["user_code"]),
        verification_uri=str(payload.get("verification_uri") or ""),
        verification_uri_complete=payload.get("verification_uri_complete"),
        expires_in=int(payload.get("expires_in") or 300),
        interval=max(1, int(payload.get("interval") or DEFAULT_POLL_INTERVAL_S)),
    )


async def poll_device_token(
    *,
    token_endpoint: str,
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    http_post: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """RFC 8628 §3.4/3.5: poll until the token, a denial, or expiry.

    Handles `authorization_pending` (keep polling) and `slow_down` (increase the
    interval). A `access_denied`/`expired_token` is an actionable terminal error.
    """
    deadline = time.monotonic() + max(1, expires_in)
    wait = max(1, interval)
    while time.monotonic() < deadline:
        await sleep(wait)
        try:
            payload = await http_post(token_endpoint, {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id,
            })
        except OAuthError:
            raise
        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            wait += SLOW_DOWN_BUMP_S
            continue
        if error in ("access_denied", "expired_token"):
            raise OAuthError(
                f"device authorization {error}: request a new login",
                code=f"mcp_oauth_{error}",
            )
        if payload.get("access_token"):
            return payload
        if error:
            raise OAuthError(f"device authorization failed: {error}", code="mcp_oauth_device_failed")
    raise OAuthError("device authorization expired before approval", code="mcp_oauth_device_expired")


__all__ = [
    "OAuthError",
    "DeviceCode",
    "BridgeTokenStore",
    "build_oauth_provider",
    "discover_device_authorization_endpoints",
    "device_authorization_request",
    "poll_device_token",
    "DEFAULT_POLL_INTERVAL_S",
]
