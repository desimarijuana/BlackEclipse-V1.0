"""Skill curator — consolidation without silent self-modification (W5.2).

The library only grows: every learned or installed skill is permanent. This
module finds duplicates, near-duplicates, stale/evaluation debt and tag drift,
and turns a merge into an **inert draft** that an operator promotes through the
existing lifecycle. It never deletes, never enables, never widens permissions,
and never edits the active version of a skill.

Modes (``HARNESS_SKILL_CURATOR``):

* ``off``      — no scan.
* ``dry_run``  — scan and persist a report/proposals; change no skill.
* ``propose``  — additionally create an inert merged draft for each proposal.
* ``apply``    — ``propose`` plus deterministic, reversible housekeeping only.

Hard rules enforced in code:

* a pinned version, a ``compliance``/``security`` tag, an external origin, or a
  quarantined skill is never proposed;
* merged permissions are the INTERSECTION of the members (never widened);
* support files are listed and carried forward, never re-synthesized;
* every run and proposal is persisted, with a before/after diff.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .manifest import SkillManifest

CURATOR_MODES = ("off", "dry_run", "propose", "apply")
PROPOSAL_KINDS = (
    "duplicate", "near_duplicate", "umbrella_merge", "stale",
    "eval_debt", "tag_drift",
)
PROTECTED_TAGS = frozenset({"compliance", "security", "pinned", "external"})
PROTECTED_ORIGINS = frozenset({"external", "installed"})
_IGNORED_SUPPORT_NAMES = frozenset({
    "skill.json", "SKILL.md", "__pycache__", ".git",
})


@dataclass(frozen=True)
class CuratorPolicy:
    mode: str = "dry_run"
    interval_hours: int = 24
    jaccard_threshold: float = 0.7
    max_skills: int = 200

    @classmethod
    def from_flags(cls) -> "CuratorPolicy":
        from ..config.flags import get_flag  # noqa: PLC0415

        mode = get_flag("HARNESS_SKILL_CURATOR")
        return cls(mode=mode if mode in CURATOR_MODES else "dry_run")


@dataclass
class CuratorProposalDraft:
    kind: str
    skillIds: list[str]
    keeperId: str
    reason: str
    diff: dict[str, Any] = field(default_factory=dict)
    baseVersion: Optional[str] = None


def _normalize(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _normalize(text)) if len(token) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _signature(summary: dict[str, Any]) -> str:
    raw = "|".join([
        _normalize(summary.get("name")),
        _normalize(summary.get("description")),
        ",".join(sorted(_normalize(tag) for tag in summary.get("tags") or [])),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _is_protected(summary: dict[str, Any], store: Any) -> bool:
    tags = {_normalize(tag) for tag in summary.get("tags") or []}
    if tags & PROTECTED_TAGS:
        return True
    if _normalize(summary.get("origin")) in PROTECTED_ORIGINS:
        return True
    try:
        versions = store.list_versions(str(summary.get("id"))) or []
    except Exception:  # noqa: BLE001 - a lookup failure must not propose a change
        return True
    return any(bool(version.get("pinned")) for version in versions)


def _version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(version or ""))
    return tuple(int(part) for part in parts[:3]) or (0,)


def _next_version(version: str) -> str:
    major, minor, patch = (_version_key(version) + (0, 0, 0))[:3]
    return f"{major}.{minor + 1}.0"


def _support_files(registry: Any, skill_id: str) -> list[str]:
    """List support files under a skill folder (never their contents)."""
    import os  # noqa: PLC0415

    loaded = registry.get(skill_id)
    path = getattr(loaded, "instructions_path", None) if loaded else None
    if not path:
        return []
    folder = os.path.dirname(path)
    found: list[str] = []
    try:
        for current, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in _IGNORED_SUPPORT_NAMES]
            for name in sorted(files):
                if name in _IGNORED_SUPPORT_NAMES:
                    continue
                relative = os.path.relpath(os.path.join(current, name), folder)
                found.append(relative.replace("\\", "/"))
    except OSError:
        return []
    return sorted(found)


def _usage(store: Any, skill_id: str) -> int:
    try:
        executions = store.list_executions(skill_id, limit=200)
    except Exception:  # noqa: BLE001
        return 0
    return sum(
        1 for execution in executions
        if str(execution.get("status") or "") in ("completed", "ok", "passed", "succeeded", "success")
    )


def _choose_keeper(summaries: list[dict[str, Any]], store: Any) -> dict[str, Any]:
    """Highest real usage, then newest update, then lowest id (deterministic)."""
    def key(summary: dict[str, Any]) -> tuple[int, str, str]:
        return (
            -_usage(store, str(summary.get("id"))),
            str(summary.get("updatedAt") or ""),
            str(summary.get("id")),
        )
    return sorted(summaries, key=key, reverse=True)[0]


def _merge_draft(
    registry: Any, store: Any, proposal: CuratorProposalDraft,
) -> Optional[dict[str, Any]]:
    keeper_id = proposal.keeperId
    keeper = registry.manifest(keeper_id)
    if keeper is None:
        return None
    members: list[SkillManifest] = []
    for skill_id in proposal.skillIds:
        manifest = registry.manifest(skill_id)
        if manifest is not None:
            members.append(manifest)
    if not members:
        return None

    permissions = set(members[0].permissions)
    for member in members[1:]:
        permissions &= set(member.permissions)
    tools = sorted({tool for member in members for tool in member.requiredTools})
    tags = sorted({tag for member in members for tag in member.tags} | {"curated"})
    category = keeper.category

    sections: list[str] = [
        f"# {keeper.name} (curated)",
        "",
        "This skill merges the procedures below. Every step is preserved; the "
        "curator never invents a procedure, a tool, or a permission.",
        "",
    ]
    support: dict[str, list[str]] = {}
    seen_lines: set[str] = set()
    for member in members:
        loaded = registry.get(member.id)
        try:
            text = loaded.load_instructions() if loaded else ""
        except OSError:
            text = ""
        files = _support_files(registry, member.id)
        if files:
            support[member.id] = files
        # Deduplicate identical body lines across members. This is a
        # deterministic clean-up, not synthesis: every retained line exists
        # verbatim in a source skill.
        kept: list[str] = []
        for line in (text.strip() or "(no instruction body was stored for this version)").splitlines():
            normalized = line.strip().lower()
            if normalized and not line.lstrip().startswith("#"):
                if normalized in seen_lines:
                    continue
                seen_lines.add(normalized)
            kept.append(line)
        sections.extend([f"## From {member.id}", "", "\n".join(kept).strip(), ""])
    if support:
        sections.extend(["## Supporting files", ""])
        for skill_id, files in sorted(support.items()):
            sections.append(f"- {skill_id}: " + ", ".join(files))
        sections.append("")

    version = _next_version(keeper.version)
    payload = keeper.model_dump()
    payload.update({
        "id": keeper_id,
        "version": version,
        "name": keeper.name,
        "description": (
            f"Curated merge of {', '.join(sorted(member.id for member in members))}. "
            f"{keeper.description}"
        )[:2000],
        "category": category,
        "tags": tags,
        "status": "draft",
        "origin": "author",
        "evaluationStatus": "not_evaluated",
        "permissions": sorted(permissions),
        "requiredTools": tools,
        "instructions": None,
    })
    # A merge is a new version of the keeper; the source run is not applicable.
    payload.pop("sourceRunId", None)
    try:
        manifest = SkillManifest(**payload)
    except Exception:  # noqa: BLE001 - an invalid merge is refused, never forced
        return None

    instructions = "\n".join(sections)
    try:
        store.save_version(
            manifest.model_dump(), manifest.content_hash(),
            instructions=instructions, base_version=keeper.version,
            patch_summary=f"curator merge of {', '.join(sorted(member.id for member in members))}",
        )
    except ValueError:
        return None
    store.append_event(
        "skill.curator_draft_created", skill_id=keeper_id, version=version,
        data={"proposalKind": proposal.kind, "members": sorted(member.id for member in members)},
    )
    return {
        "skillId": keeper_id,
        "version": version,
        "manifest": manifest.model_dump(),
        "instructions": instructions,
        "supportFiles": support,
        "permissions": sorted(permissions),
        "requiredTools": tools,
    }


def _diff_for(keeper: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "keeper": {
            "id": keeper.get("id"), "version": keeper.get("latestVersion"),
            "name": keeper.get("name"), "permissions": keeper.get("permissions") or [],
        },
        "members": [
            {
                "id": member.get("id"), "version": member.get("latestVersion"),
                "name": member.get("name"),
            }
            for member in members if member.get("id") != keeper.get("id")
        ],
        "action": "create_inert_merged_draft",
    }


def scan(registry: Any, *, policy: Optional[CuratorPolicy] = None) -> list[CuratorProposalDraft]:
    """Deterministic scan. Returns proposals; writes nothing."""
    policy = policy or CuratorPolicy.from_flags()
    summaries = registry.list_summaries()
    eligible = [
        summary for summary in summaries[: policy.max_skills]
        if summary.get("status") not in ("archived", "rejected", "deprecated")
        and not _is_protected(summary, registry.store)
    ]
    proposals: list[CuratorProposalDraft] = []

    # Exact signature duplicates.
    by_signature: dict[str, list[dict[str, Any]]] = {}
    for summary in eligible:
        by_signature.setdefault(_signature(summary), []).append(summary)
    grouped_ids: set[str] = set()
    for group in by_signature.values():
        if len(group) < 2:
            continue
        keeper = _choose_keeper(group, registry.store)
        members = sorted(group, key=lambda item: str(item.get("id")))
        grouped_ids.update(str(item.get("id")) for item in members)
        proposals.append(CuratorProposalDraft(
            kind="duplicate", skillIds=[str(item.get("id")) for item in members],
            keeperId=str(keeper.get("id")),
            reason="identical name/description/tags signature",
            diff=_diff_for(keeper, members),
            baseVersion=str(keeper.get("latestVersion") or ""),
        ))

    # Near duplicates by description/tag Jaccard.
    remaining = [s for s in eligible if str(s.get("id")) not in grouped_ids]
    token_sets = {str(s.get("id")): _tokens(f"{s.get('name')} {s.get('description')} {' '.join(s.get('tags') or [])}") for s in remaining}
    for left, right in itertools.combinations(remaining, 2):
        left_id, right_id = str(left.get("id")), str(right.get("id"))
        if left.get("category") != right.get("category"):
            continue
        if _jaccard(token_sets[left_id], token_sets[right_id]) < policy.jaccard_threshold:
            continue
        group = [left, right]
        keeper = _choose_keeper(group, registry.store)
        proposals.append(CuratorProposalDraft(
            kind="near_duplicate", skillIds=[left_id, right_id],
            keeperId=str(keeper.get("id")),
            reason=(
                "overlapping name/description/tags "
                f"(jaccard >= {policy.jaccard_threshold})"
            ),
            diff=_diff_for(keeper, group),
            baseVersion=str(keeper.get("latestVersion") or ""),
        ))

    # Evaluation debt: an enabled learned skill with no execution evidence.
    for summary in eligible:
        skill_id = str(summary.get("id"))
        if not skill_id.startswith("learned."):
            continue
        if summary.get("status") not in ("enabled", "active", "validated"):
            continue
        try:
            evaluations = registry.store.list_evaluations(skill_id, limit=5)
        except Exception:  # noqa: BLE001
            evaluations = []
        if not any(evaluation.get("executionRunIds") for evaluation in evaluations):
            proposals.append(CuratorProposalDraft(
                kind="eval_debt", skillIds=[skill_id], keeperId=skill_id,
                reason="enabled learned skill has no behavioural execution evidence",
                diff={"action": "evaluate_execution_before_next_promotion"},
                baseVersion=str(summary.get("latestVersion") or ""),
            ))

    # Tag drift: the same tag on many unrelated skills is not a useful index.
    tag_counts: dict[str, list[str]] = {}
    for summary in eligible:
        for tag in summary.get("tags") or []:
            tag_counts.setdefault(_normalize(tag), []).append(str(summary.get("id")))
    for tag, ids in sorted(tag_counts.items()):
        if len(ids) >= 8 and tag not in ("learned", "curated"):
            proposals.append(CuratorProposalDraft(
                kind="tag_drift", skillIds=sorted(ids)[:20], keeperId=sorted(ids)[0],
                reason=f"tag {tag!r} is applied to {len(ids)} skills and no longer discriminates",
                diff={"action": "review_tag", "tag": tag, "count": len(ids)},
            ))
    return proposals


def run_curator(
    store: Any,
    registry: Any,
    *,
    mode: Optional[str] = None,
    policy: Optional[CuratorPolicy] = None,
    maintenance_policy: Optional[dict[str, Any]] = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Run one curator pass and persist the report/proposals."""
    policy = policy or CuratorPolicy.from_flags()
    mode = mode or policy.mode
    if mode not in CURATOR_MODES:
        mode = "dry_run"
    if mode == "off":
        return {"ok": True, "mode": "off", "skipped": True, "proposals": 0}

    run_id = store.save_curator_run(mode=mode)
    try:
        proposals = scan(registry, policy=policy)
        created: list[dict[str, Any]] = []
        for proposal in proposals:
            draft = None
            if mode in ("propose", "apply") and proposal.kind in (
                "duplicate", "near_duplicate", "umbrella_merge",
            ):
                draft = _merge_draft(registry, store, proposal)
            status = "proposed" if draft else "reported"
            proposal_id = store.save_curator_proposal(
                run_id=run_id, kind=proposal.kind, skill_ids=proposal.skillIds,
                base_version=proposal.baseVersion,
                proposed_draft_id=f"{draft['skillId']}@{draft['version']}" if draft else None,
                diff=proposal.diff, reason=proposal.reason, status=status,
            )
            created.append({
                "id": proposal_id, "kind": proposal.kind,
                "skillIds": proposal.skillIds, "status": status,
                "proposedDraftId": f"{draft['skillId']}@{draft['version']}" if draft else None,
            })
        applied = 0
        maintenance: dict[str, Any] = {}
        if mode == "apply":
            # Archive suggestions are handed to the ONE maintenance pass, which
            # is report-only unless its own policy enables auto-archive. The
            # curator never bypasses pinned exemptions or deletes anything.
            try:
                from .maintenance import run_skill_maintenance  # noqa: PLC0415

                maintenance = run_skill_maintenance(
                    store, registry, maintenance_policy or {},
                )
                applied = len(maintenance.get("archived") or [])
            except Exception as exc:  # noqa: BLE001 - hand-off must not fail the run
                maintenance = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        store.finish_curator_run(
            run_id, status="completed",
            skills_scanned=len(registry.list_summaries()),
            groups_found=len(proposals),
            proposals_created=len(created),
            applied=applied,
            details={
                "mode": mode,
                "kinds": sorted({p.kind for p in proposals}),
                "maintenance": maintenance,
            },
        )
        store.append_event(
            "skill.curator_run",
            data={"runId": run_id, "mode": mode, "proposals": len(created)},
        )
        try:
            from ..observability.bridge import publish  # noqa: PLC0415

            publish("skill.curator_run", {
                "ok": True, "status": "completed", "mode": mode,
                "proposals": len(created), "applied": 0,
            }, run_id=run_id)
        except Exception:  # noqa: BLE001 - telemetry only
            pass
        return {
            "ok": True, "runId": run_id, "mode": mode,
            "proposals": len(created), "created": created,
            "applied": applied, "maintenance": maintenance,
        }
    except Exception as exc:  # noqa: BLE001 - a curator pass never blocks boot
        store.finish_curator_run(run_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return {"ok": False, "runId": run_id, "mode": mode, "error": str(exc)}


def approve_proposal(
    store: Any, registry: Any, proposal_id: str, *,
    actor: str = "operator", notes: str = "",
) -> dict[str, Any]:
    """Approve a proposal. Creates an inert merged draft if none exists."""
    proposal = store.get_curator_proposal(proposal_id)
    if proposal is None:
        return {"ok": False, "error": "proposal not found"}
    if proposal["status"] not in ("reported", "proposed"):
        return {"ok": False, "error": f"proposal is already {proposal['status']}"}
    draft_id = proposal.get("proposedDraftId")
    if not draft_id:
        diff = proposal.get("diff") or {}
        keeper_id = str(
            (diff.get("keeper") or {}).get("id")
            or (proposal["skillIds"] or ["unknown"])[0]
        )
        cur = CuratorProposalDraft(
            kind=str(proposal["kind"]), skillIds=list(proposal["skillIds"]),
            keeperId=keeper_id,
            reason=str(proposal.get("reason") or ""),
            diff=diff,
            baseVersion=proposal.get("baseVersion"),
        )
        # Only a merge proposal can produce a merge draft. A stale/eval-debt/
        # tag-drift proposal is a recommendation, not a version change.
        if cur.kind in ("duplicate", "near_duplicate", "umbrella_merge"):
            payload = preview_merge(registry, store, cur)
            if payload is not None:
                draft_id = f"{payload['skillId']}@{payload['version']}"
    store.decide_curator_proposal(
        proposal_id, status="approved", actor=actor, notes=notes,
    )
    store.append_event(
        "skill.curator_proposal_approved",
        data={"proposalId": proposal_id, "draft": draft_id, "actor": actor},
    )
    return {"ok": True, "proposalId": proposal_id, "status": "approved", "draft": draft_id}


def preview_merge(registry: Any, store: Any, proposal: CuratorProposalDraft) -> Optional[dict[str, Any]]:
    """Create the inert merged draft without approving it (propose mode)."""
    return _merge_draft(registry, store, proposal)


def reject_proposal(
    store: Any, proposal_id: str, *, actor: str = "operator", notes: str = "",
) -> dict[str, Any]:
    proposal = store.get_curator_proposal(proposal_id)
    if proposal is None:
        return {"ok": False, "error": "proposal not found"}
    if proposal["status"] not in ("reported", "proposed"):
        return {"ok": False, "error": f"proposal is already {proposal['status']}"}
    store.decide_curator_proposal(
        proposal_id, status="rejected", actor=actor, notes=notes,
    )
    store.append_event(
        "skill.curator_proposal_rejected",
        data={"proposalId": proposal_id, "actor": actor},
    )
    return {"ok": True, "proposalId": proposal_id, "status": "rejected"}


_CURATOR_LOCK = __import__("threading").Lock()


def curator_due(store: Any, policy: CuratorPolicy) -> bool:
    """Whether the cadence allows a pass. A missing/old run is always due."""
    import datetime  # noqa: PLC0415

    runs = store.list_curator_runs(limit=1)
    if not runs:
        return True
    stamp = runs[0].get("startedAt")
    try:
        parsed = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    age_hours = (
        datetime.datetime.now(datetime.timezone.utc) - parsed
    ).total_seconds() / 3600.0
    return age_hours >= max(0, int(policy.interval_hours))


def maybe_run_curator(
    store: Any, registry: Any, *, policy: Optional[CuratorPolicy] = None,
    maintenance_policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Cadence-guarded pass (no daemon). Concurrent callers cannot interleave."""
    policy = policy or CuratorPolicy.from_flags()
    if policy.mode == "off":
        return {"ok": True, "mode": "off", "skipped": True, "proposals": 0}
    if not curator_due(store, policy):
        return {"ok": True, "skipped": True, "reason": "not_due", "proposals": 0}
    if not _CURATOR_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "busy", "proposals": 0}
    try:
        if not curator_due(store, policy):
            return {"ok": True, "skipped": True, "reason": "not_due", "proposals": 0}
        return run_curator(
            store, registry, policy=policy,
            maintenance_policy=maintenance_policy,
        )
    finally:
        _CURATOR_LOCK.release()


def curator_report(store: Any, *, limit: int = 20) -> dict[str, Any]:
    return {
        "runs": store.list_curator_runs(limit=limit),
        "proposals": store.list_curator_proposals(limit=limit),
    }


__all__ = [
    "CURATOR_MODES",
    "CuratorPolicy",
    "CuratorProposalDraft",
    "PROPOSAL_KINDS",
    "approve_proposal",
    "curator_due",
    "curator_report",
    "maybe_run_curator",
    "preview_merge",
    "reject_proposal",
    "run_curator",
    "scan",
]
