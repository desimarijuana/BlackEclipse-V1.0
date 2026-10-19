"""The ONE cross-subsystem failure vocabulary.

Every subsystem in Eclipse already normalizes its own errors (`model_runtime`
provider errors, `execution` build/test errors, the Tool Runtime's error codes,
the browser/computer/plugin taxonomies). Each is correct for its own boundary,
but nothing maps them onto a *shared* vocabulary, so a recovery decision cannot
reason about "a timeout" the same way whether it came from a provider, a tool or
a workflow node.

This module is that shared vocabulary. `normalize_failure` classifies a failure
given a bounded, non-secret description — a code, a message, the subsystem and
the source seam — and returns an immutable `NormalizedFailure`. It is a PURE
function: it never calls a model, opens a connection or reads the environment.

Design rules:

  * **Classify conservatively.** A structured code (an upper-case enum value or
    a known provider `ErrorClass`) wins over message text. When nothing is
    certain the kind is `UNKNOWN` and retryability is `UNKNOWN` — an unknown
    transient fault must not be permanently mislabelled as non-retryable.
  * **Never carry a secret.** Only the caller-supplied (already-sanitized) code
    and message are retained; this module adds no parsing of raw payloads.
  * **Never invent a category.** If a code is not recognized, the message rules
    are consulted, then `UNKNOWN` — a guess is never presented as a fact.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class FailureKind(str, enum.Enum):
    """The normalized failure kinds (spec §6.1)."""

    NETWORK = "network"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    RATE_LIMIT = "rate_limit"
    PROVIDER_OUTAGE = "provider_outage"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DEPENDENCY = "dependency"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    ASSERTION = "assertion"
    BROWSER = "browser"
    INVALID_REQUEST = "invalid_request"
    PLUGIN = "plugin"
    DATA_QUALITY = "data_quality"
    WORKFLOW = "workflow"
    PLANNING = "planning"
    NO_PROGRESS = "no_progress"
    POLICY_DENIED = "policy_denied"
    CAPABILITY = "capability"
    UNKNOWN = "unknown"


class Retryability(str, enum.Enum):
    """Whether re-running the SAME operation unchanged could plausibly succeed."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    UNKNOWN = "unknown"


# ── Classification tables ────────────────────────────────────────────────────
# Retrying a deterministic failure only repeats a side effect or burns budget, so
# the non-retryable set spans both provider semantics (auth/invalid request) and
# harness semantics (validation/not-found/forbidden).
_NON_RETRYABLE_KINDS = frozenset(
    {
        FailureKind.AUTHENTICATION,
        FailureKind.AUTHORIZATION,
        FailureKind.INVALID_REQUEST,
        FailureKind.SYNTAX,
        FailureKind.ASSERTION,
        FailureKind.DEPENDENCY,
        FailureKind.POLICY_DENIED,
        FailureKind.PLUGIN,
        FailureKind.CAPABILITY,
        FailureKind.PLANNING,
    }
)

# Kinds that are plainly transient. Everything else is UNKNOWN retryability
# unless a code rule says otherwise.
_RETRYABLE_KINDS = frozenset(
    {
        FailureKind.NETWORK,
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMIT,
        FailureKind.PROVIDER_OUTAGE,
        FailureKind.RESOURCE_EXHAUSTION,
        FailureKind.WORKFLOW,
        FailureKind.BROWSER,
        FailureKind.DATA_QUALITY,
    }
)

