"""Install the Security subsystem into the process-wide `AgenticService`.

`install_security_layer(service)` constructs the ONE `SecurityGateway` exactly
once and attaches it as `service.security`, and sets the process-wide accessor
used by the effect-authorizer seam (`security.integration.get_gateway`). Best
effort: if construction fails the runtime still boots and the existing
per-subsystem authorizers remain the authority (never an implicit allow).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .config import SecurityConfig
from .effect_tokens import token_mode
from .gateway import SecurityGateway
from .network import NetworkPolicyEngine, default_network_engine
from .policy import PolicyEngine
from .secrets import build_default_secrets_manager

log = logging.getLogger("harness.security.bootstrap")

_GATEWAY: Optional[SecurityGateway] = None
_SHADOW_WARNED = False


def warn_if_shadow() -> None:
    """Say plainly when effect tokens are recording but not blocking (W6).

    `HARNESS_EFFECT_TOKENS=shadow` is a migration window, not a safe default for
    production. One warning per process; a development profile is exempt.
    """
    global _SHADOW_WARNED
    if _SHADOW_WARNED or token_mode() != "shadow":
        return
    _SHADOW_WARNED = True
    profile = (os.environ.get("BE_PROFILE") or os.environ.get("BLACK_ECLIPSE_ENVIRONMENT")
               or os.environ.get("NODE_ENV") or "prod").strip().lower()
    if profile in ("dev", "development", "test", "testing"):
        return
    log.warning(
        "HARNESS_EFFECT_TOKENS=shadow: replayed or widened effectful calls are "
        "recorded, not blocked. Set HARNESS_EFFECT_TOKENS=enforce for production."
    )


def install_security_layer(service: Any, *, config: Optional[SecurityConfig] = None) -> Optional[SecurityGateway]:
    """Construct and attach the process-wide security gateway (idempotent)."""
    warn_if_shadow()
    existing = getattr(service, "_security_gateway", None)
    if existing is not None:
        _set_gateway(existing)
        return existing
    cfg = config or SecurityConfig.from_env()
    if not cfg.enabled:
        log.info("security subsystem disabled (BLACK_ECLIPSE_SECURITY_ENABLED=0)")
        return None
    try:
        network = default_network_engine()
        if cfg.allow_loopback_network:
            network = NetworkPolicyEngine(list(network._rules), default="deny", allow_loopback=True)  # noqa: SLF001
        gateway = SecurityGateway(
            store=getattr(service, "store", None),
            approvals=getattr(service, "approvals", None),
            floor=None,
            policy=PolicyEngine(cfg.profile),
            network=network,
            secrets=build_default_secrets_manager(),
            profile=cfg.profile.value,
        )
        if cfg.policy:
            # Load configured layers; an invalid file is reported, not fatal.
            try:
                layers = {k: v for k, v in cfg.policy.items() if k in ("organization", "user", "project", "agent", "task")}
                if layers:
                    gateway.reload_policy(layers, profile=cfg.profile.value, actor="boot")
            except Exception:  # noqa: BLE001 - a broken policy file keeps the built-in default
                log.warning("configured security policy rejected; using built-in default", exc_info=True)
        service._security_gateway = gateway  # noqa: SLF001 - the one process-wide attach point
        _set_gateway(gateway)
        return gateway
    except Exception:  # noqa: BLE001 - security must never block boot
        log.warning("security subsystem failed to install", exc_info=True)
        return None


def _set_gateway(gateway: Optional[SecurityGateway]) -> None:
    global _GATEWAY
    _GATEWAY = gateway


def get_gateway() -> Optional[SecurityGateway]:
    """The process-wide gateway, or None when not installed."""
    return _GATEWAY


def set_gateway(gateway: Optional[SecurityGateway]) -> None:
    """Explicit setter, used by tests and the operator API."""
    _set_gateway(gateway)


def security_gateway(service: Any) -> Optional[SecurityGateway]:
    return getattr(service, "_security_gateway", None) or _GATEWAY


async def start_security(service: Any) -> None:
    """Attach observability/event sinks once they exist (best effort)."""
    gateway = security_gateway(service)
    if gateway is None:
        gateway = install_security_layer(service)
    if gateway is None:
        return
    observability = getattr(service, "observability", None)
    if observability is not None:
        gateway.audit.attach_metrics(getattr(observability, "metrics", None))
    events = getattr(service, "_event_system", None)
    if events is not None:
        gateway.audit.attach_events(events)


async def stop_security(service: Any) -> None:
    """Close every open security session (revokes their temporary authority)."""
    gateway = security_gateway(service)
    if gateway is None:
        return
    try:
        for context in list(gateway.sessions._contexts.values()):  # noqa: SLF001
            gateway.close_session(context.session_id)
    except Exception:  # noqa: BLE001
        log.warning("security shutdown failed", exc_info=True)


__all__ = [
    "get_gateway",
    "install_security_layer",
    "security_gateway",
    "set_gateway",
    "start_security",
    "stop_security",
    "warn_if_shadow",
]
