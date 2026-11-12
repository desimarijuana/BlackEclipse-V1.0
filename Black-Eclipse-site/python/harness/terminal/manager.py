"""The TerminalManager facade — one backend for agent tools AND the UI.

Everything the terminal subsystem can do is reachable through this object:

  * `execute_command`  — one-shot foreground command (bounded, cancellable);
  * sessions            — persistent shells (delegated to `SessionManager`);
  * processes           — background processes (delegated to `ProcessManager`);
  * ports               — listening ports and conflicts;
  * capabilities        — what this host can actually do;
  * recovery            — reconcile persisted state on boot.

The agent tools in `terminal/tools.py` and the FastAPI router in
`terminal/router.py` are thin adapters over THIS object, so the agent and the UI
can never disagree about a process's state.
"""

from __future__ import annotations

import os
import shlex
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ..code import sandbox as sandbox_mod
from ..code.sandbox import RunSpec, SandboxUnavailable
from ..persistence import now_iso
from . import port_manager, redaction, shell_detect
from .buffer import truncate_for_model
from .process_manager import ProcessManager
from .recovery import RecoveryManager
from .runtimes import ExecutionRuntime, RuntimeUnavailable, describe_runtimes, select_runtime
from .session import SessionManager
from .types import (
    CommandError,
    CommandResult,
    ErrorCategory,
    ProcessState,
    RuntimeName,
)

DEFAULT_TIMEOUT_MS = 120_000
MAX_TIMEOUT_MS = 900_000
_STREAM_TAIL_LINES = 200

#: The owner of an idle, pre-warmed shell. It is adopted by the first UI open so
#: the shell is already running and the prompt appears instantly.
WARM_OWNER = "__eclipse_warm__"


def _classify_result(exit_code: Optional[int], output: str, timed_out: bool) -> Optional[CommandError]:
    """Normalize a failed execution into a structured error. Never a bare string."""
    if timed_out:
        return CommandError(
            type="COMMAND_TIMEOUT", category=ErrorCategory.TIMEOUT.value,
            message="That took too long and was stopped.", exit_code=exit_code, stderr=output[-2000:],
        )
    if exit_code in (None, 0):
        return None
    lowered = output.casefold()
    if exit_code in (127, 9009) or "not recognized as an internal or external command" in lowered or "command not found" in lowered:
        category = ErrorCategory.COMMAND_NOT_FOUND.value
    elif "permission denied" in lowered or "access is denied" in lowered:
        category = ErrorCategory.PERMISSION_DENIED.value
    elif "cannot find module" in lowered or "modulenotfounderror" in lowered or "no module named" in lowered:
        category = ErrorCategory.DEPENDENCY_ERROR.value
    elif "eaddrinuse" in lowered or "address already in use" in lowered or "only one usage of each socket address" in lowered:
        category = ErrorCategory.PORT_CONFLICT.value
    elif "syntaxerror" in lowered or "compilation" in lowered or "error ts" in lowered:
        category = ErrorCategory.COMPILATION_ERROR.value
    elif "connection refused" in lowered or "getaddrinfo" in lowered or "network is unreachable" in lowered:
        category = ErrorCategory.NETWORK_ERROR.value
    else:
        category = ErrorCategory.COMMAND_FAILED.value
    return CommandError(
        type="COMMAND_FAILED", category=category,
        message=f"The command stopped with exit code {exit_code}.",
        exit_code=exit_code, stderr=output[-2000:],
    )


