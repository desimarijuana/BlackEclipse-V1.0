"""RSL subject safety: the frozen authority and the path guard.

A candidate may propose a change, but it may not propose a change to the
machinery that decides whether the change is allowed. These globs are the RSL
subject denylist; `assert_landable_target` is the deterministic check applied
before a proposal and again before landing.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath
import re
from typing import Optional

# Every path the evaluator, the gates, the approval boundary, the tests and the
# landing machinery own. A candidate that touches one is refused, never skipped.
RSL_DENY_GLOBS: tuple[str, ...] = (
    "python/harness/evaluation/**",
    "python/harness/security/**",
    "python/harness/self_improvement/**",
    "python/harness/capabilities/**",
    "python/harness/grants.py",
    "python/harness/recovery/envelope.py",
    "python/harness/code/policy.py",
    "python/harness/code/authorizers.py",
    "python/harness/code/promotion.py",
    "python/harness/code/selfhost.py",
    "python/harness/code/patch.py",
    "python/harness/code/workspace.py",
    "python/harness/code/evolution*.py",
    "python/harness/mcp/approvals.py",
    "python/harness/skills/permissions.py",
    "python/harness/skills/versioning.py",
    "python/tests/**",
    "python/harness/evaluation/datasets/**",
    "scripts/test-*.js",
    "scripts/check-all.js",
    ".env",
    "jdds.db",
)

RSL_TARGET_REQUIRED = "RSL_TARGET_REQUIRED"
RSL_FROZEN_TARGET = "RSL_FROZEN_TARGET"
RSL_TARGET_OUTSIDE_WORKSPACE = "RSL_TARGET_OUTSIDE_WORKSPACE"


class RSLTargetError(ValueError):
    """A proposed target is not a legal RSL subject."""

    def __init__(self, code: str, *, path: Optional[str] = None, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.path = path
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


def _normalise(target: str) -> str:
    text = str(target or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def assert_landable_target(target: str) -> str:
    """Return the normalized target, or raise a structured `RSLTargetError`.

    Absolute paths, drive-qualified paths and any `..` segment are outside the
    workspace. A path matching the frozen denylist is refused with
    `RSL_FROZEN_TARGET`; the check is case-insensitive and normalizes both slash
    styles, so `./python\\harness\\evaluation\\runner.py` is still refused. The
    denylist is not a parameter: a caller cannot narrow or replace it.
    """
    normal = _normalise(target)
    if not normal:
        raise RSLTargetError(RSL_TARGET_REQUIRED, detail="a candidate must name a target")

    path = PurePosixPath(normal)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", normal) or ".." in path.parts:
        raise RSLTargetError(
            RSL_TARGET_OUTSIDE_WORKSPACE, path=normal,
            detail="the target must be a relative path inside the workspace",
        )

    folded = normal.casefold()
    for pattern in RSL_DENY_GLOBS:
        if fnmatch(folded, str(pattern).casefold()):
            raise RSLTargetError(
                RSL_FROZEN_TARGET, path=normal,
                detail="that file decides what Eclipse is allowed to do, so RSL can't change it",
            )
    return normal


__all__ = [
    "RSL_DENY_GLOBS",
    "RSL_FROZEN_TARGET",
    "RSL_TARGET_OUTSIDE_WORKSPACE",
    "RSL_TARGET_REQUIRED",
    "RSLTargetError",
    "assert_landable_target",
]
