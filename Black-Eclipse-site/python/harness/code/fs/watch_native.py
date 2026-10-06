"""Native OS filesystem watch backends — Windows `ReadDirectoryChangesW` and
Linux `inotify`, with everything behind one small interface.

The subsystem must work with NO third-party dependency (zero-config), so the
native backends use `ctypes` only, and `watch.py` falls back to a portable
polling watch whenever a native primitive is unavailable or errors. A backend
never raises into the caller: `create_native_watcher` returns None to mean
"use polling", and a backend that fails mid-run stops quietly.

Each backend owns ONE background thread that collects raw `(kind, path,
old_path)` tuples into a bounded queue. `drain()` empties it. `watch.py` does the
debounce/normalize/index-invalidate step, so all policy lives in one place.
"""

from __future__ import annotations

import os
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any, Optional

# Raw kinds, matching the normalized vocabulary in `watch.py`.
CREATED = "created"
MODIFIED = "modified"
DELETED = "deleted"
RENAMED = "renamed"

MAX_QUEUE = 20_000
WATCH_POLL_TIMEOUT_MS = 250
_READ_BUFFER_BYTES = 64 * 1024


class NativeWatchBase:
    """One directory-tree watcher. `drain()` yields `(kind, path, old_path)`."""

    name = "native"
    recursive = True

    def __init__(self, targets: list[Path], *, recursive: bool) -> None:
        self.targets = list(targets)
        self.recursive = recursive
        self._queue: deque[tuple[str, str, Optional[str]]] = deque(maxlen=MAX_QUEUE)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._failed = False

    # ── public ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        try:
            self._open()
        except Exception:  # noqa: BLE001 - no primitive ⇒ caller uses polling
            self._failed = True
            raise
        self._thread = threading.Thread(target=self._run, name=f"eclipse-watch-{self.name}", daemon=True)
        self._thread.start()

    def drain(self) -> list[tuple[str, str, Optional[str]]]:
        with self._lock:
            items = list(self._queue)
            self._queue.clear()
        return items

    def stop(self) -> None:
        self._stop.set()
        try:
            self._close()
        except Exception:  # noqa: BLE001
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def healthy(self) -> bool:
        return not self._failed

    # ── overridable ─────────────────────────────────────────────────────────
    def _open(self) -> None:
        raise NotImplementedError

    def _close(self) -> None:
        pass

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._pump_once()
        except Exception:  # noqa: BLE001 - a watch must never crash the process
            self._failed = True

    def _pump_once(self) -> None:
        raise NotImplementedError

    def _emit(self, kind: str, path: str, old_path: Optional[str] = None) -> None:
        with self._lock:
            self._queue.append((kind, path, old_path))


# ── Windows: ReadDirectoryChangesW ───────────────────────────────────────────


