"""Provider-neutral data contracts for the model runtime.

Nothing here names a provider SDK. A `ModelInfo`, a `ChatRequest`, and a
`ModelResponse` mean the same thing whatever provider served them. Provider
adapters translate to and from these shapes; the agent sees only these.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


class CapabilityState(str, enum.Enum):
    """A three-plus-one state for every capability (spec §6).

    `UNKNOWN` is a first-class answer: when neither provider metadata nor a
    probe can decide, the runtime says so rather than guessing.
    """

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


# The normalized capability vocabulary (spec §5). Every flag is optional and
# absent means UNKNOWN, never False.
CAPABILITY_KEYS: tuple[str, ...] = (
    "text",
    "vision",
    "tool_calling",
    "structured_output",
    "reasoning",
    "long_context",
    "image_generation",
    "audio_input",
    "audio_output",
    "embeddings",
    "streaming",
    "parallel_tool_calls",
    "computer_use",
    "code_execution",
)


@dataclass
class ModelCapabilities:
    """Capabilities as states, never bare booleans."""

    states: dict[str, CapabilityState] = field(default_factory=dict)

    def state(self, key: str) -> CapabilityState:
        return self.states.get(key, CapabilityState.UNKNOWN)

    def is_supported(self, key: str) -> bool:
        return self.state(key) is CapabilityState.SUPPORTED

    def supports_all(self, keys: list[str]) -> bool:
        """True only when every required key is explicitly SUPPORTED.

        A required capability that is UNKNOWN does NOT satisfy the requirement,
        so the router prefers a model that is known-good.
        """
        return all(self.is_supported(k) for k in keys)

    def with_state(self, key: str, state: CapabilityState) -> "ModelCapabilities":
        merged = dict(self.states)
        merged[key] = state
        return ModelCapabilities(merged)

    def degraded_or_unsupported(self) -> list[str]:
        return [
            k
            for k, s in self.states.items()
            if s in (CapabilityState.DEGRADED, CapabilityState.UNSUPPORTED)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "states": {k: s.value for k, s in self.states.items()},
            "supported": [k for k, s in self.states.items() if s is CapabilityState.SUPPORTED],
            "degraded": [k for k, s in self.states.items() if s is CapabilityState.DEGRADED],
            "unsupported": [k for k, s in self.states.items() if s is CapabilityState.UNSUPPORTED],
            "unknown": [k for k, s in self.states.items() if s is CapabilityState.UNKNOWN],
        }


class PricingKind(str, enum.Enum):
    PER_TOKEN = "per_token"
    PER_REQUEST = "per_request"
    FREE = "free"
    UNKNOWN = "unknown"
    CUSTOM = "custom"


@dataclass
class ModelPricing:
    """Declared pricing. Unknown is `UNKNOWN`, never an invented number."""

    kind: PricingKind = PricingKind.UNKNOWN
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None
    cached_input_per_million: Optional[float] = None
    per_request: Optional[float] = None
    currency: str = "USD"
    source: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "inputPerMillion": self.input_per_million,
            "outputPerMillion": self.output_per_million,
            "cachedInputPerMillion": self.cached_input_per_million,
            "perRequest": self.per_request,
            "currency": self.currency,
            "source": self.source,
        }


@dataclass
class ModelPerformance:
    """Static, declared quality signals used for routing (not fabricated).

    These are coarse 0..1 quality priors declared per model family, combined
    with live health. They are deliberately not precise benchmark claims.
    """

    quality: Optional[float] = None
    reasoning: Optional[float] = None
    coding: Optional[float] = None
    tool_use: Optional[float] = None
    speed: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality": self.quality,
            "reasoning": self.reasoning,
            "coding": self.coding,
            "toolUse": self.tool_use,
            "speed": self.speed,
        }


@dataclass
class ModelInfo:
    """The normalized model definition (spec §4)."""

    id: str
    provider_id: str
    display_name: str = ""
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    pricing: ModelPricing = field(default_factory=ModelPricing)
    performance: ModelPerformance = field(default_factory=ModelPerformance)
    status: Literal["active", "deprecated", "unavailable"] = "active"
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_id(self) -> str:
        return f"{self.provider_id}/{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "providerId": self.provider_id,
            "qualifiedId": self.qualified_id,
            "displayName": self.display_name or self.id,
            "capabilities": self.capabilities.to_dict(),
            "contextWindow": self.context_window,
            "maxOutputTokens": self.max_output_tokens,
            "pricing": self.pricing.to_dict(),
            "performance": self.performance.to_dict(),
            "status": self.status,
            "aliases": list(self.aliases),
            "metadata": dict(self.metadata),
        }


@dataclass
class ProviderInfo:
    id: str
    label: str
    kind: str
    enabled: bool = True
    keyless: bool = False
    openai_compatible: bool = False
    default_base_url: Optional[str] = None
    dynamic_discovery: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "enabled": self.enabled,
            "keyless": self.keyless,
            "openaiCompatible": self.openai_compatible,
            "defaultBaseUrl": self.default_base_url,
            "dynamicDiscovery": self.dynamic_discovery,
            "metadata": dict(self.metadata),
        }


# ── Requests / responses ────────────────────────────────────────────────────


@dataclass
class ToolSchema:
    """The provider-neutral tool schema (spec §27)."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


