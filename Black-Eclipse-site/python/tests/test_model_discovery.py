"""Model discovery: a pasted server root must still list the models it serves.

The bug this guards: Ollama is documented as `http://localhost:11434`, but the
OpenAI-compatible surface is `/v1`. Probing only `{root}/models` returned 404,
so Settings rendered an empty model list with no Discover action.
"""

from __future__ import annotations

import httpx
import pytest

from harness.models import ModelSettings
from harness.model_runtime.providers.openai import model_list_urls, probe_openai_models


def _settings(base_url: str) -> ModelSettings:
    return ModelSettings(provider="ollama", base_url=base_url, model="llama3.1")


def test_protocol_path_is_tried_first_then_ollama_native_fallback():
    urls = model_list_urls("http://localhost:11434")
    assert urls == [
        "http://localhost:11434/models",
        "http://localhost:11434/v1/models",
        "http://localhost:11434/api/tags",
    ]
    # Already on the OpenAI surface / native API: no wrong path is invented.
    assert model_list_urls("http://localhost:11434/v1") == [
        "http://localhost:11434/v1/models",
        "http://localhost:11434/api/tags",
    ]
    assert model_list_urls("https://ollama.com/api")[0] == "https://ollama.com/api/models"


class _Response:
    def __init__(self, status_code: int, payload):  # noqa: ANN001
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _NotFoundThenTagsClient:
    """A native Ollama server: `/models` 404s, `/v1/models` lists the same set."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.requested: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str, headers=None):  # noqa: ANN001
        self.requested.append(url)
        if url.endswith("/v1/models"):
            return _Response(200, {"object": "list", "data": [{"id": "kimi-k3:cloud"}]})
        return _Response(404, {})


async def test_probe_falls_back_to_v1_and_returns_the_served_ids(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _NotFoundThenTagsClient)
    ids = await probe_openai_models(_settings("http://localhost:11434"))
    assert ids == ["kimi-k3:cloud"]


class _AllDownClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str, headers=None):  # noqa: ANN001
        raise httpx.ConnectError("connection refused")


async def test_probe_still_reports_an_honest_failure(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _AllDownClient)
    with pytest.raises(RuntimeError, match="could not reach"):
        await probe_openai_models(_settings("http://127.0.0.1:9/v1"))
