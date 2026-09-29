"""ModelSettings wire contract: camelCase from the TS front door + declared window.

Regression: the TS front door sends `baseUrl`/`apiKey` (camelCase) while the
pydantic model declared `base_url`/`api_key`, so pydantic silently DROPPED them
and the runtime fell back to the catalog default base URL with no credential.
"""

from __future__ import annotations

from harness.schemas import ModelSettings, RunRequest


def _request(model_settings: dict) -> RunRequest:
    return RunRequest.model_validate({
        "runId": "r",
        "input": {"query": "hi"},
        "agentId": "eclipse-agent",
        "modelSettings": model_settings,
        "callbackBaseUrl": "http://localhost:3000",
    })


def test_camel_case_base_url_and_api_key_are_accepted():
    # Exactly the shape the TS front door actually sends.
    settings = ModelSettings.model_validate({
        "provider": "custom",
        "baseUrl": "https://openrouter.ai/api/v1",
        "apiKey": "vault-key",
        "model": "openai/gpt-4o-mini",
    })
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.api_key == "vault-key"


def test_camel_case_survives_the_run_request_contract():
    req = _request({
        "provider": "custom",
        "baseUrl": "https://openrouter.ai/api/v1",
        "apiKey": "vault-key",
        "model": "openai/gpt-4o-mini",
    })
    assert req.modelSettings.base_url == "https://openrouter.ai/api/v1"
    assert req.modelSettings.api_key == "vault-key"


def test_snake_case_constructor_still_works():
    # Internal callers/tests use snake_case kwargs; populate_by_name keeps them.
    settings = ModelSettings(provider="openai", model="gpt-4o", base_url="http://x", api_key="k")
    assert settings.base_url == "http://x"
    assert settings.api_key == "k"


def test_declared_context_window_is_accepted_camel_case():
    settings = ModelSettings.model_validate({
        "provider": "ollama", "baseUrl": "http://localhost:11434/v1",
        "model": "llama3.1", "contextWindow": 8192,
    })
    assert settings.context_window == 8192


def test_context_window_is_optional_and_unset_by_default():
    settings = ModelSettings(provider="ollama", model="llama3.1")
    assert settings.context_window is None
