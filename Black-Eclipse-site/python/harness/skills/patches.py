"""Structured, versioned, reversible skill patches (Milestone 2).

A background review (or an operator) proposes a **structured patch** against a
known base version of a skill. The patch is validated, evaluated, and only then
may it be activated — via a canary for safe non-mutating skills, or directly for
low-risk changes that pass evaluation. Every activation is versioned and every
regression is automatically rolled back.

Hard rules enforced here (never by the model):

  * a patch NEVER mutates the active version; it creates a NEW `SkillVersion`;
  * the base version must still be the skill's latest, or the patch is rejected
    (stale/concurrent edits cannot silently overwrite);
  * only the allowed operation set (`replace`/`add`/`remove`) and the allowed
    JSON-pointer paths are accepted;
  * the resulting manifest is re-validated through the SAME `SkillManifest`
    (which enforces tool names, permissions and schema shapes);
  * a patch may not widen permissions, add forbidden permissions, add a tool the
    registry does not know, or change the skill id;
  * activation requires a passing evaluation; canary is refused for any
    security/permission/mutating/policy-shaping change;
  * rollback is atomic (one transaction) and preserves the old version.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# Operations a patch may use. `replace` overwrites an existing path; `add` sets a
# new value (must not already exist); `remove` deletes a path.
ALLOWED_OPS = frozenset({"replace", "add", "remove"})

# Only these top-level manifest fields may be patched. Security, identity and
# permission fields are deliberately NOT patchable by an automated review.
PATCHABLE_FIELDS = frozenset(
    {
        "description",
        "tags",
        "name",
        "instructions",
        "outputSchema",
        "limits",
    }
)

# A patch may never touch these, even nested (defence in depth).
FORBIDDEN_FIELDS = frozenset(
    {
        "id",
        "version",
        "permissions",
        "requiredTools",
        "requiredSkills",
        "riskLevel",
        "status",
        "origin",
        "author",
        "sourceRunId",
    }
)

MAX_OPERATIONS = 20
MAX_VALUE_CHARS = 4000


class PatchError(ValueError):
    """A patch was rejected (unknown op/path, forbidden field, or stale base)."""


@dataclass
class PatchResult:
    ok: bool
    reason: str = ""
    manifest: Optional[dict[str, Any]] = None
    patch: Optional[dict[str, Any]] = None


@dataclass
class Patch:
    """A parsed, validated structured skill patch."""

    skill: str
    base_version: str
    operations: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    evidence_runs: list[str] = field(default_factory=list)
    regression_cases: list[str] = field(default_factory=list)
    author: str = "background_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "baseVersion": self.base_version,
            "operations": self.operations,
            "reason": self.reason,
            "evidenceRuns": self.evidence_runs,
            "regressionCases": self.regression_cases,
            "author": self.author,
        }


def parse_patch(payload: dict[str, Any]) -> Patch:
    """Parse + structurally validate an untrusted patch payload."""
    if not isinstance(payload, dict):
        raise PatchError("patch must be an object")
    skill = str(payload.get("skill") or "").strip()
    base = str(payload.get("baseVersion") or payload.get("base_version") or "").strip()
    if not skill:
        raise PatchError("patch.skill is required")
    if not base:
        raise PatchError("patch.baseVersion is required")
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise PatchError("patch.operations must be a non-empty array")
    if len(operations) > MAX_OPERATIONS:
        raise PatchError(f"patch has more than {MAX_OPERATIONS} operations")
    for op in operations:
        _validate_operation(op)
    author = str(payload.get("author") or "background_review")
    if author not in ("user", "background_review", "operator"):
        raise PatchError(f"unknown patch author {author!r}")
    return Patch(
        skill=skill,
        base_version=base,
        operations=operations,
        reason=str(payload.get("reason") or "")[:1000],
        evidence_runs=[str(r) for r in (payload.get("evidenceRuns") or [])][:20],
        regression_cases=[str(c) for c in (payload.get("regressionCases") or [])][:20],
        author=author,
    )


def _validate_operation(op: Any) -> None:
    if not isinstance(op, dict):
        raise PatchError("each operation must be an object")
    kind = str(op.get("op") or "")
    if kind not in ALLOWED_OPS:
        raise PatchError(f"unsupported op {kind!r} (allowed: {sorted(ALLOWED_OPS)})")
    path = str(op.get("path") or "")
    if not path.startswith("/"):
        raise PatchError(f"operation path must be a JSON pointer, got {path!r}")
    tokens = [t for t in path.strip("/").split("/") if t != ""]
    if not tokens:
        raise PatchError("operation path must not be the document root")
    if tokens[0] in FORBIDDEN_FIELDS:
        raise PatchError(f"field {tokens[0]!r} is not patchable")
    if tokens[0] not in PATCHABLE_FIELDS:
        raise PatchError(f"field {tokens[0]!r} is not in the patchable set")
    if kind in ("replace", "add"):
        value = op.get("value")
        encoded = json.dumps(value, default=str)
        if len(encoded) > MAX_VALUE_CHARS:
            raise PatchError("operation value is too large")


def _apply_pointer(document: dict[str, Any], path: str, kind: str, value: Any = None) -> None:
    tokens = [t for t in path.strip("/").split("/") if t != ""]
    target: Any = document
    for token in tokens[:-1]:
        if isinstance(target, list):
            target = target[int(token)]
        else:
            if token not in target or not isinstance(target[token], (dict, list)):
                target[token] = {}
            target = target[token]
    last = tokens[-1]
    if isinstance(target, list):
        index = int(last)
        if kind == "remove":
            del target[index]
        elif kind == "add":
            target.insert(index, value)
        else:
            target[index] = value
        return
    if kind == "add":
        if last in target:
            raise PatchError(f"add target {path!r} already exists")
        target[last] = value
    elif kind == "remove":
        if last not in target:
            raise PatchError(f"remove target {path!r} does not exist")
        del target[last]
    else:  # replace
        if last not in target:
            raise PatchError(f"replace target {path!r} does not exist")
        target[last] = value


def apply_patch_to_manifest(manifest: dict[str, Any], patch: Patch) -> PatchResult:
    """Apply a validated patch to a manifest dict, re-validating the result.

    Does NOT touch persistence or the active version — pure transformation.
    """
    from .manifest import SkillManifest  # noqa: PLC0415

    working = copy.deepcopy(manifest)
    # Never allow a patch to alter immutable identity fields.
    if patch.skill and working.get("id") != patch.skill:
        raise PatchError(f"patch targets {patch.skill!r} but manifest is {working.get('id')!r}")
    before = {
        "permissions": list(working.get("permissions") or []),
        "requiredTools": list(working.get("requiredTools") or []),
        "riskLevel": working.get("riskLevel"),
    }
    try:
        for op in patch.operations:
            _apply_pointer(working, str(op["path"]), str(op["op"]), op.get("value"))
    except PatchError:
        raise
    except Exception as exc:  # noqa: BLE001 - any structural failure is a rejection
        raise PatchError(f"patch application failed: {exc}") from exc

    # Defence in depth: a patch can never widen the security surface.
    if list(working.get("permissions") or []) != before["permissions"]:
        raise PatchError("a patch may not change permissions")
    if list(working.get("requiredTools") or []) != before["requiredTools"]:
        raise PatchError("a patch may not change required tools")
    if working.get("riskLevel") != before["riskLevel"]:
        raise PatchError("a patch may not change the risk level")

    try:
        validated = SkillManifest(**working)
    except Exception as exc:  # noqa: BLE001 - pydantic validation error
        raise PatchError(f"patched manifest is invalid: {exc}") from exc
    return PatchResult(ok=True, manifest=validated.model_dump(), patch=patch.to_dict())


def version_conflict(store: Any, patch: Patch) -> Optional[str]:
    """Return a conflict reason when the patch base is stale, else None.

    A patch may only be applied when its `baseVersion` is the skill's CURRENT
    latest version. Otherwise a concurrent edit happened and the patch must be
    recomputed (never silently rebased).
    """
    skill = store.get_skill(patch.skill)
    if skill is None:
        return f"unknown skill {patch.skill!r}"
    latest = skill.get("latestVersion")
    if latest != patch.base_version:
        return (
            f"base version {patch.base_version!r} is stale; "
            f"skill is now at {latest!r} — recompute the patch"
        )
    if store.get_version(patch.skill, patch.base_version) is None:
        return f"base version {patch.base_version!r} does not exist"
    return None


# ── Never-canary classification ─────────────────────────────────────────────

# A version with any of these is NEVER canaried: a canary routes live traffic, so
# it must be limited to safe, non-mutating, non-policy skills.
NON_CANARY_PERMISSIONS = frozenset(
    {
        "trade.execute",
        "broker.modify",
        "production.modify",
        "code.write",
        "code.execute",
        "external.network",
        "portfolio.modify",
        "skill.enable",
        "skill.disable",
        "skill.create",
        "skill.review",
    }
)


def canary_eligible(manifest: dict[str, Any]) -> tuple[bool, str]:
    """Whether a version may be canaried. Returns `(eligible, reason)`."""
    status = manifest.get("status")
    if status not in ("validated", "approved", "testing"):
        return False, f"status {status!r} is not canary-eligible"
    perms = set(manifest.get("permissions") or [])
    blocked = perms & NON_CANARY_PERMISSIONS
    if blocked:
        return False, f"declares non-canary permission(s): {sorted(blocked)}"
    if str(manifest.get("riskLevel")) in ("high", "critical"):
        return False, "high/critical risk skills are never canaried"
    return True, "safe non-mutating skill"


__all__ = [
    "ALLOWED_OPS",
    "FORBIDDEN_FIELDS",
    "NON_CANARY_PERMISSIONS",
    "PATCHABLE_FIELDS",
    "Patch",
    "PatchError",
    "PatchResult",
    "apply_patch_to_manifest",
    "canary_eligible",
    "parse_patch",
    "version_conflict",
]
