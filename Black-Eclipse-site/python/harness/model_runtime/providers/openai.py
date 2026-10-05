"""OpenAI-family adapter (native API + every OpenAI-compatible endpoint).

OpenAI's protocol is the great unifier: Ollama, LM Studio, vLLM, OpenRouter,
DeepSeek, xAI, Together, Groq, Fireworks, Mistral, Perplexity and any custom
base URL all speak it. They share this transport but keep their own catalog
entry (base URL, model list, pricing, quirks).
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import ReasoningRequest
from .base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    kind = "openai"

    def apply_reasoning(self, model: Any, reasoning: Optional[ReasoningRequest]) -> Any:
        """Translate normalized reasoning into OpenAI's `reasoning_effort`.

        Only applied when the operator asked for it; a model that does not
        accept the knob is left untouched rather than being forced.
        """
        if not reasoning or not reasoning.enabled or not reasoning.effort:
            return model
        effort = "high" if reasoning.effort == "very_high" else reasoning.effort
        try:
            if hasattr(model, "reasoning_effort"):
                model.reasoning_effort = effort
        except Exception:  # noqa: BLE001 - a provider may reject the kwarg
            return model
        return model


class OpenAICompatibleAdapter(OpenAIAdapter):
    """A local/custom OpenAI-compatible server or an aggregator router.

    Same transport as OpenAI; discovery differs (a local server lists its own
    models, a router fronts hundreds).
    """

    kind = "openai_compatible"

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        """Probe the `/models` endpoint of an OpenAI-compatible base URL.

        A reachable endpoint that lists no models returns an empty list. A probe
        that cannot be completed raises, so the caller can report an honest
        failure instead of a misleading empty success.
        """
        base_url = settings.base_url
        if not base_url:
            return []
        try:
            import httpx  # noqa: PLC0415 - optional at import time

            headers = {}
            if settings.api_key:
                headers["Authorization"] = f"Bearer {settings.api_key}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001 - re-raised as a clear failure
            raise RuntimeError(f"could not reach {base_url}/models: {exc}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
        return []


class OllamaAdapter(OpenAICompatibleAdapter):
    kind = "openai_compatible"


class LocalAdapter(OpenAICompatibleAdapter):
    kind = "openai_compatible"


__all__ = ["LocalAdapter", "OllamaAdapter", "OpenAIAdapter", "OpenAICompatibleAdapter"]
