"""Effectful capability hand-offs: route a build to its existing owner.

A pure recipe is built and tested inside the capability builder. An effectful
capability is different: a skill, a tool, a UI component/page or a harness change
has an existing owner with its own approval gate and its own verification. This
module produces the ONE typed hand-off for those kinds. It never executes the
build, never activates anything and never invents a second builder.

The hand-off names:
  * the existing surface and the exact next tool,
  * the arguments that surface needs (with missing inputs named honestly),
  * the acceptance + evidence that prove completion,
  * who activates the result (always an operator or the existing lifecycle).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .request import CapabilityRequest, classify, slug_for

EFFECTFUL_KINDS: tuple[str, ...] = (
    "tool", "skill", "bot", "ui_widget", "ui_page", "harness_change", "plugin",
)

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = frozenset({
    "a", "an", "the", "for", "of", "to", "in", "on", "and", "or", "with",
    "my", "me", "our", "is", "are", "be", "it", "this", "that", "some",
    "any", "need", "want", "please", "can", "you", "make", "build", "create",
    "add", "new", "tool", "capability", "able", "from", "now", "use", "using",
})


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for token in _TOKEN.findall((text or "").lower()):
        if token in _STOP or token in out:
            continue
        out.add(token[:-1] if token.endswith("s") and len(token) > 3 else token)
    return out


def _match_kit(need: str) -> Optional[Any]:
    """The closest ready-made kit, or None. Pure token overlap, no model."""
    try:
        from ..code.kits.loader import load_catalog  # noqa: PLC0415

        kits = load_catalog()
    except Exception:  # noqa: BLE001 - a broken kit library must not block a hand-off
        return None
    wanted = _tokens(need)
    if not wanted:
        return None
    best: Optional[tuple[float, Any]] = None
    for kit in kits:
        manifest = kit.manifest
        haystack = " ".join([
            manifest.id, manifest.title, manifest.acceptance,
            " ".join(manifest.produces),
        ])
        overlap = wanted & _tokens(haystack)
        score = len(overlap) / max(1, len(wanted))
        if score < 0.2:
            continue
        if best is None or score > best[0]:
            best = (score, kit)
    return best[1] if best is not None else None


def _acceptance(request: CapabilityRequest, kind: str) -> list[str]:
    lines = [line.strip() for line in request.acceptance if line and line.strip()]
    if lines:
        return lines[:12]
    return [
        f"The {kind.replace('_', ' ')} is implemented and its acceptance evidence is recorded.",
    ]


@dataclass
class EffectfulHandoff:
    kind: str
    surface: str
    next_tool: str
    title: str
    objective: str
    arguments: dict[str, Any] = field(default_factory=dict)
    acceptance: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    verification: str = ""
    activation: str = "operator"
    requires_approval: bool = True
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    resume: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "surface": self.surface,
            "nextTool": self.next_tool,
            "title": self.title,
            "objective": self.objective,
            "arguments": dict(self.arguments),
            "acceptance": list(self.acceptance),
            "evidence": list(self.evidence),
            "verification": self.verification,
            "activation": self.activation,
            "requiresApproval": self.requires_approval,
            "missing": list(self.missing),
            "notes": list(self.notes),
            "resume": dict(self.resume),
        }


def _resume() -> dict[str, Any]:
    return {
        "from": "last_checkpoint",
        "after": "the target surface records its acceptance evidence",
    }


def _tool(request: CapabilityRequest, acceptance: list[str]) -> EffectfulHandoff:
    kit = _match_kit(request.need)
    if kit is not None:
        manifest = kit.manifest
        input_names = [item.name for item in manifest.inputs if item.required]
        missing = [f"a value for the kit input {name!r}" for name in input_names]
        return EffectfulHandoff(
            kind="tool",
            surface="scaffold_kit",
            next_tool="scaffold_kit",
            title=request.need.strip()[:120],
            objective=request.need,
            arguments={"kit_id": manifest.id, "inputs": {}},
            acceptance=acceptance + [manifest.acceptance],
            evidence=[
                "the kit's declared files are written into the disposable workspace",
                "the kit's shipped acceptance test / checks pass",
            ],
            verification=(
                "the kit renders only its declared outputs and its checks pass; "
                "the result stays workspace-local until an operator promotes it"
            ),
            missing=missing,
            notes=[
                "scaffold_kit is the existing tool-building surface; it writes only "
                "the declared kit outputs",
                "the hand-off does not register or enable a new tool",
            ],
            resume=_resume(),
        )
    return EffectfulHandoff(
        kind="tool",
        surface="code_agent",
        next_tool="create_goal",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={
            "request": request.need,
            "title": request.need.strip()[:120],
            "taskType": "code",
            "acceptance": acceptance,
        },
        acceptance=acceptance,
        evidence=[
            "the durable code task's acceptance criteria pass",
            "the relevant tests pass",
            "the change lands only through the code surface's approvals",
        ],
        verification=(
            "a durable code task proves the tool works with tests and review; "
            "activation stays an operator decision"
        ),
        notes=[
            "no ready-made kit fits, so the existing code agent owns the build",
            "this hand-off creates nothing; create_goal starts the tracked task",
        ],
        resume=_resume(),
    )


def _bot(request: CapabilityRequest, acceptance: list[str]) -> EffectfulHandoff:
    """A persistent scheduled agent: the existing Automation/bots surface owns it.

    This is deliberately NOT a `tool` and NOT `scaffold_kit`: a bot is a durable
    scheduled agent, not a code artefact. `bot_create` stores it and its handler
    requests the single-use `bot_schedule` approval before an autonomous
    schedule exists.
    """
    return EffectfulHandoff(
        kind="bot",
        surface="bot_create",
        next_tool="bot_create",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={
            "name": slug_for(request.need)[:60],
            "objective": request.need,
            "triggerType": "cron",
        },
        acceptance=acceptance,
        evidence=[
            "bot_create stores the bot, its objective and its schedule",
            "bot_run proves one run; bot_history shows its results",
            "the schedule is computed in the stored IANA timezone, not server time",
        ],
        verification=(
            "the handler requests a single-use bot_schedule approval before an "
            "autonomous schedule is created; nothing runs until the operator approves"
        ),
        missing=[
            "the cron expression and the IANA timezone for the schedule",
        ],
        notes=[
            "bot_create is the existing persistent-bot surface; do NOT use scaffold_kit",
            "the bot stays in the Bots workspace and runs after the browser closes",
            "pin the timezone explicitly (e.g. America/New_York), never rely on UTC",
        ],
        resume=_resume(),
    )


def _skill(request: CapabilityRequest, acceptance: list[str]) -> EffectfulHandoff:
    instructions = "\n".join(acceptance) if request.acceptance else request.evidence.strip()
    missing = [] if instructions else ["the skill's step-by-step instructions"]
    return EffectfulHandoff(
        kind="skill",
        surface="skill_create",
        next_tool="skill_create",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={
            "name": slug_for(request.need),
            "description": (request.evidence or request.need).strip()[:300],
            "instructions": instructions,
        },
        acceptance=acceptance,
        evidence=[
            "the SkillManifest validates and is stored as a draft",
            "evaluation and promotion are recorded before the skill can be enabled",
        ],
        verification=(
            "the skill is a validated, inert draft; the existing evaluation + "
            "promotion lifecycle is the only enable path"
        ),
        missing=missing,
        notes=[
            "skill_create is single-use operator-approval gated",
            "authoring never enables a skill and never grants a permission",
        ],
        resume=_resume(),
    )


def _ui(request: CapabilityRequest, kind: str, acceptance: list[str]) -> EffectfulHandoff:
    return EffectfulHandoff(
        kind=kind,
        surface="ui_start_engineering",
        next_tool="ui_start_engineering",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={
            "text": request.need + (f"\n{request.evidence}" if request.evidence else ""),
            "title": request.need.strip()[:100],
        },
        acceptance=acceptance,
        evidence=[
            "the engineering task's acceptance criteria pass",
            "a new component is registered in the UI catalog, or the page revision is saved",
        ],
        verification=(
            "the Task/Plan runtime owns the work and its acceptance criteria; "
            "composition/registration stays a separate reviewed step"
        ),
        requires_approval=False,
        missing=[],
        notes=[
            "ui_start_engineering is the existing engineering escalation, not a second builder",
            "the hand-off creates no UI state; the task owns the change",
        ],
        resume=_resume(),
    )


def _code(request: CapabilityRequest, acceptance: list[str], *, harness: bool) -> EffectfulHandoff:
    return EffectfulHandoff(
        kind="harness_change" if harness else "tool",
        surface="code_agent",
        next_tool="create_goal",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={
            "request": request.need,
            "title": request.need.strip()[:120],
            "taskType": "code",
            "acceptance": acceptance,
        },
        acceptance=acceptance,
        evidence=[
            "the durable task's acceptance criteria pass",
            "the repository's tests pass",
            "review and landing approvals are recorded",
        ],
        verification=(
            "a durable code task proves the change with tests and review; authority "
            "files stay protected and landing stays operator-gated"
        ),
        notes=[
            "harness changes use the existing code agent / RSL surface, never a new builder"
            if harness else "the existing code agent owns the build",
            "authority files stay protected; landing is operator-gated",
            "the hand-off creates nothing; create_goal starts the tracked task",
        ],
        resume=_resume(),
    )


def _plugin(request: CapabilityRequest) -> EffectfulHandoff:
    return EffectfulHandoff(
        kind="plugin",
        surface="external_adapter",
        next_tool="capability_external",
        title=request.need.strip()[:120],
        objective=request.need,
        arguments={"need": request.need, "kind": "auto"},
        acceptance=_acceptance(request, "plugin"),
        evidence=[
            "the external proposal names the surface, credential names and approval",
            "an approved install writes a DISABLED config",
            "the operator enables it explicitly in Settings",
        ],
        verification=(
            "the external lane owns the proposal and the existing MCP/plugin gate owns "
            "the install; this hand-off enables nothing"
        ),
        notes=[
            "credentials are names only; values never enter chat or a record",
        ],
        resume=_resume(),
    )


def plan_handoff(
    request: CapabilityRequest, *, kind: str = "",
) -> EffectfulHandoff:
    """The typed hand-off for an effectful kind. Pure; never executes anything."""
    chosen = classify(request.need, kind or request.kind)
    acceptance = _acceptance(request, chosen)
    if chosen == "bot":
        return _bot(request, acceptance)
    if chosen == "skill":
        return _skill(request, acceptance)
    if chosen in ("ui_widget", "ui_page"):
        return _ui(request, chosen, acceptance)
    if chosen == "harness_change":
        return _code(request, acceptance, harness=True)
    if chosen == "plugin":
        return _plugin(request)
    if chosen == "tool":
        return _tool(request, acceptance)
    return _code(request, acceptance, harness=False)


__all__ = ["EFFECTFUL_KINDS", "EffectfulHandoff", "plan_handoff"]
