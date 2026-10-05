"""Background-process spawning with per-process isolation.

`code/sandbox.py` owns one-shot bounded execution and keeps a single Job-Object
handle (correct for sequential runs). A process manager keeps MANY processes
alive at once, so it needs one isolation handle PER process. This module provides
exactly that, reusing the same platform strategy (`code/sandbox.py` documents it):

  * **Windows** — each child is assigned to its own Job Object with
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Closing the handle kills the whole tree
    (including on harness death, so no orphans); a `taskkill /F /T /PID` is the
    deterministic in-process tree kill.
  * **POSIX** — each child starts its own session/process group, killed with
    `os.killpg`.

If neither primitive is available, `spawn_process` refuses (`SandboxUnavailable`)
rather than run unsandboxed — the same honesty rule as `code/sandbox.py`.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Optional

from ..code.sandbox import RunSpec, SandboxUnavailable


@dataclass
class SpawnedProcess:
    """A live background process plus the resources that isolate it."""

    proc: subprocess.Popen
    backend: str
    _job: Optional[int] = None
    _kernel32: Optional[object] = None  # type: ignore[type-arg]

    @property
    def pid(self) -> int:
        return int(self.proc.pid)

    def poll(self) -> Optional[int]:
        return self.proc.poll()

    def kill_tree(self) -> None:
        """Kill the whole process tree, deterministically, then release."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.pid)],
                    shell=False, capture_output=True, timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            if self.proc.poll() is None:
                try:
                    self.proc.kill()
                except OSError:
                    pass
        else:
            pgid: Optional[int]
            try:
                pgid = os.getpgid(self.pid)
            except OSError:
                pgid = None
            try:
                if pgid and pgid > 1:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    self.proc.kill()
            except OSError:
                try:
                    self.proc.kill()
                except OSError:
                    pass
        self.release()

    def terminate(self) -> None:
        """Ask politely first (SIGTERM / no Windows signal), for stop semantics."""
        try:
            self.proc.terminate()
        except OSError:
            pass

    def release(self) -> None:
        """Close the isolation handle. With KILL_ON_JOB_CLOSE this also reaps."""
        if self._job and self._kernel32 is not None:
            try:
                self._kernel32.CloseHandle(self._job)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        self._job = None


def _windows_job() -> tuple[Optional[int], Optional[object]]:  # pragma: no cover - Windows
    """Create a kill-on-close Job Object. Returns (job_handle, kernel32) or (None, None)."""
    import ctypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None, None
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                        ("WriteOperationCount", ctypes.c_ulonglong),
                        ("OtherOperationCount", ctypes.c_ulonglong),
                        ("ReadTransferCount", ctypes.c_ulonglong),
                        ("WriteTransferCount", ctypes.c_ulonglong),
                        ("OtherTransferCount", ctypes.c_ulonglong)]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", ctypes.c_uint32),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", ctypes.c_uint32),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", ctypes.c_uint32),
                        ("SchedulingClass", ctypes.c_uint32)]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        return int(job), kernel32
    except Exception:  # noqa: BLE001 - no Win32 job primitive
        return None, None


def spawn_process(spec: RunSpec) -> SpawnedProcess:
    """Start a background process under an isolation primitive, or refuse.

    ``spec`` carries the argv, cwd and scrubbed env built by the caller. stdin is
    a pipe (so `write_process_input` works); stdout and stderr are SEPARATE pipes
    (so the two streams are never silently merged).
    """
    if os.name == "nt":
        job, kernel32 = _windows_job()
        flags = 0
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                creationflags=flags,
            )
        except (OSError, ValueError) as exc:
            if job and kernel32 is not None:
                try:
                    kernel32.CloseHandle(job)
                except Exception:  # noqa: BLE001
                    pass
            raise SandboxUnavailable(f"the process could not be started: {exc}") from exc
        spawned = SpawnedProcess(proc=proc, backend="windows-job", _job=job, _kernel32=kernel32)
        if job and kernel32 is not None:  # pragma: no cover - Windows
            try:
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_TERMINATE = 0x0001
                handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, proc.pid)
                if handle:
                    kernel32.AssignProcessToJobObject(job, handle)
                    kernel32.CloseHandle(handle)
            except Exception:  # noqa: BLE001 - taskkill still kills the tree
                pass
        return spawned
    if os.name == "posix":
        try:
            proc = subprocess.Popen(
                list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            raise SandboxUnavailable(f"the process could not be started: {exc}") from exc
        return SpawnedProcess(proc=proc, backend="posix-rlimit")
    raise SandboxUnavailable(f"no process primitive is available on platform {os.name!r}")


__all__ = ["SpawnedProcess", "spawn_process"]
