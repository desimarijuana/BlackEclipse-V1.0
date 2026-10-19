"""Round 4 (W5/W9) — the capability acquisition lifecycle.

Discovery answers "what could fit"; this module answers "what is the ordered,
permitted route from here, what is missing, and what must a person approve?".

    discover → assess → propose → acquire → validate → retry

It is deliberately NOT an installer or a self-granting broker:

* `use` and `alternative` are read-only resolutions and may be reported as ready;
* `enable` / `install` / `build` are mutations. They are always approval-flagged
  and only run through a caller-supplied handler; without one the step is handed
  back with its exact surface and missing information;
* validation without a real contract test is reported `unverified`, never passed;
* retry resumes the original task from its checkpoint via a caller callback —
  this module never invents a retry route.

The planning half reuses `discovery.acquisition_plan`; the execution half is the
thin seam the executor and the operator console call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .discovery import AcquisitionPlan, CapabilityIndex, acquisition_plan

#: The surfaces an acquisition step can target. A step names ONE surface so the
#: caller knows which existing gate to use.
SURFACES: tuple[str, ...] = (
    "existing_tool", "skill", "plugin", "scaffold_kit", "engineering",
    "alternative", "operator",
)

_READ_ONLY_ACTIONS = frozenset({"use", "alternative"})


@dataclass(frozen=True)
class AcquisitionStep:
    action: str
    description: str
    capability_id: Optional[str]
    requires_approval: bool
    surface: str
    ready: bool
    reason: str = ""
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "description": self.description,
            "capabilityId": self.capability_id,
            "requiresApproval": self.requires_approval,
            "surface": self.surface,
            "ready": self.ready,
            "reason": self.reason,
            "missing": list(self.missing),
        }


@dataclass
class AcquisitionProposal:
    query: str
    steps: list[AcquisitionStep] = field(default_factory=list)
    resolved_by: Optional[str] = None
    retry: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_approval(self) -> bool:
        return any(step.requires_approval for step in self.steps)

    @property
    def gaps(self) -> list[str]:
        out: list[str] = []
        for step in self.steps:
            out.extend(step.missing)
        return list(dict.fromkeys(out))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "resolvedBy": self.resolved_by,
            "steps": [step.to_dict() for step in self.steps],
            "requiresApproval": self.requires_approval,
            "gaps": self.gaps,
            "retry": dict(self.retry),
        }


def _install_surface(facts: Optional[dict[str, Any]]) -> tuple[str, bool, str, tuple[str, ...]]:
    """The install surface a SUPPLIED fact resolves to, or the honest gap.

    A fact is what the operator provides; without one the step stays on the
    generic `operator` surface with the exact missing information named — the
    planner never invents a source, a path or a kit.
    """
    facts = facts or {}
    if str(facts.get("source") or "").strip():
        return (
            "skill", False,
            "a GitHub source was supplied; the approved single-use skill_install "
            "approval performs the install",
            (),
        )
    if str(facts.get("pluginPath") or "").strip():
        return (
            "plugin", False,
            "a plugin folder was supplied; the approved plugin install places it",
            (),
        )
    if str(facts.get("kitId") or "").strip():
        return (
            "scaffold_kit", False,
            "a kit id was supplied; the approved build scaffolds it through a "
            "durable code task",
            (),
        )
    return (
        "operator", False,
        "no generic installer: provide the source/credential, then use skill_install "
        "or the approved dependency path",
        ("unknown: no source, credential or dependency was supplied",),
    )


def _surface_for(
    action: str, facts: Optional[dict[str, Any]] = None,
) -> tuple[str, bool, str, tuple[str, ...]]:
    """The existing gate for an action, whether it is ready, and what is missing."""
    if action == "use":
        return ("existing_tool", True, "already registered and available", ())
    if action == "enable":
        return ("existing_tool", False, "installed but currently unavailable", ())
    if action == "install":
        return _install_surface(facts)
    if action == "build":
        return (
            "engineering", False,
            "build through ui_start_engineering (a UI capability), a skill draft, or a scaffold_kit shape",
            ("the build target and its acceptance test are not supplied",),
        )
    return ("alternative", True, "complete the objective through a different permitted route", ())


def propose(
    query: str,
    index: CapabilityIndex,
    *,
    task_id: Optional[str] = None,
    facts: Optional[dict[str, Any]] = None,
) -> AcquisitionProposal:
    """The ordered lifecycle proposal for a capability need.

    `facts` are operator-supplied install inputs (a GitHub source, a plugin
    folder, a kit id); they only resolve WHICH existing gate an install step
    names — the step stays approval-flagged, and the handler re-checks.
    """
    plan: AcquisitionPlan = acquisition_plan(query, index)
    steps: list[AcquisitionStep] = []
    for raw in plan.steps:
        surface, ready, reason, missing = _surface_for(raw.action, facts)
        steps.append(AcquisitionStep(
            action=raw.action,
            description=raw.description,
            capability_id=raw.capability_id,
            requires_approval=bool(raw.requires_approval or raw.action not in _READ_ONLY_ACTIONS),
            surface=surface,
            ready=ready and raw.action in _READ_ONLY_ACTIONS,
            reason=reason,
            missing=missing,
        ))
    retry = {
        "action": "resume_task",
        "from": "last_checkpoint",
        "taskId": task_id,
        "note": "the original task id and a live checkpoint are required" if not task_id else "",
    }
    return AcquisitionProposal(query=query, steps=steps, resolved_by=plan.resolved_by, retry=retry)


def execute_step(
    proposal: AcquisitionProposal,
    index: int,
    *,
    handlers: Optional[dict[str, Callable[[AcquisitionStep], Any]]] = None,
    approved: bool = False,
) -> dict[str, Any]:
    """Run one step through its surface. Never self-grants a mutation."""
    if index < 0 or index >= len(proposal.steps):
        return {"status": "invalid_step", "reason": "no such acquisition step"}
    step = proposal.steps[index]
    if step.requires_approval and not approved:
        return {
            "status": "approval_required",
            "step": step.to_dict(),
            "reason": "this step is a mutation and needs an operator decision",
        }
    if step.action in _READ_ONLY_ACTIONS:
        return {"status": "ready", "step": step.to_dict()}
    handler = (handlers or {}).get(step.action)
    if handler is None:
        return {
            "status": "requires_caller",
            "step": step.to_dict(),
            "reason": "no handler is bound to this surface; use the named gate",
        }
    try:
        result = handler(step)
    except Exception as exc:  # noqa: BLE001 - a handler failure is an honest outcome
        return {"status": "failed", "step": step.to_dict(), "reason": str(exc)}
    return {"status": "executed", "step": step.to_dict(), "result": result}


def validate_step(
    result: dict[str, Any],
    *,
    verifier: Optional[Callable[[dict[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """A capability is verified only by a real contract test; otherwise unverified."""
    if verifier is None:
        return {
            "status": "unverified",
            "reason": "no capability contract test was supplied; do not claim availability",
        }
    try:
        ok = bool(verifier(result))
    except Exception as exc:  # noqa: BLE001 - a failing verifier is a failure
        return {"status": "failed", "reason": str(exc)}
    return {"status": "verified" if ok else "failed", "reason": "" if ok else "the contract test failed"}


def retry_task(
    proposal: AcquisitionProposal,
    *,
    resume: Optional[Callable[[], Any]] = None,
) -> dict[str, Any]:
    """Resume the original task from its checkpoint, through a caller callback."""
    if resume is None:
        return {
            "status": "requires_caller",
            "retry": dict(proposal.retry),
            "reason": "the original task has not been resumed; a checkpoint and task callback are required",
        }
    try:
        value = resume()
    except Exception as exc:  # noqa: BLE001 - a failed resume is reported honestly
        return {"status": "failed", "reason": str(exc)}
    return {"status": "resumed", "value": value}


def default_strategy_handlers(
    query: str,
    index: Optional[CapabilityIndex],
) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Handlers for the capability strategies: propose a route, then STOP.

    A handler returns `{"stop": True, ...}`; the executor records the operation and
    returns the acquisition to the caller instead of retrying the same failed call
    unchanged. This is the "different route or honest blocker" rule.
    """
    if index is None or not (query or "").strip():
        return {}

    def _proposal() -> dict[str, Any]:
        return propose(query, index).to_dict()

    def _substitute(_decision: dict[str, Any]) -> dict[str, Any]:
        matches = index.search(query, available_only=True, limit=3)
        if matches:
            return {
                "stop": True,
                "substitutes": [match.to_dict() for match in matches],
                "acquisition": _proposal(),
            }
        return {"stop": True, "acquisition": _proposal()}

    def _alternative(_decision: dict[str, Any]) -> dict[str, Any]:
        return {"stop": True, "acquisition": _proposal()}

    def _dependency(_decision: dict[str, Any]) -> dict[str, Any]:
        return {"stop": True, "acquisition": _proposal(), "requiresApproval": True}

    return {
        "substitute_tool": _substitute,
        "alternative_implementation": _alternative,
        "fix_dependency": _dependency,
    }


__all__ = [
    "AcquisitionProposal",
    "AcquisitionStep",
    "SURFACES",
    "default_strategy_handlers",
    "execute_step",
    "propose",
    "retry_task",
    "validate_step",
]
