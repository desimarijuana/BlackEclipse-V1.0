"""Default deterministic diagnosis probes.

A probe turns a *failure* into one environmental fact the diagnosis engine can
rank hypotheses against. These defaults are deliberately conservative and
read-only: they inspect local state that already exists, they never call a model,
install anything or mutate state, and when they cannot establish a fact they
return `None` ("unknown") rather than guessing.

Registered on the `DiagnosisEngine` at boot via `register_default_probes`. A probe
that raises is recorded as missing information by the engine, never fatal.
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any, Optional

from .diagnosis import DiagnosisEngine
from .taxonomy import FailureKind

_MODULE = re.compile(r"(?:no module named|modulenotfounderror:?[^\w]*)\s*['\"]?([\w.]+)['\"]?", re.I)


def _probe_dependency_missing(failure: Any) -> Optional[bool]:
    """True when the failure names a module that is not importable here."""
    match = _MODULE.search(failure.message or "")
    if not match:
        return None
    module = match.group(1).split(".")[0]
    if not module:
        return None
    try:
        return importlib.util.find_spec(module) is None
    except (ImportError, ValueError, ModuleNotFoundError):
        # A partially-initialized package raises rather than returning None.
        return True


def _configured_providers() -> Optional[list[dict[str, Any]]]:
    try:
        from ..models import list_providers  # noqa: PLC0415

        providers = list_providers()
        return providers if isinstance(providers, list) else None
    except Exception:  # noqa: BLE001 - absence of provider info is "unknown"
        return None


def _probe_credential_missing(_failure: Any) -> Optional[bool]:
    """True only when NO model provider is configured at all."""
    providers = _configured_providers()
    if providers is None:
        return None
    return len(providers) == 0


def _probe_provider_unhealthy(_failure: Any) -> Optional[bool]:
    """True when the model runtime reports an open (unhealthy) circuit."""
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        runtime = get_runtime()
    except Exception:  # noqa: BLE001
        return None
    health = getattr(runtime, "health", None)
    manager = getattr(runtime, "health_manager", None) or getattr(health, "manager", None)
    if manager is None:
        return None
    try:
        states = manager.snapshot() if hasattr(manager, "snapshot") else None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(states, dict):
        return None
    for value in states.values():
        state = value.get("state") if isinstance(value, dict) else value
        if isinstance(state, str) and state.upper() == "OPEN":
            return True
    return None


def register_default_probes(engine: DiagnosisEngine, service: Any = None) -> None:
    """Attach the read-only default probes to a diagnosis engine (idempotent)."""
    engine.register(
        "dependency_missing",
        lambda kind: kind == FailureKind.DEPENDENCY,
        _probe_dependency_missing,
    )
    engine.register(
        "credential_missing",
        lambda kind: kind in (FailureKind.AUTHENTICATION, FailureKind.AUTHORIZATION),
        _probe_credential_missing,
    )
    engine.register(
        "provider_unhealthy",
        lambda kind: kind == FailureKind.PROVIDER_OUTAGE,
        _probe_provider_unhealthy,
    )


__all__ = ["register_default_probes"]