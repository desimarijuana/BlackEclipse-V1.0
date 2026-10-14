"""The execution dispatcher — maps an Action onto the EXISTING runtime (§11-§15).

There is exactly one execution path. This module never runs an agent loop, a tool
registry, or a workflow engine of its own: it calls `service.run`,
`service.run_skill`, `service.run_workflow`, or `ToolRegistry.execute`. The
automation layer decides WHEN/WHY; the runtime decides WHAT/HOW.

The dispatcher returns a structured `DispatchResult` and NEVER raises for a
runtime failure — the engine records it and applies retry/recovery policy.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..schemas import ModelSettings, RunInput, RunRequest, RunWorkspace
from .model import AutomationDefinition

COMPLETED = "completed"
FAILED = "failed"
WAITING = "waiting"
BLOCKED = "blocked"

APPROVAL_KIND = "automation_action"


@dataclass
class DispatchResult:
    state: str
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    error_class: Optional[str] = None
    cost: Optional[float] = None
    tokens: Optional[int] = None
    approval_id: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)


def _default_model_settings() -> ModelSettings:
    return ModelSettings(
        provider=os.environ.get("HARNESS_JOB_PROVIDER", "ollama"),
        model=os.environ.get("HARNESS_JOB_MODEL", "llama3.1"),
        base_url=os.environ.get("HARNESS_JOB_BASE_URL") or None,
        api_key=os.environ.get("HARNESS_JOB_API_KEY") or None,
    )


def _callback_url() -> str:
    return os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1")


def plan_actions(definition: AutomationDefinition) -> list[str]:
    """A human-readable list of what a run WOULD do (dry run, §35). No side effects."""
    action = definition.action
    steps = [f"trigger: {definition.trigger.type}"]
    if definition.condition is not None:
        steps.append(f"gate condition: {definition.condition.expression}")
    if action.type == "execute_task" and action.skill_id:
        steps.append(f"run skill {action.skill_id}@{action.skill_version or 'latest'}")
    elif action.type in ("execute_task", "run_agent", "create_task", "generate_report"):
        steps.append(f"run agent {action.agent_id or 'eclipse-agent'}: {(action.objective or definition.name)[:120]}")
    elif action.type == "delegate_agent":
        steps.append(f"delegate to {action.agent_id or 'eclipse-agent'}: {(action.objective or definition.name)[:120]}")
    elif action.type == "execute_workflow":
        steps.append(f"run workflow {action.workflow_id}")
    elif action.type == "call_tool":
        steps.append(f"call tool {action.tool_name}")
    elif action.type == "send_notification":
        steps.append(f"send notification {action.notification_template or definition.name}")
    elif action.type in ("run_code", "browser_action", "custom_action"):
        steps.append(f"call tool {action.tool_name}")
    else:
        steps.append(f"action: {action.type}")
    if definition.permissions.requires_approval:
        steps.append("approval required before execution")
    for target in definition.delivery.effective_targets():
        steps.append(f"deliver via {target.adapter} to {target.destination}")
    return steps


def _approval_digest(definition: AutomationDefinition) -> str:
    payload = f"{definition.id}:{definition.version}:{definition.action.type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Dispatcher:
    """Dispatches automation actions through the one runtime."""

    def __init__(
        self,
        service: Any,
        *,
        model_settings_factory: Optional[Callable[[], ModelSettings]] = None,
    ) -> None:
        self._service = service
        self._model_settings = model_settings_factory or _default_model_settings

    def _run_request(self, definition: AutomationDefinition, run_id: str, objective: str) -> RunRequest:
        action = definition.action
        return RunRequest(
            runId=run_id,
            input=RunInput(query=(objective or definition.name)[:4000]),
            agentId=action.agent_id or "eclipse-agent",
            # A bot is one long-lived conversation: its scheduled runs share the
            # SAME private memory bucket as its interactive chat (`bot-<id>`), so
            # what the bot learns running in the background is recalled when the
            # user next talks to it — and never leaks into another bot or a chat.
            conversationId=f"bot-{definition.id}",
            modelSettings=self._model_settings(),
            autonomy=action.autonomy,
            workspace=RunWorkspace(root=action.workspace_root) if action.workspace_root else None,
            parentRunId=action.config.get("parentRunId"),
            callbackBaseUrl=_callback_url(),
            callbackToken=os.environ.get("CRON_SECRET"),
        )

    async def check_approval(self, definition: AutomationDefinition) -> tuple[bool, Optional[str]]:
        """Whether the automation may proceed, or a pending approval id.

        Uses the ONE single-use, digest-bound `ApprovalStore`. A missing store is
        an honest BLOCKED, never a silent allow.
        """
        if not definition.permissions.requires_approval:
            return True, None
        approvals = getattr(self._service, "approvals", None)
        if approvals is None:
            return False, None
        digest = _approval_digest(definition)
        granted = approvals.consume_kind(
            kind=APPROVAL_KIND, request_key=definition.id, digest=digest,
        )
        if granted is not None:
            return True, None
        pending = approvals.request_kind(
            kind=APPROVAL_KIND, request_key=definition.id, digest=digest,
            effect="external_action",
            action_summary=f"Automation {definition.name!r} ({definition.action.type})",
            affected_data=definition.action.objective or definition.action.workflow_id or definition.action.tool_name,
            risk="high" if definition.permissions.denied else "medium",
            grant_scope=definition.permissions.approval_scope,
        )
        return False, (pending or {}).get("id")

    async def dispatch(
        self, definition: AutomationDefinition, *, execution_id: str, run_id: str, dry_run: bool = False,
    ) -> DispatchResult:
        """Run the automation's action through the existing runtime."""
        if dry_run:
            return DispatchResult(state=COMPLETED, output="\n".join(plan_actions(definition)),
                                  detail={"dryRun": True})
        action = definition.action
        try:
            if action.type == "execute_task" and action.skill_id:
                return await self._run_skill(definition, run_id)
            if action.type == "create_task":
                return self._create_task(definition, execution_id)
            if action.type in ("execute_task", "run_agent", "generate_report", "delegate_agent"):
                if action.config.get("tasks"):
                    return await self._run_parallel(definition, run_id)
                return await self._run_agent(definition, run_id, execution_id)
            if action.type == "execute_workflow":
                return await self._run_workflow(definition, run_id)
            if action.type in ("call_tool", "run_code", "browser_action", "custom_action"):
                return await self._call_tool(definition, run_id)
            if action.type == "send_notification":
                return DispatchResult(state=COMPLETED, output="notification queued",
                                      detail={"notificationTemplate": action.notification_template})
            return DispatchResult(state=FAILED, error=f"unsupported action {action.type!r}",
                                  error_class="INVALID_CONFIGURATION")
        except Exception as exc:  # noqa: BLE001 - a runtime failure is recorded, never raised
            return DispatchResult(state=FAILED, run_id=run_id, error=str(exc)[:2000],
                                  error_class=_classify(exc))

    def _tasks(self) -> Any:
        return getattr(self._service, "tasks", None)

    def _create_task(self, definition: AutomationDefinition, execution_id: str) -> DispatchResult:
        """Register work in the EXISTING Task System (a task, not an automation task)."""
        action = definition.action
        manager = self._tasks()
        if manager is None:
            return DispatchResult(state=FAILED, error="the task system is unavailable",
                                  error_class="RUNTIME_UNAVAILABLE")
        try:
            task = manager.create_task({
                "title": (action.task_title or definition.name)[:300],
                "objective": (action.objective or definition.name)[:4000],
                "assigned_agent_id": action.agent_id or "eclipse-agent",
                "metadata": {"automationId": definition.id, "executionId": execution_id},
            })
        except Exception as exc:  # noqa: BLE001
            return DispatchResult(state=FAILED, error=str(exc)[:2000], error_class="TASK_ERROR")
        return DispatchResult(state=COMPLETED, task_id=task.id, output=f"created task {task.id}",
                              detail={"taskId": task.id})

    async def _run_skill(self, definition: AutomationDefinition, run_id: str) -> DispatchResult:
        from ..skills.runtime import SkillExecutionRequest  # noqa: PLC0415

        action = definition.action
        request = SkillExecutionRequest(
            skillId=action.skill_id or "",
            version=action.skill_version,
            input={"objective": action.objective or definition.name},
            runId=run_id,
            executionMode="scheduled",
            modelSettings=self._model_settings(),
            callbackBaseUrl=_callback_url(),
        )
        result = await self._service.run_skill(request)
        status = str(getattr(result, "status", FAILED))
        error = getattr(result, "error", None)
        return DispatchResult(
            state=COMPLETED if status == "completed" else FAILED,
            run_id=getattr(result, "runId", run_id) or run_id,
            output=getattr(result, "output", None),
            error=(error or {}).get("message") if isinstance(error, dict) else None,
            error_class=(error or {}).get("code") if isinstance(error, dict) else None,
        )

    async def _run_agent(self, definition: AutomationDefinition, run_id: str, execution_id: str) -> DispatchResult:
        action = definition.action
        task = self._task_start(definition, execution_id, run_id)
        request = self._run_request(definition, run_id, action.objective or definition.name)
        result = await self._service.run(request)
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        error = dumped.get("error")
        state = COMPLETED if dumped.get("status") == "completed" else FAILED
        self._task_finish(task, state=state, run_id=dumped.get("runId", run_id),
                          error=error.get("message") if isinstance(error, dict) else None,
                          error_class=error.get("code") if isinstance(error, dict) else None)
        return DispatchResult(
            state=state,
            run_id=dumped.get("runId", run_id),
            task_id=getattr(task, "id", None),
            output=dumped.get("output"),
            error=error.get("message") if isinstance(error, dict) else None,
            error_class=error.get("code") if isinstance(error, dict) else None,
            tokens=int(dumped.get("totalTokens") or 0) or None,
        )

    def _task_start(self, definition: AutomationDefinition, execution_id: str, run_id: str) -> Any:
        """Create + start a Task System task for this execution (best-effort)."""
        manager = self._tasks()
        if manager is None:
            return None
        try:
            task = manager.create_task({
                "title": (definition.action.task_title or definition.name)[:300],
                "objective": (definition.action.objective or definition.name)[:4000],
                "assigned_agent_id": definition.action.agent_id or "eclipse-agent",
                "metadata": {"automationId": definition.id, "executionId": execution_id},
            })
            manager.start_task(task.id, run_id=run_id)
            return task
        except Exception:  # noqa: BLE001 - a task ledger failure never fails the run
            return None

    def _task_finish(self, task: Any, *, state: str, run_id: Optional[str], error: Optional[str],
                     error_class: Optional[str]) -> None:
        manager = self._tasks()
        if manager is None or task is None:
            return
        try:
            if state == COMPLETED:
                manager.complete_task(task.id, output_reference=run_id)
            else:
                manager.fail_task(task.id, error=error or "", error_class=error_class)
        except Exception:  # noqa: BLE001 - the run already finished; the ledger is advisory
            pass

    async def _run_parallel(self, definition: AutomationDefinition, run_id: str) -> DispatchResult:
        """Parallel execution through the EXISTING orchestration layer (§15)."""
        orchestration = getattr(self._service, "orchestration", None)
        if orchestration is None:
            return DispatchResult(state=FAILED, error="the parallel execution layer is unavailable",
                                  error_class="RUNTIME_UNAVAILABLE")
        tasks = definition.action.config.get("tasks") or []
        runtime = orchestration.runtime_for(
            model_settings=self._model_settings(),
            callback_base_url=_callback_url(),
            callback_token=os.environ.get("CRON_SECRET"),
            run_id=run_id,
        )
        engine = orchestration.new_engine(runtime)
        from ..orchestration.primitives import parallel_execute  # noqa: PLC0415

        concurrency = definition.limits.max_parallel_tasks or 0
        result = await parallel_execute(
            engine, tasks, concurrency=concurrency, aggregate=True,
            metadata={"automationId": definition.id, "executionId": run_id},
        )
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        ok = str(payload.get("status", "")).upper() in ("COMPLETED", "SUCCESS")
        return DispatchResult(
            state=COMPLETED if ok else FAILED,
            run_id=run_id,
            output=str(payload)[:20_000],
            error=None if ok else "one or more parallel tasks failed",
            error_class=None if ok else "ORCHESTRATION_ERROR",
            detail={"orchestration": payload},
        )

    async def _run_workflow(self, definition: AutomationDefinition, run_id: str) -> DispatchResult:
        action = definition.action
        request = self._run_request(definition, run_id, definition.name)
        request = request.model_copy(update={
            "workflowId": action.workflow_id,
            "input": RunInput(query=(action.objective or definition.name)[:4000], context=action.workflow_input or None),
        })
        result = await self._service.run_workflow(request)
        status = str(result.get("status") if isinstance(result, dict) else getattr(result, "status", FAILED))
        return DispatchResult(
            state=COMPLETED if status in ("completed", "ok") else (
                BLOCKED if status == "disabled" else FAILED
            ),
            run_id=run_id,
            output=str(result)[:20_000] if not isinstance(result, dict) else result.get("output"),
            error=None if status in ("completed", "ok") else str(result.get("note") if isinstance(result, dict) else status),
            error_class=None if status in ("completed", "ok") else "WORKFLOW_NOT_FOUND" if status == "not_found" else "INVALID_CONFIGURATION",
        )

    async def _call_tool(self, definition: AutomationDefinition, run_id: str) -> DispatchResult:
        from ..tools import ToolContext  # noqa: PLC0415

        action = definition.action
        if not action.tool_name:
            return DispatchResult(state=FAILED, error="this action needs a tool name", error_class="INVALID_CONFIGURATION")
        registry = self._service.registry
        ctx = ToolContext(
            run_id=run_id,
            log=lambda *_: None,
            memory_store=self._service.store,
            memory_service=getattr(self._service, "memory", None),
            conversation_id=f"bot-{definition.id}",
            skill_registry=getattr(self._service, "skill_registry", None),
            tool_registry=registry,
            bus=getattr(self._service, "bus", None),
            approvals=getattr(self._service, "approvals", None),
            market_gateway=getattr(self._service, "market_gateway", None),
            market_store=getattr(self._service, "market_store", None),
            portfolio_service=getattr(self._service, "portfolio", None),
            search=getattr(self._service, "search", None),
        )
        result = await registry.execute(action.tool_name, dict(action.tool_args), ctx)
        ok = bool(getattr(result, "ok", False))
        text = getattr(result, "text", "")
        error = getattr(result, "error", None)
        return DispatchResult(
            state=COMPLETED if ok else FAILED,
            run_id=run_id,
            output=text if ok else None,
            error=None if ok else (getattr(error, "message", None) or str(text)),
            error_class=None if ok else (getattr(error, "code", None) or "TOOL_ERROR"),
        )


def _classify(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if "timeout" in text or "timeout" in name.lower():
        return "PROVIDER_TIMEOUT"
    if "permission" in text or "forbidden" in text:
        return "PERMISSION_DENIED"
    if "credential" in text or "api key" in text or "unauthorized" in text:
        return "INVALID_CREDENTIAL"
    return "INTERNAL_ERROR"


__all__ = ["APPROVAL_KIND", "BLOCKED", "COMPLETED", "Dispatcher", "DispatchResult", "FAILED", "WAITING", "plan_actions"]