# Stable mapping from the model runtime's `ErrorClass` values (and the tools
# runtime's effect codes) onto the shared vocabulary.
_CODE_KINDS: dict[str, FailureKind] = {
    # model_runtime.errors.ErrorClass
    "authentication_error": FailureKind.AUTHENTICATION,
    "authorization_error": FailureKind.AUTHORIZATION,
    "invalid_request": FailureKind.INVALID_REQUEST,
    "rate_limit": FailureKind.RATE_LIMIT,
    "timeout": FailureKind.TIMEOUT,
    "network_error": FailureKind.NETWORK,
    "server_error": FailureKind.PROVIDER_OUTAGE,
    "context_overflow": FailureKind.RESOURCE_EXHAUSTION,
    "capability_error": FailureKind.CAPABILITY,
    "content_policy_error": FailureKind.POLICY_DENIED,
    "model_unavailable": FailureKind.PROVIDER_OUTAGE,
    "provider_unavailable": FailureKind.PROVIDER_OUTAGE,
    "structured_output_error": FailureKind.INVALID_REQUEST,
    "tool_call_error": FailureKind.RUNTIME,
    "unknown_error": FailureKind.UNKNOWN,
    # orchestration.retry / tools runtime UPPER-case codes
    "tool_timeout": FailureKind.TIMEOUT,
    "provider_timeout": FailureKind.TIMEOUT,
    "task_timeout": FailureKind.TIMEOUT,
    "provider_error": FailureKind.PROVIDER_OUTAGE,
    "provider_unavailable": FailureKind.PROVIDER_OUTAGE,
    "provider_not_configured": FailureKind.CAPABILITY,
    "rate_limited": FailureKind.RATE_LIMIT,
    "network_error": FailureKind.NETWORK,
    "database_busy": FailureKind.RESOURCE_EXHAUSTION,
    "database_unavailable": FailureKind.NETWORK,
    "temporary_failure": FailureKind.UNKNOWN,
    "worker_lost": FailureKind.WORKFLOW,
    "lease_expired": FailureKind.WORKFLOW,
    "invalid_input": FailureKind.INVALID_REQUEST,
    "invalid_arguments": FailureKind.INVALID_REQUEST,
    "tool_validation_failed": FailureKind.INVALID_REQUEST,
    "tool_not_found": FailureKind.CAPABILITY,
    "tool_forbidden": FailureKind.AUTHORIZATION,
    "permission_denied": FailureKind.AUTHORIZATION,
    "auth_error": FailureKind.AUTHENTICATION,
    "security_blocked": FailureKind.POLICY_DENIED,
    # Round 4: a UI request named a capability the catalog cannot satisfy.
    "ui_capability_gap": FailureKind.CAPABILITY,
    "cancelled": FailureKind.UNKNOWN,
    "deterministic_error": FailureKind.UNKNOWN,
    "tool_budget_exceeded": FailureKind.RESOURCE_EXHAUSTION,
    "tool_error": FailureKind.RUNTIME,
    # execution.models.ErrorClass
    "user_code_error": FailureKind.SYNTAX,
    "build_error": FailureKind.SYNTAX,
    "test_error": FailureKind.ASSERTION,
    "runtime_error": FailureKind.RUNTIME,
    "infrastructure_error": FailureKind.NETWORK,
    "security_error": FailureKind.POLICY_DENIED,
    "resource_limit": FailureKind.RESOURCE_EXHAUSTION,
    # workflow / plugin / planning seams
    "workflow_failed": FailureKind.WORKFLOW,
    "plugin_failed": FailureKind.PLUGIN,
    "plugin_health_failed": FailureKind.PLUGIN,
    "planning_failed": FailureKind.PLANNING,
    "no_progress": FailureKind.NO_PROGRESS,
    "hash_stagnation": FailureKind.NO_PROGRESS,
    "loop_detected": FailureKind.NO_PROGRESS,
}

# Bounded message patterns consulted only when no code matched. Ordered: the
# more specific kinds precede the generic ones.
_MESSAGE_RULES: tuple[tuple[FailureKind, tuple[str, ...]], ...] = (
    (FailureKind.RATE_LIMIT, ("rate limit", "too many requests", "429", "quota exceeded")),
    (FailureKind.AUTHENTICATION, ("api key", "unauthorized", "authentication", "401", "no auth")),
    (FailureKind.AUTHORIZATION, ("permission denied", "forbidden", "not allowed", "403", "access denied")),
    (FailureKind.TIMEOUT, ("timed out", "timeout", "deadline exceeded", "deadline")),
    (FailureKind.RESOURCE_EXHAUSTION, (
        "context length", "context window", "too many tokens", "out of memory",
        "resource_exhausted", "budget exceeded",
    )),
    (FailureKind.NETWORK, (
        "connection refused", "connection reset", "network", "dns", "unreachable",
        "socket", "ssl", "tls",
    )),
    (FailureKind.DEPENDENCY, (
        "module not found", "no module named", "cannot find package", "missing dependency",
        "modulenotfounderror", "importerror",
    )),
    (FailureKind.SYNTAX, ("syntaxerror", "syntax error", "unexpected token", "parse error")),
    (FailureKind.ASSERTION, ("assertionerror", "assertion failed", "test failed", "expected")),
    (FailureKind.BROWSER, ("element not found", "navigation", "locator", "selector", "no such element")),
    (FailureKind.PLUGIN, ("plugin", "manifest", "contribution")),
    (FailureKind.CAPABILITY, (
        "no registered component", "capability gap", "no component matches",
        "not in the catalog",
    )),
    (FailureKind.DATA_QUALITY, ("stale", "no data", "missing data", "data quality", "unavailable")),
    (FailureKind.PROVIDER_OUTAGE, (
        "internal server", "server error", "bad gateway", "service unavailable",
        "overloaded", "500", "502", "503", "504",
    )),
    (FailureKind.INVALID_REQUEST, ("invalid request", "bad request", "validation", "malformed", "400")),
)

