"""One bounded execution primitive. Everything that runs, runs through here.

There is no second execution path in the harness. `mcp/client.py` owns MCP
subprocesses; this owns the code capability's commands. Both follow the same
rules: argv arrays with no shell, an explicitly constructed environment, a
bounded lifetime, and a hard cap on what comes back.

Platform isolation (matching `mcp/orphan_supervisor.py`'s documented strategy):

  * **Windows** — the child is assigned to a Job Object with
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so closing the job handle (including on
    parent death) kills the whole tree. A timeout/cancel also runs
    `taskkill /F /T /PID` as the deterministic in-process kill.
  * **POSIX** — the child starts its own process group (`start_new_session`), and
    the tree is killed with `os.killpg`.

If neither primitive is available, `select_backend()` raises `SandboxUnavailable`
and the command is REFUSED — never executed unsandboxed. The same honesty rule as
the 503 "runtime unavailable" contract in AGENTS.md.
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import policy

# A hard ceiling on any command's output, below which a class may set its own.
MAX_OUTPUT_CAP_BYTES = 4_000_000
_READ_CHUNK = 65_536
_POLL_S = 0.05
_LINE_CAP_BYTES = 1_000_000


class SandboxUnavailable(RuntimeError):
    """No isolation primitive is available. The command is refused, not run."""

    code = "SANDBOX_UNAVAILABLE"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SandboxStreamError(RuntimeError):
    """An interactive child broke the line protocol (overflow, closed pipe)."""


@dataclass(frozen=True)
class RunSpec:
    argv: list[str]                 # already resolved + validated
    cwd: Path                       # the worktree root — never the operator checkout
    env: dict[str, str]             # built from policy.SECRET_ENV_ALLOWLIST ONLY
    timeout_s: int
    output_cap_bytes: int
    network: bool
    # OS-level resource limits (0 = unset). Applied where the platform supports
    # it: POSIX via `setrlimit` in the child; Windows via Job Object limits. The
    # wall-clock timeout above is always enforced regardless.
    cpu_seconds: int = 0            # RLIMIT_CPU / PerProcessUserTimeLimit
    memory_mb: int = 0              # RLIMIT_AS / Job memory limit
    process_limit: int = 0          # RLIMIT_NPROC / ActiveProcessLimit


@dataclass(frozen=True)
class RawResult:
    exit_code: Optional[int]
    timed_out: bool
    killed: bool
    cancelled: bool
    output: str
    truncated: bool
    total_chars: int
    duration_ms: int
    backend: str
    # Set when the process could not be started (so the caller reports a refusal).
    launch_error: Optional[str] = None
    # Real resource telemetry, measured by the backend. `None` = unmeasurable on
    # this platform — never a fabricated zero. `memory_peak_mb` is the peak RSS
    # observed across the process tree during the run.
    cpu_ms: Optional[float] = None
    memory_peak_mb: Optional[float] = None
    process_count: Optional[int] = None
    # Set to the breached limit name ("memory" | "cpu" | "processes") when the
    # parent monitor killed the tree for exceeding a declared resource limit.
    resource_limit: Optional[str] = None


def build_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    """ONLY `policy.SECRET_ENV_ALLOWLIST` keys are copied from the parent.

    Never `os.environ` passthrough. Never the settings vault. Never the callback
    token: `HARNESS_*`, `CRON_SECRET`, provider keys and vault values are ABSENT
    by construction, so a command that tries to read one finds nothing to read.
    `PYTHONIOENCODING=utf-8` is the repo's own Windows lesson. Proxy variables are
    dropped so a network attempt cannot be proxied.
    """
    env = {k: os.environ[k] for k in policy.SECRET_ENV_ALLOWLIST if k in os.environ}
    # Drop proxy config that could route a command through an intermediary.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "NO_PROXY",
                "no_proxy", "HARNESS_CALLBACK_TOKEN", "CRON_SECRET"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def _sample_tree(pid: int) -> Any:
    """Sample the process tree's resource usage, or None when unsupported.

    Reuses the execution layer's telemetry module (stdlib `ctypes` on Windows,
    `/proc` on Linux) so the sandbox and the execution layer share ONE sampler.
    """
    try:
        from ..execution import telemetry  # noqa: PLC0415

        return telemetry.sample_tree(pid)
    except Exception:  # noqa: BLE001 - telemetry must never break a run
        return None


def _limit_breach(
    sample: Any,
    peak_memory_mb: Optional[float],
    cpu_ms: Optional[float],
    max_memory_mb: int,
    max_cpu_seconds: int,
    max_processes: int,
) -> Optional[str]:
    """The name of the first declared limit the sample exceeds, or None.

    CPU is enforced on CUMULATIVE CPU time (across the tree), memory on PEAK RSS,
    processes on the tree's process count. A limit of 0 means unset. Only a real
    measurement can breach — an unmeasurable value never causes a kill.
    """
    if max_memory_mb and peak_memory_mb is not None and peak_memory_mb > max_memory_mb:
        return "memory"
    if max_cpu_seconds and cpu_ms is not None and cpu_ms > max_cpu_seconds * 1000:
        return "cpu"
    if max_processes and sample is not None and getattr(sample, "process_count", None):
        if sample.process_count > max_processes:
            return "processes"
    return None


# Kernel-enforcement signatures: the OS DENIES the operation at the limit (rather
# than letting the process climb past it), so the parent monitor never samples a
# breach. Windows Job Objects do exactly this (`ProcessMemoryLimit` →
# `MemoryError`; `ActiveProcessLimit` → WinError 1816), as does RLIMIT_AS on
# POSIX. When we declared a matching limit, the denial IS the limit firing.
# The needles are deliberately PRECISE: a loose token (e.g. a bare "137") would
# match a line number or a temp path and mis-classify an ordinary failure.
_LIMIT_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("memory", (
        "MemoryError", "Cannot allocate memory", "Out of memory",
        "STATUS_COMMITMENT_LIMIT", "bad_alloc", "std::bad_alloc",
    )),
    ("processes", (
        "WinError 1816", "Not enough quota is available to process this command",
        "fork: retry", "Resource temporarily unavailable",
    )),
    ("cpu", (
        "CPU time limit exceeded", "Killed by signal 9",
    )),
)


def _signature_limit(text: str, spec: "RunSpec") -> Optional[str]:
    """A declared limit that the kernel's denial matches, or None."""
    haystack = text or ""
    if not haystack.strip():
        return None
    lowered = haystack.lower()
    for name, needles in _LIMIT_SIGNATURES:
        declared = {
            "memory": bool(spec.memory_mb),
            "processes": bool(spec.process_limit),
            "cpu": bool(spec.cpu_seconds),
        }[name]
        if not declared:
            continue
        if any(needle.lower() in lowered for needle in needles):
            return name
    return None


