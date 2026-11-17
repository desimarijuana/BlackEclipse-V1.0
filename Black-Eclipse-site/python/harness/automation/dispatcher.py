"""The execution dispatcher — maps an Action onto the EXISTING runtime (§11-§15).

There is exactly one execution path. This module never runs an agent loop, a tool
registry, or a workflow engine of its own: it calls `service.run`,
`service.run_skill`, `service.run_workflow`, or `ToolRegistry.execute`. The
automation layer decides WHEN/WHY; the runtime decides WHAT/HOW.

The dispatcher returns a structured `DispatchResult` and NEVER raises for a
runtime failure — the engine records it and applies retry/recovery policy.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

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
    # The front door sets HARNESS_CALLBACK_URL when it can. Fall back to the
    # same local port the graph runtime uses, never a bare port 80.
    return (
        os.environ.get("HARNESS_CALLBACK_URL")
        or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
    )


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
    elif action.type == "run_team":
        steps.append(
            "run team preset "
            f"{action.config.get('presetId') or 'institution'}: "
            f"{(action.objective or definition.name)[:120]}"
        )
    elif action.type == "delegate_agent":
        steps.append(f"delegate to {action.agent_id or 'eclipse-agent'}: {(action.objective or definition.name)[:120]}")
    elif action.type == "execute_workflow":
        steps.append(f"run workflow {action.workflow_id}")
    elif action.type == "run_strategy":
        config = action.config or {}
        steps.append(
            "decide on the last closed bar for "
            f"{config.get('strategyId') or 'a strategy'}@"
            f"{config.get('strategyVersion') or '?'} "
            f"({config.get('mode') or 'shadow'})"
        )
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

    def _model_settings_for(self, definition: AutomationDefinition) -> ModelSettings:
        """The model for this automation's runs.

        A bot may pin its OWN provider/model (stored on `action.config.modelSettings`
        by the Bots UI) so a scheduled run uses the model the operator chose for it,
        rather than the runtime-wide default. Credentials are never stored here: the
        provider key still resolves from the runtime's configured default, so a
        pinned model on a DIFFERENT provider without a key fails honestly
        (`PROVIDER_NOT_CONFIGURED`) rather than silently.
        """
        base = self._model_settings()
        override = definition.action.config.get("modelSettings")
        if isinstance(override, dict) and override.get("model"):
            return ModelSettings(
                provider=str(override.get("provider") or base.provider),
                model=str(override["model"]),
                base_url=override.get("baseUrl") or base.base_url,
                api_key=base.api_key,
            )
        return base

    def _run_request(self, definition: AutomationDefinition, run_id: str, objective: str) -> RunRequest:
        action = definition.action
        query = (objective or definition.name)[:4000]
        # Visual teaching: reference images reach a scheduled agent run as
        # guidance, exactly as they do in the bot's chat.
        config = action.config if isinstance(action.config, dict) else {}
        visuals = config.get("visuals")
        images: list[dict[str, Any]] = []
        if isinstance(visuals, list) and visuals:
            from . import trading_policy  # noqa: PLC0415

            teaching = trading_policy.visual_teaching_prompt(visuals)
            if teaching:
                query = f"{query}\n\n{teaching}"
            for visual in visuals:
                if not isinstance(visual, dict):
                    continue
                data_url = visual.get("dataUrl")
                if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
                    continue
                images.append({
                    "dataUrl": data_url,
                    "caption": str(visual.get("caption") or "")[:280],
                    "mime": str(visual.get("mime") or "image/png")[:40],
                })
        return RunRequest(
            runId=run_id,
            input=RunInput(query=query[:8000], images=images or None),
            agentId=action.agent_id or "eclipse-agent",
            # A bot is one long-lived conversation: its scheduled runs share the
            # SAME private memory bucket as its interactive chat (`bot-<id>`), so
            # what the bot learns running in the background is recalled when the
            # user next talks to it — and never leaks into another bot or a chat.
            conversationId=f"bot-{definition.id}",
            modelSettings=self._model_settings_for(definition),
            autonomy=action.autonomy,
            # Same read-only sandbox an interactive chat turn gets, so a bot can
            # COMPUTE a derived figure (`analysis_run`) instead of only narrating.
            # Still gated by `analysis.execute`; this grants no new capability.
            analysisEnabled=True,
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
            if action.type == "run_team":
                return await self._run_team(definition)
            if action.type in ("execute_task", "run_agent", "generate_report", "delegate_agent"):
                if action.config.get("tasks"):
                    return await self._run_parallel(definition, run_id)
                return await self._run_agent(definition, run_id, execution_id)
            if action.type == "execute_workflow":
                return await self._run_workflow(definition, run_id)
            if action.type == "run_strategy":
                # Deferred import: the runner returns a DispatchResult, which lives
                # in this module. A module-level import would be circular.
                from .trading_runner import run_strategy  # noqa: PLC0415

                return await run_strategy(
                    self._service, definition, run_id=run_id,
                    execution_id=execution_id,
                )
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
            modelSettings=self._model_settings_for(definition),
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
        agent_run_id = dumped.get("runId") or run_id
        self._task_finish(task, state=state, run_id=agent_run_id,
                          error=error.get("message") if isinstance(error, dict) else None,
                          error_class=error.get("code") if isinstance(error, dict) else None)
        # A bot that previewed an order leaves a single-use approval behind. The
        # engine has to be able to report THAT order (and its window) instead of
        # a generic success, so collect the rows this run asked for.
        pending = self._pending_trade_approvals(agent_run_id)
        return DispatchResult(
            state=state,
            run_id=agent_run_id,
            task_id=getattr(task, "id", None),
            output=dumped.get("output"),
            error=error.get("message") if isinstance(error, dict) else None,
            error_class=error.get("code") if isinstance(error, dict) else None,
            tokens=int(dumped.get("totalTokens") or 0) or None,
            detail={"pendingApprovals": pending} if pending else {},
        )

    def _pending_trade_approvals(self, run_id: str) -> list[dict[str, Any]]:
        """Pending trade approvals requested BY this run. Best-effort, never raises.

        An unavailable broker layer is not an error: a run that never touched a
        broker simply has nothing to report.
        """
        if not run_id:
            return []
        brokers = getattr(self._service, "brokers", None)
        if brokers is None:
            return []
        try:
            rows = brokers.list_approvals(status="pending", limit=50)
        except Exception:  # noqa: BLE001 - reporting must never fail the run
            return []
        wanted = str(run_id)
        return [
            {
                "approvalId": row.get("id"),
                "summary": row.get("actionSummary"),
                "expiresAt": row.get("expiresAt"),
                "risk": row.get("risk"),
            }
            for row in rows
            if str(row.get("requestedByRunId") or "") == wanted
        ]

    async def _run_team(self, definition: AutomationDefinition) -> DispatchResult:
        """Start the Institution committee and wait for its terminal decision.

        A scheduled institution run is one automation execution: it opens a team
        run, waits (bounded by the automation's own runtime budget) for the task
        graph to finish, then finalises and returns the deterministic synthesis.
        It never places an order.
        """
        action = definition.action
        preset_id = str(action.config.get("presetId") or "institution")
        if preset_id != "institution":
            return DispatchResult(
                state=FAILED, error=f"unknown team preset {preset_id!r}",
                error_class="INVALID_CONFIGURATION",
            )
        team_service = getattr(self._service, "team", None)
        if team_service is None:
            try:
                from ..team.bootstrap import install_team_layer  # noqa: PLC0415

                install_team_layer(self._service)
            except Exception:  # noqa: BLE001 - reported honestly below
                team_service = None
            team_service = getattr(self._service, "team", None)
        if team_service is None:
            return DispatchResult(
                state=FAILED, error="the team runtime is unavailable",
                error_class="RUNTIME_UNAVAILABLE",
            )
        try:
            from ..institution.preset import build_team  # noqa: PLC0415

            raw_constraints = action.config.get("constraints")
            constraints = (
                [str(c) for c in raw_constraints if str(c).strip()]
                if isinstance(raw_constraints, list) else []
            )
            team = build_team(
                action.objective or definition.name,
                universe=str(action.config.get("universe") or ""),
                horizon=str(action.config.get("horizon") or ""),
                constraints=constraints,
            )
            settings = self._model_settings_for(definition)
            run = await team_service.run(
                team, model_settings=settings.model_dump(by_alias=True),
            )
            timeout_s = max(5, min(int(definition.execution.max_runtime_s), 86_400))
            try:
                await team_service.wait(run.id, timeout_s=timeout_s)
            except Exception:  # noqa: BLE001 - a timeout is finalised below
                pass
            final = await team_service.finalize(run.id)
            status = str(final.get("status") or "")
            output = team_service.synthesize(run.id)
            return DispatchResult(
                state=COMPLETED if status in ("COMPLETED", "PARTIAL") else FAILED,
                run_id=run.root_run_id,
                output=output,
                error=None if status in ("COMPLETED", "PARTIAL") else (
                    f"team finished with status {status or 'unknown'}"
                ),
                error_class=None if status in ("COMPLETED", "PARTIAL") else "TEAM_INCOMPLETE",
                detail={
                    "teamRunId": run.id,
                    "presetId": preset_id,
                    "teamStatus": status,
                    "reviewOutcome": final.get("reviewOutcome"),
                    "conflicts": len(final.get("conflicts") or []),
                },
            )
        except Exception as exc:  # noqa: BLE001 - a dispatched failure is recorded
            return DispatchResult(
                state=FAILED, error=str(exc)[:2000], error_class="TEAM_ERROR",
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
            model_settings=self._model_settings_for(definition),
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
        graph_workflow_id = str(action.config.get("graphWorkflowId") or "").strip()
        if graph_workflow_id:
            return await self._run_graph_via_front_door(definition, run_id, graph_workflow_id)

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

    async def _run_graph_via_front_door(
        self,
        definition: AutomationDefinition,
        run_id: str,
        graph_workflow_id: str,
    ) -> DispatchResult:
        """Run a Graph Studio workflow through the front door.

        Graph Studio workflows live in JDDS (Prisma), which the Python runtime
        cannot read. The front door owns that run surface, so a workflow bot's
        scheduled action starts the run there and polls the graph run record.
        This uses the same TEST-RUN envelope as a normal scheduled graph run.
        """
        action = definition.action
        base = _callback_url().rstrip("/")
        headers = {"Content-Type": "application/json"}
        token = os.environ.get("CRON_SECRET")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = {
            "runInput": {
                "message": (action.objective or definition.name)[:4000],
                "botId": definition.id,
                "context": action.workflow_input or {},
            }
        }
        timeout_s = max(30, int(definition.execution.max_runtime_s or 900)) + 30
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{base}/api/workflows/{graph_workflow_id}/runs",
                    json=payload,
                    headers=headers,
                )
                data = res.json() if res.content else {}
                if res.status_code >= 400:
                    detail = data.get("detail") if isinstance(data, dict) else None
                    message = (
                        detail.get("message") if isinstance(detail, dict)
                        else detail or (data.get("error") if isinstance(data, dict) else None)
                        or f"HTTP {res.status_code}"
                    )
                    return DispatchResult(
                        state=FAILED, run_id=run_id, error=str(message),
                        error_class="GRAPH_RUN_REJECTED",
                    )
                graph_run = (data.get("run") if isinstance(data, dict) else None) or {}
                graph_run_id = graph_run.get("id")
                if not graph_run_id:
                    return DispatchResult(
                        state=FAILED, run_id=run_id,
                        error="the front door did not return a graph run id",
                        error_class="GRAPH_BRIDGE_ERROR",
                    )

                deadline = time.monotonic() + timeout_s
                while time.monotonic() < deadline:
                    await asyncio.sleep(1.0)
                    poll = await client.get(f"{base}/api/graph-runs/{graph_run_id}", headers=headers)
                    record = ((poll.json() if poll.content else {}) or {}).get("run") or {}
                    status = record.get("status")
                    if status in ("succeeded", "failed", "cancelled"):
                        output = record.get("output")
                        if isinstance(output, (dict, list)):
                            text = json.dumps(output, sort_keys=True)
                        elif output is None:
                            text = "The workflow finished without a terminal output."
                        else:
                            text = str(output)
                        ok = status == "succeeded"
                        return DispatchResult(
                            state=COMPLETED if ok else FAILED,
                            run_id=run_id,
                            output=text[:20_000],
                            error=None if ok else (record.get("error") or f"graph run {status}"),
                            error_class=None if ok else "GRAPH_RUN_FAILED",
                        )
                return DispatchResult(
                    state=FAILED, run_id=run_id,
                    error=f"graph run {graph_run_id} did not finish in {timeout_s}s",
                    error_class="GRAPH_RUN_TIMEOUT",
                )
        except Exception as exc:  # noqa: BLE001 - a bridge failure is reported, never raised
            return DispatchResult(
                state=FAILED, run_id=run_id,
                error=f"graph bridge failed: {type(exc).__name__}: {exc}",
                error_class="GRAPH_BRIDGE_ERROR",
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
            ledger_service=getattr(self._service, "ledger", None),
            search=getattr(self._service, "search", None),
        )
        result = await registry.execute(action.tool_name, f"call_{run_id}", dict(action.tool_args), ctx)
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
