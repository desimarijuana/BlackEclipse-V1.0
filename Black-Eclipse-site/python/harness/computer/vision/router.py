"""Vision routing — local vs cloud vs hybrid.

The router picks a vision backend for a request from the configured
`vision_mode`:

    local   → only a local backend is ever used
    cloud   → a cloud backend is preferred
    hybrid  → local when sensitive, cloud otherwise (unless policy forbids)

A frame flagged SENSITIVE (a credential region, a financial account with
redaction off, etc.) is NEVER sent to a cloud backend unless
`vision.allow_cloud_for_sensitive` is set. The decision is DATA so it is
testable without any model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..config import computer_config
from .backends import LocalModelVision, UnavailableVision
from .base import VisionEngine


@dataclass
class RoutingDecision:
    backend: str
    local: bool
    reason: str
    refused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "local": self.local, "reason": self.reason, "refused": self.refused}


def decide_vision(*, mode: str, sensitive: bool, allow_cloud_sensitive: bool, local_available: bool, cloud_available: bool) -> RoutingDecision:
    """The pure routing decision (no models involved)."""
    if sensitive and not allow_cloud_sensitive:
        if local_available:
            return RoutingDecision("local", True, "sensitive frame routed to a local model")
        return RoutingDecision("none", True, "sensitive frame and no local vision model is available", refused=True)
    if mode == "local":
        if local_available:
            return RoutingDecision("local", True, "local-only mode")
        return RoutingDecision("none", True, "local-only mode but no local model is available", refused=True)
    if mode == "cloud":
        if cloud_available:
            return RoutingDecision("cloud", False, "cloud mode")
        if local_available:
            return RoutingDecision("local", True, "cloud unavailable; fell back to local")
        return RoutingDecision("none", True, "no vision model is available", refused=True)
    # hybrid
    if cloud_available and not sensitive:
        return RoutingDecision("cloud", False, "hybrid mode: cloud for a non-sensitive frame")
    if local_available:
        return RoutingDecision("local", True, "hybrid mode: local")
    return RoutingDecision("none", True, "no vision model is available", refused=True)


class VisionRouter:
    """Selects a vision engine for a request from the config + sensitivity."""

    def __init__(self, *, local: VisionEngine, cloud: Optional[VisionEngine] = None) -> None:
        self._local = local
        self._cloud = cloud or UnavailableVision("no cloud vision backend is configured")

    def decide(self, *, sensitive: bool = False) -> RoutingDecision:
        cfg = computer_config()
        return decide_vision(
            mode=cfg.vision_mode,
            sensitive=sensitive,
            allow_cloud_sensitive=cfg.vision_allow_cloud_for_sensitive,
            local_available=self._local.available,
            cloud_available=self._cloud.available,
        )

    def engine(self, *, sensitive: bool = False) -> VisionEngine:
        decision = self.decide(sensitive=sensitive)
        if decision.refused or decision.backend == "none":
            return UnavailableVision(decision.reason)
        return self._local if decision.local else self._cloud

    def describe(self) -> dict[str, Any]:
        return {
            "local": self._local.describe_backend(),
            "cloud": self._cloud.describe_backend(),
            "mode": computer_config().vision_mode,
        }


def build_vision_router(*, local_settings: Any = None, cloud_settings: Any = None) -> VisionRouter:
    """Build the router from the process's available model settings."""
    local = LocalModelVision(settings=local_settings, local=True) if local_settings is not None else UnavailableVision()
    cloud = LocalModelVision(settings=cloud_settings, local=False) if cloud_settings is not None else None
    return VisionRouter(local=local, cloud=cloud)


__all__ = ["RoutingDecision", "VisionRouter", "build_vision_router", "decide_vision"]
