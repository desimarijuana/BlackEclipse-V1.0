"""Persistent shell sessions — a real, stateful terminal the agent can drive.

A one-shot command (`execute_command`) and a persistent shell are different
things. This module owns the second: a shell process that stays alive so
`cd project`, `export NODE_ENV=test` and `npm run dev` share one context.

Two execution modes, both honest:

  * **pty** — when a real pseudo-terminal library is installed (see
    `pty_backend.py`), the session is a true ConPTY/forkpty: raw stdin, ANSI,
    window size, Ctrl+C as a real interrupt.
  * **pipe** — otherwise a shell is kept alive with connected stdin/stdout/stderr.
    It preserves cwd and environment, accepts stdin and streams output, but it is
    NOT a TTY. The capability report says `pty: false` in this case; we never
    pretend the fallback is a PTY.

cwd is tracked by emitting a hidden sentinel command after each command and
parsing the shell's own `$PWD`/`%CD%` — never by guessing. A standalone
`cd`/`export`/`set`/`pwd` is handled natively (no process), exactly as the
existing `code/terminal_tools.py` does, so the persistent cwd survives even
across an interactive prompt.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

#: ANSI/VT control sequences. The PTY stream is full of them (colours, cursor
#: positioning); the UI receives them verbatim so a real terminal can render,
#: but the agent-facing text is stripped.
_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"      # CSI ... final byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL/ST
    r"|\x1b[@-Z\\-_]"                  # Fe escape
    r"|\x1b\([0-9A-Za-z]"             # charset designation
)


from ..persistence import now_iso
from . import redaction
from .buffer import RingBuffer
from .pty_backend import PseudoTerminal
from .shell_detect import resolve_shell
from .types import SessionInfo, ShellInfo, StreamName

_MARK_PREFIX = "::ECL-ECLIPSE::cd="
_MAX_SESSION_OUTPUT_CHARS = 60_000
_DEFAULT_TIMEOUT_S = 120
_MAX_TIMEOUT_S = 900
_QUIET_S = 0.6
_READ_BLOCK = 4096

#: A sentinel line whose value is a real path (drive letter or POSIX root). In a
#: PTY the shell echoes the COMMAND too, where the sentinel is followed by `%CD%`
#: / `(Get-Location).Path`; only the RESULT is followed by a path. This pattern
#: therefore selects the result and ignores the echo.
_MARKER_PATH = re.compile(re.escape(_MARK_PREFIX) + r"([A-Za-z]:[\\/][^\r\n\x1b]*|/[^\r\n\x1b]*)")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _marker_path(text: str) -> Optional[str]:
    match = _MARKER_PATH.search(text)
    if not match:
        return None
    return match.group(1).strip().rstrip("\r\n")


def _marker_expr(shell_kind: str) -> str:
    """A shell fragment that prints the completion sentinel plus the cwd."""
    if shell_kind == "powershell":
        return "Write-Host ('" + _MARK_PREFIX + "' + (Get-Location).Path)"
    if shell_kind == "cmd":
        return "echo " + _MARK_PREFIX + "%CD%"
    return "printf '" + _MARK_PREFIX + "%s\\n' \"$PWD\""


def _wrap_command(shell_kind: str, command: str) -> str:
    """Append the sentinel to the SAME command line.

    Writing the sentinel as a SEPARATE line would let a command that reads stdin
    consume it as input (the pipe-shell ambiguity). Appending it with the shell's
    own sequencing operator means it is only reached once the command returns —
    so interactive prompts work AND the cwd is reported after every command.
    """
    marker = _marker_expr(shell_kind)
    if shell_kind == "cmd":
        return f"{command} & {marker}"
    return f"{command}; {marker}"


def _strip_marker_echo(text: str) -> str:
    """Drop the shell's echo of the hidden sentinel line (contains the prefix)."""
    return "\n".join(line for line in text.splitlines() if _MARK_PREFIX not in line)


@dataclass
class _Live:
    """The live OS resources behind one session. Not persisted."""

    proc: Optional[subprocess.Popen] = None
    pty: Optional[PseudoTerminal] = None
    done: threading.Event = field(default_factory=threading.Event)
    run_lock: threading.Lock = field(default_factory=threading.Lock)
    alive: bool = True


