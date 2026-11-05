"""Local-only privacy mode: a remote model must be refused before any request.

WHY THIS TEST EXISTS: the privacy mode is only real if the chokepoint that builds
every chat model (agent runs, jobs, automations, vision fallbacks) refuses a
remote endpoint. A UI-only guard would be bypassed by the scheduler.
"""

from __future__ import annotations

import pytest

from harness import models
from harness.schemas import ModelSettings


def test_loopback_detection() -> None:
    assert models._is_loopback_url("http://127.0.0.1:11434/v1")
    assert models._is_loopback_url("http://localhost:1234/v1")
    assert models._is_loopback_url("http://[::1]:8080/v1")
    assert not models._is_loopback_url("https://api.openai.com/v1")
    assert not models._is_loopback_url("http://localhost.evil.example/v1")
    assert not models._is_loopback_url(None)
    assert not models._is_loopback_url("not a url")


def test_remote_provider_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    settings = ModelSettings(
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-not-a-real-key",
        model="gpt-test",
    )
    with pytest.raises(ValueError, match="PRIVACY_LOCAL_MODELS_ONLY"):
        models.build_chat_model(settings)


def test_remote_default_provider_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider with no explicit base URL still resolves to a cloud endpoint."""
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    settings = ModelSettings(provider="anthropic", api_key="test", model="claude-test")
    with pytest.raises(ValueError, match="PRIVACY_LOCAL_MODELS_ONLY"):
        models.build_chat_model(settings)


def test_mode_is_off_without_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECLIPSE_PRIVACY", raising=False)
    assert models.privacy_local_models() is False


def test_documented_spellings(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("local-models", "LOCAL_MODELS", "local-only", " no-cloud "):
        monkeypatch.setenv("ECLIPSE_PRIVACY", value)
        assert models.privacy_local_models() is True
    monkeypatch.setenv("ECLIPSE_PRIVACY", "off")
    assert models.privacy_local_models() is False
