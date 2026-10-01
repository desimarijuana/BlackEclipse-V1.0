"""Save-time guardrails for jobs (Phase 6 §6.7).

Every rule here is enforced in CODE at save time, so an invalid or over-reaching
job can never be persisted. The rules:

1. Permission binding — a skill-backed job resolves the pinned skill's manifest
   permissions and refuses when the job's declared needs exceed them, naming the
   exact missing permission. A job can never be the path by which a permission
   is acquired.
2. Autonomy — `workspace_root` + `autonomy` are only valid for a code job; a code
   job without a workspace is refused; `approve_external` requires an explicit
   operator flag and is never the default.
3. Delivery — an unknown adapter is refused here, not ignored at delivery time.
4. Watch path — must resolve inside a declared workspace root (`policy.resolve_within`).
5. Skill pinning — a job referencing a skill pins a concrete version; a skill
   that is later disabled or rolled back makes the job fail honestly at run time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..code import policy
from ..code.workspace import WorkspaceDenial, default_root
from .model import KNOWN_ADAPTERS, JobDefinition

# Named refusal codes (stable, structured).
PERMISSION_NOT_HELD = "PERMISSION_NOT_HELD"
WORKSPACE_REQUIRED = "WORKSPACE_REQUIRED"
EXTERNAL_NOT_ALLOWED = "EXTERNAL_NOT_ALLOWED"
UNKNOWN_ADAPTER = "UNKNOWN_ADAPTER"
WATCH_PATH_REFUSED = "WATCH_PATH_REFUSED"
SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
SKILL_VERSION_NOT_FOUND = "SKILL_VERSION_NOT_FOUND"
TARGET_INVALID = "TARGET_INVALID"


class JobValidationError(ValueError):
    """A refusal at save time carrying a code + an optional missing permission."""

    def __init__(self, code: str, message: str, *, missing: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing = missing


def _code_grants_for(autonomy: str) -> frozenset[str]:
    return policy.code_grants(autonomy)


def validate_job(
    job: JobDefinition,
    *,
    skill_registry: Any = None,
    allow_external: bool = False,
) -> JobDefinition:
    """Validate + normalize a job, or raise ``JobValidationError``.

    Normalization performed here: a skill-backed job gets its version pinned when
    absent. The returned object is safe to persist.
    """
    # Rule 3 — delivery adapter.
    if job.delivery.adapter not in KNOWN_ADAPTERS:
        raise JobValidationError(
            UNKNOWN_ADAPTER,
            f"delivery adapter {job.delivery.adapter!r} is not supported",
        )

    target = job.target
    is_code = target.is_code_job()

    # Rule 2 — a code job needs a workspace; approve_external needs an operator.
    if is_code and not target.workspace_root:
        raise JobValidationError(
            WORKSPACE_REQUIRED,
            "a code job needs a folder to work in",
        )
    if target.autonomy == "approve_external" and not allow_external:
        raise JobValidationError(
            EXTERNAL_NOT_ALLOWED,
            "this job can't be set up to make outside changes without an operator's say-so",
        )

    manifest_permissions: Optional[frozenset[str]] = None

    if target.kind == "skill":
        if not target.skill_id:
            raise JobValidationError(TARGET_INVALID, "a skill job needs a skill")
        if skill_registry is None:
            raise JobValidationError(SKILL_NOT_FOUND, f"skill {target.skill_id!r} is not available")
        manifest = skill_registry.manifest(target.skill_id)
        if manifest is None:
            raise JobValidationError(
                SKILL_NOT_FOUND, f"skill {target.skill_id!r} is not installed"
            )
        # Rule 5 — pin a concrete version.
        pinned = target.skill_version
        if pinned:
            resolved = skill_registry.resolve_version(target.skill_id, pinned)
            if resolved != pinned:
                raise JobValidationError(
                    SKILL_VERSION_NOT_FOUND,
                    f"skill {target.skill_id!r} version {pinned!r} is not installed",
                )
        else:
            resolved = skill_registry.resolve_version(target.skill_id)
            if not resolved:
                raise JobValidationError(
                    SKILL_VERSION_NOT_FOUND,
                    f"skill {target.skill_id!r} has no installable version",
                )
            target = target.model_copy(update={"skill_version": resolved})
            job = job.model_copy(update={"target": target})
        manifest_permissions = frozenset(manifest.permissions)
    else:  # objective
        if not target.objective or not target.objective.strip():
            raise JobValidationError(TARGET_INVALID, "an objective job needs a description")

    # Rule 1 — permission binding for a code job.
    if is_code and target.autonomy:
        needed = _code_grants_for(target.autonomy)
        if manifest_permissions is not None:
            missing = sorted(needed - manifest_permissions)
            if missing:
                raise JobValidationError(
                    PERMISSION_NOT_HELD,
                    f"this job needs {missing[0]}, which the skill doesn't allow",
                    missing=missing[0],
                )
        # A forbidden/blank grant set means an unknown profile — fail closed.
        if not needed:
            raise JobValidationError(
                PERMISSION_NOT_HELD,
                f"the access level {target.autonomy!r} isn't recognized",
            )

    # Rule 4 — watch path confinement.
    if job.kind == "file_watch":
        root = _resolve_watch_root(target.workspace_root)
        if root is None:
            raise JobValidationError(
                WATCH_PATH_REFUSED,
                "there's no folder available to watch for changes",
            )
        try:
            policy.resolve_within(root, job.watch_path or "")
        except WorkspaceDenial as denial:  # pragma: no cover - defensive
            raise JobValidationError(WATCH_PATH_REFUSED, denial.reason) from denial
        except policy.PolicyDenial as denial:
            raise JobValidationError(WATCH_PATH_REFUSED, denial.reason) from denial

    return job


def _resolve_watch_root(workspace_root: Optional[str]) -> Optional[Path]:
    """The root a watch path must stay inside: the job's declared workspace, else
    the server-resolved default workspace root."""
    if workspace_root:
        candidate = Path(workspace_root)
        if candidate.is_dir():
            return Path(__import__("os").path.realpath(candidate))
        return None
    return default_root()


__all__ = [
    "EXTERNAL_NOT_ALLOWED",
    "JobValidationError",
    "PERMISSION_NOT_HELD",
    "SKILL_NOT_FOUND",
    "SKILL_VERSION_NOT_FOUND",
    "TARGET_INVALID",
    "UNKNOWN_ADAPTER",
    "WATCH_PATH_REFUSED",
    "WORKSPACE_REQUIRED",
    "validate_job",
]
