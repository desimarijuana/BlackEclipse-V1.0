"""Bounded, SSRF-checked outbound HTTP for graph integration nodes.

This is the ONE place a workflow node makes an HTTP request. It exists so the
safety properties are testable in isolation and shared by every network node:

* the URL is checked on the initial request **and on every redirect hop**
  (``urllib`` follows redirects by default; doing that unchecked let a public
  URL redirect into loopback / link-local address space);
* redirects are opt-in, capped, and may not downgrade HTTPS to HTTP;
* responses are capped (fail or truncate) and requests are capped;
* retries are opt-in and only applied to idempotent methods unless explicitly
  allowed, with a bounded backoff and ``Retry-After`` support;
* credential references (``header -> ENV_VAR``) are resolved here and never
  logged or returned.

Determinism note: the engine is otherwise pure; this module is deliberately
effectful and only runs behind an explicit network grant.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from ..mcp import ssrf

MAX_REQUEST_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 1_000_000
MAX_HEADERS = 20
MAX_QUERY_KEYS = 50
MAX_REDIRECTS = 5
MAX_RETRIES = 3

_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

_FORBIDDEN_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "upgrade",
})
# Credentials have no safe place in a node's config. They may only come from a
# credential REFERENCE (`credentialEnvJson`) so the value is resolved at run
# time and never stored or echoed.
_SENSITIVE_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "x-auth-token", "x-access-token",
})
_SENSITIVE_RESPONSE_HEADERS = frozenset({
    "set-cookie", "set-cookie2", "www-authenticate", "proxy-authenticate",
})
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_RETRYABLE_STATUS = frozenset({408, 429})


class HttpRequestError(ValueError):
    """A bounded, user-facing HTTP failure (never carries a credential)."""


@dataclass
class HttpResult:
    status: int
    ok: bool
    body: Any
    headers: dict[str, str]
    content_type: str
    duration_ms: int
    truncated: bool
    url: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn every 3xx into an HTTPError so redirects can be checked one by one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


# Module-level opener so tests can inject a deterministic transport without
# touching the real network. Never replaced in production.
_OPENER = urllib.request.build_opener(_NoRedirect())


# ── URL / header / body helpers ───────────────────────────────────────────────


def check_url(raw_url: str) -> str:
    """SSRF-check a graph URL. Loopback is refused even though the MCP bridge
    allows it for local test servers: a workflow must never probe the host."""
    url = str(raw_url or "").strip()
    if not url:
        raise HttpRequestError("url is required")
    safe, reason = ssrf.check_outbound_url(url)
    if not safe:
        raise HttpRequestError(f"blocked URL: {reason}")
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
        raise HttpRequestError("loopback URLs are not allowed from a graph HTTP node")
    return url


def redact_url(raw_url: str) -> str:
    """A log-safe URL: scheme + host + path, no query or fragment."""
    try:
        parsed = urllib.parse.urlsplit(str(raw_url or ""))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return "(invalid url)"


def plain_headers(raw: str) -> dict[str, str]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpRequestError(f"headersJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HttpRequestError("headersJson must be a JSON object")
    if len(parsed) > MAX_HEADERS:
        raise HttpRequestError(f"headersJson is bounded to {MAX_HEADERS} headers")
    out: dict[str, str] = {}
    for name, value in parsed.items():
        header = str(name).strip()
        if not _HEADER_NAME.match(header):
            raise HttpRequestError(f"invalid header name {header!r}")
        lowered = header.lower()
        if lowered in _FORBIDDEN_HEADERS:
            raise HttpRequestError(f"header {header!r} is managed by the transport")
        if lowered in _SENSITIVE_HEADERS:
            raise HttpRequestError(
                f"header {header!r} is refused: credentials and cookies must use "
                "credentialEnvJson"
            )
        if not isinstance(value, str):
            raise HttpRequestError(f"header {header!r} must be a string")
        if len(value) > 1_000 or "\r" in value or "\n" in value:
            raise HttpRequestError(f"header {header!r} has an invalid value")
        out[header] = value
    return out


def credential_headers(raw: str, env: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Resolve `header -> ENV_VAR` references from the runtime environment."""
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpRequestError(f"credentialEnvJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HttpRequestError("credentialEnvJson must be a JSON object")
    if len(parsed) > 10:
        raise HttpRequestError("credentialEnvJson is bounded to 10 headers")
    source = env if env is not None else os.environ
    out: dict[str, str] = {}
    for name, variable in parsed.items():
        header = str(name).strip()
        if not _HEADER_NAME.match(header):
            raise HttpRequestError(f"invalid credential header name {header!r}")
        if header.lower() in _FORBIDDEN_HEADERS:
            raise HttpRequestError(f"header {header!r} is managed by the transport")
        env_name = str(variable or "").strip()
        if not _ENV_NAME.match(env_name):
            raise HttpRequestError(
                f"credentialEnvJson for {header!r} must name an environment variable"
            )
        value = source.get(env_name)
        if not value:
            raise HttpRequestError(
                f"credential variable {env_name} for header {header!r} is not set "
                "in the runtime environment"
            )
        if len(value) > 4_000 or "\r" in value or "\n" in value:
            raise HttpRequestError(f"credential variable {env_name} has an invalid value")
        out[header] = value
    return out


def merge_headers(plain: dict[str, str], credentials: dict[str, str]) -> dict[str, str]:
    overlap = {name.lower() for name in plain} & {name.lower() for name in credentials}
    if overlap:
        raise HttpRequestError(
            "a header cannot be set by both headersJson and credentialEnvJson: "
            + ", ".join(sorted(overlap))
        )
    headers = {
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        "User-Agent": "BlackEclipse-Graph/1.0",
    }
    headers.update(plain)
    headers.update(credentials)
    return headers


def apply_query(url: str, raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return url
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpRequestError(f"queryJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HttpRequestError("queryJson must be a JSON object")
    if len(parsed) > MAX_QUERY_KEYS:
        raise HttpRequestError(f"queryJson is bounded to {MAX_QUERY_KEYS} keys")
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    for key, value in parsed.items():
        name = str(key)
        if value is None:
            continue
        if isinstance(value, bool):
            pairs.append((name, "true" if value else "false"))
        elif isinstance(value, (str, int, float)):
            pairs.append((name, str(value)))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    raise HttpRequestError(f"queryJson value for {name!r} must be scalar")
                pairs.append((name, str(item)))
        else:
            raise HttpRequestError(f"queryJson value for {name!r} must be scalar or a list")
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        urllib.parse.urlencode(pairs, doseq=True), parts.fragment,
    ))


def encode_body(payload: Any, mode: str) -> tuple[Optional[bytes], Optional[str]]:
    if payload is None:
        return None, None
    mode = (mode or "json").strip().lower()
    if mode == "text":
        if not isinstance(payload, str):
            raise HttpRequestError("bodyMode=text requires a string body")
        data = payload.encode("utf-8")
        content_type = "text/plain; charset=utf-8"
    elif mode == "form":
        if not isinstance(payload, dict):
            raise HttpRequestError("bodyMode=form requires an object body")
        flat: list[tuple[str, str]] = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                raise HttpRequestError(
                    f"bodyMode=form value for {key!r} must be scalar (flat form only)"
                )
            if value is not None:
                flat.append((str(key), str(value)))
        data = urllib.parse.urlencode(flat).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    elif mode == "json":
        try:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise HttpRequestError(f"request body is not JSON-serializable: {exc}") from exc
        content_type = "application/json"
    else:
        raise HttpRequestError(f"unsupported bodyMode {mode!r}")
    if len(data) > MAX_REQUEST_BYTES:
        raise HttpRequestError(f"request body exceeds {MAX_REQUEST_BYTES} bytes")
    return data, content_type


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """`sha256=<hex>` over ``"<timestamp>.<body>"`` (the receiver recomputes it)."""
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body,
                   hashlib.sha256)
    return "sha256=" + mac.hexdigest()


