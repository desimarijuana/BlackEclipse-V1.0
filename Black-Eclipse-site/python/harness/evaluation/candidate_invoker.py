"""RSL candidate execution: a validated harness snapshot on the real graph.

A candidate is a `HarnessSnapshot` (prompt, tool subset, step/call ceilings,
optional model identity, inert skill-draft ids). This module is the bridge from
that data-only contract to the ONE runtime:

* `validate_snapshot` refuses a tool outside the base allowlist, a raised
  ceiling, or a skill id the base did not authorize;
* `CandidateAgentInvoker` runs each trial in a private temp store + registry,
  binds the trial environment, and calls the real `execute_run`;
* `assert_landable_target` (re-exported) refuses a subject that owns the judge
  or the landing machinery.

It never writes the production store and never activates anything.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Optional

from .. import graph as graph_module
from ..events import EventBus
from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..self_improvement.models import HarnessSnapshot
from ..self_improvement.security import (
    RSL_DENY_GLOBS,
    RSLTargetError,
    assert_landable_target,
)
from .environments import Environment
from .runner import (
    InvocationResult,
    ScriptedModel,
    _MODEL_OVERRIDE,
    _UnavailableBridge,
    _build_registry,
    _enrich_tool_args,
    _safe_run_id,
    _script_messages,
    _usage_for_run,
    install_model_seam,
)


class SnapshotError(ValueError):
    """A candidate snapshot is not a legal variation of the base harness."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


def validate_snapshot(base: HarnessSnapshot, candidate: HarnessSnapshot) -> HarnessSnapshot:
    """Return `candidate` when it is a bounded variation of `base`, else raise."""
    if not isinstance(base, HarnessSnapshot) or not isinstance(candidate, HarnessSnapshot):
        raise SnapshotError("SNAPSHOT_INVALID", "base and candidate must be HarnessSnapshot values")

    extra_tools = sorted(set(candidate.toolNames) - set(base.toolNames))
    if extra_tools:
        raise SnapshotError(
            "SNAPSHOT_TOOL_NOT_IN_BASE",
            "tools not in the base allowlist: " + ", ".join(extra_tools),
        )
    if candidate.maxSteps > base.maxSteps:
        raise SnapshotError(
            "SNAPSHOT_STEPS_EXCEED_BASE",
            f"maxSteps {candidate.maxSteps} exceeds the base ceiling {base.maxSteps}",
        )
    if candidate.maxToolCalls > base.maxToolCalls:
        raise SnapshotError(
            "SNAPSHOT_TOOL_CALLS_EXCEED_BASE",
            f"maxToolCalls {candidate.maxToolCalls} exceeds the base ceiling {base.maxToolCalls}",
        )
    extra_skills = sorted(set(candidate.skillDraftIds) - set(base.skillDraftIds))
    if extra_skills:
        raise SnapshotError(
            "SNAPSHOT_UNKNOWN_SKILL",
            "skill drafts not in the base set: " + ", ".join(extra_skills),
        )
    return candidate


def base_snapshot_from_agent(
    agent: Any,
    *,
    tool_names: Optional[tuple[str, ...]] = None,
) -> HarnessSnapshot:
    """Build the base snapshot from a production `AgentConfig` (or a preset).

    `agent.tools=None` means "all registered tools" to the runtime, which is too
    broad to be a base allowlist. Pass `tool_names` explicitly in that case.
    """
    names = tool_names if tool_names is not None else (getattr(agent, "tools", None) or ())
    return HarnessSnapshot(
        systemPrompt=str(getattr(agent, "systemPrompt", "") or "Eclipse agent"),
        toolNames=tuple(names),
        maxSteps=int(getattr(agent, "maxSteps", 8) or 8),
        maxToolCalls=int(getattr(agent, "maxToolCalls", 200) or 200),
    )


def _ui_bundle(store: AgentMemoryStore) -> tuple[Any, Any]:
    """The trial's UI/task runtime over the trial's OWN store."""
    from ..tasks.manager import TaskManager  # noqa: PLC0415
    from ..tasks.store import TaskStore  # noqa: PLC0415
    from ..ui.catalog import UiCatalog  # noqa: PLC0415
    from ..ui.service import UiService  # noqa: PLC0415
    from ..ui.store import UiStore  # noqa: PLC0415

    task_manager = TaskManager(TaskStore(store))
    ui_service = UiService(UiStore(store), UiCatalog(), tasks=task_manager)
    return ui_service, task_manager