class TerminalManager:
    """The single terminal runtime shared by tools and the UI."""

    def __init__(
        self,
        *,
        store: Optional[Any] = None,
        on_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self._store = store
        self._on_event = on_event
        self.sessions = SessionManager(store=store, on_event=on_event)
        self.processes = ProcessManager(
            store=store, on_event=on_event,
            port_resolver=self._ports_for_pid,
        )
        self.recovery = RecoveryManager(store, on_event=on_event)
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ── Events / capabilities ───────────────────────────────────────────────────

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001
                pass

    def capabilities(self) -> dict[str, Any]:
        caps = shell_detect.capabilities().to_dict()
        caps["runtimesDetailed"] = describe_runtimes()
        return caps

    def runtime_names(self) -> list[str]:
        return shell_detect.capabilities().runtimes  # type: ignore[return-value]

    def _runtime(self, name: str, distro: Optional[str] = None) -> ExecutionRuntime:
        return select_runtime(name, distro=distro)

    # ── Foreground execution ─────────────────────────────────────────────────────

    def execute_command(
        self,
        *,
        command: str,
        cwd: str,
        shell: Optional[str] = None,
        runtime: str = "local",
        shell_mode: bool = True,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        env: Optional[dict[str, str]] = None,
        session_env: Optional[dict[str, str]] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        purpose: Optional[str] = None,
        distro: Optional[str] = None,
    ) -> CommandResult:
        """Run one command and wait (bounded). Never blocks the whole runtime.

        Callers run this in a worker thread; `cancel(execution_id)` interrupts it
        from another thread through the sandbox's cancel event.
        """
        execution_id = "exec_" + uuid.uuid4().hex[:12]
        directory = Path(str(cwd))
        if not directory.is_dir():
            return CommandResult(
                execution_id=execution_id, status="failed", exit_code=None, stdout="", stderr="",
                duration_ms=0, timed_out=False, truncated=False, cwd=str(cwd), runtime=runtime,
                command=redaction.redact_command(command),
                error=CommandError(
                    type="COMMAND_FAILED", category=ErrorCategory.WORKING_DIRECTORY_NOT_FOUND.value,
                    message="That folder is not there.", exit_code=None,
                ),
            )
        # C6: the executor itself honours a configured sandbox profile. A profile
        # this host cannot enforce is a refusal, not a silent local fallback.
        from ..security.profiles import executor_guard  # noqa: PLC0415

        profile_refusal, profile_plan = executor_guard()
        if profile_refusal:
            self.emit("sandbox.profile.blocked", {
                "executionId": execution_id,
                "profile": profile_plan.profile.value if profile_plan else None,
                "missing": list(profile_plan.missing) if profile_plan else [],
                "reason": profile_refusal,
            })
            return CommandResult(
                execution_id=execution_id, status="unavailable", exit_code=None,
                stdout="", stderr="", duration_ms=0, timed_out=False, truncated=False,
                cwd=str(cwd), runtime=runtime,
                command=redaction.redact_command(command),
                error=CommandError(
                    type="SANDBOX_UNAVAILABLE",
                    category=ErrorCategory.RUNTIME_UNAVAILABLE.value,
                    message=profile_refusal,
                ),
            )
        try:
            exec_runtime = self._runtime(runtime, distro=distro)
            if shell_mode:
                argv = exec_runtime.build_argv(command, shell=shell, cwd=str(directory))
            else:
                # No-shell mode: the code profile's `terminal_run` promise. The
                # command is tokenized into an argv and executed directly, so a
                # `; rm -rf` or `$(...)` is inert text, not a second command.
                argv = shlex.split(command, posix=True)
            runtime_env = exec_runtime.extra_env()
        except RuntimeUnavailable as exc:
            category = (ErrorCategory.NOT_IMPLEMENTED.value if exc.code == "NOT_IMPLEMENTED" else ErrorCategory.RUNTIME_UNAVAILABLE.value)
            self.emit("runtime.unavailable", {"runtime": runtime, "code": exc.code})
            return CommandResult(
                execution_id=execution_id, status="unavailable", exit_code=None, stdout="", stderr="",
                duration_ms=0, timed_out=False, truncated=False, cwd=str(directory), runtime=runtime,
                command=redaction.redact_command(command),
                error=CommandError(type="RUNTIME_UNAVAILABLE", category=category, message=exc.reason),
            )
        timeout_s = max(1, min(int(timeout_ms // 1000 or 1), MAX_TIMEOUT_MS // 1000))
        extra = dict(runtime_env or {})
        extra.update(session_env or {})
        extra.update(env or {})
        try:
            spec = RunSpec(
                argv=argv, cwd=directory, env=sandbox_mod.build_env(extra or None),
                timeout_s=timeout_s, output_cap_bytes=sandbox_mod.MAX_OUTPUT_CAP_BYTES, network=False,
            )
        except (ValueError, OSError) as exc:
            return CommandResult(
                execution_id=execution_id, status="failed", exit_code=None, stdout="", stderr="",
                duration_ms=0, timed_out=False, truncated=False, cwd=str(directory), runtime=runtime,
                command=redaction.redact_command(command),
                error=CommandError(type="COMMAND_FAILED", category=ErrorCategory.INVALID_ARGUMENT.value, message=str(exc)),
            )
        cancel_event = threading.Event()
        with self._lock:
            self._cancel[execution_id] = cancel_event
        self.emit("command.started", {"executionId": execution_id, "runtime": runtime, "shell": shell})
        try:
            sandbox_mod.select_backend()
        except SandboxUnavailable as exc:
            with self._lock:
                self._cancel.pop(execution_id, None)
            self.emit("runtime.unavailable", {"runtime": "sandbox", "code": "SANDBOX_UNAVAILABLE"})
            return CommandResult(
                execution_id=execution_id, status="unavailable", exit_code=None, stdout="", stderr="",
                duration_ms=0, timed_out=False, truncated=False, cwd=str(directory), runtime=runtime,
                command=redaction.redact_command(command),
                error=CommandError(type="RUNTIME_UNAVAILABLE", category=ErrorCategory.RUNTIME_UNAVAILABLE.value, message=str(exc)),
            )
        raw = sandbox_mod.run(spec, cancel_event=cancel_event)
        with self._lock:
            self._cancel.pop(execution_id, None)
        stdout = redaction.redact(raw.output)
        shown, truncated = truncate_for_model(stdout)
        status = "cancelled" if raw.cancelled else ("timed_out" if raw.timed_out else ("ok" if raw.exit_code == 0 else "failed"))
        error = None if status == "cancelled" else _classify_result(raw.exit_code, stdout, raw.timed_out)
        result = CommandResult(
            execution_id=execution_id, status=status, exit_code=raw.exit_code,
            stdout=shown, stderr="", duration_ms=raw.duration_ms, timed_out=raw.timed_out,
            truncated=truncated or raw.truncated, cwd=str(directory), runtime=runtime,
            command=redaction.redact_command(command), error=error,
        )
        event = {"command.timed_out": "command.timed_out", "command.completed": "command.completed"}.get(
            f"command.{status}", "command.completed"
        )
        self.emit(event, {
            "executionId": execution_id, "runtime": runtime, "exitCode": raw.exit_code,
            "durationMs": raw.duration_ms, "status": status, "timedOut": raw.timed_out,
            "category": error.category if error else None,
        })
        if self._store is not None:
            try:
                self._store.record_command({
                    "id": execution_id, "sessionId": None, "processId": None,
                    "command": redaction.redact_command(command), "cwd": str(directory),
                    "runtime": runtime, "shell": shell, "exitCode": raw.exit_code,
                    "status": status, "durationMs": raw.duration_ms, "agentId": agent_id,
                    "runId": run_id, "taskId": task_id, "purpose": purpose, "createdAt": now_iso(),
                })
            except Exception:  # noqa: BLE001
                pass
        return result

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running foreground command. Returns whether it was running."""
        with self._lock:
            event = self._cancel.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    # ── Sessions ─────────────────────────────────────────────────────────────────

    def open_shell(self, **kwargs: Any) -> dict[str, Any]:
        session = self.sessions.open(**kwargs)
        return session.info().to_dict()

    def attach_or_open_shell(self, *, owner: str, **kwargs: Any) -> dict[str, Any]:
        """Reuse an existing live session for ``owner``, or open a new one.

        A UI terminal calls this so reopening the panel (or reloading the page)
        reattaches to the same shell instead of leaking a new PTY each time. Only
        sessions owned by ``owner`` and still alive are reused. When the owner has
        no session yet, a PRE-WARMED idle shell is adopted if one is available, so
        the first open is instant instead of paying the shell's startup cost.
        """
        for info in self.sessions.list(owner=owner):
            existing = self.sessions.get(info["sessionId"])
            if existing is not None and existing.is_alive():
                return existing.info().to_dict()
        wanted = kwargs.get("shell_name")
        for info in self.sessions.list(owner=WARM_OWNER):
            warm = self.sessions.get(info["sessionId"])
            if warm is not None and warm.is_alive() and (not wanted or warm.shell.name == wanted):
                warm.owner = owner
                if self._store is not None:
                    try:
                        self._store.update_session(warm.session_id, owner=owner, updatedAt=now_iso())
                    except Exception:  # noqa: BLE001
                        pass
                return warm.info().to_dict()
        return self.sessions.open(owner=owner, **kwargs).info().to_dict()

    def warm_shell(self, *, cwd: Optional[str] = None) -> Optional[str]:
        """Open (once) an idle shell the first UI open can adopt instantly.

        Called at boot. It is a normal persistent session the user never sees
        unless an open adopts it. Best-effort: a failure is a diagnostic, never a
        boot blocker.
        """
        try:
            for info in self.sessions.list(owner=WARM_OWNER):
                existing = self.sessions.get(info["sessionId"])
                if existing is not None and existing.is_alive():
                    return existing.session_id
            if cwd is None:
                from ..code.workspace import default_root  # noqa: PLC0415

                root = default_root()
                cwd = str(root) if root else os.getcwd()
            session = self.sessions.open(owner=WARM_OWNER, cwd=cwd)
            return session.session_id
        except Exception:  # noqa: BLE001 - prewarm must never break boot
            return None

    def close_shell(self, session_id: str) -> bool:
        return self.sessions.close(session_id)

    def list_shells(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.sessions.list(**kwargs)

    def get_shell(self, session_id: str) -> Optional[dict[str, Any]]:
        session = self.sessions.get(session_id)
        return session.info().to_dict() if session else None

    def write_shell_input(self, session_id: str, data: str, *, newline: bool = True) -> bool:
        session = self.sessions.get(session_id)
        return session.write_input(data, newline=newline) if session else False

    def read_shell_output(self, session_id: str, **kwargs: Any) -> Optional[dict[str, Any]]:
        session = self.sessions.get(session_id)
        return session.read(**kwargs) if session else None

    def resize_shell(self, session_id: str, rows: int, columns: int) -> bool:
        session = self.sessions.get(session_id)
        return session.resize(rows, columns) if session else False

    def run_in_shell(self, session_id: str, command: str, *, timeout_s: Optional[int] = None, workspace_root: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Drive one command in a persistent session.

        A `cd`/`export` change must reach the REAL shell, not just our tracking:
        the session's cwd is read back from the shell's own prompt (the sentinel)
        and then confined to the workspace root. A command that moved the shell
        outside the workspace is refused after the fact and the shell is returned
        to the root, so the session can never wander out of the project.
        """
        session = self.sessions.get(session_id)
        if session is None:
            return None
        result = session.send(command, timeout_s=timeout_s)
        if result.get("dead"):
            return {"text": "", "data": {"status": "not_found"}, "timedOut": False}

        head = command.strip().split(None, 1)[0].casefold() if command.strip() else ""
        is_builtin = head in ("cd", "chdir", "export", "set", "pwd")
        new_cwd = result.get("cwd")
        if workspace_root and new_cwd:
            root = Path(workspace_root).resolve()
            try:
                candidate = Path(new_cwd).resolve()
                candidate.relative_to(root)
            except (ValueError, OSError):
                # The shell left the workspace: move it back and report a refusal.
                back = f'cd "{root}"' if os.name == "nt" else f'cd "{root}"'
                session.send(back, timeout_s=10)
                return {
                    "text": "Refused: that folder is outside the workspace.",
                    "data": {"status": "refused", "code": "PATH_ESCAPE"},
                    "timedOut": False,
                }
            session.cwd = str(candidate)
        if is_builtin:
            result["data"] = {"status": "ok", "cwd": session.cwd}
            if not result.get("text"):
                result["text"] = f"cwd is now {session.cwd}" if head in ("cd", "chdir", "pwd") else "variables set."
        self.emit("session.output", {"sessionId": session_id, "endSequence": result.get("endSequence")})
        return result

    def send_control(self, session_id: str, key: str) -> bool:
        session = self.sessions.get(session_id)
        return session.send_control(key) if session else False

    def send_shell_raw(self, session_id: str, data: str) -> bool:
        """Write raw bytes to the shell's stdin (a keystroke, a paste, Enter).

        This is what a real terminal UI uses: every key goes straight to the PTY,
        so interactive programs (vim, a REPL, a prompt) work. The agent tools use
        the higher-level `run_in_shell`; the UI uses this.
        """
        session = self.sessions.get(session_id)
        return session.write_raw(data) if session else False

    def stream_shell_output(self, session_id: str, *, since_sequence: int = 0, timeout_s: float = 15.0) -> Optional[dict[str, Any]]:
        """Long-poll for new session output, without ANSI stripping.

        The UI renders the raw stream (a terminal must); it filters the sentinel
        out for display.
        """
        session = self.sessions.get(session_id)
        if session is None:
            return None
        window = session.wait_for_output(since_sequence, timeout_s)
        window["running"] = session.is_alive()
        window["cwd"] = session.cwd
        return window

    # ── Background processes ──────────────────────────────────────────────────────

    def start_process(
        self,
        *,
        command: str,
        cwd: str,
        shell: Optional[str] = None,
        runtime: str = "local",
        env: Optional[dict[str, str]] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        purpose: Optional[str] = None,
        distro: Optional[str] = None,
    ) -> dict[str, Any]:
        """Start a background process. Returns a record immediately (may be FAILED)."""
        directory = Path(str(cwd))
        try:
            exec_runtime = self._runtime(runtime, distro=distro)
            argv = exec_runtime.build_argv(command, shell=shell, cwd=str(directory))
            runtime_env = exec_runtime.extra_env()
        except RuntimeUnavailable as exc:
            return {
                "processId": None, "state": "FAILED", "runtime": runtime,
                "error": {"type": "RUNTIME_UNAVAILABLE", "category": "RUNTIME_UNAVAILABLE" if exc.code != "NOT_IMPLEMENTED" else "NOT_IMPLEMENTED", "message": exc.reason},
            }
        merged_env = dict(runtime_env or {})
        merged_env.update(env or {})
        info = self.processes.start_process(
            argv=argv, cwd=str(directory), env=sandbox_mod.build_env(merged_env or None),
            command=command, runtime=runtime, shell=(shell or (exec_runtime.name if runtime == "local" else runtime)),
            workspace_id=workspace_id, agent_id=agent_id, run_id=run_id, task_id=task_id, purpose=purpose,
        )
        return info

    def stop_process(self, process_id: str) -> bool:
        return self.processes.stop(process_id)

    def kill_process(self, process_id: str) -> bool:
        return self.processes.kill(process_id)

    def restart_process(self, process_id: str) -> Optional[dict[str, Any]]:
        return self.processes.restart(process_id)

    def get_process(self, process_id: str) -> Optional[dict[str, Any]]:
        info = self.processes.get(process_id)
        if info is None:
            return None
        pid = info.get("pid")
        if pid:
            info["ports"] = self._ports_for_pid(int(pid))
        return info

    def list_processes(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.processes.list(**kwargs)

    def read_process_output(self, process_id: str, **kwargs: Any) -> Optional[dict[str, Any]]:
        return self.processes.read_output(process_id, **kwargs)

    def write_process_input(self, process_id: str, data: str, *, newline: bool = True) -> bool:
        return self.processes.write_input(process_id, data, newline=newline)

    def send_signal(self, process_id: str, signal: str) -> dict[str, Any]:
        return self.processes.send_signal(process_id, signal)

    def process_tree(self, process_id: str) -> Optional[dict[str, Any]]:
        return self.processes.process_tree(process_id)

    # ── Ports ─────────────────────────────────────────────────────────────────────

    def _ports_for_pid(self, pid: int) -> list[int]:
        """Ports owned by ``pid`` or ANY of its OS descendants.

        A shell wrapper (PowerShell/CMD) does not itself listen; the dev server it
        launched does, as a child. So a managed process's ports are collected over
        its whole tree — the same tree `kill_tree` stops.
        """
        from . import proctree  # noqa: PLC0415

        targets = {int(pid)} | set(proctree.descendants(pid))
        return [p.port for p in port_manager.list_listening_ports() if p.pid in targets]

    def list_ports(self, *, process_index: Optional[dict[int, str]] = None) -> list[dict[str, Any]]:
        ports = port_manager.list_listening_ports(process_index=process_index)
        return [p.to_dict() for p in ports]

    def port_summary(self) -> dict[str, Any]:
        return port_manager.summarize(port_manager.list_listening_ports())

    def find_port_conflict(self, port: int) -> Optional[dict[str, Any]]:
        conflict = port_manager.find_conflict(port)
        return conflict.to_dict() if conflict else None

    # ── Shutdown ───────────────────────────────────────────────────────────────────

    def close_all(self) -> dict[str, Any]:
        sessions = self.sessions.close_all()
        procs = 0
        for info in self.list_processes():
            if info["state"] not in ("EXITED", "CRASHED", "STOPPED", "KILLED", "FAILED", "TIMEOUT"):
                if self.stop_process(info["processId"]):
                    procs += 1
        return {"sessions": sessions, "processes": procs}


__all__ = ["DEFAULT_TIMEOUT_MS", "MAX_TIMEOUT_MS", "TerminalManager"]
