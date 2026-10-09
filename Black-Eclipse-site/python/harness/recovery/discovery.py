"""Unified capability discovery — one ranked index over every capability.

Eclipse's capabilities live in several registries: the `ToolRegistry` (native +
MCP tools), the model provider/capability registries, and the `SkillRegistry`.
Nothing answered "what can Eclipse actually do that fits this need, and what is
its health/permission cost?" in one place.

`CapabilityIndex` unifies them into `CapabilityDescriptor`s and ranks them for a
free-text need. It is READ-ONLY: it observes registries, it never registers,
enables, installs or calls anything (spec §4.1: "validate actual capability
availability before execution; never invent tool names").

Discovery is the first half of capability acquisition (spec §4.2/§4.3). The
second half — `acquisition_plan` — never silently installs or grants anything: it
returns the ordered, approval-flagged steps a caller (or an operator) must take,
so autonomy means *finding* permitted solutions, not self-granting privilege.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

_TOKEN = re.compile(r"[a-z0-9_]+")

# Trust ranking for provenance: a native capability is more trusted than a
# downloaded/plugin one; used only as a tie-breaker, never to hide a capability.
_TRUST = {"native": 1.0, "provider": 0.9, "skill": 0.8, "mcp": 0.7, "plugin": 0.6}


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    kind: str  # "tool" | "provider" | "skill"
    description: str = ""
    available: bool = True
    permissions: tuple[str, ...] = ()
    health: str = "unknown"
    provenance: str = "native"
    tags: tuple[str, ...] = ()
    cost_tier: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "available": self.available,
            "permissions": list(self.permissions),
            "health": self.health,
            "provenance": self.provenance,
            "tags": list(self.tags),
            "costTier": self.cost_tier,
        }


CapabilitySource = Callable[[], Iterable[CapabilityDescriptor]]


@dataclass(frozen=True)
class CapabilityMatch:
    descriptor: CapabilityDescriptor
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.descriptor.to_dict(), "score": round(self.score, 3), "reason": self.reason}


class CapabilityIndex:
    def __init__(self, sources: Optional[list[CapabilitySource]] = None) -> None:
        self._sources: list[CapabilitySource] = list(sources or [])

    def add_source(self, source: CapabilitySource) -> None:
        self._sources.append(source)

    def descriptors(self) -> list[CapabilityDescriptor]:
        out: list[CapabilityDescriptor] = []
        for source in self._sources:
            try:
                out.extend(source())
            except Exception:  # noqa: BLE001 - a broken registry must not stop discovery
                continue
        return out

    def search(
        self,
        query: str,
        *,
        kind: Optional[str] = None,
        available_only: bool = False,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[CapabilityMatch]:
        tokens = _tokens(query)
        matches: list[CapabilityMatch] = []
        for descriptor in self.descriptors():
            if kind and descriptor.kind != kind:
                continue
            if available_only and not descriptor.available:
                continue
            score, reason = self._score(tokens, descriptor)
            if score <= 0 or score < min_score:
                continue
            matches.append(CapabilityMatch(descriptor, score, reason))
        matches.sort(key=lambda m: (m.score, _TRUST.get(m.descriptor.provenance, 0.5)), reverse=True)
        return matches[: max(1, int(limit))]

    @staticmethod
    def _score(tokens: set[str], descriptor: CapabilityDescriptor) -> tuple[float, str]:
        if not tokens:
            return 0.0, "no query"
        id_tokens = _tokens(descriptor.id)
        text_tokens = _tokens(descriptor.description) | set(descriptor.tags)
        id_overlap = tokens & id_tokens
        text_overlap = tokens & text_tokens
        if not id_overlap and not text_overlap:
            return 0.0, "no match"
        score = 0.0
        reasons: list[str] = []
        if id_overlap:
            score += 1.0 * len(id_overlap) / max(1, len(tokens))
            reasons.append("id match: " + ",".join(sorted(id_overlap)))
        if text_overlap:
            score += 0.5 * len(text_overlap) / max(1, len(tokens))
            reasons.append("description match: " + ",".join(sorted(text_overlap)))
        if descriptor.available:
            score += 0.1
        else:
            reasons.append("currently unavailable")
        score *= _TRUST.get(descriptor.provenance, 0.5)
        return score, "; ".join(reasons) or "match"


@dataclass
class AcquisitionStep:
    action: str  # "use" | "enable" | "install" | "build" | "alternative"
    description: str
    requires_approval: bool = False
    capability_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "description": self.description,
            "requiresApproval": self.requires_approval,
            "capabilityId": self.capability_id,
        }


@dataclass
class AcquisitionPlan:
    query: str
    steps: list[AcquisitionStep] = field(default_factory=list)
    resolved_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "resolvedBy": self.resolved_by,
            "steps": [s.to_dict() for s in self.steps],
            "requiresApproval": any(s.requires_approval for s in self.steps),
        }


def acquisition_plan(query: str, index: CapabilityIndex) -> AcquisitionPlan:
    """The ordered steps to satisfy a need, preferring an existing capability.

    A matching, available capability resolves the plan with a single `use` step.
    Otherwise the plan names the permitted routes (enable an installed
    integration, install a compatible dependency, build an adapter, take an
    alternative route) — mutations are flagged `requires_approval`; nothing is
    performed here.
    """
    matches = index.search(query, limit=5)
    plan = AcquisitionPlan(query=query)
    available = [m for m in matches if m.descriptor.available]
    if available:
        best = available[0]
        plan.resolved_by = best.descriptor.id
        plan.steps.append(AcquisitionStep(
            action="use",
            description=f"use the existing {best.descriptor.kind} '{best.descriptor.id}'",
            capability_id=best.descriptor.id,
        ))
        return plan
    if matches:
        best = matches[0]
        plan.steps.append(AcquisitionStep(
            action="enable",
            description=f"enable the installed-but-unavailable {best.descriptor.kind} '{best.descriptor.id}'",
            requires_approval=True,
            capability_id=best.descriptor.id,
        ))
    plan.steps.append(AcquisitionStep(
        action="install",
        description="install a compatible dependency or integration for this need",
        requires_approval=True,
    ))
    plan.steps.append(AcquisitionStep(
        action="build",
        description="implement a reusable adapter inside the existing architecture",
        requires_approval=True,
    ))
    plan.steps.append(AcquisitionStep(
        action="alternative",
        description="complete the objective through a different legitimate route",
        requires_approval=False,
    ))
    return plan


# ── Built-in sources (lazy, defensive) ───────────────────────────────────────


def tools_source(registry: Any) -> CapabilitySource:
    def _source() -> Iterable[CapabilityDescriptor]:
        descriptors: list[CapabilityDescriptor] = []
        try:
            definitions = registry.list()
        except Exception:  # noqa: BLE001
            return descriptors
        for definition in definitions:
            name = getattr(definition, "name", None)
            if not name:
                continue
            descriptors.append(CapabilityDescriptor(
                id=name,
                kind="tool",
                description=getattr(definition, "description", "") or "",
                available=not getattr(definition, "deprecated", False),
                permissions=(getattr(definition, "permission", "read") or "read",),
                provenance="mcp" if getattr(definition, "effect", None) else "native",
            ))
        return descriptors

    return _source


def skills_source(skill_registry: Any) -> CapabilitySource:
    def _source() -> Iterable[CapabilityDescriptor]:
        descriptors: list[CapabilityDescriptor] = []
        try:
            manifests = skill_registry.all_manifests()
        except Exception:  # noqa: BLE001
            return descriptors
        for manifest in manifests:
            descriptor_id = getattr(manifest, "id", None)
            if not descriptor_id:
                continue
            status = str(getattr(manifest, "status", "") or "")
            descriptors.append(CapabilityDescriptor(
                id=descriptor_id,
                kind="skill",
                description=str(getattr(manifest, "description", "") or ""),
                # A skill is available only when enabled — a draft is inert.
                available=status in ("enabled", "active"),
                permissions=tuple(str(p) for p in (getattr(manifest, "permissions", []) or [])),
                provenance="skill",
                tags=(str(getattr(manifest, "name", "") or ""),),
            ))
        return descriptors

    return _source


def providers_source(list_providers: Optional[Callable[[], list[dict[str, Any]]]] = None) -> CapabilitySource:
    def _source() -> Iterable[CapabilityDescriptor]:
        descriptors: list[CapabilityDescriptor] = []
        try:
            providers = (list_providers or _default_list_providers)()
        except Exception:  # noqa: BLE001
            return descriptors
        for provider in providers:
            pid = provider.get("id")
            if not pid:
                continue
            descriptors.append(CapabilityDescriptor(
                id=pid,
                kind="provider",
                description=str(provider.get("label") or provider.get("description") or ""),
                available=bool(provider.get("configured", provider.get("available", True))),
                provenance="provider",
            ))
        return descriptors

    return _source


def _default_list_providers() -> list[dict[str, Any]]:
    from ..models import list_providers  # noqa: PLC0415

    return list_providers()


def build_default_index(service: Any) -> CapabilityIndex:
    """Build the index over the live service registries (best-effort)."""
    index = CapabilityIndex()
    registry = getattr(service, "registry", None)
    if registry is not None:
        index.add_source(tools_source(registry))
    skill_registry = getattr(service, "skill_registry", None)
    if skill_registry is not None:
        index.add_source(skills_source(skill_registry))
    index.add_source(providers_source())
    return index


__all__ = [
    "AcquisitionPlan",
    "AcquisitionStep",
    "CapabilityDescriptor",
    "CapabilityIndex",
    "CapabilityMatch",
    "acquisition_plan",
    "build_default_index",
    "providers_source",
    "skills_source",
    "tools_source",
]
