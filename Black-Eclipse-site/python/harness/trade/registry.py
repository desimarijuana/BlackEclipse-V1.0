"""Broker-kind registry: the one place a new broker is declared.

A kind is a descriptor plus a factory. The descriptor is what the UI and the
agent can see; the factory is only called when a saved connection is actually
used. `list_kinds()` reports dependency availability without touching a broker.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .adapter import BrokerAdapter
from .model import KIND_MT5, BrokerKind

_FACTORIES: dict[str, Callable[[dict[str, Any]], BrokerAdapter]] = {}
_KINDS: dict[str, BrokerKind] = {}


def register_kind(
    kind: BrokerKind,
    factory: Callable[[dict[str, Any]], BrokerAdapter],
    *,
    replace: bool = False,
) -> None:
    if kind.id in _KINDS and not replace:
        raise ValueError(f"broker kind {kind.id!r} is already registered")
    _KINDS[kind.id] = kind
    _FACTORIES[kind.id] = factory


def get_kind(kind_id: str) -> BrokerKind:
    kind = _KINDS.get(str(kind_id or "").strip().lower())
    if kind is None:
        raise KeyError(
            f"unknown broker kind {kind_id!r}; Eclipse knows "
            f"{', '.join(sorted(_KINDS)) or 'none'}"
        )
    return kind


def list_kinds() -> list[dict[str, Any]]:
    """Every kind plus whether its dependency is installed on this host."""
    out: list[dict[str, Any]] = []
    for kind in _KINDS.values():
        payload = kind.to_dict()
        factory = _FACTORIES[kind.id]
        try:
            available, reason = factory({}).availability()
        except Exception as exc:  # noqa: BLE001 - availability must never raise
            available, reason = False, f"availability check failed: {exc}"
        payload["available"] = bool(available)
        payload["unavailableReason"] = None if available else (reason or "unavailable")
        out.append(payload)
    return out


def make_adapter(kind_id: str, config: Optional[dict[str, Any]] = None) -> BrokerAdapter:
    kind = get_kind(kind_id)
    return _FACTORIES[kind.id](dict(config or {}))


def _register_builtins() -> None:
    from .adapters.mt5 import MT5Adapter  # noqa: PLC0415 - avoids import cycles

    register_kind(
        BrokerKind(
            id=KIND_MT5,
            label="MetaTrader 5",
            auth="attach",
            modes=("demo", "live"),
            asset_classes=("fx", "cfd", "futures", "stocks", "crypto", "metals"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=True,
            execution_modes=("demo", "live"),
            notes=(
                "Attaches to a running, logged-in terminal64.exe over local IPC. "
                "Demo execution is always available; live execution requires a "
                "time-boxed arm, a positive maxMargin and a non-zero magic."
            ),
        ),
        MT5Adapter,
    )


_register_builtins()

__all__ = ["get_kind", "list_kinds", "make_adapter", "register_kind"]
