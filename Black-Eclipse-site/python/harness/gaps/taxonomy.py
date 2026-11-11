"""The refusal taxonomy: every dead end names WHAT is missing.

A run may stop for very different reasons. Treating them all as "can't" is the
defect this package fixes. The classes below decide the ROUTE, never widen a
permission:

  * ``capability_missing`` — the tool/recipe/skill does not exist -> offer to build
  * ``context_denied``     — it exists, but this run/profile/workspace cannot use it
                             -> offer the permitted surface (chat tool, code task)
  * ``not_configured``     — the runtime piece (sandbox, skill registry) is off
                             -> offer the setup step
  * ``malformed``          — bad arguments -> self-repair, never an offer
  * ``transient``          — timeout/rate-limit -> the recovery hot path retries
  * ``safety_denied``      — protected path/secret/finance guardrail -> explain,
                             NEVER offer to bypass
  * ``user_denied``        — the operator already said no -> stay quiet
  * ``unknown``            — unclassified -> no offer (do not nag on noise)

Only the first three are OFFERABLE. A safety denial is final.
"""

from __future__ import annotations

from typing import Optional

CAPABILITY_MISSING = "capability_missing"
CONTEXT_DENIED = "context_denied"
NOT_CONFIGURED = "not_configured"
MALFORMED = "malformed"
TRANSIENT = "transient"
SAFETY_DENIED = "safety_denied"
USER_DENIED = "user_denied"
UNKNOWN = "unknown"

OFFERABLE = frozenset({CAPABILITY_MISSING, CONTEXT_DENIED, NOT_CONFIGURED})

# Codes the runtime already uses. A code missing here falls through to the
# reason heuristics below, then to UNKNOWN (never guessed into an offer).
_CAPABILITY_CODES = frozenset({
    "CAPABILITY_MISSING", "KIT_UNKNOWN", "KIT_INPUT_MISSING", "UI_CAPABILITY_GAP",
    "RECIPE_NOT_FOUND", "TOOL_NOT_REGISTERED", "SKILL_NOT_FOUND",
    "CAPABILITY_NOT_FOUND", "NO_SUCH_TOOL", "NO_SUCH_RECIPE",
    "UNROUTED_REFUSAL",
})
_CONTEXT_CODES = frozenset({
    "PROFILE_DENIED", "WORKSPACE_UNBOUND", "TOOL_FORBIDDEN", "OUTSIDE_WORKSPACE",
    "COMMAND_NOT_ALLOWLISTED", "TOOL_NOT_ALLOWED", "NOT_ALLOWED",
    "WORKSPACE_UNAVAILABLE", "SANDBOX_UNAVAILABLE_FOR_PROFILE",
})
_CONFIG_CODES = frozenset({
    "ANALYSIS_NOT_ENABLED", "SANDBOX_UNAVAILABLE", "SKILLS_UNAVAILABLE",
    "NOT_CONFIGURED", "MISSING_KEY", "PROVIDER_NOT_CONFIGURED",
    "PYTHON_UNAVAILABLE", "RUNTIME_UNAVAILABLE",
})
_MALFORMED_CODES = frozenset({
    "INPUT_INVALID", "TOOL_ARGS_INVALID", "INVALID_REQUEST", "MANIFEST_INVALID",
    "SCHEMA_INVALID", "PATH_DENIED_INVALID",
})
_TRANSIENT_CODES = frozenset({
    "TOOL_TIMEOUT", "TIMEOUT", "RATE_LIMITED", "PROVIDER_ERROR",
    "PROVIDER_TIMEOUT", "SANDBOX_TIMEOUT", "UNAVAILABLE", "NETWORK_ERROR",
    "CONNECTION_ERROR", "TOOL_ERROR",
})
_SAFETY_CODES = frozenset({
    "PROTECTED_PATH", "POLICY_DENIED", "SECRET_DENIED", "FINANCE_GUARDRAIL",
    "MANDATE_DENIED", "KILL_SWITCH", "NETWORK_DENIED", "SSRF_BLOCKED",
    "HARD_DENY", "SECURITY_FLOOR", "TRADING_GATE", "APPROVAL_DENIED",
})
_USER_DENIED_CODES = frozenset({
    "DENIED_BY_USER", "USER_DENIED", "APPROVAL_REJECTED", "CANCELLED_BY_USER",
})


def _norm(code: Optional[str]) -> str:
    return str(code or "").strip().upper()


def classify(code: Optional[str], reason: Optional[str] = "") -> str:
    """The class of one failure. Deterministic; never raises."""
    key = _norm(code)
    if key in _USER_DENIED_CODES:
        return USER_DENIED
    if key in _SAFETY_CODES:
        return SAFETY_DENIED
    if key in _CONTEXT_CODES:
        return CONTEXT_DENIED
    if key in _CAPABILITY_CODES:
        return CAPABILITY_MISSING
    if key in _CONFIG_CODES:
        return NOT_CONFIGURED
    if key in _MALFORMED_CODES:
        return MALFORMED
    if key in _TRANSIENT_CODES:
        return TRANSIENT

    text = str(reason or "").lower()
    # A reason may be the only signal (some tools return a plain refusal text).
    # Order matters: safety first, so a security denial is never softened.
    if any(word in text for word in (
        "protected path", "secret", "guardrail", "security floor", "hard deny",
        "not permitted by policy", "blocked by policy",
    )):
        return SAFETY_DENIED
    if any(word in text for word in (
        "not allowed for this run", "profile does not grant", "permission",
        "no project folder", "workspace is not bound", "outside the workspace",
    )):
        return CONTEXT_DENIED
    if any(word in text for word in (
        "no ready-made shape", "unknown tool", "no such tool", "no such recipe",
        "not registered", "does not exist", "is not available in this run",
    )):
        return CAPABILITY_MISSING
    if any(word in text for word in (
        "timed out", "timeout", "rate limit", "temporarily unavailable",
        "connection", "try again",
    )):
        return TRANSIENT
    return UNKNOWN


def is_offerable(kind: str) -> bool:
    return kind in OFFERABLE


_REFUSAL_MARKERS = (
    "i can't ", "i cannot ", "i can’t ", "i'm unable", "i am unable",
    "i don't have the ability", "i do not have the ability",
    "there is no capability", "there isn't a capability",
    "no scheduler capability", "not available in this run",
    "isn't available in this run", "cannot do that", "can't do that",
)

# A first-person "can't" is often an epistemic caveat, not a refusal. Those
# answers are ordinary analysis and must never be relabelled as a gap.
_HEDGES = (
    "guarantee", "promise", "be sure", "predict", "for certain", "confirm",
    "know for certain", "comment on", "say whether", "tell you whether",
    "ruled out", "be certain",
)


def looks_like_bare_refusal(text: str, *, tool_calls: int = 0) -> bool:
    """A short first-person refusal with NO tool call behind it.

    The tool-result path is the reliable one. This catches the other shape: the
    model simply answers "I can't" without trying. It is deliberately narrow —
    a long analysis that mentions a limitation must not be relabelled.
    """
    body = str(text or "").strip()
    if not body or len(body) > 700 or tool_calls > 0:
        return False
    lowered = body.lower()
    if any(hedge in lowered for hedge in _HEDGES):
        return False
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


__all__ = [
    "CAPABILITY_MISSING",
    "CONTEXT_DENIED",
    "NOT_CONFIGURED",
    "MALFORMED",
    "TRANSIENT",
    "SAFETY_DENIED",
    "USER_DENIED",
    "UNKNOWN",
    "OFFERABLE",
    "classify",
    "is_offerable",
    "looks_like_bare_refusal",
]
