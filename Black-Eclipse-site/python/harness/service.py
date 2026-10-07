"""Agentic service — the runtime the TS API delegates to.

Holds the process-wide store, tool registry (with native finance tools) and
event bus, and exposes start/status/events/cancel over the request contracts.
The TS front door only validates + forwards; all agentic state lives here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Optional

from .code.tools import register_code_tools
from .eclipse_memory import EclipseMemoryService
from .events import EventBus
from .finance_tools import register_finance_tools
from .terminal.tools import register_terminal_tools
from .graph import execute_run
from .memory_tools import register_memory_tools
from .model_runtime import get_runtime
from .persistence import AgentMemoryStore
from .retrieval.cache import RetrievalCache
from .retrieval_tools import register_retrieval_tools
from .schemas import HarnessError, RunRequest, RunResult
from .skills import SkillRegistry
from .tools import DataBridge, ToolRegistry

log = logging.getLogger("harness.service")

# The MCP integration is an optional capability: when the `mcp` SDK is not
# importable (a trimmed install), the runtime reports MCP UNAVAILABLE honestly
# rather than failing to boot or pretending a fake agent exists.
try:  # noqa: SIM105
    from .mcp import MCPManager
    from .mcp.approvals import ApprovalStore

    MCP_AVAILABLE = True
    MCP_IMPORT_ERROR: Optional[str] = None
except Exception as _mcp_exc:  # noqa: BLE001 - a missing SDK is a supported state
    MCPManager = None  # type: ignore[assignment]
    ApprovalStore = None  # type: ignore[assignment]
    MCP_AVAILABLE = False
    MCP_IMPORT_ERROR = str(_mcp_exc)


def _workflow_enabled() -> bool:
    """Whether the composable-workflow path is enabled (operator flag, DEFAULT OFF)."""
    return os.environ.get("HARNESS_WORKFLOWS_ENABLED") in ("1", "true", "True")


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
        # The read-only repository navigator (Phase 1): five read tools on the
        # SAME registry. No write/execute tool is registered.
        register_code_tools(self.registry)
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
        self.skill_load_errors = self.skill_registry.load_all(
            project_root=self._project_root(),
            project_discovery=self._project_discovery_enabled(),
        )
        self.skill_registry.attach_tool_registry(self.registry)
        self.bus = EventBus()
        self._active: dict[str, asyncio.Task[Any]] = {}
        # ONE process-wide retrieval cache. It is safe to share: in-flight
        # deduplication is keyed per retrieval, so two runs asking for the same
        # dataset at the same moment share a single provider call (Milestone 2H),
        # and a fresh cached result is reused across runs.
        self.retrieval_cache = RetrievalCache()
        # Terminal subsystem (Phase 1 of the execution backbone): ONE manager
        # shared by the agent tools and the HTTP/UI surface. It is constructed
        # BEFORE registration so the tool handlers resolve it. Its events ride the
        # process-wide bus. Persistence + boot reconciliation are wired below.
        from .terminal.runtime import build_terminal_manager, set_terminal_manager  # noqa: PLC0415
        from .terminal.store import TerminalStore  # noqa: PLC0415

        self.terminal_store = TerminalStore(self.store)
        self.terminal = build_terminal_manager(store=self.terminal_store, bus=self.bus)
        set_terminal_manager(self.terminal)
        # The terminal tools are registered on the SAME registry, so validation,
        # permission and the effect authorizer apply unchanged.
        register_terminal_tools(self.registry)
        # The Code Execution & Verification Layer: the orchestrator, runtime
        # registry, scheduler, service manager and execution history, all reusing
        # the terminal manager for long-running services and `code/sandbox.py` for
        # one-shot runs. Its tools register on the SAME registry. Built BEFORE the
        # code store so the orchestrator can persist results once the store exists.
        from .execution.runtime import set_execution_service  # noqa: PLC0415
        from .execution.service import ExecutionService  # noqa: PLC0415
        from .execution.tools import register_execution_tools  # noqa: PLC0415

        self.execution = ExecutionService(store=self.store, terminal=self.terminal)
        set_execution_service(self.execution)
        register_execution_tools(self.registry)
        # The Application Runtime layer (DevOps): discovery, package managers,
        # Docker/Podman/Compose, health checks, ports, diagnostics, bounded
        # recovery. Built on the SAME terminal manager and `code/sandbox.py`; its
        # tools register on the SAME registry, so agent and UI share one engine.
        from .execution.application.manager import ApplicationRuntimeManager, build_runtime_registry  # noqa: PLC0415
        from .execution.application.runtime import set_application_runtime  # noqa: PLC0415
        from .execution.application.store import ApplicationRuntimeStore  # noqa: PLC0415
        from .execution.application.tools import register_application_tools  # noqa: PLC0415

        self.application_store = ApplicationRuntimeStore(self.store)
        self.application_runtime = ApplicationRuntimeManager(
            registry=build_runtime_registry(), terminal=self.terminal,
            store=self.application_store, bus=self.bus,
        )
        set_application_runtime(self.application_runtime)
        register_application_tools(self.registry)
        # Disposable code workspaces (Phase 2): rows in agent-memory.db bound to
        # the one store connection.
        from .code.store import CodeWorkspaceStore  # noqa: PLC0415

        self.code_store = CodeWorkspaceStore(self.store)
        # Git / Version-Control subsystem: ONE process-wide service bound to the
        # same agent-memory connection (journal + active-operation tables). Its
        # journal is owned by the service; the tools resolve it through the module
        # singleton so a tool handler never carries the store. Registered on the
        # SAME registry like the terminal and execution subsystems.
        from .git.register import register_git_subsystem  # noqa: PLC0415
        from .git.service import GitService, set_git_service  # noqa: PLC0415

        self.git = GitService(self.store)
        set_git_service(self.git)
        register_git_subsystem(self.registry)
        # The Code Intelligence & Understanding Engine (CIUE): ONE process-wide
        # runtime holding the LSP manager and a per-workspace code index/watcher.
        # Its events ride the process-wide bus. Built before any run so the
        # `code_*` tools resolve a shared runtime. A failure is a diagnostic.
        try:
            from .code.intel.runtime import build_code_intel_runtime  # noqa: PLC0415

            self.code_intel = build_code_intel_runtime(on_event=self._publish_code_intel_event)
        except Exception:  # noqa: BLE001 - CIUE must never block boot
            self.code_intel = None
            log.warning("code intelligence runtime unavailable", exc_info=True)
        # Trusted workspace roots (folder picker): the persisted allowlist of
        # directories a person approved. The SELECTED root is what
        # `workspace.default_root()` resolves to, after the env override and
        # before the built-in repo root — so zero-config is unchanged and a
        # chosen folder takes effect on the next run without a restart.
        from .code.roots import TrustedRootStore  # noqa: PLC0415
        from .code.workspace import set_trusted_root_provider  # noqa: PLC0415

        self.trusted_roots = TrustedRootStore(self.store)
        set_trusted_root_provider(self._selected_trusted_root)
        # MCP (Phase 5): configured local stdio servers. Construction only reads
        # config; nothing is launched until `start_mcp()`. Selected read-only MCP
        # tools register into THIS registry, so execution stays authoritative.
        self.mcp = MCPManager() if MCP_AVAILABLE else None
        self.mcp_registered_tools: list[str] = []
        # Effectful-tool approvals (5G): persisted in the runtime's own DB and
        # consulted by every run's effect authorizer.
        self.approvals = ApprovalStore(self.store) if MCP_AVAILABLE else None
        # Automatic learning review (M3): a lightweight in-process queue that
        # reviews completed runs after the fact. It creates ONLY inert records /
        # suggestions and never enables a skill. Started/stopped with the runtime.
        from .learning_review import LearningReviewQueue

        self.learning_review = LearningReviewQueue(self.memory, self.store)

        # Memory providers (M8): the native provider plus a candidate provider per
        # configured MCP server. Discovery is not activation — the router only
        # reaches an external provider when policy enables it AND the caller
        # explicitly allows it AND the server is connected.
        from .memory_providers import build_memory_router

        self.memory_router = build_memory_router(self.memory, mcp_manager=self.mcp)

        # Model Runtime (provider-agnostic model layer): route usage/health into
        # this service's own store so model requests are persisted in
        # agent-memory.db — never in the financial JDdS vault.
        try:
            from .model_runtime.store import ModelRuntimeStore

            self.model_runtime_store = ModelRuntimeStore(self.store)
            get_runtime().install_persistence(self.model_runtime_store)
            get_runtime().set_observer(self._observe_model_event)
        except Exception:  # noqa: BLE001 - accounting wiring must not block boot
            self.model_runtime_store = None
            log.warning("model runtime persistence wiring skipped", exc_info=True)

    def _observe_model_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Forward model-runtime observability events onto the harness bus.

        These carry no run id (a routing decision can precede the run's emitter)
        so they are published as process-level events, not persisted per run.
        """
        try:
            self.bus.publish({"type": event_type, "data": data, "at": __import__("time").time()})
        except Exception:  # noqa: BLE001 - observability must never break a run
            pass

    def _publish_code_intel_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Forward CIUE observability events (LSP start/stop/crash, indexing) to the bus.

        Process-level events (an LSP start has no run id), so they are published
        for any global subscriber and never persisted against a run.
        """
        try:
            self.bus.publish({"type": event_type, "data": data, "at": __import__("time").time()})
        except Exception:  # noqa: BLE001
            pass

    def start_code_intel(self) -> dict[str, Any]:
        """Best-effort CIUE startup. Deliberately does NOT index at boot.

        Indexing the whole repository at boot would run on every process start and
        every test client — expensive and unnecessary. The index is built LAZILY and
        incrementally: the first `code_*` query refreshes the index on a worker
        thread (`manager._ensure_fresh`), and the per-workspace watcher keeps it
        current afterwards. Language servers also start lazily on first use. A
        failure here is a diagnostic, never a boot blocker.
        """
        runtime = getattr(self, "code_intel", None)
        if runtime is None:
            return {"available": False}
        try:
            from .code.workspace import default_root  # noqa: PLC0415

            root = default_root()
            return {
                "available": True,
                "root": str(root) if root else None,
                "supportedLanguages": runtime.lsp.supported_languages(),
            }
        except Exception:  # noqa: BLE001
            log.warning("CIUE startup probe failed", exc_info=True)
            return {"available": True, "root": None}

    async def stop_code_intel(self) -> None:
        runtime = getattr(self, "code_intel", None)
        if runtime is None:
            return
        try:
            runtime.stop()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.warning("CIUE shutdown failed", exc_info=True)

    def _selected_trusted_root(self) -> Optional[str]:
        """The path of the selected trusted root, or None. Never raises."""
        try:
            selected = self.trusted_roots.selected()
            return selected.path if selected else None
        except Exception:  # noqa: BLE001 - a root lookup must never break a run
            return None

    def trusted_root_store(self) -> Any:
        """The process-wide trusted-roots registry (folder picker)."""
        return self.trusted_roots

    def _project_root(self) -> Optional[str]:
        """The project root whose local skills may apply, or None.

        The runtime is spawned by the front door from the repo root, so the
        default is the repo containing the harness. `BLACK_ECLIPSE_PROJECT_ROOT`
        overrides it (tests / a workspace pointed at another checkout).
        """
        override = os.environ.get("BLACK_ECLIPSE_PROJECT_ROOT")
        if override:
            return os.path.abspath(override)
        try:
            from .eclipse_memory.config import repo_root  # noqa: PLC0415
            return repo_root()
        except Exception:  # noqa: BLE001
            return None

    def _project_discovery_enabled(self) -> bool:
        try:
            return bool(self.memory.policy.get("project_skill_discovery"))
        except Exception:  # noqa: BLE001 - a policy read failure must fail closed
            return False

    def reload_project_skills(self) -> list[str]:
        """Re-scan project skills after a trust/untrust decision (no restart).

        Returns load errors; untrusted roots contribute notices, not skills.
        """
        self.skill_load_errors = self.skill_registry.load_all(
            project_root=self._project_root(),
            project_discovery=self._project_discovery_enabled(),
        )
        return self.skill_load_errors

    def refresh_memory_router(self) -> None:
        """Rebuild the provider router after an MCP config change."""
        from .memory_providers import build_memory_router

        external = False
        try:
            external = bool(self.memory.policy.get("external_memory_search_enabled"))
        except Exception:  # noqa: BLE001
            external = False
        self.memory_router = build_memory_router(
            self.memory, mcp_manager=self.mcp, external_enabled=external
        )

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

    def start_terminal(self) -> dict[str, Any]:
        """Reconcile persisted terminal state on boot (never blocks startup).

        The registry/manager were built in `__init__`; this only reconciles the
        rows left from a previous process — a dead pid is marked EXITED, a live
        one UNKNOWN (owned but unmanaged), every session is closed. It NEVER
        fabricates a running process and never raises.
        """
        try:
            summary = self.terminal.recovery.reconcile()
            log.info(
                "terminal recovery reconciled %s process record(s), %s session record(s)",
                summary.get("processes"), summary.get("sessions"),
            )
            # Pre-warm one idle shell in the background, so the FIRST UI open
            # adopts an already-running shell and shows a prompt instantly
            # instead of paying PowerShell's startup cost. Best-effort.
            try:
                threading.Thread(target=self.terminal.warm_shell, daemon=True).start()
            except Exception:  # noqa: BLE001
                pass
            return summary
        except Exception:  # noqa: BLE001 - recovery must never block boot
            log.warning("terminal recovery failed", exc_info=True)
            return {"processes": 0, "sessions": 0, "reconciled": [], "error": True}

    async def stop_terminal(self) -> None:
        """Stop every background process and close every session on shutdown."""
        try:
            self.terminal.close_all()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.warning("terminal shutdown failed", exc_info=True)

    def stop_execution(self) -> None:
        """Stop execution services and the scheduler on shutdown (never raises)."""
        layer = getattr(self, "execution", None)
        if layer is None:
            return
        try:
            layer.stop()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.warning("execution shutdown failed", exc_info=True)

    def reconcile_application_runtime(self) -> dict[str, Any]:
        """Reconcile the application runtimes left by a previous process (never raises).

        A runtime that was RUNNING is re-examined: if its processes/containers are
        gone it becomes DEGRADED. Eclipse never fabricates a running runtime.
        """
        manager = getattr(self, "application_runtime", None)
        if manager is None:
            return {"status": "ok", "reconciled": [], "note": "no application runtime"}
        try:
            result = manager.reconcile()
            log.info("application runtime reconciled %s runtime(s)", result.get("count", 0))
            return result
        except Exception:  # noqa: BLE001 - reconciliation must never block boot
            log.warning("application runtime reconciliation failed", exc_info=True)
            return {"status": "error", "reconciled": []}

    def stop_application_runtime(self) -> None:
        """Stop every application this process started, on shutdown (never raises)."""
        manager = getattr(self, "application_runtime", None)
        if manager is None:
            return
        try:
            for handle in list(manager._runtimes.values()):  # noqa: SLF001
                if handle.state.value not in ("STOPPED", "FAILED"):
                    manager.stop(handle.runtime_id)
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.warning("application runtime shutdown failed", exc_info=True)

    async def start_mcp(self) -> None:
        """Connect enabled MCP servers and register selected read-only tools.

        Called once at service startup. A server failure is recorded as a
        diagnostic and does not block the runtime or other servers. When the MCP
        SDK is absent, this is a no-op and MCP reports UNAVAILABLE honestly.
        """
        if self.mcp is None:
            return
        try:
            # A process-wide bridge is used only for secret resolution at spawn;
            # per-run tools still receive their own run bridge.
            bridge = self.build_bridge(
                _default_callback_base_url(), None
            )
            self.mcp.set_secret_resolver(self._secret_resolver(bridge))
            self.mcp.set_bridge_fetch(self._raw_bridge_fetch(bridge))
            # Process-level MCP events (e.g. `mcp.catalog.changed`) have no run id;
            # publish them on the shared bus so any global subscriber sees them.
            # The server card additionally surfaces the same facts via lifecycle
            # status, so the signal is not lost when nothing is subscribed.
            self.mcp.set_event_sink(self._publish_mcp_event)
            await self.mcp.start()
            self.mcp_registered_tools = self.mcp.register_selected_tools(self.registry)
        except Exception:  # noqa: BLE001 - MCP must never prevent the runtime booting
            log.warning("MCP startup failed", exc_info=True)

    async def _publish_mcp_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish a process-level MCP event on the shared bus (no run id).

        Content-free: MCP events carry counts and identity only, never content.
        """
        from .persistence import now_iso

        self.bus.publish({
            "id": f"mcp_{event_type}_{now_iso()}",
            "runId": None,
            "type": event_type,
            "seq": 0,
            "at": now_iso(),
            "data": data or {},
        })

    def _raw_bridge_fetch(self, bridge: DataBridge):
        """A raw `(capability, params) -> dict` fetch for the OAuth token store."""

        async def fetch(capability: str, params: dict[str, Any]) -> dict[str, Any]:
            return await bridge.fetch(capability, params)

        return fetch

    def _sampling_model_factory(self, request: RunRequest):
        """Build the `(policy, prompt) -> str` factory for a server sampling call.

        Uses the runtime's OWN model adapter (`models.build_chat_model`) with the
        RUN's credentials, capped by the policy's max tokens. Sampling stays off
        by default; this only ever runs when the operator enabled it for a server.
        """
        settings = request.modelSettings

        async def factory(policy: Any, prompt: str) -> str:
            from langchain_core.messages import HumanMessage

            from .models import build_chat_model

            runtime = get_runtime()
            resolution = runtime.resolve_for_run(settings, task="simple_chat")
            model = runtime.build(
                resolution.settings, builder=build_chat_model, adapter=resolution.adapter
            )
            # Best-effort token cap (providers that accept `max_tokens`).
            try:
                bound = model.bind(max_tokens=policy.clamped_max_tokens())
            except Exception:  # noqa: BLE001 - a provider may not accept the kwarg
                bound = model
            response = await bound.ainvoke([HumanMessage(content=str(prompt))])
            content = getattr(response, "content", None)
            if isinstance(content, list):
                return "\n".join(str(getattr(b, "text", b)) for b in content)
            return str(content if content is not None else response)

        return factory

    async def stop_mcp(self) -> None:
        if self.mcp is None:
            return
        try:
            await self.mcp.close()
        except Exception:  # noqa: BLE001
            log.warning("MCP shutdown failed", exc_info=True)

    def run_startup_maintenance(self) -> dict[str, Any]:
        """Run one-time memory + skill maintenance at runtime startup.

        Currently the retention sweep (due AUTOMATIC memories become inert) plus
        the deterministically-computed skill maintenance pass (report-only by
        default; it can only age enabled, unpinned, unused skills and never
        deletes). Both are idempotent, best-effort, and NEVER raise — a failure
        must not stop the application or agent runtime from starting. There is no
        new daemon or thread; this reuses the existing FastAPI lifespan hook.
        """
        try:
            result = self.memory.run_retention_maintenance()
        except Exception:  # noqa: BLE001 - startup maintenance must never block boot
            log.warning("startup memory maintenance failed", exc_info=True)
            result = {"ok": False, "error": "maintenance failed"}
        try:
            result["skillMaintenance"] = self.run_skill_maintenance()
        except Exception:  # noqa: BLE001 - skill maintenance must never block boot
            log.warning("startup skill maintenance failed", exc_info=True)
            result["skillMaintenance"] = {"ok": False, "error": "maintenance failed"}
        try:
            from .code.worktree import sweep_expired  # noqa: PLC0415

            result["codeWorkspaceSweep"] = {"released": sweep_expired()}
        except Exception:  # noqa: BLE001 - the sweep must never block boot
            log.warning("code workspace sweep failed", exc_info=True)
            result["codeWorkspaceSweep"] = {"ok": False, "error": "sweep failed"}
        return result

    def run_skill_maintenance(self) -> dict[str, Any]:
        """One skill-maintenance pass (report-only unless policy opts in).

        Idempotent, never raises, no new daemon. Wired into the existing startup
        lifespan exactly like the retention sweep.
        """
        from .skills.maintenance import run_skill_maintenance  # noqa: PLC0415

        return run_skill_maintenance(
            self.skill_store, self.skill_registry, self.memory.policy.get_all(),
        )

    def skill_maintenance_report(self) -> dict[str, Any]:
        """Read-only skill-maintenance report (stale skills, reasons, actions)."""
        from .skills.maintenance import maintenance_report  # noqa: PLC0415

        return maintenance_report(self.skill_store, self.memory.policy.get_all())

    async def start_learning_review(self) -> None:
        """Start the bounded learning-review queue workers (idempotent)."""
        try:
            await self.learning_review.start()
        except Exception:  # noqa: BLE001 - review is optional and must not block boot
            log.warning("learning review queue failed to start", exc_info=True)

    async def stop_learning_review(self) -> None:
        try:
            await self.learning_review.stop()
        except Exception:  # noqa: BLE001
            log.warning("learning review shutdown failed", exc_info=True)

    async def reload_mcp(self) -> dict[str, Any]:
        """Apply a persisted MCP config change without a runtime restart.

        Removes only the MCP tools this manager added, then reconnects and
        re-registers from the current config file. Returns non-secret status.
        """
        from .mcp.config import load_mcp_configs

        if self.mcp is None:
            return {"configured": 0, "connected": 0, "registeredTools": 0, "loadDiagnostics": [], "unavailable": True}
        configs, diagnostics = load_mcp_configs()
        self.mcp.load_diagnostics = diagnostics
        self.mcp_registered_tools = await self.mcp.reload(configs)
        # Rebuild the provider router so newly configured/removed MCP servers are
        # (or are no longer) candidate memory providers. Discovery is not
        # activation: the router still requires explicit policy + call opt-in.
        self.refresh_memory_router()
        return self.mcp.summary()

    async def oauth_login(self, server_id: str, *, client_id: Any = None, scope: str = "") -> dict[str, Any]:
        """Run an OAuth device-code login for a remote MCP server."""
        if self.mcp is None:
            return {"success": False, "reason": "MCP is unavailable (runtime missing the mcp SDK)"}
        return await self.mcp.oauth_login(server_id, client_id=client_id, scope=scope)

    async def oauth_logout(self, server_id: str) -> dict[str, Any]:
        """Clear a server's stored credentials; it stays configured but disconnected."""
        if self.mcp is None:
            return {"success": False, "reason": "MCP is unavailable"}
        return await self.mcp.oauth_logout(server_id)

    def install_mcp_integration(self, integration_id: str) -> dict[str, Any]:
        """Install a preset integration as a DISABLED, nothing-selected config.

        The user must not hand-edit JSON for a server Eclipse recommends. Nothing
        ships enabled or selected; the operator reviews and activates.

        Install is create-if-absent: if a server with the integration's id is
        already configured, the existing entry is left untouched, so re-installing
        never resets a change the user made (trust tier, selection, effects,
        declared data sources, confirmation).
        """
        from .mcp.config import load_mcp_configs, upsert_mcp_config
        from .mcp.presets import integration, integration_to_config
        from .mcp.screening import refusals, screen_entry

        spec = integration(integration_id)
        if spec is None:
            return {"success": False, "reason": "unknown integration"}
        existing, _ = load_mcp_configs()
        if any(c.id == spec.id for c in existing):
            return {
                "success": True,
                "installed": integration_id,
                "alreadyInstalled": True,
                "reason": "already configured; left unchanged",
            }
        entry = integration_to_config(spec)
        blocked = refusals(screen_entry(entry))
        if blocked:
            return {"success": False, "reason": blocked[0].message}
        from .mcp.config import MCPServerConfig

        upsert_mcp_config(MCPServerConfig(**entry))
        if self.mcp is not None:
            self.mcp.load_diagnostics = []
        return {"success": True, "installed": integration_id, "config": entry}

    async def verify_mcp_server(
        self, server_id: str, *, tool: str, arguments: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Operator-triggered credential verification (one bounded read call).

        Never automatic, never at boot, never in a loop. Distinct from Test,
        which only proves the process started and listed tools.
        """
        if self.mcp is None:
            return {"success": False, "reason": "MCP is unavailable (runtime missing the mcp SDK)"}
        result = await self.mcp.verify_credentials(server_id, tool=tool, arguments=arguments or {})
        return {"success": True, **result}

    def reset_mcp_circuit(self, server_id: str) -> dict[str, Any]:
        """Operator reset of a server's circuit breaker (back to CLOSED)."""
        if self.mcp is None:
            return {"success": False, "reason": "MCP is unavailable"}
        return self.mcp.reset_circuit(server_id)

    async def confirm_mcp_catalog(self, server_id: str) -> dict[str, Any]:
        """Snapshot the live catalog digest as the operator's reviewed version.

        This is the explicit review act that lets an annotation-sourced read-only
        tool activate. Doing it re-reads config, records the digest, and reloads
        so activation takes effect immediately.
        """
        from .mcp.config import load_mcp_configs, upsert_mcp_config

        if self.mcp is None:
            return {"success": False, "reason": "MCP is unavailable"}
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
        # Bind server-initiated sampling to THIS run's model (still off by
        # default per server; a request is refused unless the operator enabled it).
        if self.mcp is not None:
            self.mcp.set_sampling_model_factory(self._sampling_model_factory(request))
        # Foreground activity: defer expensive background reviews to a short idle.
        try:
            self.learning_review.mark_user_active()
        except Exception:  # noqa: BLE001 - scheduling hint only
            pass
        # The retrieval layer is built lazily by the retrieval tools from the
        # run context (so its events reach the emitter); only the shared cache is
        # passed here.
        result = await execute_run(
            request, self.registry, bridge, self.store, self.bus,
            retrieval_cache=self.retrieval_cache,
            memory_service=self.memory, skill_registry=self.skill_registry,
            approvals=self.approvals, memory_router=self.memory_router,
            mcp_manager=self.mcp, code_store=self.code_store,
            code_intel_runtime=getattr(self, "code_intel", None),
        )
        await self._schedule_review(request.runId, result.status)
        return result

    def run_lineage(self) -> Any:
        """The process-wide lineage/checkpoint store (Phase 1)."""
        from .run_lineage import RunLineage

        if getattr(self, "_lineage", None) is None:
            self._lineage = RunLineage(self.store)
        return self._lineage

    def code_tasks(self) -> Any:
        """The process-wide code-task view over the ONE run lineage (Phase 5)."""
        from .code.tasks import TaskStore  # noqa: PLC0415

        if getattr(self, "_code_tasks", None) is None:
            self._code_tasks = TaskStore(self.store)
        return self._code_tasks

    def workflow_store(self) -> Any:
        """The process-wide workflow definition store (Phase 5)."""
        from .workflows import WorkflowStore

        if getattr(self, "_workflow_store", None) is None:
            self._workflow_store = WorkflowStore(self.store)
        return self._workflow_store

    def evolution_store(self) -> Any:
        """The process-wide evolution store over the ONE agent-memory connection (Phase 10)."""
        from .code.evolution_store import EvolutionStore  # noqa: PLC0415

        if getattr(self, "_evolution_store", None) is None:
            self._evolution_store = EvolutionStore(self.store)
        return self._evolution_store

    def operator_actor(self) -> Any:
        """The operator Actor used by the evolution routes (already authorized)."""
        from .skills.permissions import OPERATOR_ACTOR  # noqa: PLC0415

        return OPERATOR_ACTOR

    def evolution_context(self, *, run_id: str) -> Any:
        """A ToolContext for an evolution evaluation run (broker + ledger + store)."""
        from .code.store import CodeWorkspaceStore  # noqa: PLC0415
        from .code.verify import VerificationLedger  # noqa: PLC0415
        from .tools import ToolContext  # noqa: PLC0415

        try:
            self.store.create_run(run_id, "evolution", {"query": "self-improvement evaluation"})
        except Exception:  # noqa: BLE001 - a duplicate run id is fine
            pass
        return ToolContext(
            run_id=run_id,
            log=lambda *_: None,
            memory_store=self.store,
            code_store=self.code_store or CodeWorkspaceStore(self.store),
            code_ledger=VerificationLedger(run_id),
            memory_service=self.memory,
            skill_registry=self.skill_registry,
            tool_registry=self.registry,
        )

    def jobs_store(self) -> Any:
        """The process-wide job store over the ONE agent-memory connection (Phase 6)."""
        from .jobs.store import JobStore  # noqa: PLC0415

        if getattr(self, "_jobs_store", None) is None:
            self._jobs_store = JobStore(self.store)
        return self._jobs_store

    async def start_jobs(self) -> None:
        """Start the harness job scheduler (Phase 6). Idempotent.

        A failure is a diagnostic, never a boot blocker — exactly like
        `start_mcp()`. With no Python runtime, jobs simply do not tick.
        """
        from .jobs.scheduler import JobScheduler  # noqa: PLC0415

        try:
            if getattr(self, "jobs", None) is None:
                self.jobs = JobScheduler(self, self.jobs_store())
            await self.jobs.start()
        except Exception:  # noqa: BLE001 - the scheduler must never block boot
            log.warning("job scheduler failed to start", exc_info=True)

    async def stop_jobs(self) -> None:
        scheduler = getattr(self, "jobs", None)
        if scheduler is None:
            return
        try:
            await scheduler.stop()
        except Exception:  # noqa: BLE001
            log.warning("job scheduler shutdown failed", exc_info=True)

    async def run_workflow(self, request: RunRequest) -> Any:
        """Execute a saved workflow by id over the existing graph (Phase 5).

        The workflow path is FLAG-GATED and DEFAULT OFF. With no `workflowId`
        a run behaves exactly as today (the ordinary `run` path). When enabled
        and the workflow exists, it compiles onto the existing graph.
        """
        from .workflows import compile_workflow

        if not _workflow_enabled():
            return {
                "workflowId": request.workflowId,
                "status": "disabled",
                "note": "the workflow path is disabled; set HARNESS_WORKFLOWS_ENABLED=1 to enable it",
            }
        workflow = self.workflow_store().get(request.workflowId)
        if workflow is None:
            return {
                "workflowId": request.workflowId,
                "status": "not_found",
                "note": f"no workflow {request.workflowId!r} is stored",
            }
        bridge = _HttpDataBridge(request.callbackBaseUrl, request.callbackToken)
        result = await compile_workflow(
            workflow, request, self.registry, bridge, self.store, bus=self.bus,
            retrieval_cache=self.retrieval_cache, memory_service=self.memory,
            skill_registry=self.skill_registry, approvals=self.approvals,
            memory_router=self.memory_router, mcp_manager=self.mcp,
        )
        return result.to_dict()

    async def _schedule_review(self, run_id: str, status: str) -> None:
        """Queue a bounded post-run learning review (never blocks the response)."""
        if status not in ("completed", "failed"):
            return
        try:
            run = self.store.get_run(run_id) or {}
            # Deterministic priority: a failed run is a stronger signal than a
            # completed one. Explicit corrections would be `critical`.
            priority = "medium" if status == "failed" else "normal"
            await self.learning_review.enqueue(
                run_id, priority=priority,
                session_id=run.get("chatId") or run.get("sessionId"),
                profile_id=run.get("userId"),
            )
        except Exception:  # noqa: BLE001 - scheduling must never affect the run
            log.warning("learning review scheduling failed", exc_info=True)

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
                result = await execute_run(
                    request, self.registry, bridge, self.store, self.bus,
                    retrieval_cache=self.retrieval_cache,
                    memory_service=self.memory, skill_registry=self.skill_registry,
                    approvals=self.approvals, memory_router=self.memory_router,
                    mcp_manager=self.mcp, code_store=self.code_store,
                    code_intel_runtime=getattr(self, "code_intel", None),
                )
                await self._schedule_review(request.runId, result.status)
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

    def list_receipts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Research receipts for the read-only Eclipse-as-server surface."""
        return self.store.list_receipts(limit)

    def get_receipt(self, run_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_receipt(run_id)

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
