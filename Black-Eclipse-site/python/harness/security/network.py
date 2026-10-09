"""Network policy engine — default-deny egress with SSRF / rebinding protection.

The engine answers one question: may this outbound request proceed? It defaults to
DENY. Rules match on domain / subdomain / IP / CIDR / port / protocol / HTTP method
/ URL path / direction, and an allow requires an explicit matching rule.

It reuses the canonical SSRF guard (`mcp.ssrf.check_outbound_url`) rather than
re-implementing private-address logic, and additionally pins the DNS resolution so
a rebinding host cannot slip between the check and the connection (the caller
passes the pinned IP to its transport when one is provided).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from .models import Decision

_DEFAULT_SCHEMES = {"https"}
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


@dataclass(frozen=True)
class NetworkRule:
    direction: str = "egress"          # egress | ingress
    host: str = ""                     # domain / subdomain / IP / CIDR; empty = any
    port: Optional[int] = None
    protocol: Optional[str] = None     # http | https | ws | wss | tcp
    method: Optional[str] = None       # GET | POST | …
    path: Optional[str] = None         # glob
    verdict: str = "deny"              # allow | deny | approval
    reason: str = ""

    def matches(self, *, direction: str, host: str, ip: Optional[str], port: Optional[int],
                protocol: str, method: str, path: str) -> bool:
        if self.direction != "*" and self.direction != direction:
            return False
        if self.port is not None and self.port != port:
            return False
        if self.protocol and self.protocol.lower() != protocol.lower():
            return False
        if self.method and self.method.upper() != (method or "").upper():
            return False
        if self.path and not _glob(self.path, path):
            return False
        return self._host_matches(host, ip)

    def _host_matches(self, host: str, ip: Optional[str]) -> bool:
        if not self.host or self.host in ("*", "**"):
            return True
        candidate = str(self.host).strip().lower()
        if "/" in candidate:
            # CIDR
            if not ip:
                return False
            try:
                return ipaddress.ip_address(ip) in ipaddress.ip_network(candidate, strict=False)
            except ValueError:
                return False
        try:
            ipaddress.ip_address(candidate)
            return ip is not None and ip == candidate
        except ValueError:
            pass
        host = (host or "").lower()
        if candidate.startswith("*."):
            suffix = candidate[2:]
            return host == suffix or host.endswith("." + suffix)
        # A bare domain also matches its subdomains (documented, intentional).
        return host == candidate or host.endswith("." + candidate)


def _glob(pattern: str, value: str) -> bool:
    import fnmatch

    return fnmatch.fnmatchcase(value or "", pattern or "*")


class NetworkDenied(Exception):
    def __init__(self, reason: str, host: str = "") -> None:
        self.reason = reason
        self.host = host
        super().__init__(reason)


class NetworkPolicyEngine:
    """Evaluate egress policy. Pure decisions; no sockets are opened here."""

    def __init__(
        self,
        rules: Optional[Iterable[NetworkRule]] = None,
        *,
        default: str = "deny",
        allow_loopback: bool = False,
        allow_schemes: Optional[Iterable[str]] = None,
    ) -> None:
        self._rules: tuple[NetworkRule, ...] = tuple(rules or ())
        self._default = default if default in ("allow", "deny", "approval") else "deny"
        self._allow_loopback = allow_loopback
        self._schemes = set(allow_schemes or _DEFAULT_SCHEMES)
        self._denials = 0

    @property
    def version(self) -> int:
        return len(self._rules)

    def add_rule(self, rule: NetworkRule, *, admin: bool = False) -> None:
        if not admin:
            raise PermissionError("network policy may only be changed by an administrator")
        self._rules = self._rules + (rule,)

    def _match(self, **kw: Any) -> Optional[NetworkRule]:
        best_allow: Optional[NetworkRule] = None
        for rule in self._rules:
            if not rule.matches(**kw):
                continue
            if rule.verdict == "deny":
                return rule  # deny is terminal
            if rule.verdict == "allow":
                best_allow = best_allow or rule
        return best_allow

    def resolve(
        self, url: str, *, direction: str = "egress", method: str = "",
    ) -> tuple[Decision, str, Optional[str]]:
        """Return `(decision, reason, pinned_ip)` without opening a connection.

        Combines the canonical SSRF guard with the configured allow/deny rules.
        `pinned_ip` is the first resolved address, so the caller can pin it and
        defeat DNS rebinding.
        """
        raw = str(url or "").strip()
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if not host:
            return Decision.DENY, "URL has no host", None
        if scheme not in self._schemes and scheme not in ("http", "https", "ws", "wss"):
            return Decision.DENY, f"blocked protocol: {scheme or '(none)'}", None

        # Canonical SSRF guard (private/loopback/link-local/metadata).
        try:
            from ..mcp.ssrf import check_outbound_url  # noqa: PLC0415

            safe, ssrf_reason = check_outbound_url(raw)
            if not safe and not (self._allow_loopback and host in _LOOPBACK_HOSTS):
                return Decision.DENY, ssrf_reason or "SSRF guard refused the URL", None
        except Exception:  # noqa: BLE001 - a broken guard must not become an allow
            return Decision.DENY, "outbound URL guard unavailable", None

        # Resolve + pin (best effort; a resolution failure is a denial for egress).
        pinned: Optional[str] = None
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if scheme in ("https", "wss") else 80))
            for info in infos:
                address = info[4][0]
                try:
                    ip = ipaddress.ip_address(address)
                except ValueError:
                    continue
                if not self._allow_loopback and (
                    ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified
                ):
                    return Decision.DENY, f"host resolves to a non-public address ({address})", None
                pinned = pinned or address
        except socket.gaierror:
            return Decision.DENY, f"host could not be resolved: {host}", None
        except OSError:
            pinned = None  # environment without DNS; literal checks above applied

        port = parsed.port or (443 if scheme in ("https", "wss") else 80)
        match = self._match(
            direction=direction, host=host, ip=pinned, port=port,
            protocol=scheme, method=method, path=parsed.path or "/",
        )
        if match is None:
            if self._default == "allow":
                return Decision.ALLOW, "default allow", pinned
            if self._default == "approval":
                return Decision.APPROVAL_REQUIRED, "default requires approval", pinned
            self._denials += 1
            return Decision.DENY, f"no network policy allows {host}", pinned
        if match.verdict == "allow":
            return Decision.ALLOW, match.reason or f"allowed by rule {match.host or '*'}", pinned
        if match.verdict == "approval":
            return Decision.APPROVAL_REQUIRED, match.reason or "requires approval", pinned
        self._denials += 1
        return Decision.DENY, match.reason or f"denied by rule {match.host or '*'}", pinned

    def check(self, url: str, *, direction: str = "egress", method: str = "") -> Decision:
        return self.resolve(url, direction=direction, method=method)[0]

    def assert_allowed(self, url: str, *, direction: str = "egress", method: str = "") -> Optional[str]:
        decision, reason, pinned = self.resolve(url, direction=direction, method=method)
        if decision is not Decision.ALLOW:
            raise NetworkDenied(reason, host=urlparse(url).hostname or "")
        return pinned

    def check_redirect(self, from_url: str, to_url: str) -> Decision:
        """Re-validate on every redirect hop (no implicit allow of the target)."""
        return self.check(to_url)

    def stats(self) -> dict[str, Any]:
        return {"rules": len(self._rules), "default": self._default, "denials": self._denials}

    def snapshot(self) -> dict[str, Any]:
        return {
            "default": self._default,
            "allowLoopback": self._allow_loopback,
            "schemes": sorted(self._schemes),
            "rules": [
                {
                    "direction": r.direction, "host": r.host, "port": r.port,
                    "protocol": r.protocol, "method": r.method, "path": r.path,
                    "verdict": r.verdict, "reason": r.reason,
                }
                for r in self._rules
            ],
        }


def default_network_engine() -> NetworkPolicyEngine:
    """Default-deny egress with a small, explicit allow list of well-known APIs.

    Everything not listed is DENIED. Financial and localhost/metadata are never
    allowed here; those require their own controls.
    """
    rules = [
        NetworkRule(host="api.openai.com", verdict="allow", reason="model provider"),
        NetworkRule(host="api.anthropic.com", verdict="allow", reason="model provider"),
        NetworkRule(host="generativelanguage.googleapis.com", verdict="allow", reason="model provider"),
        NetworkRule(host="api.github.com", verdict="allow", reason="vcs provider"),
        NetworkRule(host="github.com", verdict="allow", reason="vcs provider"),
    ]
    return NetworkPolicyEngine(rules, default="deny")


__all__ = [
    "NetworkDenied",
    "NetworkPolicyEngine",
    "NetworkRule",
    "default_network_engine",
]
