"""W12 — multi-agent orchestration, adopted only where measured.

The team / A2A / task machinery already exists (`harness/team`, `harness/a2a`,
`harness/delegation`, `harness/tasks`). What was missing is the EVIDENCE that a
multi-step build delegated across 2-3 specialists is measurably better than one
agent doing the same work. This module is that comparison harness: it runs BOTH
variants on the SAME frozen tasks through the SAME real runtime and returns
measured per-axis deltas plus a deterministic adoption verdict
(ADR-H213: parallel agents are adopted only where a measured benchmark beats
the single-agent baseline).

Design rules (the evaluation system's own honesty rules, applied to a team run):

* the multi-agent trial is the REAL stack — ``TeamService`` → ``A2AService`` →
  ``TaskScheduler`` → the ONE ``execute_run`` graph — over a per-trial isolated
  store (the ``ScriptedAgentInvoker`` pattern), never a re-implementation;
* the model is the only scripted part: each subtask carries its own deterministic
  script (``metadata.team.scripts``) and the model seam answers ONLY while a team
  trial is active, so a team trial can never reach a real provider;
* a task with no decomposition is ``unmeasured``, never a fabricated pass;
* the verdict is computed from measurements only — quality, wall clock and tool
  calls. The scripted tier reports no token/cost usage, so those axes are
  published as unmeasured rather than as a fabricated 0.
"""

from __future__ import annotations

import contextvars
import os
import shutil
import tempfile
from typing import Any, Optional

from .. import graph as graph_module
from ..events import EventBus
from ..persistence import AgentMemoryStore
from ..team.model import TeamDefinition
from .environments import Environment
from .runner import (
    InvocationResult,
    ScriptedModel,
    _UnavailableBridge,
    _build_registry,
    _enrich_tool_args,
    _script_messages,
)

#: The invoker name recorded on a team suite/run (`EvaluationRun.invoker`).
TEAM_INVOKER_NAME = "team"

#: The invoker name recorded on a LIVE team suite/run (real models, no scripts).
LIVE_TEAM_INVOKER_NAME = "team-live"

#: The model-name prefix a team trial assigns to every subtask run. The seam
#: answers a `build_chat_model` call whenever the trial's pool is active; the
#: prefix makes the substitution observable in a trajectory.
TEAM_MODEL_PREFIX = "evaluation-team-"

#: How much wall-clock improvement (fraction) counts as a measurable latency
#: gain before parallelism is adopted for a task class.
ADOPTION_LATENCY_MARGIN = 0.15

#: A team run is terminal once every subtask task is.
_TERMINAL_TASK_STATUS: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

#: The per-trial script pool. ``None`` means "no team trial is active" — the
#: seam then delegates to whatever was installed before it (production, or the
#: evaluation tier's own model override).
_TEAM_MODELS: contextvars.ContextVar[Optional[dict[str, list[dict[str, Any]]]]] = (
    contextvars.ContextVar("evaluation_team_models", default=None)
)


def install_team_model_seam() -> None:
    """Install the team model seam on ``graph.build_chat_model``. Idempotent.

    While a team trial is active (the contextvar is set) EVERY model build
    inside that trial is scripted: the subtask's own script when one is
    registered, else a deterministic "(no script)" answer. A team trial must be
    reproducible and must never reach a real provider — a repair task created by
    the review loop carries no script, and this is what keeps it offline.
    """
    current = graph_module.build_chat_model
    if getattr(current, "_evaluation_team_seam", False):
        return
    original = current

    def _seam(settings: Any) -> Any:
        pool = _TEAM_MODELS.get()
        if pool is None:
            return original(settings)
        key = str(getattr(settings, "model", "") or "")
        script = pool.get(key)
        if script is None:
            script = [{"type": "final",
                       "content": f"(evaluation: no team script for model {key!r})"}]
        # Tool-call ids must be unique ACROSS subtask runs: every child script
        # starts at `call_0_0`, and the argument recorder is keyed by call id.
        return ScriptedModel(_script_messages(script, call_id_prefix=f"{key}:"))

    _seam._evaluation_team_seam = True  # type: ignore[attr-defined]
    _seam._evaluation_team_original = original  # type: ignore[attr-defined]
    graph_module.build_chat_model = _seam


