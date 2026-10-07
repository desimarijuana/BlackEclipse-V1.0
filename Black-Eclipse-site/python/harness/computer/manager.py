"""The process-wide ComputerManager.

Owns every live `ComputerSession`, the ONE driver, the accessibility/OCR/vision
engines, the takeover leases, the telemetry and the durable store. It is the ONLY
thing that creates or destroys a session, enforces the concurrency limit and
performs deterministic cleanup.

Tools resolve it through the module singleton, so the agent, the HTTP router and
the CLI share one desktop runtime. It never fabricates: a missing driver is an
honest `UNAVAILABLE`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from .config import ComputerConfig, computer_config, MAX_SESSIONS_CEILING
from .diagnostics import diagnose
from .drivers import build_driver
from .errors import ComputerError, ComputerUnavailable
from .finance.firewall import build_firewall_from_config
from .ocr import build_ocr_engine
from .session import ComputerSession, SessionState
from .store import ComputerStore, new_session_id
from .takeover import TakeoverManager
from .telemetry import ComputerTelemetry
from .policy import default_policy
from .security import SecurityLayer
from .finance.extractor import FinancialExtractor

log = logging.getLogger("harness.computer.manager")


class ComputerManager:
    def __init__(self, *, config: Optional[ComputerConfig] = None, agent_store: Any = None,
                 bus: Any = None, vision: Any = None) -> None:
        self.config = config or computer_config()
        self.bus = bus
        self.store = ComputerStore(agent_store) if agent_store is not None else None
        self.driver = build_driver(self.config.driver_backend)
        self.ax = None
        self.ocr = build_ocr_engine(self.config.ocr_backend)
        # The vision router is built lazily at start (it needs model settings); a
        # provided router wins, otherwise an honest unavailable router is used.
        self.vision = vision
        self.takeover = TakeoverManager()
        self.telemetry = ComputerTelemetry(bus=bus)
        self.security = SecurityLayer(redaction_enabled=self.config.sensitive_data_redaction)
        self.extractor = FinancialExtractor()
        self._sessions: dict[str, ComputerSession] = {}
        self._lock = asyncio.Lock()
        self._sweep_task: Optional[asyncio.Task[Any]] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self, *, vision: Any = None) -> None:
        if vision is not None:
            self.vision = vision
        if self.vision is None:
            from .vision.router import VisionRouter  # noqa: PLC0415
            from .vision.backends import UnavailableVision  # noqa: PLC0415

            self.vision = VisionRouter(local=UnavailableVision("no multimodal model is configured"))
        try:
            await self.driver.start()
        except Exception:  # noqa: BLE001 - driver start must never block boot
            log.warning("computer driver failed to start", exc_info=True)
        self.ax = getattr(self.driver, "_ax", None)
        if self.ax is None:
            from .accessibility.null import NullAXProvider  # noqa: PLC0415

            self.ax = NullAXProvider()

    async def stop(self) -> None:
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None
        for session_id in list(self._sessions.keys()):
            try:
                await self.destroy_session(session_id)
            except Exception:  # noqa: BLE001 - shutdown must never raise
                pass
        try:
            await self.driver.stop()
        except Exception:  # noqa: BLE001
            pass

    async def start_sweeper(self) -> None:
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(max(30, self.config.idle_timeout_seconds // 3))
                try:
                    await self.sweep_idle()
                except Exception:  # noqa: BLE001
                    pass
        except asyncio.CancelledError:
            return

    # ── capabilities / health ────────────────────────────────────────────────

    def capabilities(self) -> dict[str, Any]:
        caps = self.driver.capabilities()
        caps.ocr = bool(getattr(self.ocr, "available", False))
        caps.vision = bool(getattr(self.vision, "engine", None) and self.vision.engine(sensitive=False).available) if self.vision else False
        return {
            "enabled": self.config.enabled,
            "driver": self.driver.id,
            "contract": self.driver.contract().to_dict(),
            "capabilities": caps.to_dict(),
            "policy": default_policy().to_dict(),
            "limits": {
                "maxConcurrent": self.config.max_concurrent,
                "maxActions": self.config.max_actions,
                "idleTimeoutSeconds": self.config.idle_timeout_seconds,
                "actionTimeoutSeconds": self.config.action_timeout_seconds,
            },
            "artifactsRoot": str(self.config.artifacts_root),
        }

    def health(self) -> dict[str, Any]:
        return {
            "driver": self.driver.health(),
            "sessions": len(self._sessions),
            "activeSessions": self.active_count(),
            "ocr": self.ocr_description(),
            "vision": self.vision_description(),
        }

    def ocr_available(self) -> bool:
        return bool(getattr(self.ocr, "available", False))

    def ocr_description(self) -> str:
        try:
            return str(self.ocr.describe())
        except Exception:  # noqa: BLE001
            return "unknown"

    def vision_available(self) -> bool:
        try:
            return bool(self.vision and self.vision.engine(sensitive=False).available)
        except Exception:  # noqa: BLE001
            return False

    def vision_description(self) -> str:
        try:
            return str(self.vision.describe()) if self.vision else "unavailable"
        except Exception:  # noqa: BLE001
            return "unknown"

    def doctor(self) -> dict[str, Any]:
        return diagnose(self)

    # ── sessions ─────────────────────────────────────────────────────────────

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.state.terminal)

    async def create_session(
        self,
        *,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        machine_id: str = "",
        risk_mode: Optional[str] = None,
        policy: Any = None,
    ) -> ComputerSession:
        if not self.config.enabled:
            raise ComputerUnavailable("The Computer Use capability is disabled in configuration.", code="COMPUTER_DISABLED")
        if self.driver.id == "null":
            raise ComputerUnavailable(
                self.driver.capabilities().notes[0] if self.driver.capabilities().notes else "no desktop driver is available",
                code="COMPUTER_DRIVER_UNAVAILABLE",
            )
        async with self._lock:
            if self.active_count() >= min(self.config.max_concurrent, MAX_SESSIONS_CEILING):
                from .errors import ActionFailed  # noqa: PLC0415

                raise ActionFailed(
                    f"Eclipse already has {self.active_count()} desktop sessions open.",
                    code="COMPUTER_SESSION_LIMIT",
                )
        session_id = new_session_id()
        session = ComputerSession(
            session_id=session_id, driver=self.driver, ax=self.ax, ocr=self.ocr,
            vision_router=self._router(), config=self.config, store=self.store,
            telemetry=self.telemetry, agent_id=agent_id, user_id=user_id, task_id=task_id,
            run_id=run_id, machine_id=machine_id,
            policy=policy or default_policy(),
            risk_mode=risk_mode or self.config.finance_mode, bus=self.bus,
        )
        # Bind the session to its control lease so the core's takeover guard reads
        # ONE authority (the manager's TakeoverManager).
        session._lease_check = lambda: self.takeover.agent_may_act(session_id)  # noqa: SLF001
        self._sessions[session_id] = session
        self._emit("computer.session.created", session.snapshot_summary())
        return session

    def _router(self) -> Any:
        if self.vision is None:
            from .vision.router import VisionRouter  # noqa: PLC0415
            from .vision.backends import UnavailableVision  # noqa: PLC0415

            return VisionRouter(local=UnavailableVision())
        return self.vision

    def get_session(self, session_id: str) -> Optional[ComputerSession]:
        return self._sessions.get(session_id)

    def require_session(self, session_id: str) -> ComputerSession:
        session = self._sessions.get(session_id)
        if session is None or session.state.terminal:
            raise ComputerUnavailable(f"Desktop session {session_id!r} isn't open.", code="COMPUTER_SESSION_NOT_FOUND")
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        return [s.snapshot_summary() for s in self._sessions.values()]

    def any_session(self) -> Optional[ComputerSession]:
        live = [s for s in self._sessions.values() if not s.state.terminal]
        if not live:
            return None
        return max(live, key=lambda s: s.last_activity)

    async def destroy_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return {"destroyed": False, "reason": "no such session"}
        await session.close()
        self._emit("computer.session.destroyed", {"sessionId": session_id})
        return {"destroyed": True, "sessionId": session_id}

    async def sweep_idle(self) -> list[str]:
        now = time.time()
        expired: list[str] = []
        for session_id, session in list(self._sessions.items()):
            if session.state.terminal or session.state in (SessionState.PAUSED, SessionState.HUMAN_REQUIRED):
                continue
            if now - session.last_activity > self.config.idle_timeout_seconds:
                expired.append(session_id)
        for session_id in expired:
            await self.destroy_session(session_id)
        return expired

    # ── takeover ─────────────────────────────────────────────────────────────

    def lease_allows_agent(self, session_id: str) -> bool:
        return self.takeover.agent_may_act(session_id)

    # ── finance firewall ─────────────────────────────────────────────────────

    def firewall(self) -> Any:
        return build_firewall_from_config(self.config)

    # ── events ───────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.bus is None:
            return
        try:
            from ..persistence import now_iso  # noqa: PLC0415

            self.bus.publish({
                "id": f"computer_{event_type}_{now_iso()}", "runId": None,
                "type": event_type, "seq": 0, "at": now_iso(), "data": data,
            })
        except Exception:  # noqa: BLE001 - observability must never break a session
            pass


__all__ = ["ComputerManager"]
