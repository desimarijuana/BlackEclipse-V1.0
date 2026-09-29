"""Milestone 1: declared context-window knowledge (pure, no network)."""

from __future__ import annotations

from harness import models


def test_resolver_returns_declared_value_for_known_provider():
    assert models.resolve_context_window("openai", "gpt-4o") == 128_000
    assert models.resolve_context_window("anthropic", "claude-3-5-sonnet-latest") == 200_000
    assert models.resolve_context_window("google", "gemini-2.0-flash") == 1_000_000


def test_resolver_returns_none_for_unknown():
    # A local server whose loaded model the runtime cannot know stays unknown.
    assert models.resolve_context_window("ollama", "llama3.1") is None
    assert models.resolve_context_window("lmstudio", "local-model") is None
    # A router fronting models of different sizes is deliberately unknown.
    assert models.resolve_context_window("openrouter", "openai/gpt-4o-mini") is None
    # An unlisted provider id is unknown too.
    assert models.resolve_context_window("does-not-exist", "x") is None


def test_model_specific_beats_provider_level():
    # Groq's provider floor is 8k; the Llama-3.3 entry declares 128k.
    assert models.PROVIDER_CATALOG["groq"].context_window == 8_192
    assert models.resolve_context_window("groq", "llama-3.3-70b-versatile") == 128_000
    # A Groq model with no specific entry falls back to the conservative floor.
    assert models.resolve_context_window("groq", "some-small-model") == 8_192
    # Longest matching substring wins: openai's gpt-4o-mini is still 128k.
    assert models.resolve_context_window("openai", "gpt-4o-mini") == 128_000


def test_resolver_is_pure_and_makes_no_network_call(monkeypatch):
    import socket

    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("resolver attempted a network call")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    # Two calls, identical result, no I/O.
    assert models.resolve_context_window("deepseek", "deepseek-chat") == 64_000
    assert models.resolve_context_window("deepseek", "deepseek-chat") == 64_000


def test_list_providers_exposes_context_window_additively():
    providers = {p["id"]: p for p in models.list_providers()}
    assert providers["openai"]["contextWindow"] == 128_000
    assert providers["ollama"]["contextWindow"] is None


def test_list_providers_exposes_declared_models_and_windows():
    providers = {p["id"]: p for p in models.list_providers()}
    # A declared model list for the picker (convenience, never an allowlist).
    assert "gpt-4o" in providers["openai"]["models"]
    assert providers["openai"]["modelWindows"]["gpt-4o"] == 128_000
    # An unknown-window provider reports None, not a fabricated number.
    assert providers["ollama"]["models"]
    assert providers["ollama"]["modelWindows"]["llama3.1"] is None
    # Unknown providers do not appear.
    assert "does-not-exist" not in providers