@dataclass
class ReasoningRequest:
    """Normalized reasoning request (spec §30)."""

    enabled: bool = False
    effort: Optional[Literal["low", "medium", "high", "max"]] = None
    max_tokens: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "effort": self.effort, "maxTokens": self.max_tokens}


@dataclass
class ChatRequest:
    """A provider-neutral generation request.

    `messages` are LangChain `BaseMessage` objects at the runtime boundary —
    the same objects the graph already builds — so no lossy conversion is
    introduced. Provider adapters consume them directly.
    """

    messages: list[Any]
    tools: list[ToolSchema] = field(default_factory=list)
    model: Optional[str] = None
    task: Optional[str] = None
    requirements: dict[str, Any] = field(default_factory=dict)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning: Optional[ReasoningRequest] = None
    response_schema: Optional[dict[str, Any]] = None
    # Routing overrides (spec §44). `allowed_providers` / `local_only` /
    # `prefer_free` narrow the candidates before scoring.
    policy_overrides: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False

    def normalized(self) -> "Usage":
        total = self.total_tokens or (self.input_tokens + self.output_tokens)
        return Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cached_tokens=self.cached_tokens,
            total_tokens=total,
            estimated=self.estimated,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cachedTokens": self.cached_tokens,
            "totalTokens": self.total_tokens,
            "estimated": self.estimated,
        }


@dataclass
class CostEstimate:
    input_cost: Optional[float] = None
    output_cost: Optional[float] = None
    cached_input_cost: Optional[float] = None
    total_cost: Optional[float] = None
    currency: str = "USD"
    kind: str = "unknown"
    estimated: bool = False
    basis: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputCost": self.input_cost,
            "outputCost": self.output_cost,
            "cachedInputCost": self.cached_input_cost,
            "totalCost": self.total_cost,
            "currency": self.currency,
            "kind": self.kind,
            "estimated": self.estimated,
            "basis": self.basis,
        }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """A normalized response. `raw` is the provider object for the graph seam."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: Optional[str] = None
    usage: Usage = field(default_factory=Usage)
    cost: Optional[CostEstimate] = None
    model_id: str = ""
    provider_id: str = ""
    finish_reason: Optional[str] = None
    raw: Any = None
    decision: Optional[dict[str, Any]] = None


# ── Streaming (spec §29) ────────────────────────────────────────────────────


@dataclass
class StreamEvent:
    """One normalized stream event.

    `type` is one of: `text_delta`, `reasoning_delta`, `tool_call_start`,
    `tool_call_delta`, `tool_call_end`, `usage`, `error`, `done`.
    """

    type: str
    text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    tool_call_id: Optional[str] = None
    usage: Optional[Usage] = None
    error: Optional[dict[str, Any]] = None


# ── W1 gateway contracts ─────────────────────────────────────────────────────
# These live in `types.py` so `ModelRuntime` can return them without importing
# the gateway facade (which imports the runtime). `gateway.py` re-exports them.

@dataclass
class Candidate:
    """One reachable model candidate in the gateway plan."""

    provider: str
    model: str
    index: int
    reason: str = "primary"          # primary | fallback | explicit
    credential_id: Optional[str] = None
    context_window: Optional[int] = None
    score: Optional[float] = None
    model_info: Optional[ModelInfo] = None
    built: Any = None                 # prebuilt primary model, when usable
    credential: Any = None            # Credential, never serialized

    @property
    def qualified_id(self) -> str:
        return f"{self.provider}/{self.model}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "index": self.index,
            "reason": self.reason,
            "credentialId": self.credential_id,
            "contextWindow": self.context_window,
            "score": None if self.score is None else round(self.score, 4),
        }


@dataclass
class Attempt:
    """One physical model attempt (one provider request)."""

    provider: str
    model: str
    index: int
    attempt: int
    outcome: str                       # completed | failed | skipped
    reason: str = ""
    error_class: Optional[str] = None
    status_code: Optional[int] = None
    latency_ms: int = 0
    ttft_ms: Optional[int] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    priced: bool = False
    retryable: bool = False
    will_retry: bool = False
    will_fallback: bool = False
    credential_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "index": self.index,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "reason": self.reason,
            "errorClass": self.error_class,
            "statusCode": self.status_code,
            "latencyMs": self.latency_ms,
            "ttftMs": self.ttft_ms,
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
            "costUsd": self.cost_usd,
            "priced": self.priced,
            "retryable": self.retryable,
            "willRetry": self.will_retry,
            "willFallback": self.will_fallback,
            "credentialId": self.credential_id,
        }


@dataclass
class GatewayResult:
    """The final response plus the full physical-attempt trace."""

    response: Any
    attempts: tuple[Attempt, ...] = ()
    fallback_used: bool = False
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    priced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fallbackUsed": self.fallback_used,
            "totalTokens": self.total_tokens,
            "costUsd": self.cost_usd,
            "priced": self.priced,
            "attempts": [a.to_dict() for a in self.attempts],
        }


__all__ = [
    "CAPABILITY_KEYS",
    "CapabilityState",
    "ChatRequest",
    "CostEstimate",
    "ModelCapabilities",
    "ModelInfo",
    "ModelPerformance",
    "ModelPricing",
    "ModelResponse",
    "PricingKind",
    "ProviderInfo",
    "ReasoningRequest",
    "StreamEvent",
    "ToolCall",
    "ToolSchema",
    "Usage",
    "Candidate",
    "Attempt",
    "GatewayResult",
]
