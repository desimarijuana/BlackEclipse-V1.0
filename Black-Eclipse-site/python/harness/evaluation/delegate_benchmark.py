"""W11 — is the `delegate` fan-out worth its cost?

`team_benchmark.py` compares a specialist TEAM against one agent. This module
does the same job for the fan-out path a user actually triggers (`delegate`), on
FROZEN tasks, through the REAL `execute_run` graph and the REAL `delegate` tool.

Honesty rules:

* the model is a deterministic simulator, not a provider. Each model call takes
  a fixed SIMULATED latency, so the comparison measures the ORCHESTRATION (does
  N independent parts overlap?), not model quality or a vendor's speed;
* both variants are scripted to produce the same facts, so quality is held
  equal by construction — the verdict is about cost, and a coverage regression
  still fails it;
* the report says `simulated: true` and never presents a simulated millisecond
  as a measured provider latency;
* a task whose answer misses a fact is `unmeasured`, never a pass.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import runner as eval_runner

#: Per-model-call latency the simulator charges. Deliberately coarse: the point
#: is ordering, not an SLO.
SIMULATED_CALL_MS = 120

#: A latency gain must clear this fraction before the fan-out is adopted.
ADOPTION_LATENCY_MARGIN = 0.15

_ANSWER_PREFIX = "Combined review:"


@dataclass(frozen=True)
class FanoutTask:
    id: str
    prompt: str
    goals: tuple[str, ...]
    facts: tuple[str, ...]          # one per goal, in order


#: Frozen, offline, and small enough to run in CI.
FROZEN_TASKS: tuple[FanoutTask, ...] = (
    FanoutTask(
        id="fanout_three_notes",
        prompt="Review these three separate notes and combine them into one answer.",
        goals=("Review ACME's note", "Review BETA's note", "Review GAMMA's note"),
        facts=(
            "ACME grew revenue 12%.",
            "BETA cut costs 8%.",
            "GAMMA returned 5%.",
        ),
    ),
    FanoutTask(
        id="fanout_two_sources",
        prompt="Check these two independent sources and give one combined answer.",
        goals=("Check source one", "Check source two"),
        facts=("Source one is current.", "Source two is current."),
    ),
)


@dataclass
class VariantResult:
    variant: str
    wall_ms: int
    model_calls: int
    tool_calls: int
    coverage: float
    output: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant, "wallMs": self.wall_ms,
            "modelCalls": self.model_calls, "toolCalls": self.tool_calls,
            "coverage": round(self.coverage, 4), "error": self.error,
        }


@dataclass
class BenchmarkReport:
    task_id: str
    task: str
    simulated: bool
    single: VariantResult
    fanout: VariantResult
    verdict: dict[str, Any]
    note: str = (
        "Simulated per-call latency through the real runtime. Not a provider "
        "measurement: it answers whether N independent parts overlap."
    )
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id, "task": self.task,
            "simulated": self.simulated,
            "single": self.single.to_dict(), "fanout": self.fanout.to_dict(),
            "verdict": self.verdict, "note": self.note, **self.extra,
        }


class _SimulatedModel:
    """A deterministic, LangChain-shaped model for one variant.

    The fan-out variant: the parent's first call is the `delegate` tool call;
    each child answers from its goal; the parent then combines.
    The single variant: N `bench_step` tool calls, then one answer.
    """

    def __init__(
        self, variant: str, task: FanoutTask, *, delay_s: float,
    ) -> None:
        self.variant = variant
        self.task = task
        self.delay_s = delay_s
        self.bound_tools: Any = None
        self.model_calls = 0
        self._delegated = False
        self._steps = 0

    def bind_tools(self, tools: Any) -> "_SimulatedModel":
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: Any) -> Any:
        from langchain_core.messages import AIMessage  # noqa: PLC0415

        self.model_calls += 1
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        text = _user_text(messages)
        final = _ANSWER_PREFIX + " " + " ".join(self.task.facts)

        if self.variant == "single":
            if self._steps < len(self.task.goals):
                self._steps += 1
                return AIMessage(content="", tool_calls=[{
                    "id": f"bench_{self._steps}", "name": "bench_step", "args": {},
                }])
            return AIMessage(content=final)

        # fan-out: a child run's prompt starts with its own goal.
        for goal, fact in zip(self.task.goals, self.task.facts):
            if text.strip().startswith(goal):
                return AIMessage(content=fact)
        if not self._delegated:
            self._delegated = True
            return AIMessage(content="", tool_calls=[{
                "id": "bench_delegate", "name": "delegate",
                "args": {
                    "strategy": "split",
                    "children": [{"goal": goal} for goal in self.task.goals],
                },
            }])
        return AIMessage(content=final)

    async def astream(self, messages: Any):  # noqa: ANN201
        yield await self.ainvoke(messages)


def _user_text(messages: Any) -> str:
    for message in messages if isinstance(messages, list) else []:
        if getattr(message, "type", "") == "human":
            return str(getattr(message, "content", "") or "")
    return ""


def _bench_registry(recorder: list[dict[str, Any]]) -> ToolRegistry:
    """The real code tools (so `delegate` is the REAL one) + one pacing tool."""
    registry = ToolRegistry()

    async def _step(_args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
        return "ok", {"ok": True}

    registry.register(ToolDefinition(
        name="bench_step",
        description="A deterministic no-op step used only by the benchmark.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_step, permission="read", risk="low", timeout_ms=5_000,
    ))
    from ..code.tools import register_code_tools  # noqa: PLC0415

    register_code_tools(registry)
    return registry


def _coverage(output: str, facts: tuple[str, ...]) -> float:
    if not facts:
        return 0.0
    return sum(1 for fact in facts if fact in (output or "")) / len(facts)


async def _run_variant(
    task: FanoutTask, variant: str, *, delay_s: float,
) -> VariantResult:
    eval_runner.install_model_seam()
    trial_dir = tempfile.mkdtemp(prefix=f"be-delegate-{variant}-")
    store = AgentMemoryStore(os.path.join(trial_dir, "agent-memory.db"))
    registry = _bench_registry([])
    agent = AgentConfig(
        id="evaluation-agent", name="Evaluation Agent",
        systemPrompt="Benchmark agent. Use the available tools exactly as scripted.",
        tools=list(registry.names()), maxSteps=24, maxToolCalls=200,
    )
    request = RunRequest(
        runId=f"bench_{task.id}_{variant}",
        input=RunInput(query=task.prompt),
        agent=agent,
        modelSettings=ModelSettings(
            provider="ollama", model=f"benchmark-{variant}",
            base_url="http://localhost:11434/v1",
        ),
        callbackBaseUrl="http://localhost:3000", liveSurface=False,
    )
    model = _SimulatedModel(variant, task, delay_s=delay_s)
    from ..events import EventBus  # noqa: PLC0415

    bus = EventBus()
    events: list[dict[str, Any]] = []
    bus.subscribe(events.append)
    token = eval_runner._MODEL_OVERRIDE.set(model)  # noqa: SLF001 - the eval seam
    started = time.monotonic()
    try:
        result = await eval_runner.graph_module.execute_run(
            request, registry, eval_runner._UnavailableBridge(), store, bus=bus,
        )
        output = str(getattr(result, "output", "") or "")
        error = getattr(result, "error", None)
        status = getattr(result, "status", "")
    except Exception as exc:  # noqa: BLE001 - a crashed trial is a real outcome
        output, error, status = "", {"message": str(exc)}, "failed"
    finally:
        eval_runner._MODEL_OVERRIDE.reset(token)  # noqa: SLF001
    wall_ms = int((time.monotonic() - started) * 1000)
    tool_calls = sum(1 for event in events if event.get("type") == "tool.requested")
    coverage = _coverage(output, task.facts) if status == "completed" else 0.0
    return VariantResult(
        variant=variant, wall_ms=wall_ms, model_calls=model.model_calls,
        tool_calls=tool_calls, coverage=coverage, output=output,
        error=None if status == "completed" else (
            error.get("message") if isinstance(error, dict) else "run did not complete"
        ),
    )


def run_delegate_benchmark(
    task: FanoutTask, *, delay_ms: int = SIMULATED_CALL_MS,
) -> BenchmarkReport:
    """Run both variants for one frozen task and return the measured verdict."""
    delay_s = max(0, delay_ms) / 1000.0
    single = asyncio.run(_run_variant(task, "single", delay_s=delay_s))
    fanout = asyncio.run(_run_variant(task, "fanout", delay_s=delay_s))
    verdict = adoption_verdict(single, fanout)
    return BenchmarkReport(
        task_id=task.id, task=task.prompt, simulated=True,
        single=single, fanout=fanout, verdict=verdict,
        extra={"delayMs": delay_ms},
    )


def adoption_verdict(single: VariantResult, fanout: VariantResult) -> dict[str, Any]:
    """Adopt only when quality does not regress AND latency really improves."""
    if single.coverage < 1.0 or fanout.coverage < 1.0:
        return {
            "adopted": False, "reason": "unmeasured: at least one variant missed a fact",
            "qualityDelta": round(fanout.coverage - single.coverage, 4),
        }
    if single.wall_ms <= 0:
        return {"adopted": False, "reason": "unmeasured: no comparable wall time"}
    gain = (single.wall_ms - fanout.wall_ms) / single.wall_ms
    return {
        "adopted": gain >= ADOPTION_LATENCY_MARGIN,
        "reason": (
            f"fan-out {'beats' if gain >= ADOPTION_LATENCY_MARGIN else 'does not beat'} "
            f"the single agent by {gain:.1%} (needs {ADOPTION_LATENCY_MARGIN:.0%})"
        ),
        "latencyGain": round(gain, 4),
        "qualityDelta": round(fanout.coverage - single.coverage, 4),
    }


def run_frozen_suite(*, delay_ms: int = SIMULATED_CALL_MS) -> list[BenchmarkReport]:
    return [run_delegate_benchmark(task, delay_ms=delay_ms) for task in FROZEN_TASKS]


__all__ = [
    "ADOPTION_LATENCY_MARGIN",
    "FROZEN_TASKS",
    "FanoutTask",
    "BenchmarkReport",
    "VariantResult",
    "adoption_verdict",
    "run_delegate_benchmark",
    "run_frozen_suite",
]
