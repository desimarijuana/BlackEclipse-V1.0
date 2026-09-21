"""Agentic service — the runtime the TS API delegates to.

Holds the process-wide store, tool registry (with native finance tools) and
event bus, and exposes start/status/events/cancel over the request contracts.
The TS front door only validates + forwards; all agentic state lives here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .events import EventBus
from .finance_tools import register_finance_tools
from .graph import execute_run
from .persistence import AgentMemoryStore
from .schemas import HarnessError, RunRequest, RunResult
from .tools import DataBridge, ToolRegistry

log = logging.getLogger("harness.service")


class _HttpDataBridge(DataBridge):
    """Reads JDdS data through the thin TS bridge."""

    def __init__(self, base_url: str, token: Optional[str]) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self._base}/api/harness/data",
                    headers=headers,
                    json={"capability": capability, "params": params},
                )
            if response.status_code >= 400:
                return {"status": "UNAVAILABLE", "error": f"bridge HTTP {response.status_code}"}
            return response.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("data bridge failed (%s): %s", capability, exc)
            return {"status": "UNAVAILABLE", "error": str(exc)}


class AgenticService:
    def __init__(self, store: Optional[AgentMemoryStore] = None) -> None:
        self.store = store or AgentMemoryStore()
        self.registry = ToolRegistry()
        register_finance_tools(self.registry)
        self.bus = EventBus()
        self._active: dict[str, asyncio.Task[Any]] = {}

    async def run(self, request: RunRequest) -> RunResult:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)
        return await execute_run(request, self.registry, bridge, self.store, self.bus)

    async def run_background(self, request: RunRequest) -> None:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)

        async def _task() -> None:
            await execute_run(request, self.registry, bridge, self.store, self.bus)

        task = asyncio.create_task(_task())
        self._active[request.runId] = task
        task.add_done_callback(lambda _t: self._active.pop(request.runId, None))

    def cancel(self, run_id: str) -> bool:
        task = self._active.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_run(run_id)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_runs(limit)

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_events(run_id)

    def list_tool_executions(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_tool_executions(run_id)

    def remember(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.remember(**kwargs)

    def recall(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.recall(**kwargs)

    def close(self) -> None:
        self.store.close()


__all__ = ["AgenticService", "HarnessError"]
