"""Skill authoring — let users create and edit their own skills.

A user skill is stored in **eclipse-memory** (`UserSkill` tables) rather than on
disk: the runtime has no filesystem-write path by design, and DB storage keeps
user skills separate from the shipped library while surviving restarts. The
`UserSkill` row is loaded into the SAME `SkillRegistry` as built-in skills, so
execution, discovery and the agent tools work unchanged.

Safety, enforced in code:
  * The manifest is validated by the same pydantic `SkillManifest` the built-ins
    use — no second schema.
  * A user skill may only declare the **safe permission set**; a forbidden or
    operator-only permission is rejected at author time (and would be blocked at
    enable time regardless).
  * Instructions are bounded; they are data, never a security boundary.
  * Authoring requires an authorized operator (the same gate as every mutation).
  * Editing an enabled skill creates a NEW version — it never mutates the
    enabled version in place.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .manifest import SkillManifest
from .permissions import SAFE_PERMISSIONS

MAX_INSTRUCTIONS_CHARS = 20_000
MAX_DESCRIPTION_CHARS = 2000

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_RESERVED_PREFIXES = ("learned.",)


class SkillAuthoringError(ValueError):
    """A user skill could not be created/updated (never silently dropped)."""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:60] or "skill"


def suggest_skill_id(name: str, *, existing_ids: set[str]) -> str:
    """A `user.<slug>` id that does not collide with an installed skill."""
    base = f"user.{_slugify(name)}"
    if base not in existing_ids:
        return base
    for n in range(2, 100):
        candidate = f"{base}-{n}"
        if candidate not in existing_ids:
            return candidate
    raise SkillAuthoringError("could not derive a unique skill id")


def build_user_manifest(
    *,
    skill_id: str,
    name: str,
    description: str,
    instructions: str,
    category: str = "research",
    tags: Optional[list[str]] = None,
    required_tools: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
    risk_level: str = "low",
    version: str = "1.0.0",
    author: str = "user",
    status: str = "enabled",
) -> SkillManifest:
    """Validate and build a user-authored manifest.

    The returned manifest is a normal `SkillManifest`; `instructions` is inline
    text (a user skill has no SKILL.md file).
    """
    if not _ID_RE.match(skill_id):
        raise SkillAuthoringError(
            "skill id must be a lowercase slug (letters, digits, '.', '-', '_')"
        )
    if any(skill_id.startswith(prefix) for prefix in _RESERVED_PREFIXES):
        raise SkillAuthoringError("skill id prefix is reserved")

    # A user skill may only declare the SAFE, read-only set. Operator-only
    # permissions (skill.enable, skill.review, portfolio.modify) and forbidden
    # ones (trade.execute, …) are both refused — a user-authored skill can never
    # widen its own authority.
    requested = list(permissions or ["data.read", "analysis.execute"])
    outside = [p for p in requested if p not in SAFE_PERMISSIONS]
    if outside:
        raise SkillAuthoringError(
            f"permissions not allowed (safe set only): {', '.join(sorted(set(outside)))}"
        )

    text = (instructions or "").strip()
    if not text:
        raise SkillAuthoringError("instructions must not be empty")
    if len(text) > MAX_INSTRUCTIONS_CHARS:
        raise SkillAuthoringError(f"instructions exceed {MAX_INSTRUCTIONS_CHARS} characters")
    if len(description or "") > MAX_DESCRIPTION_CHARS:
        raise SkillAuthoringError(f"description exceeds {MAX_DESCRIPTION_CHARS} characters")

    try:
        manifest = SkillManifest(
            id=skill_id,
            name=name.strip() or skill_id,
            version=version,
            description=description.strip() or f"User skill {name}",
            category=category,  # validated by the literal
            tags=tags or [],
            status=status,  # validated by the literal
            instructions=None,  # no file — inline text supplied separately
            inputSchema={
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "The objective this skill addresses."}
                },
                "required": ["objective"],
            },
            outputSchema=None,
            requiredTools=list(required_tools or []),
            requiredSkills=[],
            permissions=requested,
            riskLevel=risk_level,  # validated by the literal
            author=author,
            origin="author",
        )
    except Exception as exc:  # noqa: BLE001 - surface a clear authoring error
        raise SkillAuthoringError(str(exc)) from exc
    return manifest


def scan_manifest_content(manifest: SkillManifest, instructions: str) -> dict[str, Any]:
    """Advisory content-injection scan of a user skill's description + prose.

    Returns a bounded `ScanResult.to_dict()`. It NEVER blocks authoring (the
    permission gate is authoritative); it exists so the UI can warn before the
    skill is enabled. A clean scan is not proof of safety.
    """
    try:
        from .content_scan import scan_content  # noqa: PLC0415

        blob = f"{manifest.name}\n{manifest.description}\n{instructions or ''}"
        return scan_content(blob, location="profile").to_dict()
    except Exception:  # noqa: BLE001 - scanning must never break authoring
        return {"ok": True, "findings": [], "shouldQuarantine": False, "categories": []}


def validate_against_tools(manifest: SkillManifest, available_tools: list[str]) -> None:
    """Every required tool must exist in the runtime registry."""
    missing = [t for t in manifest.requiredTools if t not in set(available_tools)]
    if missing:
        raise SkillAuthoringError(f"unknown tool(s): {', '.join(missing)}")


def next_version(current: str) -> str:
    """Bump the minor version for an edit (never mutate an enabled version)."""
    from .manifest import parse_version

    try:
        major, minor, _patch, _pre = parse_version(current)
    except ValueError:
        return "1.0.0"
    return f"{major}.{minor + 1}.0"


__all__ = [
    "MAX_INSTRUCTIONS_CHARS",
    "SkillAuthoringError",
    "build_user_manifest",
    "next_version",
    "scan_manifest_content",
    "suggest_skill_id",
    "validate_against_tools",
]
