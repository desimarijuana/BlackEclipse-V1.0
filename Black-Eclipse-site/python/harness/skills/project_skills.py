"""Project-local skills — repository-carried skill roots with explicit trust.

Inspired by Hermes' project-local skills, with Black Eclipse's safety model
kept intact. A repository may carry its own skills so a project's conventions
travel with the code — but skills are *procedures the agent follows*, so they
are **never auto-loaded from an arbitrary cloned repository**.

Design:

  * **Roots.** A project root is a directory (normally the repo root) that may
    contain skills under `.black-eclipse/skills/` and/or `.agents/skills/`.
    The `.agents` location is the cross-tool convention; `.black-eclipse` is
    this app's native location. Both are scanned, deterministically.
  * **Trust.** A root is inert until an operator records an explicit trust
    decision (`store.set_project_trust`). Discovery reports untrusted roots and
    their skill names as *notices* only — nothing is registered, so untrusted
    prose can never reach the agent.
  * **Precedence.** project > bundled library. A project skill may shadow a
    bundled skill of the same id for sessions in that project; it can never
    widen permissions (the normal permission check still runs at execution).
  * **No self-expansion.** This module only *discovers and reads* manifests.
    It cannot enable a skill, grant a permission, or change policy. A project
    skill still runs through `runtime.execute_skill` with the same default-deny
    permission gate and immutable-version checks as any other skill.

Discovery is bounded and content-hash-cached so a `git pull` cannot silently
change what a trusted root exposes without re-validation.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .loader import LoadedSkill, SkillLoadError, load_skill_folder

# Subdirectory conventions, in precedence order (first wins on id collision).
PROJECT_SKILL_SUBDIRS: tuple[str, ...] = (
    os.path.join(".black-eclipse", "skills"),
    os.path.join(".agents", "skills"),
)

# A project skill root is bounded to this many skills so a hostile repo cannot
# flood the registry/discovery surface.
MAX_PROJECT_SKILLS = 200


@dataclass
class ProjectSkillRoot:
    """One discovered project root and the trust state of its skill directory."""

    path: str
    trusted: bool
    skills_dir: str
    skill_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "trusted": self.trusted,
            "skillsDir": self.skills_dir,
            "skillIds": self.skill_ids,
            "errors": self.errors,
        }


@dataclass
class ProjectDiscovery:
    """The result of scanning a project root for skills.

    `trusted_skills` are loadable (the root is trusted); `notices` describe
    untrusted roots (names only — contents are never read).
    """

    root: Optional[str]
    trusted_root: bool = False
    roots: list[ProjectSkillRoot] = field(default_factory=list)
    trusted_skills: list[LoadedSkill] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "trustedRoot": self.trusted_root,
            "roots": [r.to_dict() for r in self.roots],
            "trustedSkillIds": [s.manifest.id for s in self.trusted_skills],
            "notices": self.notices,
        }


def canonical_root(path: str) -> str:
    """A stable absolute identity for a project root (case-normalized on Win)."""
    return os.path.normcase(os.path.abspath(path))


def find_project_root(start: str) -> Optional[str]:
    """The nearest ancestor of `start` containing `.git` (worktrees count).

    Falls back to `start` itself when no VCS marker is present, so an operator
    can still trust an ad-hoc directory explicitly.
    """
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, ".git")) or os.path.isfile(
            os.path.join(current, ".git")
        ):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def _skills_dir(root: str) -> Optional[str]:
    for sub in PROJECT_SKILL_SUBDIRS:
        candidate = os.path.join(root, sub)
        if os.path.isdir(candidate):
            return candidate
    return None


def is_trusted(store: Any, root: str) -> bool:
    """Whether an operator has trusted this root. A missing store/db is
    untrusted (fail closed)."""
    if store is None:
        return False
    try:
        record = store.get_project_trust(canonical_root(root))
    except Exception:  # noqa: BLE001 - a trust lookup failure must fail closed
        return False
    return bool(record and record.get("trusted"))


def trust_root(
    store: Any, root: str, *, note: Optional[str] = None,
) -> ProjectSkillRoot:
    """Record explicit trust for a project root. Operator-gated at the API."""
    path = os.path.abspath(root)
    store.set_project_trust(canonical_root(path), True, note=note)
    return _scan_root(store, path)


def untrust_root(store: Any, root: str) -> ProjectSkillRoot:
    """Revoke trust. Immediately stops project-skill injection on next load."""
    path = os.path.abspath(root)
    store.set_project_trust(canonical_root(path), False)
    return _scan_root(store, path)


def _load_project_skills(skills_dir: str) -> tuple[list[LoadedSkill], list[str], list[str]]:
    """Load every immediate child folder of a skills dir that has a skill.json.

    Returns (skills, ids, errors). Malformed manifests are surfaced as errors,
    never silently ignored. `MAX_PROJECT_SKILLS` bounds the scan.
    """
    skills: list[LoadedSkill] = []
    ids: list[str] = []
    errors: list[str] = []
    if not os.path.isdir(skills_dir):
        return skills, ids, errors
    try:
        entries = sorted(os.listdir(skills_dir))
    except OSError as exc:
        return skills, ids, [f"cannot read {skills_dir}: {exc}"]
    for name in entries[:MAX_PROJECT_SKILLS]:
        folder = os.path.join(skills_dir, name)
        if not os.path.isdir(folder):
            continue
        if not os.path.isfile(os.path.join(folder, "skill.json")):
            continue
        try:
            loaded = load_skill_folder(folder)
        except SkillLoadError as exc:
            errors.append(str(exc))
            continue
        skills.append(loaded)
        ids.append(loaded.manifest.id)
    return skills, ids, errors


def _scan_root(store: Any, root: str) -> ProjectSkillRoot:
    path = os.path.abspath(root)
    skills_dir = _skills_dir(path) or os.path.join(path, PROJECT_SKILL_SUBDIRS[0])
    trusted = is_trusted(store, path)
    if not trusted:
        # Never read skill contents for an untrusted root — names only, and even
        # the name listing is best-effort/skippable.
        ids: list[str] = []
        if os.path.isdir(skills_dir):
            try:
                ids = [
                    n for n in sorted(os.listdir(skills_dir))
                    if os.path.isfile(os.path.join(skills_dir, n, "skill.json"))
                ]
            except OSError:
                ids = []
        return ProjectSkillRoot(path=path, trusted=False, skills_dir=skills_dir, skill_ids=ids)
    skills, ids, errors = _load_project_skills(skills_dir)
    return ProjectSkillRoot(
        path=path, trusted=True, skills_dir=skills_dir, skill_ids=ids, errors=errors,
    )


def discover_project_skills(
    store: Any, root: Optional[str] = None, *,
    project_discovery: bool = True,
) -> ProjectDiscovery:
    """Discover project skills for a session root.

    When `project_discovery` is False the feature is off entirely: no scan, no
    notice (the global opt-out). An untrusted root yields a *notice only* —
    the skill list is reported but nothing is loaded.
    """
    if not project_discovery or not root:
        return ProjectDiscovery(root=root)
    root_path = find_project_root(root)
    root_state = _scan_root(store, root_path)
    discovery = ProjectDiscovery(
        root=root_path,
        trusted_root=root_state.trusted,
        roots=[root_state],
    )
    if not root_state.trusted:
        if root_state.skill_ids:
            discovery.notices.append(
                f"{len(root_state.skill_ids)} project skill(s) found in {root_path} "
                "but the project is not trusted — they are not loaded. "
                "Trust the project to enable them."
            )
        return discovery
    discovery.trusted_skills = [
        s for s in _load_project_skills(root_state.skills_dir)[0]
    ]
    for error in root_state.errors:
        discovery.notices.append(error)
    return discovery


def root_content_hash(root: str) -> Optional[str]:
    """A content hash of every project skill manifest under a root.

    Used so a `git pull` that changes a project skill is observable. Returns
    None when the root has no skills directory.
    """
    skills_dir = _skills_dir(os.path.abspath(root))
    if not skills_dir or not os.path.isdir(skills_dir):
        return None
    digest = hashlib.sha256()
    for name in sorted(os.listdir(skills_dir)):
        manifest_path = os.path.join(skills_dir, name, "skill.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "rb") as handle:
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(handle.read())
        except OSError:
            continue
    return digest.hexdigest()[:16]


__all__ = [
    "MAX_PROJECT_SKILLS",
    "PROJECT_SKILL_SUBDIRS",
    "ProjectDiscovery",
    "ProjectSkillRoot",
    "canonical_root",
    "discover_project_skills",
    "find_project_root",
    "is_trusted",
    "root_content_hash",
    "trust_root",
    "untrust_root",
]
