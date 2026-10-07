"""A per-repository advisory lock for mutating Git operations.

Git itself prevents a concurrent `index.lock`, but that is a race: two agent runs
(or the terminal and the Git tools) can both decide to merge. This module adds a
best-effort, cross-process lock keyed by the repository root, so a mutating
operation is serialized per repository within a process AND across processes.

Design:

  * In-process it is a `threading.Lock` per repository root.
  * Across processes it is an OS file lock on `<git_dir>/eclipse-git.lock`:
    `msvcrt.locking` on Windows, `fcntl.flock` on POSIX. When neither is
    available the file lock degrades to a best-effort exclusive create with a
    TTL; the in-process lock still applies.
  * Reads NEVER take the lock. Only a mutating operation does.

`locked(repo)` is a context manager. On contention it raises `GitError` with
`LOCKED_REPOSITORY` rather than blocking forever — a bounded `wait_s` is honored.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import errors
from .errors import GitError

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _inproc_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


# ── OS file lock ──────────────────────────────────────────────────────────────

class _FileLock:
    """An exclusive advisory lock on a lock file, or None when unsupported."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None
        self._kind = "none"

    def acquire(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Open without truncating: the file is a token, not content.
            self._fh = open(self.path, "a+b")
        except OSError:
            return False
        if os.name == "nt":
            try:
                import msvcrt  # noqa: PLC0415

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                self._kind = "msvcrt"
                return True
            except OSError:
                self._close()
                return False
        else:
            try:
                import fcntl  # noqa: PLC0415

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._kind = "flock"
                return True
            except OSError:
                self._close()
                return False

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if self._kind == "msvcrt":
                import msvcrt  # noqa: PLC0415

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            elif self._kind == "flock":
                import fcntl  # noqa: PLC0415

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._close()

    def _close(self) -> None:
        try:
            if self._fh is not None:
                self._fh.close()
        except OSError:
            pass
        self._fh = None


LOCK_FILENAME = "eclipse-git.lock"


@contextmanager
def locked(lock_dir: Path, *, wait_s: float = 30.0) -> Iterator[None]:
    """Hold the per-repository mutating lock, or raise `LOCKED_REPOSITORY`.

    `lock_dir` is the repository's git dir (a directory even for a linked
    worktree). The in-process lock is acquired first (bounded by `wait_s`); then
    the OS file lock is attempted with a short bounded spin. A contended lock is a
    structured refusal, never an indefinite block.
    """
    key = os.path.realpath(str(lock_dir))
    lock = _inproc_lock(key)
    if not lock.acquire(timeout=max(0.1, wait_s)):
        raise GitError(errors.LOCKED_REPOSITORY, "The project is busy with another action.")
    file_lock: Optional[_FileLock] = None
    try:
        lock_path = Path(key) / LOCK_FILENAME
        file_lock = _FileLock(lock_path)
        deadline = time.monotonic() + max(0.1, wait_s)
        while not file_lock.acquire():
            if time.monotonic() > deadline:
                raise GitError(errors.LOCKED_REPOSITORY, "The project is busy with another action.")
            time.sleep(0.05)
        yield
    finally:
        if file_lock is not None:
            file_lock.release()
        lock.release()


__all__ = ["LOCK_FILENAME", "locked"]
