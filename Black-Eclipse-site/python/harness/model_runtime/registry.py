"""Registries: providers, models, capabilities and pricing.

These are the runtime's in-memory knowledge. They are seeded from the existing
`harness.models.PROVIDER_CATALOG` (so the runtime reuses, rather than replaces,
the provider definitions the rest of Eclipse already depends on) plus the static
`catalog` data, and can be extended at startup by discovery or by the caller.
"""

from __future__ import annotations

import fnmatch
from typing import Any, Callable, Iterable, Optional

from ..models import PROVIDER_CATALOG, PROVIDER_MODELS, resolve_context_window
from . import capability as _capability
from .catalog import (
    ALIASES,
    PERFORMANCE_PRIORS,
    PRICING_CATALOG,
    TASK_PROFILES,
)
from .types import (
    CapabilityState,
    ModelCapabilities,
    ModelInfo,
    ModelPerformance,
    ModelPricing,
    PricingKind,
    ProviderInfo,
)


def _substring_performance(model_id: str) -> ModelPerformance:
    needle = (model_id or "").lower()
    best = ""
    chosen = ModelPerformance()
    for substring, perf in PERFORMANCE_PRIORS.items():
        if substring in needle and len(substring) > len(best):
            best = substring
            chosen = perf
    return chosen


def _substring_pricing(provider_id: str, model_id: str) -> Optional[ModelPricing]:
    qualified = f"{provider_id}/{model_id}".lower()
    for pattern, pricing in PRICING_CATALOG.items():
        if fnmatch.fnmatch(qualified, pattern.lower()):
            return pricing
    return None


