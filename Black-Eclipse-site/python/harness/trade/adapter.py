"""The broker adapter contract.

Every broker — MetaTrader 5's local IPC, an MT4 bridge EA, a REST broker — is
reduced to these read operations in P0. Adding a broker is implementing this
class and registering it; no caller changes.

`probe()` must never claim availability it cannot prove. A missing package, a
missing terminal, a logged-out terminal and a disabled Algo Trading switch are
distinct, named reasons.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class AdapterUnavailable(RuntimeError):
    """A broker cannot be reached, with a machine-readable code and a reason."""

    def __init__(self, code: str, reason: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.reason, **self.detail}


class BrokerAdapter(ABC):
    """Read-only broker surface for P0.

    Implementations open a short-lived session per call and close it. They must
    be safe to construct without a reachable broker (construction never connects).
    """

    kind: str = ""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = dict(config or {})

    @classmethod
    @abstractmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        """Whether this adapter's dependency is installed on this host.

        Returns `(available, reason)`. This is a cheap check (package + platform),
        never a network or terminal call.
        """

    @abstractmethod
    def probe(self) -> dict[str, Any]:
        """Test the connection and return an honest, structured status."""

    @abstractmethod
    def account(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def positions(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def orders(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def quote(self, symbol: str) -> dict[str, Any]:
        ...

    def close(self) -> None:
        """Release any shared session. Safe to call more than once."""


class TradingAdapter(BrokerAdapter):
    """The P1 execution extension (demo-only until the live gates land).

    `order_preview` must be side-effect free: normalize the volume, validate the
    symbol/stops/filling mode and run the broker's own `order_check`. It must not
    call `order_send`. `submit_order` re-validates and sends exactly once; it never
    retries an ambiguous result.
    """

    @abstractmethod
    def order_preview(self, intent: Any) -> dict[str, Any]:
        ...

    @abstractmethod
    def submit_order(self, intent: Any) -> dict[str, Any]:
        ...

    @abstractmethod
    def cancel_order(self, ticket: int) -> dict[str, Any]:
        ...

    @abstractmethod
    def cancel_all(self, magic: int) -> dict[str, Any]:
        """Cancel every working order that carries `magic` (never a blind all)."""

    def deals_since(self, since_ms: int) -> list[dict[str, Any]]:
        """Deals at/after `since_ms` (server epoch ms). Default: unsupported."""
        return []

    def order_status(self, ticket: int) -> dict[str, Any]:
        """The broker's current/historical state for one order ticket."""
        return {"found": False}


__all__ = ["AdapterUnavailable", "BrokerAdapter", "TradingAdapter"]
