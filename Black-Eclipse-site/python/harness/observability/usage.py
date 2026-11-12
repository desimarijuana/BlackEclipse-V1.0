"""Process USE snapshot for the observability hub (C7).

Utilization / Saturation / Errors need real numbers, not placeholders. This
module samples the harness process with the standard library only:

  * Windows — `GetProcessMemoryInfo` (working set) and `GetProcessTimes` (CPU);
  * POSIX   — `resource.getrusage` + `ru_maxrss` (or `/proc/self/status`).

CPU percent is the delta since the previous sample, normalized to the machine
(0–100). `available=False` is reported honestly when the platform cannot be
read; the caller then records nothing rather than a fabricated zero.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Optional

_LOCK = threading.RLock()
_LAST: Optional[tuple[float, float]] = None


def _cpu_count() -> int:
    return max(1, int(os.cpu_count() or 1))


def _windows_snapshot() -> dict[str, Any]:
    import ctypes
    from ctypes import wintypes

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

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    memory = None
    if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        memory = int(counters.WorkingSetSize)

    creation, exit_time, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    cpu_seconds = None
    if kernel32.GetProcessTimes(
        process, ctypes.byref(creation), ctypes.byref(exit_time),
        ctypes.byref(kernel), ctypes.byref(user),
    ):
        def _to_seconds(value: Any) -> float:
            ticks = (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)
            return ticks / 10_000_000.0
        cpu_seconds = _to_seconds(kernel) + _to_seconds(user)
    return {"memoryBytes": memory, "cpuSeconds": cpu_seconds}


def _posix_snapshot() -> dict[str, Any]:
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_seconds = float(usage.ru_utime + usage.ru_stime)
    memory = int(usage.ru_maxrss) * (1024 if sys.platform != "darwin" else 1)
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    memory = int(line.split()[1]) * 1024
                    break
    except OSError:
        pass
    return {"memoryBytes": memory, "cpuSeconds": cpu_seconds}


def process_usage() -> dict[str, Any]:
    """A point-in-time process snapshot. Never raises."""
    global _LAST
    try:
        raw = _windows_snapshot() if sys.platform == "win32" else _posix_snapshot()
    except Exception:  # noqa: BLE001 - a usage probe must never break telemetry
        return {"available": False}
    now = time.monotonic()
    cpu = raw.get("cpuSeconds")
    cpu_percent: Optional[float] = None
    if cpu is not None:
        with _LOCK:
            last = _LAST
            _LAST = (now, float(cpu))
        if last is not None:
            elapsed = now - last[0]
            if elapsed > 0:
                delta = max(0.0, float(cpu) - last[1])
                cpu_percent = round((delta / elapsed) * 100.0 / _cpu_count(), 3)
    return {
        "available": True,
        "cpuPercent": cpu_percent,
        "cpuSeconds": cpu,
        "memoryBytes": raw.get("memoryBytes"),
        "threads": threading.active_count(),
    }


def reset_usage_sampler() -> None:
    """Test seam: forget the previous CPU sample."""
    global _LAST
    with _LOCK:
        _LAST = None


__all__ = ["process_usage", "reset_usage_sampler"]
