"""Refuse model endpoints that point inside the host or the private network.

A user-supplied OpenAI-compatible base URL is an outbound request made with the
user's credentials attached. The classic mistakes: a typo that points at
`169.254.169.254` (cloud metadata), `localhost:11434` copied from a local setup
into a cloud profile, or a resolvable name that answers with a private address.

Two levels, deliberately separate:

  * **Always on:** an IP *literal* that is private, loopback, link-local,
    multicast, reserved or unspecified is refused. No DNS, no network, no
    configuration — `http://127.0.0.1` typed as a remote endpoint is a mistake.
  * **Opt-in (``BE_ENDPOINT_PINNING=1``):** hostnames are resolved and every
    answer must be public. This closes DNS rebinding *at validation time*; the
    connect-time pinning (connecting to the checked address) is NOT implemented
    here and the docstring says so rather than implying more than it does.

Local model servers are a first-class case: `allow_private=True` (used when the
URL itself is loopback, or when local-only privacy mode is on) permits them.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlsplit


class EndpointBlocked(ValueError):
    """The endpoint is not allowed. `code` is stable for callers and tests."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedEndpoint:
    url: str
    host: str
    port: Optional[int]
    addresses: tuple[str, ...]


def is_public_address(value: str) -> bool:
    """Whether an IP literal is a globally routable public address."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if address.is_private or address.is_loopback or address.is_link_local:
        return False
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        return False
    if getattr(address, "is_site_local", False):
        return False
    return True


def pinning_enabled() -> bool:
    return str(os.environ.get("BE_ENDPOINT_PINNING", "")).strip().lower() in {
        "1", "on", "true", "yes",
    }


def _resolve(host: str, port: Optional[int]) -> tuple[str, ...]:
    infos = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    return tuple(sorted({info[4][0] for info in infos}))


def resolve_public_endpoint(
    url: str,
    *,
    allow_private: bool = False,
    resolver: Optional[Iterable[str]] = None,
) -> ResolvedEndpoint:
    """Validate `url` and return its resolved addresses.

    `resolver` lets a caller (or a test) supply the addresses instead of DNS.
    Raises `EndpointBlocked` with a stable code on any refusal.
    """
    raw = str(url or "").strip()
    if not raw:
        raise EndpointBlocked("EMPTY_URL", "the endpoint URL is empty")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise EndpointBlocked("BAD_SCHEME", f"scheme {parts.scheme!r} is not http(s)")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise EndpointBlocked("NO_HOST", "the endpoint URL has no host")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not allow_private and not is_public_address(str(literal)):
            raise EndpointBlocked(
                "PRIVATE_ADDRESS",
                f"{host} is a private/loopback/link-local address",
            )
        return ResolvedEndpoint(url=raw, host=host, port=parts.port, addresses=(str(literal),))

    if resolver is None:
        if not pinning_enabled():
            # No DNS work unless asked: an unresolvable host must not break a
            # provider that would resolve at connect time.
            return ResolvedEndpoint(url=raw, host=host, port=parts.port, addresses=())
        try:
            addresses = _resolve(host, parts.port)
        except OSError as exc:
            raise EndpointBlocked("DNS_FAILED", f"could not resolve {host}: {exc}") from exc
    else:
        addresses = tuple(sorted(set(resolver)))

    if not addresses:
        raise EndpointBlocked("DNS_FAILED", f"no addresses for {host}")
    if not allow_private:
        blocked = [address for address in addresses if not is_public_address(address)]
        if blocked:
            raise EndpointBlocked(
                "PRIVATE_RESOLUTION",
                f"{host} resolves to non-public address(es): {', '.join(blocked)}",
            )
    return ResolvedEndpoint(url=raw, host=host, port=parts.port, addresses=addresses)


def validate_endpoint(url: str, *, allow_private: bool = False, resolver=None) -> str:
    """Return `url` unchanged when allowed; raise `EndpointBlocked` otherwise."""
    return resolve_public_endpoint(url, allow_private=allow_private, resolver=resolver).url


__all__ = [
    "EndpointBlocked",
    "ResolvedEndpoint",
    "is_public_address",
    "pinning_enabled",
    "resolve_public_endpoint",
    "validate_endpoint",
]
