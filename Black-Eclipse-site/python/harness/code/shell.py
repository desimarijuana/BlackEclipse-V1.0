"""Real shell execution with background processes.

`terminal.py` is argv-only and shell-free by design. This module adds the
explicitly-opted-in *real shell* a coding harness needs: a command string runs
through the detected shell (PowerShell/CMD on Windows, bash/sh elsewhere),
still confined to the bound workspace root, still timed out, still capped in
output, and still gated by the same approval policy as `terminal_run`.

Two surfaces:
  * one-shot:  `run(command...)` -> structured result (for `shell_run`)
  * background: `spawn(command...)` -> ProcessHandle with pollable output
    (for `shell_spawn` / `process_output` / `process_kill` / `process_list`)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAX_OUTPUT_CHARS = 200_000
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 900


def _scrubbed_env() -> dict[str, str]:
    """The child environment: the allowlist ONLY, never `os.environ` in full.

    This is the SAME builder the sandboxed command path uses
    (`code.sandbox.build_env`), so a shell and a sandboxed command see the
    same world. A secret that is absent from one is absent from both.
    """
    from .sandbox import build_env  # noqa: PLC0415

    return build_env()


def detect_shell() -> list[str]:
    """The argv prefix for the host shell, best-effort."""
    if os.name == "nt":
        pwsh = shutil.which("powershell") or shutil.which("pwsh")
        if pwsh:
            return [pwsh, "-NoProfile", "-NonInteractive", "-Command"]
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/s", "/c"]
    for name in ("bash", "sh"):
        found = shutil.which(name)
        if found:
            return [found, "-c"]
    return ["/bin/sh", "-c"]


@dataclass
class ShellResult:
    command: str
    cwd: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool
    status: str  # "success" | "failed" | "timeout" | "killed"


def run(
    command: str,
    *,
    cwd: Path,
    timeout_s: Optional[int] = None,
    env_extra: Optional[dict[str, str]] = None,
    stdin: Optional[str] = None,
) -> ShellResult:
    argv = detect_shell() + [command]
    # Round 3 / W9 (ADR-H297): the shell gets the SAME scrubbed environment a
    # sandboxed command gets - `policy.SECRET_ENV_ALLOWLIST` keys ONLY. It used
    # to inherit `os.environ` in full, so a single `shell_run` could read the
    # provider keys, the callback token and the vault, and print them into the
    # conversation. A shell must never see more of the environment than a
    # sandboxed command does.
    env = _scrubbed_env()
    if env_extra:
        env.update(env_extra)
    timeout = max(1, min(int(timeout_s or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=env, input=stdin,
            capture_output=True, text=True, timeout=timeout,
        )
        duration = int((time.monotonic() - started) * 1000)
        out, err = proc.stdout or "", proc.stderr or ""
        truncated = False
        if len(out) > MAX_OUTPUT_CHARS:
            out = out[-MAX_OUTPUT_CHARS:]
            truncated = True
        if len(err) > MAX_OUTPUT_CHARS:
            err = err[-MAX_OUTPUT_CHARS:]
            truncated = True
        return ShellResult(command, str(cwd), proc.returncode, out, err, duration, False, truncated,
                           "success" if proc.returncode == 0 else "failed")
    except subprocess.TimeoutExpired as exc:
        duration = int((time.monotonic() - started) * 1000)
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return ShellResult(command, str(cwd), None, out, err, duration, True, False, "timeout")


@dataclass
class ProcessHandle:
    pid: str
    command: str
    cwd: str
    started: float
    proc: subprocess.Popen
    stdout_buf: list[str] = field(default_factory=list)
    stderr_buf: list[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    status: str = "running"  # running | exited | killed
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def output(self) -> tuple[str, str]:
        with self._lock:
            return "".join(self.stdout_buf), "".join(self.stderr_buf)

    def poll(self) -> None:
        rc = self.proc.poll()
        if rc is not None and self.status == "running":
            self.exit_code = rc
            self.status = "exited"


_PROCESSES: dict[str, ProcessHandle] = {}
_PROCESSES_LOCK = threading.Lock()


def spawn(command: str, *, cwd: Path, env_extra: Optional[dict[str, str]] = None) -> ProcessHandle:
    argv = detect_shell() + [command]
    # Round 3 / W9 (ADR-H297): the same scrubbed environment as `run` - a
    # background process must not be a way around the scrub.
    env = _scrubbed_env()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        argv, cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, errors="replace",
    )
    handle = ProcessHandle(pid=uuid.uuid4().hex[:8], command=command, cwd=str(cwd),
                           started=time.time(), proc=proc)
    def _pump(stream, buf):
        try:
            for line in iter(stream.readline, ""):
                with handle._lock:
                    buf.append(line)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_pump, args=(proc.stdout, handle.stdout_buf), daemon=True).start()
    threading.Thread(target=_pump, args=(proc.stderr, handle.stderr_buf), daemon=True).start()
    with _PROCESSES_LOCK:
        _PROCESSES[handle.pid] = handle
    return handle


def get(pid: str) -> Optional[ProcessHandle]:
    with _PROCESSES_LOCK:
        return _PROCESSES.get(pid)


def kill(pid: str) -> bool:
    handle = get(pid)
    if handle is None:
        return False
    try:
        handle.proc.kill()
        handle.status = "killed"
        handle.exit_code = handle.proc.wait(timeout=5)
        return True
    except Exception:  # noqa: BLE001
        return False


def list_processes() -> list[ProcessHandle]:
    with _PROCESSES_LOCK:
        handles = list(_PROCESSES.values())
    for h in handles:
        h.poll()
    return handles
