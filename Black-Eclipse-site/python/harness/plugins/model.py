"""Plugin lifecycle states, the transition table and the persisted record shape.

The lifecycle is a closed state machine. Every transition is validated against
`ALLOWED_TRANSITIONS` so a plugin can never reach an impossible state, and every
operation the manager exposes drives the machine through this table — there is
exactly one authority for "what state may follow what".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .errors import LifecycleError


class PluginState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    INSTALLED = "INSTALLED"
    ENABLED = "ENABLED"
    LOADING = "LOADING"
    RUNNING = "RUNNING"
    DISABLED = "DISABLED"
    UPDATING = "UPDATING"
    ROLLING_BACK = "ROLLING_BACK"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"
    UNINSTALLED = "UNINSTALLED"


class TrustLevel(str, Enum):
    TRUSTED = "trusted"
    VERIFIED = "verified"
    COMMUNITY = "community"
    UNTRUSTED = "untrusted"


class PluginStatus(str, Enum):
    OFFICIAL = "official"
    VERIFIED = "verified"
    COMMUNITY = "community"
    UNTRUSTED = "untrusted"
    DEPRECATED = "deprecated"
    QUARANTINED = "quarantined"


# The complete transition table. A transition absent from this map is refused.
ALLOWED_TRANSITIONS: dict[PluginState, frozenset[PluginState]] = {
    PluginState.DISCOVERED: frozenset({PluginState.VALIDATING, PluginState.UNINSTALLED}),
    PluginState.VALIDATING: frozenset({PluginState.INSTALLED, PluginState.FAILED, PluginState.UNINSTALLED}),
    PluginState.INSTALLED: frozenset({
        PluginState.ENABLED, PluginState.DISABLED, PluginState.UPDATING,
        PluginState.ROLLING_BACK, PluginState.UNINSTALLED, PluginState.FAILED,
    }),
    PluginState.ENABLED: frozenset({
        PluginState.LOADING, PluginState.DISABLED, PluginState.UPDATING,
        PluginState.ROLLING_BACK, PluginState.FAILED, PluginState.QUARANTINED, PluginState.UNINSTALLED,
    }),
    PluginState.LOADING: frozenset({PluginState.RUNNING, PluginState.FAILED, PluginState.QUARANTINED}),
    PluginState.RUNNING: frozenset({
        PluginState.DISABLED, PluginState.ENABLED, PluginState.UPDATING,
        PluginState.ROLLING_BACK, PluginState.FAILED, PluginState.QUARANTINED, PluginState.UNINSTALLED,
    }),
    PluginState.DISABLED: frozenset({
        PluginState.ENABLED, PluginState.UPDATING, PluginState.ROLLING_BACK,
        PluginState.UNINSTALLED, PluginState.FAILED, PluginState.QUARANTINED,
    }),
    PluginState.UPDATING: frozenset({
        PluginState.ROLLING_BACK, PluginState.INSTALLED, PluginState.ENABLED,
        PluginState.RUNNING, PluginState.FAILED, PluginState.QUARANTINED,
    }),
    PluginState.ROLLING_BACK: frozenset({
        PluginState.INSTALLED, PluginState.ENABLED, PluginState.RUNNING,
        PluginState.FAILED, PluginState.QUARANTINED,
    }),
    PluginState.QUARANTINED: frozenset({
        PluginState.INSTALLED, PluginState.DISABLED, PluginState.UNINSTALLED, PluginState.FAILED,
    }),
    PluginState.FAILED: frozenset({
        PluginState.INSTALLED, PluginState.VALIDATING, PluginState.ROLLING_BACK,
        PluginState.UNINSTALLED, PluginState.QUARANTINED,
    }),
    PluginState.UNINSTALLED: frozenset({PluginState.DISCOVERED, PluginState.VALIDATING, PluginState.INSTALLED}),
}

# States in which the plugin's contributions are live.
ACTIVE_STATES: frozenset[PluginState] = frozenset({PluginState.RUNNING, PluginState.ENABLED})
# States from which an uninstall is legal directly.
UNINSTALLABLE: frozenset[PluginState] = frozenset({
    PluginState.INSTALLED, PluginState.DISABLED, PluginState.FAILED,
    PluginState.QUARANTINED, PluginState.DISCOVERED, PluginState.VALIDATING,
    PluginState.UNINSTALLED, PluginState.ENABLED, PluginState.RUNNING, PluginState.UPDATING,
})


def can_transition(current: PluginState, target: PluginState) -> bool:
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: PluginState, target: PluginState) -> None:
    if not can_transition(current, target):
        raise LifecycleError(
            "PLUGIN_ILLEGAL_TRANSITION",
            f"cannot move plugin from {current.value} to {target.value}",
            detail={"from": current.value, "to": target.value},
        )


@dataclass
class PluginRecord:
    """The persisted registry record for one plugin (mirrors §10 of the spec)."""

    plugin_id: str
    name: str
    version: str
    publisher: str
    manifest: dict[str, Any]
    status: PluginState = PluginState.DISCOVERED
    enabled: bool = False
    trust: TrustLevel = TrustLevel.COMMUNITY
    installation_path: str = ""
    installed_at: str = ""
    updated_at: str = ""
    sdk_version: str = ""
    runtime_type: str = "python"
    permissions: list[str] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    checksum: str = ""
    signature: Optional[str] = None
    verification: str = "unsigned"  # unsigned | checksum | signed | trusted-publisher
    health: str = "unknown"
    configuration: dict[str, Any] = field(default_factory=dict)
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "publisher": self.publisher,
            "status": self.status.value if isinstance(self.status, PluginState) else self.status,
            "enabled": self.enabled,
            "trust": self.trust.value if isinstance(self.trust, TrustLevel) else self.trust,
            "installationPath": self.installation_path,
            "installedAt": self.installed_at,
            "updatedAt": self.updated_at,
            "sdkVersion": self.sdk_version,
            "runtimeType": self.runtime_type,
            "permissions": list(self.permissions),
            "dependencies": list(self.dependencies),
            "checksum": self.checksum,
            "signature": self.signature,
            "verification": self.verification,
            "health": self.health,
            "configuration": dict(self.configuration),
            "lastError": self.last_error,
            "manifest": self.manifest,
        }


__all__ = [
    "PluginState",
    "TrustLevel",
    "PluginStatus",
    "PluginRecord",
    "ALLOWED_TRANSITIONS",
    "ACTIVE_STATES",
    "UNINSTALLABLE",
    "can_transition",
    "assert_transition",
]
