"""The evaluation runner: drive the REAL agent runtime and capture the trajectory.

Two invokers are provided:

* :class:`ScriptedAgentInvoker` — drives the real ``harness.graph.execute_run``
  tool loop (real registry, real authorization, real events) with a deterministic
  scripted chat model. This is the offline tier; it is exactly how the repo's own
  tests exercise the graph, so it is the real runtime, not a re-implementation.
* :class:`ServiceAgentInvoker` — drives the production ``AgenticService.run`` with
  a live model. This is the live tier.

Invocation isolation is by ``contextvars`` (the model override and the bound
environment), so independent trials run concurrently in one process.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .. import graph as graph_module
from ..events import EventBus
from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..tools import DataBridge, ToolRegistry
from .config import EvaluationConfig
from .environments import Environment, build_environment
from .graders import GradeContext, build_graders
from .scoring import EvaluationScore, check_thresholds, score_trial
from .stats import TrialStats, aggregate_trials
from .store import EvaluationStore
from .taxonomy import classify_failure
from .trajectory import Trajectory

# The model override seam. Installed once on ``harness.graph.build_chat_model``
# (the existing documented test seam) and read per-task via a contextvar so
# concurrent scripted trials never see each other's model.
_MODEL_OVERRIDE: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "evaluation_model_override", default=None
)


def install_model_seam() -> None:
    current = graph_module.build_chat_model
    if getattr(current, "_evaluation_seam", False):
        return
    original = current

    def _seam(settings: ModelSettings) -> Any:
        override = _MODEL_OVERRIDE.get()
        if override is not None:
            return override
        return original(settings)

    _seam._evaluation_seam = True  # type: ignore[attr-defined]
    _seam._evaluation_original = original  # type: ignore[attr-defined]
    graph_module.build_chat_model = _seam


class ScriptedModel:
    """A LangChain-shaped chat model that replays a deterministic script."""

    def __init__(self, messages: list[Any]) -> None:
        self._messages = list(messages)
        self.bound_tools: Any = None

    def bind_tools(self, tools: Any) -> "ScriptedModel":
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: Any) -> Any:
        from langchain_core.messages import AIMessage  # noqa: PLC0415

        if not self._messages:
            return AIMessage(content="(evaluation script exhausted)")
        return self._messages.pop(0)

    async def astream(self, messages: Any):  # noqa: ANN201
        yield await self.ainvoke(messages)


def _script_messages(script: list[dict[str, Any]]) -> list[Any]:
    from langchain_core.messages import AIMessage  # noqa: PLC0415

    messages: list[Any] = []
    for i, step in enumerate(script):
        if step.get("type") == "tool":
            raw_calls = step.get("calls") or [{"name": step.get("name"), "args": step.get("args", {})}]
            tool_calls = [
                {"id": f"call_{i}_{j}", "name": call["name"], "args": call.get("args", {})}
                for j, call in enumerate(raw_calls)
            ]
            messages.append(AIMessage(content=step.get("content", ""), tool_calls=tool_calls))
        else:
            messages.append(AIMessage(content=str(step.get("content", ""))))
    if not messages or messages[-1].tool_calls:
        messages.append(AIMessage(content="(completed)"))
    return messages


class _UnavailableBridge(DataBridge):
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "UNAVAILABLE", "capability": capability, "reason": "evaluation sandbox"}


@dataclass
class InvocationResult:
    run_id: str
    status: str
    output: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    agent: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    error: Optional[dict[str, Any]] = None
    unmeasured_reason: Optional[str] = None


class AgentInvoker(Protocol):
    name: str

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        ...


def _build_registry(recorder: Optional[list[dict[str, Any]]] = None) -> ToolRegistry:
    registry: ToolRegistry = _RecordingRegistry(recorder) if recorder is not None else ToolRegistry()
    from .tools import register_evaluation_tools  # noqa: PLC0415

    register_evaluation_tools(registry)
    for register in ("register_finance_tools", "register_retrieval_tools"):
        try:
            if register == "register_finance_tools":
                from ..finance_tools import register_finance_tools as fn  # noqa: PLC0415
            else:
                from ..retrieval_tools import register_retrieval_tools as fn  # noqa: PLC0415
            fn(registry)
        except Exception:  # noqa: BLE001 - a missing tool family is not fatal
            continue
    return registry


class _RecordingRegistry(ToolRegistry):
    """A ToolRegistry that records each executed call's NAME and ARGS.

    The runtime's ``tool.requested`` event deliberately omits arguments (privacy),
    so the evaluation harness records them here — at the registry boundary, without
    changing the runtime — and folds them back into the trajectory. This is the
    only way to grade tool ARGUMENTS honestly.
    """

    def __init__(self, recorder: list[dict[str, Any]]) -> None:
        super().__init__()
        self._recorder = recorder

    async def execute(  # type: ignore[override]
        self,
        name: str,
        call_id: str,
        arguments: dict[str, Any],
        ctx: Any,
        *,
        allowed: Any = None,
        timeout_ms: Any = None,
    ) -> Any:
        try:
            self._recorder.append({
                "name": name, "args": dict(arguments or {}), "toolCallId": call_id,
            })
        except Exception:  # noqa: BLE001 - recording must never break a trial
            pass
        return await super().execute(name, call_id, arguments, ctx, allowed=allowed, timeout_ms=timeout_ms)


def _agent_for(task: Any, registry: ToolRegistry) -> AgentConfig:
    forbidden = set(getattr(task, "forbidden_tools", ()) or ())
    tools = [name for name in registry.names() if name not in forbidden]
    script = getattr(task, "agent_script", [])
    steps = min(32, max(8, len(script) + 2))
    limits = getattr(task, "limits", None)
    max_tool_calls = min(200, int(getattr(limits, "max_tool_calls", 200) or 200))
    return AgentConfig(
        id="evaluation-agent",
        name="Evaluation Agent",
        systemPrompt=(
            "You are the Eclipse agent under evaluation. Follow the task exactly and "
            "use the available tools."
        ),
        tools=tools,
        maxSteps=steps,
        maxToolCalls=max_tool_calls,
    )


class ScriptedAgentInvoker:
    """The offline tier: the real graph with a deterministic scripted model."""

    name = "scripted"

    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        install_model_seam()

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        script = getattr(task, "agent_script", [])
        if not script:
            return InvocationResult(
                run_id=f"eval-{trial_id}", status="unmeasured",
                unmeasured_reason="task ships no deterministic script (live tier only)",
            )
        recorded: list[dict[str, Any]] = []
        registry = _build_registry(recorded)
        agent = _agent_for(task, registry)
        run_id = _safe_run_id(task, trial_id)
        request = RunRequest(
            runId=run_id,
            input=RunInput(query=str(getattr(task, "input", {}).get("prompt") or task.name)),
            agent=agent,
            modelSettings=ModelSettings(
                provider="ollama", model=f"evaluation-{trial_id}",
                base_url="http://localhost:11434/v1",
            ),
            callbackBaseUrl="http://localhost:3000",
        )
        bus = EventBus()
        collected: list[dict[str, Any]] = []
        unsubscribe = bus.subscribe(lambda ev: collected.append(ev))
        from .tools import bind_environment, reset_environment  # noqa: PLC0415

        env_token = bind_environment(environment)
        model_token = _MODEL_OVERRIDE.set(ScriptedModel(_script_messages(script)))
        try:
            result = await graph_module.execute_run(request, registry, _UnavailableBridge(), self.store, bus=bus)
        except Exception as exc:  # noqa: BLE001 - a crashing run is a real outcome
            return InvocationResult(
                run_id=run_id, status="failed", events=collected,
                error={"code": type(exc).__name__, "message": str(exc)},
                agent={"id": agent.id}, model={"provider": "ollama", "scripted": True},
            )
        finally:
            _MODEL_OVERRIDE.reset(model_token)
            reset_environment(env_token)
            unsubscribe()
        _enrich_tool_args(collected, recorded)
        return InvocationResult(
            run_id=run_id,
            status=result.status,
            output=result.output or "",
            events=collected,
            agent={"id": agent.id},
            model={"provider": "ollama", "model": f"evaluation-{trial_id}", "scripted": True},
            error=result.error.model_dump() if getattr(result, "error", None) else None,
        )


class ServiceAgentInvoker:
    """The live tier: the production AgenticService with a real model."""

    name = "service"

    def __init__(self, service: Any, model_settings: Optional[ModelSettings] = None,
                 *, agent_id: str = "eclipse-agent", allow_external_side_effects: bool = False) -> None:
        self.service = service
        self.model_settings = model_settings
        self.agent_id = agent_id
        self.allow_external_side_effects = allow_external_side_effects

    async def invoke(self, task: Any, trial_id: str, environment: Environment) -> InvocationResult:
        run_id = _safe_run_id(task, trial_id)
        settings = self.model_settings or ModelSettings(provider="ollama", model="llama3.1",
                                                         base_url="http://localhost:11434/v1")
        request = RunRequest(
            runId=run_id,
            input=RunInput(query=str(getattr(task, "input", {}).get("prompt") or task.name)),
            agentId=self.agent_id,
            modelSettings=settings,
            callbackBaseUrl="http://localhost:3000",
        )
        collected: list[dict[str, Any]] = []
        unsubscribe = self.service.bus.subscribe(
            lambda ev: collected.append(ev) if ev.get("runId") == run_id else None
        )
        try:
            result = await self.service.run(request)
        except Exception as exc:  # noqa: BLE001
            return InvocationResult(run_id=run_id, status="failed", events=collected,
                                    error={"code": type(exc).__name__, "message": str(exc)})
        finally:
            unsubscribe()
        return InvocationResult(
            run_id=run_id, status=result.status, output=result.output or "", events=collected,
            agent={"id": self.agent_id},
            model={"provider": settings.provider, "model": settings.model},
            error=result.error.model_dump() if getattr(result, "error", None) else None,
        )


def _safe_run_id(task: Any, trial_id: str) -> str:
    raw = f"eval-{task.id}-{trial_id}"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)[:120]


def _enrich_tool_args(events: list[dict[str, Any]], recorded: list[dict[str, Any]]) -> None:
    """Fold recorded tool arguments into the trajectory's ``tool.requested`` data.

    Mutates the collected event dicts in place (they are this trial's own copy).
    """
    if not recorded:
        return
    by_id = {r.get("toolCallId"): r.get("args") for r in recorded if r.get("toolCallId")}
    fallback: list[dict[str, Any]] = list(recorded)
    for event in events:
        if event.get("type") != "tool.requested":
            continue
        data = event.setdefault("data", {})
        call_id = data.get("toolCallId")
        if call_id in by_id:
            data["args"] = by_id[call_id]
        elif fallback and fallback[0].get("name") == data.get("name"):
            data["args"] = fallback.pop(0).get("args")
        if "args" not in data:
            data["args"] = {}


@dataclass
class TrialResult:
    task_id: str
    task_version: int
    trial_id: str
    trial_index: int
    passed: bool
    unmeasured: bool
    status: str
    score: EvaluationScore
    trajectory: Trajectory
    env_state: dict[str, Any] = field(default_factory=dict)
    error: Optional[dict[str, Any]] = None
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "taskVersion": self.task_version,
            "trialId": self.trial_id,
            "trialIndex": self.trial_index,
            "passed": self.passed,
            "unmeasured": self.unmeasured,
            "status": self.status,
            "labels": self.labels,
            "score": self.score.to_dict(),
            "trajectory": self.trajectory.to_dict(),
        }


@dataclass
class TaskResult:
    task: Any
    trials: list[TrialResult]
    stats: TrialStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task.id,
            "taskVersion": self.task.version,
            "category": self.task.category,
            "difficulty": self.task.difficulty,
            "stats": self.stats.to_dict(),
            "trials": [t.to_dict() for t in self.trials],
        }


@dataclass
class SuiteResult:
    run_id: str
    dataset_name: str
    dataset_version: str
    dataset_checksum: str
    tasks: list[TaskResult]
    aggregates: dict[str, Optional[float]] = field(default_factory=dict)
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    flaky_tasks: list[str] = field(default_factory=list)
    unmeasured_tasks: list[str] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    tier: int = 0
    thresholds: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.thresholds.get("passed", False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "dataset": {
                "name": self.dataset_name,
                "version": self.dataset_version,
                "checksum": self.dataset_checksum,
            },
            "tier": self.tier,
            "aggregates": self.aggregates,
            "categories": self.categories,
            "flakyTasks": self.flaky_tasks,
            "unmeasuredTasks": self.unmeasured_tasks,
            "failures": self.failures,
            "thresholds": self.thresholds,
            "tasks": [t.to_dict() for t in self.tasks],
        }


class EvaluationRunner:
    """Orchestrates trials: environment → real runtime → trajectory → graders."""

    def __init__(
        self,
        store: AgentMemoryStore,
        *,
        invoker: Optional[AgentInvoker] = None,
        config: Optional[EvaluationConfig] = None,
        eval_store: Optional[EvaluationStore] = None,
    ) -> None:
        self.store = store
        self.eval_store = eval_store or EvaluationStore(store)
        self.config = config or EvaluationConfig.from_env()
        self.invoker: AgentInvoker = invoker or ScriptedAgentInvoker(store)
        self.last_suite: Optional[SuiteResult] = None

    async def run_task(
        self,
        task: Any,
        *,
        trials: Optional[int] = None,
        run_id: Optional[str] = None,
        persist: bool = True,
    ) -> TaskResult:
        count = max(1, int(trials or self.config.trials))
        results: list[TrialResult] = []
        for index in range(count):
            trial_id = f"{run_id or 'local'}-{task.id}-t{index}"
            results.append(await self._run_trial(task, index, trial_id, run_id=run_id, persist=persist))
        outcomes = [r.passed for r in results if not r.unmeasured]
        scores = [r.score.composite or 0.0 for r in results if not r.unmeasured]
        stats = aggregate_trials(outcomes, scores=scores, k=count)
        return TaskResult(task=task, trials=results, stats=stats)

    async def _run_trial(
        self,
        task: Any,
        index: int,
        trial_id: str,
        *,
        run_id: Optional[str],
        persist: bool,
    ) -> TrialResult:
        environment = build_environment(getattr(task, "environment", {}) or {})
        environment.reset(getattr(task, "initial_state", {}) or {})
        state_before = environment.inspect_state()
        invocation = await self.invoker.invoke(task, trial_id, environment)
        state_after = environment.inspect_state()

        trajectory = Trajectory.from_events(
            invocation.events,
            run_id=invocation.run_id,
            task_id=task.id,
            trial_id=trial_id,
            task_version=task.version,
            agent=invocation.agent,
            model=invocation.model,
            final_answer={"output": invocation.output, "status": invocation.status},
            outcome={"status": invocation.status, "error": invocation.error,
                     "unmeasuredReason": invocation.unmeasured_reason},
            state_before=state_before,
            state_after=state_after,
        )

        if invocation.unmeasured_reason:
            score = EvaluationScore(
                task_id=task.id, task_version=task.version, trial_id=trial_id,
                category=task.category, passed=False, dimensions={}, unmeasured=True,
            )
            result = TrialResult(
                task_id=task.id, task_version=task.version, trial_id=trial_id,
                trial_index=index, passed=False, unmeasured=True, status="unmeasured",
                score=score, trajectory=trajectory, env_state=state_after,
            )
        else:
            ctx = GradeContext(
                task=task,
                trajectory=trajectory,
                final_output=invocation.output,
                environment=environment,
                env_state=state_after,
                tool_calls=trajectory.tool_calls(),
                outcome=trajectory.outcome,
                config={},
            )
            grader_results = [grader.grade(ctx) for grader in build_graders(task)]
            score = score_trial(task, trajectory, grader_results)
            result = TrialResult(
                task_id=task.id, task_version=task.version, trial_id=trial_id,
                trial_index=index, passed=score.passed, unmeasured=score.unmeasured,
                status=invocation.status, score=score, trajectory=trajectory,
                env_state=state_after, error=invocation.error,
                labels=score.labels,
            )

        environment.teardown()

        if persist and run_id:
            self._persist_trial(run_id, task, result)
        return result

    def _persist_trial(self, run_id: str, task: Any, result: TrialResult) -> None:
        try:
            self.eval_store.add_trial(
                id=f"{run_id}:{result.trial_id}",
                runId=run_id, taskId=task.id, taskVersion=task.version,
                trialIndex=result.trial_index, passed=result.passed,
                unmeasured=result.unmeasured, status=result.status,
                score=result.score.to_dict(), trajectory=result.trajectory.to_dict(),
                cost=result.score.cost, latencyMs=result.score.latency_ms,
                totalTokens=result.score.total_tokens,
            )
            for dimension, value in result.score.dimensions.items():
                self.eval_store.add_score(
                    runId=run_id, trialId=result.trial_id, taskId=task.id,
                    taskVersion=task.version, category=task.category,
                    dimension=dimension, value=value,
                )
            if not result.passed and not result.unmeasured:
                self.eval_store.record_failure(
                    runId=run_id, trialId=result.trial_id, taskId=task.id,
                    taskVersion=task.version, category=task.category,
                    labels=result.labels,
                    detail={"status": result.status, "graders": result.score.grader_results},
                )
        except Exception:  # noqa: BLE001 - persistence must not abort the evaluation
            pass

    async def run_suite(
        self,
        tasks: list[Any],
        *,
        dataset_name: str = "",
        dataset_version: str = "",
        dataset_checksum: str = "",
        suite: str = "",
        trials: Optional[int] = None,
        tier: int = 0,
        run_id: Optional[str] = None,
        persist: bool = True,
        concurrency: Optional[int] = None,
    ) -> SuiteResult:
        run_id = run_id or f"evalrun-{_now_token()}"
        if persist:
            self.eval_store.create_run(
                id=run_id, suite=suite, datasetName=dataset_name,
                datasetVersion=dataset_version, datasetChecksum=dataset_checksum,
                tier=tier, invoker=getattr(self.invoker, "name", "unknown"),
                model=getattr(self.invoker, "model_settings", None) and self.invoker.model_settings.model,
                provider=getattr(self.invoker, "model_settings", None) and self.invoker.model_settings.provider,
                config={"trials": trials or self.config.trials, "tier": tier},
                status="running", startedAt=None,
            )
        limit = max(1, int(concurrency or self.config.max_concurrency))
        semaphore = asyncio.Semaphore(limit)

        async def _guarded(task: Any) -> TaskResult:
            async with semaphore:
                return await self.run_task(task, trials=trials, run_id=run_id, persist=persist)

        task_results = await asyncio.gather(*[_guarded(task) for task in tasks])
        suite_result = self._assemble(run_id, dataset_name, dataset_version, dataset_checksum,
                                      task_results, tier=tier, trials=trials)
        if persist:
            self._persist_suite(suite_result)
        self.last_suite = suite_result
        return suite_result

    def _assemble(
        self,
        run_id: str,
        dataset_name: str,
        dataset_version: str,
        dataset_checksum: str,
        task_results: list[TaskResult],
        *,
        tier: int,
        trials: Optional[int],
    ) -> SuiteResult:
        aggregates = aggregate_suite(task_results)
        suite_result = SuiteResult(
            run_id=run_id, dataset_name=dataset_name, dataset_version=dataset_version,
            dataset_checksum=dataset_checksum, tasks=task_results, aggregates=aggregates,
            categories=aggregate_categories(task_results),
            flaky_tasks=[t.task.id for t in task_results if t.stats.flakiness == "flaky"],
            unmeasured_tasks=[t.task.id for t in task_results if all(tr.unmeasured for tr in t.trials)],
            failures=[
                {
                    "taskId": tr.task_id, "trialId": tr.trial_id, "labels": tr.labels,
                    "status": tr.status,
                }
                for t in task_results for tr in t.trials if not tr.passed and not tr.unmeasured
            ],
            tier=tier,
        )
        suite_result.thresholds = check_thresholds(
            aggregates, sample_size=sum(len(t.trials) for t in task_results)
        )
        return suite_result

    def _persist_suite(self, suite: SuiteResult) -> None:
        try:
            self.eval_store.update_run(
                suite.run_id, status="completed", finishedAt=_now_iso(),
                trialCount=sum(len(t.trials) for t in suite.tasks),
            )
            for dimension, value in suite.aggregates.items():
                sample = sum(1 for t in suite.tasks for tr in t.trials if not tr.unmeasured
                             and dimension in tr.score.dimensions)
                self.eval_store.add_metric(
                    runId=suite.run_id, scope="overall", dimension=dimension,
                    value=value, sampleSize=sample,
                )
        except Exception:  # noqa: BLE001
            pass


def aggregate_suite(task_results: list[TaskResult]) -> dict[str, Optional[float]]:
    """Per-dimension means over measured trials + the pass rate as task_success."""
    from .scoring import DIMENSIONS  # noqa: PLC0415

    aggregates: dict[str, Optional[float]] = {}
    measured = [tr for t in task_results for tr in t.trials if not tr.unmeasured]
    if measured:
        aggregates["task_success"] = sum(1 for tr in measured if tr.passed) / len(measured)
    else:
        aggregates["task_success"] = None
    for dimension in DIMENSIONS:
        if dimension == "task_success":
            continue
        values = [
            tr.score.dimensions[dimension]
            for tr in measured
            if dimension in tr.score.dimensions and tr.score.dimensions[dimension] is not None
        ]
        aggregates[dimension] = (sum(values) / len(values)) if values else None
    return aggregates


def aggregate_categories(task_results: list[TaskResult]) -> dict[str, dict[str, Any]]:
    by_category: dict[str, list[TrialResult]] = {}
    for task_result in task_results:
        by_category.setdefault(task_result.task.category, []).extend(task_result.trials)
    out: dict[str, dict[str, Any]] = {}
    for category, trials in sorted(by_category.items()):
        measured = [t for t in trials if not t.unmeasured]
        out[category] = {
            "trials": len(trials),
            "measured": len(measured),
            "passed": sum(1 for t in measured if t.passed),
            "unmeasured": len(trials) - len(measured),
            "passRate": (sum(1 for t in measured if t.passed) / len(measured)) if measured else None,
        }
    return out


def _now_iso() -> str:
    from ..persistence import now_iso  # noqa: PLC0415

    return now_iso()


def _now_token() -> str:
    import time  # noqa: PLC0415

    return f"{int(time.time() * 1000)}"


__all__ = [
    "AgentInvoker",
    "EvaluationRunner",
    "InvocationResult",
    "ScriptedAgentInvoker",
    "ScriptedModel",
    "ServiceAgentInvoker",
    "SuiteResult",
    "TaskResult",
    "TrialResult",
    "aggregate_categories",
    "aggregate_suite",
    "install_model_seam",
]
