"""Resource telemetry and runaway-process protection.

The terminal subsystem must be able to notice a process that is running away —
spinning, ballooning, or spawning without bound — and, per policy, report it
rather than silently killing a user's legitimate long-running server.

  * `SystemResources` — a one-shot snapshot of CPU count, memory and load, from
    the OS, with NO optional dependency (psutil is not required; `/proc` and the
    Win32 API are read directly).
  * `ResourceLimits` — the configurable policy: a maximum number of tracked
    processes, a maximum output buffer, and a maximum lifetime after which a
    process is *flagged* (never auto-killed). Read from the environment so an
    operator can tighten it without a code change.

Nothing here kills anything. The monitor reports `runaway` on a process record and
emits an event; the caller (and the operator) decide.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

#: Default caps. Conservative; the point is to catch the pathological case, not
#: to police normal work. A dev server may run for hours and is never "runaway".
DEFAULT_MAX_PROCESSES = 64
DEFAULT_RUNAWAY_SECONDS = 24 * 60 * 60
DEFAULT_MAX_OUTPUT_BYTES = 8_000_000


def _env_int(name: str, default: int) -> int:
    try:
        value = os.environ.get(name)
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ResourceLimits:
    """Operator-tunable bounds. Env vars: `HARNESS_TERMINAL_MAX_PROCESSES`,
    `HARNESS_TERMINAL_RUNAWAY_SECONDS`, `HARNESS_TERMINAL_MAX_OUTPUT_BYTES`."""

    max_processes: int = DEFAULT_MAX_PROCESSES
    runaway_seconds: int = DEFAULT_RUNAWAY_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    @classmethod
    def from_env(cls) -> "ResourceLimits":
        return cls(
            max_processes=_env_int("HARNESS_TERMINAL_MAX_PROCESSES", DEFAULT_MAX_PROCESSES),
            runaway_seconds=_env_int("HARNESS_TERMINAL_RUNAWAY_SECONDS", DEFAULT_RUNAWAY_SECONDS),
            max_output_bytes=_env_int("HARNESS_TERMINAL_MAX_OUTPUT_BYTES", DEFAULT_MAX_OUTPUT_BYTES),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "maxProcesses": self.max_processes,
            "runawaySeconds": self.runaway_seconds,
            "maxOutputBytes": self.max_output_bytes,
        }


def _memory_windows() -> tuple[Optional[int], Optional[int]]:
    """(total_bytes, available_bytes) from the Win32 API, or (None, None)."""
    try:  # pragma: no cover - Windows
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except Exception:  # noqa: BLE001
        return None, None


def _memory_posix() -> tuple[Optional[int], Optional[int]]:
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page
        available = os.sysconf("SC_AVPHYS_PAGES") * page
        return int(total), int(available)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                info[key.strip()] = int(rest.strip().split()[0]) * 1024
        return info.get("MemTotal"), info.get("MemAvailable")
    except (OSError, ValueError):
        return None, None


def _loadavg() -> Optional[float]:
    try:
        return float(os.getloadavg()[0])  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        return None


def system_resources() -> dict[str, Any]:
    """A one-shot resource snapshot, honest about what the OS exposes."""
    if os.name == "nt":
        total, available = _memory_windows()
    else:
        total, available = _memory_posix()
    used = (total - available) if (total is not None and available is not None) else None
    return {
        "cpuCount": os.cpu_count(),
        "loadAverage1m": _loadavg(),
        "memoryTotalBytes": total,
        "memoryAvailableBytes": available,
        "memoryUsedBytes": used,
        "memoryUsedPct": (round(used / total * 100, 1) if (used is not None and total) else None),
    }


__all__ = [
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_MAX_PROCESSES",
    "DEFAULT_RUNAWAY_SECONDS",
    "ResourceLimits",
    "system_resources",
]
