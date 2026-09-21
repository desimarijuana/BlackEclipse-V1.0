"""Universal model provider factory.

Goal: connect EVERY model the operator has a key for, without hard-coding a
vendor into the agent runtime. Two mechanisms cover the field:

  1. Native LangChain integrations for first-party APIs (Anthropic, Google
     Gemini, Mistral, Groq, AWS Bedrock, Cohere, ...).
  2. The OpenAI-compatible protocol for everything else — Ollama, LM Studio,
     vLLM, OpenRouter, DeepSeek, xAI, Perplexity, Together, Fireworks, and any
     custom base URL. This one path alone reaches most hosted + local models.

The catalog is data, not branches: `PROVIDER_CATALOG` declares each provider's
LangChain class, its default base URL, model, and which env var holds its key.
Adding a provider is an entry here plus a requirements line.

Credentials are passed in per run (resolved by the TS vault) — this service
never reads env for secrets except as an explicit fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from .schemas import ModelSettings


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    # LangChain integration family:
    #   "openai"    -> langchain_openai.ChatOpenAI (also all compatible endpoints)
    #   "anthropic" -> langchain_anthropic.ChatAnthropic
    #   "google"    -> langchain_google_genai.ChatGoogleGenerativeAI
    #   "mistral"   -> langchain_mistralai.ChatMistralAI
    #   "groq"      -> langchain_groq.ChatGroq
    kind: str
    default_base_url: Optional[str] = None
    default_model: str = ""
    env_var: Optional[str] = None
    keyless: bool = False
    # OpenAI-compatible endpoints beyond the first-party ones.
    openai_compatible: bool = False


# ─── Catalog ─────────────────────────────────────────────────────────────────
# Model IDs are sensible defaults; the operator's saved config wins. "all models
# that exist" is reached through the openai-compatible rows, which accept ANY
# base URL + model id.
PROVIDER_CATALOG: dict[str, ProviderSpec] = {
    "openai": ProviderSpec("openai", "OpenAI", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY", openai_compatible=True),
    "anthropic": ProviderSpec("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com", "claude-3-5-sonnet-latest", "ANTHROPIC_API_KEY"),
    "google": ProviderSpec("google", "Google Gemini", "google", None, "gemini-2.0-flash", "GEMINI_API_KEY"),
    "mistral": ProviderSpec("mistral", "Mistral", "mistral", "https://api.mistral.ai/v1", "mistral-large-latest", "MISTRAL_API_KEY", openai_compatible=True),
    "groq": ProviderSpec("groq", "Groq", "groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY", openai_compatible=True),
    "ollama": ProviderSpec("ollama", "Ollama (local)", "openai", "http://localhost:11434/v1", "llama3.1", "OLLAMA_BASE_URL", keyless=True, openai_compatible=True),
    "lmstudio": ProviderSpec("lmstudio", "LM Studio (local)", "openai", "http://localhost:1234/v1", "local-model", keyless=True, openai_compatible=True),
    "deepseek": ProviderSpec("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY", openai_compatible=True),
    "xai": ProviderSpec("xai", "xAI (Grok)", "openai", "https://api.x.ai/v1", "grok-2-latest", "XAI_API_KEY", openai_compatible=True),
    "openrouter": ProviderSpec("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", "OPENROUTER_API_KEY", openai_compatible=True),
    "together": ProviderSpec("together", "Together AI", "openai", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY", openai_compatible=True),
    "perplexity": ProviderSpec("perplexity", "Perplexity", "openai", "https://api.perplexity.ai", "sonar", "PERPLEXITY_API_KEY", openai_compatible=True),
    "fireworks": ProviderSpec("fireworks", "Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3p3-70b-instruct", "FIREWORKS_API_KEY", openai_compatible=True),
    # Any endpoint not listed: give a base URL and a model id.
    "custom": ProviderSpec("custom", "Custom (OpenAI-compatible)", "openai", None, "", keyless=True, openai_compatible=True),
}


def _resolve_key(settings: ModelSettings, spec: ProviderSpec) -> Optional[str]:
    """Prefer the per-run key from the vault, then the env var, then a local default."""
    if settings.api_key:
        return settings.api_key
    if spec.env_var:
        env_value = os.environ.get(spec.env_var)
        if env_value:
            return env_value
    if spec.keyless:
        return "local"
    return None


def build_chat_model(settings: ModelSettings) -> Any:
    """Construct a LangChain chat model for the requested provider.

    Raises ValueError with a structured reason when the provider is unknown or
    unconfigured — the caller maps that to PROVIDER_NOT_CONFIGURED.
    """
    spec = PROVIDER_CATALOG.get(settings.provider)
    if spec is None:
        raise ValueError(f"Unknown model provider '{settings.provider}'")

    api_key = _resolve_key(settings, spec)
    temperature = settings.temperature

    if spec.kind == "openai":
        from langchain_openai import ChatOpenAI

        base_url = settings.base_url or spec.default_base_url
        model = settings.model or spec.default_model
        if not base_url:
            raise ValueError(f"Provider '{spec.id}' requires a base URL")
        if not model:
            raise ValueError(f"Provider '{spec.id}' requires a model id")
        if not api_key:
            raise ValueError(f"Provider '{spec.id}' is not configured (missing API key)")
        kwargs: dict[str, Any] = {"model": model, "base_url": base_url, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatOpenAI(**kwargs)

    if spec.kind == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not api_key:
            raise ValueError("Anthropic is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatAnthropic(**kwargs)

    if spec.kind == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not api_key:
            raise ValueError("Google Gemini is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatGoogleGenerativeAI(**kwargs)

    if spec.kind == "mistral":
        from langchain_mistralai import ChatMistralAI

        if not api_key:
            raise ValueError("Mistral is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatMistralAI(**kwargs)

    if spec.kind == "groq":
        from langchain_groq import ChatGroq

        if not api_key:
            raise ValueError("Groq is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatGroq(**kwargs)

    raise ValueError(f"Provider '{spec.id}' has unsupported kind '{spec.kind}'")


def list_providers() -> list[dict[str, Any]]:
    """Catalog for the TS side / UI — declares what can be connected."""
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "defaultBaseUrl": spec.default_base_url,
            "defaultModel": spec.default_model,
            "envVar": spec.env_var,
            "keyless": spec.keyless,
            "openaiCompatible": spec.openai_compatible,
        }
        for spec in PROVIDER_CATALOG.values()
    ]
