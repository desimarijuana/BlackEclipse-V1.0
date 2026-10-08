"""Vision routing: native-first, then auxiliary fallback, with privacy.

The central rule (spec §8):

    If the run's own model sees images, send the image to IT.
    Only when it cannot does the orchestrator fall back to an auxiliary
    vision model.

Privacy (spec §38) constrains both paths: a sensitive frame under a local-only
policy is never sent to a cloud provider, and if no local model exists the
request is refused (never silently uploaded).

Selection uses the existing model registry (`findByCapability`) and provider
registry; credentials are reused exactly as the runtime's fallback does — a
different provider is only usable when keyless (local). The plan is pure DATA so
it is fully testable without any model or network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .capabilities import (
    VISION_SUPPORT,
    VisionCapabilities,
    capabilities_for_model,
    capabilities_for_settings,
)
from .config import VisionConfig, vision_config
from .contracts import VisionInput
from .errors import VisionError, VisionErrorClass


@dataclass
class PrivacyDecision:
    allow_local: bool = True
    allow_cloud: bool = True
    prefer: str = "cloud"  # "cloud" | "local"
    reason: str = ""


@dataclass
class RouteCandidate:
    settings: Any
    provider: Optional[str]
    model: Optional[str]
    local: bool
    reason: str = ""


@dataclass
class RoutingPlan:
    kind: str  # "native" | "auxiliary" | "none"
    settings: Any = None
    capabilities: VisionCapabilities = field(default_factory=VisionCapabilities)
    candidates: list[RouteCandidate] = field(default_factory=list)
    privacy: PrivacyDecision = field(default_factory=PrivacyDecision)
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.kind in ("native", "auxiliary") and self.settings is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "provider": getattr(self.settings, "provider", None),
            "model": getattr(self.settings, "model", None),
            "capabilities": self.capabilities.to_dict(),
            "privacy": {"allowLocal": self.privacy.allow_local, "allowCloud": self.privacy.allow_cloud,
                        "prefer": self.privacy.prefer, "reason": self.privacy.reason},
            "candidates": [
                {"provider": c.provider, "model": c.model, "local": c.local, "reason": c.reason}
                for c in self.candidates
            ],
        }


def decide_privacy(
    *,
    mode: str,
    sensitive: bool,
    allow_cloud_for_sensitive: bool,
) -> PrivacyDecision:
    """The pure privacy decision (no models, no I/O)."""
    if mode == "local_only":
        return PrivacyDecision(allow_local=True, allow_cloud=False, prefer="local", reason="local-only policy")
    if sensitive and not allow_cloud_for_sensitive:
        return PrivacyDecision(allow_local=True, allow_cloud=False, prefer="local", reason="sensitive frame; cloud not permitted")
    if mode == "local_preferred":
        return PrivacyDecision(allow_local=True, allow_cloud=True, prefer="local", reason="local preferred")
    if mode == "cloud_preferred":
        return PrivacyDecision(allow_local=True, allow_cloud=True, prefer="cloud", reason="cloud preferred")
    return PrivacyDecision(allow_local=True, allow_cloud=True, prefer="cloud", reason="cloud allowed")


def _local_candidate_allowed(cap: VisionCapabilities, privacy: PrivacyDecision) -> bool:
    return privacy.allow_local and cap.local


def _cloud_candidate_allowed(cap: VisionCapabilities, privacy: PrivacyDecision) -> bool:
    return privacy.allow_cloud and not cap.local


def plan_route(
    input: VisionInput,
    *,
    run_settings: Any,
    cfg: Optional[VisionConfig] = None,
    runtime: Any = None,
    aux_settings: Any = None,
) -> RoutingPlan:
    """Build the routing plan for a request.

    `run_settings` is the model the agent is already using. `aux_settings`, when
    provided, is an explicit auxiliary vision model (highest priority). Otherwise
    the configured `vision_model`/`fallback_priority` and the runtime's vision
    task profile are used, constrained by credentials and privacy.
    """
    cfg = cfg or vision_config()
    # Fall back to the process-wide runtime so registry vision models are always
    # considered — the orchestrator/tools may not pass one explicitly.
    if runtime is None:
        try:
            from ..model_runtime import get_runtime  # noqa: PLC0415

            runtime = get_runtime()
        except Exception:  # noqa: BLE001
            runtime = None
    mode = input.privacy or cfg.privacy_mode
    sensitive = bool(input.sensitive)
    allow_cloud_sensitive = cfg.allow_cloud_for_sensitive
    privacy = decide_privacy(
        mode=mode,
        sensitive=sensitive,
        allow_cloud_for_sensitive=allow_cloud_sensitive,
    )
    if input.local_only:
        privacy = PrivacyDecision(allow_local=True, allow_cloud=False, prefer="local", reason="run requested local-only")

    # The native decision asks about the RUN'S OWN model directly — never a model
    # the router might substitute. Otherwise a text-only run model on a provider
    # that also hosts a VLM could be wrongly reported native and receive the image.
    run_caps = capabilities_for_model(run_settings) if run_settings is not None else VisionCapabilities()

    # Auxiliary candidates are computed in both paths so a NATIVE plan still has
    # a fallback if the native model's vision call fails at runtime (spec §9).
    aux_candidates = _auxiliary_candidates(
        run_settings=run_settings, cfg=cfg, runtime=runtime,
        aux_settings=aux_settings, privacy=privacy,
    )

    # ── native first ─────────────────────────────────────────────────────────
    if run_caps.native_vision:
        if _local_candidate_allowed(run_caps, privacy) or _cloud_candidate_allowed(run_caps, privacy):
            # Never fall back to the native model on itself.
            fallbacks = [c for c in aux_candidates if c.settings is not run_settings]
            return RoutingPlan(
                kind="native", settings=run_settings, capabilities=run_caps, privacy=privacy,
                candidates=fallbacks,
                reason="the run's model supports native image input",
            )
        # Native vision exists but privacy forbids the only usable side.
        # Fall through to find a permitted auxiliary.

    candidates = aux_candidates

    if not candidates:
        reason = (
            "the run's model cannot accept images and no permitted vision model is available"
            if not privacy.allow_cloud
            else "the run's model cannot accept images and no vision model is configured"
        )
        return RoutingPlan(kind="none", capabilities=run_caps, privacy=privacy, reason=reason)

    chosen = candidates[0]
    chosen_caps = capabilities_for_settings(chosen.settings, task="vision")
    return RoutingPlan(
        kind="auxiliary", settings=chosen.settings, capabilities=chosen_caps,
        candidates=candidates, privacy=privacy,
        reason=chosen.reason or "auxiliary vision model selected",
    )


def _auxiliary_candidates(
    *,
    run_settings: Any,
    cfg: VisionConfig,
    runtime: Any,
    aux_settings: Any,
    privacy: PrivacyDecision,
) -> list[RouteCandidate]:
    ordered: list[RouteCandidate] = []

    explicit: list[Any] = []
    if aux_settings is not None:
        explicit.append(aux_settings)
    if cfg.vision_model:
        coerced = _coerce_model_ref(cfg.vision_model, run_settings)
        if coerced is not None:
            explicit.append(coerced)
    for ref in cfg.fallback_priority:
        coerced = _coerce_model_ref(ref, run_settings)
        if coerced is not None:
            explicit.append(coerced)

    seen: set[str] = set()
    for settings in explicit:
        candidate = _as_candidate(settings, run_settings=run_settings, runtime=runtime, privacy=privacy)
        key = _key(settings)
        if candidate is not None and key not in seen:
            seen.add(key)
            ordered.append(candidate)

    # Then the runtime's vision task profile (registered vision models).
    if runtime is not None:
        for candidate in _registry_candidates(runtime, run_settings, privacy):
            key = _key(candidate.settings)
            if key not in seen:
                seen.add(key)
                ordered.append(candidate)

    if not ordered:
        # Last resort: the run's own settings, only if it is a local model under a
        # local-only policy (a cloud model that lacks vision would just fail).
        run_caps = capabilities_for_settings(run_settings, task="vision")
        if run_settings is not None and run_caps.local and privacy.allow_local:
            if run_settings is not (aux_settings or None):
                ordered.append(RouteCandidate(settings=run_settings, provider=getattr(run_settings, "provider", None),
                                              model=getattr(run_settings, "model", None), local=True,
                                              reason="local provider used for vision"))
    return ordered


def _registry_candidates(runtime: Any, run_settings: Any, privacy: PrivacyDecision) -> list[RouteCandidate]:
    out: list[RouteCandidate] = []
    try:
        # `findByCapability` takes an iterable of keys; pass a LIST so a string
        # is not iterated character-by-character (which matched nothing).
        models = runtime.models.findByCapability([VISION_SUPPORT])
    except Exception:  # noqa: BLE001
        return out
    for model_info in models:
        provider_id = getattr(model_info, "provider_id", None)
        provider = None
        try:
            provider = runtime.providers.get_provider(provider_id)
        except Exception:  # noqa: BLE001
            provider = None
        local = bool(provider is not None and provider.keyless)
        if local and not privacy.allow_local:
            continue
        if not local and not privacy.allow_cloud:
            continue
        settings = _settings_for_model(run_settings, provider_id, getattr(model_info, "id", None), provider)
        if settings is None:
            continue
        out.append(RouteCandidate(settings=settings, provider=provider_id, model=getattr(model_info, "id", None),
                                  local=local, reason="registered vision model"))
    return out


def _settings_for_model(run_settings: Any, provider_id: Optional[str], model_id: Optional[str], provider: Any) -> Any:
    """Build settings for a vision candidate on `provider_id`.

    Same provider reuses the run's credentials. A DIFFERENT provider is only
    usable when the process can actually reach it: a keyless local server, or a
    hosted provider whose environment credential is present. A remote provider the
    run holds no key for is never selected (ADR-H146 §31/§45).
    """
    try:
        if run_settings is not None and getattr(run_settings, "provider", None) == provider_id:
            return run_settings.model_copy(update={"model": model_id})
        from ..models import provider_has_credentials  # noqa: PLC0415

        if provider is not None and provider.keyless and run_settings is not None:
            return run_settings.model_copy(update={
                "provider": provider_id, "model": model_id,
                "base_url": provider.default_base_url, "api_key": None,
            })
        if run_settings is not None and provider_has_credentials(provider_id or ""):
            return run_settings.model_copy(update={
                "provider": provider_id, "model": model_id,
                "base_url": (getattr(provider, "default_base_url", None) or run_settings.base_url),
                "api_key": None,
            })
    except Exception:  # noqa: BLE001
        return None
    return None


def _as_candidate(settings: Any, *, run_settings: Any, runtime: Any, privacy: PrivacyDecision) -> Optional[RouteCandidate]:
    if settings is None:
        return None
    caps = capabilities_for_model(settings)
    local = caps.local
    if local and not privacy.allow_local:
        return None
    if not local and not privacy.allow_cloud:
        return None
    # An explicitly configured auxiliary may be vision-capable or may be the only
    # local model the operator has; we accept it if it is at least plausibly
    # vision-capable OR local (a local model is tried because its true capability
    # is only knowable at call time).
    if not caps.native_vision and not local:
        return None
    return RouteCandidate(settings=settings, provider=getattr(settings, "provider", None),
                          model=getattr(settings, "model", None), local=local,
                          reason="explicitly configured vision model")


def _coerce_model_ref(ref: str, run_settings: Any) -> Any:
    """Turn a `provider/model` or bare `model` reference into a settings object."""
    if not ref or run_settings is None:
        return None
    try:
        if "/" in ref:
            provider_id, model_id = ref.split("/", 1)
            if getattr(run_settings, "provider", None) == provider_id:
                return run_settings.model_copy(update={"model": model_id})
            # A different provider is usable only when the process can reach it: a
            # keyless local server, or a hosted provider with an env credential.
            from ..model_runtime import get_runtime  # noqa: PLC0415

            provider = get_runtime().providers.get_provider(provider_id)
            from ..models import provider_has_credentials  # noqa: PLC0415

            if provider is not None and provider.keyless:
                return run_settings.model_copy(update={
                    "provider": provider_id, "model": model_id,
                    "base_url": provider.default_base_url, "api_key": None,
                })
            if provider_has_credentials(provider_id):
                return run_settings.model_copy(update={
                    "provider": provider_id, "model": model_id,
                    "base_url": (provider.default_base_url if provider else None) or run_settings.base_url,
                    "api_key": None,
                })
            return None
        return run_settings.model_copy(update={"model": ref})
    except Exception:  # noqa: BLE001
        return None


def _key(settings: Any) -> str:
    return f"{getattr(settings, 'provider', None)}/{getattr(settings, 'model', None)}"


__all__ = [
    "PrivacyDecision", "RouteCandidate", "RoutingPlan", "decide_privacy", "plan_route",
]