def _read_stream(stream: Any, cap: int, sink: dict[str, Any], done: threading.Event) -> None:
    """Drain a pipe into a bounded buffer, counting the honest total."""
    chunks: list[bytes] = []
    kept = 0
    total = 0
    try:
        while True:
            chunk = stream.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if kept < cap:
                room = cap - kept
                chunks.append(chunk[:room])
                kept += min(len(chunk), room)
    except (OSError, ValueError):
        pass
    finally:
        sink["data"] = b"".join(chunks)
        sink["total"] = total
        done.set()


_OVERFLOW = object()
_EOF = object()


class SpawnedProcess:
    """A long-lived child with a bounded newline-delimited stdout protocol.

    The persistent analysis kernel is the only caller. It starts through the
    SAME backend as `run()` (Job Object / process group, scrubbed env, resource
    limits), but keeps stdin open and returns one line per request. stdout is
    protocol traffic only: the child redirects generated-code stdout/stderr into
    a bounded buffer. A line over the cap, a resource breach, or a dead child kills
    the whole tree and surfaces a named error — never an unbounded read.
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        *,
        kill: Callable[[], None],
        on_close: Callable[[], None],
        spec: RunSpec,
        line_cap_bytes: int = _LINE_CAP_BYTES,
    ) -> None:
        self.proc = proc
        self._kill_tree = kill
        self._on_close = on_close
        self._line_cap = max(1, int(line_cap_bytes))
        self._lines: queue.Queue[Any] = queue.Queue()
        self._lock = threading.Lock()
        self._closed = False
        self._killed = False
        self.resource_limit: Optional[str] = None
        self._stderr_sink: dict[str, Any] = {"data": b"", "total": 0}
        self._stderr_done = threading.Event()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(
            target=_read_stream,
            args=(proc.stderr, 16_384, self._stderr_sink, self._stderr_done),
            daemon=True,
        )
        self._monitor = threading.Thread(target=self._watch, args=(spec,), daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        self._monitor.start()

    def _read_stdout(self) -> None:
        try:
            while True:
                line = self.proc.stdout.readline(self._line_cap + 1) if self.proc.stdout else b""
                if not line:
                    break
                if len(line) > self._line_cap or not line.endswith(b"\n"):
                    self.resource_limit = "protocol"
                    self._kill()
                    self._lines.put(_OVERFLOW)
                    return
                self._lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._lines.put(_EOF)

    def _watch(self, spec: RunSpec) -> None:
        max_memory_mb = int(spec.memory_mb or 0)
        max_processes = int(spec.process_limit or 0)
        peak_memory_mb: Optional[float] = None
        last_sample = 0.0
        while not self._closed and self.proc.poll() is None:
            now = time.monotonic()
            if now - last_sample >= 0.25:
                last_sample = now
                sample = _sample_tree(self.proc.pid)
                if sample is not None:
                    if sample.memory_mb is not None:
                        peak_memory_mb = max(peak_memory_mb or 0.0, sample.memory_mb)
                    breach = _limit_breach(
                        sample, peak_memory_mb, sample.cpu_ms,
                        max_memory_mb, int(spec.cpu_seconds or 0), max_processes,
                    )
                    if breach:
                        self.resource_limit = breach
                        self._kill()
                        return
            time.sleep(_POLL_S)

    def _kill(self) -> None:
        with self._lock:
            if self._killed:
                return
            self._killed = True
        try:
            self._kill_tree()
        except Exception:  # noqa: BLE001 - kill is best-effort; close() still waits
            try:
                self.proc.kill()
            except OSError:
                pass

    def write_line(self, text: str) -> None:
        if self._closed or self.proc.stdin is None:
            raise SandboxStreamError("the kernel channel is closed")
        try:
            self.proc.stdin.write((text + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise SandboxStreamError(f"the kernel channel is closed: {exc}") from exc

    def read_line(self, timeout: float) -> str:
        try:
            item = self._lines.get(timeout=max(0.01, timeout))
        except queue.Empty as exc:
            raise TimeoutError("the kernel did not answer in time") from exc
        if item is _OVERFLOW:
            raise SandboxStreamError("the kernel sent an oversized protocol line")
        if item is _EOF:
            raise EOFError("the kernel process exited")
        return bytes(item).decode("utf-8", "replace").rstrip("\r\n")

    def alive(self) -> bool:
        return not self._closed and self.proc.poll() is None

    def stderr_text(self) -> str:
        return bytes(self._stderr_sink.get("data", b"")).decode("utf-8", "replace")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._kill()
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - kill should be prompt
            try:
                self.proc.kill()
            except OSError:
                pass
        try:
            self._on_close()
        except Exception:  # noqa: BLE001 - cleanup must not raise
            pass
        self._stderr_done.wait(timeout=2)


class _BaseBackend:
    name = "unknown"
    guarantees: tuple[str, ...] = ()

    def run(self, spec: RunSpec, *, cancel_event: Optional[threading.Event] = None) -> RawResult:
        return self._spawn_and_wait(spec, cancel_event=cancel_event)

    def spawn(self, spec: RunSpec, *, line_cap_bytes: int = _LINE_CAP_BYTES) -> SpawnedProcess:
        if spec.network:
            raise SandboxUnavailable(
                "the local runner cannot keep a network-capable kernel contained"
            )
        try:
            proc = self._popen_interactive(spec)
        except (OSError, ValueError) as exc:
            raise SandboxUnavailable(f"the kernel process could not start: {exc}") from exc
        self._on_spawn(proc, spec)
        return SpawnedProcess(
            proc,
            kill=lambda: self._kill_tree(proc),
            on_close=lambda: self._on_close(proc),
            spec=spec,
            line_cap_bytes=line_cap_bytes,
        )

    def _spawn_and_wait(
        self, spec: RunSpec, *, cancel_event: Optional[threading.Event]
    ) -> RawResult:
        started = time.monotonic()
        cap = max(1, min(int(spec.output_cap_bytes), MAX_OUTPUT_CAP_BYTES))
        try:
            proc = self._popen(spec)
        except (OSError, ValueError) as exc:
            return RawResult(
                exit_code=None, timed_out=False, killed=False, cancelled=False,
                output="", truncated=False, total_chars=0,
                duration_ms=int((time.monotonic() - started) * 1000),
                backend=self.name, launch_error=str(exc),
            )
        self._on_spawn(proc, spec)
        sink: dict[str, Any] = {"data": b"", "total": 0}
        done = threading.Event()
        reader = threading.Thread(
            target=_read_stream, args=(proc.stdout, cap, sink, done), daemon=True
        )
        reader.start()

        timed_out = cancelled = killed = False
        resource_limit: Optional[str] = None
        deadline = started + max(1, int(spec.timeout_s))
        # Resource telemetry: sample the process tree while it runs and keep the
        # peak. Sampling is cheap (a couple of syscalls) and best-effort — an
        # unmeasurable value stays None.
        peak_memory_mb: Optional[float] = None
        last_cpu_ms: Optional[float] = None
        last_process_count: Optional[int] = None
        sample_every = 0.25
        last_sample = 0.0
        # The parent-side enforcement thresholds. Windows Job-Object limits already
        # kill on breach; these also cover POSIX and give a deterministic verdict.
        max_memory_mb = int(spec.memory_mb or 0)
        max_cpu_seconds = int(spec.cpu_seconds or 0)
        max_processes = int(spec.process_limit or 0)
        # Sample immediately after spawn so even a very short process is measured.
        first = _sample_tree(proc.pid)
        if first is not None:
            peak_memory_mb = first.memory_mb
            last_cpu_ms = first.cpu_ms
            last_process_count = first.process_count
        while True:
            if proc.poll() is not None:
                break
            now_monotonic = time.monotonic()
            if now_monotonic - last_sample >= sample_every:
                last_sample = now_monotonic
                sample = _sample_tree(proc.pid)
                if sample is not None:
                    if sample.memory_mb is not None:
                        peak_memory_mb = max(peak_memory_mb or 0.0, sample.memory_mb)
                    last_cpu_ms = sample.cpu_ms
                    last_process_count = sample.process_count
                # Enforce the declared limits, killing the whole tree on breach.
                breach = _limit_breach(sample, peak_memory_mb, last_cpu_ms,
                                       max_memory_mb, max_cpu_seconds, max_processes)
                if breach:
                    resource_limit = breach
                    killed = True
                    self._kill_tree(proc)
                    break
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                killed = True
                self._kill_tree(proc)
                break
            if time.monotonic() > deadline:
                timed_out = True
                killed = True
                self._kill_tree(proc)
                break
            time.sleep(_POLL_S)
        # Take one final CPU sample while the handle is still valid (a process that
        # has already exited may not read, so this is best-effort).
        final_sample = _sample_tree(proc.pid)
        if final_sample is not None:
            if final_sample.cpu_ms is not None:
                last_cpu_ms = final_sample.cpu_ms
            if final_sample.memory_mb is not None:
                peak_memory_mb = max(peak_memory_mb or 0.0, final_sample.memory_mb)
            if final_sample.process_count is not None:
                last_process_count = final_sample.process_count
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - kill should be prompt
            try:
                proc.kill()
            except OSError:
                pass
        done.wait(timeout=5)
        reader.join(timeout=2)
        self._on_close(proc)
        raw: bytes = sink.get("data", b"")
        total: int = int(sink.get("total", len(raw)))
        text = raw.decode("utf-8", "replace")
        # If the kernel DENIED an operation at a declared limit (Windows Job
        # Objects, POSIX RLIMIT_AS), the parent monitor saw no climbing breach but
        # the run still hit the limit — classify it from the output signature.
        if resource_limit is None and not cancelled and not timed_out:
            resource_limit = _signature_limit(text, spec)
            if resource_limit:
                killed = True
        return RawResult(
            exit_code=proc.returncode,
            timed_out=timed_out,
            killed=killed,
            cancelled=cancelled,
            output=text,
            truncated=total > cap,
            total_chars=total,
            duration_ms=int((time.monotonic() - started) * 1000),
            backend=self.name,
            cpu_ms=last_cpu_ms,
            memory_peak_mb=peak_memory_mb,
            process_count=last_process_count,
            resource_limit=resource_limit,
        )

    def _popen(self, spec: RunSpec) -> subprocess.Popen:  # pragma: no cover - overridden
        raise NotImplementedError

    def _popen_interactive(self, spec: RunSpec) -> subprocess.Popen:  # pragma: no cover
        raise NotImplementedError

    def _on_spawn(self, proc: subprocess.Popen, spec: RunSpec) -> None:
        pass

    def _on_close(self, proc: subprocess.Popen) -> None:
        pass

    def _kill_tree(self, proc: subprocess.Popen) -> None:
        raise NotImplementedError


def _posix_rlimit_hook(spec: RunSpec):  # pragma: no cover - POSIX only
    """A `preexec_fn` that applies RLIMIT_CPU / RLIMIT_AS / RLIMIT_NPROC.

    Best-effort: a platform without `resource` (or a limit it cannot set) simply
    skips that limit; the wall-clock timeout is still enforced by the parent.
    """
    if not (spec.cpu_seconds or spec.memory_mb or spec.process_limit):
        return None
    try:
        import resource  # noqa: PLC0415
    except ImportError:
        return None

    def _apply() -> None:
        try:
            if spec.cpu_seconds:
                resource.setrlimit(resource.RLIMIT_CPU, (spec.cpu_seconds, spec.cpu_seconds))
        except (ValueError, OSError):
            pass
        try:
            if spec.memory_mb:
                limit = spec.memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass
        try:
            if spec.process_limit:
                resource.setrlimit(resource.RLIMIT_NPROC, (spec.process_limit, spec.process_limit))
        except (ValueError, OSError):
            pass

    return _apply


class WindowsJobBackend(_BaseBackend):
    """Windows: a Job Object with KILL_ON_JOB_CLOSE plus a deterministic tree kill."""

    name = "windows-job"
    guarantees = ("process_tree_kill", "env_scrub", "output_cap", "parent_death_kill")

    def __init__(self) -> None:
        self._jobs: dict[int, Any] = {}
        try:  # pragma: no cover - platform-specific
            import ctypes

            self._ctypes = ctypes
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except Exception as exc:  # noqa: BLE001 - no Win32 = no isolation primitive
            raise SandboxUnavailable(f"the Windows job primitive is unavailable: {exc}") from exc

    @staticmethod
    def _creation_flags() -> int:
        return (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    def _popen(self, spec: RunSpec) -> subprocess.Popen:
        return subprocess.Popen(
            list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )

    def _popen_interactive(self, spec: RunSpec) -> subprocess.Popen:
        return subprocess.Popen(
            list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=self._creation_flags(),
        )

    def _on_spawn(self, proc: subprocess.Popen, spec: RunSpec) -> None:
        self._assign_job(proc, spec)  # best-effort; taskkill still kills the tree

    def _assign_job(self, proc: subprocess.Popen, spec: RunSpec) -> None:  # pragma: no cover - Windows
        try:
            ctypes = self._ctypes
            kernel32 = self._kernel32
            from ctypes import wintypes
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return
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
                _fields_ = [("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                            ("IoInfo", IO_COUNTERS),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            # Optional OS-level limits when the caller declared them.
            JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
            JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
            if getattr(spec, "memory_mb", 0):
                info.ProcessMemoryLimit = int(spec.memory_mb) * 1024 * 1024
                info.JobMemoryLimit = int(spec.memory_mb) * 1024 * 1024
                limit_flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY
            if getattr(spec, "process_limit", 0):
                info.BasicLimitInformation.ActiveProcessLimit = int(spec.process_limit)
                limit_flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.LimitFlags = limit_flags
            kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
            )
            # Attach via the process handle (OpenProcess on the pid).
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001
            handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, proc.pid)
            if handle:
                kernel32.AssignProcessToJobObject(job, handle)
                kernel32.CloseHandle(handle)
            self._jobs[proc.pid] = job
        except Exception:  # noqa: BLE001 - best-effort; taskkill kills the tree
            self._jobs.pop(proc.pid, None)

    def _on_close(self, proc: subprocess.Popen) -> None:  # pragma: no cover - Windows
        job = self._jobs.pop(proc.pid, None)
        if job:
            try:
                self._kernel32.CloseHandle(job)
            except Exception:  # noqa: BLE001
                pass

    def _kill_tree(self, proc: subprocess.Popen) -> None:
        # Fixed, argument-free tree kill. `proc.pid` is internal, never model text.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                shell=False, capture_output=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            try:
                proc.kill()
            except OSError:
                pass


class PosixBackend(_BaseBackend):
    """POSIX: a new process group per child, killed with `os.killpg`."""

    name = "posix-rlimit"
    guarantees = ("process_tree_kill", "env_scrub", "output_cap")

    def _popen(self, spec: RunSpec) -> subprocess.Popen:
        return subprocess.Popen(
            list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, preexec_fn=_posix_rlimit_hook(spec),
        )

    def _popen_interactive(self, spec: RunSpec) -> subprocess.Popen:
        return subprocess.Popen(
            list(spec.argv), cwd=str(spec.cwd), env=dict(spec.env), shell=False,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, preexec_fn=_posix_rlimit_hook(spec),
        )

    def _kill_tree(self, proc: subprocess.Popen) -> None:
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = None
        try:
            if pgid and pgid > 1:
                os.killpg(pgid, signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass


_BACKEND: Optional[_BaseBackend] = None


def select_backend() -> _BaseBackend:
    """Prefer OS-level isolation; report exactly what was chosen.

    Windows → a Job Object backend; POSIX → process groups. If neither primitive
    exists, raise `SandboxUnavailable`. There is no 'unbounded' fallback.
    """
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    if os.name == "nt":
        _BACKEND = WindowsJobBackend()
    elif os.name == "posix":
        _BACKEND = PosixBackend()
    else:
        raise SandboxUnavailable(f"no sandbox primitive is available on platform {os.name!r}")
    return _BACKEND


def set_backend(backend: Optional[_BaseBackend]) -> None:
    """TEST SEAM: force a backend (or None to re-detect). Never used in production."""
    global _BACKEND
    _BACKEND = backend


def run(spec: RunSpec, *, cancel_event: Optional[threading.Event] = None) -> RawResult:
    """Run one command through the selected isolation primitive.

    The local primitive enforces NO network boundary: a spec that DECLARES
    network is refused here (never silently run with host network) and must be
    routed to the network-capable tier by its caller (`code/backends.py`).
    """
    if spec.network:
        raise SandboxUnavailable(
            "this command needs a runner that can keep its network use contained; "
            "the local runner cannot, so it was not run"
        )
    return select_backend().run(spec, cancel_event=cancel_event)


def spawn(spec: RunSpec, *, line_cap_bytes: int = _LINE_CAP_BYTES) -> SpawnedProcess:
    """Start a long-lived child through the selected isolation primitive.

    Only the persistent analysis kernel uses this. It has the same env scrub,
    process-tree kill and resource limits as `run()`; `network=True` is refused.
    """
    if spec.network:
        raise SandboxUnavailable(
            "this kernel needs a runner that can keep its network use contained; "
            "the local runner cannot, so it was not started"
        )
    return select_backend().spawn(spec, line_cap_bytes=line_cap_bytes)


def backend_name() -> str:
    """The current backend's name, or 'unavailable' — honest, never guessed."""
    try:
        return select_backend().name
    except SandboxUnavailable:
        return "unavailable"


__all__ = [
    "MAX_OUTPUT_CAP_BYTES",
    "PosixBackend",
    "RawResult",
    "RunSpec",
    "SandboxStreamError",
    "SandboxUnavailable",
    "SpawnedProcess",
    "WindowsJobBackend",
    "backend_name",
    "build_env",
    "run",
    "select_backend",
    "set_backend",
    "spawn",
]
