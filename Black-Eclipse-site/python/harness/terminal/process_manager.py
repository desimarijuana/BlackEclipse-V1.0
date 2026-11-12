"""Background process management — the authoritative lifecycle.

Every background process is registered here, not in the UI. The UI subscribes;
the agent calls tools; both read the same records. This module owns:

  * the deterministic state machine (`CREATED → STARTING → RUNNING → …`);
  * stdout/stderr pumped into SEPARATE sequenced ring buffers (never merged);
  * stdin, signals and process-tree termination;
  * crash detection (a non-zero exit is CRASHED, with the last output kept);
  * restart with the original configuration preserved;
  * an optional health check (PID alive + port listening + optional HTTP).

It never infers state from "does a PID exist" — the monitor thread records the
real exit and the transition is applied once, under a lock. Long-running
processes have NO ordinary execution timeout; only an explicit stop/kill or a
crash ends them.
"""

from __future__ import annotations

import signal as signal_mod
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..code.sandbox import RunSpec, SandboxUnavailable
from ..persistence import now_iso
from . import redaction
from .buffer import RingBuffer
from . import proctree
from .resources import ResourceLimits
from .spawn import SpawnedProcess, spawn_process
from .types import (
    TERMINAL_STATES,
    CommandError,
    ErrorCategory,
    ProcessState,
    SignalName,
    StreamName,
)


def _classify_start_error(reason: str) -> CommandError:
    lowered = reason.casefold()
    if "no such file" in lowered or "cannot find" in lowered or "not recognized" in lowered:
        return CommandError(
            type="COMMAND_FAILED", category=ErrorCategory.COMMAND_NOT_FOUND.value,
            message="That program is not installed on this computer.", stderr=reason,
        )
    return CommandError(
        type="PROCESS_FAILED", category=ErrorCategory.RUNTIME_ERROR.value,
        message="The process could not be started.", stderr=reason,
    )


@dataclass
class _Record:
    """A tracked process: its metadata, its live handle and its buffers."""

    process_id: str
    pid: Optional[int]
    command: str
    cwd: str
    runtime: str
    shell: str
    argv: list[str]
    env: dict[str, str]
    created_at: str
    updated_at: str
    state: str = ProcessState.CREATED.value
    started_at: Optional[str] = None
    exit_at: Optional[str] = None
    exit_code: Optional[int] = None
    ports: tuple[int, ...] = ()
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    purpose: Optional[str] = None
    parent_pid: Optional[int] = None
    last_error: Optional[CommandError] = None
    health: Optional[dict[str, Any]] = None
    buffer: RingBuffer = field(default_factory=RingBuffer)
    spawned: Optional[SpawnedProcess] = None
    stop_requested: bool = False
    timed_out: bool = False
    runaway: Optional[dict[str, Any]] = None

    def info(self) -> dict[str, Any]:
        return {
            "processId": self.process_id,
            "pid": self.pid,
            "parentPid": self.parent_pid,
            "command": self.command,
            "cwd": self.cwd,
            "runtime": self.runtime,
            "shell": self.shell,
            "state": self.state,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "startedAt": self.started_at,
            "exitAt": self.exit_at,
            "exitCode": self.exit_code,
            "ports": list(self.ports),
            "workspaceId": self.workspace_id,
            "agentId": self.agent_id,
            "runId": self.run_id,
            "taskId": self.task_id,
            "purpose": self.purpose,
            "health": self.health,
            "runaway": self.runaway,
            "error": self.last_error.to_dict() if self.last_error else None,
        }


# Signals that mean "end the process". SIGSTOP/SIGCONT are pause/resume where the
# platform supports them; Windows has no equivalent and reports NOT_IMPLEMENTED.
_END_SIGNALS = {SignalName.TERM.value, SignalName.KILL.value, SignalName.INT.value}


