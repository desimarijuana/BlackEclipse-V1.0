"""Vision-model recognition + routing tests.

Locks in the fix for "vision needs a vision-capable model configured": the shared
`openai` SDK kind must not blanket-claim vision (Ollama/DeepSeek/Groq/xAI serve
text-only models), known VLMs must be recognized, and a text-only run model must
be able to fall back to a real vision model when one is available.
"""

from __future__ import annotations

import pytest

from harness.model_runtime.capability import detect_capabilities
from harness.models import provider_has_credentials
from harness.schemas import ModelSettings
from harness.vision.contracts import VisionInput
from harness.vision.routing import plan_route

_KIND = {
    "openai": "openai", "ollama": "openai", "custom": "openai", "deepseek": "openai",
    "xai": "openai", "groq": "groq", "google": "google", "anthropic": "anthropic",
}


def _vision(provider: str, model: str) -> bool:
    caps = detect_capabilities(kind=_KIND[provider], model_id=model)
    return caps.state("vision").value == "supported"


# ── accurate recognition ────────────────────────────────────────────────────────

VISION_MODELS = [
    ("openai", "gpt-4o"), ("openai", "gpt-4o-mini"), ("openai", "gpt-4.1-mini"),
    ("openai", "gpt-4-turbo"), ("openai", "o3"), ("openai", "gpt-5"),
    ("anthropic", "claude-3-5-sonnet-latest"), ("anthropic", "claude-4-sonnet-latest"),
    ("google", "gemini-2.0-flash"), ("google", "gemini-2.5-pro"), ("google", "gemma3"),
    ("xai", "grok-2-vision"), ("xai", "grok-4"),
    ("ollama", "llava"), ("ollama", "qwen2.5-vl"), ("ollama", "minicpm-v"),
    ("ollama", "moondream"), ("custom", "llama-3.2-11b-vision-instruct"),
    ("custom", "internvl2"), ("custom", "pixtral-12b"), ("custom", "deepseek-vl2"),
]

TEXT_ONLY_MODELS = [
    ("openai", "gpt-3.5-turbo"), ("openai", "gpt-4"), ("openai", "o1-mini"), ("openai", "o3-mini"),
    ("deepseek", "deepseek-chat"), ("deepseek", "deepseek-reasoner"),
    ("groq", "llama-3.3-70b-versatile"), ("xai", "grok-2-latest"),
    ("ollama", "llama3.1"), ("ollama", "qwen2.5"), ("ollama", "mistral"), ("ollama", "phi3"),
    ("custom", "mixtral-8x7b"), ("custom", "codestral-latest"),
]


@pytest.mark.parametrize("provider,model", VISION_MODELS)
def test_known_vision_models_are_recognized(provider, model):
    assert _vision(provider, model) is True


@pytest.mark.parametrize("provider,model", TEXT_ONLY_MODELS)
def test_known_text_models_are_not_claimed_vision(provider, model):
    assert _vision(provider, model) is False


# ── routing ─────────────────────────────────────────────────────────────────────

def test_native_when_run_model_is_a_vlm():
    settings = ModelSettings(provider="ollama", model="llava", base_url="http://local/v1")
    plan = plan_route(VisionInput(source="x", source_kind="path"), run_settings=settings)
    assert plan.kind == "native"


def test_text_run_model_falls_back_to_a_vision_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    run = ModelSettings(provider="deepseek", model="deepseek-chat", base_url="https://api.deepseek.com/v1", api_key="dk")
    plan = plan_route(VisionInput(source="x", source_kind="path"), run_settings=run)
    assert plan.kind == "auxiliary"
    assert getattr(plan.settings, "provider", None) == "openai"
    assert _vision("openai", getattr(plan.settings, "model", "")) is True


def test_local_only_never_routes_to_cloud(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    # A text-only run model; cloud credentials EXIST but local-only must ignore them.
    run = ModelSettings(provider="groq", model="llama-3.3-70b-versatile", base_url="https://api.groq.com/openai/v1", api_key="g")
    plan = plan_route(VisionInput(source="x", source_kind="path", privacy="local_only"), run_settings=run)
    # Never the run's cloud model, never any cloud provider.
    assert plan.kind != "native"
    if plan.usable:
        assert getattr(plan.settings, "provider", None) not in ("openai", "anthropic", "google", "groq")


def test_provider_has_credentials(monkeypatch):
    assert provider_has_credentials("ollama") is True  # keyless local
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert provider_has_credentials("openai") is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert provider_has_credentials("openai") is True
