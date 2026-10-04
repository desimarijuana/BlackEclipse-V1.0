"""Capability detection: provider metadata → static catalog → runtime probe.

Spec §6: never blindly trust provider metadata. We merge three sources and let a
successful or failed probe override a declaration:

    provider metadata  →  static catalog  →  runtime probe  →  normalized state

An operator-declared capability that a probe contradicts is marked DEGRADED
(claimed, not proven) or UNSUPPORTED (proven absent). A capability nobody can
decide stays UNKNOWN.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .catalog import (
    LONG_CONTEXT_MIN_TOKENS,
    MODEL_CAPABILITY_OVERRIDES,
    PROVIDER_CAPABILITIES,
)
from .types import CAPABILITY_KEYS, CapabilityState, ModelCapabilities


def _kind_defaults(kind: str) -> dict[str, CapabilityState]:
    return dict(PROVIDER_CAPABILITIES.get(kind, {}))


def _model_overrides(model_id: str) -> dict[str, CapabilityState]:
    """Longest matching substring override wins (like context windows)."""
    needle = (model_id or "").lower()
    best_key = ""
    merged: dict[str, CapabilityState] = {}
    for substring, states in MODEL_CAPABILITY_OVERRIDES.items():
        if substring in needle and len(substring) > len(best_key):
            best_key = substring
            merged = states
    return dict(merged)


def detect_capabilities(
    *,
    kind: str,
    model_id: str,
    provider_metadata: Optional[dict[str, Any]] = None,
    context_window: Optional[int] = None,
    overrides: Optional[dict[str, CapabilityState]] = None,
) -> ModelCapabilities:
    """Merge the three pre-probe sources into a normalized capability object.

    Resolution order per key: static model override > provider metadata >
    provider-kind default. The result records UNKNOWN explicitly for every
    capability nobody declared.
    """
    states: dict[str, CapabilityState] = {}

    kind_defaults = _kind_defaults(kind)
    model_overrides = _model_overrides(model_id)
    meta = _normalize_metadata(provider_metadata or {})

    for key in CAPABILITY_KEYS:
        if key in model_overrides:
            states[key] = model_overrides[key]
        elif key in meta:
            states[key] = meta[key]
        elif key in kind_defaults:
            states[key] = kind_defaults[key]
        else:
            states[key] = CapabilityState.UNKNOWN

    # A large resolved window promotes long_context only when it was unknown —
    # never overriding an explicit UNSUPPORTED declaration.
    if (
        context_window is not None
        and context_window >= LONG_CONTEXT_MIN_TOKENS
        and states.get("long_context") is CapabilityState.UNKNOWN
    ):
        states["long_context"] = CapabilityState.SUPPORTED

    if overrides:
        states.update(overrides)

    return ModelCapabilities(states)


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, CapabilityState]:
    """Accept several provider-metadata shapes and normalize to states."""
    states: dict[str, CapabilityState] = {}
    raw = metadata.get("capabilities") if isinstance(metadata.get("capabilities"), dict) else metadata
    if not isinstance(raw, dict):
        return states
    for key in CAPABILITY_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, CapabilityState):
            states[key] = value
        elif isinstance(value, bool):
            states[key] = CapabilityState.SUPPORTED if value else CapabilityState.UNSUPPORTED
        elif isinstance(value, str):
            try:
                states[key] = CapabilityState(value)
            except ValueError:
                continue
    return states


def apply_probe(
    capabilities: ModelCapabilities,
    *,
    key: str,
    observed: CapabilityState,
) -> ModelCapabilities:
    """Fold a runtime probe result into a capability set.

    A probe that proves support upgrades UNKNOWN → SUPPORTED. A probe that
    proves a claim wrong downgrades SUPPORTED → DEGRADED (not proven) on a
    negative result only when the failure is specific; callers pass the exact
    state they observed.
    """
    if key not in CAPABILITY_KEYS:
        return capabilities
    return capabilities.with_state(key, observed)


def probe_streaming(capabilities: ModelCapabilities, *, streamed: bool) -> ModelCapabilities:
    return apply_probe(
        capabilities,
        key="streaming",
        observed=CapabilityState.SUPPORTED if streamed else CapabilityState.DEGRADED,
    )


def probe_tool_calling(capabilities: ModelCapabilities, *, worked: bool) -> ModelCapabilities:
    return apply_probe(
        capabilities,
        key="tool_calling",
        observed=CapabilityState.SUPPORTED if worked else CapabilityState.DEGRADED,
    )


def probe_structured_output(capabilities: ModelCapabilities, *, worked: bool) -> ModelCapabilities:
    return apply_probe(
        capabilities,
        key="structured_output",
        observed=CapabilityState.SUPPORTED if worked else CapabilityState.DEGRADED,
    )


def required_missing(capabilities: ModelCapabilities, required: Iterable[str]) -> list[str]:
    return [k for k in required if not capabilities.is_supported(k)]


__all__ = [
    "apply_probe",
    "detect_capabilities",
    "probe_streaming",
    "probe_structured_output",
    "probe_tool_calling",
    "required_missing",
]
