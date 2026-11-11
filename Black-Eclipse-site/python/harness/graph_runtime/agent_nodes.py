"""Agent nodes.

The graph node is a thin adapter over the EXISTING agent run plane
(`AgenticService.run`): it does not create a second agent loop, model adapter or
tool registry. `bootstrap.py` binds a runner at boot so tests can substitute a
fake and the runtime does not import the whole service here.

Model credentials are held in memory for the run and are never written into the
durable Fabric job payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_DELEGATE_TASKS = 6

def merge_bot_model_override(
    base: dict[str, Any], override: Any,
) -> dict[str, Any]:
    """Apply a saved bot's provider/model pin to a graph run's model settings.

    Mirrors the automation dispatcher's rule: the bot may choose its provider and
    model, while credentials/base URL still resolve from the runtime's configured
    settings unless the pin names a base URL. An absent/malformed pin leaves the
    graph run's settings untouched, so graphs that never reuse a bot are
    unaffected.
    """
    merged = dict(base)
    if not isinstance(override, dict):
        return merged
    model = override.get("model")
    if not isinstance(model, str) or not model.strip():
        return merged
    merged["provider"] = str(override.get("provider") or merged.get("provider") or "ollama")
    merged["model"] = model.strip()
    base_url = override.get("baseUrl") or override.get("base_url")
    if isinstance(base_url, str) and base_url.strip():
        merged["baseUrl"] = base_url.strip()
    return merged


AgentRunner = Callable[[NodeExecContext, dict[str, Any], str], dict[str, Any]]
AgentTaskRunner = Callable[[NodeExecContext, dict[str, Any], str], dict[str, Any]]
PlanRunner = Callable[[NodeExecContext, str], dict[str, Any]]
# `(bot_id) -> bot dict | None`. Bound at boot to the automation store so this
# module never imports the scheduler.
BotResolver = Callable[[str], Optional[dict[str, Any]]]
_runner: Optional[AgentRunner] = None
_plan_runner: Optional[PlanRunner] = None
_bot_resolver: Optional[BotResolver] = None
_task_runner: Optional[AgentTaskRunner] = None


def set_agent_runner(runner: Optional[AgentRunner]) -> None:
    global _runner
    _runner = runner


def set_plan_runner(runner: Optional[PlanRunner]) -> None:
    global _plan_runner
    _plan_runner = runner


def set_bot_resolver(resolver: Optional[BotResolver]) -> None:
    global _bot_resolver
    _bot_resolver = resolver


def set_agent_task_runner(runner: Optional[AgentTaskRunner]) -> None:
    """The n8n-style agent node runner (instructions/tools/memory aware)."""
    global _task_runner
    _task_runner = runner


def _tasks(context: NodeExecContext) -> list[dict[str, str]]:
    raw = context.inputs.get("tasks")
    if raw is None:
        text = str(context.config.get("tasksJson") or "").strip()
        if not text:
            raise ValueError("agent.delegate needs a tasks array or configured tasksJson")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"tasksJson is not valid JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise ValueError("tasks must be a non-empty array")
    limit = max(1, min(int(context.config.get("maxTasks", 4)), MAX_DELEGATE_TASKS))
    if len(raw) > limit:
        raise ValueError(f"agent.delegate is bounded to {limit} task(s) (got {len(raw)})")
    out: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            objective = item.strip()
            title = f"Task {index + 1}"
        elif isinstance(item, dict):
            objective = str(item.get("objective") or item.get("query") or "").strip()
            title = str(item.get("title") or f"Task {index + 1}").strip()
        else:
            raise ValueError(f"task {index + 1} must be a string or an object")
        if not objective:
            raise ValueError(f"task {index + 1} has no objective")
        if len(objective) > 2_000:
            raise ValueError(f"task {index + 1} exceeds 2 000 characters")
        out.append({"title": title[:120], "objective": objective})
    return out


# The agent run plane reports a successful turn as `completed` (see
# `schemas.RunStatus`). `succeeded` is accepted too so substitute runtimes and
# older fakes keep working.
RUN_SUCCESS_STATUSES = frozenset({"completed", "succeeded"})


def agent_run_identity(
    store: Any,
    base_id: str,
    *,
    lineage: Any = None,
) -> tuple[str, Optional[str]]:
    """Pick the agent-plane run id and a resume checkpoint, if one exists.

    A graph node that is re-executed after a process restart must re-enter the
    SAME agent run when that run has a durable checkpoint. Without a checkpoint
    (or after a terminal run) it gets a fresh id, so the agent plane never
    rejects a retry as a duplicate.
    """
    prior = store.get_run(base_id) if store is not None else None
    if prior is not None:
        status = str(prior.get("status") or "")
        if status not in ("completed", "failed", "cancelled"):
            if lineage is None:
                from ..run_lineage import RunLineage  # noqa: PLC0415

                lineage = RunLineage(store)
            checkpoint = lineage.latest_checkpoint(base_id)
            if checkpoint:
                return base_id, str(checkpoint["id"])
        return f"{base_id}:{uuid.uuid4().hex[:6]}", None
    return base_id, None


def agent_result_payload(result: Any) -> dict[str, Any]:
    """Project an agent-plane RunResult onto the node's declared outputs.

    This is the ONE place the run-status vocabulary is interpreted. It used to
    live inline in `bootstrap._agent_runner` and accepted only `succeeded`,
    which turned every real (completed) agent turn into a node failure.
    """
    status = getattr(result.status, "value", str(result.status))
    if status not in RUN_SUCCESS_STATUSES:
        error = getattr(result, "error", None)
        message = getattr(error, "message", None) or status
        raise ValueError(f"agent run {status}: {message}")
    finding = {
        "text": getattr(result, "output", None) or "",
        "runId": getattr(result, "runId", None),
        "status": status,
        "research": getattr(result, "research", None),
        "tokens": getattr(result, "totalTokens", None),
        "toolCalls": getattr(result, "toolCalls", None),
    }
    return {"finding": finding, "evidence": getattr(result, "research", None) or {}}


def exec_research_agent(context: NodeExecContext) -> dict[str, Any]:
    objective = str(
        context.inputs.get("query") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.research needs a query input or a configured objective")
    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    config = {
        "agent": str(context.config.get("agent") or "eclipse-agent"),
        "agentVersion": int(context.config.get("agentVersion", 0)),
        "objective": objective,
        "maxSteps": int(context.config.get("maxSteps", 8)),
        "instructions": str(context.config.get("instructions") or ""),
        "tools": _tools_list(context.config.get("tools")),
    }
    result = _runner(context, config, objective)
    if not isinstance(result, dict):
        raise ValueError("the agent runner returned no structured result")
    return result


def exec_plan_agent(context: NodeExecContext) -> dict[str, Any]:
    objective = str(
        context.inputs.get("objective") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.plan needs an objective input or a configured objective")
    if _plan_runner is None:
        raise ValueError("the step planner is not configured in this graph runtime")
    plan = _plan_runner(context, objective)
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        raise ValueError("the step planner returned no structured plan")
    context.emit(f"planned {len(plan['steps'])} step(s)")
    return {
        "plan": plan,
        "steps": plan["steps"],
        "summary": {
            "stepCount": len(plan["steps"]),
            "rationale": plan.get("rationale") or "",
        },
    }


def exec_delegate_agent(context: NodeExecContext) -> dict[str, Any]:
    tasks = _tasks(context)
    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    agent = str(context.config.get("agent") or "eclipse-agent")
    max_steps = int(context.config.get("maxSteps", 8))
    findings: list[dict[str, Any]] = []
    failed = 0
    for index, task in enumerate(tasks):
        context.emit(f"delegating {index + 1}/{len(tasks)}: {task['title']}")
        try:
            result = _runner(context, {
                "agent": agent,
                "agentVersion": int(context.config.get("agentVersion", 0)),
                "objective": task["objective"],
                "maxSteps": max_steps,
                "instructions": str(context.config.get("instructions") or ""),
                "tools": _tools_list(context.config.get("tools")),
            }, task["objective"])
            if not isinstance(result, dict):
                raise ValueError("the agent runner returned no structured result")
            findings.append({
                "title": task["title"],
                "objective": task["objective"],
                "status": "succeeded",
                "finding": result.get("finding"),
                "evidence": result.get("evidence"),
            })
        except Exception as exc:  # noqa: BLE001 - one failed part is a partial answer
            failed += 1
            findings.append({
                "title": task["title"],
                "objective": task["objective"],
                "status": "failed",
                "error": str(exc),
            })
    succeeded = len(findings) - failed
    status = "OK" if failed == 0 else ("PARTIAL" if succeeded else "FAILED")
    context.emit(f"delegated {succeeded}/{len(findings)} task(s), status {status}")
    return {
        "findings": findings,
        "summary": {
            "status": status,
            "total": len(findings),
            "succeeded": succeeded,
            "failed": failed,
        },
    }


def exec_bot_agent(context: NodeExecContext) -> dict[str, Any]:
    """Run a SAVED bot as one bounded turn.

    The bot is resolved from the automation store (bound at boot) and its own
    agent preset is used, so a bot answers as itself. It never registers a
    trigger and never runs the bot's schedule: the graph is the caller.
    """
    bot_id = str(context.config.get("botId") or "").strip()
    if not bot_id:
        raise ValueError(
            "agent.bot needs a bot: pick one in the inspector (Bot) "
            "or set botId in the node config"
        )
    if _bot_resolver is None:
        raise ValueError("the bot store is not configured in this graph runtime")
    bot = _bot_resolver(bot_id)
    if not isinstance(bot, dict):
        raise ValueError(
            f"bot {bot_id!r} was not found; pick another one (it may have been deleted)"
        )
    if not bool(bot.get("isBot", True)):
        raise ValueError(f"automation {bot_id!r} is not a bot")
    if str(bot.get("kind") or "agent") == "workflow":
        # Nesting a workflow run inside a graph run is a second execution plane.
        raise ValueError(
            f"bot {bot_id!r} runs a workflow; use flow.subworkflow instead of "
            "agent.bot (a graph never nests a scheduler run)"
        )

    objective = str(
        context.inputs.get("query")
        or context.config.get("objective")
        or bot.get("objective")
        or bot.get("name")
        or ""
    ).strip()
    if not objective:
        raise ValueError("agent.bot needs an objective: wire a query or fill Objective")
    extra = context.inputs.get("context")
    if isinstance(extra, dict) and extra:
        # Bounded, labelled data — never instructions spliced into the objective.
        objective = (
            f"{objective}\n\nContext (JSON):\n"
            f"{json.dumps(extra, ensure_ascii=False)[:2_000]}"
        )

    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    agent = str(bot.get("agentId") or "eclipse-agent")
    max_steps = max(1, min(int(context.config.get("maxSteps", 8)), 32))
    context.emit(f"running bot {bot.get('name') or bot_id} as {agent}")
    result = _runner(context, {
        "agent": agent,
        "objective": objective,
        "maxSteps": max_steps,
        "instructions": str(context.config.get("instructions") or ""),
        "tools": _tools_list(context.config.get("tools")),
        # The bot's own provider/model pin travels with the call so an
        # `agent.bot` node behaves like that bot's scheduled runs. The runner
        # merges it onto the graph run's resolved credentials.
        "modelSettings": bot.get("modelSettings"),
    }, objective)
    if not isinstance(result, dict):
        raise ValueError("the agent runner returned no structured result")
    return result


def _bounded_json(value: Any, limit: int = 4_000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:limit]


def _tools_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        parts = str(raw or "").split(",")
    out: list[str] = []
    for part in parts:
        value = str(part).strip()
        if value and value not in out:
            out.append(value)
    return out[:64]


def _json_from_text(text: str) -> Any:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        from ..vision.analyze import extract_json  # noqa: PLC0415

        return extract_json(cleaned)


def exec_agent_task(context: NodeExecContext) -> dict[str, Any]:
    task = str(
        context.inputs.get("task") or context.config.get("task") or ""
    ).strip()
    if not task:
        raise ValueError("agent.task needs a task (wire one or fill Task)")
    parts = [task]
    if bool(context.config.get("includeInput", True)) and context.inputs.get("input") is not None:
        parts.append(f"Input (JSON):\n{_bounded_json(context.inputs['input'])}")
    if context.inputs.get("context") is not None:
        parts.append(f"Context (JSON):\n{_bounded_json(context.inputs['context'])}")
    objective = "\n\n".join(parts)

    memory_mode = str(context.config.get("memoryMode") or "read").strip().lower()
    if memory_mode not in ("none", "read", "write", "read_write"):
        raise ValueError(f"unknown memoryMode {memory_mode!r}")
    if context.test_run and memory_mode in ("write", "read_write"):
        raise ValueError(
            "agent.task memory writes are refused in a test run; use an operator run"
        )
    if _task_runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    config = {
        "agent": str(context.config.get("agent") or "eclipse-agent"),
        "agentVersion": int(context.config.get("agentVersion", 0)),
        "maxSteps": int(context.config.get("maxSteps", 8)),
        "instructions": str(context.config.get("instructions") or ""),
        "tools": _tools_list(context.config.get("tools")),
        "memoryMode": memory_mode,
        "memoryScope": str(context.config.get("memoryScope") or "workflow"),
        "memoryLimit": int(context.config.get("memoryLimit", 8)),
        "memoryImportance": float(context.config.get("memoryImportance", 0.5)),
    }
    result = _task_runner(context, config, objective)
    if not isinstance(result, dict):
        raise ValueError("the agent runner returned no structured result")
    finding = result.get("finding") if isinstance(result.get("finding"), dict) else {}
    output = str(finding.get("text") or "")
    output_mode = str(context.config.get("outputMode") or "text").strip().lower()
    if output_mode not in ("text", "json"):
        raise ValueError(f"unknown outputMode {output_mode!r}")

    data: Any = None
    valid = bool(output.strip())
    issues: list[str] = []
    if output_mode == "json":
        parsed = _json_from_text(output)
        if not isinstance(parsed, dict):
            valid = False
            issues.append("the agent did not return a JSON object")
        else:
            data = parsed
            schema_text = str(context.config.get("outputSchemaJson") or "").strip()
            if schema_text:
                try:
                    schema = json.loads(schema_text)
                except json.JSONDecodeError as exc:
                    valid = False
                    issues.append(f"output schema is not valid JSON: {exc}")
                else:
                    from .agent_structured import validate_extraction  # noqa: PLC0415

                    valid, schema_issues = validate_extraction(data, schema)
                    issues.extend(schema_issues)
                    if not valid:
                        data = None
    context.emit(
        f"agent {config['agent']} · {'json' if output_mode == 'json' else 'text'}"
        + ("" if valid else " · invalid output")
    )
    return {
        "output": output,
        "data": data,
        "finding": finding,
        "run": {
            "runId": finding.get("runId"),
            "status": finding.get("status"),
            "tokens": finding.get("tokens"),
            "toolCalls": finding.get("toolCalls"),
        },
        "valid": valid,
        "issues": issues,
    }


def build_agent_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="agent.research", version="1.0.0", label="Research agent",
            category="agent",
            # Optional: the configured `objective` is a valid alternative, and
            # `exec_research_agent` prefers the input when one is wired.
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="evidence", name="Evidence", type=PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("agentVersion", "integer", 0, minimum=0, maximum=1_000_000),
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
                ConfigField("instructions", "string", "", max_length=8_000),
                ConfigField("tools", "string", "", max_length=2_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_research_agent,
            metadata={
                "docs": (
                    "Runs the EXISTING agent runtime for one bounded turn. Requires "
                    "an operator run with network + agent.run grants; the front door "
                    "resolves model settings into memory, never into the durable job."
                ),
            },
        ),
        NodeDef(
            type="agent.plan", version="1.0.0", label="Plan steps",
            category="agent",
            inputs=(PortDef(id="objective", name="Objective", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="plan", name="Plan", type=PortType.OBJECT),
                PortDef(id="steps", name="Steps", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("objective", "string", "", max_length=2_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=300_000,
            executor=exec_plan_agent,
            metadata={
                "docs": (
                    "One bounded model call that returns 1-8 independent steps. It does "
                    "not execute them; wire the steps into agent.delegate or the graph."
                ),
            },
        ),
        NodeDef(
            type="agent.delegate", version="1.0.0", label="Delegate tasks",
            category="agent",
            inputs=(PortDef(id="tasks", name="Tasks", type=PortType.ARRAY, optional=True),),
            outputs=(
                PortDef(id="findings", name="Findings", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("tasksJson", "string", "", max_length=20_000),
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("agentVersion", "integer", 0, minimum=0, maximum=1_000_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
                ConfigField("maxTasks", "integer", 4, minimum=1, maximum=MAX_DELEGATE_TASKS),
                ConfigField("instructions", "string", "", max_length=8_000),
                ConfigField("tools", "string", "", max_length=2_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_delegate_agent,
            metadata={
                "docs": (
                    "Runs each task as one bounded turn on the existing agent plane. "
                    "A failed part is reported as failed; partial answers are explicit."
                ),
            },
        ),
        NodeDef(
            type="agent.bot", version="1.0.0", label="Run bot",
            category="agent",
            inputs=(
                PortDef(id="query", name="Query", type=PortType.STRING, optional=True),
                PortDef(id="context", name="Context", type=PortType.OBJECT, optional=True),
            ),
            outputs=(
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="evidence", name="Evidence", type=PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("botId", "string", "", max_length=120),
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
                ConfigField("instructions", "string", "", max_length=8_000),
                ConfigField("tools", "string", "", max_length=2_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_bot_agent,
            metadata={
                "docs": (
                    "Resolves a saved bot from the automation store and runs ONE "
                    "bounded turn with the bot's own agent preset. No trigger is "
                    "registered and the bot's schedule is never run. A workflow "
                    "bot is refused (use flow.subworkflow); the bot's per-run "
                    "model override is ignored in favour of the graph run's."
                ),
            },
        ),
        NodeDef(
            type="agent.task", version="1.0.0", label="Agent",
            category="agent",
            inputs=(
                PortDef(id="input", name="Input", type=PortType.ANY, optional=True),
                PortDef(id="context", name="Context", type=PortType.OBJECT, optional=True),
                PortDef(id="task", name="Task", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="output", name="Output", type=PortType.STRING),
                PortDef(id="data", name="Data", type=PortType.OBJECT, nullable=True),
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="run", name="Run", type=PortType.OBJECT),
                PortDef(id="valid", name="Valid", type=PortType.BOOLEAN),
                PortDef(id="issues", name="Issues", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("agentVersion", "integer", 0, minimum=0, maximum=1_000_000),
                ConfigField("task", "string", "", max_length=4_000),
                ConfigField("instructions", "string", "", max_length=8_000),
                ConfigField("tools", "string", "", max_length=2_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
                ConfigField("memoryMode", "enum", "read", enum=("none", "read", "write", "read_write")),
                ConfigField("memoryScope", "enum", "workflow", enum=("general", "workflow", "run")),
                ConfigField("memoryLimit", "integer", 8, minimum=1, maximum=50),
                ConfigField("memoryImportance", "number", 0.5, minimum=0.0, maximum=1.0),
                ConfigField("outputMode", "enum", "text", enum=("text", "json")),
                ConfigField("outputSchemaJson", "string", "", max_length=20_000),
                ConfigField("includeInput", "boolean", True),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_agent_task,
            metadata={
                "docs": (
                    "The n8n-style Agent node: instructions + task + agent preset + "
                    "tool allowlist + memory mode + a declared output shape. It runs "
                    "ONE bounded turn on the existing agent plane; a JSON output is "
                    "checked against the schema and reports valid=false on mismatch. "
                    "Memory writes are refused in a test run."
                ),
            },
        ),
    ]


__all__ = [
    "RUN_SUCCESS_STATUSES",
    "agent_result_payload",
    "agent_run_identity",
    "build_agent_nodes",
    "exec_agent_task",
    "exec_bot_agent",
    "set_agent_runner",
    "set_agent_task_runner",
    "set_bot_resolver",
    "set_plan_runner",
    "exec_research_agent",
    "exec_plan_agent",
    "exec_delegate_agent",
]
