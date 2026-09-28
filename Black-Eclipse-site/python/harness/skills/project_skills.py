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
    """One discovered project root and the trust state of its skill directory.

    `drift` is True when the root is trusted but its content identity no longer
    matches the hash recorded at trust time. With per-skill identity, only the
    CHANGED skills are quarantined (`changed_skill_ids`); unchanged skills still
    load. Without per-skill identity (a legacy root-level trust row) the whole
    root is quarantined, preserving the previous behavior.
    """

    path: str
    trusted: bool
    skills_dir: str
    skill_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    drift: bool = False
    trusted_hash: Optional[str] = None
    current_hash: Optional[str] = None
    # Per-skill identity (Phase 2 final hardening).
    changed_skill_ids: list[str] = field(default_factory=list)
    quarantined_skill_ids: list[str] = field(default_factory=list)
    unchanged_skill_ids: list[str] = field(default_factory=list)
    per_skill_hashes: dict[str, str] = field(default_factory=dict)
    approved_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "trusted": self.trusted,
            "skillsDir": self.skills_dir,
            "skillIds": self.skill_ids,
            "errors": self.errors,
            "drift": self.drift,
            "trustedHash": self.trusted_hash,
            "currentHash": self.current_hash,
            "changedSkillIds": self.changed_skill_ids,
            "quarantinedSkillIds": self.quarantined_skill_ids,
            "unchangedSkillIds": self.unchanged_skill_ids,
            "perSkillHashes": self.per_skill_hashes,
            "approvedHashes": self.approved_hashes,
        }


@dataclass
class ProjectDiscovery:
    """The result of scanning a project root for skills.

    `trusted_skills` are loadable (the root is trusted and each skill is either
    unchanged or re-approved); `notices` describe untrusted roots (names only —
    contents are never read) and changed-skill quarantine.
    """

    root: Optional[str]
    trusted_root: bool = False
    roots: list[ProjectSkillRoot] = field(default_factory=list)
    trusted_skills: list[LoadedSkill] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    drift: bool = False
    # Per-skill drift (Phase 2 final hardening): the changed skills held back and
    # the unchanged skills still loaded.
    changed_skill_ids: list[str] = field(default_factory=list)
    quarantined_skill_ids: list[str] = field(default_factory=list)
    unchanged_skill_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "trustedRoot": self.trusted_root,
            "drift": self.drift,
            "roots": [r.to_dict() for r in self.roots],
            "trustedSkillIds": [s.manifest.id for s in self.trusted_skills],
            "changedSkillIds": self.changed_skill_ids,
            "quarantinedSkillIds": self.quarantined_skill_ids,
            "unchangedSkillIds": self.unchanged_skill_ids,
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
    store: Any, root: str, *, note: Optional[str] = None, actor: Optional[str] = None,
    skill_ids: Optional[list[str]] = None, level: str = "root",
) -> ProjectSkillRoot:
    """Record explicit trust for a project root, capturing its content identity.

    The captured hash is the baseline a later change is compared against; an
    approval after drift uses the same path so it re-baselines. Both the
    root-level hash and a per-skill hash map are stored so a later change can be
    narrowed to the affected skill(s). Every decision is appended to the
    approval history (`actor` is an operator transport label, never a body
    identity). Operator-gated at the API.

    `skill_ids`/`level` let a per-skill re-approval be recorded distinctly
    (`level='skill'`), though re-approval always re-baselines the whole root so
    the identity is consistent.
    """
    path = os.path.abspath(root)
    hashes = per_skill_hashes(path)
    store.set_project_trust(
        canonical_root(path), True, note=note,
        content_hash=root_content_hash(path), content_hashes=hashes,
    )
    try:
        store.record_project_approval(
            canonical_root(path), "approve", level=level, actor=actor,
            approved_hash=root_content_hash(path), content_hashes=hashes,
            skill_ids=skill_ids or sorted(hashes.keys()), note=note,
        )
    except Exception:  # noqa: BLE001 - history is best-effort, never blocks trust
        pass
    return _scan_root(store, path)


