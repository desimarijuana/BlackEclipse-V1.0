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
from .retrieval.cache import RetrievalCache
from .retrieval_tools import register_retrieval_tools
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
        # The legacy JDdS-only tools remain for compatibility; the Phase-2
        # retrieval tools are the provider-agnostic path the agent should prefer.
        register_finance_tools(self.registry)
        register_retrieval_tools(self.registry)
        self.bus = EventBus()
        self._active: dict[str, asyncio.Task[Any]] = {}
        # ONE process-wide retrieval cache. It is safe to share: in-flight
        # deduplication is keyed per retrieval, so two runs asking for the same
        # dataset at the same moment share a single provider call (Milestone 2H),
        # and a fresh cached result is reused across runs.
        self.retrieval_cache = RetrievalCache()

    async def run(self, request: RunRequest) -> RunResult:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)
        # The retrieval layer is built lazily by the retrieval tools from the
        # run context (so its events reach the emitter); only the shared cache is
        # passed here.
        return await execute_run(request, self.registry, bridge, self.store, self.bus, retrieval_cache=self.retrieval_cache)

    async def run_background(self, request: RunRequest) -> None:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)

        async def _task() -> None:
            try:
                await execute_run(request, self.registry, bridge, self.store, self.bus, retrieval_cache=self.retrieval_cache)
            finally:
                # Signal live SSE consumers that the run is over, whatever the
                # terminal status, so their streams close promptly.
                self.bus.end_stream(request.runId)

        task = asyncio.create_task(_task())
        self._active[request.runId] = task
        task.add_done_callback(lambda _t: self._active.pop(request.runId, None))

    def retrieval_metrics(self) -> dict[str, Any]:
        """Performance counters from the shared retrieval cache/layer."""
        return {"cache": self.retrieval_cache.stats()}

    def cancel(self, run_id: str) -> bool:
        task = self._active.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def is_active(self, run_id: str) -> bool:
        task = self._active.get(run_id)
        return task is not None and not task.done()

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_run(run_id)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_runs(limit)

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_events(run_id)

    def list_tool_executions(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_tool_executions(run_id)

    def usage_summary(self, days: int = 30) -> dict[str, Any]:
        return self.store.usage_summary(days)

    def remember(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.remember(**kwargs)

    def recall(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.recall(**kwargs)

    def close(self) -> None:
        self.store.close()


__all__ = ["AgenticService", "HarnessError"]
