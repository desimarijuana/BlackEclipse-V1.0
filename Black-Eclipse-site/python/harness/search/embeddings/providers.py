"""Concrete embedding providers.

Each provider speaks its own HTTP protocol and translates a batch of texts into
a batch of vectors. All providers normalize to unit length when
``normalize=True`` so the store's cosine metric is exact. A provider raises
``EmbeddingProviderError(retryable=...)`` so the batcher can decide whether to
retry with backoff — a malformed request is never retried pointlessly.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .base import EmbeddingCapabilities, EmbeddingProvider, EmbeddingProviderError

_TIMEOUT = 30.0


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm <= 1e-12:
        return vector
    return [x / norm for x in vector]


def _classify_status(status: int) -> tuple[bool, str]:
    if status == 429:
        return True, "embedding rate limited"
    if status >= 500:
        return True, f"embedding provider error ({status})"
    return False, f"embedding request rejected ({status})"


async def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    try:
        import httpx  # noqa: PLC0415 - optional at import time
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingProviderError("httpx is unavailable", retryable=False) from exc

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except Exception as exc:  # noqa: BLE001 - network/timeout are retryable
        raise EmbeddingProviderError(f"embedding request failed: {exc}", retryable=True) from exc

    if response.status_code >= 400:
        retryable, message = _classify_status(response.status_code)
        raise EmbeddingProviderError(message, retryable=retryable)
    try:
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingProviderError("embedding response was not JSON", retryable=True) from exc
    if not isinstance(data, dict):
        raise EmbeddingProviderError("embedding response had an unexpected shape", retryable=True)
    return data


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """OpenAI /embeddings protocol: OpenAI, Ollama, LM Studio, vLLM, custom."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        provider_id: str,
        model: str,
        dimensions: int,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        version: str = "1",
        normalize: bool = True,
        timeout: float = _TIMEOUT,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self.normalize = normalize
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._timeout = timeout

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model, "input": texts, "encoding_format": "float"}
        if self.dimensions:
            # OpenAI v3 models accept a dimensions reduction; harmless elsewhere
            # only when the endpoint understands it, so send it solely for OpenAI.
            if self.provider_id == "openai":
                payload["dimensions"] = self.dimensions
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        data = await _post_json(
            f"{self._base_url}/embeddings", headers=headers, payload=payload, timeout=self._timeout
        )
        return self._parse(data)

    def _parse(self, data: dict[str, Any]) -> list[list[float]]:
        entries = data.get("data")
        if not isinstance(entries, list):
            raise EmbeddingProviderError("embedding response missing 'data'", retryable=True)
        indexed: list[tuple[int, list[float]]] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            vector = entry.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingProviderError("embedding entry missing a vector", retryable=True)
            index = int(entry.get("index", i) or i)
            indexed.append((index, [float(v) for v in vector]))
        indexed.sort(key=lambda kv: kv[0])
        return [self._finish(v) for _, v in indexed]

    def _finish(self, vector: list[float]) -> list[float]:
        self._check_dimensions(vector)
        return _normalize(vector) if self.normalize else vector

    def _check_dimensions(self, vector: list[float]) -> None:
        if self.dimensions and len(vector) != self.dimensions:
            raise EmbeddingProviderError(
                f"model {self.model} returned {len(vector)} dims, expected {self.dimensions}",
                retryable=False,
            )

    def get_capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(native_dimensions=self.dimensions, distance_metric="cosine")


class GoogleEmbeddingProvider(EmbeddingProvider):
    provider_id = "google"

    def __init__(
        self, *, model: str, dimensions: int, api_key: Optional[str] = None,
        base_url: Optional[str] = None, version: str = "1", normalize: bool = True,
        timeout: float = _TIMEOUT,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self.normalize = normalize
        self._api_key = api_key or ""
        self._base_url = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        self._timeout = timeout

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self._base_url}/v1beta/models/{self.model}:batchEmbedContents"
        requests = [
            {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        data = await _post_json(url, headers=headers, payload={"requests": requests}, timeout=self._timeout)
        entries = data.get("embeddings")
        if not isinstance(entries, list):
            raise EmbeddingProviderError("google embedding response missing 'embeddings'", retryable=True)
        vectors = []
        for entry in entries:
            values = entry.get("values") if isinstance(entry, dict) else None
            if not isinstance(values, list) or not values:
                raise EmbeddingProviderError("google embedding entry missing values", retryable=True)
            vector = [float(v) for v in values]
            if self.dimensions and len(vector) != self.dimensions:
                raise EmbeddingProviderError(
                    f"google returned {len(vector)} dims, expected {self.dimensions}",
                    retryable=False,
                )
            vectors.append(_normalize(vector) if self.normalize else vector)
        return vectors


class CohereEmbeddingProvider(EmbeddingProvider):
    provider_id = "cohere"

    def __init__(
        self, *, model: str, dimensions: int, api_key: Optional[str] = None,
        base_url: Optional[str] = None, version: str = "1", normalize: bool = True,
        timeout: float = _TIMEOUT,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self.normalize = normalize
        self._api_key = api_key or ""
        self._base_url = (base_url or "https://api.cohere.com/v2").rstrip("/")
        self._timeout = timeout

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.model,
            "texts": texts,
            "input_type": "search_document",
            "embedding_types": ["float"],
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        data = await _post_json(f"{self._base_url}/embed", headers=headers, payload=payload, timeout=self._timeout)
        embeddings = data.get("embeddings")
        if isinstance(embeddings, dict):
            embeddings = embeddings.get("float")
        if not isinstance(embeddings, list):
            raise EmbeddingProviderError("cohere embedding response missing vectors", retryable=True)
        return [self._finish([float(v) for v in vec]) for vec in embeddings]

    def _finish(self, vector: list[float]) -> list[float]:
        if self.dimensions and len(vector) != self.dimensions:
            raise EmbeddingProviderError("cohere dimension mismatch", retryable=False)
        return _normalize(vector) if self.normalize else vector


class VoyageEmbeddingProvider(EmbeddingProvider):
    provider_id = "voyage"

    def __init__(
        self, *, model: str, dimensions: int, api_key: Optional[str] = None,
        base_url: Optional[str] = None, version: str = "1", normalize: bool = True,
        timeout: float = _TIMEOUT,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self.normalize = normalize
        self._api_key = api_key or ""
        self._base_url = (base_url or "https://api.voyageai.com/v1").rstrip("/")
        self._timeout = timeout

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        data = await _post_json(f"{self._base_url}/embeddings", headers=headers, payload=payload, timeout=self._timeout)
        entries = data.get("data")
        if not isinstance(entries, list):
            raise EmbeddingProviderError("voyage embedding response missing 'data'", retryable=True)
        indexed: list[tuple[int, list[float]]] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            vector = entry.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingProviderError("voyage entry missing a vector", retryable=True)
            indexed.append((int(entry.get("index", i) or i), [float(v) for v in vector]))
        indexed.sort(key=lambda kv: kv[0])
        out = []
        for _, vector in indexed:
            if self.dimensions and len(vector) != self.dimensions:
                raise EmbeddingProviderError("voyage dimension mismatch", retryable=False)
            out.append(_normalize(vector) if self.normalize else vector)
        return out


__all__ = [
    "CohereEmbeddingProvider",
    "GoogleEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "VoyageEmbeddingProvider",
]