class ProviderRegistry:
    """Register/enable/disable providers (spec §9)."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderInfo] = {}

    def seed_from_catalog(self) -> None:
        for spec in PROVIDER_CATALOG.values():
            self.register(
                ProviderInfo(
                    id=spec.id,
                    label=spec.label,
                    kind=spec.kind,
                    keyless=spec.keyless,
                    openai_compatible=spec.openai_compatible,
                    default_base_url=spec.default_base_url,
                    dynamic_discovery=spec.id in ("ollama", "lmstudio", "openrouter", "custom"),
                    metadata={"defaultModel": spec.default_model, "envVar": spec.env_var},
                )
            )

    def register(self, provider: ProviderInfo) -> None:
        self._providers[provider.id] = provider

    def remove_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def get_provider(self, provider_id: str) -> Optional[ProviderInfo]:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ProviderInfo]:
        return list(self._providers.values())

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        provider = self._providers.get(provider_id)
        if provider is not None:
            provider.enabled = enabled

    def enable_provider(self, provider_id: str) -> None:
        self.set_enabled(provider_id, True)

    def disable_provider(self, provider_id: str) -> None:
        self.set_enabled(provider_id, False)

    def enabled_providers(self) -> list[ProviderInfo]:
        return [p for p in self._providers.values() if p.enabled]


class CapabilityRegistry:
    """Capability lookup + probe-result folding (spec §6)."""

    def __init__(self) -> None:
        self._probes: dict[str, dict[str, CapabilityState]] = {}

    def record_probe(self, qualified_model_id: str, key: str, state: CapabilityState) -> None:
        self._probes.setdefault(qualified_model_id, {})[key] = state

    def apply(self, model: ModelInfo) -> ModelCapabilities:
        caps = model.capabilities
        for key, state in self._probes.get(model.qualified_id, {}).items():
            caps = caps.with_state(key, state)
        return caps

    def find_supporting(
        self, models: Iterable[ModelInfo], required: Iterable[str]
    ) -> list[ModelInfo]:
        out = []
        for model in models:
            caps = self.apply(model)
            if caps.supports_all(list(required)):
                out.append(model)
        return out


class PricingRegistry:
    """Pricing lookup. Unknown stays unknown; never invented (spec §23)."""

    def __init__(self) -> None:
        self._overrides: dict[str, ModelPricing] = {}

    def register(self, qualified_model_id: str, pricing: ModelPricing) -> None:
        self._overrides[qualified_model_id] = pricing

    def pricing_for(self, model: ModelInfo) -> ModelPricing:
        override = self._overrides.get(model.qualified_id)
        if override is not None:
            return override
        if model.pricing.kind is not PricingKind.UNKNOWN:
            return model.pricing
        declared = _substring_pricing(model.provider_id, model.id)
        return declared if declared is not None else ModelPricing()


class ModelRegistry:
    """Central model registry (spec §8)."""

    def __init__(self, providers: Optional[ProviderRegistry] = None) -> None:
        self._models: dict[str, ModelInfo] = {}
        self._by_provider: dict[str, list[str]] = {}
        self._aliases: dict[str, str] = {}
        self._providers = providers

    # ── registration ────────────────────────────────────────────────────────
    def register_model(self, model: ModelInfo) -> None:
        self._models[model.qualified_id] = model
        provider_models = self._by_provider.setdefault(model.provider_id, [])
        if model.qualified_id not in provider_models:
            provider_models.append(model.qualified_id)
        for alias in model.aliases:
            self._aliases[alias] = model.qualified_id

    def update_model(self, model: ModelInfo) -> None:
        self.register_model(model)

    def remove_model(self, qualified_model_id: str) -> None:
        model = self._models.pop(qualified_model_id, None)
        if model is None:
            return
        provider_models = self._by_provider.get(model.provider_id, [])
        if qualified_model_id in provider_models:
            provider_models.remove(qualified_model_id)
        self._aliases = {a: m for a, m in self._aliases.items() if m != qualified_model_id}

    # ── lookup ──────────────────────────────────────────────────────────────
    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        if model_id in self._models:
            return self._models[model_id]
        # Bare id: resolve only when unambiguous.
        matches = [m for m in self._models.values() if m.id == model_id]
        if len(matches) == 1:
            return matches[0]
        return None

    def list_models(self, *, provider_id: Optional[str] = None) -> list[ModelInfo]:
        if provider_id is None:
            return list(self._models.values())
        return [self._models[q] for q in self._by_provider.get(provider_id, [])]

    def findByProvider(self, provider_id: str) -> list[ModelInfo]:  # noqa: N802 - spec name
        return self.list_models(provider_id=provider_id)

    def findByCapability(self, required: Iterable[str]) -> list[ModelInfo]:  # noqa: N802
        required = list(required)
        return [m for m in self._models.values() if m.capabilities.supports_all(required)]

    def register_alias(self, alias: str, qualified_model_id: str) -> None:
        self._aliases[alias] = qualified_model_id

    def resolve_alias(self, alias: str) -> Optional[str]:
        return self._aliases.get(alias)

    def alias_intent(self, name: str) -> Optional[dict[str, Any]]:
        return ALIASES.get(name)

    # ── discovery ───────────────────────────────────────────────────────────
    def discover_models(self, provider_id: str, model_ids: Iterable[str]) -> list[ModelInfo]:
        """Register models discovered dynamically (e.g. an Ollama /v1/models list)."""
        provider = self._providers.get_provider(provider_id) if self._providers else None
        kind = provider.kind if provider else "openai_compatible"
        added: list[ModelInfo] = []
        for model_id in model_ids:
            if not model_id or self.get_model(f"{provider_id}/{model_id}"):
                continue
            model = build_model_info(
                provider_id=provider_id,
                model_id=model_id,
                kind=kind,
                context_window=resolve_context_window(provider_id, model_id),
                dynamic=True,
            )
            self.register_model(model)
            added.append(model)
        return added


def build_model_info(
    *,
    provider_id: str,
    model_id: str,
    kind: str,
    context_window: Optional[int] = None,
    provider_metadata: Optional[dict[str, Any]] = None,
    dynamic: bool = False,
) -> ModelInfo:
    """Build a normalized `ModelInfo` from static catalog + provider metadata."""
    caps = _capability.detect_capabilities(
        kind=kind,
        model_id=model_id,
        provider_metadata=provider_metadata,
        context_window=context_window,
    )
    pricing = _substring_pricing(provider_id, model_id)
    if pricing is None:
        pricing = ModelPricing()
    return ModelInfo(
        id=model_id,
        provider_id=provider_id,
        display_name=model_id,
        capabilities=caps,
        context_window=context_window,
        pricing=pricing,
        performance=_substring_performance(model_id),
        metadata={"dynamic": dynamic, "kind": kind},
    )


def build_default_registries(
    *,
    provider_metadata: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[ProviderRegistry, ModelRegistry, CapabilityRegistry, PricingRegistry]:
    """The process-wide default set, seeded from the existing catalog.

    Declared models (`PROVIDER_MODELS`) are registered with their resolved
    context windows. Discovery later adds whatever else a provider reports —
    the registry is never an allowlist.
    """
    providers = ProviderRegistry()
    providers.seed_from_catalog()
    capabilities = CapabilityRegistry()
    pricing = PricingRegistry()
    models = ModelRegistry(providers)

    meta = provider_metadata or {}
    for provider in providers.list_providers():
        model_ids = PROVIDER_MODELS.get(provider.id)
        if not model_ids:
            default_model = provider.metadata.get("defaultModel")
            model_ids = [default_model] if default_model else []
        for model_id in model_ids:
            window = resolve_context_window(provider.id, model_id)
            models.register_model(
                build_model_info(
                    provider_id=provider.id,
                    model_id=model_id,
                    kind=provider.kind,
                    context_window=window,
                    provider_metadata=meta.get(provider.id),
                )
            )
    return providers, models, capabilities, pricing


__all__ = [
    "CapabilityRegistry",
    "ModelRegistry",
    "PricingRegistry",
    "ProviderRegistry",
    "build_default_registries",
    "build_model_info",
]
