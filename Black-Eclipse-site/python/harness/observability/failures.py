"""Closed failure taxonomy for telemetry (C7).

Raw error codes are implementation detail; a release gate needs a stable,
bounded vocabulary. Every failure maps to exactly one class so metrics, spans,
error records and SLOs can group failures without cardinality explosions.

The mapping is data, not heuristics: exact codes first, then exception types,
then a conservative `internal` fallback. Unknown errors are counted so the
vocabulary can be extended deliberately instead of silently growing.
"""

from __future__ import annotations

from typing import Any, Optional

FAILURE_CLASSES: tuple[str, ...] = (
    "provider",
    "timeout",
    "transient",
    "validation",
    "tool",
    "budget",
    "policy",
    "sandbox",
    "persistence",
    "cancel",
    "internal",
)

FAILURE_NONE = "none"

_BY_CODE: dict[str, str] = {
    # provider / model
    "PROVIDER_ERROR": "provider",
    "PROVIDER_NOT_CONFIGURED": "provider",
    "PROVIDER_TIMEOUT": "timeout",
    "MODEL_ERROR": "provider",
    "MODEL_UNAVAILABLE": "provider",
    "RATE_LIMIT": "provider",
    "RATE_LIMITED": "provider",
    "CONTEXT_OVERFLOW": "budget",
    # timeouts
    "RUN_TIMEOUT": "timeout",
    "TOOL_TIMEOUT": "timeout",
    "TIMEOUT": "timeout",
    "DEADLINE_EXCEEDED": "timeout",
    # transient
    "TRANSIENT": "transient",
    "TRANSIENT_ERROR": "transient",
    "CONNECTION_ERROR": "transient",
    "CONNECTION_RESET": "transient",
    "DISCONNECT": "transient",
    "RETRY_EXHAUSTED": "transient",
    "STREAM_ERROR": "transient",
    # validation / input
    "INVALID_INPUT": "validation",
    "TOOL_VALIDATION_FAILED": "validation",
    "TOOL_NOT_FOUND": "validation",
    "VALIDATION_ERROR": "validation",
    "BAD_REQUEST": "validation",
    # tool execution
    "TOOL_ERROR": "tool",
    "TOOL_EXECUTION_FAILED": "tool",
    "TOOL_REFUSED": "tool",
    # budgets
    "MAX_STEPS_EXCEEDED": "budget",
    "TOOL_BUDGET_EXCEEDED": "budget",
    "BUDGET_EXCEEDED": "budget",
    "DEPTH_EXCEEDED": "budget",
    "CHILD_LIMIT": "budget",
    "TOKEN_BUDGET_EXCEEDED": "budget",
    # policy / safety
    "TOOL_FORBIDDEN": "policy",
    "POLICY_DENIED": "policy",
    "GUARDRAIL_TOOL_REQUIRED": "policy",
    "GUARDRAIL_CITATION_MISSING": "policy",
    "GUARDRAIL_ANSWER_TOO_LONG": "policy",
    "MONEY_GUARDRAIL_BLOCKED": "policy",
    "UNAUTHORIZED": "policy",
    "SANDBOX_UNAVAILABLE": "sandbox",
    "RUNTIME_UNAVAILABLE": "sandbox",
    "DEPENDENCY_UNAVAILABLE": "sandbox",
    # persistence / resume
    "PERSISTENCE_ERROR": "persistence",
    "CHECKPOINT_NOT_FOUND": "persistence",
    "RESUME_CONFLICT": "persistence",
    "STORE_UNAVAILABLE": "persistence",
    # cancellation
    "CANCELLED": "cancel",
    "CANCELED": "cancel",
    "RUN_CANCELLED": "cancel",
    # explicit terminal failure
    "RUN_FAILED": "internal",
    "INTERNAL_ERROR": "internal",
}

_BY_EXCEPTION: dict[str, str] = {
    "TimeoutError": "timeout",
    "ReadTimeout": "timeout",
    "ConnectTimeout": "timeout",
    "CancelledError": "cancel",
    "ConnectionError": "transient",
    "ConnectionResetError": "transient",
    "BrokenPipeError": "transient",
    "ValueError": "validation",
    "ValidationError": "validation",
    "KeyError": "validation",
    "PermissionError": "policy",
    "FileNotFoundError": "validation",
}

# Prefix families (checked after exact matches).
_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("PROVIDER_", "provider"),
    ("GUARDRAIL_", "policy"),
    ("MONEY_GUARDRAIL_", "policy"),
    ("POLICY_", "policy"),
    ("TOOL_BUDGET_", "budget"),
    ("BUDGET_", "budget"),
    ("TOOL_TIMEOUT", "timeout"),
    ("TOOL_VALIDATION_", "validation"),
    ("TOOL_", "tool"),
    ("SANDBOX_", "sandbox"),
    ("RUNTIME_", "sandbox"),
    ("PERSISTENCE_", "persistence"),
    ("CHECKPOINT_", "persistence"),
    ("RESUME_", "persistence"),
)


def classify_failure(
    *, code: Optional[str] = None, error_type: Optional[str] = None,
) -> str:
    """Map a code or exception class to exactly one failure class."""
    raw = str(code or "").strip().upper()
    if raw:
        if raw in _BY_CODE:
            return _BY_CODE[raw]
        for prefix, failure_class in _BY_PREFIX:
            if raw.startswith(prefix):
                return failure_class
    exc = str(error_type or "").strip()
    if exc:
        if exc in _BY_EXCEPTION:
            return _BY_EXCEPTION[exc]
        if exc.endswith("TimeoutError") or exc.endswith("Timeout"):
            return "timeout"
        if exc.endswith("CancelledError"):
            return "cancel"
        if exc.endswith("ValidationError"):
            return "validation"
        if exc.endswith("ConnectionError"):
            return "transient"
    return "internal"


def is_known_code(code: Optional[str]) -> bool:
    raw = str(code or "").strip().upper()
    if not raw:
        return False
    if raw in _BY_CODE:
        return True
    return any(raw.startswith(prefix) for prefix, _ in _BY_PREFIX)


def failure_labels(
    *, code: Optional[str] = None, error_type: Optional[str] = None,
    component: str = "run",
) -> dict[str, str]:
    """The bounded metric/span labels for a failure."""
    return {
        "failureClass": classify_failure(code=code, error_type=error_type),
        "component": str(component or "run"),
    }


def classify_event(event: Any) -> str:
    """Classify a HookEvent-shaped object (duck-typed, no import cycle)."""
    attributes = getattr(event, "attributes", None) or {}
    return classify_failure(
        code=getattr(event, "error_type", None) or attributes.get("errorCode"),
        error_type=getattr(event, "error_type", None),
    )


__all__ = [
    "FAILURE_CLASSES",
    "FAILURE_NONE",
    "classify_event",
    "classify_failure",
    "failure_labels",
    "is_known_code",
]
