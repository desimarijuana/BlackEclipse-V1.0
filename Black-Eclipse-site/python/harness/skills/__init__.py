"""Phase 3 — the Skill System.

Skills are versioned, machine-readable procedures executed by the EXISTING
Phase-1 agent runtime. This package owns:

    manifest.py     the pydantic skill manifest + enums
    permissions.py  the centralized, default-deny permission policy
    store.py        skill lifecycle persistence in agent-memory.db
    library.py      loading skill.json + SKILL.md folders
    registry.py     the single skill registry (discovery, validation, versions)
    runtime.py      SkillExecutionRequest/Result + execution via execute_run
    learning.py     trace analysis → learning candidates (never auto-enable)
    draft.py        candidate → unvalidated draft (never auto-enable)
    evaluation.py   deterministic evaluation + promotion gates
    events.py       skill.* event vocabulary
    library/        the shipped skills

There is no second runtime, no second tool registry, and no second database.
"""

from .loader import LoadedSkill, SkillLoadError, load_catalog, load_skill_folder
from .manifest import (
    ExecutionLimits,
    ExecutionMode,
    SkillDependencySpec,
    SkillManifest,
    parse_version,
    version_satisfies,
)
from .permissions import (
    Actor,
    DEFAULT_ACTOR,
    OPERATOR_ACTOR,
    PermissionDecision,
    check_permissions,
)
from .registry import DependencyResolution, SkillRegistry
from .store import SkillStore

__all__ = [
    "Actor",
    "DEFAULT_ACTOR",
    "DependencyResolution",
    "ExecutionLimits",
    "ExecutionMode",
    "LoadedSkill",
    "OPERATOR_ACTOR",
    "PermissionDecision",
    "SkillDependencySpec",
    "SkillLoadError",
    "SkillManifest",
    "SkillRegistry",
    "SkillStore",
    "check_permissions",
    "load_catalog",
    "load_skill_folder",
    "parse_version",
    "version_satisfies",
]
