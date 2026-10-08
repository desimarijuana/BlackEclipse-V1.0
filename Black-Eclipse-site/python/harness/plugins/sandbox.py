"""Process-isolated plugin execution (the host side).

A `community`/`untrusted` plugin runs in a **separate OS process** (`build trust`
is configurable, see `PluginManager._should_sandbox`). The child speaks a
newline-delimited JSON-RPC protocol over stdio; the host proxies the plugin's
context operations (config, secrets, storage, HTTP, auth, logging, events,
webhooks) back through the same channel, so *every* host-side permission check,
SSRF guard and secret boundary still applies — the sandbox does not bypass them.

The sandbox gives: crash isolation (a plugin crash cannot crash Eclipse Core),
per-call timeouts, bounded message size, an optional POSIX address-space limit,
and clean teardown. Lifecycle, tools, commands, hooks and events are all proxied.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .errors import PluginError
from .manifest import PluginManifest
from .model import PluginRecord
from .sdk import CONTRIB_ATTR  # noqa: F401  (documents the contract used in-process)

_MAX_MESSAGE_BYTES = 4 * 1024 * 1024
_DEFAULT_CALL_TIMEOUT_S = 40.0
_LIFECYCLE_TIMEOUT_S = 30.0


class SandboxError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


def _python_path(root: Path) -> str:
    """The directory that contains the `harness` package (for the child's sys.path)."""
    # sandbox.py -> plugins -> harness -> parent (the dir containing `harness`).
    return str(Path(__file__).resolve().parents[2])


class SandboxedPlugin:
    """A plugin running in a child process. Exposes the same lifecycle/contribution
    surface the in-process loader produces, so the registry wires it unchanged."""

    def __init__(self, manager: Any, record: PluginRecord, manifest: PluginManifest,
                 directory: Path, ctx: Any) -> None:
        self._manager = manager
        self._record = record
        self._manifest = manifest
        self._directory = directory
        self._ctx = ctx
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._seq = 0
        self._reader: Optional[asyncio.Task[Any]] = None
        self._stderr_task: Optional[asyncio.Task[Any]] = None
        self._stderr_tail: list[str] = []
        self._contribs: list[dict[str, Any]] = []
        self._restarts = 0
        self._max_memory_mb = int(os.environ.get("HARNESS_PLUGIN_MAX_MEMORY_MB", "0") or 0)

    # ── spawning ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        plugin_dir = str(self._directory)
        entrypoint = self._manifest.runtime.entrypoint or ""
        py = _python_path(self._directory)
        bootstrap = (
            "import sys; "
            f"sys.path.insert(0, {py!r}); "
            "from harness.plugins.sandbox_runner import main; "
            "sys.exit(main())"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = py + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONUNBUFFERED"] = "1"
        env["HARNESS_PLUGIN_IN_SANDBOX"] = "1"
        if self._max_memory_mb:
            env["HARNESS_PLUGIN_MAX_MEMORY_MB"] = str(self._max_memory_mb)
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", bootstrap, plugin_dir, entrypoint, self._manifest.id,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env,
        )
        self._reader = asyncio.ensure_future(self._read_loop())
        self._stderr_task = asyncio.ensure_future(self._drain_stderr())
        described = await self._call("describe", timeout=_LIFECYCLE_TIMEOUT_S)
        self._contribs = list(described.get("contributions", []))
        self._build_proxies()

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                if len(line) > _MAX_MESSAGE_BYTES:
                    continue
                try:
                    message = json.loads(line.decode("utf-8", errors="replace"))
                except Exception:  # noqa: BLE001 - a malformed frame is dropped
                    continue
                await self._dispatch(message)
        except Exception:  # noqa: BLE001 - the reader must never raise
            pass
        finally:
            if self._stderr_tail:
                for line in self._stderr_tail[-10:]:
                    self._manager.log_plugin(self._record.plugin_id, "warning", f"sandbox stderr: {line}")
            self._fail_all("the plugin sandbox process ended")

    async def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        try:
            while True:
                chunk = await self._proc.stderr.readline()
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    self._stderr_tail.append(text[:500])
                    if len(self._stderr_tail) > 40:
                        self._stderr_tail.pop(0)
        except Exception:  # noqa: BLE001
            pass

    async def _dispatch(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "response":
            fut = self._pending.pop(message.get("id"), None)
            if fut is not None and not fut.done():
                if message.get("ok"):
                    fut.set_result(message.get("result"))
                else:
                    err = message.get("error") or {}
                    fut.set_exception(SandboxError(err.get("code", "PLUGIN_SANDBOX_ERROR"),
                                                   err.get("message", "sandbox call failed")))
        elif kind == "callback":
            result_msg = await self._run_callback(message)
            await self._write(result_msg)

    async def _run_callback(self, message: dict[str, Any]) -> dict[str, Any]:
        callback_id = message.get("id")
        op = str(message.get("op") or "")
        params = message.get("params") or {}
        try:
            result = await self._handle_callback(op, params)
            return {"type": "callback_result", "id": callback_id, "ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001 - a callback failure is data
            return {"type": "callback_result", "id": callback_id, "ok": False,
                    "error": {"code": getattr(exc, "code", "PLUGIN_SANDBOX_CALLBACK"),
                              "message": str(exc)}}

    async def close(self) -> None:
        try:
            if self._proc is not None and self._proc.returncode is None:
                try:
                    await self._call("shutdown", timeout=5.0)
                except Exception:  # noqa: BLE001
                    pass
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
        finally:
            if self._reader is not None:
                self._reader.cancel()
            self._fail_all("the plugin sandbox was closed")
            self._proc = None

    # ── request/callback plumbing ────────────────────────────────────────────

    async def _write(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        data = json.dumps(message, default=str).encode("utf-8")
        if len(data) > _MAX_MESSAGE_BYTES:
            raise SandboxError("PLUGIN_SANDBOX_MESSAGE_TOO_LARGE", "message exceeded the sandbox size limit")
        self._proc.stdin.write(data + b"\n")
        try:
            await self._proc.stdin.drain()
        except Exception:  # noqa: BLE001 - a closed pipe surfaces as a call failure
            pass

    async def _call(self, op: str, *, timeout: float = _DEFAULT_CALL_TIMEOUT_S, **params: Any) -> Any:
        if self._proc is None or self._proc.returncode is not None:
            raise SandboxError("PLUGIN_SANDBOX_DOWN", "the plugin sandbox process is not running")
        self._seq += 1
        request_id = self._seq
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut
        await self._write({"type": "request", "id": request_id, "op": op, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            self._manager.store.bump_health(self._record.plugin_id, crashes=1)
            await self.close()
            raise SandboxError("PLUGIN_SANDBOX_TIMEOUT", f"{op!r} exceeded {timeout:.0f}s in the sandbox")
        finally:
            self._pending.pop(request_id, None)

    def _fail_all(self, reason: str) -> None:
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(SandboxError("PLUGIN_SANDBOX_CRASH", reason))
        self._pending.clear()

    # ── host-side context callbacks ──────────────────────────────────────────

    async def _handle_callback(self, op: str, params: dict[str, Any]) -> Any:
        ctx = self._ctx
        if op == "config.all":
            return ctx.config.all()
        if op == "secrets.all":
            return {name: ctx.secrets.get(name) for name in ctx.secrets.names()}
        if op == "storage.all":
            namespaces = self._manager.store.kv_namespaces(self._record.plugin_id)
            return {ns: self._manager.store.kv_list(self._record.plugin_id, ns) for ns in namespaces}
        if op == "storage.set":
            ctx.storage.set(params["key"], params.get("value"), namespace=params.get("namespace", "default"))
            return True
        if op == "storage.delete":
            ctx.storage.delete(params["key"], namespace=params.get("namespace", "default"))
            return True
        if op == "log":
            getattr(ctx.logger, str(params.get("level", "info")), ctx.logger.info)(str(params.get("message", "")))
            return True
        if op == "event.publish":
            ctx.events.publish(str(params.get("type", "")), params.get("data") or {})
            return True
        if op == "http.request":
            response = await ctx.http.request(
                str(params.get("method", "GET")), str(params.get("url", "")),
                params=params.get("params"), headers=params.get("headers"),
                json=params.get("json"), data=params.get("data"),
            )
            return {"status": response.status, "headers": response.headers, "body": response.text}
        if op == "auth.token":
            return await ctx.auth.token()
        if op == "auth.status":
            return ctx.auth.status()
        if op == "webhook.deliver":
            return await ctx.webhooks.deliver(str(params.get("webhook", "")), params.get("payload") or {})
        if op == "require":
            ctx.require(str(params.get("permission", "")), str(params.get("action", "")))
            return True
        raise SandboxError("PLUGIN_SANDBOX_UNSUPPORTED", f"sandbox context operation {op!r} is not supported")

    # ── contribution proxies ─────────────────────────────────────────────────

    def contributions(self) -> list[dict[str, Any]]:
        return self._contribs

    def _build_proxies(self) -> None:
        built: list[dict[str, Any]] = []
        for desc in self._contribs:
            kind = desc.get("kind")
            name = desc.get("name")
            mark = dict(desc)
            if kind == "tool":
                mark["handler"] = self._tool_proxy(name)
            elif kind == "command":
                mark["handler"] = self._two_arg_proxy("command", name)
            elif kind == "hook":
                mark["handler"] = self._two_arg_proxy("hook", name)
            elif kind == "event":
                mark["handler"] = self._two_arg_proxy("event", desc.get("pattern"))
            elif kind == "worker":
                mark["handler"] = self._worker_proxy(name)
            elif kind == "ui":
                mark["handler"] = self._ui_proxy(desc.get("id"))
            built.append(mark)
        self._contribs = built

    def _tool_proxy(self, name: str):
        async def handler(args: dict[str, Any], run_ctx: Any) -> Any:
            return await self._call("tool", name=name, args=args)

        return handler

    def _two_arg_proxy(self, op: str, name: Optional[str]):
        async def handler(payload: Any, ctx: Any) -> Any:
            return await self._call(op, name=name, payload=payload)

        return handler

    def _ui_proxy(self, panel_id: Optional[str]):
        async def handler() -> Any:
            return await self._call("ui", name=panel_id)

        return handler

    def _worker_proxy(self, name: str):
        async def handler(ctx: Any) -> Any:
            # A sandbox worker runs INSIDE the child (its own task). Here we only
            # wait for the child's reply, which returns when the worker's first
            # iteration completes (or immediately for an interval worker).
            return await self._call("worker", name=name, timeout=_LIFECYCLE_TIMEOUT_S * 4)

        return handler

    # ── lifecycle proxies ────────────────────────────────────────────────────

    async def on_load(self, ctx: Any) -> None:
        await self._call("lifecycle", event="load", timeout=_LIFECYCLE_TIMEOUT_S)

    async def on_enable(self, ctx: Any) -> None:
        await self._call("lifecycle", event="enable", timeout=_LIFECYCLE_TIMEOUT_S)

    async def on_disable(self, ctx: Any) -> None:
        try:
            await self._call("lifecycle", event="disable", timeout=_LIFECYCLE_TIMEOUT_S)
        finally:
            await self.close()

    async def on_unload(self, ctx: Any) -> None:
        await self.close()


__all__ = ["SandboxedPlugin", "SandboxError"]