class _TeamHost:
    """The minimal host the A2A / Task / Team layers need, per trial.

    Deliberately lighter than `AgenticService`: the same layers (`install_task_layer`
    → `install_a2a_layer` → `install_team_layer`) over a trial-private store and
    registry, with `run()` dispatching to the ONE `execute_run` graph — exactly
    the isolation pattern the `ScriptedAgentInvoker` already proves. Constructing
    a full `AgenticService` per trial would touch process-wide singletons and the
    developer's real databases, which a benchmark must never do.
    """

    def __init__(self, store: AgentMemoryStore, registry: Any, bus: EventBus) -> None:
        self.store = store
        self.registry = registry
        self.bus = bus
        self.tasks: Any = None
        self.tasks_store: Any = None
        self.task_scheduler: Any = None
        self.a2a: Any = None
        self.team: Any = None

    async def run(self, request: Any) -> Any:
        return await graph_module.execute_run(
            request, self.registry, _UnavailableBridge(), self.store, bus=self.bus,
        )


class TeamAgentInvoker:
    """The multi-agent trial: a 2-3 specialist team over the real team stack.

    A task opts in by declaring ``metadata.team``: ``members`` + ``subtasks`` +
    ``policy`` (a `TeamDefinition` payload) and ``scripts`` (subtask id → the
    deterministic model program that subtask's run executes). A task without one
    is `unmeasured` — the scripted tier cannot invent a decomposition.
    """

    name = TEAM_INVOKER_NAME

    def __init__(self, store: Optional[AgentMemoryStore] = None, *, max_ticks: int = 60) -> None:
        self.store = store
        self.max_ticks = max(1, int(max_ticks))
        install_team_model_seam()

    # -- spec ---------------------------------------------------------------

    @staticmethod
    def team_spec(task: Any) -> Optional[dict[str, Any]]:
        """The task's team decomposition, or None when it declares none."""
        spec = (getattr(task, "metadata", {}) or {}).get("team")
        if not isinstance(spec, dict) or not spec.get("subtasks"):
            return None
        return spec

    def _definition(self, task: Any, spec: dict[str, Any]) -> TeamDefinition:
        keys = ("id", "name", "agentId", "objective", "members", "subtasks", "policy")
        payload = {key: spec[key] for key in keys if key in spec}
        payload.setdefault("id", f"bench-{task.id}")
        payload.setdefault("name", f"Team benchmark: {getattr(task, 'name', task.id)}")
        return TeamDefinition(**payload)

    def _model_name(self, trial_id: str, subtask_id: str) -> str:
        return f"{TEAM_MODEL_PREFIX}{trial_id}-{subtask_id}"

    # -- model wiring (the ONE hook the live tier overrides) ----------------

    def _trial_pool(
        self, trial_id: str, team: TeamDefinition, scripts: dict[str, list[dict[str, Any]]],
    ) -> Optional[dict[str, list[dict[str, Any]]]]:
        """The script pool to bind for this trial, or None (never scripted)."""
        return {
            self._model_name(trial_id, subtask.id): scripts.get(subtask.id, [])
            for subtask in team.subtasks
        }

    def _subtask_settings(self, trial_id: str, subtask_id: str) -> dict[str, Any]:
        """The `metadata.modelSettings` override one subtask run executes under."""
        return {
            "provider": "ollama",
            "model": self._model_name(trial_id, subtask_id),
            "base_url": "http://localhost:11434/v1",
        }

    def _model_meta(self) -> dict[str, Any]:
        """The model provenance recorded on the invocation result."""
        return {"provider": "ollama", "scripted": True, "orchestration": "team"}

    # -- execution ----------------------------------------------------------

    async def _drain(self, host: _TeamHost, run: Any) -> dict[str, int]:
        """Tick the REAL scheduler until every subtask is terminal.

        Ticks are awaited INSIDE the trial's asyncio context, so the bound
        environment and the script pool reach every child run.
        """
        ticks = 0
        for _ in range(self.max_ticks):
            await host.task_scheduler.tick()
            await host.task_scheduler.wait_idle()
            ticks += 1
            statuses = [
                str(row.get("status"))
                for row in host.team.status(run.id).get("subtasks", [])
            ]
            if statuses and all(status in _TERMINAL_TASK_STATUS for status in statuses):
                break
            if not host.tasks.runnable_tasks():
                break
        return {"ticks": ticks}

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        run_id = _safe_team_run_id(task, trial_id)
        spec = self.team_spec(task)
        if spec is None:
            return InvocationResult(
                run_id=run_id, status="unmeasured",
                unmeasured_reason="task declares no team decomposition (metadata.team)",
            )
        scripts = {
            str(key): list(value)
            for key, value in (spec.get("scripts") or {}).items()
            if isinstance(value, list)
        }
        # A team trial is one isolated world: private store, private registry,
        # the real layers. It is torn down here unless the environment owns the
        # store (a `bind`-capable environment grades it after invoke returns).
        trial_dir = tempfile.mkdtemp(prefix="be-eval-team-")
        trial_store = AgentMemoryStore(os.path.join(trial_dir, "agent-memory.db"))
        collected: list[dict[str, Any]] = []
        recorded: list[dict[str, Any]] = []
        bus = EventBus()
        bus.subscribe(lambda event: collected.append(event))
        registry = _build_registry(recorded)
        host = _TeamHost(trial_store, registry, bus)
        from ..a2a.bootstrap import install_a2a_layer  # noqa: PLC0415
        from ..tasks.bootstrap import install_task_layer  # noqa: PLC0415
        from ..team.bootstrap import install_team_layer  # noqa: PLC0415

        install_task_layer(host)
        install_a2a_layer(host)
        install_team_layer(host)

        from .tools import bind_environment, reset_environment  # noqa: PLC0415

        team = self._definition(task, spec)
        pool = self._trial_pool(trial_id, team, scripts)
        env_token = None
        pool_token = None
        environment_owns_store = False
        restore_ui: Any = None
        try:
            from ..ui.bootstrap import get_ui_service, set_ui_service  # noqa: PLC0415

            previous_ui = get_ui_service()
            restore_ui = lambda: set_ui_service(previous_ui)  # noqa: E731
            set_ui_service(None)
            env_token = bind_environment(environment)
            if hasattr(environment, "bind"):
                environment.bind(
                    task_manager=host.tasks, store=trial_store, store_dir=trial_dir,
                )
                environment_owns_store = True
            if pool is not None:
                pool_token = _TEAM_MODELS.set(pool)

            run = await host.team.run(team, root_run_id=run_id, autostart=False)
            # Per-subtask model settings: the run executor resolves
            # `task.metadata.modelSettings` BEFORE the plan's, so each subtask
            # gets its own scripted model (offline) or the operator's real one
            # (live). Merge — never clobber the team metadata.
            for subtask_id, task_id in run.subtask_task_ids.items():
                child = host.tasks.get_task(task_id)
                meta = dict(child.metadata or {})
                meta["modelSettings"] = self._subtask_settings(trial_id, subtask_id)
                host.tasks.update_task(task_id, {"metadata": meta})
            host.tasks.start_plan(run.plan_id)
            await self._drain(host, run)
            settlement = await host.team.finalize(run.id)
            output = host.team.synthesize(run.id)
            team_status = str(settlement.get("status") or "failed")
        except Exception as exc:  # noqa: BLE001 - a crashing team run is a real outcome
            return InvocationResult(
                run_id=run_id, status="failed", events=collected,
                error={"code": type(exc).__name__, "message": str(exc)},
                agent={"id": team.agent_id},
                model=self._model_meta(),
            )
        finally:
            if pool_token is not None:
                _TEAM_MODELS.reset(pool_token)
            if env_token is not None:
                reset_environment(env_token)
            if restore_ui is not None:
                try:
                    restore_ui()
                except Exception:  # noqa: BLE001
                    pass
            if not environment_owns_store:
                try:
                    trial_store.close()
                except Exception:  # noqa: BLE001
                    pass
                shutil.rmtree(trial_dir, ignore_errors=True)

        _enrich_tool_args(collected, recorded)
        status = {"COMPLETED": "completed", "PARTIAL": "partial"}.get(team_status, "failed")
        error = None
        if status != "completed":
            review = (settlement or {}).get("review") or {}
            error = {
                "code": f"TEAM_{team_status}",
                "message": str(review.get("notes") or "") or f"the team run ended {team_status}",
            }
        return InvocationResult(
            run_id=run_id, status=status, output=output, events=collected,
            agent={"id": team.agent_id},
            model=self._model_meta(),
            error=error,
        )


