"""Vision error classification.

Every vision operation fails into ONE of these classes so the orchestrator,
telemetry and the agent can react exactly (retry, fallback, or refuse) instead
of string-matching a provider message. The classes mirror the model runtime's
`ErrorClass` vocabulary so a failure that bubbles out of a provider call keeps
its meaning.

Nothing here is ever used to fake success: a raised `VisionError` is a real,
reported failure. `VisionError.retryable` and `.fallbackable` are the only
signals the orchestrator acts on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class VisionErrorClass(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"            # missing/unknown source, bad args
    INVALID_IMAGE = "INVALID_IMAGE"            # undecodable / corrupt image
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"  # real image, format we cannot use
    OVERSIZED = "OVERSIZED"                    # exceeds a hard size/pixel ceiling
    DECOMPRESSION_BOMB = "DECOMPRESSION_BOMB"  # pixel bomb / zip bomb
    SECURITY_BLOCKED = "SECURITY_BLOCKED"      # SSRF / injection / policy refusal
    NO_SOURCE = "NO_SOURCE"                    # file/url/clipboard not found
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"  # source kind not supported here
    NO_VISION_MODEL = "NO_VISION_MODEL"        # no model can accept an image
    PRIVACY_REFUSED = "PRIVACY_REFUSED"        # local-only policy, no local model
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"  # model output failed validation
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_FAILED = "OCR_FAILED"
    STORAGE_ERROR = "STORAGE_ERROR"
    CACHE_ERROR = "CACHE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_RETRYABLE = frozenset({
    VisionErrorClass.PROVIDER_ERROR,
    VisionErrorClass.PROVIDER_TIMEOUT,
    VisionErrorClass.RATE_LIMIT,
    VisionErrorClass.PROVIDER_UNAVAILABLE,
    VisionErrorClass.INTERNAL_ERROR,
})

# A retryable error is also worth trying on a DIFFERENT backend; an invalid
# image is not (no backend will make it decodable).
_FALLBACKABLE = _RETRYABLE | frozenset({
    VisionErrorClass.NO_VISION_MODEL,
    VisionErrorClass.MALFORMED_RESPONSE,
})


@dataclass
class VisionError(Exception):
    """A classified, reportable vision failure. Never silent, never faked."""

    error_class: VisionErrorClass
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None
    source_ref: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    cause: Optional[BaseException] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    @property
    def retryable(self) -> bool:
        return self.error_class in _RETRYABLE

    @property
    def fallbackable(self) -> bool:
        return self.error_class in _FALLBACKABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "errorClass": self.error_class.value,
            "message": self.message,
            "provider": self.provider,
            "model": self.model,
            "sourceRef": self.source_ref,
            "retryable": self.retryable,
            "fallbackable": self.fallbackable,
            "details": self.details or {},
        }


__all__ = ["VisionError", "VisionErrorClass"]