class ShellSession:
    """One persistent shell. Created by `SessionManager.open`."""

    def __init__(
        self,
        *,
        session_id: str,
        shell: ShellInfo,
        runtime: str,
        cwd: str,
        env: dict[str, str],
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        owner: Optional[str] = None,
        rows: int = 24,
        columns: int = 80,
        use_pty: bool = True,
    ) -> None:
        self.session_id = session_id
        self.shell = shell
        self.runtime = runtime
        self.cwd = cwd
        self.env_profile: dict[str, str] = dict(env or {})
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.owner = owner
        self.rows = int(rows)
        self.columns = int(columns)
        self.created_at = now_iso()
        self.updated_at = self.created_at
        self.status = "starting"
        self.pid: Optional[int] = None
        self.pty = False
        self.buffer = RingBuffer()
        self._live = _Live()
        self._closed = False
        self._marker_scan_seq = 0
        #: Wakes a live UI stream the instant new output arrives, so a terminal
        #: renders with low latency instead of polling on a timer.
        self._output_cv = threading.Condition()
        #: Serializes writes to the PTY. A terminal sends one HTTP request per
        #: keystroke, so many threads can call `write_raw` at once; without this
        #: lock their bytes interleave (and pywinpty's write is not reentrant),
        #: which is why typed commands arrived jumbled or never reached the shell.
        self._write_lock = threading.Lock()
        self._spawn(use_pty=use_pty)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _spawn(self, *, use_pty: bool) -> None:
        env = dict(os.environ)
        env.update(self.env_profile)
        env["PYTHONIOENCODING"] = "utf-8"
        argv = list(self.shell.argv_prefix) + ["-"] if self._supports_stdio_dash() else list(self.shell.argv_prefix) + [""]
        if use_pty:
            self._live.pty = PseudoTerminal()
            started = self._live.pty.spawn(
                self._interactive_argv(), cwd=self.cwd, env=env,
                rows=self.rows, columns=self.columns,
            )
            if started:
                self.pty = True
                self.pid = getattr(self._live.pty._impl, "pid", None)
                threading.Thread(target=self._pump_pty, daemon=True).start()
                self.status = "running"
                # No synthetic banner: a real PTY prints its own prompt. We only
                # wake any waiting UI stream so it re-reads immediately.
                self._wake()
                return
            self._live.pty = None
        # Piped persistent shell fallback.
        try:
            self._live.proc = subprocess.Popen(
                self._pipe_argv(), cwd=self.cwd, env=env, shell=False,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
            )
        except (OSError, ValueError) as exc:
            self.status = "failed"
            self._notify(f"session could not start: {exc}\n")
            raise SessionStartError(str(exc)) from exc
        self.pid = self._live.proc.pid
        threading.Thread(target=self._pump, args=(self._live.proc.stdout, StreamName.STDOUT.value), daemon=True).start()
        threading.Thread(target=self._pump, args=(self._live.proc.stderr, StreamName.STDERR.value), daemon=True).start()
        threading.Thread(target=self._watch_exit, daemon=True).start()
        self.status = "running"
        self._wake()

    def _supports_stdio_dash(self) -> bool:
        return self.shell.kind in ("powershell", "cmd")

    def _interactive_argv(self) -> list[str]:
        if self.shell.kind == "powershell":
            return [self.shell.path or "powershell", "-NoLogo", "-NoProfile"]
        if self.shell.kind == "cmd":
            return [self.shell.path or "cmd.exe"]
        return [self.shell.path or "bash", "-i"] if self.shell.kind == "bash" else [self.shell.path or "sh"]

    def _pipe_argv(self) -> list[str]:
        # PowerShell reads commands from stdin with `-Command -`; cmd.exe reads
        # from stdin with no args; bash/sh use `-s`.
        if self.shell.kind == "powershell":
            return [self.shell.path or "powershell", "-NoLogo", "-NoProfile", "-Command", "-"]
        if self.shell.kind == "cmd":
            return [self.shell.path or os.environ.get("COMSPEC") or "cmd.exe"]
        return [self.shell.path or "bash", "-s"]

    # ── Pumps ─────────────────────────────────────────────────────────────────

    def _notify(self, text: str) -> None:
        self.buffer.note(text, now_iso())
        self._wake()

    def _wake(self) -> None:
        with self._output_cv:
            self._output_cv.notify_all()

    def _pump(self, stream: Any, stream_name: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                if _MARK_PREFIX in line:
                    self._absorb_marker(line)
                    continue
                self.buffer.append(stream_name, line, now_iso())
                with self._output_cv:
                    self._output_cv.notify_all()
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    def _pump_pty(self) -> None:
        while self._live.alive:
            try:
                chunk = self._live.pty.read(_READ_BLOCK) if self._live.pty else ""
            except Exception:  # noqa: BLE001
                break
            if chunk:
                self.buffer.append(StreamName.STDOUT.value, chunk, now_iso())
                with self._output_cv:
                    self._output_cv.notify_all()
            elif self._live.pty and not self._live.pty.isalive():
                break
            else:
                time.sleep(0.05)
        self._live.alive = False
        if self.status == "running":
            self.status = "exited"
        with self._output_cv:
            self._output_cv.notify_all()

    def wait_for_output(self, since_sequence: int, timeout: float) -> dict[str, Any]:
        """Block until output past ``since_sequence`` arrives, or the timeout elapses.

        This is what backs a live terminal stream: the caller long-polls with its
        last cursor and gets new data the instant it lands, instead of a fixed
        poll interval. Returns the same shape as `read`.
        """
        window = self.read(since_sequence=since_sequence)
        if window["count"] > 0 or timeout <= 0 or not self.is_alive():
            return window
        with self._output_cv:
            self._output_cv.wait(timeout=timeout)
        return self.read(since_sequence=since_sequence)

    def _absorb_marker(self, line: str) -> None:
        # Only a sentinel followed by a real path is the RESULT; the PTY echo of
        # the command has a shell variable expression after the prefix instead.
        path = _marker_path(line)
        if path is None:
            return
        self.cwd = path
        self.updated_at = now_iso()
        self._live.done.set()

    def _watch_exit(self) -> None:
        proc = self._live.proc
        if proc is None:
            return
        rc = proc.wait()
        self._live.alive = False
        if self.status == "running":
            self.status = "exited"
        self.updated_at = now_iso()
        self._notify(f"session exited (code {rc})")
        self._live.done.set()

    # ── Driving the shell ─────────────────────────────────────────────────────

    def send(self, command: str, *, timeout_s: Optional[int] = None) -> dict[str, Any]:
        """Run a command in the session and wait for it to finish (bounded).

        Returns ``{text, timedOut, startSequence, endSequence}``. The command is
        NOT executed natively here; the caller handles `cd`/`export` fast paths
        before calling. Echo of the hidden sentinel is stripped.
        """
        if not self.is_alive():
            return {"text": "", "timedOut": False, "startSequence": 0, "endSequence": 0, "dead": True}
        timeout = max(1, min(int(timeout_s or _DEFAULT_TIMEOUT_S), _MAX_TIMEOUT_S))
        with self._live.run_lock:
            start_seq = self.buffer.snapshot()["lastSequence"]
            self._live.done.clear()
            if self.pty:
                # In a real PTY a fresh line executes the command; the sentinel
                # rides on the SAME line so an interactive prompt still works, then
                # its output updates `cwd`. We wait for the echoed sentinel line.
                self.write_raw(_wrap_command(self.shell.kind, command) + "\r")
                got = self._wait_marker(timeout)
            else:
                self.write_raw(_wrap_command(self.shell.kind, command) + "\n")
                got = self._live.done.wait(timeout=timeout)
            self.updated_at = now_iso()
            window = self.buffer.read(since_sequence=start_seq)
            raw = _strip_marker_echo(window["text"])
            # The agent sees clean text; a real terminal (the UI) reads the buffer
            # directly and keeps the ANSI so it can render colours and layout.
            clean = redaction.redact(strip_ansi(raw))
            clean = _strip_marker_echo(clean)
            return {
                "text": clean[-_MAX_SESSION_OUTPUT_CHARS:],
                "raw": raw,
                "cwd": self.cwd,
                "timedOut": not got,
                "startSequence": start_seq,
                "endSequence": window["nextSequence"],
                "dead": False,
            }

    def write_raw(self, data: str) -> bool:
        """Write raw bytes to the shell's stdin (control chars pass through in PTY).

        Serialized by `_write_lock`: a terminal UI sends one request per keystroke,
        so concurrent writes must not interleave (and pywinpty's write is not
        reentrant). The lock keeps the byte order exactly the typing order.
        """
        with self._write_lock:
            if self.pty and self._live.pty is not None:
                return self._live.pty.write(data)
            proc = self._live.proc
            if proc is None or proc.stdin is None:
                return False
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
                return True
            except (OSError, ValueError):
                return False

    def write_input(self, data: str, *, newline: bool = True) -> bool:
        payload = data if (not newline or data.endswith(("\n", "\r"))) else data + ("\r" if self.pty else "\n")
        return self.write_raw(payload)

    def send_control(self, key: str) -> bool:
        """Ctrl+C / Ctrl+D / Ctrl+Z. INTR is a real byte in PTY; on the pipe
        fallback it is written to the child but cannot raise a signal, so a
        command-interrupt on a pipe session is reported honestly by the caller."""
        mapping = {"c": "\x03", "d": "\x04", "z": "\x1a"}
        char = mapping.get(str(key).strip().lower())
        if char is None:
            return False
        return self.write_raw(char)

    def _wait_marker(self, timeout: int) -> bool:
        """Wait for the completion sentinel RESULT (a path) in a PTY stream.

        The shell echoes the command (whose sentinel tail is a variable
        expression, not a path); only the real result carries a path. Waiting for
        the path is what distinguishes "the command came back" from "the shell
        merely echoed what we typed".
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            window = self.buffer.read(since_sequence=self._marker_scan_seq)
            self._marker_scan_seq = window["nextSequence"]
            text = window["text"]
            if _MARK_PREFIX in text:
                path = _marker_path(text)
                if path is not None:
                    self.cwd = path
                    self.updated_at = now_iso()
                    self._live.done.set()
                    return True
            if not self.is_alive():
                return True
            time.sleep(0.05)
        return False

    def _wait_quiet(self, timeout: int) -> bool:
        deadline = time.monotonic() + timeout
        last_seq = self.buffer.snapshot()["lastSequence"]
        last_change = time.monotonic()
        while time.monotonic() < deadline:
            seq = self.buffer.snapshot()["lastSequence"]
            if seq != last_seq:
                last_seq = seq
                last_change = time.monotonic()
            elif time.monotonic() - last_change >= _QUIET_S:
                return True
            if not self.is_alive():
                return True
            time.sleep(0.05)
        return False

    # ── State ─────────────────────────────────────────────────────────────────

    def resize(self, rows: int, columns: int) -> bool:
        self.rows = max(1, int(rows))
        self.columns = max(1, int(columns))
        self.updated_at = now_iso()
        if self.pty and self._live.pty is not None:
            return self._live.pty.resize(self.rows, self.columns)
        return False

    def is_alive(self) -> bool:
        if self._closed:
            return False
        if self.pty and self._live.pty is not None:
            return self._live.pty.isalive()
        proc = self._live.proc
        return bool(proc is not None and proc.poll() is None)

    def read(self, **kwargs: Any) -> dict[str, Any]:
        return self.buffer.read(**kwargs)

    def close(self, *, force: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self.status = "closed"
        self.updated_at = now_iso()
        if self.pty and self._live.pty is not None:
            self._live.pty.terminate(force=force)
        proc = self._live.proc
        if proc is not None and proc.poll() is None:
            try:
                if force:
                    proc.kill()
                else:
                    proc.terminate()
            except OSError:
                pass
        self._live.alive = False
        self._notify("session closed")

    def info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            runtime=self.runtime,
            shell=self.shell.name,
            pid=self.pid,
            cwd=self.cwd,
            status=("running" if self.is_alive() else self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
            rows=self.rows,
            columns=self.columns,
            env_profile=dict(self.env_profile),
            workspace_id=self.workspace_id,
            agent_id=self.agent_id,
            owner=self.owner,
            pty=self.pty,
        )


class SessionStartError(RuntimeError):
    """Raised when a shell process cannot be started at all."""

    code = "SHELL_START_FAILED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SessionManager:
    """Owns the live sessions and (optionally) their persisted metadata."""

    def __init__(self, *, store: Optional[Any] = None, on_event: Optional[Callable[[str, dict[str, Any]], None]] = None) -> None:
        self._sessions: dict[str, ShellSession] = {}
        self._lock = threading.Lock()
        self._store = store
        self._on_event = on_event

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001 - an event must never break a session
                pass

    def open(
        self,
        *,
        shell_name: Optional[str] = None,
        runtime: str = "local",
        cwd: str,
        env: Optional[dict[str, str]] = None,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        owner: Optional[str] = None,
        rows: int = 24,
        columns: int = 80,
        use_pty: bool = True,
    ) -> ShellSession:
        shell = resolve_shell(shell_name)
        if shell is None:
            raise SessionStartError("the requested shell is not available on this computer")
        session_id = "term_" + uuid.uuid4().hex[:12]
        session = ShellSession(
            session_id=session_id, shell=shell, runtime=runtime, cwd=cwd,
            env=env or {}, workspace_id=workspace_id, agent_id=agent_id,
            owner=owner, rows=rows, columns=columns, use_pty=use_pty,
        )
        with self._lock:
            self._sessions[session_id] = session
        if self._store is not None:
            try:
                self._store.save_session(session.info().to_dict())
            except Exception:  # noqa: BLE001
                pass
        self._emit("session.created", {"sessionId": session_id, "shell": shell.name, "pid": session.pid, "pty": session.pty})
        self._emit("session.ready", {"sessionId": session_id, "cwd": session.cwd})
        return session

    def get(self, session_id: str) -> Optional[ShellSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list(
        self, *, workspace_id: Optional[str] = None, agent_id: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        out: list[dict[str, Any]] = []
        for session in sessions:
            if workspace_id is not None and session.workspace_id != workspace_id:
                continue
            if agent_id is not None and session.agent_id != agent_id:
                continue
            if owner is not None and session.owner != owner:
                continue
            out.append(session.info().to_dict())
        return out

    def close(self, session_id: str, *, force: bool = True) -> bool:
        session = self.get(session_id)
        if session is None:
            return False
        session.close(force=force)
        if self._store is not None:
            try:
                self._store.mark_session_closed(session_id)
            except Exception:  # noqa: BLE001
                pass
        self._emit("session.closed", {"sessionId": session_id})
        with self._lock:
            self._sessions.pop(session_id, None)
        return True

    def close_all(self) -> int:
        with self._lock:
            ids = list(self._sessions)
        for session_id in ids:
            self.close(session_id)
        return len(ids)

    # ── Native fast paths (no process spawn) ───────────────────────────────────

    @staticmethod
    def handle_session_builtin(session: ShellSession, command: str, workspace_root: Path) -> Optional[tuple[str, dict[str, Any]]]:
        """Handle a standalone `cd` / `export` / `set` / `pwd` without spawning.

        Mirrors the persistent-cwd behaviour of `code/terminal_tools.py`. Returns
        ``(text, data)`` or None when the command is not a builtin.
        """
        try:
            tokens = shlex.split(command.strip(), posix=True)
        except ValueError:
            return None
        if not tokens:
            return None
        head = tokens[0].casefold()
        root = Path(workspace_root).resolve()
        if head in ("cd", "chdir"):
            target = tokens[1] if len(tokens) > 1 else "."
            base = Path(session.cwd or root)
            candidate = base if target in ("~",) else (base / target if not os.path.isabs(target) else Path(target))
            candidate = candidate.resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                return ("Refused: that folder is outside the workspace.", {"status": "refused", "code": "PATH_ESCAPE"})
            if not candidate.is_dir():
                return (f"There is no folder `{target}` here.", {"status": "not_found", "cwd": str(candidate)})
            session.cwd = str(candidate)
            session.updated_at = now_iso()
            return (f"cwd is now {candidate}", {"status": "ok", "cwd": str(candidate)})
        if head in ("export", "set") and len(tokens) > 1:
            changed = 0
            for assignment in tokens[1:]:
                if "=" in assignment:
                    key, _, value = assignment.partition("=")
                    session.env_profile[key] = value
                    changed += 1
            return (f"Set {changed} variable(s) for this session.", {"status": "ok", "envKeys": sorted(session.env_profile)})
        if head == "pwd":
            return (str(session.cwd), {"status": "ok", "cwd": str(session.cwd)})
        return None


__all__ = ["SessionManager", "SessionStartError", "ShellSession"]
