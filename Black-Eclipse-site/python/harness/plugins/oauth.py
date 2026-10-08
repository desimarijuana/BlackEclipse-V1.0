"""Centralized OAuth 2.0 for plugins.

Plugins declare their flow in the manifest; the host owns the token lifecycle so
a plugin never implements credential storage. Supported grants:

  * `authorization_code` with PKCE (S256) — the host returns an authorization URL;
    the browser returns a `code`; the host exchanges it.
  * `device_code` (RFC 8628) — the host returns a user code + verification URI and
    (optionally) polls the token endpoint.
  * `client_credentials` — server-to-server, no user interaction.
  * refresh + revoke.

Tokens (access/refresh/expiry/scope/verifier/state/device code) are stored in the
plugin's **encrypted** secret store, scoped per plugin. `ctx.auth.token()` returns
a valid access token, refreshing transparently and raising `AuthRequired` when
interaction is needed.
"""

from __future__ import annotations

import base64
import hashlib
import secrets as _pysecrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

from .errors import PluginError
from .manifest import AuthenticationSpec

# Encrypted secret keys (never returned by a listing).
K_ACCESS = "oauth:access_token"
K_REFRESH = "oauth:refresh_token"
K_EXPIRES = "oauth:expires_at"
K_TYPE = "oauth:token_type"
K_SCOPE = "oauth:scope"
K_VERIFIER = "oauth:code_verifier"
K_STATE = "oauth:state"
K_DEVICE = "oauth:device_code"
_OAUTH_KEYS = (K_ACCESS, K_REFRESH, K_EXPIRES, K_TYPE, K_SCOPE, K_VERIFIER, K_STATE, K_DEVICE)

_EXPIRY_SKEW_S = 30.0
_PENDING = {"authorization_pending", "slow_down"}


class OAuthError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


