"""Draft generation — turn an approved learning candidate into a skill draft.

A draft is ALWAYS inert: `status: draft`, `evaluationStatus: not_evaluated`,
`origin: learning`. It cannot be executed until it passes evaluation and an
authorized operator promotes it. This module never enables anything.

Constraints:
  * Reuse the existing skill format (a `SkillManifest`).
  * Never invent tool names or APIs — only tools already registered.
  * Never invent financial claims; the procedure is the observed lesson, with
    its limitations preserved verbatim.
  * Mark the draft unvalidated.
"""

from __future__ import annotations

from typing import Any

from .manifest import SkillManifest
from .store import SkillStore


def _slug(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:60] or "learned-skill"


def _candidate_type_to_category(candidate_type: str) -> str:
    return {
        "failure_recovery": "quality",
        "validation_improvement": "quality",
        "source_selection_improvement": "research",
        "successful_procedure": "research",
        "workflow_pattern": "system",
        "user_correction": "quality",
        "terminology_or_preference": "quality",
    }.get(candidate_type, "quality")


def propose_draft(
    candidate_id: str,
    store: SkillStore,
    *,
    available_tools: list[str],
) -> dict[str, Any]:
    """Generate an unvalidated draft manifest from a candidate.

    Returns `{ok, draft, issues}`. `issues` are non-fatal notes (e.g. a lesson
    with no tool evidence) — they are preserved on the draft as limitations.
    """
    candidate = store.get_candidate(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate not found"}
    if candidate["status"] in ("rejected", "promoted"):
        return {"ok": False, "error": f"candidate is {candidate['status']} and cannot produce a draft"}

    issue_notes: list[str] = []
    tool_evidence = [
        ref for ref in (candidate.get("evidenceReferences") or [])
        if isinstance(ref, dict) and ref.get("kind") == "tool" and ref.get("name")
    ]
    required_tools: list[str] = []
    for ref in tool_evidence:
        name = ref["name"]
        if name in available_tools and name not in required_tools:
            required_tools.append(name)
        elif name not in available_tools:
            issue_notes.append(f"evidence referenced unavailable tool {name!r}; dropped from draft")

    if not required_tools:
        issue_notes.append("no registered tool evidence; the draft declares no required tools")

    category = _candidate_type_to_category(candidate["candidateType"])
    skill_id = f"learned.{_slug(candidate['title'])}"
    description = (candidate.get("proposedLesson") or candidate.get("problem") or candidate["title"])[:2000]

    # Permissions default to the read-only analysis set — a learned draft can
    # never request more than the safe set; promotion would require a new
    # manifest edit for anything stronger.
    permissions = ["data.read", "analysis.execute"]

    limitations = candidate.get("knownLimitations")
    limitations_text = limitations or "Unvalidated draft generated from a single execution."

    manifest_payload: dict[str, Any] = {
        "id": skill_id,
        "name": candidate["title"][:200],
        "version": "0.1.0",
        "description": description,
        "category": category,
        "tags": ["learned", candidate["candidateType"]],
        "status": "draft",
        "instructions": None,  # a generated draft is manifest-only until reviewed
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "The objective this procedure addresses."}
            },
            "required": ["objective"],
        },
        "outputSchema": None,
        "requiredTools": required_tools,
        "requiredSkills": [],
        "permissions": permissions,
        "riskLevel": "medium",
        "author": "eclipse-learning",
        "origin": "learning",
        "sourceRunId": candidate.get("sourceRunId"),
        "evaluationStatus": "not_evaluated",
        "compatibleRuntime": ">=0.1.0",
    }

    try:
        manifest = SkillManifest(**manifest_payload)
    except Exception as exc:  # noqa: BLE001 - a bad draft is a structured failure
        return {"ok": False, "error": f"generated manifest is invalid: {exc}", "issues": issue_notes}

    draft = manifest.model_dump()
    draft["procedureNotes"] = candidate.get("proposedProcedure")
    draft["sourceRunId"] = candidate.get("sourceRunId")
    draft["knownLimitations"] = limitations_text
    draft["generationIssues"] = issue_notes

    # Persist the draft onto the candidate and store as an inert version.
    store.update_candidate(
        candidate_id,
        status="drafted",
        resultingSkillId=skill_id,
        resultingSkillVersion="0.1.0",
        draftManifest=draft,
    )
    store.upsert_skill(
        skill_id=skill_id,
        name=manifest.name,
        description=manifest.description,
        category=manifest.category,
        latest_version="0.1.0",
        status="draft",
        tags=manifest.tags,
    )
    try:
        store.save_version(manifest.model_dump(), manifest.content_hash())
    except ValueError:
        pass  # version already stored
    store.append_event("skill.draft_generated", skill_id=skill_id, version="0.1.0",
                       data={"candidateId": candidate_id, "issues": issue_notes})

    return {"ok": True, "draft": draft, "issues": issue_notes}


__all__ = ["propose_draft"]