class LiveTeamAgentInvoker(TeamAgentInvoker):
    """The LIVE multi-agent trial: the same real team stack, REAL models.

    Identical orchestration to `TeamAgentInvoker` — the ONE difference is the
    model wiring: no script pool is ever bound, so every subtask run resolves
    the operator's `modelSettings` through the production `build_chat_model`
    path and reaches the configured provider. Deliberately does NOT install the
    scripted seam: a live trial has nothing to script, and if the seam is
    installed elsewhere in the process (an offline trial ran first) an unset
    pool delegates to the original build — still the real model.

    Without model settings every trial is `unmeasured` with the reason stated:
    the live tier publishes unmeasured rather than fabricating a run
    (ADR-H213 — a variant nobody configured decides nothing).
    """

    name = LIVE_TEAM_INVOKER_NAME

    def __init__(
        self, store: Optional[AgentMemoryStore] = None,
        model_settings: Optional[Any] = None, *, max_ticks: int = 60,
    ) -> None:
        # Deliberately NOT `super().__init__`: the scripted seam is the offline
        # tier's; a live invoker installs nothing and pools nothing.
        self.store = store
        self.max_ticks = max(1, int(max_ticks))
        self.model_settings = model_settings

    def _model_name(self, trial_id: str, subtask_id: str) -> str:
        return str(getattr(self.model_settings, "model", "") or "live")

    def _trial_pool(
        self, trial_id: str, team: TeamDefinition, scripts: dict[str, list[dict[str, Any]]],
    ) -> Optional[dict[str, list[dict[str, Any]]]]:
        return None  # a live trial is never scripted

    def _subtask_settings(self, trial_id: str, subtask_id: str) -> dict[str, Any]:
        settings = self.model_settings
        payload: dict[str, Any] = {
            "provider": str(getattr(settings, "provider", "") or ""),
            "model": str(getattr(settings, "model", "") or ""),
        }
        base_url = getattr(settings, "base_url", None)
        api_key = getattr(settings, "api_key", None)
        if base_url:
            payload["base_url"] = str(base_url)
        if api_key:
            payload["api_key"] = str(api_key)
        return payload

    def _model_meta(self) -> dict[str, Any]:
        settings = self.model_settings
        return {
            "provider": str(getattr(settings, "provider", "") or "unknown"),
            "model": str(getattr(settings, "model", "") or ""),
            "scripted": False,
            "orchestration": "team",
        }

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        if self.model_settings is None:
            return InvocationResult(
                run_id=_safe_team_run_id(task, trial_id), status="unmeasured",
                unmeasured_reason=(
                    "the live tier needs model settings (a configured provider); "
                    "none were supplied — published unmeasured, never fabricated"
                ),
            )
        return await super().invoke(task, trial_id, environment)


