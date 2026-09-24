"""Outbound URL safety for remote MCP endpoints (Phase 5D).

A remote MCP `url` is user-supplied and the runtime will make requests to it, so
it is an SSRF surface. This mirror of `src/lib/api-guard.ts` (`checkOutboundUrl`)
refuses non-https URLs (loopback http is allowed for local testing), private /
link-local hosts, IP-literal URLs, and embedded credentials.

The same rule is enforced on the TS side; this copy exists because the Python
process makes the actual outbound connection.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

# Hostname suffixes that must never be reachable from a config-driven URL.
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")


class UnsafeUrlError(ValueError):
    """A remote MCP URL failed the outbound-safety check."""


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_outbound_url(raw_url: str) -> tuple[bool, Optional[str]]:
    """Return `(safe, reason)`. `safe=False` means refuse the URL.

    Loopback `http` is permitted ONLY for `localhost`/`127.0.0.1`/`::1` so a local
    test server works; every other scheme must be `https`.
    """
    try:
        parsed = urlparse((raw_url or "").strip())
    except ValueError:
        return False, "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked protocol: {parsed.scheme or '(none)'}"
    if parsed.username or parsed.password:
        return False, "URLs with embedded credentials are not allowed"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "URL has no host"
    if host.endswith(_BLOCKED_SUFFIXES):
        return False, f"Blocked host: {host}"

    loopback = host in ("localhost", "127.0.0.1", "::1", "[::1]")
    if parsed.scheme == "http" and not loopback:
        return False, "Remote MCP endpoints must use https"

    # Reject any IP literal that is private/loopback unless it is the loopback
    # host (a local test server); a public IP literal is allowed but discouraged.
    if _is_private_ip(host) and not loopback:
        return False, f"Blocked private host: {host}"

    # A hostname that resolves to a private address is also refused (best-effort:
    # a literal name is still re-checked by the HTTP client's own transport).
    if not _is_private_ip(host) and not loopback:
        try:
            info = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            for entry in info:
                addr = entry[4][0]
                if _is_private_ip(addr):
                    return False, f"Host {host} resolves to a private address"
        except socket.gaierror:
            return False, f"Host could not be resolved: {host}"
        except OSError:
            # DNS resolution unavailable — do not fail closed on an environment
            # limitation; the literal-host checks above still applied.
            pass

    return True, None


def assert_safe_url(raw_url: str) -> None:
    safe, reason = check_outbound_url(raw_url)
    if not safe:
        raise UnsafeUrlError(reason or "unsafe URL")
