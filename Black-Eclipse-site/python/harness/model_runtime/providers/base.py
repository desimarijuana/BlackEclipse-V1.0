"""Provider adapter base.

An adapter is the ONLY place that knows a provider family's construction quirks.
It does not duplicate model construction: it delegates to the existing
`harness.models.build_chat_model`, which already owns the LangChain class choice
per provider kind. The adapter adds provider-specific metadata, model discovery,
and request translation (reasoning), and nothing else.

Adding a provider whose API speaks the OpenAI protocol needs no new adapter: it
is a catalog entry served by `OpenAICompatibleAdapter`. Adding a genuinely new
API family is one subclass here plus a registry line.
"""

from __future__ import annotations

import abc
from typing import Any, Optional

from ...schemas import ModelSettings
from ..types import ReasoningRequest


class ProviderAdapter(abc.ABC):
    """One provider family's translation layer."""

    #: The `ProviderSpec.kind` this adapter serves (openai/anthropic/google/…).
    kind: str = ""

    def build(self, settings: ModelSettings) -> Any:
        """Construct the LangChain chat model for these settings.

        Delegates to the single existing factory. The agent never sees which
        provider SDK this eventually instantiates.
        """
        from ..models import build_chat_model  # local import: avoids a cycle

        return build_chat_model(settings)

    def apply_reasoning(self, model: Any, reasoning: Optional[ReasoningRequest]) -> Any:
        """Best-effort translation of a normalized reasoning request.

        Returns the model (possibly unchanged). Providers that do not expose a
        reasoning knob simply ignore it — the runtime never fabricates support.
        """
        return model

    async def discover_models(self, settings: ModelSettings) -> list[str]:
        """Best-effort dynamic model discovery. Default: none."""
        return []

    async def health_check(self, settings: ModelSettings) -> dict[str, Any]:
        """A lightweight reachability probe. Default: unknown."""
        return {"ok": None, "detail": "no probe implemented"}


class DelegatingAdapter(ProviderAdapter):
    """The safe default: construct via the factory, apply no extra translation."""


__all__ = ["DelegatingAdapter", "ProviderAdapter"]
