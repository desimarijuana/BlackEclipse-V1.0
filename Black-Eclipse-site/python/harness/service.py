"""Agentic service — the runtime the TS API delegates to.

Holds the process-wide store, tool registry (with native finance tools) and
event bus, and exposes start/status/events/cancel over the request contracts.
The TS front door only validates + forwards; all agentic state lives here.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from .eclipse_memory import EclipseMemoryService
from .events import EventBus
from .finance_tools import register_finance_tools
from .graph import execute_run
from .mcp import MCPManager
from .mcp.approvals import ApprovalStore
from .memory_tools import register_memory_tools
from .persistence import AgentMemoryStore
from .retrieval.cache import RetrievalCache
from .retrieval_tools import register_retrieval_tools
from .schemas import HarnessError, RunRequest, RunResult
from .skills import SkillRegistry
from .tools import DataBridge, ToolRegistry

log = logging.getLogger("harness.service")


def _default_callback_base_url() -> str:
    """The Next.js front door base URL for process-wide bridge calls.

    The runtime is spawned by the front door; `HARNESS_CALLBACK_URL` is the
    explicit override, otherwise loopback on the app port.
    """
    return os.environ.get("HARNESS_CALLBACK_URL") or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"


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
        # The memory/skill tools the system prompt promises — on the SAME
        # registry, so validation/permission/timeout machinery is shared.
        register_memory_tools(self.registry)
        # Eclipse-Memory is the dedicated control database for memory AND
        # skills. One service owns it; the skill tables live here (migrated out
        # of agent-memory.db) so there is exactly one skill registry.
        self.memory = EclipseMemoryService()
        self.memory_store = self.memory.store
        self.skill_store = self.memory_store  # same object — one persistence path
        # One-time, non-destructive import of Phase-3 skill rows that previously
        # lived in agent-memory.db (a no-op on fresh installs / after import).
        try:
            self.memory.import_legacy_skills(self.store.path)
        except Exception:  # noqa: BLE001 - migration must not block boot
            log.warning("legacy skill import skipped", exc_info=True)
        self.skill_registry = SkillRegistry(self.skill_store)
        self.skill_load_errors = self.skill_registry.load_all()
        self.skill_registry.attach_tool_registry(self.registry)
        self.bus = EventBus()
        self._active: dict[str, asyncio.Task[Any]] = {}
        # ONE process-wide retrieval cache. It is safe to share: in-flight
        # deduplication is keyed per retrieval, so two runs asking for the same
        # dataset at the same moment share a single provider call (Milestone 2H),
        # and a fresh cached result is reused across runs.
        self.retrieval_cache = RetrievalCache()
        # MCP (Phase 5): configured local stdio servers. Construction only reads
        # config; nothing is launched until `start_mcp()`. Selected read-only MCP
        # tools register into THIS registry, so execution stays authoritative.
        self.mcp = MCPManager()
        self.mcp_registered_tools: list[str] = []
        # Effectful-tool approvals (5G): persisted in the runtime's own DB and
        # consulted by every run's effect authorizer.
        self.approvals = ApprovalStore(self.store)

    def _secret_resolver(self, bridge: DataBridge):
        """Bind an async vault-secret resolver to a run's data bridge.

        The MCP manager calls this at child spawn; the value is fetched through
        the authenticated, read-only bridge and never stored or logged.
        """

        async def resolve(name: str) -> Optional[str]:
            try:
                payload = await bridge.fetch("mcp_secret_resolve", {"name": name})
            except Exception:  # noqa: BLE001 - an unreachable vault is not a value
                return None
            if isinstance(payload, dict) and payload.get("status") == "OK":
                value = payload.get("value")
                return str(value) if value else None
            return None

        return resolve

    async def start_mcp(self) -> None:
        """Connect enabled MCP servers and register selected read-only tools.

        Called once at service startup. A server failure is recorded as a
        diagnostic and does not block the runtime or other servers.
        """
        try:
            # A process-wide bridge is used only for secret resolution at spawn;
            # per-run tools still receive their own run bridge.
            bridge = self.build_bridge(
                _default_callback_base_url(), None
            )
            self.mcp.set_secret_resolver(self._secret_resolver(bridge))
            await self.mcp.start()
            self.mcp_registered_tools = self.mcp.register_selected_tools(self.registry)
        except Exception:  # noqa: BLE001 - MCP must never prevent the runtime booting
            log.warning("MCP startup failed", exc_info=True)

    async def stop_mcp(self) -> None:
        try:
            await self.mcp.close()
        except Exception:  # noqa: BLE001
            log.warning("MCP shutdown failed", exc_info=True)

    async def reload_mcp(self) -> dict[str, Any]:
        """Apply a persisted MCP config change without a runtime restart.

        Removes only the MCP tools this manager added, then reconnects and
        re-registers from the current config file. Returns non-secret status.
        """
        from .mcp.config import load_mcp_configs

        configs, diagnostics = load_mcp_configs()
        self.mcp.load_diagnostics = diagnostics
        self.mcp_registered_tools = await self.mcp.reload(configs)
        return self.mcp.summary()

    async def confirm_mcp_catalog(self, server_id: str) -> dict[str, Any]:
        """Snapshot the live catalog digest as the operator's reviewed version.

        This is the explicit review act that lets an annotation-sourced read-only
        tool activate. Doing it re-reads config, records the digest, and reloads
        so activation takes effect immediately.
        """
        from .mcp.config import load_mcp_configs, upsert_mcp_config

        digest = self.mcp.catalog_digest_for(server_id)
        if not digest:
            return {"success": False, "reason": "server is not connected; test it first"}
        configs, _ = load_mcp_configs()
        target = next((c for c in configs if c.id == server_id), None)
        if target is None:
            return {"success": False, "reason": "server not found"}
        upsert_mcp_config(target.model_copy(update={"confirmed_catalog_digest": digest}))
        await self.reload_mcp()
        return {"success": True, "serverId": server_id, "catalogDigest": digest, **self.mcp.summary()}

    def build_bridge(self, base_url: str, token: Optional[str]) -> DataBridge:
        """Build the read-only JDdS bridge for a research request."""
        return _HttpDataBridge(base_url, token)

    async def retrieve_for_research(self, bridge: DataBridge, request: Any) -> Any:
        """Run ONE retrieval for the research flow through the shared layer/cache.

        Reuses the process-wide retrieval cache and the durable store, exactly
        like the agent tools do — research is not a parallel retrieval system.
        """
        from .retrieval import FinancialRetrievalLayer

        layer = FinancialRetrievalLayer(
            bridge, cache=self.retrieval_cache, store=self.store
        )
        return await layer.retrieve(request)

    async def run(self, request: RunRequest) -> RunResult:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)
        # The retrieval layer is built lazily by the retrieval tools from the
        # run context (so its events reach the emitter); only the shared cache is
        # passed here.
        return await execute_run(
            request, self.registry, bridge, self.store, self.bus,
            retrieval_cache=self.retrieval_cache,
            memory_service=self.memory, skill_registry=self.skill_registry,
            approvals=self.approvals,
        )

    async def run_skill(self, request: Any) -> Any:
        """Execute a skill through the existing runtime.

        Imported lazily so `service` stays importable without the skills package
        (and to keep the module import graph flat).
        """
        from .skills.runtime import execute_skill

        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)
        return await execute_skill(
            request,
            self.skill_registry,
            self.registry,
            bridge,
            self.store,
            bus=self.bus,
            memory_service=self.memory,
        )

    async def run_background(self, request: RunRequest) -> None:
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)

        async def _task() -> None:
            try:
                await execute_run(
                    request, self.registry, bridge, self.store, self.bus,
                    retrieval_cache=self.retrieval_cache,
                    memory_service=self.memory, skill_registry=self.skill_registry,
                    approvals=self.approvals,
                )
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

    # Memory now lives in Eclipse-Memory (the dedicated database), not the run
    # store. These delegate so existing callers keep working with the richer
    # write pipeline (type/scope/dedupe/evidence) instead of a raw insert.
    def remember(self, **kwargs: Any) -> dict[str, Any]:
        return self.memory.write_memory(**kwargs)

    def recall(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.memory.retrieve(**kwargs).memories

    def close(self) -> None:
        self.store.close()
        # `skill_store` IS `memory_store` — one connection, closed once.
        self.memory.close()


__all__ = ["AgenticService", "HarnessError"]
