"""Gap detection and the cheapest safe route for a capability request."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..recovery.discovery import CapabilityIndex, tools_source
from .manifest import CapabilityPort

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "a", "an", "the", "for", "of", "to", "in", "on", "and", "or", "with",
    "my", "me", "our", "is", "are", "be", "it", "this", "that", "some",
    "any", "need", "want", "please", "can", "you", "compute", "calculate",
    "work", "out", "give", "show", "make", "get", "use", "using", "from",
    "now", "price", "prices", "series", "values", "value", "data", "time",
    "over",
})

_REUSABLE = (
    "from now on", "every time", "each time", "reusable", "reuse", "again",
    "add a tool", "build a", "create a", "make it able", "save it", "recipe",
    "template", "repeat", "automate", "always",
)
_ONE_OFF = ("just this", "one-off", "one off", "for this", "quickly", "ad hoc")
_REPORT = ("report", "pdf", "docx", "xlsx", "deck", "memo", "tear sheet")
_UI = ("widget", "page", "dashboard", "screen", "layout", "component")
_PLUGIN = ("broker", "connect", "integration", "plugin", "mcp", "api", "oauth")
_SKILL = ("skill", "procedure", "routine", "playbook")
_HARNESS = ("harness", "agent loop", "model provider", "policy")
_TOOL = ("tool", "adapter", "endpoint")

_KIND_SURFACE = {
    "one_off": "analysis_run",
    "recipe": "capability_builder",
    "report_template": "capability_builder",
    "tool": "scaffold_kit",
    "skill": "skill_create",
    "ui_widget": "ui_start_engineering",
    "ui_page": "ui_start_engineering",
    "plugin": "external_adapter",
    "harness_change": "code_agent_or_rsl",
}

# The exact existing tool that owns an effectful build. A display surface is not
# a tool name; the hand-off always names a callable tool (or the operator).
_NEXT_TOOL = {
    "tool": "scaffold_kit",
    "skill": "skill_create",
    "ui_widget": "ui_start_engineering",
    "ui_page": "ui_start_engineering",
    "plugin": "capability_external",
    "harness_change": "create_goal",
}

_PURE = frozenset({"recipe", "report_template"})
_EFFECTFUL = frozenset({"tool", "skill", "ui_widget", "ui_page", "plugin", "harness_change"})


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP}


def _ordered_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in _TOKEN.findall((text or "").lower()):
        if token in _STOP or token in seen:
            continue
        seen.append(token)
    return seen


def _contains(text: str, words: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in words)


def slug_for(need: str, explicit: str = "") -> str:
    if explicit:
        candidate = explicit.strip().lower().replace("-", "_")
        if re.fullmatch(r"[a-z][a-z0-9_]{1,63}", candidate):
            return candidate
    tokens = _ordered_tokens(need)
    picked = tokens[:4]
    if not picked:
        picked = ["capability"]
    slug = "_".join(picked)
    slug = re.sub(r"[^a-z0-9_]+", "_", slug).strip("_")
    if not slug or not slug[0].isalpha():
        slug = "capability_" + hashlib.sha256((need or "").encode("utf-8")).hexdigest()[:8]
    return slug[:64]


class CapabilityRequest(BaseModel):
    model_config = _CAMEL

    request_id: str = Field(default_factory=lambda: "capreq_" + uuid.uuid4().hex[:16])
    need: str = Field(..., min_length=1, max_length=2_000)
    examples: list[str] = Field(default_factory=list, max_length=8)
    evidence: str = Field(default="", max_length=4_000)
    kind: str = Field(default="auto", max_length=32)
    scope: str = Field(default="workspace", max_length=16)
    capability_id: str = Field(default="", max_length=64)
    version: str = Field(default="", max_length=16)
    inputs: list[CapabilityPort] = Field(default_factory=list, max_length=24)
    outputs: list[CapabilityPort] = Field(default_factory=list, max_length=24)
    permissions: list[str] = Field(default_factory=lambda: ["analysis.execute"], max_length=8)
    effect: str = Field(default="read", max_length=24)
    imports: list[str] = Field(default_factory=list, max_length=32)
    acceptance: list[str] = Field(default_factory=list, max_length=12)
    timeout_ms: int = Field(default=30_000, ge=100, le=600_000)
    implementation: str = Field(default="", max_length=20_000)
    test: str = Field(default="", max_length=20_000)
    sample_inputs: dict[str, Any] = Field(default_factory=dict)

    # Filled by the builder when an effectful kind is routed to its existing
    # owner. Kept on the same durable request record; never an execution grant.
    handoff: dict[str, Any] = Field(default_factory=dict)

    # The durable task this capability was requested for, when the request came
    # from a scheduled task run. Activation resumes it from its checkpoint.
    resume_task_id: str = Field(default="", max_length=64)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_dict(cls, raw: Any) -> "CapabilityRequest":
        if not isinstance(raw, dict):
            raise ValueError("capability request must be an object")
        return cls.model_validate(raw)


@dataclass
class CapabilityAssessment:
    need: str
    status: str
    kind: str
    surface: str
    scope: str
    one_off: bool
    requires_approval: bool
    resolved_by: Optional[str] = None
    matches: list[dict[str, Any]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: str = ""
    next_tool: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "need": self.need,
            "status": self.status,
            "kind": self.kind,
            "surface": self.surface,
            "scope": self.scope,
            "oneOff": self.one_off,
            "requiresApproval": self.requires_approval,
            "resolvedBy": self.resolved_by,
            "matches": list(self.matches),
            "steps": list(self.steps),
            "missing": list(self.missing),
            "reason": self.reason,
            "nextTool": self.next_tool,
        }


def classify(need: str, kind: str = "auto") -> str:
    explicit = (kind or "auto").strip().lower()
    if explicit and explicit != "auto":
        return explicit
    text = (need or "").lower()
    reusable = _contains(text, _REUSABLE)
    if _contains(text, _UI):
        return "ui_widget" if "widget" in text else "ui_page"
    if _contains(text, _PLUGIN):
        return "plugin"
    if _contains(text, _SKILL):
        return "skill"
    if _contains(text, _HARNESS) and _contains(text, ("change", "fix", "improve", "patch")):
        return "harness_change"
    if _contains(text, _REPORT):
        return "report_template"
    if _contains(text, _TOOL):
        return "tool"
    if reusable:
        return "recipe"
    if _contains(text, _ONE_OFF):
        return "one_off"
    return "one_off"


def _recipe_matches(need: str) -> list[dict[str, Any]]:
    from ..code.recipes import list_recipes

    tokens = _tokens(need)
    out: list[dict[str, Any]] = []
    for recipe in list_recipes():
        haystack = " ".join([
            str(recipe.get("name") or ""),
            str(recipe.get("answers") or ""),
            " ".join(
                str(item.get("name") or "") + " " + str(item.get("description") or "")
                for item in (recipe.get("inputs") or [])
            ),
        ])
        overlap = tokens & _tokens(haystack)
        if not overlap:
            continue
        score = len(overlap) / max(1, len(tokens))
        if score < 0.2:
            continue
        out.append({
            "capability": {
                "id": recipe.get("name"), "kind": "recipe",
                "description": recipe.get("answers") or "", "available": True,
            },
            "score": round(score, 3),
            "reason": "recipe match: " + ",".join(sorted(overlap)),
        })
    out.sort(key=lambda item: item["score"], reverse=True)
    return out[:5]


def _generated_matches(store: Any, root: Optional[Path]) -> list[dict[str, Any]]:
    if store is None:
        return []
    try:
        from .registry import generated_descriptors

        return [descriptor.to_dict() for descriptor in generated_descriptors(store, root)]
    except Exception:
        return []


def _tool_matches(need: str, tool_registry: Any) -> list[dict[str, Any]]:
    if tool_registry is None:
        return []
    index = CapabilityIndex([tools_source(tool_registry)])
    return [match.to_dict() for match in index.search(need, limit=5, min_score=0.35)]


def _merge_matches(groups: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for match in group:
            capability = match.get("capability") if isinstance(match, dict) else None
            if not isinstance(capability, dict):
                continue
            cap_id = str(capability.get("id") or "")
            key = f"{capability.get('kind')}:{cap_id}"
            if not cap_id or key in seen:
                continue
            seen.add(key)
            merged.append(match)
    merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return merged[:8]


def _available_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in matches:
        capability = match.get("capability") or {}
        if capability.get("available") is not False:
            out.append(match)
    return out


def assess(
    need: str,
    *,
    kind: str = "auto",
    scope: str = "workspace",
    tool_registry: Any = None,
    store: Any = None,
    root: Optional[Path] = None,
    capability_id: str = "",
) -> CapabilityAssessment:
    chosen = classify(need, kind)
    recipe_matches = _recipe_matches(need)
    tool_matches = _tool_matches(need, tool_registry)
    generated = _generated_matches(store, root)
    generated_matches = [
        {
            "capability": descriptor, "score": 1.0,
            "reason": "active generated capability",
        }
        for descriptor in generated
        if _tokens(need) & _tokens(str(descriptor.get("id", "")) + " " + str(descriptor.get("description", "")))
    ]
    matches = _merge_matches([recipe_matches, generated_matches, tool_matches])
    available = _available_matches(matches)
    if chosen in _PURE:
        available = [
            match for match in available
            if (match.get("capability") or {}).get("kind") == "recipe"
        ]
    if available:
        best = available[0]
        capability = best.get("capability") or {}
        return CapabilityAssessment(
            need=need,
            status="satisfied",
            kind=str(capability.get("kind") or chosen),
            surface="existing_capability",
            scope=scope,
            one_off=False,
            requires_approval=False,
            resolved_by=str(capability.get("id") or ""),
            matches=matches,
            steps=[f"use the existing {capability.get('kind', 'capability')} '{capability.get('id')}'"],
            reason="an available capability already fits this need",
            next_tool="analysis_run" if capability.get("kind") in ("recipe", "report_template") else "",
        )
    if chosen == "one_off":
        return CapabilityAssessment(
            need=need,
            status="one_off",
            kind="one_off",
            surface=_KIND_SURFACE["one_off"],
            scope=scope,
            one_off=True,
            requires_approval=False,
            matches=matches,
            steps=[
                "run the computation once with analysis_run",
                "return the result and persist no recipe",
            ],
            reason="this reads as a single computation, not a reusable capability",
            next_tool="analysis_run",
        )
    surface = _KIND_SURFACE.get(chosen, "capability_builder")
    requires_approval = chosen in _EFFECTFUL or scope == "global"
    missing: list[str] = []
    if chosen in _PURE:
        missing.extend(["implementation source", "sample inputs", "contract test"])
    elif chosen == "plugin":
        missing.extend([
            "operator-supplied credentials (names only)",
            "operator approval",
            "an MCP preset, plugin folder or MCP endpoint",
        ])
    else:
        missing.extend(["the hand-off inputs", "operator approval for activation"])
    if chosen in _PURE:
        steps = [
            "record the capability request and its gap",
            "write a versioned manifest, source and contract test into the workspace",
            "run static checks and the contract test in the PTC sandbox",
            "activate only after the test passes",
            "retry the original task with the new capability",
        ]
    elif chosen == "plugin":
        steps = [
            "record the external capability request and its gap",
            "propose the existing MCP preset or plugin platform surface",
            "collect credential NAMES from the operator (never values)",
            "install disabled through the approved MCP/plugin gate",
            "the operator enables it explicitly, then resumes the original task",
        ]
    else:
        steps = [
            "record the effectful capability request and its gap",
            "prepare a typed hand-off for its existing owner",
            "call the named surface with the hand-off arguments",
            "the target surface records its acceptance evidence and approval",
            "the operator activates it, then resumes the original task",
        ]
    next_tool = (
        "capability_build" if chosen in _PURE
        else _NEXT_TOOL.get(chosen, "")
    )
    return CapabilityAssessment(
        need=need,
        status="gap",
        kind=chosen,
        surface=surface,
        scope=scope,
        one_off=False,
        requires_approval=requires_approval,
        matches=matches,
        steps=steps,
        missing=missing,
        reason=(
            "no available capability fits this need; the cheapest safe surface is "
            f"{surface}"
        ),
        next_tool=next_tool,
    )


__all__ = [
    "CapabilityAssessment",
    "CapabilityRequest",
    "assess",
    "classify",
    "slug_for",
]
