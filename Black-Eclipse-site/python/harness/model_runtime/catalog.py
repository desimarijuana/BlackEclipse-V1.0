"""Static, declarative catalog data for the model runtime.

Everything here is DATA, not branches: capabilities, task profiles, aliases and
(where declared) pricing. Adding a model family is an entry, never a new code
path in the runtime or the agent.

Honesty rules:

  * **Capabilities are states, not facts.** A declaration is a PRIOR. Runtime
    probes may degrade it (see `capability.py`).
  * **Pricing is never invented.** `PRICING_CATALOG` ships nearly empty on
    purpose; an operator or the settings vault supplies real prices through
    `PricingRegistry.register`. Local providers are honestly `FREE`.
  * **Performance priors are coarse routing signals, not benchmark claims.**
    They are optional; the router also uses live health/latency.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    CapabilityState,
    ModelPerformance,
    ModelPricing,
    PricingKind,
)

# ── Capability priors ───────────────────────────────────────────────────────

# Provider-kind defaults. A model inherits these unless a model-substring
# override below applies. `UNKNOWN` entries are omitted (the runtime treats an
# absent key as UNKNOWN already).
_SUPPORTED = CapabilityState.SUPPORTED
_UNSUPPORTED = CapabilityState.UNSUPPORTED
_UNKNOWN = CapabilityState.UNKNOWN

PROVIDER_CAPABILITIES: dict[str, dict[str, CapabilityState]] = {
    "openai": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
        "structured_output": _SUPPORTED,
        "tool_calling": _SUPPORTED,
        "parallel_tool_calls": _SUPPORTED,
        "vision": _SUPPORTED,
        "embeddings": _UNKNOWN,
        "reasoning": _UNKNOWN,
    },
    "anthropic": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
        "structured_output": _SUPPORTED,
        "tool_calling": _SUPPORTED,
        "parallel_tool_calls": _SUPPORTED,
        "vision": _SUPPORTED,
        "long_context": _SUPPORTED,
        "reasoning": _UNKNOWN,
    },
    "google": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
        "structured_output": _SUPPORTED,
        "tool_calling": _SUPPORTED,
        "vision": _SUPPORTED,
        "audio_input": _SUPPORTED,
        "long_context": _SUPPORTED,
    },
    "mistral": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
        "tool_calling": _SUPPORTED,
        "structured_output": _SUPPORTED,
    },
    "groq": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
        "tool_calling": _SUPPORTED,
    },
    # A local OpenAI-compatible server: the operator's loaded model decides.
    # Only the protocol-level facts are declared; the rest stays UNKNOWN.
    "openai_compatible": {
        "text": _SUPPORTED,
        "streaming": _SUPPORTED,
    },
    # A router fronts heterogeneous models; nothing can be assumed.
    "router": {},
}

# Model-substring overrides, longest substring wins. Keyed provider-kind aware
# where the same name means different things across servers.
MODEL_CAPABILITY_OVERRIDES: dict[str, dict[str, CapabilityState]] = {
    # OpenAI reasoning models.
    "o1": {"reasoning": _SUPPORTED, "tool_calling": _SUPPORTED, "vision": _SUPPORTED},
    "o3": {"reasoning": _SUPPORTED, "tool_calling": _SUPPORTED, "vision": _SUPPORTED},
    "o4": {"reasoning": _SUPPORTED, "tool_calling": _SUPPORTED, "vision": _SUPPORTED},
    "gpt-4o": {"vision": _SUPPORTED, "tool_calling": _SUPPORTED},
    "gpt-4.1": {"vision": _SUPPORTED, "tool_calling": _SUPPORTED, "reasoning": _SUPPORTED},
    # Anthropic extended thinking.
    "claude-4": {"reasoning": _SUPPORTED, "vision": _SUPPORTED},
    "claude-3-7": {"reasoning": _SUPPORTED, "vision": _SUPPORTED},
    # Google.
    "gemini-1.5": {"long_context": _SUPPORTED, "vision": _SUPPORTED},
    "gemini-2.5": {"reasoning": _SUPPORTED, "vision": _SUPPORTED, "long_context": _SUPPORTED},
    # DeepSeek.
    "deepseek-chat": {"tool_calling": _SUPPORTED, "structured_output": _SUPPORTED},
    "deepseek-reasoner": {"reasoning": _SUPPORTED, "tool_calling": _UNSUPPORTED},
    # Open-weight reasoning.
    "r1": {"reasoning": _SUPPORTED, "tool_calling": _UNKNOWN},
    "qwq": {"reasoning": _SUPPORTED},
    "qwen3": {"reasoning": _SUPPORTED, "tool_calling": _SUPPORTED},
    # Kimi / Moonshot.
    "kimi-k2": {"reasoning": _SUPPORTED, "tool_calling": _SUPPORTED},
    "moonshot": {"tool_calling": _SUPPORTED},
    # Embedding-only families: not chat models.
    "embed": {"text": _UNSUPPORTED, "embeddings": _SUPPORTED, "tool_calling": _UNSUPPORTED},
    "bge": {"text": _UNSUPPORTED, "embeddings": _SUPPORTED, "tool_calling": _UNSUPPORTED},
    "nomic-embed": {"text": _UNSUPPORTED, "embeddings": _SUPPORTED, "tool_calling": _UNSUPPORTED},
}

# Model families that are genuinely long-context even without a per-model
# declaration (used only when the resolved window is unknown).
LONG_CONTEXT_MIN_TOKENS = 200_000


# ── Pricing (declared, never invented) ──────────────────────────────────────


def _free(source: str = "local inference") -> ModelPricing:
    return ModelPricing(kind=PricingKind.FREE, source=source)


# Deliberately sparse: only facts that are true by construction (a local model
# costs nothing). Hosted prices drift, so the runtime refuses to hardcode them;
# the operator supplies them through `PricingRegistry` (e.g. from the vault),
# and absent entries honestly report `UNKNOWN`.
PRICING_CATALOG: dict[str, ModelPricing] = {
    "ollama/*": _free(),
    "lmstudio/*": _free(),
    "local/*": _free(),
    "vllm/*": _free(),
}


# ── Performance priors (coarse, optional) ───────────────────────────────────


# Coarse prior used only as a tie-breaker. These are not benchmark claims; the
# router treats them as weak signals weighted low by default.
PERFORMANCE_PRIORS: dict[str, ModelPerformance] = {
    "o1": ModelPerformance(reasoning=0.95, coding=0.9, tool_use=0.85, quality=0.95, speed=0.35),
    "o3": ModelPerformance(reasoning=0.97, coding=0.92, tool_use=0.88, quality=0.97, speed=0.3),
    "gpt-4.1": ModelPerformance(reasoning=0.85, coding=0.9, tool_use=0.9, quality=0.9, speed=0.6),
    "gpt-4o": ModelPerformance(reasoning=0.7, coding=0.8, tool_use=0.9, quality=0.85, speed=0.7),
    "claude-4": ModelPerformance(reasoning=0.9, coding=0.92, tool_use=0.92, quality=0.92, speed=0.55),
    "claude-3-5": ModelPerformance(reasoning=0.75, coding=0.85, tool_use=0.9, quality=0.85, speed=0.7),
    "gemini-2.5": ModelPerformance(reasoning=0.88, coding=0.85, tool_use=0.85, quality=0.88, speed=0.65),
    "gemini-2.0": ModelPerformance(reasoning=0.6, coding=0.7, tool_use=0.8, quality=0.75, speed=0.85),
    "deepseek-reasoner": ModelPerformance(reasoning=0.9, coding=0.85, tool_use=0.3, quality=0.85, speed=0.4),
    "deepseek-chat": ModelPerformance(reasoning=0.65, coding=0.78, tool_use=0.75, quality=0.75, speed=0.7),
    "llama-3.3-70b": ModelPerformance(reasoning=0.6, coding=0.65, tool_use=0.7, quality=0.65, speed=0.8),
    "qwen3": ModelPerformance(reasoning=0.78, coding=0.8, tool_use=0.78, quality=0.78, speed=0.6),
    "kimi-k2": ModelPerformance(reasoning=0.82, coding=0.8, tool_use=0.8, quality=0.82, speed=0.55),
}


# ── Task profiles (spec §14) ────────────────────────────────────────────────


# A profile says what a task REQUIRES and what it PREFERS. `weights` drive the
# router's scoring; all are configurable and may be overridden by policy.
TASK_PROFILES: dict[str, dict[str, Any]] = {
    "simple_chat": {
        "required": ["text"],
        "preferred": ["streaming"],
        "weights": {"capability": 1.0, "quality": 0.3, "reliability": 0.5, "latency": 0.9, "availability": 0.6, "context": 0.2, "cost": 0.5},
        "reasoning": "low",
        "cost_sensitivity": "medium",
    },
    "coding": {
        "required": ["text", "tool_calling"],
        "preferred": ["reasoning", "structured_output"],
        "weights": {"capability": 1.4, "quality": 1.0, "reliability": 1.0, "latency": 0.4, "availability": 0.6, "context": 0.6, "cost": 0.4},
        "reasoning": "high",
        "cost_sensitivity": "medium",
    },
    "code_review": {
        "required": ["text", "reasoning"],
        "preferred": ["tool_calling", "long_context"],
        "weights": {"capability": 1.5, "quality": 1.1, "reliability": 1.0, "latency": 0.3, "availability": 0.6, "context": 0.7, "cost": 0.3},
        "reasoning": "high",
        "cost_sensitivity": "low",
    },
    "financial_research": {
        "required": ["text", "reasoning", "tool_calling"],
        "preferred": ["long_context", "structured_output"],
        "weights": {"capability": 1.6, "quality": 1.3, "reliability": 1.4, "latency": 0.2, "availability": 0.7, "context": 0.8, "cost": 0.2},
        "reasoning": "very_high",
        "cost_sensitivity": "low",
    },
    "financial_extraction": {
        "required": ["text", "structured_output"],
        "preferred": ["tool_calling"],
        "weights": {"capability": 1.2, "quality": 0.5, "reliability": 0.8, "latency": 0.5, "availability": 0.7, "context": 0.5, "cost": 1.5},
        "reasoning": "low",
        "cost_sensitivity": "very_high",
    },
    "summarization": {
        "required": ["text"],
        "preferred": ["long_context"],
        "weights": {"capability": 1.0, "quality": 0.7, "reliability": 0.7, "latency": 0.5, "availability": 0.7, "context": 0.8, "cost": 0.8},
        "reasoning": "low",
        "cost_sensitivity": "high",
    },
    "classification": {
        "required": ["text"],
        "preferred": ["structured_output"],
        "weights": {"capability": 1.0, "quality": 0.4, "reliability": 0.8, "latency": 0.8, "availability": 0.7, "context": 0.2, "cost": 1.4},
        "reasoning": "low",
        "cost_sensitivity": "very_high",
    },
    "planning": {
        "required": ["text", "reasoning"],
        "preferred": ["tool_calling", "long_context"],
        "weights": {"capability": 1.5, "quality": 1.2, "reliability": 1.1, "latency": 0.3, "availability": 0.6, "context": 0.7, "cost": 0.3},
        "reasoning": "high",
        "cost_sensitivity": "low",
    },
    "agentic_execution": {
        "required": ["text", "tool_calling"],
        "preferred": ["reasoning", "parallel_tool_calls", "long_context"],
        "weights": {"capability": 1.4, "quality": 1.0, "reliability": 1.5, "latency": 0.5, "availability": 0.8, "context": 0.7, "cost": 0.4},
        "reasoning": "high",
        "cost_sensitivity": "medium",
    },
    "vision": {
        "required": ["vision"],
        "preferred": ["text", "structured_output"],
        "weights": {"capability": 2.0, "quality": 0.9, "reliability": 0.9, "latency": 0.4, "availability": 0.7, "context": 0.5, "cost": 0.4},
        "reasoning": "medium",
        "cost_sensitivity": "medium",
    },
    "document_analysis": {
        "required": ["text", "long_context"],
        "preferred": ["reasoning", "structured_output", "vision"],
        "weights": {"capability": 1.5, "quality": 0.9, "reliability": 0.9, "latency": 0.3, "availability": 0.7, "context": 1.2, "cost": 0.4},
        "reasoning": "medium",
        "cost_sensitivity": "medium",
    },
    "background_task": {
        "required": ["text"],
        "preferred": [],
        "weights": {"capability": 1.0, "quality": 0.4, "reliability": 0.8, "latency": 0.1, "availability": 0.9, "context": 0.3, "cost": 1.8},
        "reasoning": "low",
        "cost_sensitivity": "very_high",
    },
    "embedding": {
        "required": ["embeddings"],
        "preferred": [],
        "weights": {"capability": 2.0, "quality": 0.5, "reliability": 0.9, "latency": 0.6, "availability": 0.8, "context": 0.0, "cost": 1.2},
        "reasoning": "none",
        "cost_sensitivity": "high",
    },
    "image_generation": {
        "required": ["image_generation"],
        "preferred": [],
        "weights": {"capability": 2.0, "quality": 0.9, "reliability": 0.8, "latency": 0.3, "availability": 0.7, "context": 0.0, "cost": 0.5},
        "reasoning": "none",
        "cost_sensitivity": "medium",
    },
    "audio": {
        "required": ["audio_input"],
        "preferred": ["text"],
        "weights": {"capability": 2.0, "quality": 0.8, "reliability": 0.8, "latency": 0.5, "availability": 0.7, "context": 0.2, "cost": 0.6},
        "reasoning": "none",
        "cost_sensitivity": "medium",
    },
    "default": {
        "required": ["text"],
        "preferred": [],
        "weights": {"capability": 1.0, "quality": 0.6, "reliability": 0.8, "latency": 0.5, "availability": 0.7, "context": 0.4, "cost": 0.6},
        "reasoning": "medium",
        "cost_sensitivity": "medium",
    },
}

# Reasoning effort → an ordered scale for capability matching.
REASONING_LEVELS = ("none", "low", "medium", "high", "very_high", "max")


def reasoning_rank(level: Optional[str]) -> int:
    try:
        return REASONING_LEVELS.index(level or "medium")
    except ValueError:
        return REASONING_LEVELS.index("medium")


# ── Aliases (spec §15) ──────────────────────────────────────────────────────


# An alias is an INTENT, resolved dynamically against current health/quality/
# cost. It never points permanently at one model. `resolve` names the selector.
ALIASES: dict[str, dict[str, Any]] = {
    "eclipse-default": {"resolve": "default", "task": "default"},
    "eclipse-fast": {"resolve": "lowest_latency", "task": "simple_chat", "require": ["text"]},
    "eclipse-smart": {"resolve": "highest_quality", "task": "default", "require": ["text"]},
    "eclipse-reasoning": {"resolve": "highest_quality", "task": "coding", "require": ["text", "reasoning"]},
    "eclipse-coder": {"resolve": "best_coding", "task": "coding", "require": ["text", "tool_calling"]},
    "eclipse-vision": {"resolve": "highest_quality", "task": "vision", "require": ["vision"]},
    "eclipse-cheap": {"resolve": "lowest_cost", "task": "background_task", "require": ["text"]},
    "eclipse-local": {"resolve": "best_local", "task": "default", "require": ["text"], "local_only": True},
    "eclipse-extraction": {"resolve": "lowest_cost", "task": "financial_extraction", "require": ["text", "structured_output"]},
    "eclipse-background": {"resolve": "lowest_cost", "task": "background_task", "require": ["text"]},
}


__all__ = [
    "ALIASES",
    "LONG_CONTEXT_MIN_TOKENS",
    "MODEL_CAPABILITY_OVERRIDES",
    "PERFORMANCE_PRIORS",
    "PRICING_CATALOG",
    "PROVIDER_CAPABILITIES",
    "REASONING_LEVELS",
    "TASK_PROFILES",
    "reasoning_rank",
]
