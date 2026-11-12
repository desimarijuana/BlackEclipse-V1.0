"""The domain workers that back the Execution Fabric.

Every worker invokes an EXISTING Eclipse capability through a clean interface —
it never re-implements tool logic, an agent loop, browser control, the plugin
runtime or the automation engine:

  * agent       -> `service.run` (a normal run: trace, events, verification)
  * tool        -> `ToolRegistry.execute` (validation/permission/timeout shared)
  * research    -> agent run, or a named research tool
  * browser     -> a named browser tool, or an agent run
  * scraping    -> a named scraping tool, or an agent run
  * market      -> a named market tool, or an agent run
  * quant       -> a named quant tool, or an agent run
  * python/code -> the isolated `code.sandbox` runner (or a named tool)
  * plugin      -> `PluginManager.run_command` / plugin tool
  * notification-> the live event bus + Event System (the in-app/SSE surface)
  * automation  -> the Automation Engine (`fire`)
  * event       -> the Event System / bus `publish`

A worker returns a `WorkerOutcome`; the WorkerManager owns durability, retries,
cancellation and observability around it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from .config import FabricConfig
from .models import WorkerKind, WorkerOutcome
from .workers import BaseWorker, FunctionWorker, WorkerContext

log = logging.getLogger("harness.fabric.builtin_workers")


def _payload(ctx: WorkerContext) -> dict[str, Any]:
    return dict(ctx.job.input or {})


def _tool_name(payload: dict[str, Any]) -> Optional[str]:
    for key in ("tool", "name", "toolName"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tool_args(payload: dict[str, Any]) -> dict[str, Any]:
    args = payload.get("args") or payload.get("arguments") or payload.get("toolArgs")
    return dict(args) if isinstance(args, dict) else {}


def _query(payload: dict[str, Any]) -> str:
    for key in ("query", "objective", "prompt", "message", "task"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _default_model_settings() -> Any:
    from ..schemas import ModelSettings

    return ModelSettings(
        provider=(os.environ.get("HARNESS_FABRIC_PROVIDER")
                  or os.environ.get("HARNESS_JOB_PROVIDER", "ollama")),
        model=(os.environ.get("HARNESS_FABRIC_MODEL")
               or os.environ.get("HARNESS_JOB_MODEL", "llama3.1")),
        base_url=(os.environ.get("HARNESS_FABRIC_BASE_URL")
                  or os.environ.get("HARNESS_JOB_BASE_URL") or None),
        api_key=(os.environ.get("HARNESS_FABRIC_API_KEY")
                 or os.environ.get("HARNESS_JOB_API_KEY") or None),
    )


def _model_settings(payload: dict[str, Any]) -> Any:
    override = payload.get("modelSettings")
    if isinstance(override, dict) and override.get("provider") and override.get("model"):
        from ..schemas import ModelSettings

        try:
            return ModelSettings(**override)
        except Exception:  # noqa: BLE001 - a bad override falls back to defaults
            return _default_model_settings()
    return _default_model_settings()


def _tool_context(service: Any, ctx: WorkerContext) -> Any:
    from ..tools import ToolContext

    return ToolContext(
        run_id=f"fabric_{ctx.job.id}",
        log=lambda *_: None,
        memory_store=getattr(service, "store", None),
        memory_service=getattr(service, "memory", None),
        skill_registry=getattr(service, "skill_registry", None),
        tool_registry=getattr(service, "registry", None),
        bus=getattr(service, "bus", None),
        approvals=getattr(service, "approvals", None),
        market_gateway=getattr(service, "market_gateway", None),
        market_store=getattr(service, "market_store", None),
        portfolio_service=getattr(service, "portfolio", None),
        ledger_service=getattr(service, "ledger", None),
        quant_store=getattr(service, "quant_store", None),
        dataset_store=getattr(service, "dataset_store", None),
        search=getattr(service, "search", None),
        plugin_manager=getattr(service, "plugins", None),
        evidence_store=getattr(service, "evidence_store", None),
        data_bridge=_server_bridge(service),
    )


def _server_bridge(service: Any) -> Any:
    """The market DataBridge for market-fetching tools, or None. Best-effort."""
    factory = getattr(service, "server_bridge", None)
    if not callable(factory):
        return None
    try:
        return factory()
    except Exception:  # noqa: BLE001 - an unavailable bridge must not break a job
        return None


async def _run_tool(service: Any, ctx: WorkerContext, tool: str, args: dict[str, Any]) -> WorkerOutcome:
    registry = getattr(service, "registry", None)
    if registry is None:
        return WorkerOutcome(status="failed", error="the tool registry is unavailable",
                             error_class="RUNTIME_UNAVAILABLE")
    result = await registry.execute(tool, f"fabric_{ctx.job.id}", args, _tool_context(service, ctx))
    if getattr(result, "ok", False):
        return WorkerOutcome(status="succeeded", output=getattr(result, "data", None) or result.text,
                             metrics={"tool": tool})
    error = getattr(result, "error", None)
    return WorkerOutcome(
        status="failed",
        error=(getattr(error, "message", None) or getattr(result, "text", "tool failed")),
        error_class=(getattr(error, "code", None) or "TOOL_ERROR"),
        retryable=bool(getattr(error, "retryable", False)),
    )


async def _run_agent(service: Any, ctx: WorkerContext, *, default_agent: str = "eclipse-agent",
                     default_agent_from_input: bool = True) -> WorkerOutcome:
    runner = getattr(service, "run", None)
    if runner is None:
        return WorkerOutcome(status="failed", error="the agent runtime is unavailable",
                             error_class="RUNTIME_UNAVAILABLE")
    from ..schemas import RunInput, RunRequest

    payload = _payload(ctx)
    query = _query(payload)
    if not query:
        return WorkerOutcome(status="failed", error="no query/objective supplied to the agent worker",
                             error_class="INVALID_INPUT")
    agent_id = (
        (payload.get("agentId") if default_agent_from_input else None)
        or ctx.job.agent_id or default_agent
    )
    request = RunRequest(
        runId=f"fabric_run_{ctx.job.id}_{ctx.attempt}",
        input=RunInput(query=query[:4000], context=payload.get("context") if isinstance(payload.get("context"), dict) else None),
        agentId=agent_id,
        modelSettings=_model_settings(payload),
        callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        callbackToken=os.environ.get("HARNESS_CALLBACK_TOKEN") or os.environ.get("CRON_SECRET"),
        parentRunId=payload.get("parentRunId"),
        userId=payload.get("userId"),
        workspaceId=payload.get("workspaceId"),
        sessionId=payload.get("sessionId"),
        maxSteps=payload.get("maxSteps"),
        runTimeoutMs=payload.get("runTimeoutMs"),
    )
    result = await runner(request)
    dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    status = str(dumped.get("status") or "failed")
    error = dumped.get("error")
    if status == "completed":
        return WorkerOutcome(
            status="succeeded", output=dumped.get("output"),
            metrics={"runId": dumped.get("runId"), "totalTokens": dumped.get("totalTokens", 0)},
        )
    return WorkerOutcome(
        status="failed",
        error=(error.get("message") if isinstance(error, dict) else None) or "agent run failed",
        error_class=(error.get("code") if isinstance(error, dict) else None) or "AGENT_ERROR",
        retryable=(error.get("code") in ("PROVIDER_TIMEOUT", "RATE_LIMITED", "NETWORK_ERROR")
                   if isinstance(error, dict) else False),
        metrics={"runId": dumped.get("runId")},
    )


async def _delegate(service: Any, ctx: WorkerContext, *, default_agent: str = "eclipse-agent") -> WorkerOutcome:
    """Route a domain job to a named tool, else to the agent runtime."""
    payload = _payload(ctx)
    tool = _tool_name(payload)
    if tool:
        return await _run_tool(service, ctx, tool, _tool_args(payload))
    if _query(payload):
        return await _run_agent(service, ctx, default_agent=default_agent)
    return WorkerOutcome(
        status="failed", error_class="INVALID_INPUT",
        error=f"job {ctx.job.type!r} needs a 'tool' or a 'query' in its input",
    )


async def _run_sandbox(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    """Execute code in the existing isolated sandbox, off the event loop."""
    payload = _payload(ctx)
    code = payload.get("code")
    argv = payload.get("argv")
    language = str(payload.get("language") or "python").lower()
    if not code and not argv:
        tool = _tool_name(payload)
        if tool:
            return await _run_tool(service, ctx, tool, _tool_args(payload))
        if _query(payload):
            return await _run_agent(service, ctx)
        return WorkerOutcome(status="failed", error_class="INVALID_INPUT",
                             error="a sandbox job needs 'code' or 'argv'")
    try:
        from ..code import sandbox  # noqa: PLC0415
        from ..code.sandbox import RunSpec  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return WorkerOutcome(status="failed", error=f"the sandbox is unavailable: {exc}",
                             error_class="SANDBOX_UNAVAILABLE")

    workdir = Path(tempfile.mkdtemp(prefix="fabric-sbx-"))
    try:
        if argv:
            command = [str(a) for a in argv]
        else:
            interpreter = _interpreter(language)
            if interpreter is None:
                return WorkerOutcome(status="failed", error_class="RUNTIME_UNAVAILABLE",
                                     error=f"no interpreter for language {language!r}")
            command = [interpreter, "-c", str(code)]
        spec = RunSpec(
            argv=command, cwd=workdir, env=sandbox.build_env(),
            timeout_s=max(1, int(ctx.job.timeout_ms / 1000)),
            output_cap_bytes=int(payload.get("outputCapBytes", 100_000)),
            network=bool(payload.get("network", False)),
            cpu_seconds=int(payload.get("cpuSeconds", 0) or 0),
            memory_mb=int(payload.get("memoryMb", 0) or 0),
        )

        import threading  # noqa: PLC0415

        cancel = threading.Event()
        watcher = asyncio.create_task(_bridge_cancel(ctx, cancel))
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: sandbox.run(spec, cancel_event=cancel))
        finally:
            watcher.cancel()
        if result.cancelled:
            return WorkerOutcome(status="cancelled", error="sandbox run cancelled",
                                 error_class="CANCELLED")
        if result.timed_out:
            return WorkerOutcome(status="timed_out", error="sandbox run timed out",
                                 error_class="TIMEOUT", retryable=True)
        if result.launch_error:
            return WorkerOutcome(status="failed", error=result.launch_error,
                                 error_class="SANDBOX_LAUNCH_ERROR")
        if result.exit_code not in (0, None):
            return WorkerOutcome(
                status="failed", error=f"exit code {result.exit_code}",
                error_class="NONZERO_EXIT", output=result.output,
                metrics={"exitCode": result.exit_code, "durationMs": result.duration_ms},
            )
        return WorkerOutcome(
            status="succeeded", output=result.output,
            metrics={"exitCode": result.exit_code, "durationMs": result.duration_ms,
                     "truncated": result.truncated},
        )
    finally:
        import shutil  # noqa: PLC0415

        shutil.rmtree(workdir, ignore_errors=True)


def _interpreter(language: str) -> Optional[str]:
    import sys  # noqa: PLC0415

    if language in ("python", "py", "python3"):
        return sys.executable or "python"
    if language in ("javascript", "js", "node"):
        from shutil import which  # noqa: PLC0415
        return which("node")
    if language in ("shell", "sh", "bash"):
        from shutil import which  # noqa: PLC0415
        return which("bash") or which("sh")
    return None


async def _bridge_cancel(ctx: WorkerContext, event: "Any") -> None:
    try:
        await ctx.cancel_event.wait()
        event.set()
    except asyncio.CancelledError:
        raise


async def _task_worker(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    """Execute one claimed task through the task layer's own executor.

    The TaskScheduler still owns claim/lease/verification; this worker is the
    ONE execution attempt. It reconstructs the live task from the manager (a
    durable row, not a serialized object on the job) and reports the task
    outcome as the worker output.
    """
    payload = _payload(ctx)
    task_id = str(payload.get("taskId") or ctx.job.task_id or "")
    run_id = str(payload.get("runId") or ctx.job.id)
    manager = getattr(service, "tasks", None)
    executor = getattr(service, "task_executor", None)
    if manager is None or executor is None or not task_id:
        return WorkerOutcome(
            status="failed", error_class="RUNTIME_UNAVAILABLE",
            error="the task runtime (manager or executor) is unavailable",
        )
    try:
        task = manager.get_task(task_id)
        from ..tasks.context import build_task_context  # noqa: PLC0415

        context = build_task_context(
            manager, task,
            constraints={"leaseSeconds": int(payload.get("leaseSeconds") or 600)},
        )
        outcome = await executor(task, context, run_id)
    except Exception as exc:  # noqa: BLE001 - a task failure is data
        return WorkerOutcome(status="failed", error=str(exc)[:2000],
                             error_class="TASK_RUNTIME_ERROR")
    data = outcome.to_dict() if hasattr(outcome, "to_dict") else dict(outcome or {})
    ok = str(data.get("status") or "") == "completed"
    return WorkerOutcome(
        status="succeeded" if ok else "failed",
        output=data,
        error=str(data.get("error") or ""),
        error_class=str(data.get("errorClass") or ""),
        metrics={"taskId": task_id},
    )


async def _plugin_worker(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    payload = _payload(ctx)
    manager = getattr(service, "plugins", None)
    plugin_id = payload.get("plugin") or payload.get("pluginId")
    command = payload.get("command")
    if manager is not None and plugin_id and command:
        try:
            result = await manager.run_command(str(plugin_id), str(command), _tool_args_or_config(payload))
        except Exception as exc:  # noqa: BLE001
            return WorkerOutcome(status="failed", error=str(exc)[:2000], error_class="PLUGIN_ERROR",
                                 retryable=True)
        return WorkerOutcome(status="succeeded", output=result)
    return await _delegate(service, ctx)


def _tool_args_or_config(payload: dict[str, Any]) -> dict[str, Any]:
    args = payload.get("args")
    if isinstance(args, dict):
        return dict(args)
    config = payload.get("config")
    return dict(config) if isinstance(config, dict) else {}


async def _notification_worker(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    from ..persistence import now_iso

    payload = _payload(ctx)
    notification = {
        "jobId": ctx.job.id,
        "title": str(payload.get("title") or payload.get("subject") or "Eclipse notification"),
        "message": str(payload.get("message") or payload.get("body") or ""),
        "level": str(payload.get("level") or "info"),
        "target": str(payload.get("target") or "in_app"),
        "correlationId": ctx.job.correlation_id,
        "at": now_iso(),
    }
    delivered = False
    bus = getattr(service, "bus", None)
    if bus is not None:
        try:
            bus.publish({"type": "notification.delivered", "data": notification, "at": notification["at"]})
            delivered = True
        except Exception:  # noqa: BLE001
            pass
    system = getattr(service, "_event_system", None)
    if system is not None:
        try:
            system.emit_nowait("notification.delivered", notification)
            delivered = True
        except Exception:  # noqa: BLE001
            pass
    if not delivered:
        return WorkerOutcome(status="failed", error="no notification surface is available",
                             error_class="NO_DESTINATION")
    ctx.log("notification.delivered", notification)
    return WorkerOutcome(status="succeeded", output=notification)


async def _automation_worker(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    payload = _payload(ctx)
    automation_id = payload.get("automationId") or payload.get("automation") or payload.get("id")
    engine = None
    getter = getattr(service, "automation_engine", None)
    if callable(getter):
        engine = getter()
    if engine is None:
        engine = getattr(service, "automation", None)
    if engine is None or not automation_id:
        return WorkerOutcome(status="failed", error_class="INVALID_INPUT",
                             error="an automation job needs an automationId and a live engine")
    execution_id = await engine.fire(str(automation_id), trigger_type="fabric",
                                     trigger_ref=ctx.job.correlation_id)
    if execution_id is None:
        return WorkerOutcome(status="failed", error_class="AUTOMATION_NOT_ACTIVE",
                             error=f"automation {automation_id!r} is not active")
    return WorkerOutcome(status="succeeded", output={"executionId": execution_id},
                         metrics={"automationId": str(automation_id)})


async def _event_worker(service: Any, ctx: WorkerContext) -> WorkerOutcome:
    payload = _payload(ctx)
    event_type = str(payload.get("eventType") or payload.get("type") or "fabric.event")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    delivered = False
    system = getattr(service, "_event_system", None)
    if system is not None:
        try:
            system.emit_nowait(event_type, {**data, "jobId": ctx.job.id})
            delivered = True
        except Exception:  # noqa: BLE001
            pass
    bus = getattr(service, "bus", None)
    if bus is not None:
        try:
            from ..persistence import now_iso
            bus.publish({"type": event_type, "data": data, "jobId": ctx.job.id, "at": now_iso()})
            delivered = True
        except Exception:  # noqa: BLE001
            pass
    if not delivered:
        return WorkerOutcome(status="failed", error="no event surface is available",
                             error_class="NO_DESTINATION")
    return WorkerOutcome(status="succeeded", output={"emitted": event_type})


def _mk(kind: str, queues: list[str], handler: Callable[..., Any], service: Any,
        config: FabricConfig) -> BaseWorker:
    queue = queues[0]
    return FunctionWorker(
        kind, queues, handler, service=service,
        concurrency=config.concurrency_for(queue),
    )


def build_default_workers(service: Any, config: Optional[FabricConfig] = None) -> list[BaseWorker]:
    """Build one worker per domain, wired to the live service."""
    cfg = config or FabricConfig()

    async def agent_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _run_agent(service, ctx)

    async def tool_handler(ctx: WorkerContext) -> WorkerOutcome:
        payload = _payload(ctx)
        tool = _tool_name(payload)
        if not tool:
            return WorkerOutcome(status="failed", error_class="INVALID_INPUT",
                                 error="a tool job needs a 'tool' name")
        return await _run_tool(service, ctx, tool, _tool_args(payload))

    async def research_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _delegate(service, ctx, default_agent="eclipse-agent")

    async def browser_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _delegate(service, ctx)

    async def scraping_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _delegate(service, ctx)

    async def market_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _delegate(service, ctx)

    async def quant_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _delegate(service, ctx)

    async def python_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _run_sandbox(service, ctx)

    async def code_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _run_sandbox(service, ctx)

    async def plugin_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _plugin_worker(service, ctx)

    async def notification_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _notification_worker(service, ctx)

    async def automation_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _automation_worker(service, ctx)

    async def event_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _event_worker(service, ctx)

    async def task_handler(ctx: WorkerContext) -> WorkerOutcome:
        return await _task_worker(service, ctx)

    workers = [
        _mk(WorkerKind.AGENT.value, ["agent", "user"], agent_handler, service, cfg),
        _mk(WorkerKind.TOOL.value, ["user"], tool_handler, service, cfg),
        _mk(WorkerKind.RESEARCH.value, ["research"], research_handler, service, cfg),
        _mk(WorkerKind.BROWSER.value, ["browser"], browser_handler, service, cfg),
        _mk(WorkerKind.SCRAPING.value, ["scraping"], scraping_handler, service, cfg),
        _mk(WorkerKind.MARKET.value, ["market"], market_handler, service, cfg),
        _mk(WorkerKind.QUANT.value, ["quant"], quant_handler, service, cfg),
        _mk(WorkerKind.PYTHON.value, ["python"], python_handler, service, cfg),
        _mk(WorkerKind.CODE.value, ["code"], code_handler, service, cfg),
        _mk(WorkerKind.PLUGIN.value, ["plugin"], plugin_handler, service, cfg),
        _mk(WorkerKind.NOTIFICATION.value, ["notification"], notification_handler, service, cfg),
        _mk(WorkerKind.AUTOMATION.value, ["automation"], automation_handler, service, cfg),
        _mk(WorkerKind.EVENT.value, ["event"], event_handler, service, cfg),
        _mk(WorkerKind.TASK.value, ["task"], task_handler, service, cfg),
    ]
    # The ML Research Lab's dedicated worker (isolated, timeout-bounded,
    # cancellable, resource-limited). Wiring lives in `ml/fabric.py`; absence is
    # honest — ML background jobs then report WORKER_UNAVAILABLE rather than
    # silently running inline.
    try:
        from ..ml.fabric import build_ml_worker

        ml_worker = build_ml_worker(service)
        if ml_worker is not None:
            workers.append(ml_worker)
    except Exception:  # noqa: BLE001 - ML must never block the fabric
        log.warning("ML worker unavailable", exc_info=True)
    # Portfolio walk-forward simulations: long, cancellable, time-bounded. Wiring
    # lives in `portfolio/fabric.py`; absence is honest (jobs report
    # WORKER_UNAVAILABLE rather than silently running inline).
    try:
        from ..portfolio.fabric import build_portfolio_worker

        workers.append(build_portfolio_worker(service))
    except Exception:  # noqa: BLE001 - portfolio must never block the fabric
        log.warning("portfolio worker unavailable", exc_info=True)
    # Native video rendering: an isolated fframes process behind a queued,
    # timeout-bounded, cancellable, restart-recoverable worker on its own queue.
    # Wiring lives in `video/fabric.py`; absence is honest — video jobs then
    # report WORKER_UNAVAILABLE rather than silently rendering in-process.
    try:
        from ..video.fabric import build_video_worker

        video_worker = build_video_worker(service)
        if video_worker is not None:
            workers.append(video_worker)
    except Exception:  # noqa: BLE001 - video must never block the fabric
        log.warning("video worker unavailable", exc_info=True)
    return workers


__all__ = ["build_default_workers"]
