"""Skill bundles — composable, deterministic groupings of skills (Phase 3).

A bundle is a *reference*: it names skills that must already exist. It never
installs, enables or copies a skill, so it can never:
  * enable a disabled skill,
  * widen a permission or bypass the permission gate,
  * exceed the bounded prompt budget,
  * or change what the model is allowed to do.

`resolve_bundle` reports missing and non-executable members honestly. Expansion
composes the members' *discovery metadata* into one bounded block — full
instructions still load only through `skill_view`, exactly as for a single
skill. Provenance (manual/profile/project/imported) is retained so a bundle's
origin is visible and reviewable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Bounds — a bundle must not flood the prompt or the registry.
MAX_BUNDLE_SKILLS = 12
MAX_BUNDLE_INSTRUCTION_CHARS = 800
MAX_BUNDLE_CONSTRAINTS_CHARS = 800
MAX_BUNDLE_MANIFEST_CHARS = 1200

_BUNDLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

BUNDLE_PROVENANCES = ("manual", "profile", "project", "imported")

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class BundleError(ValueError):
    """A bundle definition was rejected (bad id/empty skills/too many skills)."""


@dataclass
class SkillBundle:
    id: str
    name: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    instruction: str = ""
    constraints: str = ""
    provenance: str = "manual"
    # Version identity + optional reproducibility lock (Phase 9). A lock pins the
    # exact resolved member versions so a later run reproduces the same set.
    version: str = "1.0.0"
    member_versions: dict[str, str] = field(default_factory=dict)
    # Per-member CONTENT HASH at lock time (Phase 9 hardening). Lets a locked
    # bundle be reconstructed and detects an in-place content edit under the same
    # version.
    member_hashes: dict[str, str] = field(default_factory=dict)
    locked: bool = False
    # Bounded history of prior locks (newest first) for safe rollback.
    lock_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _BUNDLE_ID_RE.match(self.id or ""):
            raise BundleError("bundle id must be a lowercase slug")
        if not self.skills:
            raise BundleError("a bundle must reference at least one skill")
        if len(self.skills) > MAX_BUNDLE_SKILLS:
            raise BundleError(f"a bundle may reference at most {MAX_BUNDLE_SKILLS} skills")
        # Normalize + de-duplicate, preserving order (deterministic).
        seen: list[str] = []
        for skill in self.skills:
            name = str(skill).strip()
            if name and name not in seen:
                seen.append(name)
        self.skills = seen
        if self.provenance not in BUNDLE_PROVENANCES:
            self.provenance = "manual"
        if not self.name:
            self.name = self.id
        self.instruction = (self.instruction or "")[:MAX_BUNDLE_INSTRUCTION_CHARS]
        self.constraints = (self.constraints or "")[:MAX_BUNDLE_CONSTRAINTS_CHARS]
        if not _SEMVER_RE.match(self.version or ""):
            raise BundleError("bundle version must be semver")
        # Only keep lock entries for members the bundle actually names.
        self.member_versions = {
            str(k): str(v) for k, v in (self.member_versions or {}).items()
            if str(k) in self.skills
        }
        self.member_hashes = {
            str(k): str(v) for k, v in (self.member_hashes or {}).items()
            if str(k) in self.skills
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skills": self.skills,
            "instruction": self.instruction,
            "constraints": self.constraints,
            "provenance": self.provenance,
            "version": self.version,
            "memberVersions": self.member_versions,
            "memberHashes": self.member_hashes,
            "lockHistory": self.lock_history,
            "locked": self.locked,
        }


@dataclass
class BundleResolution:
    """The outcome of resolving a bundle against the live registry.

    `resolved` are skills that exist and are executable by the actor; `missing`
    and `unavailable` are reported, never silently dropped. `content` is a
    bounded, metadata-only manifest block.
    """

    bundle_id: str
    ok: bool
    resolved: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    content: str = ""
    provenance: str = "manual"
    instruction: str = ""
    constraints: str = ""
    # Phase 9 lifecycle.
    version: str = "1.0.0"
    locked: bool = False
    drifted: bool = False
    incompatible: list[str] = field(default_factory=list)
    resolved_versions: dict[str, str] = field(default_factory=dict)
    # Per-member content hash at lock time, and the live hash now: a mismatch (a
    # content edit under the same version) is reported as drifted content.
    locked_hashes: dict[str, str] = field(default_factory=dict)
    current_hashes: dict[str, str] = field(default_factory=dict)
    content_drifted: list[str] = field(default_factory=list)
    # A reproducibility receipt: the exact member (id, version, contentHash) set.
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundleId": self.bundle_id,
            "ok": self.ok,
            "resolved": self.resolved,
            "missing": self.missing,
            "unavailable": self.unavailable,
            "provenance": self.provenance,
            "chars": len(self.content),
            "version": self.version,
            "locked": self.locked,
            "drifted": self.drifted,
            "contentDrifted": self.content_drifted,
            "compatible": not self.incompatible and not self.drifted and not self.missing,
            "incompatible": self.incompatible,
            "resolvedVersions": self.resolved_versions,
            "lockedHashes": self.locked_hashes,
            "currentHashes": self.current_hashes,
            "receipt": self.receipt,
        }


def resolve_bundle(
    store: Any,
    registry: Any,
    bundle_id: str,
    *,
    actor: Any = None,
) -> BundleResolution:
    """Resolve a bundle deterministically.

    A missing bundle is an error (`ok=False`). A missing/non-executable member
    is *reported* and skipped — the bundle still resolves its loadable members,
    matching the documented "missing skills are not fatal" behaviour, but never
    enables a disabled skill. Permission filtering is applied when an actor is
    supplied; a member the actor cannot use is `unavailable`.
    """
    record = store.get_skill_bundle(bundle_id)
    if not record:
        return BundleResolution(bundle_id=bundle_id, ok=False)
    bundle = SkillBundle(
        id=record["id"],
        name=record.get("name") or record["id"],
        description=record.get("description") or "",
        skills=list(record.get("skills") or []),
        instruction=record.get("instruction") or "",
        constraints=record.get("constraints") or "",
        provenance=record.get("provenance") or "manual",
        version=record.get("version") or "1.0.0",
        member_versions=record.get("memberVersions") or {},
        member_hashes=record.get("memberHashes") or {},
        lock_history=list(record.get("lockHistory") or []),
        locked=bool(record.get("locked")),
    )
    return _resolve(bundle, registry, actor=actor)


def lock_bundle(
    store: Any, registry: Any, bundle_id: str,
) -> dict[str, Any]:
    """Pin the bundle's current resolved member versions AND content hashes.

    Records the exact version and content hash of each resolvable member and
    marks the bundle locked. A later resolve reports `drifted` when a member's
    version differs and `contentDrifted` when its content hash differs (an
    in-place edit under the same version). Never enables or widens anything. The
    saved lock is exportable, so a locked bundle can be reconstructed.
    """
    record = store.get_skill_bundle(bundle_id)
    if not record:
        return {"ok": False, "error": "bundle not found"}
    resolution = resolve_bundle(store, registry, bundle_id)
    member_versions: dict[str, str] = {}
    member_hashes: dict[str, str] = {}
    for skill_id in resolution.resolved:
        manifest = registry.manifest(skill_id) if registry else None
        if manifest is not None:
            member_versions[skill_id] = manifest.version
            member_hashes[skill_id] = _member_hash(registry, skill_id, manifest.version)
    # Preserve the prior lock (if any) so a rollback has a target.
    history = list(record.get("lockHistory") or [])
    if record.get("locked") and record.get("memberVersions"):
        history.insert(0, {
            "memberVersions": record.get("memberVersions") or {},
            "memberHashes": record.get("memberHashes") or {},
        })
    saved = store.save_skill_bundle({
        **record, "memberVersions": member_versions,
        "memberHashes": member_hashes, "lockHistory": history[:10], "locked": True,
    })
    try:
        store.append_event("skill.bundle_locked", data={
            "bundleId": bundle_id, "members": member_versions, "hashes": member_hashes,
        })
    except Exception:  # noqa: BLE001 - audit is best-effort
        pass
    return {"ok": True, "bundle": saved}


def _member_hash(registry: Any, skill_id: str, version: str) -> str:
    """The LIVE content identity of a member version (manifest + prose).

    Uses the loaded skill's `version_identity` (which folds the instruction
    content), so an in-place edit of a `SKILL.md` under the same version is
    detectable. Falls back to the stored version hash, then the manifest hash.
    Never raises.
    """
    try:
        loaded = registry.get(skill_id) if hasattr(registry, "get") else None
        manifest = registry.manifest(skill_id)
        if manifest is not None:
            instructions = None
            if loaded is not None:
                try:
                    instructions = loaded.load_instructions()
                except Exception:  # noqa: BLE001
                    instructions = None
            return manifest.version_identity(instructions)
    except Exception:  # noqa: BLE001
        pass
    try:
        stored = registry.store.get_version(skill_id, version)
        if stored and stored.get("contentHash"):
            return str(stored["contentHash"])
    except Exception:  # noqa: BLE001
        pass
    return ""


def bundle_update_preview(store: Any, registry: Any, bundle_id: str) -> dict[str, Any]:
    """What would change if the bundle were re-locked at the current versions.

    Reports each member's locked vs current version/hash so an update never
    silently changes locked behavior. Deterministic; never mutates.
    """
    record = store.get_skill_bundle(bundle_id)
    if not record:
        return {"ok": False, "error": "bundle not found"}
    resolution = resolve_bundle(store, registry, bundle_id)
    locked_versions = record.get("memberVersions") or {}
    locked_hashes = record.get("memberHashes") or {}
    changes = []
    for skill_id in resolution.resolved:
        manifest = registry.manifest(skill_id)
        current_version = manifest.version if manifest else None
        current_hash = _member_hash(registry, skill_id, current_version) if current_version else None
        lv = locked_versions.get(skill_id)
        lh = locked_hashes.get(skill_id)
        if lv is None:
            kind = "added"
        elif lv != current_version:
            kind = "version_changed"
        elif lh and lh != current_hash:
            kind = "content_changed"
        else:
            kind = "unchanged"
        changes.append({
            "skillId": skill_id, "change": kind,
            "lockedVersion": lv, "currentVersion": current_version,
            "lockedHash": lh, "currentHash": current_hash,
        })
    return {
        "ok": True, "bundleId": bundle_id, "locked": bool(record.get("locked")),
        "wouldChange": any(c["change"] != "unchanged" for c in changes),
        "changes": changes,
    }


def rollback_bundle(store: Any, registry: Any, bundle_id: str) -> dict[str, Any]:
    """Re-pin the bundle to its most recent recorded lock (safe rollback).

    Restores the previous lock from the bounded history, so an update that
    drifted the bundle is reverted to the recorded, reproducible state. Falls
    back to the current lock when there is no history. Never enables a disabled
    skill or widens a permission — it only restores lock metadata.
    """
    record = store.get_skill_bundle(bundle_id)
    if not record:
        return {"ok": False, "error": "bundle not found"}
    history = list(record.get("lockHistory") or [])
    if history:
        previous = history[0]
        saved = store.save_skill_bundle({
            **record,
            "memberVersions": previous.get("memberVersions") or {},
            "memberHashes": previous.get("memberHashes") or {},
            "lockHistory": history[1:],
            "locked": True,
        })
    else:
        # No recorded prior lock: re-affirm the current lock.
        saved = store.save_skill_bundle({
            **record,
            "memberVersions": record.get("memberVersions") or {},
            "memberHashes": record.get("memberHashes") or {},
            "locked": True,
        })
    try:
        store.append_event("skill.bundle_rolled_back", data={"bundleId": bundle_id})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "bundle": saved}


def unlock_bundle(store: Any, bundle_id: str) -> dict[str, Any]:
    record = store.get_skill_bundle(bundle_id)
    if not record:
        return {"ok": False, "error": "bundle not found"}
    saved = store.save_skill_bundle({**record, "locked": False})
    return {"ok": True, "bundle": saved}


def _resolve(bundle: SkillBundle, registry: Any, *, actor: Any) -> BundleResolution:
    order: list[str] = []
    for skill_id in bundle.skills:
        if skill_id in order:
            continue
        manifest = registry.manifest(skill_id) if registry else None
        if manifest is None:
            continue
        order.append(skill_id)

    resolved: list[str] = []
    missing: list[str] = []
    unavailable: list[str] = []
    incompatible: list[str] = []
    resolved_versions: dict[str, str] = {}
    locked_hashes: dict[str, str] = dict(bundle.member_hashes)
    current_hashes: dict[str, str] = {}
    content_drifted: list[str] = []
    receipt_members: list[dict[str, Any]] = []
    drifted = False
    lines = [
        f"Skill bundle '{bundle.id}' v{bundle.version} ({bundle.provenance}) — discovery only; "
        "call skill_view for full instructions. It does not enable or run anything."
    ]
    if bundle.description:
        lines.append(bundle.description[:200])
    lines.append("Skills:")
    for skill_id in bundle.skills:
        manifest = registry.manifest(skill_id) if registry else None
        if manifest is None:
            missing.append(skill_id)
            lines.append(f"- {skill_id} (MISSING — not installed)")
            continue
        # A disabled/deprecated skill is never silently enabled by a bundle.
        stored = registry.store.get_skill(skill_id)
        status = stored["status"] if stored else manifest.status
        if status in ("disabled", "deprecated", "rejected", "superseded"):
            unavailable.append(skill_id)
            lines.append(f"- {skill_id} ({status} — not loaded)")
            continue
        if actor is not None:
            from .permissions import check_permissions  # noqa: PLC0415

            if not check_permissions(manifest.permissions, actor).allowed:
                unavailable.append(skill_id)
                lines.append(f"- {skill_id} (permission denied for this actor)")
                continue
        current_hash = _member_hash(registry, skill_id, manifest.version)
        current_hashes[skill_id] = current_hash
        # Lock/compatibility: a locked bundle reports a member whose version OR
        # content changed since it was locked. It is still loaded (a bundle never
        # disables), but the drift is visible before execution.
        locked_version = bundle.member_versions.get(skill_id)
        locked_hash = bundle.member_hashes.get(skill_id)
        if bundle.locked and locked_version and locked_version != manifest.version:
            drifted = True
            incompatible.append(f"{skill_id}: locked v{locked_version} -> v{manifest.version}")
            lines.append(f"- {skill_id} (v{manifest.version} — DRIFTED from locked v{locked_version})")
        elif bundle.locked and locked_hash and current_hash and locked_hash != current_hash:
            content_drifted.append(skill_id)
            incompatible.append(f"{skill_id}: content changed under v{manifest.version}")
            lines.append(f"- {skill_id} (v{manifest.version} — CONTENT DRIFTED from locked)")
        else:
            lines.append(f"- {skill_id} (v{manifest.version}): {manifest.description[:120]}")
        resolved.append(skill_id)
        resolved_versions[skill_id] = manifest.version
        receipt_members.append({
            "skillId": skill_id, "version": manifest.version,
            "contentHash": current_hash,
            "lockedVersion": locked_version, "lockedHash": locked_hash,
        })
    content = "\n".join(lines)
    if len(content) > MAX_BUNDLE_MANIFEST_CHARS:
        content = content[: MAX_BUNDLE_MANIFEST_CHARS - 1].rstrip() + "…"
    return BundleResolution(
        bundle_id=bundle.id,
        ok=bool(resolved),
        resolved=resolved,
        missing=missing,
        unavailable=unavailable,
        content=content,
        provenance=bundle.provenance,
        instruction=bundle.instruction,
        constraints=bundle.constraints,
        version=bundle.version,
        locked=bundle.locked,
        drifted=drifted,
        incompatible=incompatible,
        resolved_versions=resolved_versions,
        locked_hashes=locked_hashes,
        current_hashes=current_hashes,
        content_drifted=content_drifted,
        receipt={
            "bundleId": bundle.id, "bundleVersion": bundle.version,
            "locked": bundle.locked, "members": receipt_members,
        },
    )


__all__ = [
    "BUNDLE_PROVENANCES",
    "MAX_BUNDLE_SKILLS",
    "bundle_update_preview",
    "lock_bundle",
    "rollback_bundle",
    "unlock_bundle",
    "BundleError",
    "BundleResolution",
    "SkillBundle",
    "resolve_bundle",
]
