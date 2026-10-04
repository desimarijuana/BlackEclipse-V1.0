"""Normalized provider errors — the one error vocabulary of the model runtime.

An agent must never branch on a provider's native exception text. Provider
adapters translate whatever a provider raised into a `ModelError` carrying a
stable `ErrorClass`, and the runtime (retry, fallback, health) reasons only
about that class.

Rules:

  * **Classify conservatively.** A structured signal (an error code, an HTTP
    status) wins over message text. When nothing is certain the class is
    `unknown_error`, which is retryable — a transient fault must not be
    permanently mislabelled.
  * **Never leak credentials.** Messages are redacted through the runtime's
    redactor before they are persisted or emitted (see `runtime.redact`).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class ErrorClass(str, enum.Enum):
    """The normalized failure classes (spec §17)."""

    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    CONTEXT_OVERFLOW = "context_overflow"
    CAPABILITY_ERROR = "capability_error"
    CONTENT_POLICY_ERROR = "content_policy_error"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    STRUCTURED_OUTPUT_ERROR = "structured_output_error"
    TOOL_CALL_ERROR = "tool_call_error"
    UNKNOWN_ERROR = "unknown_error"


# Classes where retrying the SAME model is pointless: the request or credential
# is wrong, so a retry can only repeat the failure. `rate_limit` is retryable
# after a wait; the rest are retryable in principle.
_NON_RETRYABLE = frozenset({
    ErrorClass.AUTHENTICATION_ERROR,
    ErrorClass.AUTHORIZATION_ERROR,
    ErrorClass.INVALID_REQUEST,
    ErrorClass.CONTENT_POLICY_ERROR,
    ErrorClass.CAPABILITY_ERROR,
    ErrorClass.STRUCTURED_OUTPUT_ERROR,
})

# Classes that mean "this model/provider is down" — the fallback chain should
# move on, and the circuit breaker should count it.
_PROVIDER_FAULT = frozenset({
    ErrorClass.SERVER_ERROR,
    ErrorClass.PROVIDER_UNAVAILABLE,
    ErrorClass.MODEL_UNAVAILABLE,
    ErrorClass.NETWORK_ERROR,
})


@dataclass
class ModelError(Exception):
    """A provider failure normalized for the runtime."""

    error_class: ErrorClass
    message: str
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    # The provider's raw status/code, kept for debugging, never branched on.
    status_code: Optional[int] = None
    raw_code: Optional[str] = None
    retryable: Optional[bool] = None
    detail: Optional[str] = None
    cause: Optional[BaseException] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Exception.__init__ does not run for dataclasses; set args so `str()`
        # and logging behave, and default retryability from the class.
        super().__init__(self.message)
        if self.retryable is None:
            self.retryable = self.error_class not in _NON_RETRYABLE

    @property
    def is_provider_fault(self) -> bool:
        """True when the provider itself looks unhealthy (not the request)."""
        return self.error_class in _PROVIDER_FAULT

    def to_dict(self) -> dict[str, Any]:
        return {
            "errorClass": self.error_class.value,
            "message": self.message,
            "provider": self.provider_id,
            "model": self.model_id,
            "statusCode": self.status_code,
            "rawCode": self.raw_code,
            "retryable": bool(self.retryable),
        }


# Bounded message patterns. Ordered: the first match wins, so the more specific
# classes (auth, overflow, rate limit) come before the generic ones.
_MESSAGE_RULES: tuple[tuple[ErrorClass, tuple[str, ...]], ...] = (
    (ErrorClass.CONTEXT_OVERFLOW, (
        "maximum context length", "context length", "context window",
        "prompt is too long", "too many tokens", "reduce the length",
        "string_above_max_length", "input token count",
        "max_tokens_exceeded", "context_length_exceeded",
    )),
    (ErrorClass.RATE_LIMIT, (
        "rate limit", "rate_limit", "too many requests", "429",
        "quota exceeded", "insufficient_quota", "resource_exhausted",
    )),
    (ErrorClass.AUTHENTICATION_ERROR, (
        "incorrect api key", "invalid api key", "invalid_api_key",
        "unauthorized", "authentication", "401", "no auth", "missing api key",
        "api key not valid",
    )),
    (ErrorClass.AUTHORIZATION_ERROR, (
        "permission", "forbidden", "not allowed", "403", "access denied",
    )),
    (ErrorClass.TIMEOUT, ("timed out", "timeout", "deadline exceeded", "deadline")),
    (ErrorClass.NETWORK_ERROR, (
        "connection", "connection refused", "network", "dns", "unreachable",
        "socket", "ssl", "tls",
    )),
    (ErrorClass.MODEL_UNAVAILABLE, (
        "model not found", "no such model", "unknown model",
        "model is not available", "does not exist",
    )),
    (ErrorClass.CONTENT_POLICY_ERROR, (
        "content policy", "content_filter", "safety", "blocked",
    )),
    (ErrorClass.TOOL_CALL_ERROR, (
        "tool call", "tool_call", "function call", "tool use",
    )),
    (ErrorClass.INVALID_REQUEST, (
        "invalid request", "bad request", "400", "validation", "malformed",
        "invalid parameter",
    )),
    (ErrorClass.SERVER_ERROR, (
        "internal server", "server error", "500", "502", "503", "504",
        "overloaded", "bad gateway", "service unavailable",
    )),
)

_STRUCTURED_CODE_HINTS: dict[str, ErrorClass] = {
    "context_length_exceeded": ErrorClass.CONTEXT_OVERFLOW,
    "contextlengthexceeded": ErrorClass.CONTEXT_OVERFLOW,
    "context_window_exceeded": ErrorClass.CONTEXT_OVERFLOW,
    "string_above_max_length": ErrorClass.CONTEXT_OVERFLOW,
    "max_tokens_exceeded": ErrorClass.CONTEXT_OVERFLOW,
    "rate_limit_exceeded": ErrorClass.RATE_LIMIT,
    "rate_limit": ErrorClass.RATE_LIMIT,
    "insufficient_quota": ErrorClass.RATE_LIMIT,
    "invalid_api_key": ErrorClass.AUTHENTICATION_ERROR,
    "authentication_error": ErrorClass.AUTHENTICATION_ERROR,
    "permission_denied": ErrorClass.AUTHORIZATION_ERROR,
    "content_filter": ErrorClass.CONTENT_POLICY_ERROR,
    "model_not_found": ErrorClass.MODEL_UNAVAILABLE,
    "server_error": ErrorClass.SERVER_ERROR,
    "overloaded_error": ErrorClass.SERVER_ERROR,
    "timeout": ErrorClass.TIMEOUT,
}


def _structured_code(exc: BaseException) -> Optional[str]:
    """Best-effort read of a provider error's structured code, if any."""
    for attr in ("code", "error_code", "type"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            return value.lower()
    for attr in ("body", "response"):
        value = getattr(exc, attr, None)
        if isinstance(value, dict):
            nested = value.get("error")
            if isinstance(nested, dict) and isinstance(nested.get("code"), str):
                return nested["code"].lower()
            if isinstance(value.get("code"), str):
                return value["code"].lower()
            if isinstance(value.get("type"), str):
                return value["type"].lower()
    return None


def _status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def classify_exception(
    exc: BaseException,
    *,
    provider_id: Optional[str] = None,
    model_id: Optional[str] = None,
) -> ModelError:
    """Translate any exception into a normalized `ModelError`.

    A `ModelError` passes through untouched. Otherwise: structured code, then
    HTTP status, then bounded message patterns, then `unknown_error`.
    """
    if isinstance(exc, ModelError):
        if exc.provider_id is None:
            exc.provider_id = provider_id
        if exc.model_id is None:
            exc.model_id = model_id
        return exc

    raw_code = _structured_code(exc)
    status = _status_code(exc)
    message = str(exc) or exc.__class__.__name__

    error_class: Optional[ErrorClass] = None
    if raw_code and raw_code in _STRUCTURED_CODE_HINTS:
        error_class = _STRUCTURED_CODE_HINTS[raw_code]
    if error_class is None and status is not None:
        if status == 401:
            error_class = ErrorClass.AUTHENTICATION_ERROR
        elif status == 403:
            error_class = ErrorClass.AUTHORIZATION_ERROR
        elif status == 404:
            error_class = ErrorClass.MODEL_UNAVAILABLE
        elif status == 408:
            error_class = ErrorClass.TIMEOUT
        elif status == 429:
            error_class = ErrorClass.RATE_LIMIT
        elif 500 <= status < 600:
            error_class = ErrorClass.SERVER_ERROR
        elif status == 400:
            error_class = ErrorClass.INVALID_REQUEST

    if error_class is None:
        lowered = message.lower()
        for candidate, needles in _MESSAGE_RULES:
            if any(needle in lowered for needle in needles):
                error_class = candidate
                break

    if error_class is None:
        error_class = ErrorClass.UNKNOWN_ERROR

    return ModelError(
        error_class=error_class,
        message=message,
        provider_id=provider_id,
        model_id=model_id,
        status_code=status,
        raw_code=raw_code,
        cause=exc,
    )


__all__ = ["ErrorClass", "ModelError", "classify_exception"]
