"""Per-server runtime state, descriptors and pure helpers (Phase 6.1 extraction).

Pure move out of `manager.py` with no behavior change: `_ServerRuntime` holds one
server's mutable runtime state (connection, descriptors, lifecycle bookkeeping,
interaction counters); the dataclasses describe discovered tools and safe status;
the free functions are pure helpers over a runtime/config. `MCPManager` remains
the facade and re-exports these names so existing imports keep working.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import MCPServerConfig, redact_secrets
from .lifecycle import RetryBudget

log = logging.getLogger("harness.mcp.runtime")


@dataclass
class MCPToolDescriptor:
    """A discovered tool with its resolved identity, effect and activation state."""

    original_name: str
    eclipse_name: str
    description: str
    input_schema: dict[str, Any]
    effect: str
    effect_source: str
    selected: bool
    activatable: bool
    diagnostic: Optional[str] = None
    # An INFORMATIONAL note that does NOT block activation (e.g. the callable name
    # was shortened to fit the provider limit). Distinct from `diagnostic`, which
    # gates activation.
    note: Optional[str] = None

    def public(self) -> dict[str, Any]:
        return {
            "originalName": self.original_name,
            "eclipseName": self.eclipse_name,
            "description": self.description,
            "effect": self.effect,
            "effectSource": self.effect_source,
            "selected": self.selected,
            "activatable": self.activatable,
            "diagnostic": self.diagnostic,
            "note": self.note,
        }


@dataclass
class MCPServerStatus:
    """Safe, non-secret status for one configured server."""

    id: str
    name: str
    enabled: bool
    state: str
    protocol_version: Optional[str] = None
    server_info: Optional[dict[str, Any]] = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    diagnostic: Optional[str] = None
    registered_tools: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "state": self.state,
            "protocolVersion": self.protocol_version,
            "serverInfo": self.server_info,
            "tools": self.tools,
            "diagnostic": self.diagnostic,
            "registeredTools": self.registered_tools,
        }


class _ServerRuntime:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.limits = config.limits()
        self.secrets = config.secret_values()
        self.connection: Optional[Any] = None
        self.resolved_connection: Any = None
        self.state = "disabled" if not config.enabled else "pending"
        self.diagnostic: Optional[str] = None
        self.descriptors: dict[str, MCPToolDescriptor] = {}
        self.registered_tools: list[str] = []
        self.semaphore = __import__("asyncio").Semaphore(self.limits["maxConcurrency"])
        # A versioned digest of the discovered catalog, so a change is reviewable
        # (a different digest means the server's tool set/descriptions changed).
        self.catalog_digest: Optional[str] = None
        self.catalog_reviewed_at: Optional[str] = None
        # Lifecycle (Milestone 2): retry budget, lazy/cached state, keepalive and
        # recycle bookkeeping. `lazy_active` is True when tools were registered
        # from the on-disk cache without a live connection.
        self.budget = RetryBudget()
        self.lazy_active = False
        self.cache_fingerprint: Optional[str] = None
        self.last_error_code: Optional[str] = None
        self.last_error: Optional[str] = None
        self.keepalive_last_probe: Optional[float] = None
        self.keepalive_failures = 0
        self.recycled_reason: Optional[str] = None
        self.connect_lock = __import__("asyncio").Lock()
        self.in_flight = 0
        self.registered_pgids: list[int] = []
        # Server-initiated interactions (Milestone 5): sampling policy + audit.
        from .interactions import InteractionCounters, SamplingPolicy

        self.sampling = SamplingPolicy()
        self.interactions = InteractionCounters()
        # Content-free call metrics for the diagnostics surface.
        self.calls = 0
        self.errors = 0
        self.total_latency_ms = 0
        # The last operator-triggered Verify result (content-free: a stable code,
        # an optional provider status/code, the tool, and when). Never the body.
        self.verify_result: Optional[dict[str, Any]] = None
        # Per-run call counter for the bounded MCP call budget, keyed by run id.
        self.run_calls: dict[str, int] = {}
        # Truncation record when the discovered catalog exceeds `maxTools`, so a
        # user never believes they are seeing a server's full catalog.
        self.tools_discovered: Optional[int] = None
        self.tools_kept: Optional[int] = None
        # True when a lazy server's on-disk cache did not match the current
        # connection fingerprint, so the cached declarations are stale and a
        # connect is required (never silently served).
        self.cache_stale = False
        # Inbound-notification bookkeeping (continuation): a declared
        # `tools/list_changed` triggers rediscovery of this one server. These are
        # content-free audit facts surfaced on the card.
        self.catalog_changes = 0
        self.last_catalog_change_at: Optional[str] = None
        self.removed_tools: list[str] = []
        # Circuit breaker for a server that connects but fails every call.
        from .circuit import CircuitBreaker

        self.circuit = CircuitBreaker()

    def redact(self, text: str) -> str:
        return redact_secrets(text, self.secrets)

    def all_secret_values(self) -> list[str]:
        """Declared env values plus values resolved from the vault at spawn."""
        values = list(self.secrets)
        if self.connection is not None:
            for value in self.connection.redaction_values:
                if value not in values:
                    values.append(value)
        return values


_ALLOWED_RESOURCE_SCHEMES = ("file", "http", "https", "mcp", "resource", "db", "git", "data", "memory", "skill", "workspace", "note", "doc", "ui")


def effective_resource_schemes(narrowing: Optional[list[str]] = None) -> tuple[str, ...]:
    """The URI schemes a server may read.

    The global list is a hard CEILING: an optional per-server list only ever
    REMOVES schemes (an intersection), so a server can never broaden access by
    naming a scheme outside the global allowlist. An empty/unset narrowing keeps
    the full global list.
    """
    if not narrowing:
        return _ALLOWED_RESOURCE_SCHEMES
    allowed = set(_ALLOWED_RESOURCE_SCHEMES)
    narrowed = {str(s).strip().lower() for s in narrowing if str(s).strip()}
    return tuple(sorted(allowed & narrowed))


def _allowed_uri(uri: str, narrowing: Optional[list[str]] = None) -> bool:
    """A resource URI scheme authorization rule (no `javascript:`/`cmd:` etc.).

    `narrowing` is an optional per-server subset of the global allowlist; it can
    only remove schemes, never add one.
    """
    if not uri or ":" not in uri:
        return False
    scheme = uri.split(":", 1)[0].lower()
    return scheme in effective_resource_schemes(narrowing)


def _unsafe_url_reason(config: MCPServerConfig, url: Optional[str] = None) -> Optional[str]:
    """The refusal reason for a remote endpoint, or None when safe/not-remote."""
    from .ssrf import check_outbound_url

    if config.transport not in ("http", "sse"):
        return None
    effective = url if url is not None else config.url
    if not effective:
        return None
    safe, reason = check_outbound_url(effective)
    return None if safe else (reason or "unsafe URL")


def _catalog_digest(rt: _ServerRuntime) -> str:
    """A stable digest of a server's discovered catalog.

    Covers each tool's identity, effect and schema, so a changed tool set,
    description or schema produces a different digest and can be reviewed.
    """
    payload = [
        {
            "name": d.original_name,
            "effect": d.effect,
            "schema": d.input_schema,
            "description": d.description,
        }
        for d in sorted(rt.descriptors.values(), key=lambda d: d.original_name)
    ]
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "MCPToolDescriptor",
    "MCPServerStatus",
    "_ServerRuntime",
    "_ALLOWED_RESOURCE_SCHEMES",
    "effective_resource_schemes",
    "_allowed_uri",
    "_unsafe_url_reason",
    "_catalog_digest",
]
