"""Transactions and rollback — multi-file changes are all-or-nothing.

A `FileTransaction` captures the original bytes (and mode) of every path it is
about to touch BEFORE the first write. If any operation fails, `rollback()`
restores every captured path exactly. On success `commit()` discards the
snapshots.

The snapshot is in-memory byte data, independent of Git: filesystem safety must
NOT depend on Git being installed. Git-awareness is an additive convenience,
never the safety mechanism.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from . import errors as err
from .resolver import relative


MAX_SNAPSHOT_FILES = 5_000


@dataclass(frozen=True)
class Snapshot:
    path: Path
    existed: bool
    data: Optional[bytes]
    mode: Optional[int]
    is_dir: bool = False
    children: tuple["Snapshot", ...] = ()

    @property
    def size(self) -> int:
        return len(self.data) if self.data is not None else 0


def capture(path: Path, *, _budget: Optional[list[int]] = None) -> Snapshot:
    """Read the current state of `path` (a file, a symlink, or a whole tree).

    A directory is captured recursively so a recursive delete can be rolled back.
    The recursion is bounded (`MAX_SNAPSHOT_FILES`); past the bound a
    `TRANSACTION_FAILED` is raised rather than a partial snapshot used as if complete.
    """
    budget = _budget if _budget is not None else [MAX_SNAPSHOT_FILES]
    try:
        if path.is_symlink():
            target = os.readlink(path)
            return Snapshot(path=path, existed=True, data=("LINK:" + target).encode("utf-8"), mode=None)
        if not path.exists():
            return Snapshot(path=path, existed=False, data=None, mode=None)
        if path.is_dir():
            children: list[Snapshot] = []
            for child in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
                budget[0] -= 1
                if budget[0] < 0:
                    raise err.FsError(err.TRANSACTION_FAILED, "This change touches too many files to make at once.")
                children.append(capture(child, _budget=budget))
            return Snapshot(path=path, existed=True, data=None, mode=None, is_dir=True, children=tuple(children))
        stat = path.stat()
        with open(path, "rb") as handle:
            data = handle.read()
        return Snapshot(path=path, existed=True, data=data, mode=stat.st_mode)
    except err.FsError:
        raise
    except OSError as exc:
        raise err.FsError(err.PERMISSION_DENIED, "A file couldn't be prepared for the change.", path=str(path)) from exc


def restore(snapshot: Snapshot) -> None:
    """Restore one snapshot exactly (bytes for a file, removal for a new path)."""
    path = snapshot.path
    try:
        if snapshot.is_dir:
            path.mkdir(parents=True, exist_ok=True)
            for child in snapshot.children:
                restore(child)
            return
        if not snapshot.existed:
            if path.exists() or path.is_symlink():
                if path.is_dir() and not path.is_symlink():
                    import shutil

                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.data is not None and snapshot.data.startswith(b"LINK:"):
            target = snapshot.data[len(b"LINK:"):].decode("utf-8")
            if path.exists() or path.is_symlink():
                path.unlink()
            try:
                os.symlink(target, path)
            except OSError:
                pass
            return
        tmp = path.with_name(f".{path.name}.{os.getpid()}.restore.tmp")
        with open(tmp, "wb") as handle:
            handle.write(snapshot.data or b"")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if snapshot.mode is not None and os.name == "posix":
            try:
                os.chmod(path, snapshot.mode)
            except OSError:
                pass
    except OSError as exc:
        raise err.FsError(err.ROLLBACK_FAILED, "A change couldn't be undone cleanly.", path=str(path)) from exc


class FileTransaction:
    """A bounded, reversible set of file mutations.

    Usage:
        txn = FileTransaction(ws)
        txn.backup(path)     # before mutating
        ...write...
        txn.commit()         # or txn.rollback() on failure
    """

    MAX_SNAPSHOTS = 200

    def __init__(self, ws: object) -> None:
        self.ws = ws
        self._snapshots: dict[str, Snapshot] = {}
        self._order: list[str] = []
        self._closed = False

    def backup(self, path: Path) -> None:
        key = os.path.realpath(str(path))
        if key in self._snapshots:
            return
        if len(self._snapshots) >= self.MAX_SNAPSHOTS:
            raise err.FsError(
                err.TRANSACTION_FAILED,
                "This change touches too many files to make at once.",
            )
        self._snapshots[key] = capture(path)
        self._order.append(key)

    def rollback(self) -> list[str]:
        """Restore every captured path, newest first. Returns restored rel paths."""
        restored: list[str] = []
        for key in reversed(self._order):
            snapshot = self._snapshots[key]
            restore(snapshot)
            restored.append(relative(self.ws, snapshot.path))
        self._closed = True
        return restored

    def commit(self) -> None:
        self._snapshots.clear()
        self._order.clear()
        self._closed = True

    def __enter__(self) -> "FileTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and not self._closed:
            try:
                self.rollback()
            except err.FsError:
                pass
        return False


def snapshot_paths(ws: object, paths: Iterable[Path]) -> list[Snapshot]:
    return [capture(p) for p in paths]


def restore_snapshots(snapshots: Iterable[Snapshot]) -> list[str]:
    restored = []
    for snapshot in reversed(list(snapshots)):
        restore(snapshot)
        restored.append(str(snapshot.path))
    return restored


__all__ = [
    "FileTransaction",
    "Snapshot",
    "capture",
    "restore",
    "restore_snapshots",
    "snapshot_paths",
]
