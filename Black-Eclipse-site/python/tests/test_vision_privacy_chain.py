"""Vision: one privacy story, and a bounded fallback chain.

Live evidence (2026-11-06): with `ECLIPSE_PRIVACY` unset the app correctly used a
local model for chat, but `screenshot_analyze` walked five local models, then LM
Studio, then OpenRouter (`openai/gpt-4o-mini`) — 12 provider calls — and the
screenshot left the machine. Two defects:

  * vision had its OWN privacy default (`cloud_allowed`) that ignored the
    app-wide switch, so `ECLIPSE_PRIVACY=local-models` could not keep a frame
    local;
  * the fallback chain had no bound, so one slow/dead vendor cost a walk through
    every configured provider.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.vision.config import load_vision_config
from harness.vision.errors import VisionError, VisionErrorClass
from harness.vision.orchestrator import bounded_attempts
from harness.vision.routing import RoutingPlan, RouteCandidate
from harness.vision import orchestrator
from harness.vision import telemetry as tel


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("HARNESS_VISION_PRIVACY", "ECLIPSE_PRIVACY", "HARNESS_VISION_CONFIG",
                "HARNESS_VISION_MAX_ATTEMPTS", "HARNESS_VISION_MAX_PER_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HARNESS_VISION_CONFIG", "/nonexistent/vision.json")
    yield


# ── privacy: the app-wide switch is the floor ────────────────────────────────
def test_local_models_means_vision_is_local_only(monkeypatch):
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    assert load_vision_config().privacy_mode == "local_only"


def test_unset_privacy_allows_cloud(monkeypatch):
    assert load_vision_config().privacy_mode == "cloud_allowed"


def test_explicit_vision_switch_wins_over_the_app_switch(monkeypatch):
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    monkeypatch.setenv("HARNESS_VISION_PRIVACY", "cloud_allowed")
    assert load_vision_config().privacy_mode == "cloud_allowed"


def test_vision_can_be_stricter_than_the_app(monkeypatch):
    monkeypatch.setenv("HARNESS_VISION_PRIVACY", "local_only")
    assert load_vision_config().privacy_mode == "local_only"


# ── the chain is bounded ─────────────────────────────────────────────────────
def _settings(provider: str, model: str) -> SimpleNamespace:
    return SimpleNamespace(provider=provider, model=model)


def test_bounded_attempts_caps_total_and_per_provider():
    cfg = SimpleNamespace(max_attempts=4, max_per_provider=2)
    attempts = [
        _settings("ollama", "gemma3"),
        _settings("ollama", "qwen2.5-vl"),
        _settings("ollama", "llava"),
        _settings("lmstudio", "qwen2.5-vl"),
        _settings("openrouter", "openai/gpt-4o-mini"),
        _settings("openrouter", "google/gemini-2.5-pro"),
    ]
    out = bounded_attempts(attempts, cfg)
    assert [a.provider for a in out] == ["ollama", "ollama", "lmstudio", "openrouter"]
    assert len(out) == 4


def test_bounded_attempts_always_keeps_the_primary():
    cfg = SimpleNamespace(max_attempts=1, max_per_provider=1)
    attempts = [_settings("ollama", "gemma3"), _settings("openrouter", "gpt-4o-mini")]
    assert bounded_attempts(attempts, cfg) == [attempts[0]]


def test_failed_chain_stops_at_the_cap_and_records_it(monkeypatch):
    """A dead vendor costs the cap, not every configured model."""
    cfg = SimpleNamespace(max_attempts=3, max_per_provider=2, vision_model=None)
    candidates = [
        RouteCandidate(_settings("ollama", "gemma3"), "ollama", "gemma3", local=True),
        RouteCandidate(_settings("ollama", "llava"), "ollama", "llava", local=True),
        RouteCandidate(_settings("lmstudio", "qwen2.5-vl"), "lmstudio", "qwen2.5-vl", local=True),
        RouteCandidate(_settings("openrouter", "gpt-4o-mini"), "openrouter", "gpt-4o-mini", local=False),
    ]
    plan = RoutingPlan(kind="auxiliary", settings=candidates[0].settings, candidates=candidates)
    telemetry = tel.VisionTelemetry()
    tried: list[str] = []

    async def factory(settings):
        tried.append(str(settings.provider))
        raise VisionError(VisionErrorClass.PROVIDER_ERROR, "vendor down")

    result = asyncio.run(orchestrator._try_candidates(plan, telemetry, factory, cfg=cfg))

    assert not result.ok
    assert tried == ["ollama", "ollama", "lmstudio"]  # 3, not all 4
    assert telemetry.counters[tel.EVENT_ROUTE_CAPPED] == 1
    assert telemetry.counters[tel.EVENT_PROVIDER_CALL] == 3


def test_success_names_the_model_that_looked():
    cfg = SimpleNamespace(max_attempts=2, max_per_provider=2)
    settings = _settings("ollama", "gemma3")
    plan = RoutingPlan(kind="auxiliary", settings=settings, candidates=[])

    async def factory(_settings):
        return orchestrator.VisionResult(ok=True, mode="analyze", provenance={})

    result = asyncio.run(orchestrator._try_candidates(plan, tel.VisionTelemetry(), factory, cfg=cfg))
    assert result.ok
    assert result.provenance["provider"] == "ollama"
    assert result.provenance["model"] == "gemma3"
