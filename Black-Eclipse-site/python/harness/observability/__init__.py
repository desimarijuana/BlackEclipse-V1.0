"""Eclipse Observability Platform — vendor-neutral telemetry for the runtime.

This package is the observability core: correlation context, structured logging,
OpenTelemetry-shaped distributed tracing, metrics, observer hooks, token/cost
accounting, redaction, sampling, health, anomaly/loop detection, SLOs and
fail-open exporters. The runtime integration that projects Eclipse's event bus
into these primitives lives in `integration.py`.

Public entry points:

    from harness.observability import get_hub, ObservationContext, HookEvent, Observer

`get_hub()` returns the process-wide `ObservabilityHub` (creating a disabled-safe
one on first use), so any subsystem can emit telemetry without importing the
service. `install_observability(service)` wires the hub to the runtime.
"""

from __future__ import annotations

from typing import Optional

from .config import ObservabilityConfig, load_config
from .context import ObservationContext, bind_context, current_context, extract, inject
from .core import ObservabilityHub
from .events import HOOKS, HookEvent, make_event
from .observers import Observer, ObserverHub
from .integration import (
    install_observability,
    start_observability,
    stop_observability,
)

_hub: Optional[ObservabilityHub] = None


def get_hub() -> ObservabilityHub:
    """The process-wide hub, created lazily if `install_observability` has not run."""
    global _hub
    if _hub is None:
        _hub = ObservabilityHub()
    return _hub


def set_hub(hub: Optional[ObservabilityHub]) -> None:
    global _hub
    _hub = hub


__all__ = [
    "ObservabilityConfig",
    "ObservabilityHub",
    "ObservationContext",
    "HookEvent",
    "HOOKS",
    "Observer",
    "ObserverHub",
    "load_config",
    "make_event",
    "current_context",
    "bind_context",
    "inject",
    "extract",
    "get_hub",
    "set_hub",
    "install_observability",
    "start_observability",
    "stop_observability",
]