def _safe_team_run_id(task: Any, trial_id: str) -> str:
    raw = f"evalteam-{getattr(task, 'id', 'task')}-{trial_id}"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)[:120]


# -- measurement ------------------------------------------------------------


def variant_axes(suite: Any, *, wall_ms: Optional[int] = None) -> dict[str, Any]:
    """The measured axes of one variant's suite: quality, wall clock, cost proxies.

    ``taskSuccess`` is the suite's own pass rate; ``toolCalls``/``modelSteps``
    are summed from the REAL trajectories (a deterministic proxy for process
    cost — tokens/cost are NOT reported by the scripted tier, so they are never
    derived here).
    """
    measured = [trial for task in suite.tasks for trial in task.trials if not trial.unmeasured]
    metrics = [trial.trajectory.metrics or {} for trial in measured]
    return {
        "taskSuccess": suite.aggregates.get("task_success"),
        "trials": sum(len(task.trials) for task in suite.tasks),
        "measured": len(measured),
        "wallMs": wall_ms,
        "toolCalls": sum(int(item.get("toolCalls") or 0) for item in metrics),
        "modelSteps": sum(int(item.get("modelSteps") or 0) for item in metrics),
        "toolErrors": sum(int(item.get("toolErrors") or 0) for item in metrics),
        "failures": len(suite.failures),
    }


