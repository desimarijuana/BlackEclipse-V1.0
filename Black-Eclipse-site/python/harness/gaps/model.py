"""The durable capability-gap contract and its user-facing offer view."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CapabilityGap:
    gapId: str
    runId: str
    signature: str
    need: str
    kind: str  # taxonomy class (capability_missing / context_denied / ...)
    code: str
    tool: str = ""
    reason: str = ""
    taskId: str = ""
    state: str = "open"  # open | offered | accepted | declined | suppressed | resolved
    createdAt: str = ""
    updatedAt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gapId": self.gapId,
            "runId": self.runId,
            "signature": self.signature,
            "need": self.need,
            "kind": self.kind,
            "code": self.code,
            "tool": self.tool,
            "reason": self.reason,
            "taskId": self.taskId or None,
            "state": self.state,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }


@dataclass
class GapOffer:
    """One actionable route the user may accept.

    This is a VIEW over a stored gap, never an authorization. Accepting it starts
    the existing acquisition route; every effectful step still asks for its own
    single-use approval.
    """

    gapId: str
    need: str
    kind: str
    code: str
    title: str
    reason: str
    status: str  # "gap" | "handoff_required" (the capability card's vocab)
    surface: str
    nextTool: str
    steps: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    actionLabel: str = "Do it"
    actionPrompt: str = ""
    requiresApproval: bool = True

    def to_event(self) -> dict[str, Any]:
        """The bounded `capability.offer` event payload (card-compatible)."""
        return {
            "gapId": self.gapId,
            "need": self.need,
            "kind": self.kind,
            "code": self.code,
            "title": self.title,
            "reason": self.reason,
            "status": self.status,
            "surface": self.surface,
            "nextTool": self.nextTool,
            "steps": list(self.steps),
            "missing": list(self.missing),
            "actionLabel": self.actionLabel,
            "actionPrompt": self.actionPrompt,
            "requiresApproval": self.requiresApproval,
            "offer": True,
            "class": self.kind,
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.to_event()
        data["gapClass"] = data.pop("class")
        return data


def gap_offer_from_dict(raw: Any) -> Optional[GapOffer]:
    if not isinstance(raw, dict):
        return None
    gap_id = str(raw.get("gapId") or "")
    need = str(raw.get("need") or "")
    if not gap_id or not need:
        return None
    return GapOffer(
        gapId=gap_id,
        need=need,
        kind=str(raw.get("kind") or raw.get("class") or ""),
        code=str(raw.get("code") or ""),
        title=str(raw.get("title") or need),
        reason=str(raw.get("reason") or ""),
        status=str(raw.get("status") or "gap"),
        surface=str(raw.get("surface") or ""),
        nextTool=str(raw.get("nextTool") or ""),
        steps=[str(item) for item in (raw.get("steps") or [])],
        missing=[str(item) for item in (raw.get("missing") or [])],
        actionLabel=str(raw.get("actionLabel") or "Do it"),
        actionPrompt=str(raw.get("actionPrompt") or ""),
        requiresApproval=bool(raw.get("requiresApproval", True)),
    )


__all__ = ["CapabilityGap", "GapOffer", "gap_offer_from_dict"]
