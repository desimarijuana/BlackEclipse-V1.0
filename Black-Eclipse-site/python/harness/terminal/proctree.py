"""OS-level parent/child lookup, so a shell-wrapped process's tree is real.

A managed process is often a shell (PowerShell/CMD) whose actual work — a Node
server, a compiler — runs as a CHILD. `taskkill /T` already walks the tree to kill
it, but to report the tree (and to attribute a listening port to the process the
agent started) we need the OS's own parent map. This module reads it directly:

  * **Windows** — `CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS)`, a fast,
    dependency-free snapshot of every process's parent id.
  * **POSIX** — `/proc/<pid>/stat` (field 4 = ppid), falling back to `ps`.

Nothing is inferred: a process whose parent is unknown is simply not linked. All
functions are best-effort and never raise.
"""

from __future__ import annotations

import os
from typing import Optional


def _parent_map_windows() -> dict[int, int]:  # pragma: no cover - Windows
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return {}
    mapping: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                mapping[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return mapping


def _parent_map_posix() -> dict[int, int]:
    mapping: dict[int, int] = {}
    proc = "/proc"
    if not os.path.isdir(proc):
        return mapping
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc, name, "stat"), encoding="utf-8", errors="replace") as handle:
                data = handle.read()
        except OSError:
            continue
        # `pid (comm) state ppid ...` — comm may contain spaces/parens, so split
        # after the LAST ')'.
        close = data.rfind(")")
        if close < 0:
            continue
        fields = data[close + 1:].split()
        if len(fields) >= 2:
            try:
                mapping[int(name)] = int(fields[1])
            except ValueError:
                continue
    return mapping


def parent_map() -> dict[int, int]:
    """Every process's parent id, from the OS. Empty when unavailable."""
    try:
        if os.name == "nt":
            return _parent_map_windows()
        return _parent_map_posix()
    except Exception:  # noqa: BLE001 - a missing snapshot is an honest empty map
        return {}


def descendants(pid: Optional[int], *, max_depth: int = 6) -> list[int]:
    """Every descendant pid of ``pid`` (depth-first, bounded). Never includes pid."""
    if not pid:
        return []
    mapping = parent_map()
    if not mapping:
        return []
    children: dict[int, list[int]] = {}
    for child, parent in mapping.items():
        children.setdefault(parent, []).append(child)
    out: list[int] = []
    frontier = [int(pid)]
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[int] = []
        for current in frontier:
            for child in children.get(current, []):
                out.append(child)
                nxt.append(child)
        frontier = nxt
        depth += 1
    return out


def process_map() -> dict[int, tuple[int, str]]:
    """``{pid: (ppid, image_name)}`` for every process, from the OS.

    Used where a caller needs to know WHICH process a pid is (e.g. "are any
    python processes still descendants of me?"), not just the parent links.
    Empty when the snapshot is unavailable.
    """
    try:
        if os.name == "nt":
            return _process_map_windows()
        return _process_map_posix()
    except Exception:  # noqa: BLE001
        return {}


def _process_map_windows() -> dict[int, tuple[int, str]]:  # pragma: no cover - Windows
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return {}
    out: dict[int, tuple[int, str]] = {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                name = entry.szExeFile.decode("utf-8", "replace")
                out[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), name)
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return out


def _process_map_posix() -> dict[int, tuple[int, str]]:
    out: dict[int, tuple[int, str]] = {}
    proc = "/proc"
    if not os.path.isdir(proc):
        return out
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc, name, "stat"), encoding="utf-8", errors="replace") as handle:
                data = handle.read()
        except OSError:
            continue
        close = data.rfind(")")
        if close < 0:
            continue
        comm = data[data.find("(") + 1:close]
        fields = data[close + 1:].split()
        if len(fields) >= 2:
            try:
                out[int(name)] = (int(fields[1]), comm)
            except ValueError:
                continue
    return out


def descendant_pids_matching(pid: Optional[int], name_substring: str) -> list[int]:
    """Descendants of ``pid`` whose image name contains ``name_substring``.

    A precise orphan check: "did MY child of this kind survive?" rather than a
    machine-wide process count that another test could perturb.
    """
    if not pid:
        return []
    mapping = process_map()
    if not mapping:
        return []
    want = name_substring.casefold()
    matches = {p for p, (_ppid, name) in mapping.items() if want in name.casefold()}
    return [p for p in descendants(pid) if p in matches]


__all__ = ["descendant_pids_matching", "descendants", "parent_map", "process_map"]
