"""Provider adapters — one module per provider family.

Every adapter delegates model construction to the single existing
`harness.models.build_chat_model`; it only adds provider-specific translation,
discovery and probing. Register a new kind here.
"""

from __future__ import annotations

from typing import Optional

from .base import DelegatingAdapter, ProviderAdapter
from .first_party import AnthropicAdapter, GoogleAdapter, GroqAdapter, MistralAdapter
from .openai import (
    LocalAdapter,
    OllamaAdapter,
    OpenAIAdapter,
    OpenAICompatibleAdapter,
)

# Map `ProviderSpec.kind` (and a few provider ids whose kind is shared) to an
# adapter. Anything not listed uses the delegating default, so an unknown but
# catalog-known kind still works.
_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "openai": OpenAIAdapter,
    "openai_compatible": OpenAICompatibleAdapter,
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
    "mistral": MistralAdapter,
    "groq": GroqAdapter,
}

_FAMILY_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "ollama": OllamaAdapter,
    "lmstudio": LocalAdapter,
    "local": LocalAdapter,
    "vllm": LocalAdapter,
    "custom": OpenAICompatibleAdapter,
    "openrouter": OpenAICompatibleAdapter,
    "together": OpenAICompatibleAdapter,
    "deepseek": OpenAICompatibleAdapter,
    "cerebras": OpenAICompatibleAdapter,
    "qwen": OpenAICompatibleAdapter,
    "kimi": OpenAICompatibleAdapter,
    "nous": OpenAICompatibleAdapter,
    "fireworks": OpenAICompatibleAdapter,
    "perplexity": OpenAICompatibleAdapter,
    "xai": OpenAICompatibleAdapter,
}


def adapter_for(*, kind: str, provider_id: Optional[str] = None) -> ProviderAdapter:
    cls: Optional[type[ProviderAdapter]] = None
    if provider_id and provider_id in _FAMILY_ADAPTERS:
        cls = _FAMILY_ADAPTERS[provider_id]
    if cls is None:
        cls = _ADAPTERS.get(kind)
    if cls is None:
        # An OpenAI-compatible kind is the broadest safe default.
        cls = DelegatingAdapter
    return cls()


__all__ = ["adapter_for"]
