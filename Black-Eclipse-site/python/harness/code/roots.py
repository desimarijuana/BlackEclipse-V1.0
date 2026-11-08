"""Trusted workspace roots — the folder a person chooses for Eclipse to work on.

This is the opencode-style "pick a folder" foundation, built as one more
table on the runtime's OWN store (`agent-memory.db`), exactly like
`run_lineage.py` and `code/store.py`. It owns no agent loop and executes nothing;
it is a persisted, operator-approved allowlist of directories.

Why a registry and not "any path the model names": `resolve_workspace` refuses a
root it cannot justify. This module is the ONE place a new root becomes
justifiable. Approving a folder is an explicit operator act (the route is
operator-gated); afterwards every tool is still confined to that root by
`policy.resolve_within`, and `PROTECTED_PATHS` remain untouchable even inside an
approved folder. A missing/empty registry means the runtime falls back to its
own repo root — the previous behaviour — so zero-config keeps working.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso

# Bounds: a folder picker lists directories, bounded; a browse never recurses.
MAX_BROWSE_ENTRIES = 500

_TRUSTED_ROOT_DDL = """
CREATE TABLE IF NOT EXISTS TrustedRoot (
  id         TEXT PRIMARY KEY,
  path       TEXT NOT NULL UNIQUE,
  label      TEXT,
  createdAt  TEXT NOT NULL,
  lastUsedAt TEXT,
  selected   INTEGER NOT NULL DEFAULT 0
)
"""


def _normalized(path: str) -> str:
    """A stable identity for a directory: realpath, case-folded on Windows."""
    real = os.path.realpath(str(path))
    return os.path.normcase(real) if os.name == "nt" else real


def root_id(path: str) -> str:
    return "root_" + hashlib.sha256(_normalized(path).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TrustedRoot:
    id: str
    path: str
    label: Optional[str]
    created_at: str
    last_used_at: Optional[str]
    selected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "label": self.label,
            "createdAt": self.created_at,
            "lastUsedAt": self.last_used_at,
            "selected": self.selected,
        }


def _row_to_root(row: Any) -> TrustedRoot:
    return TrustedRoot(
        id=row["id"],
        path=row["path"],
        label=row["label"],
        created_at=row["createdAt"],
        last_used_at=row["lastUsedAt"],
        selected=bool(row["selected"]),
    )


class TrustedRootStore:
    """Trusted roots over the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(_TRUSTED_ROOT_DDL)
        self._db.commit()

    # ── Writes ───────────────────────────────────────────────────────────────
    def approve(self, path: str, label: Optional[str] = None) -> TrustedRoot:
        """Approve a directory as a workspace root. Idempotent by realpath.

        Raises ValueError when the path is not an existing directory — a root
        that cannot be worked on is refused at approval, never stored and then
        failed later.
        """
        candidate = Path(os.path.realpath(str(path)))
        if not candidate.is_dir():
            raise ValueError("That location is not a folder Eclipse can open.")
        identity = _normalized(str(candidate))
        existing = self._db.execute(
            "SELECT * FROM TrustedRoot WHERE path=?", (str(candidate),)
        ).fetchone()
        if existing is not None:
            if label is not None:
                self._db.execute("UPDATE TrustedRoot SET label=? WHERE id=?", (label, existing["id"]))
                self._db.commit()
                existing = self._db.execute("SELECT * FROM TrustedRoot WHERE id=?", (existing["id"],)).fetchone()
            return _row_to_root(existing)
        record = {
            "id": root_id(str(candidate)),
            "path": str(candidate),
            "label": label or candidate.name or str(candidate),
            "created_at": now_iso(),
            "last_used_at": None,
            "selected": 0,
        }
        self._db.execute(
            "INSERT OR REPLACE INTO TrustedRoot (id, path, label, createdAt, lastUsedAt, selected)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (record["id"], record["path"], record["label"], record["created_at"],
             record["last_used_at"], record["selected"]),
        )
        self._db.commit()
        return TrustedRoot(**record)

    def select(self, root_id_value: str) -> Optional[TrustedRoot]:
        """Mark one root selected (exactly one at a time). None when unknown."""
        row = self._db.execute("SELECT * FROM TrustedRoot WHERE id=?", (root_id_value,)).fetchone()
        if row is None:
            return None
        self._db.execute("UPDATE TrustedRoot SET selected=0")
        self._db.execute(
            "UPDATE TrustedRoot SET selected=1, lastUsedAt=? WHERE id=?",
            (now_iso(), root_id_value),
        )
        self._db.commit()
        return _row_to_root(self._db.execute("SELECT * FROM TrustedRoot WHERE id=?", (root_id_value,)).fetchone())

    def clear_selection(self) -> None:
        self._db.execute("UPDATE TrustedRoot SET selected=0")
        self._db.commit()

    def revoke(self, root_id_value: str) -> bool:
        cursor = self._db.execute("DELETE FROM TrustedRoot WHERE id=?", (root_id_value,))
        self._db.commit()
        return cursor.rowcount > 0

    # ── Reads ────────────────────────────────────────────────────────────────
    def list(self) -> list[TrustedRoot]:
        rows = self._db.execute(
            "SELECT * FROM TrustedRoot ORDER BY selected DESC, createdAt ASC"
        ).fetchall()
        return [_row_to_root(r) for r in rows]

    def get(self, root_id_value: str) -> Optional[TrustedRoot]:
        row = self._db.execute("SELECT * FROM TrustedRoot WHERE id=?", (root_id_value,)).fetchone()
        return _row_to_root(row) if row else None

    def selected(self) -> Optional[TrustedRoot]:
        row = self._db.execute(
            "SELECT * FROM TrustedRoot WHERE selected=1 ORDER BY lastUsedAt DESC LIMIT 1"
        ).fetchone()
        return _row_to_root(row) if row else None

    def is_trusted(self, path: str) -> bool:
        """Whether `path` is exactly an approved root (realpath-compared)."""
        if not path:
            return False
        row = self._db.execute(
            "SELECT 1 FROM TrustedRoot WHERE path=?", (str(Path(os.path.realpath(str(path)))),)
        ).fetchone()
        return row is not None


