"""Universal model catalog + factory behaviour."""

from __future__ import annotations

import pytest

from harness import models
from harness.schemas import ModelSettings


def test_catalog_covers_first_party_and_compatible():
    ids = set(models.PROVIDER_CATALOG)
    # First-party integrations
    assert {"anthropic", "google", "mistral", "groq"}.issubset(ids)
    # OpenAI-compatible endpoints (the path that reaches "all models")
    assert {"openai", "ollama", "lmstudio", "openrouter", "opencode", "deepseek", "xai", "custom"}.issubset(ids)


def test_every_catalog_entry_has_a_factory_kind():
    for spec in models.PROVIDER_CATALOG.values():
        assert spec.kind in {"openai", "anthropic", "google", "mistral", "groq"}


def test_list_providers_shape():
    providers = models.list_providers()
    assert any(p["id"] == "openai" and p["openaiCompatible"] for p in providers)
    assert all("defaultModel" in p for p in providers)


def test_list_providers_marks_runtime_discoverable_endpoints():
    providers = {p["id"]: p for p in models.list_providers()}
    # Every provider can enumerate its models on demand: a local server lists
    # what is installed, and a hosted API/router lists its live catalog, so the
    # operator sees real current model ids rather than only a declared sample.
    for provider in ("ollama", "lmstudio", "openrouter", "custom", "openai"):
        assert providers[provider]["dynamicDiscovery"] is True, provider


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        models.build_chat_model(ModelSettings(provider="does-not-exist", model="x"))


def test_missing_key_raises_for_remote_provider():
    with pytest.raises(ValueError):
        models.build_chat_model(ModelSettings(provider="openai", model="gpt-4o-mini", api_key=None))


def test_ollama_is_keyless_and_builds_offline():
    model = models.build_chat_model(
        ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1")
    )
    assert model is not None


def test_custom_requires_base_url_and_model():
    with pytest.raises(ValueError):
        models.build_chat_model(ModelSettings(provider="custom", model=""))


def test_sampling_defaults_reach_the_openai_client(monkeypatch):
    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import langchain_openai
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)

    models.build_chat_model(ModelSettings(
        provider="openai", model="gpt-4o-mini", api_key="k",
        temperature=0.2, max_tokens=512,
    ))
    assert captured["temperature"] == 0.2
    assert captured["max_tokens"] == 512


def test_auto_sampling_defaults_are_not_sent(monkeypatch):
    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import langchain_openai
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)

    models.build_chat_model(ModelSettings(provider="openai", model="gpt-4o-mini", api_key="k"))
    assert "temperature" not in captured
    assert "max_tokens" not in captured