# ── Response helpers ──────────────────────────────────────────────────────────


def _header_items(headers: Any) -> list[tuple[str, str]]:
    items = getattr(headers, "items", None)
    if callable(items):
        return [(str(k), str(v)) for k, v in items()]
    return []


def _header(headers: Any, name: str) -> Optional[str]:
    lowered = name.lower()
    for key, value in _header_items(headers):
        if key.lower() == lowered:
            return value
    return None


def _content_type(headers: Any) -> str:
    getter = getattr(headers, "get_content_type", None)
    if callable(getter):
        return str(getter() or "")
    return (_header(headers, "content-type") or "").split(";")[0].strip()


def response_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _header_items(headers):
        lowered = key.lower()
        if lowered in _SENSITIVE_RESPONSE_HEADERS:
            continue
        if len(out) >= MAX_HEADERS or len(value) > 2_000:
            continue
        out[lowered] = value
    return out


def parse_body(raw: bytes, content_type: str, response_type: str) -> Any:
    text = raw.decode("utf-8", errors="replace")
    mode = (response_type or "auto").strip().lower()
    looks_json = "json" in content_type.lower() or text.lstrip().startswith(("{", "["))
    if mode == "json" or (mode == "auto" and looks_json):
        try:
            return json.loads(text) if text.strip() else None
        except json.JSONDecodeError as exc:
            if mode == "json":
                raise HttpRequestError(f"response is not valid JSON: {exc}") from exc
    return text


