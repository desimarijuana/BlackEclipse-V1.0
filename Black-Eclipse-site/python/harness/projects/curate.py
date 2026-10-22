"""The curated project view — what a project is, and what it is missing.

A project member list is a filing cabinet. A **curated** project is a summary:
what this project is about, which members matter most, and what it does not
have yet.

The curation is deterministic and explainable. It does not guess: it ranks by
a fixed priority per member kind, breaks ties by recency, and names the gaps it
sees. Every member that is promoted carries the reason it was promoted, so the
ranking can be argued with rather than merely trusted.

The gap list is the half that matters most. A project with a strategy and no
result is not finished, and it should say so rather than look busy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: How much a kind of member matters to a project's story. A result outranks an
#: intent, an intent outranks an input, and a run record outranks a note.
KIND_PRIORITY: dict[str, int] = {
    "experiment": 40,
    "strategy": 35,
    "dataset": 20,
    "artifact": 15,
    "note": 10,
    "chat": 5,
}

#: The kinds a project is expected to have before it is "a piece of work".
EXPECTED_KINDS: tuple[str, ...] = ("strategy", "experiment")


@dataclass
class CuratedMember:
    """One member, with the reason it was ranked where it was."""

    id: str
    kind: str
    ref: str
    label: str = ""
    score: int = 0
    reason: str = ""
    created_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "ref": self.ref,
            "label": self.label,
            "score": self.score,
            "reason": self.reason,
            "createdAt": self.created_at,
            "meta": dict(self.meta),
        }


@dataclass
class ProjectDigest:
    """What a project is, ranked, and what it lacks."""

    project_id: str
    name: str = ""
    headline: str = ""
    summary: str = ""
    members: list[CuratedMember] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    auto_run: Optional[dict[str, Any]] = None

    @property
    def member_count(self) -> int:
        return len(self.members)

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "name": self.name,
            "headline": self.headline,
            "summary": self.summary,
            "members": [m.to_dict() for m in self.members],
            "memberCount": self.member_count,
            "gaps": list(self.gaps),
            "counts": dict(self.counts),
            "autoRun": self.auto_run,
        }

    def to_markdown(self) -> str:
        lines = [f"## Project: {self.name} (`{self.project_id}`)"]
        if self.headline:
            lines.append(self.headline)
        if self.summary:
            lines.append(self.summary)
        if self.members:
            lines.append("Members (most important first):")
            for member in self.members:
                label = f" — {member.label}" if member.label else ""
                lines.append(f"- {member.kind}: `{member.ref}`{label} — {member.reason}")
        else:
            lines.append("Members: none yet.")
        if self.auto_run:
            state = "ON" if self.auto_run.get("enabled") else "off"
            lines.append(f"Auto-run: {state} - {self.auto_run.get('summary', '')}")
        if self.gaps:
            lines.append("Still missing:")
            for gap in self.gaps:
                lines.append(f"- {gap}")
        return "\n".join(lines)


def _headline(project: Any, counts: dict[str, int]) -> str:
    """One line: what this project is, from what it actually holds."""
    name = str(getattr(project, "name", "") or "").strip()
    symbols = list(getattr(project, "symbols", []) or [])
    where = f" on {', '.join(symbols)}" if symbols else ""
    bits = []
    for kind, singular, plural in (("strategy", "strategy", "strategies"),
                                  ("experiment", "result", "results"),
                                  ("dataset", "dataset", "datasets"),
                                  ("artifact", "artifact", "artifacts")):
        count = counts.get(kind, 0)
        if count:
            bits.append(f"{count} {singular if count == 1 else plural}")
    if not bits:
        return f"{name}{where} — nothing has been put in it yet."
    return f"{name}{where} — {', '.join(bits)}."


def _summary(project: Any, counts: dict[str, int]) -> str:
    description = str(getattr(project, "description", "") or "").strip()
    if description:
        return description
    return ""


def _gaps(counts: dict[str, int], total: int) -> list[str]:
    """What the project does not have yet — said plainly."""
    gaps: list[str] = []
    for kind in EXPECTED_KINDS:
        if not counts.get(kind):
            gaps.append({
                "strategy": "no strategy has been attached yet",
                "experiment": "no result has been attached yet — a strategy with no "
                              "tested outcome is an intention, not a finding",
            }[kind])
    if not gaps and total == 0:
        gaps.append("the project is empty")
    return gaps


def _member_label(member: Any) -> str:
    """A readable label for a member, preferring its own text."""
    label = str(getattr(member, "label", "") or "").strip()
    if label:
        return label
    meta = getattr(member, "meta", {}) or {}
    excerpt = str(meta.get("excerpt") or "").strip()
    if excerpt:
        first = excerpt.split("\n")[0]
        return first[:120] + ("…" if len(first) > 120 else "")
    return ""


def curate_project(
    project_store: Any,
    project_id: str,
    *,
    max_members: int = 20,
    auto_run_store: Any = None,
) -> Optional[ProjectDigest]:
    """Curate one project: what it is, what matters, what it lacks."""
    project = project_store.get(str(project_id))
    if project is None:
        return None
    members = project_store.members(project.id)

    counts: dict[str, int] = {}
    for member in members:
        counts[member.kind] = counts.get(member.kind, 0) + 1

    ranked: list[CuratedMember] = []
    for member in members:
        priority = KIND_PRIORITY.get(member.kind, 0)
        reason = f"a {member.kind}"
        if member.kind == "experiment":
            reason = "a tested result"
        elif member.kind == "strategy":
            reason = "a strategy to trade"
        elif member.kind == "dataset":
            reason = "the data it runs on"
        elif member.kind == "artifact":
            reason = "something it produced"
        elif member.kind == "note":
            reason = "a run record"
        ranked.append(CuratedMember(
            id=member.id, kind=member.kind, ref=member.ref,
            label=_member_label(member),
            score=priority, reason=reason,
            created_at=str(getattr(member, "created_at", "") or ""),
            meta=dict(getattr(member, "meta", {}) or {}),
        ))

    # Most important first; the newest breaks a tie (and the id breaks that).
    ranked.sort(key=lambda m: (-m.score, _negated(m.created_at), m.ref))

    return ProjectDigest(
        project_id=project.id,
        name=str(getattr(project, "name", "") or ""),
        headline=_headline(project, counts),
        summary=_summary(project, counts),
        members=ranked[:max_members],
        gaps=_gaps(counts, len(members)),
        counts=counts,
        auto_run=_auto_run_state(auto_run_store, project.id),
    )


def _auto_run_state(auto_run_store: Any, project_id: str) -> Optional[dict[str, Any]]:
    """What the auto-run policy says about this project, and what is left."""
    if auto_run_store is None:
        return None
    try:
        policy = auto_run_store.get_policy(project_id)
        budget = auto_run_store.budget_state(policy)
    except Exception:  # noqa: BLE001 - the policy is a nicety, never a blocker
        return None
    return {
        "enabled": policy.enabled,
        "summary": (f"{budget['usedRuns']}/{policy.max_runs_per_day} run(s) today, "
                    f"{budget['usedSeconds']:.0f}/{policy.max_seconds_per_day}s, "
                    f"at most every {policy.min_interval_minutes} min"),
        "budget": budget,
        "allowedTools": list(policy.allowed_tools),
    }


def _negated(stamp: str) -> str:
    """Sort key that puts the NEWEST first for an ascending sort."""
    return "".join(chr(0x10FFFF - ord(ch)) if ord(ch) < 0x10FFFF else ch
                   for ch in stamp)


__all__ = [
    "CuratedMember",
    "EXPECTED_KINDS",
    "KIND_PRIORITY",
    "ProjectDigest",
    "curate_project",
]
