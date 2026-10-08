"""The child process for a sandboxed plugin.

Launched by `sandbox.SandboxedPlugin` as `python -c "<bootstrap>" <plugin_dir>
<entrypoint> <plugin_id>`. It imports the plugin, builds a `SandboxContext` whose
operations are proxied to the host, and serves the JSON-RPC loop on stdin/stdout.

Run standalone for debugging:

    python -m harness.plugins.sandbox_runner <plugin_dir> plugin:Impl <id>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .loader import instantiate, read_manifest


def _apply_memory_limit() -> None:
    try:
        mb = int(os.environ.get("HARNESS_PLUGIN_MAX_MEMORY_MB", "0") or 0)
    except ValueError:
        mb = 0
    if mb <= 0:
        return
    try:
        import resource  # noqa: PLC0415

        limit = mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:  # noqa: BLE001 - not supported on this platform
        pass


class _HttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = int(payload.get("status", 0))
        self.headers = payload.get("headers") or {}
        self._body = str(payload.get("body", ""))

    @property
    def text(self) -> str:
        return self._body

    def json(self) -> Any:
        return json.loads(self._body)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class _Config:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def all(self) -> dict[str, Any]:
        return dict(self._values)


class _Secrets:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, name: str) -> Optional[str]:
        return self._values.get(name)

    def require(self, name: str) -> str:
        if name not in self._values:
            raise KeyError(f"secret {name!r} is not set")
        return self._values[name]

    def has(self, name: str) -> bool:
        return name in self._values

    def names(self) -> list[str]:
        return sorted(self._values)


class _Storage:
    def __init__(self, client: "SandboxClient", data: dict[str, dict[str, Any]]) -> None:
        self._client = client
        self._data = data

    def _ns(self, namespace: str) -> dict[str, Any]:
        return self._data.setdefault(namespace, {})

    def get(self, key: str, default: Any = None, *, namespace: str = "default") -> Any:
        return self._ns(namespace).get(key, default)

    def set(self, key: str, value: Any, *, namespace: str = "default") -> None:
        self._ns(namespace)[key] = value
        self._client.notify("storage.set", {"key": key, "value": value, "namespace": namespace})

    def delete(self, key: str, *, namespace: str = "default") -> None:
        self._ns(namespace).pop(key, None)
        self._client.notify("storage.delete", {"key": key, "namespace": namespace})

    def keys(self, *, namespace: str = "default") -> list[str]:
        return sorted(self._ns(namespace))

    def all(self, *, namespace: str = "default") -> dict[str, Any]:
        return dict(self._ns(namespace))


class _Logger:
    def __init__(self, client: "SandboxClient") -> None:
        self._client = client

    def _log(self, level: str, message: str) -> None:
        self._client.notify("log", {"level": level, "message": str(message)})

    def debug(self, message: str) -> None:
        self._log("debug", message)

    def info(self, message: str) -> None:
        self._log("info", message)

    def warning(self, message: str) -> None:
        self._log("warning", message)

    def error(self, message: str) -> None:
        self._log("error", message)


class _Events:
    def __init__(self, client: "SandboxClient") -> None:
        self._client = client

    def publish(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        self._client.notify("event.publish", {"type": event_type, "data": data or {}})

    emit = publish


class _Http:
    def __init__(self, client: "SandboxClient") -> None:
        self._client = client

    async def request(self, method: str, url: str, *, params=None, headers=None, json=None, data=None,
                      timeout_s=None) -> _HttpResponse:
        payload = await self._client.callback("http.request", {
            "method": method, "url": url, "params": params, "headers": headers,
            "json": json, "data": data,
        })
        return _HttpResponse(payload or {})

    async def get(self, url: str, **kw: Any) -> _HttpResponse:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> _HttpResponse:
        return await self.request("POST", url, **kw)

    async def put(self, url: str, **kw: Any) -> _HttpResponse:
        return await self.request("PUT", url, **kw)

    async def patch(self, url: str, **kw: Any) -> _HttpResponse:
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any) -> _HttpResponse:
        return await self.request("DELETE", url, **kw)


class _Auth:
    def __init__(self, client: "SandboxClient", status: dict[str, Any]) -> None:
        self._client = client
        self._status = status

    async def token(self) -> str:
        return await self._client.callback("auth.token", {})

    def status(self) -> dict[str, Any]:
        return self._status


class _Webhooks:
    def __init__(self, client: "SandboxClient") -> None:
        self._client = client

    async def deliver(self, webhook_id: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self._client.callback("webhook.deliver", {"webhook": webhook_id, "payload": payload or {}})


class SandboxContext:
    """The plugin-facing context inside the child; mirrors `PluginContext` for the
    host-mediated operations and refuses the ones that cannot cross the boundary."""

    def __init__(self, manifest: Any, client: "SandboxClient") -> None:
        self.plugin_id = manifest.id
        self.version = manifest.version
        self.manifest = manifest
        self._client = client
        self.config = _Config({})
        self.secrets = _Secrets({})
        self.storage = _Storage(client, {})
        self.logger = _Logger(client)
        self.log = self.logger
        self.events = _Events(client)
        self.http = _Http(client)
        self.auth = _Auth(client, {})
        self.webhooks = _Webhooks(client)

    async def prefetch(self) -> None:
        self.config = _Config(await self._safe("config.all", {}) or {})
        self.secrets = _Secrets(await self._safe("secrets.all", {}) or {})
        self.storage = _Storage(self._client, await self._safe("storage.all", {}) or {})
        self.auth = _Auth(self._client, await self._safe("auth.status", {}) or {})

    async def _safe(self, op: str, default: Any) -> Any:
        """A prefetch that a restricted plugin cannot satisfy degrades to empty."""
        try:
            return await self._client.callback(op, {})
        except Exception:  # noqa: BLE001 - an ungranted capability is simply absent
            return default

    def require(self, permission: str, action: str = "") -> None:
        # The host enforces every permission inside each proxied operation, so a
        # direct require() here is advisory only.
        return None

    def has_permission(self, permission: str) -> bool:
        return True

    def telemetry(self, name: str, data: Optional[dict[str, Any]] = None) -> None:
        self._client.notify("log", {"level": "info", "message": f"telemetry {name}"})

    def _unsupported(self, what: str) -> Any:
        raise RuntimeError(f"{what} is not available in the plugin sandbox")

    async def create_task(self, *a: Any, **k: Any) -> Any:
        return self._unsupported("create_task")

    async def invoke_agent(self, *a: Any, **k: Any) -> Any:
        return self._unsupported("invoke_agent")

    async def run_workflow(self, *a: Any, **k: Any) -> Any:
        return self._unsupported("run_workflow")

    def remember(self, **k: Any) -> Any:
        return self._unsupported("remember")

    def recall(self, **k: Any) -> Any:
        return self._unsupported("recall")

    def add_evidence(self, *a: Any, **k: Any) -> Any:
        return self._unsupported("add_evidence")


class SandboxClient:
    """The child-side protocol client."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._callback_seq = 0
        self._pending_callbacks: dict[int, asyncio.Future[Any]] = {}
        self._instance: Optional[Any] = None
        self._ctx: Optional[SandboxContext] = None
        self._handlers: dict[tuple[str, str], Any] = {}
        self._workers: dict[str, asyncio.Task[Any]] = {}

    # ── transport ────────────────────────────────────────────────────────────

    def _write(self, message: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, default=str) + "\n")
        sys.stdout.flush()

    def notify(self, op: str, params: dict[str, Any]) -> None:
        self._callback_seq += 1
        # Fire-and-forget: the host replies but nobody waits.
        self._write({"type": "callback", "id": self._callback_seq, "op": op, "params": params})

    async def callback(self, op: str, params: dict[str, Any]) -> Any:
        self._callback_seq += 1
        cid = self._callback_seq
        fut: asyncio.Future[Any] = self._loop.create_future()
        self._pending_callbacks[cid] = fut
        self._write({"type": "callback", "id": cid, "op": op, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=60.0)
        finally:
            self._pending_callbacks.pop(cid, None)

    async def _read_stdin(self) -> None:
        while True:
            line = await self._loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            try:
                message = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if message.get("type") == "callback_result":
                fut = self._pending_callbacks.get(message.get("id"))
                if fut is not None and not fut.done():
                    if message.get("ok"):
                        fut.set_result(message.get("result"))
                    else:
                        err = message.get("error") or {}
                        fut.set_exception(RuntimeError(err.get("message", "callback failed")))
                continue
            if message.get("type") == "request":
                asyncio.ensure_future(self._handle_request(message))

    # ── request handling ─────────────────────────────────────────────────────

    def bind(self, instance: Any, ctx: SandboxContext) -> None:
        self._instance = instance
        self._ctx = ctx
        for contribution in instance.contributions():
            kind = contribution.get("kind")
            name = contribution.get("pattern") if kind == "event" else contribution.get("name")
            if kind and name:
                self._handlers[(kind, name)] = contribution["handler"]

    async def _handle_request(self, message: dict[str, Any]) -> None:
        rid = message.get("id")
        op = message.get("op")
        params = message.get("params") or {}
        try:
            result = await self._perform(op, params)
            self._write({"type": "response", "id": rid, "ok": True, "result": result})
        except Exception as exc:  # noqa: BLE001 - the child reports failures as data
            self._write({"type": "response", "id": rid, "ok": False,
                         "error": {"code": getattr(exc, "code", "PLUGIN_SANDBOX_ERROR"), "message": str(exc)}})

    async def _perform(self, op: str, params: dict[str, Any]) -> Any:
        if op == "describe":
            return {"contributions": self._describe()}
        if op == "lifecycle":
            return await self._lifecycle(params.get("event", ""))
        if op == "tool":
            handler = self._handlers[("tool", params["name"])]
            return await _maybe(handler(params.get("args") or {}, self._ctx))
        if op == "command":
            handler = self._handlers[("command", params["name"])]
            return await _maybe(handler(params.get("args") or {}, self._ctx))
        if op == "hook":
            handler = self._handlers[("hook", params["name"])]
            return await _maybe(handler(params.get("payload") or {}, self._ctx))
        if op == "event":
            handler = self._handlers[("event", params.get("name"))]
            return await _maybe(handler(params.get("payload") or {}, self._ctx))
        if op == "worker":
            return await self._worker(params["name"])
        if op == "ui":
            handler = self._handlers.get(("ui", params["name"]))
            if handler is None:
                return None
            return await _maybe(handler(self._ctx) if _takes_ctx(handler) else handler())
        if op == "shutdown":
            return True
        raise RuntimeError(f"unknown sandbox op {op!r}")

    def _describe(self) -> list[dict[str, Any]]:
        out = []
        for contribution in self._instance.contributions():
            mark = {k: v for k, v in contribution.items() if k not in ("handler", "attr")}
            out.append(mark)
        return out

    async def _lifecycle(self, event: str) -> Any:
        method = {"load": "on_load", "enable": "on_enable", "disable": "on_disable", "unload": "on_unload"}.get(event)
        if method is None:
            return None
        if event == "disable":
            for task in self._workers.values():
                task.cancel()
            self._workers.clear()
        fn = getattr(self._instance, method, None)
        if fn is not None:
            await _maybe(fn(self._ctx))
        return True

    async def _worker(self, name: str) -> Any:
        handler = self._handlers.get(("worker", name))
        if handler is None:
            return None
        interval = 0.0
        for contribution in self._instance.contributions():
            if contribution.get("kind") == "worker" and contribution.get("name") == name:
                interval = float(contribution.get("interval_seconds", 0) or 0)
                break
        if interval <= 0:
            return await _maybe(handler(self._ctx))

        async def _loop() -> None:
            while True:
                try:
                    await _maybe(handler(self._ctx))
                except asyncio.CancelledError:
                    return
                except Exception as exc:  # noqa: BLE001
                    self.notify("log", {"level": "error", "message": f"worker {name} raised: {exc}"})
                await asyncio.sleep(interval)

        self._workers[name] = asyncio.ensure_future(_loop())
        return True


async def _maybe(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _takes_ctx(handler: Any) -> bool:
    try:
        import inspect  # noqa: PLC0415

        required = [
            p for p in inspect.signature(handler).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
        ]
        return len(required) >= 1
    except (TypeError, ValueError):
        return False


def main(argv: Optional[list[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 3:
        sys.stderr.write("usage: sandbox_runner <plugin_dir> <entrypoint> <plugin_id>\n")
        return 2
    plugin_dir = Path(args[0])
    _apply_memory_limit()
    manifest, _raw = read_manifest(plugin_dir)
    instance = instantiate(manifest, plugin_dir)

    async def _run() -> int:
        client = SandboxClient()
        ctx = SandboxContext(manifest, client)
        client.bind(instance, ctx)
        # The reader must be live BEFORE prefetch: prefetch issues callbacks whose
        # replies arrive on stdin, and only this loop consumes them.
        reader = asyncio.ensure_future(client._read_stdin())  # noqa: SLF001
        try:
            await ctx.prefetch()
        except Exception:  # noqa: BLE001 - a failed prefetch degrades to empty context
            pass
        await reader
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