_CODE_RETRYABILITY: dict[str, Retryability] = {
    "cancelled": Retryability.NON_RETRYABLE,
    "security_blocked": Retryability.NON_RETRYABLE,
    "tool_budget_exceeded": Retryability.NON_RETRYABLE,
}


def _norm_code(code: Optional[str]) -> str:
    return (code or "").strip().lower()


def classify(code: Optional[str], message: Optional[str] = None) -> FailureKind:
    """The failure kind for a code, falling back to a message scan, then UNKNOWN.

    A structured code always wins over message text (spec §6.1): a caller that
    already normalized an error must not have that decision overridden by a
    coincidental word in the message.
    """
    key = _norm_code(code)
    if key in _CODE_KINDS:
        return _CODE_KINDS[key]
    lowered = (message or "").lower()
    for kind, needles in _MESSAGE_RULES:
        if any(needle in lowered for needle in needles):
            return kind
    return FailureKind.UNKNOWN


def retryability_for(code: Optional[str], kind: FailureKind) -> Retryability:
    """Whether the SAME operation could succeed on retry, given the kind."""
    key = _norm_code(code)
    if key in _CODE_RETRYABILITY:
        return _CODE_RETRYABILITY[key]
    if kind in _NON_RETRYABLE_KINDS:
        return Retryability.NON_RETRYABLE
    if kind in _RETRYABLE_KINDS:
        return Retryability.RETRYABLE
    return Retryability.UNKNOWN


@dataclass(frozen=True)
class NormalizedFailure:
    """A failure described in the shared vocabulary, safe to persist and display."""

    kind: FailureKind
    retryability: Retryability
    code: str
    message: str
    subsystem: str
    source: str
    signature: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def retryable(self) -> bool:
        # UNKNOWN is treated as potentially retryable: an unrecognized transient
        # fault must not be permanently mislabelled as non-retryable. Only an
        # explicit NON_RETRYABLE classification blocks a retry.
        return self.retryability != Retryability.NON_RETRYABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "retryability": self.retryability.value,
            "retryable": self.retryable,
            "code": self.code,
            "message": self.message,
            "subsystem": self.subsystem,
            "source": self.source,
            "signature": self.signature,
            "details": dict(self.details),
        }


def normalize_failure(
    *,
    code: Optional[str] = None,
    message: Optional[str] = None,
    subsystem: str = "harness",
    source: str = "unknown",
    location: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    max_message: int = 500,
) -> NormalizedFailure:
    """Classify a bounded failure description into the shared vocabulary.

    `location` (a file/line, node id, tool name — never a secret) participates in
    the signature only; `details` is retained as-is for diagnostics. The message
    is truncated so an unbounded provider payload can never bloat a durable row.
    """
    from .signature import failure_signature  # local import avoids a cycle

    kind = classify(code, message)
    retryability = retryability_for(code, kind)
    text = (message or "").strip()
    if len(text) > max_message:
        text = text[:max_message]
    signature = failure_signature(
        kind=kind, code=code or "", source=source, subsystem=subsystem,
        location=location, message=text,
    )
    return NormalizedFailure(
        kind=kind,
        retryability=retryability,
        code=str(code or ""),
        message=text,
        subsystem=subsystem,
        source=source,
        signature=signature,
        details=dict(details or {}),
    )


__all__ = [
    "FailureKind",
    "NormalizedFailure",
    "Retryability",
    "classify",
    "normalize_failure",
    "retryability_for",
]
