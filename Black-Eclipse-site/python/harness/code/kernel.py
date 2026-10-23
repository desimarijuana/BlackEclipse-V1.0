"""A persistent analysis kernel: one sandboxed interpreter per conversation.

The one-shot runner pays interpreter start-up on every tool round. This module
keeps a single isolated process alive for a session and sends it one full program
per round. It is an EXECUTION STRATEGY for `run_analysis`, never a second data
path: `prepare_analysis`, the AST gate, the `eclipse_tools` replay protocol and
the provenance rules are the same objects the one-shot runner uses.

Isolation is unchanged (Job Object / process group, scrubbed env, memory and
process limits). The only new surface is a stdin/stdout line protocol: large
commands and responses go through files in the kernel's own staging directory,
and the pipe carries one small JSON acknowledgement per round. A crash, an
oversized line, an idle timeout or a pool eviction KILLS the whole process tree.

Kernels are keyed by conversation, not by run: an ordinary chat turn may reuse a
kernel across turns, while a delegated child (or a run with no session) may only
reuse its own run. A failed spawn falls back to the one-shot runner; a kernel
that dies mid-execution fails the analysis (`KERNEL_CRASHED`) rather than being
silently retried, because re-running would duplicate side effects.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from . import sandbox as sandbox_mod
from . import sandbox_tools as st
from .execution import (
    ANALYSIS_PRELUDE,
    DEFAULT_MEMORY_MB,
    MAX_CPU_SECONDS,
    MAX_PROCESSES,
    OUTPUT_TOO_LARGE,
    TIMED_OUT,
    AnalysisRequest,
    AnalysisResult,
    PreparedAnalysis,
    _bounded_outputs,
    _collect_artifacts,
    computed_provenance,
    guard_payload,
    interpreter_path,
    prepare_analysis,
    resolve_tool_request,
)

KERNEL_CRASHED = "KERNEL_CRASHED"
KERNEL_KEY_INVALID = "KERNEL_KEY_INVALID"
MAX_KERNEL_COMMAND_BYTES = 8_000_000
MAX_KERNEL_RESPONSE_BYTES = 2_000_000
DEFAULT_MAX_KERNELS = 4
DEFAULT_IDLE_S = 300.0
DEFAULT_KERNEL_TIMEOUT_S = 600


_WORKER = ANALYSIS_PRELUDE + '''

import io

_TOOL_SENTINEL = 75
_CAPTURE_LIMIT = 400_000
_MAX_RESPONSE_BYTES = 2_000_000
_PROTO_IN = None
_PROTO_OUT = None


def _protocol():
    # Keep private duplicates of the original stdin/stdout for the host channel,
    # then point fd 0/1 at the null device. A C extension that writes straight to
    # stdout can no longer corrupt the newline-delimited protocol; Python-level
    # generated output is captured by `_Capture` below. stderr stays connected to
    # the sandbox's bounded drain for crash diagnostics.
    global _PROTO_IN, _PROTO_OUT
    _PROTO_IN = os.fdopen(os.dup(0), "r", encoding="utf-8")
    _PROTO_OUT = os.fdopen(os.dup(1), "w", encoding="utf-8")
    devnull_in = os.open(os.devnull, os.O_RDONLY)
    devnull_out = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_in, 0)
        os.dup2(devnull_out, 1)
    finally:
        os.close(devnull_in)
        os.close(devnull_out)
    sys.stdin = open(os.devnull, "r", encoding="utf-8")



class _Capture(io.TextIOBase):
    def __init__(self, limit):
        self._limit = limit
        self._parts = []
        self._size = 0
        self.truncated = False

    def write(self, value):
        text = str(value)
        if self._size < self._limit:
            keep = text[: self._limit - self._size]
            self._parts.append(keep)
            self._size += len(keep)
            if keep != text:
                self.truncated = True
        elif text:
            self.truncated = True
        return len(text)

    def flush(self):
        return None

    def getvalue(self):
        text = "".join(self._parts)
        return text + ("\\n[output truncated]" if self.truncated else "")


def _bound_outputs(outputs):
    out = {}
    for key, value in list(outputs.items())[:50]:
        try:
            text = json.dumps(value)
        except (TypeError, ValueError):
            out[key] = str(value)[:2000]
            continue
        out[key] = text[:20000] if len(text) > 20000 else value
    return out


def _write(response_path, payload):
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        text = json.dumps({
            "status": "error",
            "error": "the analysis result exceeded the response budget",
        })
    with open(response_path, "w", encoding="utf-8") as handle:
        handle.write(text)


_NOTEBOOK_GLOBALS = None


def _run(command):
    global _NOTEBOOK_GLOBALS
    for path in command.get("extra_paths") or []:
        if path and path not in sys.path:
            sys.path.insert(0, path)
    if command.get("persist"):
        # A notebook cell keeps its variables between rounds. `analysis_run`
        # never sends `persist`, so an ordinary analysis still starts clean.
        if _NOTEBOOK_GLOBALS is None:
            _NOTEBOOK_GLOBALS = {"__name__": "__analysis__"}
        g = _NOTEBOOK_GLOBALS
        g.pop("result", None)
    else:
        g = {"__name__": "__analysis__"}
    g["__builtins__"] = _safe_builtins()
    g["inputs"] = command["inputs"]
    g["write_artifact"] = _write_artifact
    sys.modules.pop("eclipse_tools", None)
    g.pop("eclipse_tools", None)
    if command.get("tool_bindings"):
        memo = command.get("tool_memo") or {}
        pending_path = command.get("tool_pending_path")
        if not isinstance(memo, dict) or not pending_path:
            raise ValueError("the analysis tool channel is incomplete")
        module = _tool_module(command["tool_bindings"], memo, pending_path)
        sys.modules["eclipse_tools"] = module
        g["eclipse_tools"] = module
    # The guard goes in BEFORE the program runs (same enforcement point as the
    # one-shot runner): guarded `__import__`, audit hook, path confinement.
    _guard_install(
        command.get("import_allowlist") or [],
        command.get("read_roots") or [],
        command.get("write_roots") or [],
    )
    code = compile(command["source"], "<analysis>", "exec")
    exec(code, g)
    out = g.get("result")
    if out is None:
        out = {
            k: v for k, v in g.items()
            if not k.startswith("_") and k not in ("inputs", "write_artifact", "eclipse_tools")
        }
    return _bound_outputs(out)


def main():
    _protocol()
    while True:
        line = _PROTO_IN.readline()
        if not line:
            return
        try:
            ack = json.loads(line)
        except ValueError:
            return
        command_id = ack.get("id")
        command_path = ack.get("command")
        response_path = ack.get("response")
        if not command_id or not command_path or not response_path:
            return
        try:
            with open(command_path, "r", encoding="utf-8") as handle:
                command = json.load(handle)
        except (OSError, ValueError):
            _write(response_path, {"status": "error", "error": "unreadable command"})
            _PROTO_OUT.write(json.dumps({"id": command_id, "status": "error"}) + "\\n")
            _PROTO_OUT.flush()
            continue
        capture = _Capture(_CAPTURE_LIMIT)
        saved_out, saved_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = capture
        try:
            outputs = _run(command)
            status = "ok"
            payload = {"status": "ok", "outputs": outputs}
        except SystemExit as exc:
            if exc.code == _TOOL_SENTINEL:
                status = "tool_request"
                payload = {"status": "tool_request"}
            else:
                status = "error"
                payload = {"status": "error", "error": capture.getvalue() or "the analysis stopped"}
        except BaseException as exc:  # generated code is not trusted to raise cleanly
            status = "error"
            message = capture.getvalue()
            payload = {
                "status": "error",
                "error": (message + "\\n" if message else "") + f"{type(exc).__name__}: {exc}",
            }
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
        _write(response_path, payload)
        _PROTO_OUT.write(json.dumps({"id": command_id, "status": status}) + "\\n")
        _PROTO_OUT.flush()


main()
'''


class Kernel:
    """One live worker process and its staging directory."""

    def __init__(self, key: str, stage: Path, spawned: sandbox_mod.SpawnedProcess) -> None:
        self.key = key
        self.stage = stage
        self.spawned = spawned
        self.last_used = time.monotonic()
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._in_use = 0
        self._dead = False

    @classmethod
    def start(cls, key: str) -> Optional["Kernel"]:
        interpreter = interpreter_path()
        if not interpreter:
            return None
        stage = Path(tempfile.mkdtemp(prefix="be-kernel-"))
        try:
            worker = stage / "kernel_worker.py"
            worker.write_text(_WORKER, encoding="utf-8")
            (stage / "output").mkdir(exist_ok=True)
            spec = sandbox_mod.RunSpec(
                argv=[interpreter, str(worker)],
                cwd=stage,
                env=sandbox_mod.build_env(),
                timeout_s=DEFAULT_KERNEL_TIMEOUT_S,
                output_cap_bytes=0,
                network=False,
                cpu_seconds=MAX_CPU_SECONDS,
                memory_mb=DEFAULT_MEMORY_MB,
                process_limit=MAX_PROCESSES,
            )
            spawned = sandbox_mod.spawn(spec)
        except (OSError, sandbox_mod.SandboxUnavailable, sandbox_mod.SandboxStreamError):
            shutil.rmtree(stage, ignore_errors=True)
            return None
        return cls(key, stage, spawned)

    def reserve(self) -> None:
        """Mark the kernel as checked out so the idle sweep cannot evict it."""
        with self._state_lock:
            self._in_use += 1
            self.last_used = time.monotonic()

    def release(self) -> None:
        with self._state_lock:
            if self._in_use > 0:
                self._in_use -= 1
            self.last_used = time.monotonic()

    def busy(self) -> bool:
        return self._lock.locked() or self._in_use > 0

    def close(self) -> None:
        self._dead = True
        try:
            self.spawned.close()
        finally:
            shutil.rmtree(self.stage, ignore_errors=True)

    def _clear_output(self) -> None:
        output = self.stage / "output"
        if not output.is_dir():
            return
        for entry in output.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)

    def _reset_stage(self) -> None:
        keep = {"kernel_worker.py", "command.json", "response.json", "pending.json", "output"}
        for entry in self.stage.iterdir():
            if entry.name in keep:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        self._clear_output()
        for name in ("command.json", "response.json", "pending.json"):
            (self.stage / name).unlink(missing_ok=True)

    def _fail(
        self, prepared: PreparedAnalysis, started: float, code: str, reason: str,
        *, status: str = "failed", tool_calls: Optional[list[st.ToolCallRef]] = None,
    ) -> AnalysisResult:
        return AnalysisResult(
            status=status, code=code, source_digest=prepared.source_digest,
            input_digests=prepared.input_digests, interpreter=prepared.interpreter,
            package_lock_digest=prepared.package_lock_digest,
            duration_ms=int((time.monotonic() - started) * 1000),
            tool_calls=tool_calls or [], stderr=reason[:4_000],
        )

    def execute(
        self,
        request: AnalysisRequest,
        *,
        output_dir: Optional[Path] = None,
        tool_resolver: Optional[st.ToolResolver] = None,
    ) -> AnalysisResult:
        started = time.monotonic()
        prepared = prepare_analysis(request, tool_resolver=tool_resolver)
        if isinstance(prepared, AnalysisResult):
            return prepared

        with self._lock:
            self.last_used = time.monotonic()
            if self._dead or not self.spawned.alive():
                return self._fail(
                    prepared, started, KERNEL_CRASHED,
                    "the analysis kernel is no longer running",
                )
            try:
                return self._execute_locked(
                    prepared, request, started, output_dir=output_dir,
                    tool_resolver=tool_resolver,
                )
            except (
                EOFError, ValueError, sandbox_mod.SandboxStreamError,
                BrokenPipeError, OSError,
            ) as exc:
                self._dead = True
                try:
                    self.spawned.close()
                except Exception:  # noqa: BLE001 - already failing
                    pass
                return self._fail(
                    prepared, started, KERNEL_CRASHED,
                    f"the analysis kernel stopped: {exc}",
                )

    def _execute_locked(
        self,
        prepared: PreparedAnalysis,
        request: AnalysisRequest,
        started: float,
        *,
        output_dir: Optional[Path],
        tool_resolver: Optional[st.ToolResolver],
    ) -> AnalysisResult:
        self._reset_stage()
        command_path = self.stage / "command.json"
        response_path = self.stage / "response.json"
        pending_path = self.stage / "pending.json"
        deadline = started + max(1, int(request.timeout_s))
        memo: dict[str, Any] = {}
        tool_calls: list[st.ToolCallRef] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._dead = True
                self.spawned.close()
                return self._fail(
                    prepared, started, TIMED_OUT, "the analysis ran out of time",
                    status="timed_out", tool_calls=tool_calls,
                )

            # Each replay starts from a clean output folder, so a file written by
            # an earlier round cannot be collected as if the final round made it.
            self._clear_output()
            for stale in (command_path, response_path, pending_path):
                stale.unlink(missing_ok=True)
            command: dict[str, Any] = {
                "source": request.source,
                "inputs": prepared.inputs,
                "persist": bool(getattr(request, "persist_namespace", False)),
                "extra_paths": (
                    [str(prepared.managed_path)]
                    if prepared.managed_path is not None and prepared.managed_path.is_dir()
                    else []
                ),
            }
            # The runtime guard travels with the command, so the kernel enforces
            # exactly the same confinement as the one-shot runner.
            command.update(guard_payload(prepared, self.stage, command["extra_paths"]))
            if prepared.allow_tools:
                command.update({
                    "tool_bindings": list(prepared.tool_names),
                    "tool_memo": memo,
                    "tool_pending_path": str(pending_path),
                })
            text = json.dumps(command)
            if len(text.encode("utf-8")) > MAX_KERNEL_COMMAND_BYTES:
                return self._fail(
                    prepared, started, st.TOOL_ARGS_INVALID,
                    "the analysis command exceeded the kernel budget", status="refused",
                    tool_calls=tool_calls,
                )
            command_path.write_text(text, encoding="utf-8")

            command_id = uuid.uuid4().hex
            try:
                self.spawned.write_line(json.dumps({
                    "id": command_id,
                    "command": str(command_path),
                    "response": str(response_path),
                }))
            except sandbox_mod.SandboxStreamError as exc:
                self._dead = True
                self.spawned.close()
                return self._fail(
                    prepared, started, KERNEL_CRASHED,
                    f"the analysis kernel stopped: {exc}", tool_calls=tool_calls,
                )

            try:
                ack = json.loads(self.spawned.read_line(remaining))
            except TimeoutError:
                self._dead = True
                self.spawned.close()
                return self._fail(
                    prepared, started, TIMED_OUT, "the analysis ran out of time",
                    status="timed_out", tool_calls=tool_calls,
                )
            if ack.get("id") != command_id:
                self._dead = True
                self.spawned.close()
                return self._fail(
                    prepared, started, st.TOOL_PROTOCOL_INVALID,
                    "the analysis kernel sent an unexpected reply", tool_calls=tool_calls,
                )

            status = ack.get("status")
            if status == "tool_request":
                if not pending_path.is_file():
                    return self._fail(
                        prepared, started, st.TOOL_PROTOCOL_INVALID,
                        "the analysis stopped without a valid data request",
                        tool_calls=tool_calls,
                    )
                try:
                    if pending_path.stat().st_size > st.MAX_TOOL_REQUEST_BYTES:
                        return self._fail(
                            prepared, started, st.TOOL_ARGS_INVALID,
                            "the analysis sent an oversized data request",
                            status="refused", tool_calls=tool_calls,
                        )
                    pending = json.loads(pending_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return self._fail(
                        prepared, started, st.TOOL_PROTOCOL_INVALID,
                        "the analysis sent an unreadable data request",
                        tool_calls=tool_calls,
                    )
                failure = resolve_tool_request(
                    pending, memo=memo, tool_calls=tool_calls,
                    tool_resolver=tool_resolver, source_digest=prepared.source_digest,
                    input_digests=prepared.input_digests, interpreter=prepared.interpreter,
                    package_lock=prepared.package_lock_digest, started=started,
                )
                if failure is not None:
                    return failure
                continue

            if status != "ok":
                try:
                    payload = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    payload = {}
                reason = str(payload.get("error") or self.spawned.stderr_text() or
                             "the analysis stopped")
                return self._fail(
                    prepared, started, None, reason, tool_calls=tool_calls,
                )

            try:
                size = response_path.stat().st_size
                if size > MAX_KERNEL_RESPONSE_BYTES:
                    return self._fail(
                        prepared, started, OUTPUT_TOO_LARGE,
                        "the analysis result exceeded the response budget",
                        status="refused", tool_calls=tool_calls,
                    )
                payload = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return self._fail(
                    prepared, started, st.TOOL_PROTOCOL_INVALID,
                    "the analysis returned an unreadable result", tool_calls=tool_calls,
                )
            if payload.get("status") == "error":
                return self._fail(
                    prepared, started, OUTPUT_TOO_LARGE,
                    str(payload.get("error") or "the analysis result was rejected"),
                    status="refused", tool_calls=tool_calls,
                )

            outputs = _bounded_outputs(payload.get("outputs") or {})
            artifacts = _collect_artifacts(output_dir, self.stage) if output_dir else []
            return AnalysisResult(
                status="ok", outputs=outputs, artifacts=artifacts,
                source_digest=prepared.source_digest,
                input_digests=prepared.input_digests, interpreter=prepared.interpreter,
                package_lock_digest=prepared.package_lock_digest,
                duration_ms=int((time.monotonic() - started) * 1000),
                tool_calls=tool_calls,
                provenance=computed_provenance(
                    request.purpose, source_digest=prepared.source_digest,
                ),
            )


class KernelPool:
    """Bounded, idle-expiring set of kernels keyed by conversation."""

    def __init__(self, *, max_kernels: int, idle_s: float) -> None:
        self.max_kernels = max(1, int(max_kernels))
        self.idle_s = max(1.0, float(idle_s))
        self._kernels: "OrderedDict[str, Kernel]" = OrderedDict()
        self._lock = threading.Lock()

    def _sweep_locked(self, now: float) -> None:
        for key, kernel in list(self._kernels.items()):
            if kernel.busy():
                continue
            if now - kernel.last_used >= self.idle_s:
                self._kernels.pop(key, None)
                kernel.close()

    def _acquire(self, key: str, *, reserve: bool) -> Optional[Kernel]:
        now = time.monotonic()
        with self._lock:
            self._sweep_locked(now)
            existing = self._kernels.pop(key, None)
            if existing is not None:
                if existing.spawned.alive():
                    existing.last_used = now
                    self._kernels[key] = existing
                    if reserve:
                        existing.reserve()
                    return existing
                existing.close()
            while len(self._kernels) >= self.max_kernels:
                victim_key = next(
                    (k for k, v in self._kernels.items() if not v.busy()), None
                )
                if victim_key is None:
                    # Every slot is executing. Fall back to the one-shot runner
                    # rather than exceeding the pool bound.
                    return None
                victim = self._kernels.pop(victim_key)
                victim.close()
            kernel = Kernel.start(key)
            if kernel is None:
                return None
            if reserve:
                kernel.reserve()
            self._kernels[key] = kernel
            return kernel

    def acquire(self, key: str) -> Optional[Kernel]:
        """Return a kernel without a lease (callers that execute immediately)."""
        return self._acquire(key, reserve=False)

    def lease(self, key: str) -> Optional[Kernel]:
        """Return a kernel held against idle eviction until `release`."""
        return self._acquire(key, reserve=True)

    def release(self, key: str) -> None:
        with self._lock:
            kernel = self._kernels.get(key)
            if kernel is not None:
                kernel.release()

    def drop(self, key: str) -> None:
        with self._lock:
            kernel = self._kernels.pop(key, None)
        if kernel is not None:
            kernel.close()

    def close_all(self) -> None:
        with self._lock:
            kernels = list(self._kernels.values())
            self._kernels.clear()
        for kernel in kernels:
            kernel.close()


def kernel_key(ctx: Any) -> str:
    """The isolation key: a conversation, or exactly one delegated run."""
    agent = str(getattr(ctx, "agent_id", None) or "eclipse-agent")[:64]
    session = getattr(ctx, "session_id", None)
    depth = int(getattr(ctx, "delegation_depth", 0) or 0)
    if session and depth <= 0:
        return f"session:{str(session)[:180]}|agent:{agent}"[:300]
    run = str(getattr(ctx, "run_id", None) or "run")[:180]
    return f"run:{run}|agent:{agent}"[:300]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


_POOL: Optional[KernelPool] = None
_POOL_LOCK = threading.Lock()


def get_pool() -> Optional[KernelPool]:
    global _POOL
    if not _env_flag("ECLIPSE_ANALYSIS_KERNEL", True):
        return None
    with _POOL_LOCK:
        if _POOL is None:
            try:
                max_kernels = int(os.environ.get("ECLIPSE_ANALYSIS_KERNEL_MAX", DEFAULT_MAX_KERNELS))
            except ValueError:
                max_kernels = DEFAULT_MAX_KERNELS
            try:
                idle_s = float(os.environ.get("ECLIPSE_ANALYSIS_KERNEL_IDLE_S", DEFAULT_IDLE_S))
            except ValueError:
                idle_s = DEFAULT_IDLE_S
            _POOL = KernelPool(max_kernels=max_kernels, idle_s=idle_s)
        return _POOL


def kernel_for_context(ctx: Any) -> Optional[Kernel]:
    """Lease the conversation's kernel; call `release_kernel` in a finally."""
    pool = get_pool()
    if pool is None:
        return None
    return pool.lease(kernel_key(ctx))


def release_kernel(kernel: Optional[Kernel]) -> None:
    if kernel is None:
        return
    pool = get_pool()
    if pool is not None:
        pool.release(kernel.key)


def reset_kernel_for_context(ctx: Any) -> None:
    pool = get_pool()
    if pool is not None:
        pool.drop(kernel_key(ctx))


def reset_kernel_pool() -> None:
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.close_all()


atexit.register(reset_kernel_pool)


__all__ = [
    "DEFAULT_IDLE_S",
    "DEFAULT_MAX_KERNELS",
    "KERNEL_CRASHED",
    "Kernel",
    "KernelPool",
    "get_pool",
    "kernel_for_context",
    "kernel_key",
    "release_kernel",
    "reset_kernel_for_context",
    "reset_kernel_pool",
]
