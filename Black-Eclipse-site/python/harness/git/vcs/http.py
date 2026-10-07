"""A minimal, dependency-free HTTPS client for the VCS providers.

The harness ships no HTTP client library it owns (the MCP SDK carries its own).
Rather than add a dependency, the provider layer uses `urllib.request` from the
standard library. This module wraps it with:

  * bounded timeouts and a bounded response size;
  * a token header the caller supplies (held only for the request);
  * a structured `ProviderError` for every HTTP status and network fault, so a
    provider method never raises a bare urllib exception;
  * JSON decode with an honest error when the body is not JSON.

No request or response body is ever logged.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .base import (
    AUTHENTICATION_FAILED, CONFLICT, NETWORK_ERROR, NOT_FOUND, PERMISSION_DENIED,
    PROVIDER_UNAVAILABLE, RATE_LIMITED, VALIDATION_FAILED, ProviderError,
)

DEFAULT_TIMEOUT_S = 30
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
USER_AGENT = "BlackEclipse-Git/1.0"


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str
    url: str

    def json(self) -> Any:
        if not self.body:
            return None
        try:
            return json.loads(self.body)
        except ValueError as exc:
            raise ProviderError(VALIDATION_FAILED, "The service returned an unexpected response.") from exc


def _status_error(status: int, detail: str) -> ProviderError:
    if status in (401,):
        return ProviderError(AUTHENTICATION_FAILED, "The sign-in for this service was not accepted.", status=status)
    if status == 403:
        return ProviderError(PERMISSION_DENIED, "This account does not have permission for that here.", status=status)
    if status == 404:
        return ProviderError(NOT_FOUND, "That was not found on the service.", status=status)
    if status == 409:
        return ProviderError(CONFLICT, "The service reported a conflict.", status=status, recoverable=True)
    if status == 422:
        return ProviderError(VALIDATION_FAILED, "The service rejected the request details.", status=status)
    if status == 429:
        return ProviderError(RATE_LIMITED, "The service asked to slow down; try again shortly.", status=status, recoverable=True)
    if 500 <= status < 600:
        return ProviderError(PROVIDER_UNAVAILABLE, "The service is temporarily unavailable.", status=status, recoverable=True)
    return ProviderError(PROVIDER_UNAVAILABLE, f"The service returned an error ({status}).{detail}", status=status)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never carry an `Authorization` header across a host change.

    `urllib` re-sends the redirected header set on a redirect. Without this, a
    provider (or a proxy) answering with a redirect to another host would receive
    the account token. A cross-host redirect drops the credential; the request is
    still followed (an `https` upgrade on the same host keeps it).
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).netloc.casefold()
        new_host = urllib.parse.urlsplit(newurl).netloc.casefold()
        if old_host != new_host:
            for key in list(new.headers):
                if key.casefold() == "authorization":
                    del new.headers[key]
            for key in list(getattr(new, "unredirected_hdrs", {})):
                if key.casefold() == "authorization":
                    del new.unredirected_hdrs[key]
        return new


_OPENER: Optional[urllib.request.OpenerDirector] = None


def _opener() -> urllib.request.OpenerDirector:
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(_SafeRedirectHandler())
    return _OPENER


class HttpClient:
    """A small authenticated JSON client. One instance per provider."""

    def __init__(self, *, token: str = "", timeout_s: int = DEFAULT_TIMEOUT_S,
                 extra_headers: Optional[dict[str, str]] = None) -> None:
        self._token = token
        self._timeout = timeout_s
        self._headers = dict(extra_headers or {})

    def request(
        self, method: str, url: str, *, data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None, raw: bool = False,
    ) -> HttpResponse:
        body: Optional[bytes] = None
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json",
            **self._headers,
        }
        if headers:
            request_headers.update(headers)
        if self._token and "Authorization" not in request_headers:
            request_headers["Authorization"] = f"Bearer {self._token}"
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url, data=body, method=method.upper(), headers=request_headers)
        try:
            with _opener().open(req, timeout=self._timeout) as response:
                payload = response.read(MAX_RESPONSE_BYTES)
                return HttpResponse(
                    status=response.status,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=payload.decode("utf-8", "replace"),
                    url=response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                raw_body = exc.read(4096).decode("utf-8", "replace")
                if raw_body:
                    detail = f" {raw_body[:300]}"
            except Exception:  # noqa: BLE001
                pass
            raise _status_error(exc.code, detail) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise ProviderError(NETWORK_ERROR, "The service could not be reached.", recoverable=True) from exc

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("DELETE", url, **kwargs)

    @staticmethod
    def quote(*parts: str) -> str:
        return "/".join(urllib.parse.quote(str(p), safe="") for p in parts)


__all__ = ["DEFAULT_TIMEOUT_S", "HttpClient", "HttpResponse", "MAX_RESPONSE_BYTES"]