class ProcessManager:
    """Owns the live background processes and their persisted records."""

    def __init__(
        self,
        *,
        store: Optional[Any] = None,
        on_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
        port_resolver: Optional[Callable[[int], list[int]]] = None,
    ) -> None:
        self._procs: dict[str, _Record] = {}
        self._by_pid: dict[int, str] = {}
        self._lock = threading.RLock()
        self._store = store
        self._on_event = on_event
        self._port_resolver = port_resolver
        self._limits = ResourceLimits.from_env()
        self._next_pid_hint = 1

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    def _active_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._procs.values() if r.state not in TERMINAL_STATES)

    # ── Event / persistence seams ──────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001 - an event must never break a process
                pass

    def _persist(self, record: _Record) -> None:
        if self._store is None:
            return
        try:
            self._store.upsert_process(record.info())
        except Exception:  # noqa: BLE001 - a record failure must not kill the process
            pass

    # ── Start ──────────────────────────────────────────────────────────────────

    def start_process(
        self,
        *,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        command: str,
        runtime: str = "local",
        shell: str = "argv",
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        purpose: Optional[str] = None,
        parent_pid: Optional[int] = None,
    ) -> dict[str, Any]:
        """Start a background process and return its record immediately.

        A runaway guard refuses to exceed the configured number of ACTIVE
        processes; it is a structured refusal, never an automatic kill of an
        existing process.
        """
        if self._active_count() >= self._limits.max_processes:
            self._emit("process.refused", {"reason": "PROCESS_LIMIT", "limit": self._limits.max_processes})
            return {
                "processId": None, "state": "FAILED", "runtime": runtime,
                "error": {
                    "type": "PROCESS_LIMIT", "category": ErrorCategory.RUNTIME_ERROR.value,
                    "message": f"too many processes are already running (limit {self._limits.max_processes})",
                },
            }
        # C6: a configured profile the host cannot enforce refuses the spawn here
        # too, so a caller that bypassed the gateway still cannot run unisolated.
        from ..security.profiles import executor_guard  # noqa: PLC0415

        profile_refusal, profile_plan = executor_guard()
        if profile_refusal:
            self._emit("sandbox.profile.blocked", {
                "profile": profile_plan.profile.value if profile_plan else None,
                "missing": list(profile_plan.missing) if profile_plan else [],
                "reason": profile_refusal,
            })
            return {
                "processId": None, "state": "FAILED", "runtime": runtime,
                "error": {
                    "type": "SANDBOX_UNAVAILABLE",
                    "category": ErrorCategory.RUNTIME_UNAVAILABLE.value,
                    "message": profile_refusal,
                },
            }
        process_id = "proc_" + uuid.uuid4().hex[:12]
        created = now_iso()
        record = _Record(
            process_id=process_id, pid=None, command=command, cwd=str(cwd),
            runtime=runtime, shell=shell, argv=list(argv), env=dict(env),
            created_at=created, updated_at=created, workspace_id=workspace_id,
            agent_id=agent_id, run_id=run_id, task_id=task_id, purpose=purpose,
            parent_pid=parent_pid,
        )
        with self._lock:
            self._procs[process_id] = record
        self._emit("process.created", {"processId": process_id, "command": redaction.redact_command(command)})
        self._persist(record)

        record.state = ProcessState.STARTING.value
        record.updated_at = now_iso()
        try:
            spec = RunSpec(
                argv=list(argv), cwd=Path(cwd), env=dict(env),
                timeout_s=0, output_cap_bytes=0, network=False,
            )
            spawned = spawn_process(spec)
        except (SandboxUnavailable, OSError, ValueError) as exc:
            record.state = ProcessState.FAILED.value
            record.last_error = _classify_start_error(str(exc))
            record.updated_at = now_iso()
            record.buffer.note(f"failed to start: {exc}\n", now_iso())
            self._persist(record)
            self._emit("process.failed", {"processId": process_id, "reason": str(exc)})
            return record.info()

        record.spawned = spawned
        record.pid = spawned.pid
        record.state = ProcessState.RUNNING.value
        record.started_at = now_iso()
        record.updated_at = record.started_at
        with self._lock:
            self._by_pid[spawned.pid] = process_id
        record.buffer.note(f"started (pid {spawned.pid})\n", now_iso())
        self._persist(record)
        self._emit("process.started", {"processId": process_id, "pid": spawned.pid, "command": redaction.redact_command(command)})

        threading.Thread(target=self._pump, args=(record, spawned.proc.stdout, StreamName.STDOUT.value), daemon=True).start()
        threading.Thread(target=self._pump, args=(record, spawned.proc.stderr, StreamName.STDERR.value), daemon=True).start()
        threading.Thread(target=self._monitor, args=(record,), daemon=True).start()
        return record.info()

    # ── Pumps / monitor ─────────────────────────────────────────────────────────

    def _pump(self, record: _Record, stream: Any, stream_name: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                chunks = record.buffer.append(stream_name, line, now_iso())
                for chunk in chunks:
                    self._emit("process.output", {
                        "processId": record.process_id, "stream": stream_name,
                        "sequence": chunk.sequence, "data": redaction.redact(chunk.data),
                    })
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    def _monitor(self, record: _Record) -> None:
        spawned = record.spawned
        if spawned is None:
            return
        rc = spawned.proc.wait()
        with self._lock:
            if record.state in TERMINAL_STATES:
                return
            record.exit_code = rc
            record.exit_at = now_iso()
            record.updated_at = record.exit_at
            if record.timed_out:
                record.state = ProcessState.TIMEOUT.value
            elif record.stop_requested:
                record.state = ProcessState.STOPPED.value
            elif rc == 0:
                record.state = ProcessState.EXITED.value
            else:
                record.state = ProcessState.CRASHED.value
            if record.state == ProcessState.CRASHED.value:
                record.last_error = CommandError(
                    type="PROCESS_CRASH",
                    category=(ErrorCategory.PROCESS_CRASH.value if rc not in (127, 9009) else ErrorCategory.COMMAND_NOT_FOUND.value),
                    message=f"The process ended on its own with code {rc}.",
                    exit_code=rc,
                )
            tail = record.buffer.read(tail=40)["text"]
            state = record.state
        spawned.release()
        record.buffer.note(f"exited (code {rc}, {state})\n", now_iso())
        self._persist(record)
        if state == ProcessState.EXITED.value:
            self._emit("process.exited", {"processId": record.process_id, "exitCode": rc, "durationMs": self._duration_ms(record)})
        elif state == ProcessState.CRASHED.value:
            self._emit("process.crashed", {
                "processId": record.process_id, "exitCode": rc, "durationMs": self._duration_ms(record),
                "lastOutput": redaction.redact(tail),
            })
        elif state == ProcessState.TIMEOUT.value:
            self._emit("process.crashed", {"processId": record.process_id, "exitCode": rc, "reason": "timeout"})
        else:
            self._emit("process.stopped", {"processId": record.process_id, "exitCode": rc})

    @staticmethod
    def _duration_ms(record: _Record) -> int:
        if not record.started_at:
            return 0
        try:
            from datetime import datetime

            started = datetime.fromisoformat(record.started_at)
            ended = datetime.fromisoformat(record.exit_at or now_iso())
            return int((ended - started).total_seconds() * 1000)
        except Exception:  # noqa: BLE001
            return 0

    # ── Queries ─────────────────────────────────────────────────────────────────

    def get(self, process_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            record = self._procs.get(process_id)
            return record.info() if record else None

    def _record(self, process_id: str) -> Optional[_Record]:
        with self._lock:
            return self._procs.get(process_id)

    def list(self, *, workspace_id: Optional[str] = None, agent_id: Optional[str] = None, state: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._procs.values())
        out = []
        for record in records:
            if workspace_id is not None and record.workspace_id != workspace_id:
                continue
            if agent_id is not None and record.agent_id != agent_id:
                continue
            if state is not None and record.state != state:
                continue
            out.append(record.info())
        return out

    def read_output(
        self,
        process_id: str,
        *,
        stream: Optional[str] = None,
        since_sequence: Optional[int] = None,
        cursor: Optional[int] = None,
        tail: Optional[int] = None,
        lines: Optional[int] = None,
        byte_limit: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        record = self._record(process_id)
        if record is None:
            return None
        window = record.buffer.read(
            stream=stream, since_sequence=since_sequence, cursor=cursor,
            tail=tail, lines=lines, byte_limit=byte_limit,
        )
        window["status"] = record.state
        return window

    # ── Input / signals ─────────────────────────────────────────────────────────

    def write_input(self, process_id: str, data: str, *, newline: bool = True) -> bool:
        record = self._record(process_id)
        if record is None or record.spawned is None or record.state in TERMINAL_STATES:
            return False
        payload = data if (not newline or data.endswith(("\n", "\r"))) else data + "\n"
        try:
            assert record.spawned.proc.stdin is not None
            record.spawned.proc.stdin.write(payload)
            record.spawned.proc.stdin.flush()
        except (OSError, ValueError, AssertionError):
            return False
        self._emit("process.input", {"processId": process_id, "bytes": len(payload)})
        return True

    def send_signal(self, process_id: str, signal_name: str) -> dict[str, Any]:
        record = self._record(process_id)
        if record is None:
            return {"ok": False, "code": "NOT_FOUND"}
        if record.state in TERMINAL_STATES:
            return {"ok": False, "code": "ALREADY_EXITED", "state": record.state}
        name = str(signal_name).upper()
        if not name.startswith("SIG"):
            name = "SIG" + name
        if name in (SignalName.STOP.value, SignalName.CONT.value):
            if name == SignalName.STOP.value:
                return {"ok": False, "code": "NOT_IMPLEMENTED", "reason": "this computer cannot pause a process"}
            return {"ok": False, "code": "NOT_IMPLEMENTED", "reason": "this computer cannot resume a process"}
        return self._end(record, signal=name)

    def stop(self, process_id: str, *, timeout_s: int = 5) -> bool:
        record = self._record(process_id)
        if record is None or record.state in TERMINAL_STATES:
            return False
        record.stop_requested = True
        record.state = ProcessState.STOPPING.value
        record.updated_at = now_iso()
        self._persist(record)
        self._emit("process.stopping", {"processId": process_id})
        spawned = record.spawned
        if spawned is not None:
            spawned.terminate()
            deadline = time.monotonic() + max(1, int(timeout_s))
            while time.monotonic() < deadline and spawned.poll() is None:
                time.sleep(0.05)
            if spawned.poll() is None:
                self._end(record, signal=SignalName.KILL.value, already_stopping=True)
        return True

    def kill(self, process_id: str) -> bool:
        record = self._record(process_id)
        if record is None:
            return False
        if record.state in TERMINAL_STATES and record.spawned is None:
            return False
        self._end(record, signal=SignalName.KILL.value)
        return True

    def _end(self, record: _Record, *, signal: str, already_stopping: bool = False) -> dict[str, Any]:
        spawned = record.spawned
        if spawned is None:
            with self._lock:
                record.state = ProcessState.KILLED.value
                record.exit_at = now_iso()
                record.updated_at = record.exit_at
            self._persist(record)
            self._emit("process.killed", {"processId": record.process_id, "signal": signal})
            return {"ok": True, "signal": signal}
        with self._lock:
            if record.state not in TERMINAL_STATES:
                record.stop_requested = True
                if not already_stopping:
                    record.state = ProcessState.STOPPING.value
        started = time.monotonic()
        spawned.kill_tree()
        # The monitor thread owns the final transition; give it a moment.
        for _ in range(50):
            if spawned.poll() is not None:
                break
            time.sleep(0.02)
        with self._lock:
            if record.state not in TERMINAL_STATES:
                record.exit_code = spawned.poll()
                record.exit_at = now_iso()
                record.updated_at = record.exit_at
                record.state = ProcessState.KILLED.value
        record.buffer.note(f"killed after {int((time.monotonic() - started) * 1000)}ms\n", now_iso())
        spawned.release()
        self._persist(record)
        self._emit("process.killed", {"processId": record.process_id, "signal": signal})
        return {"ok": True, "signal": signal}

    # ── Restart ─────────────────────────────────────────────────────────────────

    def restart(self, process_id: str) -> Optional[dict[str, Any]]:
        """Stop and start again with the ORIGINAL configuration. New id, new pid."""
        record = self._record(process_id)
        if record is None:
            return None
        config = {
            "argv": list(record.argv), "cwd": record.cwd, "env": dict(record.env),
            "command": record.command, "runtime": record.runtime, "shell": record.shell,
            "workspace_id": record.workspace_id, "agent_id": record.agent_id,
            "run_id": record.run_id, "task_id": record.task_id, "purpose": record.purpose,
            "parent_pid": record.parent_pid,
        }
        if record.state not in TERMINAL_STATES:
            self.stop(process_id, timeout_s=5)
        if record.state not in TERMINAL_STATES:
            self.kill(process_id)
        new = self.start_process(**config)
        self._emit("process.restarted", {
            "processId": new["processId"], "previousProcessId": process_id,
            "pid": new.get("pid"),
        })
        return new

    # ── Process tree / health ────────────────────────────────────────────────────

    def process_tree(self, process_id: str) -> Optional[dict[str, Any]]:
        """The process and its OS descendants, plus any harness siblings.

        The children come from the OS's own parent map (`proctree`), so a shell
        wrapper's real children (node, next, workers) are shown. Harness-started
        children (by recorded pid) are merged in. Never an invented tree.
        """
        record = self._record(process_id)
        if record is None:
            return None
        known_pids = set(proctree.descendants(record.pid))
        for other in self._procs.values():
            if other.process_id != record.process_id and other.parent_pid == record.pid and other.pid:
                known_pids.add(int(other.pid))
        return _tree_for(record, self._procs, known_pids)

    def health(self, process_id: str, *, port: Optional[int] = None, url: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Distinguish RUNNING from READY: pid alive + port listening + optional HTTP.

        A process can be RUNNING (its pid exists) yet not READY (the server has not
        bound its port, or the HTTP check fails). This reports both, honestly, and
        never invents an OK.
        """
        record = self._record(process_id)
        if record is None:
            return None
        alive = bool(record.spawned is not None and record.spawned.poll() is None)
        listening = False
        if port is not None and self._port_resolver is not None:
            listening = int(port) in set(self._port_resolver(record.pid or 0))
        ready = alive and (listening if port is not None else True)
        result: dict[str, Any] = {
            "processId": process_id, "state": record.state, "pidAlive": alive,
            "port": port, "portListening": listening if port is not None else None,
            "ready": ready,
        }
        if url and alive:
            try:
                import urllib.request

                with urllib.request.urlopen(str(url), timeout=3) as response:  # noqa: S310
                    result["httpStatus"] = int(getattr(response, "status", 200))
                result["httpOk"] = True
                result["ready"] = True
            except Exception as exc:  # noqa: BLE001 - an unreachable health URL is not ready
                result["httpOk"] = False
                result["httpError"] = str(exc)
                result["ready"] = False
        # Runaway detection: REPORT, never auto-kill. A process flagged runaway is
        # long-lived or has produced an outsized buffer. The operator decides.
        runaway = self._runaway_flags(record)
        if runaway:
            result["runaway"] = runaway
            if record.runaway != runaway:
                self._emit("process.runaway", {"processId": process_id, **runaway})
        elif record.runaway is not None:
            record.runaway = None
        record.health = result
        return result

    def _runaway_flags(self, record: _Record) -> Optional[dict[str, Any]]:
        reasons: list[str] = []
        snapshot = record.buffer.snapshot()
        if snapshot.get("totalBytes", 0) > self._limits.max_output_bytes:
            reasons.append("output")
        if record.started_at:
            try:
                from datetime import datetime

                started = datetime.fromisoformat(record.started_at)
                age = (datetime.fromisoformat(now_iso()) - started).total_seconds()
                if age > self._limits.runaway_seconds:
                    reasons.append("lifetime")
            except Exception:  # noqa: BLE001
                pass
        return {"reasons": reasons, "limits": self._limits.to_dict()} if reasons else None

    def resource_report(self) -> dict[str, Any]:
        """A snapshot for the resource tool: limits + the processes that are active."""
        from .resources import system_resources

        with self._lock:
            live = [r for r in self._procs.values() if r.state not in TERMINAL_STATES]
        active = []
        for r in live:
            flags = self._runaway_flags(r)
            r.runaway = flags
            if flags:
                self._emit("process.runaway", {"processId": r.process_id, **flags})
            active.append({
                "processId": r.process_id, "pid": r.pid,
                "command": redaction.redact_command(r.command), "state": r.state, "runaway": flags,
            })
        return {
            "system": system_resources(),
            "limits": self._limits.to_dict(),
            "activeProcesses": len(active),
            "processes": active,
        }

    def process_ids_for_pid_or_descendants(self, pid: Optional[int]) -> list[str]:
        """Every managed process whose pid is ``pid`` or a descendant of it."""
        if not pid:
            return []
        targets = {int(pid)} | set(proctree.descendants(pid))
        out: list[str] = []
        with self._lock:
            for record in self._procs.values():
                if record.pid in targets:
                    out.append(record.process_id)
        return out


def _tree_for(record: _Record, all_records: dict[str, _Record], os_child_pids: set[int]) -> dict[str, Any]:
    """Build a tree over OS descendants plus harness siblings by known pid."""
    children: list[dict[str, Any]] = []
    for child_pid in sorted(p for p in os_child_pids if p):
        # A harness-managed child gets its full managed subtree; an unmanaged OS
        # descendant is a leaf node with just its pid.
        managed = [r for r in all_records.values() if r.pid == child_pid]
        if managed:
            for row in managed:
                children.append({
                    "processId": row.process_id, "pid": row.pid, "state": row.state,
                    "command": redaction.redact_command(row.command), "children": [],
                    "managed": True,
                })
        else:
            children.append({
                "processId": None, "pid": child_pid, "state": "UNKNOWN",
                "command": None, "children": [], "managed": False,
            })
    return {
        "processId": record.process_id,
        "pid": record.pid,
        "state": record.state,
        "command": redaction.redact_command(record.command),
        "children": children,
        "childCount": len(children),
        "managed": True,
    }


__all__ = ["ProcessManager"]
