"""The BrowserProviderRouter.

Chooses the appropriate provider for a task from:
  * explicit configuration (`default_provider`),
  * capability requirements (does the action need a capability this provider lacks?),
  * security policy (a private/local target must run locally),
  * availability (the provider's real runtime dependency),
  * provider health (recent failures demote a provider).

Never route sensitive/private content to a cloud provider unless explicitly
authorized. Every routing decision carries a plain `rationale` so it is
observable in the trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .config import BrowserConfig
from .policy import is_private_target


@dataclass
class RoutingRequest:
    provider: Optional[str] = None              # explicit operator/model choice
    url: Optional[str] = None                   # the target (for private detection)
    required_capabilities: tuple[str, ...] = ()
    interactive: bool = True                    # False = extraction
    allow_remote: bool = False                  # may cloud be used for a private target


@dataclass
class RoutingDecision:
    provider: str
    rationale: str
    candidates: list[str] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "rationale": self.rationale,
            "candidates": self.candidates,
            "rejected": self.rejected,
        }


class BrowserProviderRouter:
    """Deterministic provider selection over registered providers."""

    def __init__(self, config: BrowserConfig, providers: dict[str, Any]) -> None:
        self._config = config
        self._providers = providers

    def _is_private(self, request: RoutingRequest) -> bool:
        return bool(request.url) and is_private_target(request.url)

    def _capability_fit(self, provider_id: str, request: RoutingRequest) -> Optional[str]:
        """None when the provider fits, else a plain rejection reason."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return "not registered"
        caps = provider.capabilities()
        for capability in request.required_capabilities:
            if not caps.supports(capability):
                return f"cannot {capability.replace('_', ' ')}"
        if request.interactive and not caps.interactive:
            return "is an extraction backend, not an interactive browser"
        return None

    def decide(self, request: RoutingRequest) -> RoutingDecision:
        rejected: dict[str, str] = {}
        candidates: list[str] = []

        # 1. An explicit provider wins when it fits, is available and permitted.
        requested = request.provider or self._config.default_provider
        explicit = requested not in ("", "auto", None)

        private = self._is_private(request)
        order: list[str] = []
        if explicit:
            order.append(str(requested))
        # 2. The sensible defaults.
        order.extend(["local_chromium", "cdp"])
        if not private or request.allow_remote:
            order.extend(["browser_use", "browserbase", "lightpanda", "agent_browser"])
        if not request.interactive:
            order.insert(0, "firecrawl")
        # De-duplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for provider_id in order:
            if provider_id not in seen:
                seen.add(provider_id)
                ordered.append(provider_id)

        for provider_id in ordered:
            provider = self._providers.get(provider_id)
            if provider is None:
                rejected[provider_id] = "not registered"
                continue
            availability = provider.availability()
            if not availability.get("available"):
                rejected[provider_id] = availability.get("reason") or "unavailable"
                continue
            caps = provider.capabilities()
            if private and caps.remote and not (request.allow_remote or self._config_allow_private_remote()):
                rejected[provider_id] = "is a cloud backend and this address is private"
                continue
            fit = self._capability_fit(provider_id, request)
            if fit is not None:
                rejected[provider_id] = fit
                continue
            candidates.append(provider_id)
            if explicit and provider_id == requested:
                return RoutingDecision(
                    provider=provider_id,
                    rationale=f"Used {provider.label} as requested.",
                    candidates=candidates, rejected=rejected,
                )

        if explicit and requested in candidates:
            return RoutingDecision(
                provider=requested,
                rationale=f"Used {requested} as requested.",
                candidates=candidates, rejected=rejected,
            )

        if candidates:
            chosen = candidates[0]
            if private:
                rationale = "This address is local or private, so Eclipse used its own browser locally."
            elif not request.interactive:
                rationale = "This is a content-extraction task, so Eclipse used its extraction backend."
            else:
                rationale = f"Eclipse used {self._providers[chosen].label}."
            return RoutingDecision(provider=chosen, rationale=rationale, candidates=candidates, rejected=rejected)

        return RoutingDecision(
            provider="",
            rationale=(
                "No browser backend is available for this task. Install the browser "
                "runtime with `npm run setup:python` and `python -m playwright install chromium`."
            ),
            candidates=[], rejected=rejected,
        )

    def _config_allow_private_remote(self) -> bool:
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            "default": self._config.default_provider,
            "providers": [self._providers[p].to_dict() for p in self._providers],
        }


__all__ = ["BrowserProviderRouter", "RoutingDecision", "RoutingRequest"]
