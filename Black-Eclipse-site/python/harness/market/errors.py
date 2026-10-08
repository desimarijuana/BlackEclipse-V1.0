"""Structured error model for the Market Data Layer.

Every market-data failure is one of a closed vocabulary of codes, each carrying
an actionable message, whether the caller may retry it, and (optionally) the
provider that produced it. This is the ONE error vocabulary the market tools,
the gateway, the router and the routes all speak, so "the provider is down" is
never confused with "this instrument genuinely has no options chain".

The codes mirror the directive's error model and the existing retrieval
taxonomy (`retrieval.routing.RouteCategory`) — they are deliberately compatible
so a market result and a retrieval result are classifiable the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# The closed error-code vocabulary. A value outside this set must never be
# constructed; `MarketError.__post_init__` guards it.
MarketErrorCode = str

PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
RATE_LIMITED = "RATE_LIMITED"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
DATA_NOT_AVAILABLE = "DATA_NOT_AVAILABLE"
DATA_STALE = "DATA_STALE"
DATA_CONFLICT = "DATA_CONFLICT"
INVALID_INTERVAL = "INVALID_INTERVAL"
INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
STREAM_DISCONNECTED = "STREAM_DISCONNECTED"
STREAM_RESYNC_REQUIRED = "STREAM_RESYNC_REQUIRED"
UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
INVALID_REQUEST = "INVALID_REQUEST"
CONFIGURATION_ERROR = "CONFIGURATION_ERROR"

CODES: frozenset[str] = frozenset(
    {
        PROVIDER_UNAVAILABLE,
        RATE_LIMITED,
        AUTHENTICATION_FAILED,
        SYMBOL_NOT_FOUND,
        INSTRUMENT_NOT_FOUND,
        DATA_NOT_AVAILABLE,
        DATA_STALE,
        DATA_CONFLICT,
        INVALID_INTERVAL,
        INVALID_DATE_RANGE,
        STREAM_DISCONNECTED,
        STREAM_RESYNC_REQUIRED,
        UNSUPPORTED_CAPABILITY,
        INVALID_REQUEST,
        CONFIGURATION_ERROR,
    }
)

# Which codes are worth retrying with backoff. A wrong symbol or an unsupported
# capability must never be retried (it will fail identically).
RETRYABLE: frozenset[str] = frozenset({PROVIDER_UNAVAILABLE, RATE_LIMITED})

# Route category the retrieval layer's classifier would assign, so a market
# error and a retrieval diagnostic describe the same real condition.
_ROUTE_CATEGORY: dict[str, str] = {
    PROVIDER_UNAVAILABLE: "provider_failure",
    RATE_LIMITED: "rate_limited",
    AUTHENTICATION_FAILED: "unconfigured",
    SYMBOL_NOT_FOUND: "no_instrument",
    INSTRUMENT_NOT_FOUND: "no_instrument",
    DATA_NOT_AVAILABLE: "no_data",
    DATA_STALE: "stale_data",
    DATA_CONFLICT: "provider_failure",
    INVALID_INTERVAL: "no_data",
    INVALID_DATE_RANGE: "no_data",
    STREAM_DISCONNECTED: "provider_failure",
    STREAM_RESYNC_REQUIRED: "provider_failure",
    UNSUPPORTED_CAPABILITY: "not_implemented",
    INVALID_REQUEST: "no_data",
    CONFIGURATION_ERROR: "unconfigured",
}


@dataclass
class MarketError:
    """One structured market-data failure. Pure data, JSON-safe."""

    code: MarketErrorCode
    message: str
    provider: Optional[str] = None
    capability: Optional[str] = None
    retryable: bool = False
    retry_after_s: Optional[float] = None
    detail: Optional[dict[str, Any]] = field(default=None)

    def __post_init__(self) -> None:
        if self.code not in CODES:
            raise ValueError(f"unknown market error code: {self.code!r}")
        if self.retryable is False and self.code in RETRYABLE:
            # Default retryability from the code unless explicitly overridden.
            self.retryable = True

    @property
    def routeCategory(self) -> str:  # noqa: N802 - mirrors retrieval vocabulary
        return _ROUTE_CATEGORY.get(self.code, "provider_failure")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "routeCategory": self.routeCategory,
        }
        if self.provider:
            out["provider"] = self.provider
        if self.capability:
            out["capability"] = self.capability
        if self.retry_after_s is not None:
            out["retryAfterS"] = self.retry_after_s
        if self.detail:
            out["detail"] = self.detail
        return out


def classify_bridge_failure(payload: dict[str, Any], *, capability: str) -> MarketError:
    """Map a bridge failure payload to the market error vocabulary.

    The bridge already distinguishes `no_data` from `source_failure`,
    `not_covered`, `ambiguous`, `invalid_request`, `incomplete`. This is the ONE
    place that translation happens, so every market capability reports the same
    codes for the same real condition.
    """
    status = str(payload.get("status") or "UNAVAILABLE").upper()
    failure = str(payload.get("failureClass") or "").lower()
    error = str(payload.get("error") or "")
    provider = payload.get("provider") or payload.get("healthContext", {}).get("source")
    diagnostics = payload.get("diagnostics") or []
    http_status = None
    retry_hint = None
    for d in diagnostics if isinstance(diagnostics, list) else []:
        if isinstance(d, dict):
            http_status = http_status or d.get("httpStatus")
            retry_hint = retry_hint or d.get("retryAfterS")
    if status == "AMBIGUOUS" or failure == "ambiguous":
        return MarketError(INVALID_REQUEST, error or "the identifier is ambiguous",
                           provider=provider, capability=capability)
    if failure == "not_covered":
        return MarketError(UNSUPPORTED_CAPABILITY, error or "not covered by any provider",
                           provider=provider, capability=capability)
    if failure == "not_found" or "not found" in error.lower():
        return MarketError(SYMBOL_NOT_FOUND, error or "symbol not found",
                           provider=provider, capability=capability)
    if failure == "invalid_request":
        return MarketError(INVALID_REQUEST, error or "invalid request",
                           provider=provider, capability=capability)
    if failure in ("incomplete",):
        return MarketError(DATA_NOT_AVAILABLE, error or "incomplete provider payload",
                           provider=provider, capability=capability)
    if http_status == 429 or "rate limit" in error.lower() or failure == "rate_limited":
        return MarketError(RATE_LIMITED, error or "provider rate limit reached",
                           provider=provider, capability=capability,
                           retryable=True, retry_after_s=retry_hint)
    if http_status in (401, 403) or "auth" in error.lower() or "required key" in error.lower():
        return MarketError(AUTHENTICATION_FAILED, error or "provider authentication failed",
                           provider=provider, capability=capability)
    if failure == "source_failure":
        return MarketError(PROVIDER_UNAVAILABLE, error or "provider unavailable",
                           provider=provider, capability=capability,
                           retryable=True, detail={"httpStatus": http_status})
    if failure == "no_data":
        return MarketError(DATA_NOT_AVAILABLE, error or "no data available",
                           provider=provider, capability=capability)
    return MarketError(DATA_NOT_AVAILABLE, error or "no data available",
                       provider=provider, capability=capability)


__all__ = [
    "AUTHENTICATION_FAILED",
    "CODES",
    "CONFIGURATION_ERROR",
    "DATA_CONFLICT",
    "DATA_NOT_AVAILABLE",
    "DATA_STALE",
    "INSTRUMENT_NOT_FOUND",
    "INVALID_DATE_RANGE",
    "INVALID_INTERVAL",
    "INVALID_REQUEST",
    "MarketError",
    "MarketErrorCode",
    "PROVIDER_UNAVAILABLE",
    "RATE_LIMITED",
    "RETRYABLE",
    "STREAM_DISCONNECTED",
    "STREAM_RESYNC_REQUIRED",
    "SYMBOL_NOT_FOUND",
    "UNSUPPORTED_CAPABILITY",
    "classify_bridge_failure",
]