class AuthRequired(OAuthError):
    def __init__(self, plugin_id: str, reason: str = "authorization is required") -> None:
        super().__init__(
            "PLUGIN_AUTH_REQUIRED",
            f"plugin {plugin_id!r} needs authorization: {reason}",
            detail={"plugin_id": plugin_id},
        )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_pkce() -> tuple[str, str]:
    verifier = _b64url(_pysecrets.token_bytes(40))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class OAuthClient:
    """Per-plugin OAuth token lifecycle over the encrypted secret store."""

    def __init__(
        self,
        secrets: Any,
        plugin_id: str,
        spec: AuthenticationSpec,
        *,
        transport: Any = None,
        timeout_s: float = 20.0,
    ) -> None:
        self._secrets = secrets
        self._plugin_id = plugin_id
        self._spec = spec
        self._transport = transport
        self._timeout = timeout_s

    # ── credential helpers ───────────────────────────────────────────────────

    def _client_id(self, override: Optional[str] = None) -> Optional[str]:
        return override or self._secrets.get(self._plugin_id, "clientId")

    def _client_secret(self) -> Optional[str]:
        return self._secrets.get(self._plugin_id, "clientSecret")

    def _basic_auth(self, client_id: str, client_secret: Optional[str]) -> tuple[str, str]:
        return (client_id, client_secret or "")

    async def _post(self, url: str, data: dict[str, Any], *, client_id: Optional[str] = None,
                    client_secret: Optional[str] = None) -> dict[str, Any]:
        import httpx  # noqa: PLC0415

        headers = {"Accept": "application/json"}
        auth = None
        body = dict(data)
        if self._spec.token_endpoint_auth_method == "client_secret_basic" and client_id:
            auth = self._basic_auth(client_id, client_secret)
        elif client_id:
            body.setdefault("client_id", client_id)
            if client_secret and self._spec.token_endpoint_auth_method == "client_secret_post":
                body.setdefault("client_secret", client_secret)
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            response = await client.post(url, data=body, headers=headers, auth=auth)
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001 - a non-JSON error body is still an error
            raise OAuthError("PLUGIN_OAUTH_FAILED", f"token endpoint returned HTTP {response.status_code}")
        if response.status_code >= 400 or "error" in payload:
            raise OAuthError(
                "PLUGIN_OAUTH_FAILED",
                f"{payload.get('error', 'oauth_error')}: {payload.get('error_description', '')}".strip(),
                detail={"status": response.status_code},
            )
        return payload

    def _store_tokens(self, payload: dict[str, Any]) -> dict[str, Any]:
        access = payload.get("access_token")
        if not access:
            raise OAuthError("PLUGIN_OAUTH_FAILED", "token response had no access_token")
        self._secrets.set(self._plugin_id, K_ACCESS, str(access))
        if payload.get("refresh_token"):
            self._secrets.set(self._plugin_id, K_REFRESH, str(payload["refresh_token"]))
        self._secrets.set(self._plugin_id, K_TYPE, str(payload.get("token_type", "Bearer")))
        if payload.get("scope"):
            self._secrets.set(self._plugin_id, K_SCOPE, str(payload["scope"]))
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            self._secrets.set(self._plugin_id, K_EXPIRES, str(time.time() + float(expires_in)))
        return self.status()

    # ── token access ─────────────────────────────────────────────────────────

    def _expires_at(self) -> Optional[float]:
        raw = self._secrets.get(self._plugin_id, K_EXPIRES)
        try:
            return float(raw) if raw else None
        except (TypeError, ValueError):
            return None

    def has_access(self) -> bool:
        return bool(self._secrets.get(self._plugin_id, K_ACCESS))

    def is_expired(self) -> bool:
        expires = self._expires_at()
        return expires is not None and time.time() >= (expires - _EXPIRY_SKEW_S)

    async def token(self) -> str:
        """A valid access token, refreshing when possible, else `AuthRequired`."""
        access = self._secrets.get(self._plugin_id, K_ACCESS)
        if access and not self.is_expired():
            return access
        if self._secrets.get(self._plugin_id, K_REFRESH):
            try:
                await self.refresh()
                refreshed = self._secrets.get(self._plugin_id, K_ACCESS)
                if refreshed:
                    return refreshed
            except OAuthError:
                pass
        if access and not self._secrets.get(self._plugin_id, K_REFRESH):
            # No expiry was recorded and no refresh token: use what we have.
            expires = self._expires_at()
            if expires is None:
                return access
        raise AuthRequired(self._plugin_id)

    async def refresh(self) -> dict[str, Any]:
        refresh_token = self._secrets.get(self._plugin_id, K_REFRESH)
        if not refresh_token:
            raise AuthRequired(self._plugin_id, "no refresh token is stored")
        payload = await self._post(
            self._spec.token_url,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            client_id=self._client_id(), client_secret=self._client_secret(),
        )
        # A refresh response may omit a new refresh token; keep the old one.
        if not payload.get("refresh_token"):
            payload["refresh_token"] = refresh_token
        return self._store_tokens(payload)

    # ── flows ────────────────────────────────────────────────────────────────

    async def start(self, *, client_id: Optional[str] = None, scope: str = "") -> dict[str, Any]:
        grant = self._spec.grant
        if grant == "client_credentials":
            payload = await self._post(
                self._spec.token_url,
                {"grant_type": "client_credentials", "scope": scope or " ".join(self._spec.scopes)},
                client_id=self._client_id(client_id), client_secret=self._client_secret(),
            )
            return {"grant": grant, "authorized": True, **self._store_tokens(payload)}
        if grant == "device_code":
            payload = await self._post(
                self._spec.device_authorization_url,
                {"client_id": self._client_id(client_id) or "",
                 "scope": scope or " ".join(self._spec.scopes)},
                client_id=None,
            )
            device_code = str(payload.get("device_code") or "")
            self._secrets.set(self._plugin_id, K_DEVICE, device_code)
            return {
                "grant": grant,
                "authorized": False,
                "userCode": payload.get("user_code"),
                "verificationUri": payload.get("verification_uri") or payload.get("verification_url"),
                "interval": payload.get("interval", 5),
                "expiresIn": payload.get("expires_in"),
            }
        # authorization_code + PKCE
        verifier, challenge = make_pkce()
        state = _b64url(_pysecrets.token_bytes(16))
        self._secrets.set(self._plugin_id, K_VERIFIER, verifier)
        self._secrets.set(self._plugin_id, K_STATE, state)
        params = {
            "response_type": "code",
            "client_id": self._client_id(client_id) or "",
            "redirect_uri": self._spec.redirect_uri or "",
            "scope": scope or " ".join(self._spec.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if self._spec.audience:
            params["audience"] = self._spec.audience
        return {"grant": grant, "authorized": False, "authorizationUrl": f"{self._spec.authorization_url}?{urlencode(params)}",
                "state": state, "redirectUri": self._spec.redirect_uri}

    async def poll_device(self, *, client_id: Optional[str] = None) -> dict[str, Any]:
        device_code = self._secrets.get(self._plugin_id, K_DEVICE)
        if not device_code:
            raise OAuthError("PLUGIN_OAUTH_STATE", "no device authorization is in progress")
        try:
            payload = await self._post(
                self._spec.token_url,
                {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                 "device_code": device_code, "client_id": self._client_id(client_id) or ""},
                client_id=None,
            )
        except OAuthError as exc:
            err = str(exc).split(":")[0].strip()
            if err in _PENDING or "pending" in str(exc).lower() or "slow_down" in str(exc).lower():
                return {"authorized": False, "pending": True, "detail": str(exc)}
            raise
        self._secrets.delete(self._plugin_id, K_DEVICE)
        result = self._store_tokens(payload)
        return {"grant": "device_code", "authorized": True, **result}

    async def complete(self, code: str, state: str = "", *, client_id: Optional[str] = None) -> dict[str, Any]:
        expected_state = self._secrets.get(self._plugin_id, K_STATE)
        if expected_state and state and state != expected_state:
            raise OAuthError("PLUGIN_OAUTH_STATE", "OAuth state did not match; refusing the code")
        verifier = self._secrets.get(self._plugin_id, K_VERIFIER)
        payload = await self._post(
            self._spec.token_url,
            {"grant_type": "authorization_code", "code": code,
             "redirect_uri": self._spec.redirect_uri or "", "code_verifier": verifier or ""},
            client_id=self._client_id(client_id), client_secret=self._client_secret(),
        )
        for key in (K_VERIFIER, K_STATE):
            self._secrets.delete(self._plugin_id, key)
        result = self._store_tokens(payload)
        return {"grant": "authorization_code", "authorized": True, **result}

    # ── status / revoke ──────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        expires = self._expires_at()
        return {
            "pluginId": self._plugin_id,
            "grant": self._spec.grant,
            "authorized": self.has_access(),
            "expired": self.is_expired(),
            "expiresAt": expires,
            "scope": self._secrets.get(self._plugin_id, K_SCOPE),
            "hasRefreshToken": bool(self._secrets.get(self._plugin_id, K_REFRESH)),
        }

    async def revoke(self) -> dict[str, Any]:
        for key in _OAUTH_KEYS:
            try:
                self._secrets.delete(self._plugin_id, key)
            except Exception:  # noqa: BLE001 - clearing is best-effort
                pass
        return {"pluginId": self._plugin_id, "revoked": True}


def is_oauth(manifest: Any) -> bool:
    return bool(manifest is not None and manifest.authentication.type == "oauth2")


__all__ = ["OAuthClient", "OAuthError", "AuthRequired", "make_pkce", "is_oauth"]
