"""Model Runtime — the provider-agnostic model layer of Eclipse.

    Agent → ModelRuntime → ModelRouter → ProviderAdapter → Provider

The rest of Eclipse communicates only with `ModelRuntime` (and its normalized
types). No agent, tool, memory or financial logic should import a provider SDK
or construct a provider client.

This package REUSES the existing `harness.models` provider definitions
(`PROVIDER_CATALOG`, context windows, overflow classification) as its low-level
adapter data, so there is one source of truth for provider facts and one model
construction path (`build_chat_model`).
"""

from __future__ import annotations

from .errors import ErrorClass, ModelError, classify_exception, local_endpoint, provider_failure_message
from .catalog import ALIASES, TASK_PROFILES
from .registry import (
    CapabilityRegistry,
    ModelRegistry,
    PricingRegistry,
    ProviderRegistry,
    build_default_registries,
)
from .routing import (
    ModelRouter,
    RouteCandidate,
    RoutingDecision,
    RoutingPolicy,
    RoutingRequirements,
    TaskProfiles,
)
from .runtime import ModelRuntime, Resolution, extract_usage, get_runtime, set_runtime
from .health import (
    CircuitBreaker,
    CircuitState,
    HealthManager,
    RateLimitManager,
)
from .structured import SchemaValidator, StructuredOutputManager, StructuredResult
from .types import (
    CAPABILITY_KEYS,
    CapabilityState,
    ChatRequest,
    CostEstimate,
    ModelCapabilities,
    ModelInfo,
    ModelPerformance,
    ModelPricing,
    ModelResponse,
    PricingKind,
    ProviderInfo,
    ReasoningRequest,
    StreamEvent,
    ToolCall,
    ToolSchema,
    Usage,
)
from .usage import (
    Budget,
    BudgetManager,
    CostTracker,
    LatencyTracker,
    UsageRecord,
    UsageStore,
)

__all__ = [
    "ALIASES",
    "Budget",
    "BudgetManager",
    "CAPABILITY_KEYS",
    "CapabilityRegistry",
    "CapabilityState",
    "ChatRequest",
    "CircuitBreaker",
    "CircuitState",
    "CostEstimate",
    "CostTracker",
    "ErrorClass",
    "HealthManager",
    "LatencyTracker",
    "ModelCapabilities",
    "ModelError",
    "ModelInfo",
    "ModelPerformance",
    "ModelPricing",
    "ModelRegistry",
    "ModelResponse",
    "ModelRouter",
    "ModelRuntime",
    "PricingKind",
    "PricingRegistry",
    "ProviderInfo",
    "ProviderRegistry",
    "RateLimitManager",
    "ReasoningRequest",
    "Resolution",
    "RouteCandidate",
    "RoutingDecision",
    "RoutingPolicy",
    "RoutingRequirements",
    "SchemaValidator",
    "StreamEvent",
    "StructuredOutputManager",
    "StructuredResult",
    "TaskProfiles",
    "ToolCall",
    "ToolSchema",
    "Usage",
    "UsageRecord",
    "UsageStore",
    "build_default_registries",
    "classify_exception",
    "extract_usage",
    "get_runtime",
    "local_endpoint",
    "provider_failure_message",
    "set_runtime",
]
