"""Persistent browser profiles.

A profile is a named, on-disk Chromium user-data directory holding cookies,
local/session storage, IndexedDB and preferences, so a signed-in research or
finance session survives across runs. Profiles are directories under
``artifacts_root/profiles``; this module owns their lifecycle and confinement.

Never expose credentials directly: a profile may hold authentication STATE, and
the metadata here is content-free. A profile id is validated against a strict
pattern so it can never escape the profiles directory.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# A profile name is a single path segment; no separators, no dots-only.
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")

RESERVED_PROFILES = ("default",)


class ProfileError(ValueError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class ProfileInfo:
    id: str
    path: str
    exists: bool
    persistent: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "exists": self.exists,
            "persistent": self.persistent,
            "createdAt": self.created_at,
        }


class ProfileManager:
    """Names, creates and resolves persistent profiles under one confined root."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _validate(self, profile_id: str) -> str:
        text = (profile_id or "").strip()
        if not _PROFILE_ID_RE.match(text):
            raise ProfileError(
                "INVALID_PROFILE",
                "That profile name isn't allowed (use letters, numbers, dot, dash, underscore).",
            )
        return text

    def _path(self, profile_id: str) -> Path:
        return self._root / profile_id

    def resolve(self, profile_id: Optional[str]) -> Optional[Path]:
        """The user-data dir for a profile, or None for an ephemeral (no) profile."""
        if not profile_id:
            return None
        return self._path(self._validate(profile_id))

    def ensure(self, profile_id: str) -> Path:
        """Create the profile directory if absent and return its path."""
        safe = self._validate(profile_id)
        path = self._path(safe)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def info(self, profile_id: str) -> ProfileInfo:
        safe = self._validate(profile_id)
        path = self._path(safe)
        return ProfileInfo(id=safe, path=str(path), exists=path.is_dir())

    def list_profiles(self) -> list[dict[str, Any]]:
        if not self._root.is_dir():
            return []
        found: list[dict[str, Any]] = []
        for child in sorted(self._root.iterdir()):
            if child.is_dir() and _PROFILE_ID_RE.match(child.name):
                found.append(ProfileInfo(id=child.name, path=str(child), exists=True).to_dict())
        return found

    def create(self, profile_id: str) -> ProfileInfo:
        path = self.ensure(profile_id)
        return ProfileInfo(id=profile_id, path=str(path), exists=True)

    def delete(self, profile_id: str) -> bool:
        safe = self._validate(profile_id)
        path = self._path(safe)
        # Confinement: only ever remove a direct child of the root.
        if path.parent != self._root or not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return not path.exists()


__all__ = ["ProfileError", "ProfileInfo", "ProfileManager", "RESERVED_PROFILES"]
