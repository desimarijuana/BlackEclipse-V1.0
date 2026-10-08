"""Process-level orchestration service wrapper.

Holds the ONE orchestration store bound to the runtime's agent-memory connection,
a primary engine for recovery/queries, and any per-request engines created with a
caller's model settings. It never duplicates the tool registry or the event bus —
both come from the shared `AgenticService`.
"""

from __future__ import annotations

from typing import Any, Optional

from .engine import EngineConfig, OrchestrationEngine
from .runner import RuntimeContext
from .store import OrchestrationStore

_MAX_ENGINES = 64


def _builtin_reducers() -> dict[str, Any]:
    from .tools import _reduce_list, _reduce_merge, _reduce_text

    return {"reduce_list": _reduce_list, "reduce_merge": _reduce_merge, "reduce_text": _reduce_text}


class OrchestrationService:
    def __init__(self, service: Any) -> None:
        self._service = service
        self.store = OrchestrationStore(service.store)
        self._engines: list[OrchestrationEngine] = []
        self.primary = self._new_engine(self._base_runtime(), track=False)

    # ── runtime construction ─────────────────────────────────────────────────

    def _base_runtime(self) -> RuntimeContext:
        bridge = None
        try:
            import os

            base_url = os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
            bridge = self._service.build_bridge(base_url, os.environ.get("CRON_SECRET"))
        except Exception:  # noqa: BLE001 - a missing bridge is handled per node
            bridge = None
        return RuntimeContext(
            registry=self._service.registry,
            data_bridge=bridge,
            store=self._service.store,
            bus=self._service.bus,
            run_id="",
        )

    def runtime_for(
        self, *,
        model_settings: Any = None,
        callback_base_url: str = "",
        callback_token: Optional[str] = None,
        user_id: Optional[str] = None,
        allowed: Optional[set[str]] = None,
        run_id: str = "",
    ) -> RuntimeContext:
        return self._base_runtime().extend(
            model_settings=model_settings,
            callback_base_url=callback_base_url,
            callback_token=callback_token,
            user_id=user_id,
            allowed=allowed,
            run_id=run_id,
        )

    # ── engines ──────────────────────────────────────────────────────────────

    def _new_engine(self, runtime: RuntimeContext, *, track: bool = True) -> OrchestrationEngine:
        engine = OrchestrationEngine(self.store, runtime, config=EngineConfig.from_env())
        for name, fn in _builtin_reducers().items():
            engine.register_callable(name, fn)
        if track:
            self._prune()
            self._engines.append(engine)
        return engine

    def _prune(self) -> None:
        """Drop the oldest engine once the list is large and it has nothing active."""
        if len(self._engines) < _MAX_ENGINES:
            return
        for index, engine in enumerate(self._engines):
            if all(ex.done.is_set() for ex in engine._executions.values()):  # noqa: SLF001
                self._engines.pop(index)
                return
        self._engines.pop(0)  # all busy: bound memory anyway

    def new_engine(self, runtime: RuntimeContext) -> OrchestrationEngine:
        return self._new_engine(runtime, track=True)

    def find(self, execution_id: str) -> OrchestrationEngine:
        """The engine that owns a live execution, else the primary engine."""
        for engine in reversed(self._engines):
            if execution_id in engine._executions:  # noqa: SLF001 - deliberate
                return engine
        return self.primary

    def status(self) -> dict[str, Any]:
        return {"primary": self.primary.summary(), "engines": len(self._engines) + 1}


__all__ = ["OrchestrationService"]