def measured_usage(suite: Any) -> dict[str, Any]:
    """Token/cost usage summed from the REAL trajectories, or None per axis.

    ``None`` means no measured trial reported the axis — an unreported
    measurement is never estimated. The scripted tier reports 0 (no model ran),
    which stays unpublished rather than becoming a fabricated 0; a LIVE suite's
    trajectories carry the provider-reported usage, so the same axes turn
    measured with no code change at the call site.
    """
    tokens = 0
    cost = 0.0
    tokens_measured = False
    cost_measured = False
    for task in getattr(suite, "tasks", []):
        for trial in getattr(task, "trials", []):
            if getattr(trial, "unmeasured", False):
                continue
            metrics = getattr(getattr(trial, "trajectory", None), "metrics", None) or {}
            token_count = metrics.get("totalTokens")
            if isinstance(token_count, (int, float)) and token_count > 0:
                tokens_measured = True
                tokens += int(token_count)
            spend = metrics.get("cost")
            if isinstance(spend, (int, float)) and spend > 0:
                cost_measured = True
                cost += float(spend)
    return {
        "totalTokens": tokens if tokens_measured else None,
        "cost": round(cost, 6) if cost_measured else None,
    }


def adoption_verdict(
    single: dict[str, Any], team: dict[str, Any], *,
    latency_margin: float = ADOPTION_LATENCY_MARGIN,
) -> dict[str, Any]:
    """Whether the measured comparison authorizes multi-agent adoption.

    The rule (deterministic, no blended score):

    * both variants must be MEASURED — an unmeasured axis decides nothing;
    * the team must NOT regress quality (``taskSuccess``) — a tie is fine;
    * and it must show a real gain on at least one axis: wall-clock improved by
      at least ``latency_margin``, or strictly fewer tool calls.

    Anything else is ``adopted: false`` with the measured numbers named.
    """
    single_success = single.get("taskSuccess")
    team_success = team.get("taskSuccess")
    latency: dict[str, Any] = {
        "singleMs": single.get("wallMs"), "teamMs": team.get("wallMs"), "improvement": None,
    }
    single_wall, team_wall = single.get("wallMs"), team.get("wallMs")
    if isinstance(single_wall, (int, float)) and isinstance(team_wall, (int, float)) and single_wall > 0:
        latency["improvement"] = round((single_wall - team_wall) / single_wall, 4)
    cost = {
        "singleToolCalls": single.get("toolCalls"), "teamToolCalls": team.get("toolCalls"),
        "delta": None,
    }
    if isinstance(single.get("toolCalls"), int) and isinstance(team.get("toolCalls"), int):
        cost["delta"] = int(single["toolCalls"]) - int(team["toolCalls"])
    axes = {"quality": {"single": single_success, "team": team_success}, "latency": latency, "cost": cost}

    if not single.get("measured") or not team.get("measured"):
        return {"adopted": False, "reason": "unmeasured: a variant produced no measured trials", "axes": axes}
    if single_success is None or team_success is None:
        return {"adopted": False, "reason": "unmeasured: task_success was not measured for both variants", "axes": axes}
    if team_success < single_success:
        return {
            "adopted": False,
            "reason": (f"quality regression: team task_success {team_success} < "
                       f"single-agent {single_success}"),
            "axes": axes,
        }
    improvement = latency["improvement"]
    if improvement is not None and improvement >= latency_margin:
        return {
            "adopted": True,
            "reason": (f"quality equal ({team_success}); wall clock improved "
                       f"{improvement * 100:.1f}% (>= {latency_margin * 100:.0f}% margin)"),
            "axes": axes,
        }
    if cost["delta"] is not None and cost["delta"] > 0:
        return {
            "adopted": True,
            "reason": (f"quality equal ({team_success}); tool calls fell by {cost['delta']} "
                       f"({single['toolCalls']} -> {team['toolCalls']})"),
            "axes": axes,
        }
    if improvement is None:
        reason = "no measured gain: wall clock was not comparable"
    else:
        reason = (f"no measured gain: quality equal ({team_success}), wall clock change "
                  f"{improvement * 100:+.1f}% (< {latency_margin * 100:.0f}% margin)")
    if cost["delta"] is not None:
        reason += f", tool-call delta {cost['delta']:+d}"
    return {"adopted": False, "reason": reason, "axes": axes}


__all__ = [
    "ADOPTION_LATENCY_MARGIN",
    "LIVE_TEAM_INVOKER_NAME",
    "TEAM_INVOKER_NAME",
    "TEAM_MODEL_PREFIX",
    "LiveTeamAgentInvoker",
    "TeamAgentInvoker",
    "adoption_verdict",
    "install_team_model_seam",
    "measured_usage",
    "variant_axes",
]