def _retry_after_seconds(headers: Any) -> Optional[float]:
    raw = _header(headers, "retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime  # noqa: PLC0415
            when = parsedate_to_datetime(raw)
            return max(0.0, when.timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def _send(
    request: urllib.request.Request, timeout_s: float, cap: int,
) -> tuple[int, bytes, Any, bool]:
    try:
        response = _OPENER.open(request, timeout=timeout_s)
    except urllib.error.HTTPError as exc:
        headers = exc.headers
        try:
            raw = exc.read(cap + 1)
        finally:
            exc.close()
        return int(exc.code), raw or b"", headers, False
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise HttpRequestError(f"HTTP request timed out after {int(timeout_s * 1000)} ms") from exc
        raise HttpRequestError(f"network error: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise HttpRequestError(f"HTTP request timed out after {int(timeout_s * 1000)} ms") from exc
    with response:
        status = int(getattr(response, "status", 200))
        raw = response.read(cap + 1)
        return status, raw, response.headers, False


def _one_attempt(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    data: Optional[bytes],
    content_type: Optional[str],
    timeout_s: float,
    follow_redirects: bool,
    max_redirects: int,
    max_response_bytes: int,
    on_oversize: str,
    response_type: str,
) -> HttpResult:
    started = time.monotonic()
    current_url = url
    current_method = method
    current_data = data
    current_headers = dict(headers)
    if content_type and current_data is not None:
        current_headers["Content-Type"] = content_type

    for hop in range(max_redirects + 1):
        current_url = check_url(current_url)
        request = urllib.request.Request(
            current_url, data=current_data, method=current_method, headers=current_headers,
        )
        status, raw, raw_headers, _ = _send(request, timeout_s, int(max_response_bytes))
        if status in _REDIRECT_CODES and follow_redirects:
            location = _header(raw_headers, "location")
            if not location:
                break
            if hop >= max_redirects:
                raise HttpRequestError(f"too many redirects (limit {max_redirects})")
            target = urllib.parse.urljoin(current_url, location)
            before = urllib.parse.urlparse(current_url)
            after = urllib.parse.urlparse(target)
            if before.scheme == "https" and after.scheme == "http":
                raise HttpRequestError("refusing an HTTPS -> HTTP redirect downgrade")
            if status == 303 or (status in (301, 302) and current_method == "POST"):
                current_method = "GET"
                current_data = None
                current_headers.pop("Content-Type", None)
            current_url = target
            continue

        if len(raw) > max_response_bytes:
            if on_oversize == "truncate":
                raw = raw[:max_response_bytes]
                truncated = True
            else:
                raise HttpRequestError(f"response exceeds {max_response_bytes} bytes")
        else:
            truncated = False
        text_type = _content_type(raw_headers)
        body = parse_body(raw, text_type, response_type)
        return HttpResult(
            status=status,
            ok=200 <= status < 300,
            body=body,
            headers=response_headers(raw_headers),
            content_type=text_type,
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=truncated,
            url=current_url,
        )

    raise HttpRequestError("redirect response had no Location header")


def _is_retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUS or 500 <= status < 600


def request(
    *,
    url: str,
    method: str = "GET",
    query_json: str = "",
    headers_json: str = "",
    credential_env_json: str = "",
    payload: Any = None,
    body_json: str = "",
    body_mode: str = "json",
    response_type: str = "auto",
    max_response_bytes: int = MAX_RESPONSE_BYTES,
    on_oversize: str = "error",
    follow_redirects: bool = False,
    max_redirects: int = 3,
    fail_on_http_error: bool = False,
    retries: int = 0,
    retry_backoff_ms: int = 500,
    retry_unsafe: bool = False,
    timeout_ms: int = 10_000,
) -> HttpResult:
    method = str(method or "GET").strip().upper()
    if method not in _ALLOWED_METHODS:
        raise HttpRequestError(f"unsupported HTTP method {method!r}")
    if max_response_bytes < 1 or max_response_bytes > 10_000_000:
        raise HttpRequestError("maxResponseBytes must be between 1 and 10,000,000")
    if on_oversize not in ("error", "truncate"):
        raise HttpRequestError("onOversize must be error or truncate")
    if retries < 0 or retries > MAX_RETRIES:
        raise HttpRequestError(f"retries must be between 0 and {MAX_RETRIES}")
    retry_backoff_ms = max(100, min(10_000, int(retry_backoff_ms)))
    if max_redirects < 0 or max_redirects > MAX_REDIRECTS:
        raise HttpRequestError(f"maxRedirects must be between 0 and {MAX_REDIRECTS}")
    try:
        timeout_s = max(1.0, min(int(timeout_ms), 60_000) / 1000.0)
    except (TypeError, ValueError) as exc:
        raise HttpRequestError("timeoutMs must be a whole number") from exc

    target = apply_query(check_url(url), query_json)
    plain = plain_headers(headers_json)
    credentials = credential_headers(credential_env_json)
    headers = merge_headers(plain, credentials)

    body = payload
    if body is None:
        raw_body = str(body_json or "").strip()
        if raw_body:
            try:
                body = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise HttpRequestError(f"bodyJson is not valid JSON: {exc}") from exc
    data, content_type = encode_body(body, body_mode)
    if data is not None and method in ("GET", "HEAD", "OPTIONS"):
        data, content_type = None, None

    attempts_allowed = retries + 1
    can_retry = method in _IDEMPOTENT_METHODS or retry_unsafe
    attempt = 0
    while True:
        try:
            result = _one_attempt(
                url=target, method=method, headers=headers, data=data,
                content_type=content_type, timeout_s=timeout_s,
                follow_redirects=follow_redirects, max_redirects=max_redirects,
                max_response_bytes=int(max_response_bytes),
                on_oversize=on_oversize, response_type=response_type,
            )
        except HttpRequestError:
            if can_retry and attempt + 1 < attempts_allowed:
                time.sleep(min(10.0, retry_backoff_ms * (2 ** attempt) / 1000.0))
                attempt += 1
                continue
            raise
        if _is_retryable_status(result.status) and can_retry and attempt + 1 < attempts_allowed:
            wait = min(10.0, retry_backoff_ms * (2 ** attempt) / 1000.0)
            retry_after = _retry_after_seconds(result.headers)
            if retry_after is not None:
                wait = min(10.0, retry_after)
            time.sleep(wait)
            attempt += 1
            continue
        if fail_on_http_error and result.status >= 400:
            preview = result.body
            if not isinstance(preview, str):
                try:
                    preview = json.dumps(preview, sort_keys=True)
                except (TypeError, ValueError):
                    preview = str(preview)
            preview = (preview or "")[:300]
            raise HttpRequestError(
                f"HTTP {result.status} from {redact_url(result.url)}"
                + (f": {preview}" if preview else "")
            )
        return result
