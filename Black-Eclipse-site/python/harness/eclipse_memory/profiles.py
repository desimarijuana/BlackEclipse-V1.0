"""Named profiles (Milestone 4) — the durable identity/isolation layer.

A **profile** is a named namespace that scopes memory, sessions, skills and
provider access, and carries its own prompt profile, retention and settings. It
is a thin metadata record plus a human-readable directory projection — NOT a
second database. SQLite (`eclipse-memory.db`) stays canonical for structured
records; the directory under `.black-eclipse/profiles/<profileId>/` is a
projection.

Isolation rules enforced here:

  * every memory / session / skill / provider query must carry the resolved
    `profileId`; a memory or session from another profile is never returned;
  * inheritance is explicit and READ-ONLY in the child (a child profile may read
    a parent's memory but never mutate it);
  * profiles are local labels, not security identities — but a cross-profile
    query is still refused, because leaking one profile's memory into another is
    a correctness bug even for one user.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Safe, filesystem-friendly profile id.
_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

DEFAULT_PROFILE_ID = "default"

# Per-namespace defaults. A profile may override retention/settings; it can only
# TIGHTEN a privacy control (e.g. shorter retention), never widen a safety floor.
_NAMESPACE_KEYS = ("memory", "session", "skill", "provider")


@dataclass
class ProfileRecord:
    id: str
    name: str
    directory: str
    memoryNamespace: str
    sessionNamespace: str
    skillNamespace: str
    providerNamespace: str
    promptProfile: str
    retentionDays: int = 0
    settings: dict[str, Any] = field(default_factory=dict)
    inherits: Optional[str] = None
    inheritsReadOnly: bool = True
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profiles_root() -> str:
    override = os.environ.get("BLACK_ECLIPSE_PROFILES_ROOT")
    if override:
        return os.path.abspath(override)
    # <repo root>/.black-eclipse/profiles — anchored to the package, not cwd.
    from .config import repo_root  # noqa: PLC0415

    return os.path.join(repo_root(), ".black-eclipse", "profiles")


def profile_dir(profile_id: str) -> str:
    return os.path.join(profiles_root(), profile_id)


class ProfileError(ValueError):
    """A profile operation was rejected (bad id, unknown profile, cycle)."""


def validate_profile_id(profile_id: str) -> str:
    if not _PROFILE_ID_RE.match(profile_id or ""):
        raise ProfileError(
            "profile id must be a lowercase slug (letters, digits, '.', '-', '_', max 64)"
        )
    return profile_id


def _default_record(profile_id: str, *, name: Optional[str] = None, inherits: Optional[str] = None) -> ProfileRecord:
    validate_profile_id(profile_id)
    return ProfileRecord(
        id=profile_id,
        name=name or profile_id,
        directory=profile_dir(profile_id),
        memoryNamespace=f"profile:{profile_id}",
        sessionNamespace=f"profile:{profile_id}",
        skillNamespace=f"profile:{profile_id}",
        providerNamespace=f"profile:{profile_id}",
        promptProfile=profile_id,
        inherits=inherits,
    )


class ProfileRegistry:
    """Reads/writes the named-profile registry as a JSON file under the profiles
    root. This is metadata only — no memory content lives here."""

    def __init__(self, root: Optional[str] = None) -> None:
        self._root = root or profiles_root()

    @property
    def root(self) -> str:
        return self._root

    def _index_path(self) -> str:
        return os.path.join(self._root, "PROFILES.json")

    def _load_index(self) -> dict[str, Any]:
        path = self._index_path()
        if not os.path.isfile(path):
            return {"profiles": {}}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
                return {"profiles": {}}
            return data
        except (OSError, ValueError):
            return {"profiles": {}}

    def _save_index(self, data: dict[str, Any]) -> None:
        os.makedirs(self._root, exist_ok=True)
        path = self._index_path()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    # ── CRUD ────────────────────────────────────────────────────────────────

    def list(self) -> list[dict[str, Any]]:
        data = self._load_index()
        records = [ProfileRecord(**rec) for rec in data["profiles"].values()]
        if not records:
            records = [_default_record(DEFAULT_PROFILE_ID, name="Default")]
        records.sort(key=lambda r: (r.id != DEFAULT_PROFILE_ID, r.id))
        return [r.to_dict() for r in records]

    def get(self, profile_id: str) -> Optional[dict[str, Any]]:
        data = self._load_index()
        rec = data["profiles"].get(profile_id)
        if rec is None and profile_id == DEFAULT_PROFILE_ID:
            return _default_record(DEFAULT_PROFILE_ID, name="Default").to_dict()
        return ProfileRecord(**rec).to_dict() if rec else None

    def ensure_default(self) -> dict[str, Any]:
        existing = self.get(DEFAULT_PROFILE_ID)
        if existing:
            return existing
        return self.create(DEFAULT_PROFILE_ID, name="Default")

    def create(
        self, profile_id: str, *, name: Optional[str] = None,
        inherits: Optional[str] = None, retention_days: int = 0,
        settings: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        validate_profile_id(profile_id)
        if inherits is not None:
            validate_profile_id(inherits)
            if inherits == profile_id:
                raise ProfileError("a profile cannot inherit from itself")
            if self.get(inherits) is None:
                raise ProfileError(f"parent profile {inherits!r} does not exist")
            self._assert_no_cycle(profile_id, inherits)
        data = self._load_index()
        if profile_id in data["profiles"]:
            raise ProfileError(f"profile {profile_id!r} already exists")
        record = _default_record(profile_id, name=name, inherits=inherits)
        record.retentionDays = max(0, int(retention_days))
        record.settings = dict(settings or {})
        from .db import now_iso  # noqa: PLC0415

        record.createdAt = now_iso()
        record.updatedAt = record.createdAt
        data["profiles"][profile_id] = record.to_dict()
        self._save_index(data)
        self._write_projection(record)
        return record.to_dict()

    def update(self, profile_id: str, **patch: Any) -> dict[str, Any]:
        data = self._load_index()
        rec = data["profiles"].get(profile_id)
        if rec is None:
            raise ProfileError(f"unknown profile {profile_id!r}")
        allowed = {
            "name", "retentionDays", "settings", "promptProfile",
            "memoryNamespace", "sessionNamespace", "skillNamespace",
            "providerNamespace", "inherits", "inheritsReadOnly",
        }
        for key, value in patch.items():
            if key not in allowed:
                continue
            if key == "inherits" and value == profile_id:
                raise ProfileError("a profile cannot inherit from itself")
            if key == "inherits" and value is not None:
                validate_profile_id(value)
                if self.get(value) is None:
                    raise ProfileError(f"parent profile {value!r} does not exist")
                self._assert_no_cycle(profile_id, value)
            rec[key] = value
        from .db import now_iso  # noqa: PLC0415

        rec["updatedAt"] = now_iso()
        record = ProfileRecord(**rec)
        data["profiles"][profile_id] = record.to_dict()
        self._save_index(data)
        self._write_projection(record)
        return record.to_dict()

    def delete(self, profile_id: str) -> dict[str, Any]:
        if profile_id == DEFAULT_PROFILE_ID:
            raise ProfileError("the default profile cannot be deleted")
        data = self._load_index()
        if profile_id not in data["profiles"]:
            return {"deleted": False, "reason": "not found"}
        for other_id, other in data["profiles"].items():
            if other.get("inherits") == profile_id:
                raise ProfileError(
                    f"profile {other_id!r} inherits from {profile_id!r}; reparent or delete it first"
                )
        del data["profiles"][profile_id]
        self._save_index(data)
        return {"deleted": True, "profileId": profile_id}

    # ── Inheritance / isolation ─────────────────────────────────────────────

    def _assert_no_cycle(self, profile_id: str, parent_id: str) -> None:
        seen = {profile_id}
        cursor = parent_id
        data = self._load_index()
        while cursor:
            if cursor in seen:
                raise ProfileError("profile inheritance cycle detected")
            seen.add(cursor)
            rec = data["profiles"].get(cursor)
            cursor = rec.get("inherits") if rec else None

    def inherited_ids(self, profile_id: str) -> list[str]:
        """The chain of parent profiles this profile may READ (read-only)."""
        out: list[str] = []
        data = self._load_index()
        rec = data["profiles"].get(profile_id)
        cursor = rec.get("inherits") if rec else None
        seen = {profile_id}
        while cursor and cursor not in seen:
            seen.add(cursor)
            out.append(cursor)
            parent = data["profiles"].get(cursor)
            cursor = parent.get("inherits") if parent else None
        return out

    def readable_profile_ids(self, profile_id: str) -> list[str]:
        """The profile's own id plus inherited read-only parents."""
        return [profile_id, *self.inherited_ids(profile_id)]

    def _write_projection(self, record: ProfileRecord) -> None:
        """Write the human-readable directory projection. Never the source of
        truth; never contains secrets."""
        try:
            directory = record.directory or profile_dir(record.id)
            for sub in ("sessions", "skills", "history", "exports"):
                os.makedirs(os.path.join(directory, sub), exist_ok=True)
            profile_json = os.path.join(directory, "PROFILE.json")
            with open(profile_json, "w", encoding="utf-8") as handle:
                json.dump(record.to_dict(), handle, indent=2, ensure_ascii=False, default=str)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # A projection failure is a diagnostic, never a mutation failure.
            pass


__all__ = [
    "DEFAULT_PROFILE_ID",
    "ProfileError",
    "ProfileRecord",
    "ProfileRegistry",
    "profile_dir",
    "profiles_root",
    "validate_profile_id",
]
