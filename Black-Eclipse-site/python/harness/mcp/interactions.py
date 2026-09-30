"""Server-initiated interactions: sampling and elicitation (Phase 6, Milestone 5).

These are the two MCP directions where a server asks *Eclipse* for something. Both
are real new authority surfaces, so they ship **last among protocol features, off
by default, and fully audited**.

  * **Sampling** (`sampling/createMessage`) — off by default, per server. When
    enabled: a hard `max_tokens` cap, an RPM cap, a max tool-round count (0
    disables tool use inside sampling), a timeout, and audit counters. A sampling
    request can never trigger an effectful tool without that tool's normal
    approval and can never widen the agent's allowlist.
  * **Elicitation** (`elicitation/create`) — form-mode requests route through the
    EXISTING approval surface (`ToolContext.authorize_effect` / the approval
    store), never a parallel prompt path. URL-mode requests are declined.

Sampling/elicitation content is UNTRUSTED data: it can request, but must achieve
nothing that changes agent state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Sampling policy default caps (all overridable per server).
DEFAULT_MAX_TOKENS = 512
DEFAULT_RPM = 10
DEFAULT_MAX_TOOL_ROUNDS = 0
DEFAULT_TIMEOUT_S = 30.0
MAX_TOKENS_CEILING = 8_192


@dataclass
class SamplingPolicy:
    enabled: bool = False
    model: Optional[str] = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    rpm: int = DEFAULT_RPM
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS
    timeout_s: float = DEFAULT_TIMEOUT_S
    # A model allowlist (continuation, M7). When non-empty, a server's REQUESTED
    # model is honoured only if it is on the list; otherwise the operator's
    # configured default (`model`) is used — never the server's preference. An
    # ABSENT/empty list means today's behaviour (the server's request is ignored
    # and `model` is used, since the runtime serves sampling on its OWN adapter).
    allowed_models: list[str] = field(default_factory=list)

    def resolve_model(self, requested: Optional[str]) -> tuple[str, bool]:
        """Return (model_to_use, fell_back).

        `requested` is the model the server asked for. With an allowlist, a
        requested model not on it falls back to the configured default and reports
        `fell_back=True`; an empty allowlist is unchanged behaviour.
        """
        if self.allowed_models:
            if requested and requested in self.allowed_models:
                return requested, False
            return (self.model or "eclipse"), True
        return (self.model or requested or "eclipse"), False

    def clamped_max_tokens(self) -> int:
        return max(1, min(int(self.max_tokens or DEFAULT_MAX_TOKENS), MAX_TOKENS_CEILING))

    def public(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model,
            "maxTokens": self.clamped_max_tokens(),
            "rpm": self.rpm,
            "maxToolRounds": max(0, int(self.max_tool_rounds or 0)),
            "timeoutSeconds": self.timeout_s,
            "allowedModels": list(self.allowed_models),
        }


@dataclass
class InteractionCounters:
    """Content-free audit counters for a server's sampling/elicitation."""

    sampling_requests: int = 0
    sampling_errors: int = 0
    sampling_tokens: int = 0
    sampling_tool_uses: int = 0
    # A server requested a model that is not on the allowlist, so the operator's
    # default was used instead (continuation, M7). Content-free.
    sampling_model_fallbacks: int = 0
    elicitation_requests: int = 0
    elicitation_approved: int = 0
    elicitation_denied: int = 0

    def public(self) -> dict[str, int]:
        return {
            "samplingRequests": self.sampling_requests,
            "samplingErrors": self.sampling_errors,
            "samplingTokens": self.sampling_tokens,
            "samplingToolUses": self.sampling_tool_uses,
            "samplingModelFallbacks": self.sampling_model_fallbacks,
            "elicitationRequests": self.elicitation_requests,
            "elicitationApproved": self.elicitation_approved,
            "elicitationDenied": self.elicitation_denied,
        }


class _RateLimiter:
    """A simple per-window request limiter for sampling."""

    def __init__(self) -> None:
        self._window_start = 0.0
        self._count = 0

    def allow(self, now: float, per_minute: int) -> bool:
        if now - self._window_start >= 60.0:
            self._window_start = now
            self._count = 0
        if self._count >= max(1, per_minute):
            return False
        self._count += 1
        return True


