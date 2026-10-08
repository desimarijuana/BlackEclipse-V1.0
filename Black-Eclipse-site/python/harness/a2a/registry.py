"""The canonical Agent Registry.

Agent behaviour is DATA: a versioned `AgentDefinition` (capabilities, tools,
permissions, budgets, delegation rights) persisted on the ONE agent-memory
connection. Nothing about a specific agent is hardcoded across the codebase — the
runtime, the planner and the tools all read the registry.

The registry owns: register / update / remove / get / list / enable / disable /
validate, plus the machine-readable capability index the planner uses to answer
"which agent can do this?".
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import AgentDefinition, AgentStatus
from .store import A2AStore

REGISTRY_NOT_FOUND = "AGENT_NOT_FOUND"
REGISTRY_INVALID = "AGENT_INVALID"
REGISTRY_DUPLICATE_VERSION = "AGENT_DUPLICATE_VERSION"

Publisher = Callable[[str, dict[str, Any]], None]


class RegistryError(ValueError):
    """A structured registry error. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class AgentRegistry:
    """Versioned agent definitions + the capability index."""

    def __init__(self, store: A2AStore, *, publisher: Optional[Publisher] = None) -> None:
        self._store = store
        self._publisher = publisher

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def register_agent(self, definition: AgentDefinition, *, overwrite: bool = True) -> AgentDefinition:
        self.validate_agent(definition)
        existing = self._store.get_agent(definition.id, definition.version)
        if existing is not None and not overwrite:
            raise RegistryError(
                REGISTRY_DUPLICATE_VERSION,
                f"{definition.id}@{definition.version} already exists",
            )
        saved = self._store.save_agent(definition)
        self._emit("agent.registered" if existing is None else "agent.updated", {
            "agentId": saved.id, "version": saved.version, "status": saved.status.value,
        })
        return saved

    def update_agent(self, agent_id: str, fields: dict[str, Any], *, bump_version: bool = True) -> AgentDefinition:
        current = self.get_agent(agent_id)
        merged = current.model_dump()
        merged.update(fields)
        if bump_version:
            merged["version"] = _bump(current.version)
        from datetime import datetime, timezone

        merged["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        definition = AgentDefinition(**merged)
        return self.register_agent(definition)

    def remove_agent(self, agent_id: str) -> bool:
        removed = self._store.delete_agent(agent_id)
        if removed:
            self._emit("agent.removed", {"agentId": agent_id})
        return removed

    def get_agent(self, agent_id: str, version: Optional[str] = None) -> AgentDefinition:
        definition = self._store.get_agent(agent_id, version)
        if definition is None:
            raise RegistryError(REGISTRY_NOT_FOUND, f"No agent {agent_id!r}.")
        return definition

    def has_agent(self, agent_id: str) -> bool:
        return self._store.get_agent(agent_id) is not None

    def list_agents(self, *, status: Optional[str] = None, limit: int = 200) -> list[AgentDefinition]:
        return self._store.list_agents(status=status, limit=limit)

    def agent_versions(self, agent_id: str) -> list[dict[str, Any]]:
        return self._store.agent_versions(agent_id)

    def enable_agent(self, agent_id: str) -> AgentDefinition:
        return self._set_status(agent_id, AgentStatus.ACTIVE)

    def disable_agent(self, agent_id: str) -> AgentDefinition:
        return self._set_status(agent_id, AgentStatus.DISABLED)

    def _set_status(self, agent_id: str, status: AgentStatus) -> AgentDefinition:
        if not self._store.set_agent_status(agent_id, status):
            raise RegistryError(REGISTRY_NOT_FOUND, f"No agent {agent_id!r}.")
        self._emit("agent.status.changed", {"agentId": agent_id, "status": status.value})
        return self.get_agent(agent_id)

    def validate_agent(self, definition: AgentDefinition) -> None:
        """Refuse an incoherent definition with a named reason."""
        if not definition.name.strip():
            raise RegistryError(REGISTRY_INVALID, "an agent needs a name")
        if definition.max_concurrency < 1:
            raise RegistryError(REGISTRY_INVALID, "maxConcurrency must be at least 1")
        if definition.timeout_ms < 1_000:
            raise RegistryError(REGISTRY_INVALID, "timeoutMs is too small to be useful")
        # A delegate that cannot delegate must not declare delegates it cannot use.
        if definition.allowed_delegates and not definition.can_delegate:
            raise RegistryError(
                REGISTRY_INVALID, "allowedDelegates is set but canDelegate is false",
            )
        unknown = [c for c in definition.allowed_delegates if not self._store.get_agent(c)]
        if unknown and definition.allowed_delegates:
            # Allow forward references at seed time only when the registry is fresh;
            # a live registration must name real agents (fail-closed otherwise).
            known = {a.id for a in self._store.list_agents(limit=1000)}
            dangling = [c for c in unknown if c not in known]
            if dangling:
                raise RegistryError(
                    REGISTRY_INVALID, f"allowedDelegates names unknown agent(s): {dangling}",
                )

    # ── capability index (§6) ──────────────────────────────────────────────────

    def capability_index(self) -> dict[str, list[str]]:
        """Map each capability noun to the ACTIVE agents that declare it."""
        index: dict[str, list[str]] = {}
        for definition in self.list_agents(status=AgentStatus.ACTIVE.value, limit=1000):
            for capability in definition.capabilities:
                index.setdefault(capability, []).append(definition.id)
        return index

    def find_capable(self, capability: str, *, enabled_only: bool = True) -> list[AgentDefinition]:
        matches = [
            d for d in self.list_agents(limit=1000)
            if capability in d.capabilities
            and (not enabled_only or d.status is AgentStatus.ACTIVE)
        ]
        return matches

    def capable_agent_for(self, capability: str) -> Optional[str]:
        """The FIRST active agent that declares `capability` (deterministic)."""
        agents = sorted(self.find_capable(capability), key=lambda d: d.id)
        return agents[0].id if agents else None

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._publisher is None:
            return
        try:
            self._publisher(event_type, data)
        except Exception:  # noqa: BLE001 - an event must never break a registry write
            pass


def _bump(version: str) -> str:
    try:
        major, minor, patch = (int(x) for x in version.split(".")[:3])
        return f"{major}.{minor}.{patch + 1}"
    except (ValueError, AttributeError):
        return "1.0.1"


__all__ = [
    "AgentRegistry",
    "Publisher",
    "REGISTRY_DUPLICATE_VERSION",
    "REGISTRY_INVALID",
    "REGISTRY_NOT_FOUND",
    "RegistryError",
]