class WindowsDirectoryWatcher(NativeWatchBase):
    name = "windows-rdcw"

    FILE_LIST_DIRECTORY = 0x0001
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OVERLAPPED = 0x40000000
    FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
    FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
    FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
    FILE_NOTIFY_CHANGE_SIZE = 0x00000008
    ERROR_IO_PENDING = 997
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    INVALID_HANDLE_VALUE = -1

    ACTION_ADDED = 1
    ACTION_REMOVED = 2
    ACTION_MODIFIED = 3
    ACTION_RENAMED_OLD_NAME = 4
    ACTION_RENAMED_NEW_NAME = 5

    def _open(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handles: list[tuple[Any, Any, Any, Path, bool]] = []

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        self._overlapped_type = OVERLAPPED
        self._handles: list[dict[str, Any]] = []
        for target in self.targets:
            is_file = target.is_file()
            directory = target.parent if is_file else target
            if not directory.is_dir():
                continue
            # A single-file target watches its parent non-recursively and filters
            # to that one name, so a sibling's change is never reported.
            file_filter = target.name if is_file else None
            handle = self._kernel32.CreateFileW(
                str(directory),
                self.FILE_LIST_DIRECTORY,
                self.FILE_SHARE_READ | self.FILE_SHARE_WRITE | self.FILE_SHARE_DELETE,
                None,
                self.OPEN_EXISTING,
                self.FILE_FLAG_BACKUP_SEMANTICS | self.FILE_FLAG_OVERLAPPED,
                None,
            )
            if handle == self.INVALID_HANDLE_VALUE or handle is None:
                continue
            event = self._kernel32.CreateEventW(None, True, False, None)
            if not event:
                self._kernel32.CloseHandle(handle)
                continue
            overlapped = OVERLAPPED()
            overlapped.hEvent = event
            self._handles.append({
                "handle": handle, "event": event, "overlapped": overlapped,
                "directory": directory, "filter": file_filter, "buffer": None,
                "armed": False,
            })

    def _close(self) -> None:
        for entry in getattr(self, "_handles", []):
            if entry["armed"]:
                try:
                    self._kernel32.CancelIoEx(entry["handle"], self._ctypes.byref(entry["overlapped"]))
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._kernel32.SetEvent(entry["event"])
                except Exception:  # noqa: BLE001
                    pass
        for entry in getattr(self, "_handles", []):
            try:
                self._kernel32.CloseHandle(entry["event"])
            except Exception:  # noqa: BLE001
                pass
            try:
                self._kernel32.CloseHandle(entry["handle"])
            except Exception:  # noqa: BLE001
                pass
        self._handles = []

    def _arm(self, entry: dict[str, Any]) -> None:
        ctypes = self._ctypes
        flags = (
            self.FILE_NOTIFY_CHANGE_FILE_NAME
            | self.FILE_NOTIFY_CHANGE_DIR_NAME
            | self.FILE_NOTIFY_CHANGE_LAST_WRITE
            | self.FILE_NOTIFY_CHANGE_SIZE
        )
        entry["buffer"] = ctypes.create_string_buffer(_READ_BUFFER_BYTES)
        entry["overlapped"] = self._overlapped_type()
        entry["overlapped"].hEvent = entry["event"]
        ctypes.set_last_error(0)
        ok = self._kernel32.ReadDirectoryChangesW(
            entry["handle"], entry["buffer"], _READ_BUFFER_BYTES,
            1 if self.recursive else 0, flags, None,
            ctypes.byref(entry["overlapped"]), None,
        )
        entry["armed"] = bool(ok) or ctypes.get_last_error() == self.ERROR_IO_PENDING

    def _pump_once(self) -> None:
        ctypes = self._ctypes
        for entry in self._handles:
            if not entry["armed"]:
                self._arm(entry)
                if not entry["armed"]:
                    continue
            wait = self._kernel32.WaitForSingleObject(entry["event"], WATCH_POLL_TIMEOUT_MS)
            if wait == self.WAIT_TIMEOUT:
                # Keep the pending read armed: cancelling here would DISCARD the
                # changes the OS has already buffered on the handle.
                continue
            if wait != self.WAIT_OBJECT_0:
                continue
            bytes_read = ctypes.c_ulong(0)
            if not self._kernel32.GetOverlappedResult(
                entry["handle"], ctypes.byref(entry["overlapped"]), ctypes.byref(bytes_read), False,
            ):
                entry["armed"] = False
                continue
            raw = entry["buffer"].raw[: bytes_read.value] if entry["buffer"] is not None else b""
            entry["armed"] = False
            if raw:
                self._parse(raw, entry["directory"], entry["filter"])
            self._arm(entry)

    def _parse(self, raw: bytes, directory: Path, file_filter: Optional[str]) -> None:
        offset = 0
        pending_old: Optional[str] = None
        while offset + 12 <= len(raw):
            next_offset = int.from_bytes(raw[offset:offset + 4], "little")
            action = int.from_bytes(raw[offset + 4:offset + 8], "little")
            name_len = int.from_bytes(raw[offset + 8:offset + 12], "little")
            name = raw[offset + 12:offset + 12 + name_len].decode("utf-16-le", "replace")
            if file_filter is None or Path(name).name == file_filter:
                rel = str(directory / name)
                if action == self.ACTION_ADDED:
                    self._emit(CREATED, rel)
                elif action == self.ACTION_REMOVED:
                    self._emit(DELETED, rel)
                elif action == self.ACTION_MODIFIED:
                    self._emit(MODIFIED, rel)
                elif action == self.ACTION_RENAMED_OLD_NAME:
                    pending_old = rel
                elif action == self.ACTION_RENAMED_NEW_NAME:
                    self._emit(RENAMED, rel, pending_old)
                    pending_old = None
            if not next_offset:
                break
            offset += next_offset


# ── Linux: inotify ────────────────────────────────────────────────────────────


class LinuxInotifyWatcher(NativeWatchBase):
    name = "linux-inotify"

    IN_NONBLOCK = 0x800
    IN_CLOEXEC = 0x80000
    IN_MODIFY = 0x00000002
    IN_CLOSE_WRITE = 0x00000008
    IN_MOVED_FROM = 0x00000040
    IN_MOVED_TO = 0x00000080
    IN_CREATE = 0x00000100
    IN_DELETE = 0x00000200
    IN_DELETE_SELF = 0x00000400
    IN_MOVE_SELF = 0x00000800
    IN_ISDIR = 0x40000000

    def _open(self) -> None:
        import ctypes
        import ctypes.util

        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        self._ctypes = ctypes
        self._libc = ctypes.CDLL(libc_name, use_errno=True)
        self._fd = self._libc.inotify_init1(self.IN_NONBLOCK | self.IN_CLOEXEC)
        if self._fd < 0:
            raise OSError("inotify_init1 failed")
        self._wd_to_dir: dict[int, Path] = {}
        self._add_tree(self.targets, self.recursive)

    def _mask(self) -> int:
        return (
            self.IN_MODIFY | self.IN_CLOSE_WRITE | self.IN_MOVED_FROM
            | self.IN_MOVED_TO | self.IN_CREATE | self.IN_DELETE
            | self.IN_DELETE_SELF | self.IN_MOVE_SELF
        )

    def _add_watch(self, directory: Path) -> None:
        wd = self._libc.inotify_add_watch(
            self._fd, str(directory).encode("utf-8"), self._mask(),
        )
        if wd >= 0:
            self._wd_to_dir[wd] = directory

    def _add_tree(self, targets: list[Path], recursive: bool, *, initial: bool = False) -> None:
        for target in targets:
            directory = target.parent if target.is_file() else target
            if not directory.is_dir():
                continue
            self._add_watch(directory)
            if recursive:
                for dirpath, dirnames, _files in os.walk(directory, followlinks=False):
                    for name in dirnames:
                        self._add_watch(Path(dirpath) / name)

    def _close(self) -> None:
        fd = getattr(self, "_fd", -1)
        if fd is not None and fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fd = -1

    def _pump_once(self) -> None:
        import select

        fd = getattr(self, "_fd", -1)
        if fd is None or fd < 0:
            return
        ready, _w, _x = select.select([fd], [], [], WATCH_POLL_TIMEOUT_MS / 1000.0)
        if not ready:
            return
        try:
            data = os.read(fd, _READ_BUFFER_BYTES)
        except BlockingIOError:
            return
        except OSError:
            self._close()
            return
        self._parse(data)

    def _parse(self, data: bytes) -> None:
        offset = 0
        moved: dict[int, tuple[str, int]] = {}  # cookie → (path, wd)
        while offset + 16 <= len(data):
            wd = int.from_bytes(data[offset:offset + 4], "little", signed=True)
            mask = int.from_bytes(data[offset + 4:offset + 8], "little")
            cookie = int.from_bytes(data[offset + 8:offset + 12], "little")
            name_len = int.from_bytes(data[offset + 12:offset + 16], "little")
            name_bytes = data[offset + 16:offset + 16 + name_len]
            name = name_bytes.split(b"\x00", 1)[0].decode("utf-8", "replace")
            offset += 16 + name_len
            directory = self._wd_to_dir.get(wd)
            if directory is None:
                continue
            is_dir = bool(mask & self.IN_ISDIR)
            full = str(directory / name) if name else str(directory)
            if mask & (self.IN_MOVED_FROM | self.IN_MOVED_TO) and cookie:
                if mask & self.IN_MOVED_FROM:
                    moved[cookie] = (full, wd)
                    continue
                old = moved.pop(cookie, None)
                if old is not None:
                    self._emit(RENAMED, full, old[0])
                else:
                    self._emit(CREATED, full)
                if is_dir and self.recursive:
                    self._add_watch(Path(full))
                continue
            if mask & self.IN_CREATE:
                self._emit(CREATED, full)
                if is_dir and self.recursive:
                    self._add_watch(Path(full))
            elif mask & (self.IN_MODIFY | self.IN_CLOSE_WRITE):
                self._emit(MODIFIED, full)
            elif mask & self.IN_DELETE:
                self._emit(DELETED, full)
            elif mask & (self.IN_DELETE_SELF | self.IN_MOVE_SELF):
                self._emit(DELETED, str(directory))


# ── backend selection ────────────────────────────────────────────────────────


def native_backend_name() -> str:
    """The native primitive this host would use, or "polling"."""
    if sys.platform == "win32":
        return "windows-rdcw"
    if sys.platform.startswith("linux"):
        return "linux-inotify"
    return "polling"


def create_native_watcher(targets: list[Path], *, recursive: bool) -> Optional[NativeWatchBase]:
    """A native watcher, or None when this host has no usable primitive."""
    try:
        if sys.platform == "win32":
            return WindowsDirectoryWatcher(targets, recursive=recursive)
        if sys.platform.startswith("linux"):
            return LinuxInotifyWatcher(targets, recursive=recursive)
    except Exception:  # noqa: BLE001 - fall back to polling
        return None
    return None


__all__ = [
    "CREATED",
    "DELETED",
    "MODIFIED",
    "NativeWatchBase",
    "RENAMED",
    "LinuxInotifyWatcher",
    "WindowsDirectoryWatcher",
    "create_native_watcher",
    "native_backend_name",
]