def browse(path: Optional[str]) -> dict[str, Any]:
    """A bounded directory listing for the folder picker.

    Read-only. With no path, returns the filesystem roots (drives on Windows,
    `/` on POSIX). Entries are the DIRECT children only (no recursion); hidden
    entries are included but flagged, so a picker can show them. A path that is
    not a directory returns an empty listing with an honest reason — never a
    guessed value.
    """
    if not path:
        roots = _drive_roots()
        return {"path": None, "parent": None, "entries": roots, "truncated": False, "reason": None}
    try:
        target = Path(os.path.realpath(str(path)))
    except (OSError, ValueError):
        return {"path": str(path), "parent": None, "entries": [], "truncated": False,
                "reason": "That location could not be opened."}
    if not target.is_dir():
        return {"path": str(target), "parent": _parent_of(target), "entries": [],
                "truncated": False, "reason": "That location is not a folder."}
    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            if len(entries) >= MAX_BROWSE_ENTRIES:
                truncated = True
                break
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            entries.append({
                "name": child.name,
                "path": str(child),
                "isDir": is_dir,
                "hidden": child.name.startswith("."),
            })
    except (OSError, PermissionError):
        return {"path": str(target), "parent": _parent_of(target), "entries": [],
                "truncated": False, "reason": "That folder could not be read."}
    return {"path": str(target), "parent": _parent_of(target), "entries": entries,
            "truncated": truncated, "reason": None}


def create_folder(parent: Optional[str], name: str) -> dict[str, Any]:
    """Create ONE folder directly under `parent` for the picker.

    A deliberate operator act (the route is operator-gated). `name` is a single
    leaf, never a path: separators, `.` and `..` are refused, so the picker can
    make a folder in the directory it is showing and nothing above it. An empty
    `parent` means the drive list, which has no writable location.
    """
    leaf = str(name or "").strip()
    if not leaf or leaf in (".", "..") or "/" in leaf or "\\" in leaf:
        raise ValueError("Enter a folder name without a path.")
    if len(leaf) > 128:
        raise ValueError("That folder name is too long.")
    if not parent:
        raise ValueError("Choose a drive or folder first.")
    try:
        base = Path(os.path.realpath(str(parent)))
    except (OSError, ValueError) as exc:
        raise ValueError("That location could not be opened.") from exc
    if not base.is_dir():
        raise ValueError("That location is not a folder.")
    target = base / leaf
    try:
        target.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"That folder could not be created: {exc}") from exc
    if not target.is_dir():
        raise ValueError("A file with that name already exists.")
    return {"path": str(target), "name": target.name, "parent": str(base)}


def _parent_of(path: Path) -> Optional[str]:
    parent = path.parent
    if str(parent) == str(path):
        return None
    return str(parent)


def _drive_roots() -> list[dict[str, Any]]:
    if os.name != "nt":
        return [{"name": "/", "path": "/", "isDir": True, "hidden": False}]
    roots: list[dict[str, Any]] = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        base = f"{letter}:\\"
        if os.path.isdir(base):
            roots.append({"name": base, "path": base, "isDir": True, "hidden": False})
    return roots


__all__ = [
    "MAX_BROWSE_ENTRIES",
    "TrustedRoot",
    "TrustedRootStore",
    "browse",
    "create_folder",
    "root_id",
]
