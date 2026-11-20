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


def model_list_urls(base_url: str) -> list[str]:
    """Candidate model-list URLs for an OpenAI-protocol endpoint.

    `{base}/models` is the protocol default, so it is always tried first. But
    operators paste the native server root (`http://localhost:11434`,
    `https://ollama.com`) rather than the OpenAI `/v1` surface, and Ollama's
    native list is `/api/tags`. Both name the SAME server, so probing only
    `{root}/models` 404s and leaves the model picker empty. The alternates are
    only reached when the primary fails — a provider that speaks the protocol
    is never second-guessed.
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        root = base[: -len("/v1")]
    elif base.endswith("/api"):
        root = base[: -len("/api")]
    else:
        root = base
    urls = [f"{base}/models", f"{root}/v1/models", f"{root}/api/tags"]
    # Preserve order (the primary must stay first) while dropping duplicates.
    return list(dict.fromkeys(urls))


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
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"could not reach {base_url}/models: {exc}") from exc

    headers = {}
    api_key = getattr(settings, "api_key", None)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    first_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in model_list_urls(base_url):
            try:
                response = await client.get(url, headers=headers)
                if response.status_code >= 400:
                    # A 404 means "not this path"; any other status is more
                    # informative and is what a failure should report.
                    if first_error is None and response.status_code != 404:
                        first_error = f"HTTP {response.status_code} from {url}"
                    continue
                # A 200 that is not JSON (a website at /models) is not a model
                # list — fall through to the next candidate rather than fail.
                return _parse_openai_models(response.json())
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                if first_error is None:
                    first_error = f"could not reach {url}: {exc}"
    raise RuntimeError(first_error or f"could not reach {base_url}/models")


def _parse_openai_models(payload: Any) -> list[str]:
    """Extract model ids from an OpenAI-style `{data:[{id}]}` payload.

    Tolerates the shapes seen in the wild: `data` as a list of objects with an
    `id`, a bare list of id strings, or a top-level `models` list. Never
    fabricates an id.

    When the provider reports a `created` timestamp (OpenAI, OpenRouter, Groq,
    Together, Fireworks, Ollama all do) the ids are returned NEWEST FIRST, so
    the picker leads with the latest releases instead of the oldest. Without a
    timestamp the provider's own order is preserved.
    """
    if isinstance(payload, dict):
        entries = payload.get("data")
        if not isinstance(entries, list):
            entries = payload.get("models")
    else:
        entries = payload if isinstance(payload, list) else None
    if not isinstance(entries, list):
        return []
    found: list[tuple[str, Optional[float]]] = []
    for item in entries:
        created: Optional[float] = None
        if isinstance(item, dict):
            value = item.get("id") or item.get("name")
            raw_created = item.get("created", item.get("created_at"))
            if isinstance(raw_created, (int, float)):
                created = float(raw_created)
        else:
            value = item
        if value:
            found.append((str(value), created))
    if any(created is not None for _, created in found):
        # Models without a timestamp sort after dated ones, preserving their order.
        found.sort(key=lambda pair: (pair[1] is None, -(pair[1] or 0.0)))
    return [model_id for model_id, _ in found]


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


class OpenCodeAdapter(OpenAICompatibleAdapter):
    """OpenCode Console gateway.

    Chat is OpenAI-compatible at `…/inference/openai/v1/chat/completions`, but
    the gateway publishes its catalog one level up at `…/inference/v1/models`.
    The generic `{base}/models` probe would 404, so discovery rewrites the base.
    """

    kind = "openai_compatible"

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        url = opencode_models_url(getattr(settings, "base_url", None))
        headers = {}
        api_key = getattr(settings, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"could not reach {url}: {exc}") from exc
        return _parse_openai_models(payload)


OPENCODE_DEFAULT_BASE = "https://opencode.ai/inference/openai/v1"


def opencode_models_url(base_url: Optional[str]) -> str:
    """The OpenCode gateway catalog URL for a configured chat base URL.

    `…/inference/openai/v1` (chat) → `…/inference/v1/models` (catalog).
    Any other base is used as-is with `/models` appended.
    """
    base = (base_url or OPENCODE_DEFAULT_BASE).rstrip("/")
    list_base = base[: -len("/openai/v1")] + "/v1" if base.endswith("/openai/v1") else base
    return f"{list_base}/models"


__all__ = [
    "LocalAdapter",
    "OllamaAdapter",
    "OpenAIAdapter",
    "OpenAICompatibleAdapter",
    "OpenCodeAdapter",
    "model_list_urls",
    "opencode_models_url",
    "probe_openai_models",
]
