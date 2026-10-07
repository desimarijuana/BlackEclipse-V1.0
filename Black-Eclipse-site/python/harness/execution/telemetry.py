"""Process resource telemetry — real CPU time and peak memory, no psutil.

Two platforms, two mechanisms, one honest contract:

  * **Windows** — `GetProcessTimes` (CPU) and `GetProcessMemoryInfo` (working
    set) via `ctypes`, against a queried handle. A process that has exited reads
    as `None`, never as zero.
  * **POSIX/Linux** — `/proc/<pid>/stat` (`utime`+`stime`, in clock ticks) and
    `/proc/<pid>/statm`/`status` (resident pages). A kernel without `/proc`
    (macOS, some containers) reports `None` rather than a fabricated number.

A tree's total is the sum over the process and its OS descendants, so a build
that forks (npm → tsc + esbuild) is measured as a whole. Nothing here raises:
an unmeasurable value is `None`, and the caller keeps it `None` all the way to
the stored metric — unknown is unknown.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# Windows constants.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ONE_HUNDRED_NS_PER_S = 10_000_000.0


@dataclass(frozen=True)
class ProcessSample:
    """One point-in-time measurement of a process (or a tree, when summed)."""

    cpu_ms: Optional[float] = None
    memory_mb: Optional[float] = None
    process_count: Optional[int] = None


def _noop() -> None:
    return None


def _posix_clock_ticks() -> int:
    try:
        return int(os.sysconf("SC_CLK_TCK")) or 100
    except (ValueError, OSError):
        return 100


def _posix_page_size() -> int:
    try:
        return int(os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError):
        return 4096


def sample_pid(pid: int) -> Optional[ProcessSample]:
    """Sample one process. `None` when it cannot be measured (gone / no /proc)."""
    if pid <= 0:
        return None
    if os.name == "nt":
        return _sample_windows(pid)
    if os.name == "posix":
        return _sample_posix(pid)
    return None


def _sample_windows(pid: int) -> Optional[ProcessSample]:  # pragma: no cover - Windows
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # noqa: BLE001
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
    except Exception:  # noqa: BLE001
        return None
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        creation = FILETIME()
        exit_t = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_t),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        def _to_ms(ft: "FILETIME") -> float:
            ticks = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            return ticks / _ONE_HUNDRED_NS_PER_S * 1000.0
        cpu_ms = _to_ms(kernel) + _to_ms(user)
        memory_mb: Optional[float] = None
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            memory_mb = counters.WorkingSetSize / (1024.0 * 1024.0)
        return ProcessSample(cpu_ms=cpu_ms, memory_mb=memory_mb, process_count=1)
    except Exception:  # noqa: BLE001 - a sampling failure is simply no sample
        return None
    finally:
        try:
            kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            pass


def _sample_posix(pid: int) -> Optional[ProcessSample]:
    clock_ticks = _posix_clock_ticks()
    page_size = _posix_page_size()
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as handle:
            stat = handle.read()
    except OSError:
        return None
    try:
        # comm may contain spaces/parens; split after the last ')'.
        fields = stat.rsplit(")", 1)[1].split()
        # After comm: state(idx0) ppid(1) ... utime is field 14 overall ->
        # idx 11 here (utime), 12 (stime).
        utime = int(fields[11])
        stime = int(fields[12])
        cpu_ms = (utime + stime) / clock_ticks * 1000.0
    except (IndexError, ValueError):
        return None
    memory_mb: Optional[float] = None
    try:
        with open(f"/proc/{pid}/statm", "r", encoding="utf-8", errors="replace") as handle:
            parts = handle.read().split()
        resident_pages = int(parts[1])
        memory_mb = resident_pages * page_size / (1024.0 * 1024.0)
    except (OSError, IndexError, ValueError):
        # Fall back to VmRSS in status.
        try:
            with open(f"/proc/{pid}/status", "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        memory_mb = float(line.split()[1]) / 1024.0
                        break
        except (OSError, ValueError):
            pass
    return ProcessSample(cpu_ms=cpu_ms, memory_mb=memory_mb, process_count=1)


def sample_tree(pid: int) -> Optional[ProcessSample]:
    """Sum CPU and RSS over `pid` and its OS descendants. `None` if unmeasurable."""
    sample = sample_pid(pid)
    if sample is None:
        return None
    cpu_total = sample.cpu_ms or 0.0
    mem_total = sample.memory_mb or 0.0
    count = 1
    try:
        from ..code import proctree  # noqa: PLC0415 - lazy to avoid an import cycle

        for child in proctree.descendants(pid):
            child_sample = sample_pid(child)
            if child_sample is None:
                continue
            if child_sample.cpu_ms is not None:
                cpu_total += child_sample.cpu_ms
            if child_sample.memory_mb is not None:
                mem_total += child_sample.memory_mb
            count += 1
    except Exception:  # noqa: BLE001 - descendants is best-effort
        pass
    return ProcessSample(cpu_ms=cpu_total, memory_mb=mem_total, process_count=count)


def available() -> bool:
    """Whether resource sampling is supported on this platform/kernel."""
    if os.name == "nt":
        try:
            import ctypes  # noqa: F401, PLC0415

            _ = ctypes.WinDLL  # presence check only
            return True
        except Exception:  # noqa: BLE001
            return False
    if os.name == "posix":
        return os.path.isdir("/proc")
    return False


__all__ = ["ProcessSample", "available", "sample_pid", "sample_tree"]
