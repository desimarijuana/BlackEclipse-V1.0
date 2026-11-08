"""The decision-provider registry.

One process-wide registry, mirroring the ToolRegistry/ProviderRegistry idiom:
providers register under a stable name, and resolution is explicit about WHY it
refused. Privacy is checked HERE, before any adapter can make a network call, so
a remote decision provider can never be reached in local-only mode.

Resolution order: the caller's explicit preference first, then registration
order. No silent substitution: if the preferred provider is missing or blocked,
the registry falls through to the next candidate and records the reason.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ..models import privacy_local_models
from .providers.base import DecisionProvider


class DecisionRegistry:
    def __init__(self, providers: Iterable[DecisionProvider] = ()) -> None:
        self._providers: dict[str, DecisionProvider] = {}
        for provider in providers:
            self.register(provider)

    # ── Registration ─────────────────────────────────────────────────────────
    def register(self, provider: DecisionProvider) -> DecisionProvider:
        if not provider.name:
            raise ValueError("a decision provider must declare a name")
        self._providers[provider.name] = provider
        return provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def get(self, name: str) -> Optional[DecisionProvider]:
        return self._providers.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def list(self) -> list[dict[str, Any]]:
        return [provider.capabilities() for provider in self._providers.values()]

    # ── Resolution ───────────────────────────────────────────────────────────
    def remote_allowed(self) -> bool:
        return not privacy_local_models()

    def resolve(
        self, preferred: Optional[str] = None
    ) -> tuple[Optional[DecisionProvider], Optional[str]]:
        """Return `(provider, reason)`. `reason` explains an unavailability.

        An explicit preference is NEVER silently substituted: if that provider is
        missing or blocked by privacy, resolution fails with a reason. Only an
        unqualified request falls through registration order.
        """
        if not self._providers:
            return None, "no decision provider is installed"

        allow_remote = self.remote_allowed()

        if preferred:
            provider = self._providers.get(preferred)
            if provider is None:
                return None, f"decision provider {preferred!r} is not installed"
            if not allow_remote and not provider.local:
                return None, (
                    f"decision provider {preferred!r} is remote and local-only "
                    "privacy mode is on (ECLIPSE_PRIVACY=local-models)"
                )
            return provider, None

        blocked_remote = False
        for provider in self._providers.values():
            if not allow_remote and not provider.local:
                blocked_remote = True
                continue
            return provider, None

        if blocked_remote:
            return None, (
                "local-only privacy mode is on (ECLIPSE_PRIVACY=local-models) "
                "and every installed decision provider is remote"
            )
        return None, "no usable decision provider is installed"


__all__ = ["DecisionRegistry"]
