"""The model router: pick the best model for a task, and explain why (spec §11–16, §33).

The router never calls a provider. It scores the registry's candidates against a
task profile and returns a fully explained decision:

    requirements → eligibility → scoring → ranking → fallbacks → trace

Scoring is configurable. `RoutingPolicy` carries the default weights and task
overrides; a caller (or the settings vault) may replace it. `TaskProfiles` come
from the static catalog so adding one is data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .catalog import LONG_CONTEXT_MIN_TOKENS, TASK_PROFILES, reasoning_rank
from .capability import required_missing
from .health import CircuitBreaker, HealthManager, RateLimitManager
from .registry import CapabilityRegistry, ModelRegistry, PricingRegistry, ProviderRegistry
from .types import (
    ChatRequest,
    ModelInfo,
    ModelPricing,
    PricingKind,
    Usage,
)

# Providers whose endpoints are local by construction.
_LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "local", "vllm", "llamacpp", "text-generation-webui"})
_LOCAL_HOST_HINTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal")


@dataclass
class RoutingRequirements:
    required: list[str] = field(default_factory=lambda: ["text"])
    preferred: list[str] = field(default_factory=list)
    min_context: Optional[int] = None
    reasoning_effort: Optional[str] = None
    local_only: bool = False
    prefer_free: bool = False
    allowed_providers: Optional[list[str]] = None
    denied_providers: list[str] = field(default_factory=list)
    max_cost_per_request: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "preferred": list(self.preferred),
            "minContext": self.min_context,
            "reasoningEffort": self.reasoning_effort,
            "localOnly": self.local_only,
            "preferFree": self.prefer_free,
            "allowedProviders": self.allowed_providers,
            "deniedProviders": list(self.denied_providers),
            "maxCostPerRequest": self.max_cost_per_request,
        }


@dataclass
class RouteCandidate:
    model: ModelInfo
    score: Optional[float] = None
    breakdown: dict[str, float] = field(default_factory=dict)
    excluded_reason: Optional[str] = None

    @property
    def qualified_id(self) -> str:
        return self.model.qualified_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.qualified_id,
            "provider": self.model.provider_id,
            "score": None if self.score is None else round(self.score, 4),
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
            "excludedReason": self.excluded_reason,
        }


@dataclass
class RoutingDecision:
    request_id: str
    task: str
    requirements: RoutingRequirements
    selected: Optional[RouteCandidate]
    fallbacks: list[RouteCandidate] = field(default_factory=list)
    candidates: list[RouteCandidate] = field(default_factory=list)
    alias: Optional[str] = None
    reason: str = ""
    policy: dict[str, Any] = field(default_factory=dict)

    @property
    def selected_model(self) -> Optional[ModelInfo]:
        return self.selected.model if self.selected else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "task": self.task,
            "alias": self.alias,
            "reason": self.reason,
            "requirements": self.requirements.to_dict(),
            "selected": self.selected.to_dict() if self.selected else None,
            "fallbacks": [c.to_dict() for c in self.fallbacks],
            "candidates": [c.to_dict() for c in self.candidates],
            "policy": dict(self.policy),
        }


@dataclass
class RoutingPolicy:
    """Configurable scoring weights (spec §13).

    Base weights apply to every task; `task_overrides` replace them per task.
    `normalize` scales raw features into 0..1. `fallback_depth` bounds the
    fallback chain.
    """

    base_weights: dict[str, float] = field(default_factory=lambda: {
        "capability": 1.0,
        "quality": 0.6,
        "reliability": 0.8,
        "latency": 0.5,
        "availability": 0.7,
        "context": 0.4,
        "cost": 0.6,
    })
    task_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    fallback_depth: int = 3
    # Budget pressure above which the router boosts the cost weight and shifts
    # toward cheaper/free models (spec §24).
    budget_downgrade_pressure: float = 0.7

    def weights_for(self, task: str) -> dict[str, float]:
        profile = self.task_overrides.get(task) or TASK_PROFILES.get(task) or TASK_PROFILES.get("default")
        weights = dict(self.base_weights)
        weights.update(profile.get("weights", {}))
        return weights


class TaskProfiles:
    """Named task profiles (spec §14)."""

    def __init__(self, overrides: Optional[dict[str, dict[str, Any]]] = None) -> None:
        self._overrides = overrides or {}

    def get(self, task: Optional[str]) -> dict[str, Any]:
        name = task or "default"
        if name in self._overrides:
            base = dict(TASK_PROFILES.get(name, TASK_PROFILES["default"]))
            base.update(self._overrides[name])
            return base
        return TASK_PROFILES.get(name, TASK_PROFILES["default"])

    def names(self) -> list[str]:
        return sorted(set(TASK_PROFILES) | set(self._overrides))


class ModelRouter:
    """Provider-agnostic model selection with explainable traces."""

    def __init__(
        self,
        *,
        models: ModelRegistry,
        providers: ProviderRegistry,
        capabilities: CapabilityRegistry,
        pricing: PricingRegistry,
        health: HealthManager,
        circuit: CircuitBreaker,
        rate_limits: RateLimitManager,
        policy: Optional[RoutingPolicy] = None,
        task_profiles: Optional[TaskProfiles] = None,
        budget_manager: Any = None,
    ) -> None:
        self._models = models
        self._providers = providers
        self._capabilities = capabilities
        self._pricing = pricing
        self._health = health
        self._circuit = circuit
        self._rate_limits = rate_limits
        self._policy = policy or RoutingPolicy()
        self._tasks = task_profiles or TaskProfiles()
        self._budgets = budget_manager

    # ── public ──────────────────────────────────────────────────────────────
    def route(self, request: ChatRequest, *, request_id: Optional[str] = None) -> RoutingDecision:
        request_id = request_id or uuid.uuid4().hex
        alias = self._models.alias_intent(request.model) if request.model else None
        task = request.task or (alias or {}).get("task") or "default"
        profile = self._tasks.get(task)
        requirements = self._build_requirements(request, profile, alias)

        # Score EVERY registered model against the task requirements. This one
        # pass yields both the ranked candidates and the ordered fallback chain.
        evaluated = [self._evaluate(model, requirements, task, profile) for model in self._models.list_models()]
        eligible = [c for c in evaluated if c.excluded_reason is None]
        self._score_candidates(eligible, task, profile, requirements)
        eligible.sort(key=lambda c: (c.score or 0.0), reverse=True)

        # An explicit model (spec §44) is the caller's override: it is selected
        # when it is not disabled and passes the HARD policy checks (local-only,
        # denied provider, required capability). Otherwise selection falls to the
        # highest-scoring eligible candidate.
        selected: Optional[RouteCandidate] = None
        source = "router"
        if request.model and alias is None:
            explicit = self._explicit_candidate(request, requirements)
            if explicit is not None and explicit.excluded_reason is None:
                selected = explicit
                source = "explicit"
                eligible = [c for c in eligible if c.qualified_id != explicit.qualified_id] + [explicit]
            else:
                source = "router"
        if selected is None and eligible:
            selected = eligible[0]
            source = "alias" if alias else "router"

        # Fallbacks: every eligible candidate except the selected one, ranked,
        # respecting the required capabilities (already enforced by eligibility).
        fallbacks = [c for c in eligible if c.qualified_id != (selected.qualified_id if selected else None)]
        fallbacks = fallbacks[: self._policy.fallback_depth]
        reason = self._explain(selected, evaluated, task, alias, request.model)
        if source == "explicit":
            reason = f"Explicit model requested by the caller. {reason}"

        return RoutingDecision(
            request_id=request_id,
            task=task,
            requirements=requirements,
            selected=selected,
            fallbacks=fallbacks,
            candidates=evaluated,
            alias=request.model if alias else None,
            reason=reason,
            policy={
                "source": source,
                "weights": self._policy.weights_for(task),
                "fallbackDepth": self._policy.fallback_depth,
            },
        )

    # ── requirements ────────────────────────────────────────────────────────
    def _build_requirements(
        self,
        request: ChatRequest,
        profile: dict[str, Any],
        alias: Optional[dict[str, Any]],
    ) -> RoutingRequirements:
        overrides = request.policy_overrides or {}
        required: list[str] = list(dict.fromkeys(profile.get("required", ["text"])))
        required += [c for c in (alias or {}).get("require", [])]
        required += [c for c in (request.requirements.get("required") or [])]
        preferred = list(dict.fromkeys(
            list(profile.get("preferred", [])) + list(request.requirements.get("preferred") or [])
        ))
        required = list(dict.fromkeys(required))
        effort = (
            request.reasoning.effort if request.reasoning else None
        ) or request.requirements.get("reasoning") or profile.get("reasoning")
        return RoutingRequirements(
            required=required,
            preferred=preferred,
            min_context=request.requirements.get("min_context") or overrides.get("min_context"),
            reasoning_effort=effort,
            local_only=bool(overrides.get("local_only") or (alias or {}).get("local_only")),
            prefer_free=bool(overrides.get("prefer_free")),
            allowed_providers=overrides.get("allowed_providers"),
            denied_providers=list(overrides.get("denied_providers") or []),
            max_cost_per_request=overrides.get("max_cost_per_request"),
        )

    # ── eligibility ─────────────────────────────────────────────────────────
    def _explicit_candidate(
        self,
        request: ChatRequest,
        requirements: RoutingRequirements,
    ) -> Optional[RouteCandidate]:
        """Resolve an explicitly-requested model, applying HARD policy checks.

        An explicit choice overrides soft routing (capability priors, quality,
        cost) but never a hard rule: a disabled provider, a denied provider, a
        local-only policy against a remote model, or a missing required
        capability still excludes it.
        """
        if not request.model:
            return None
        model = self._resolve_explicit_model(request.model)
        if model is None:
            return None  # unknown id → fall through to dynamic routing
        provider = self._providers.get_provider(model.provider_id)
        if model.status == "unavailable":
            return RouteCandidate(model=model, excluded_reason="model is marked unavailable")
        if provider is not None and not provider.enabled:
            return RouteCandidate(model=model, excluded_reason="provider is disabled")
        missing = required_missing(self._capabilities.apply(model), requirements.required)
        if missing:
            return RouteCandidate(model=model, excluded_reason=f"missing required capability: {', '.join(missing)}")
        if self._is_local_only_violation(model, requirements):
            return RouteCandidate(model=model, excluded_reason="local-only policy")
        if requirements.allowed_providers is not None and model.provider_id not in requirements.allowed_providers:
            return RouteCandidate(model=model, excluded_reason="provider not in allowed list")
        if model.provider_id in requirements.denied_providers:
            return RouteCandidate(model=model, excluded_reason="provider denied")
        return RouteCandidate(model=model, score=1.0, breakdown={"explicit": 1.0})

    def _resolve_explicit_model(self, ref: str) -> Optional[ModelInfo]:
        if "/" in ref:
            provider_id, _, model_id = ref.partition("/")
            found = self._models.get_model(ref)
            if found is not None:
                return found
            # An unknown model on a known provider: synthesize a definition so an
            # operator can always type a model the registry has not discovered.
            provider = self._providers.get_provider(provider_id)
            if provider is not None:
                from .registry import build_model_info  # local import avoids cycle

                from ..models import resolve_context_window

                return build_model_info(
                    provider_id=provider_id,
                    model_id=model_id,
                    kind=provider.kind,
                    context_window=resolve_context_window(provider_id, model_id),
                )
        alias_target = self._models.resolve_alias(ref)
        if alias_target:
            return self._models.get_model(alias_target)
        return self._models.get_model(ref)

    def _evaluate(
        self,
        model: ModelInfo,
        requirements: RoutingRequirements,
        task: str,
        profile: dict[str, Any],
    ) -> RouteCandidate:
        provider = self._providers.get_provider(model.provider_id)

        def reject(reason: str) -> RouteCandidate:
            return RouteCandidate(model=model, excluded_reason=reason)

        if model.status == "unavailable":
            return reject("model is marked unavailable")
        if provider is not None and not provider.enabled:
            return reject("provider is disabled")

        caps = self._capabilities.apply(model)
        missing = required_missing(caps, requirements.required)
        if missing:
            return reject(f"missing required capability: {', '.join(missing)}")

        # Reasoning effort requirement.
        effort = requirements.reasoning_effort
        if effort and reasoning_rank(effort) >= reasoning_rank("high") and not caps.is_supported("reasoning"):
            # Not a hard failure when the model has no declared reasoning: many
            # models reason without a dedicated mode. Only exclude a model that
            # explicitly declares reasoning UNSUPPORTED.
            if caps.state("reasoning").value == "unsupported":
                return reject("reasoning unsupported")

        if requirements.min_context is not None:
            if model.context_window is None:
                return reject("context window unknown (cannot satisfy min context)")
            if model.context_window < requirements.min_context:
                return reject(
                    f"context window {model.context_window} < required {requirements.min_context}"
                )

        if self._is_local_only_violation(model, requirements):
            return reject("local-only policy")
        if requirements.allowed_providers is not None and model.provider_id not in requirements.allowed_providers:
            return reject("provider not in allowed list")
        if model.provider_id in requirements.denied_providers:
            return reject("provider denied")

        if not self._circuit.allow(model.qualified_id):
            return reject("circuit open (recent repeated failures)")
        if not self._circuit.allow(model.provider_id):
            return reject("provider circuit open")
        if self._rate_limits.is_limited(model.qualified_id):
            return reject("rate limited")

        cost = self._pricing.pricing_for(model)
        if requirements.prefer_free and cost.kind not in (PricingKind.FREE, PricingKind.UNKNOWN):
            return reject("free model required")

        return RouteCandidate(model=model)

    def _is_local_only_violation(self, model: ModelInfo, requirements: RoutingRequirements) -> bool:
        if not requirements.local_only:
            return False
        provider = self._providers.get_provider(model.provider_id)
        if model.provider_id in _LOCAL_PROVIDERS:
            return False
        base_url = (provider.default_base_url if provider else None) or ""
        return not any(hint in base_url.lower() for hint in _LOCAL_HOST_HINTS)

    # ── scoring ─────────────────────────────────────────────────────────────
    def _score_candidates(
        self,
        eligible: list[RouteCandidate],
        task: str,
        profile: dict[str, Any],
        requirements: RoutingRequirements,
    ) -> None:
        if not eligible:
            return
        weights = self._policy.weights_for(task)

        budget_key = self._budget_keys(task, requirements)
        budget_pressure = self._budgets.pressure(budget_key) if self._budgets else 0.0
        if budget_pressure >= self._policy.budget_downgrade_pressure:
            weights["cost"] = weights.get("cost", 0.6) * (1.0 + budget_pressure)
            weights["quality"] = weights.get("quality", 0.6) * (1.0 - 0.3 * budget_pressure)

        raw = {c.qualified_id: self._raw_features(c, requirements) for c in eligible}
        max_context = max((r["contextRaw"] for r in raw.values()), default=0.0) or 1.0
        max_quality = max((r["qualityRaw"] for r in raw.values()), default=0.0) or 1.0
        costs = [r["costRaw"] for r in raw.values() if r["costRaw"] is not None]
        latencies = [r["latencyRaw"] for r in raw.values() if r["latencyRaw"] is not None]
        max_cost = max(costs) if costs else 1.0
        max_latency = max(latencies) if latencies else 1.0

        for candidate in eligible:
            features = raw[candidate.qualified_id]
            breakdown = {
                "capability": features["capability"],
                "quality": (features["qualityRaw"] / max_quality) if max_quality else 0.0,
                "reliability": features["reliability"],
                "latency": 1.0 - (features["latencyRaw"] / max_latency if max_latency else 0.0),
                "availability": features["availability"],
                "context": (features["contextRaw"] / max_context) if max_context else 0.0,
                "cost": self._cost_score(features["costRaw"], max_cost, budget_pressure, requirements),
            }
            score = sum(breakdown[k] * weights.get(k, 0.0) for k in breakdown)
            candidate.score = score
            candidate.breakdown = breakdown

    def _raw_features(self, candidate: RouteCandidate, requirements: RoutingRequirements) -> dict[str, float]:
        model = candidate.model
        caps = self._capabilities.apply(model)
        quality = self._quality_for(model)
        reliability = self._health.health(model.qualified_id) or self._health.health(model.provider_id) or 0.5

        last = self._latency_last(model.qualified_id)
        if last is not None:
            latency_raw = last
        elif model.performance.speed is not None:
            latency_raw = 3000.0 * (1.0 - model.performance.speed)
        else:
            latency_raw = 1500.0

        context_raw = float(model.context_window) if model.context_window else (
            float(LONG_CONTEXT_MIN_TOKENS) if caps.is_supported("long_context") else 0.0
        )

        pricing = self._pricing.pricing_for(model)
        cost_raw = self._cost_raw(pricing)

        availability = 1.0
        if self._circuit.state(model.qualified_id) in ("degraded",):
            availability = 0.5

        return {
            "capability": self._preferred_ratio(caps, requirements.preferred),
            "qualityRaw": quality,
            "reliability": reliability,
            "latencyRaw": latency_raw,
            "availability": availability,
            "contextRaw": context_raw,
            "costRaw": cost_raw,
        }

    def _quality_for(self, model: ModelInfo) -> float:
        perf = model.performance
        values = [v for v in (perf.quality, perf.reasoning) if v is not None]
        if not values:
            return 0.5
        return sum(values) / len(values)

    def _preferred_ratio(self, caps: Any, preferred: list[str]) -> float:
        if not preferred:
            return 1.0
        supported = sum(1 for k in preferred if caps.is_supported(k))
        return supported / len(preferred)

    def _latency_last(self, key: str) -> Optional[float]:
        tracker = getattr(self, "_latency", None)
        if tracker is None:
            return None
        return tracker.last_latency_ms(key)

    def set_latency_tracker(self, tracker: Any) -> None:
        self._latency = tracker

    def _cost_raw(self, pricing: ModelPricing) -> Optional[float]:
        if pricing.kind is PricingKind.FREE:
            return 0.0
        if pricing.kind is PricingKind.PER_REQUEST:
            return pricing.per_request
        if pricing.kind is PricingKind.PER_TOKEN and pricing.input_per_million is not None:
            # Cost of a nominal 1k-in / 1k-out request.
            out = pricing.output_per_million or 0.0
            return (pricing.input_per_million + out) / 1000.0
        return None  # unknown — handled neutrally

    def _cost_score(
        self,
        cost_raw: Optional[float],
        max_cost: float,
        budget_pressure: float,
        requirements: RoutingRequirements,
    ) -> float:
        if requirements.prefer_free:
            return 1.0
        if cost_raw is None:
            return 0.5
        if cost_raw <= 0:
            return 1.0
        # Cheaper is better; clamp so a single candidate scores 1.0.
        if max_cost <= 0:
            return 1.0
        return max(0.0, 1.0 - (cost_raw / max_cost))

    def _budget_keys(self, task: str, requirements: RoutingRequirements) -> list[str]:
        return ["global", "global:daily", f"task:{task}"]

    # ── explanation ─────────────────────────────────────────────────────────
    def _explain(
        self,
        selected: Optional[RouteCandidate],
        evaluated: list[RouteCandidate],
        task: str,
        alias: Optional[dict[str, Any]],
        requested: Optional[str],
    ) -> str:
        if selected is None:
            return f"No model satisfied the {task} requirements."
        if alias:
            return (
                f"Alias '{requested}' resolved to {selected.qualified_id} "
                f"for task {task}."
            )
        rejected = sum(1 for c in evaluated if c.excluded_reason)
        return (
            f"Selected {selected.qualified_id} for task {task} "
            f"(score {round(selected.score or 0.0, 3)}); "
            f"{rejected} candidate(s) excluded."
        )


__all__ = [
    "ModelRouter",
    "RouteCandidate",
    "RoutingDecision",
    "RoutingPolicy",
    "RoutingRequirements",
    "TaskProfiles",
]