class CandidateAgentInvoker:
    """Run a validated `HarnessSnapshot` through the real runtime, isolated."""

    name = "candidate"

    def __init__(
        self,
        store: AgentMemoryStore,
        snapshot: HarnessSnapshot,
        *,
        base: HarnessSnapshot,
        allow_live_bridge: bool = False,
    ) -> None:
        if allow_live_bridge:
            raise SnapshotError(
                "CANDIDATE_LIVE_BRIDGE_UNAVAILABLE",
                "the live data bridge is not wired for candidate runs in R3",
            )
        self.store = store
        self.base = base
        self.snapshot = validate_snapshot(base, snapshot)
        install_model_seam()

    def _agent_for(self, task: Any, registry: Any) -> AgentConfig:
        registered = set(registry.names())
        unknown = sorted(set(self.snapshot.toolNames) - registered)
        if unknown:
            raise SnapshotError(
                "CANDIDATE_UNKNOWN_TOOL",
                "tools not registered for this trial: " + ", ".join(unknown),
            )
        forbidden = set(getattr(task, "forbidden_tools", ()) or ())
        allowed = [name for name in self.snapshot.toolNames if name not in forbidden]
        limits = getattr(task, "limits", None)
        task_max_tool_calls = int(
            getattr(limits, "max_tool_calls", self.snapshot.maxToolCalls)
            or self.snapshot.maxToolCalls
        )
        task_max_steps = int(
            getattr(limits, "max_turns", self.snapshot.maxSteps) or self.snapshot.maxSteps
        )
        return self.snapshot.to_agent_config().model_copy(update={
            "tools": allowed,
            "maxSteps": min(self.snapshot.maxSteps, task_max_steps),
            "maxToolCalls": min(self.snapshot.maxToolCalls, task_max_tool_calls),
        })

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        script = getattr(task, "agent_script", [])
        run_id = _safe_run_id(task, trial_id)
        if not script:
            return InvocationResult(
                run_id=run_id, status="unmeasured",
                unmeasured_reason="task ships no deterministic script (live tier only)",
            )

        recorded: list[dict[str, Any]] = []
        registry = _build_registry(recorded)
        try:
            agent = self._agent_for(task, registry)
        except SnapshotError as exc:
            return InvocationResult(
                run_id=run_id, status="failed", error=exc.to_dict(),
                agent={"id": "rsl-candidate"}, model={"candidate": True},
            )

        settings = ModelSettings(
            provider=self.snapshot.modelProvider or "ollama",
            model=self.snapshot.modelName or f"evaluation-{trial_id}",
            base_url="http://localhost:11434/v1",
            temperature=self.snapshot.temperature,
        )
        request = RunRequest(
            runId=run_id,
            input=RunInput(query=str(getattr(task, "input", {}).get("prompt") or task.name)),
            agent=agent,
            modelSettings=settings,
            callbackBaseUrl="http://localhost:3000", liveSurface=False,
        )

        trial_dir = tempfile.mkdtemp(prefix="be-rsl-trial-")
        trial_store = AgentMemoryStore(os.path.join(trial_dir, "agent-memory.db"))
        bus = EventBus()
        collected: list[dict[str, Any]] = []
        unsubscribe = bus.subscribe(lambda ev: collected.append(ev))

        from .tools import bind_environment, reset_environment  # noqa: PLC0415
        from ..ui.bootstrap import get_ui_service, set_ui_service  # noqa: PLC0415

        ui_service, task_manager = _ui_bundle(trial_store)
        previous_ui = get_ui_service()
        set_ui_service(ui_service)
        bound = False
        if hasattr(environment, "bind"):
            environment.bind(
                ui_service=ui_service, task_manager=task_manager,
                store=trial_store, store_dir=trial_dir,
            )
            bound = True
        env_token = bind_environment(environment)
        model_token = _MODEL_OVERRIDE.set(ScriptedModel(_script_messages(script)))
        try:
            result = await graph_module.execute_run(
                request, registry, _UnavailableBridge(), trial_store,
                bus=bus, ui_service=ui_service,
            )
        except Exception as exc:  # noqa: BLE001 - a crashing run is a real outcome
            return InvocationResult(
                run_id=run_id, status="failed", events=collected,
                error={"code": type(exc).__name__, "message": str(exc)},
                agent={"id": agent.id},
                model={"provider": settings.provider, "model": settings.model, "candidate": True},
                model_usage=_usage_for_run(run_id),
            )
        finally:
            _MODEL_OVERRIDE.reset(model_token)
            reset_environment(env_token)
            set_ui_service(previous_ui)
            unsubscribe()
            if not bound:
                try:
                    trial_store.close()
                except Exception:  # noqa: BLE001
                    pass
                shutil.rmtree(trial_dir, ignore_errors=True)

        _enrich_tool_args(collected, recorded)
        return InvocationResult(
            run_id=run_id,
            status=result.status,
            output=result.output or "",
            events=collected,
            agent={"id": agent.id},
            model={"provider": settings.provider, "model": settings.model, "candidate": True},
            error=result.error.model_dump() if getattr(result, "error", None) else None,
            model_usage=_usage_for_run(run_id),
        )


__all__ = [
    "CandidateAgentInvoker",
    "HarnessSnapshot",
    "RSL_DENY_GLOBS",
    "RSLTargetError",
    "SnapshotError",
    "assert_landable_target",
    "base_snapshot_from_agent",
    "validate_snapshot",
]
