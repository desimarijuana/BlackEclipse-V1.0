"""Provider contracts for the Channel Gateway.

A provider is one external messaging surface. The gateway owns identity, scope,
idempotency, rate limiting, dispatch and audit; a provider only normalizes
inbound traffic and sends replies.

`ProviderSpec` is the single source of truth for the operator surface: it says
which config fields exist, which are required, and how inbound arrives. The
service, the webhook router and the settings UI all read from it, so adding a
provider is a spec + a factory — never edits in five unrelated modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

InboundMode = Literal["poll", "push", "both", "none"]


@dataclass(frozen=True)
class ConfigField:
    """One operator-visible config field.

    `secret` is advisory for the UI; redaction is still enforced by the
    security heuristic in `config.is_sensitive_key` plus the encrypted vault.
    """

    key: str
    label: str
    secret: bool = False
    required: bool = False
    placeholder: str = ""
    hint: str = ""


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    label: str
    description: str
    inbound_mode: InboundMode
    config_fields: tuple[ConfigField, ...] = ()
    capabilities: frozenset[str] = frozenset()
    # Alternative credential groups: at least one group must be fully present.
    any_required: tuple[tuple[str, ...], ...] = ()
    # Boolean-ish config keys (e.g. "useAdc"); "false" is not configured.
    flag_fields: frozenset[str] = frozenset()

    @property
    def required_fields(self) -> tuple[ConfigField, ...]:
        return tuple(field for field in self.config_fields if field.required)

    @property
    def required_keys(self) -> tuple[str, ...]:
        return tuple(field.key for field in self.required_fields)

    def is_configured(self, get: Callable[[str], Any]) -> bool:
        """Configured = every required field AND one alternative group.

        `get` returns the resolved value (the service passes the vault-aware
        resolver), so boolean-ish fields such as `useAdc=false` do not count as
        configured.
        """

        def present(key: str) -> bool:
            value = get(key)
            if key in self.flag_fields:
                return str(value).strip().lower() in ("1", "true", "yes", "on")
            return bool(value)

        if not all(present(key) for key in self.required_keys):
            return False
        if self.any_required:
            return any(all(present(key) for key in group) for group in self.any_required)
        return True


@dataclass(frozen=True)
class ProviderContext:
    """Everything a factory needs, without exposing the store or the vault."""

    kind: str
    config: dict[str, Any]
    secret: Callable[[str], str]


__all__ = [
    "ConfigField",
    "InboundMode",
    "ProviderContext",
    "ProviderSpec",
]