def untrust_root(store: Any, root: str, *, actor: Optional[str] = None) -> ProjectSkillRoot:
    """Revoke trust. Immediately stops project-skill injection on next load."""
    path = os.path.abspath(root)
    store.set_project_trust(
        canonical_root(path), False, content_hash=root_content_hash(path),
    )
    try:
        store.record_project_approval(
            canonical_root(path), "untrust", level="root", actor=actor,
            approved_hash=None, skill_ids=[],
        )
    except Exception:  # noqa: BLE001 - history is best-effort
        pass
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


def _skill_identity(folder: str) -> tuple[Optional[str], Optional[str]]:
    """(skillId, contentHash) for one project skill folder, or (None, None).

    The content hash covers `skill.json` **and** each declared instruction file
    (e.g. `SKILL.md`), so a prose change counts as a content change. `skillId` is
    read from the manifest so identity survives a folder rename.
    """
    manifest_path = os.path.join(folder, "skill.json")
    if not os.path.isfile(manifest_path):
        return None, None
    try:
        with open(manifest_path, "rb") as handle:
            manifest_bytes = handle.read()
    except OSError:
        return None, None
    try:
        import json as _json  # noqa: PLC0415

        declared = _json.loads(manifest_bytes).get("instructions")
        skill_id = _json.loads(manifest_bytes).get("id")
    except (ValueError, TypeError):
        declared = None
        skill_id = None
    digest = hashlib.sha256()
    digest.update(manifest_bytes)
    candidates = [declared] if isinstance(declared, str) and declared else []
    if not candidates:
        for default in ("SKILL.md", "skill.md"):
            if os.path.isfile(os.path.join(folder, default)):
                candidates.append(default)
                break
    for rel in candidates:
        instr_path = os.path.join(folder, rel)
        if os.path.isfile(instr_path):
            try:
                with open(instr_path, "rb") as handle:
                    digest.update(rel.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(handle.read())
            except OSError:
                pass
    return (str(skill_id) if skill_id else None), digest.hexdigest()[:16]


def per_skill_hashes(root: str) -> dict[str, str]:
    """A `{skillId: contentHash}` map for every project skill under a root.

    Bounded and content-derived (manifest + prose). Used as the per-skill trust
    baseline so a later change can be attributed to the affected skill(s).
    """
    out: dict[str, str] = {}
    skills_dir = _skills_dir(os.path.abspath(root))
    if not skills_dir or not os.path.isdir(skills_dir):
        return out
    for name in sorted(os.listdir(skills_dir))[:MAX_PROJECT_SKILLS]:
        folder = os.path.join(skills_dir, name)
        if not os.path.isdir(folder):
            continue
        skill_id, content_hash = _skill_identity(folder)
        if skill_id and content_hash:
            out[skill_id] = content_hash
    return out


def _scan_root(store: Any, root: str) -> ProjectSkillRoot:
    path = os.path.abspath(root)
    skills_dir = _skills_dir(path) or os.path.join(path, PROJECT_SKILL_SUBDIRS[0])
    record = None
    if store is not None:
        try:
            record = store.get_project_trust(canonical_root(path))
        except Exception:  # noqa: BLE001 - a trust lookup failure fails closed
            record = None
    trusted = bool(record and record.get("trusted"))
    current_hashes = per_skill_hashes(path)
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
        return ProjectSkillRoot(
            path=path, trusted=False, skills_dir=skills_dir, skill_ids=ids,
            current_hash=root_content_hash(path),
            per_skill_hashes=current_hashes,
        )

    current_hash = root_content_hash(path)
    trusted_hash = record.get("trustedHash") if record else None
    approved_hashes = {}
    if record and isinstance(record.get("contentHashes"), dict):
        approved_hashes = {str(k): str(v) for k, v in record["contentHashes"].items()}
    root_drift = bool(trusted_hash) and trusted_hash != current_hash

    if not approved_hashes:
        # Legacy/root-level trust with no per-skill identity: quarantine the whole
        # root when it changed (previous behavior, fail-closed).
        if root_drift:
            ids = sorted(
                n for n in (os.listdir(skills_dir) if os.path.isdir(skills_dir) else [])
                if os.path.isfile(os.path.join(skills_dir, n, "skill.json"))
            )
            return ProjectSkillRoot(
                path=path, trusted=True, skills_dir=skills_dir, skill_ids=ids,
                drift=True, trusted_hash=trusted_hash, current_hash=current_hash,
                quarantined_skill_ids=list(current_hashes.keys()) or ids,
                per_skill_hashes=current_hashes,
                errors=[
                    "project skills changed since trust was granted; they are "
                    "quarantined until the project is re-approved"
                ],
            )
        skills, ids, errors = _load_project_skills(skills_dir)
        return ProjectSkillRoot(
            path=path, trusted=True, skills_dir=skills_dir, skill_ids=ids, errors=errors,
            drift=False, trusted_hash=trusted_hash, current_hash=current_hash,
            per_skill_hashes=current_hashes,
        )

    # Per-skill identity is present: quarantine only the changed/new skills.
    changed: list[str] = []
    unchanged: list[str] = []
    for skill_id, content_hash in current_hashes.items():
        approved = approved_hashes.get(skill_id)
        if approved is not None and approved == content_hash:
            unchanged.append(skill_id)
        else:
            # Newly added (no approved hash) OR changed: require re-approval.
            changed.append(skill_id)
    drift = bool(changed)
    ids = sorted(current_hashes.keys())
    return ProjectSkillRoot(
        path=path, trusted=True, skills_dir=skills_dir, skill_ids=ids,
        drift=drift, trusted_hash=trusted_hash, current_hash=current_hash,
        changed_skill_ids=sorted(changed),
        quarantined_skill_ids=sorted(changed),
        unchanged_skill_ids=sorted(unchanged),
        per_skill_hashes=current_hashes,
        approved_hashes=approved_hashes,
        errors=(
            ["project skills changed since approval; changed skills are "
             "quarantined until re-approved: " + ", ".join(sorted(changed))]
            if changed else []
        ),
    )


def discover_project_skills(
    store: Any, root: Optional[str] = None, *,
    project_discovery: bool = True,
) -> ProjectDiscovery:
    """Discover project skills for a session root.

    When `project_discovery` is False the feature is off entirely: no scan, no
    notice (the global opt-out). An untrusted root yields a *notice only* —
    the skill list is reported but nothing is loaded.

    With per-skill identity, a changed skill is quarantined on its own: unchanged
    skills still load, and only the changed skill(s) require re-approval.
    """
    if not project_discovery or not root:
        return ProjectDiscovery(root=root)
    root_path = find_project_root(root)
    root_state = _scan_root(store, root_path)
    discovery = ProjectDiscovery(
        root=root_path,
        trusted_root=root_state.trusted,
        roots=[root_state],
        drift=root_state.drift,
        changed_skill_ids=list(root_state.changed_skill_ids),
        quarantined_skill_ids=list(root_state.quarantined_skill_ids),
        unchanged_skill_ids=list(root_state.unchanged_skill_ids),
    )
    if not root_state.trusted:
        if root_state.skill_ids:
            discovery.notices.append(
                f"{len(root_state.skill_ids)} project skill(s) found in {root_path} "
                "but the project is not trusted — they are not loaded. "
                "Trust the project to enable them."
            )
        return discovery
    if root_state.drift:
        if root_state.quarantined_skill_ids and root_state.unchanged_skill_ids:
            # Per-skill quarantine: load only the unchanged skills.
            all_skills, _, errors = _load_project_skills(root_state.skills_dir)
            changed = set(root_state.quarantined_skill_ids)
            discovery.trusted_skills = [
                s for s in all_skills if s.manifest.id not in changed
            ]
            discovery.notices.append(
                "changed project skill(s) are quarantined and not loaded until "
                "re-approved: " + ", ".join(root_state.quarantined_skill_ids)
            )
            for error in [*root_state.errors, *errors]:
                if error not in discovery.notices:
                    discovery.notices.append(error)
            return discovery
        # Legacy/root-level quarantine: nothing loads (fail closed).
        discovery.notices.append(
            f"project skills in {root_path} changed since trust was granted and "
            "are quarantined — review and re-approve the project to enable them."
        )
        return discovery
    discovery.trusted_skills = [
        s for s in _load_project_skills(root_state.skills_dir)[0]
    ]
    for error in root_state.errors:
        discovery.notices.append(error)
    return discovery


def changed_skill_review(store: Any, root: str) -> dict[str, Any]:
    """A content-free review of what changed under a trusted root.

    Reports, per skill: the approved hash, the current hash, and whether it
    changed. The full content is never returned — only hashes and ids — so the
    review is safe to surface broadly. Deterministic; never loads or executes
    anything.
    """
    state = _scan_root(store, root)
    changes: list[dict[str, Any]] = []
    for skill_id, current in sorted(state.per_skill_hashes.items()):
        approved = state.approved_hashes.get(skill_id)
        status = "unchanged" if approved == current else ("new" if approved is None else "changed")
        changes.append({
            "skillId": skill_id, "status": status,
            "approvedHash": approved, "currentHash": current,
        })
    # Skills present at approval but now missing.
    for skill_id in sorted(set(state.approved_hashes) - set(state.per_skill_hashes)):
        changes.append({
            "skillId": skill_id, "status": "removed",
            "approvedHash": state.approved_hashes[skill_id], "currentHash": None,
        })
    return {
        "path": state.path,
        "trusted": state.trusted,
        "drift": state.drift,
        "changedSkillIds": state.changed_skill_ids,
        "quarantinedSkillIds": state.quarantined_skill_ids,
        "unchangedSkillIds": state.unchanged_skill_ids,
        "changes": changes,
    }


def drift_status(store: Any, root: str) -> dict[str, Any]:
    """Bounded, content-free drift status for a project root (for the UI)."""
    state = _scan_root(store, root)
    return {
        "path": state.path,
        "trusted": state.trusted,
        "drift": state.drift,
        "trustedHash": state.trusted_hash,
        "currentHash": state.current_hash,
        "skillIds": state.skill_ids,
        "changedSkillIds": state.changed_skill_ids,
        "quarantinedSkillIds": state.quarantined_skill_ids,
        "unchangedSkillIds": state.unchanged_skill_ids,
        "perSkillHashes": state.per_skill_hashes,
        "approvedHashes": state.approved_hashes,
    }


def root_content_hash(root: str) -> Optional[str]:
    """A content hash of every project skill under a root (manifest AND prose).

    Covers `skill.json` **and** each declared instruction file (e.g. `SKILL.md`),
    so a change to a skill's executable procedure is detectable, not just its
    metadata. Used as the trust baseline and to detect post-trust drift. Returns
    None when the root has no skills directory.
    """
    skills_dir = _skills_dir(os.path.abspath(root))
    if not skills_dir or not os.path.isdir(skills_dir):
        return None
    digest = hashlib.sha256()
    for name in sorted(os.listdir(skills_dir)):
        folder = os.path.join(skills_dir, name)
        manifest_path = os.path.join(folder, "skill.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "rb") as handle:
                manifest_bytes = handle.read()
        except OSError:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(manifest_bytes)
        # Include the instruction file(s) so prose changes count as content drift.
        try:
            import json as _json  # noqa: PLC0415

            declared = _json.loads(manifest_bytes).get("instructions")
        except (ValueError, TypeError):
            declared = None
        candidates = [declared] if isinstance(declared, str) and declared else []
        if not candidates:
            for default in ("SKILL.md", "skill.md"):
                if os.path.isfile(os.path.join(folder, default)):
                    candidates.append(default)
                    break
        for rel in candidates:
            instr_path = os.path.join(folder, rel)
            if os.path.isfile(instr_path):
                try:
                    with open(instr_path, "rb") as handle:
                        digest.update(rel.encode("utf-8"))
                        digest.update(b"\0")
                        digest.update(handle.read())
                except OSError:
                    pass
    return digest.hexdigest()[:16]


__all__ = [
    "MAX_PROJECT_SKILLS",
    "PROJECT_SKILL_SUBDIRS",
    "ProjectDiscovery",
    "ProjectSkillRoot",
    "canonical_root",
    "changed_skill_review",
    "discover_project_skills",
    "drift_status",
    "find_project_root",
    "is_trusted",
    "per_skill_hashes",
    "root_content_hash",
    "trust_root",
    "untrust_root",
]
