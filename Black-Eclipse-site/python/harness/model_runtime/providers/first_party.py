"""First-party adapters: Anthropic, Google Gemini, Mistral, Groq.

Each keeps provider-specific reasoning translation. Construction is delegated to
the factory so no second copy of the LangChain wiring exists.

Mistral and Groq speak the OpenAI protocol (`{base}/models`), so they inherit
discovery from `OpenAIAdapter` via their catalog `kind`. Anthropic and Google
have their own model-list shapes and override `discover_models` below.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import ReasoningRequest
from .base import ProviderAdapter
from .openai import probe_openai_models


class AnthropicAdapter(ProviderAdapter):
    kind = "anthropic"

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        """List Anthropic models via `GET {base}/v1/models`.

        Uses the native API auth (`x-api-key` + `anthropic-version`), whether the
        configured base is the bare host (`https://api.anthropic.com`) or already
        ends in `/v1`. The response is `{data:[{id}]}`.
        """
        api_key = getattr(settings, "api_key", None)
        if not api_key:
            return []
        base = (getattr(settings, "base_url", None) or "https://api.anthropic.com").rstrip("/")
        url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
        try:
            import httpx  # noqa: PLC0415

            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"could not reach {url}: {exc}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            found: list[tuple[str, Optional[str]]] = [
                (str(item.get("id")), item.get("created_at"))
                for item in data
                if isinstance(item, dict) and item.get("id")
            ]
            # Anthropic returns an ISO-8601 `created_at`; newest first so a new
            # Claude release leads the picker. Lexicographic order is correct
            # for ISO timestamps; undated ids keep their relative order.
            dated = sorted((p for p in found if p[1]), key=lambda pair: pair[1], reverse=True)
            undated = [p for p in found if not p[1]]
            return [model_id for model_id, _ in [*dated, *undated]]
        return []

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

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        """List Gemini models via the Generative Language models endpoint.

        `GET https://generativelanguage.googleapis.com/v1beta/models?key=KEY`
        returns `{models:[{name:"models/gemini-2.0-flash", ...}]}`; the `models/`
        prefix is stripped so ids match the chat model names the catalog expects.
        """
        api_key = getattr(settings, "api_key", None)
        if not api_key:
            return []
        base = (getattr(settings, "base_url", None) or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        # A base pointing at the OpenAI-compat path (`…/openai`) still lists via
        # the native versioned root.
        if "/openai" in base:
            base = base.split("/openai")[0]
        url = f"{base}/models"
        try:
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, params={"key": api_key})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"could not reach {url}: {exc}") from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if isinstance(models, list):
            found: list[tuple[str, str]] = []
            for item in models:
                if isinstance(item, dict):
                    name = item.get("name")
                    version = str(item.get("version") or "")
                else:
                    name = item
                    version = ""
                if name:
                    found.append((str(name).replace("models/", "", 1), version))
            # Gemini reports a `version` (e.g. `001`); newest first when present.
            if any(version for _, version in found):
                found.sort(key=lambda pair: pair[1], reverse=True)
            return [model_id for model_id, _ in found]
        return []

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
    """Mistral speaks the OpenAI protocol; only discovery is added."""

    kind = "mistral"

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        return await probe_openai_models(settings)


class GroqAdapter(ProviderAdapter):
    """Groq speaks the OpenAI protocol; only discovery is added."""

    kind = "groq"

    async def discover_models(self, settings) -> list[str]:  # type: ignore[override]
        return await probe_openai_models(settings)


__all__ = ["AnthropicAdapter", "GoogleAdapter", "GroqAdapter", "MistralAdapter"]
