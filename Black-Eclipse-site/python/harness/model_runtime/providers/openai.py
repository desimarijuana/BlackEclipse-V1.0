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

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        """List an OpenAI-family provider's models via `GET {base_url}/models`.

        OpenAI's protocol is the great unifier: OpenAI itself, Groq, Mistral,
        DeepSeek, xAI, Together, Fireworks, Perplexity, OpenRouter, Ollama, LM
        Studio and any custom endpoint all expose a `{base_url}/models` list in
        the same `{data:[{id}]}` shape. The probe sends the resolved key as a
        `Bearer` token, so a private endpoint (OpenAI, Groq, …) enumerates too,
        and it does NOT assume localhost — any remote base URL works.

        A reachable endpoint that lists no models returns an empty list. A probe
        that cannot be completed raises, so the caller reports an honest failure
        instead of a misleading empty success.
        """
        return await probe_openai_models(settings)

    def apply_reasoning(self, model: Any, reasoning: Optional[ReasoningRequest]) -> Any:
        """Translate normalized reasoning into OpenAI's `reasoning_effort`.

        Only applied when the operator asked for it; a model that does not
        accept the knob is left untouched rather than being forced.

        OpenAI's `reasoning_effort` has no tier above `high`, so the runtime's
        `max`/`very_high` (the UI's "Ultra") is capped at `high` here — sending
        the literal `max` would be an unknown value and a provider 400.
        """
        if not reasoning or not reasoning.enabled or not reasoning.effort:
            return model
        effort = "high" if reasoning.effort in ("very_high", "max") else reasoning.effort
        try:
            if hasattr(model, "reasoning_effort"):
                model.reasoning_effort = effort
        except Exception:  # noqa: BLE001 - a provider may reject the kwarg
            return model
        return model


async def probe_openai_models(settings: Any) -> list[str]:
    """Probe `{base_url}/models` for any OpenAI-protocol provider.

    Shared by `OpenAIAdapter` and the first-party OpenAI-protocol adapters
    (Mistral, Groq) so there is one discovery implementation. Returns the model
    ids; raises on an unreachable endpoint.
    """
    base_url = getattr(settings, "base_url", None)
    if not base_url:
        return []
    try:
        import httpx  # noqa: PLC0415 - optional at import time

        headers = {}
        api_key = getattr(settings, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001 - re-raised as a clear failure
        raise RuntimeError(f"could not reach {base_url}/models: {exc}") from exc
    return _parse_openai_models(payload)


def _parse_openai_models(payload: Any) -> list[str]:
    """Extract model ids from an OpenAI-style `{data:[{id}]}` payload.

    Tolerates the shapes seen in the wild: `data` as a list of objects with an
    `id`, a bare list of id strings, or a top-level `models` list. Never
    fabricates an id.
    """
    if isinstance(payload, dict):
        entries = payload.get("data")
        if not isinstance(entries, list):
            entries = payload.get("models")
    else:
        entries = payload if isinstance(payload, list) else None
    if not isinstance(entries, list):
        return []
    ids: list[str] = []
    for item in entries:
        if isinstance(item, dict):
            value = item.get("id") or item.get("name")
        else:
            value = item
        if value:
            ids.append(str(value))
    return ids


class OpenAICompatibleAdapter(OpenAIAdapter):
    """A local/custom OpenAI-compatible server or an aggregator router.

    Same transport as OpenAI; discovery differs (a local server lists its own
    models, a router fronts hundreds). Discovery is inherited from
    `OpenAIAdapter` — a `{base_url}/models` probe with the resolved key.
    """

    kind = "openai_compatible"


class OllamaAdapter(OpenAICompatibleAdapter):
    kind = "openai_compatible"


class LocalAdapter(OpenAICompatibleAdapter):
    kind = "openai_compatible"


__all__ = [
    "LocalAdapter",
    "OllamaAdapter",
    "OpenAIAdapter",
    "OpenAICompatibleAdapter",
    "probe_openai_models",
]
