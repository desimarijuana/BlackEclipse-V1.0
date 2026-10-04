"""First-party adapters: Anthropic, Google Gemini, Mistral, Groq.

Each keeps provider-specific reasoning translation. Construction is delegated to
the factory so no second copy of the LangChain wiring exists.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import ReasoningRequest
from .base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    kind = "anthropic"

    def apply_reasoning(self, model: Any, reasoning: Optional[ReasoningRequest]) -> Any:
        """Map to Anthropic's `thinking` budget (tokens), when requested."""
        if not reasoning or not reasoning.enabled:
            return model
        budget = reasoning.max_tokens
        if budget is None:
            budget = {"low": 1024, "medium": 4096, "high": 8192, "max": 16384}.get(
                reasoning.effort or "medium", 4096
            )
        try:
            if hasattr(model, "thinking"):
                model.thinking = {"type": "enabled", "budget_tokens": budget}
        except Exception:  # noqa: BLE001
            return model
        return model


class GoogleAdapter(ProviderAdapter):
    kind = "google"

    def apply_reasoning(self, model: Any, reasoning: Optional[ReasoningRequest]) -> Any:
        """Map to Gemini's `thinking_budget` when requested."""
        if not reasoning or not reasoning.enabled:
            return model
        budget = reasoning.max_tokens
        if budget is None:
            budget = {"low": 0, "medium": 2048, "high": 8192, "max": 24576}.get(
                reasoning.effort or "medium", 2048
            )
        try:
            if hasattr(model, "thinking_budget"):
                model.thinking_budget = budget
        except Exception:  # noqa: BLE001
            return model
        return model


class MistralAdapter(ProviderAdapter):
    kind = "mistral"


class GroqAdapter(ProviderAdapter):
    kind = "groq"


__all__ = ["AnthropicAdapter", "GoogleAdapter", "GroqAdapter", "MistralAdapter"]