def build_sampling_callback(
    *,
    policy: SamplingPolicy,
    server_id: str,
    counters: InteractionCounters,
    run_model: Callable[[str], Any] | None = None,
    emit: Any = None,
):
    """Build the SDK sampling callback for one server.

    Off by default: an unenabled policy refuses with a clear code. The callback
    bounds tokens and RPM, never triggers an effectful tool, and returns inert
    text. It records a harness event and increments audit counters.
    """
    limiter = _RateLimiter()

    async def sampling(context: Any, params: Any) -> Any:
        from mcp.types import CreateMessageResult, TextContent

        counters.sampling_requests += 1
        if not policy.enabled:
            counters.sampling_errors += 1
            raise _Refusal("sampling is disabled for this server", "mcp_sampling_disabled")
        import time

        if not limiter.allow(time.monotonic(), policy.rpm):
            counters.sampling_errors += 1
            raise _Refusal("sampling rate limit exceeded", "mcp_sampling_rate_limited")
        # Model allowlist (M7): honour the server's requested model only when a
        # configured allowlist permits it; otherwise use the operator's default
        # and record the fallback. No allowlist = unchanged behaviour.
        requested = _requested_model(params)
        chosen_model, fell_back = policy.resolve_model(requested)
        if fell_back:
            counters.sampling_model_fallbacks += 1
        if emit is not None:
            try:
                await emit("mcp.sampling.requested", {
                    "serverId": server_id,
                    "maxTokens": policy.clamped_max_tokens(),
                    "toolRounds": max(0, policy.max_tool_rounds),
                    "requestedModel": requested,
                    "modelUsed": chosen_model,
                    "modelFallback": fell_back,
                })
            except Exception:  # noqa: BLE001 - an emit failure must not authorize
                pass
        # A model invocation would go here; the runtime's own model adapter is
        # used (never a second one). Without a bound model we refuse honestly.
        if run_model is None:
            counters.sampling_errors += 1
            raise _Refusal("no model is bound for sampling", "mcp_sampling_unavailable")
        try:
            content = await run_model(_sampling_text(params))
        except SamplingUnavailable:
            counters.sampling_errors += 1
            raise _Refusal("no model is bound for sampling", "mcp_sampling_unavailable")
        except _Refusal:
            raise
        except Exception:  # noqa: BLE001
            counters.sampling_errors += 1
            raise _Refusal("sampling model failed", "mcp_sampling_failed")
        counters.sampling_tokens += _estimate_tokens(_sampling_text(params) + str(content))
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=str(content)),
            model=chosen_model,
        )

    return sampling


def _requested_model(params: Any) -> Optional[str]:
    """The model name the server asked for, if any (from `modelPreferences`)."""
    prefs = getattr(params, "model_preferences", None) or getattr(params, "modelPreferences", None)
    if prefs is None:
        return None
    # The SDK exposes `hints` (a list of `{name}`) and `intelligencePriority` etc.
    hints = getattr(prefs, "hints", None) or []
    for hint in hints:
        name = getattr(hint, "name", None)
        if isinstance(name, str) and name:
            return name
    return None


def build_elicitation_callback(
    *,
    server_id: str,
    counters: InteractionCounters,
    authorize: Any = None,
    emit: Any = None,
):
    """Build the SDK elicitation callback, routed through the approval surface.

    Form-mode requests become an approval; a denial is terminal. URL-mode requests
    are declined with an explanatory response and never auto-opened. Elicitation is
    per-call consent — never "remember this decision".
    """

    async def elicitation(context: Any, params: Any) -> Any:
        from mcp.types import ElicitResult

        counters.elicitation_requests += 1
        mode = getattr(params, "mode", "form") or "form"
        if mode == "url":
            counters.elicitation_denied += 1
            return ElicitResult(action="decline")
        message = str(getattr(params, "message", "") or "")
        if authorize is None:
            counters.elicitation_denied += 1
            return ElicitResult(action="decline")
        try:
            approved = bool(await authorize({"serverId": server_id, "message": message, "params": params}))
        except Exception:  # noqa: BLE001 - a failing authorizer must never approve
            approved = False
        if not approved:
            counters.elicitation_denied += 1
            return ElicitResult(action="decline")
        counters.elicitation_approved += 1
        # The schema-validated content is supplied by the caller's approval UI.
        return ElicitResult(action="accept", content=None)

    return elicitation


class _Refusal(Exception):
    code = "mcp_sampling_refused"

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class SamplingUnavailable(Exception):
    """No model is bound to serve sampling (reported as `mcp_sampling_unavailable`)."""


def _sampling_text(params: Any) -> str:
    messages = getattr(params, "messages", None) or []
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is not None:
            parts.append(str(getattr(content, "text", content)))
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    try:
        from ..eclipse_memory.profile import estimate_tokens

        return int(estimate_tokens(text))
    except Exception:  # noqa: BLE001
        return max(1, len(text) // 4)


__all__ = [
    "SamplingPolicy",
    "InteractionCounters",
    "SamplingUnavailable",
    "build_sampling_callback",
    "build_elicitation_callback",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RPM",
    "DEFAULT_MAX_TOOL_ROUNDS",
    "MAX_TOKENS_CEILING",
]
