"""The agent-facing Application Runtime tools.

Every handler is a thin adapter over the process-wide `ApplicationRuntimeManager`
(`application/runtime.py`). It resolves the workspace root + actor from the run,
performs one runtime operation, and returns a plain-text summary PLUS the
structured result. The autonomy profile is enforced structurally (the write tools
are removed at `plan_only` via `code/policy.py`) and in the handler (an operation
the profile does not permit is refused).

Destructive operations (remove a container/volume/image, compose down, env
mutation, killing a foreign process) require explicit authorization; this module
NEVER assumes permission. There is no `while true` anywhere: recovery is bounded.

This module owns the runtime, package, environment, port and health tools; the
container/compose handlers live in `container_tools.py` (same package) and share
`_tool_common.py` so there is no duplication and no import cycle.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ...tools import ToolContext
from ._tool_common import (
    ALL_TOOL_NAMES,
    APP_RUNTIME_READ_TOOLS,
    APP_RUNTIME_WRITE_TOOLS,
    EnvCompareInput,
    EnvNameInput,
    EnvSetInput,
    HealthInput,
    LogsInput,
    PackageInstallInput,
    PackageRunInput,
    PortInput,
    RecoverInput,
    RuntimeIdInput,
    StartInput,
    _NO_RUNTIME,
    _NO_WORKSPACE,
    _PROFILE_DENIED,
    actor as _actor,
    confined as _confined,
    grants_execute as _grants_execute,
    is_operator as _is_operator,
    manager as _manager,
    refusal as _refusal,
    root as _root,
    workspace_id as _workspace_id,
)
from .container_tools import CONTAINER_HANDLERS
from .k8s_infra_tools import K8S_INFRA_DESCRIPTIONS, K8S_INFRA_HANDLERS, k8s_infra_schemas

__all__ = [
    "ALL_TOOL_NAMES",
    "APP_RUNTIME_READ_TOOLS",
    "APP_RUNTIME_WRITE_TOOLS",
    "application_schemas",
    "register_application_tools",
]


# ── runtime handlers ─────────────────────────────────────────────────────────────


async def runtime_detect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    from .environment import EnvironmentDetector

    data = await asyncio.to_thread(lambda: EnvironmentDetector().detect())
    available = [name for name, info in data.get("tools", {}).items() if info.get("available")]
    return f"Detected {len(available)} available tool(s) on this machine.", {"status": "ok", **data}


async def runtime_capabilities(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    data = manager.describe()
    return "Runtime capabilities reported.", {"status": "ok", **data}


async def runtime_inspect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    data = await asyncio.to_thread(manager.inspect, root)
    desc = data.get("descriptor", {})
    text = (
        f"{desc.get('name', 'Project')} is a {desc.get('framework') or desc.get('language') or 'project'}"
        + (f" using {desc.get('packageManager')}" if desc.get("packageManager") else "")
        + (f" with {len(data.get('serviceGraph', {}).get('nodes', []))} service(s)" if data.get("serviceGraph", {}).get("nodes") else "")
        + "."
    )
    return text, {"status": "ok", **data}


async def runtime_start(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = StartInput(**{k: v for k, v in args.items() if v is not None})
    handle = await asyncio.to_thread(
        manager.start, root,
        name=model.name, workspace_id=_workspace_id(ctx),
        run_id=str(getattr(ctx, "run_id", "")), agent_id=getattr(ctx, "agent_id", None),
        install=model.install, build=model.build, use_compose=model.useCompose,
        wait_ready=model.waitReady, health_timeout_s=model.healthTimeoutS,
    )
    data = handle.to_dict()
    if handle.state.value == "FAILED":
        err = handle.last_error or {}
        return _refusal(err.get("category", "RUNTIME_FAILED"), err.get("message", "the application could not start"), runtime=data)
    text = (
        f"Started {handle.application_id} ({handle.state.value}"
        + (f", {handle.health.status.value}" if handle.health else "")
        + f") on {len(handle.ports)} port(s)."
    )
    return text, {"status": "ok", "runtime": data}


async def runtime_stop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    data = await asyncio.to_thread(manager.stop, model.runtimeId, actor=_actor(ctx))
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    return "Stopped the application.", {"status": "ok", **data}


async def runtime_restart(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    try:
        handle = await asyncio.to_thread(manager.restart, model.runtimeId, actor=_actor(ctx), install=False, build=False)
    except KeyError:
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    return f"Restarted the application (restart #{handle.restart_count}).", {"status": "ok", "runtime": handle.to_dict()}


async def runtime_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    data = manager.status(model.runtimeId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    runtime = data.get("runtime", {})
    return f"Runtime {model.runtimeId}: {runtime.get('state')} health={runtime.get('health', {}).get('status')}.", data


async def runtime_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await runtime_status(args, ctx)


async def runtime_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = LogsInput(**{k: v for k, v in args.items() if v is not None})
    if not model.runtimeId:
        return _refusal("INPUT_INVALID", "a runtime id is required")
    data = await asyncio.to_thread(
        manager.logs, model.runtimeId, tail=model.tail, stream=model.stream,
        filter_text=model.filter, errors_only=model.errorsOnly, severity=model.severity,
        service=model.service,
    )
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    text = "\n".join(s.get("text", "") for s in data.get("streams", []))[:4000] or "No output."
    return f"Logs for {model.runtimeId}:\n{text}", data


async def runtime_cleanup(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    data = await asyncio.to_thread(manager.cleanup, model.runtimeId, actor=_actor(ctx))
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    return "Cleaned up the runtime.", {"status": "ok", **data}


async def runtime_reconcile(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    data = await asyncio.to_thread(manager.reconcile)
    return f"Reconciled {data.get('count', 0)} runtime(s).", {"status": "ok", **data}


async def runtime_diagnose(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    data = manager.diagnose(model.runtimeId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    diagnosis = data.get("diagnosis", {})
    return f"Diagnosis: {diagnosis.get('category')} — {diagnosis.get('message')}", {"status": "ok", **data}


async def runtime_recover(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RecoverInput(**{k: v for k, v in args.items() if v is not None})
    data = await asyncio.to_thread(manager.recover, model.runtimeId, actor=_actor(ctx), max_attempts=model.maxAttempts)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    recovery = data.get("recovery", {})
    text = (
        f"Recovered after {recovery.get('attempts')} attempt(s)."
        if recovery.get("recovered") else
        f"Couldn't recover automatically: {recovery.get('stoppedReason') or 'no recovery applied'}."
    )
    return text, {"status": "ok", **data}


async def runtime_metrics(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = RuntimeIdInput(**{k: v for k, v in args.items() if v is not None})
    data = manager.metrics(model.runtimeId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    return f"Runtime {model.runtimeId}: uptime {int(data.get('uptimeS', 0))}s, {len(data.get('processes', []))} process(es).", data


# ── package handlers ─────────────────────────────────────────────────────────────


def _package_adapter(manager: Any, ctx: ToolContext, requested: str = "") -> tuple[Any, Any]:
    root = _root(ctx)
    if root is None:
        return None, {"status": "refused", "code": "WORKSPACE_UNBOUND", "reason": "there's no project open"}
    descriptor = manager.discover(root)
    if requested:
        adapter = manager.registry.packages.get(requested)
    else:
        adapter = manager.registry.packages.detect(root, descriptor)
    if adapter is None:
        return None, {"status": "refused", "code": "NO_PACKAGE_MANAGER", "reason": "I couldn't find a package manager for this project"}
    return adapter, None


async def package_detect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    data = await asyncio.to_thread(manager.discover, root)
    return (
        f"This project uses {data.package_manager or 'an unknown package manager'}"
        + (f" (lockfile {data.lockfile})" if data.lockfile else "")
        + ".",
        {"status": "ok", "descriptor": data.to_dict()},
    )


async def package_version(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    adapter, err = _package_adapter(manager, ctx)
    if err:
        return _refusal(err["code"], err["reason"])
    version = await asyncio.to_thread(adapter.version)
    return f"{adapter.name} {version or 'is not installed'}.", {"status": "ok", "manager": adapter.name, "version": version, "available": adapter.available()}


async def package_install(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PackageInstallInput(**{k: v for k, v in args.items() if v is not None})
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    adapter, err = _package_adapter(manager, ctx, model.manager)
    if err:
        return _refusal(err["code"], err["reason"])
    if not adapter.available():
        return _refusal("PACKAGE_MANAGER_UNAVAILABLE", f"{adapter.name} is required but isn't installed")
    if model.packages:
        if "install_package" not in (getattr(adapter, "capabilities", ()) or ()):
            return _refusal("NOT_SUPPORTED", f"{adapter.name} can't add individual packages")
        argv = adapter.install_package(root, model.packages)
    else:
        argv = adapter.install_dependencies(root)
    result = await asyncio.to_thread(adapter.run, argv, cwd=root, limits=manager.limits)
    if not result.ok:
        return _refusal("INSTALL_FAILED", f"{adapter.name} reported a failure (exit {result.exit_code})", output=result.output[-2000:])
    return f"Installed dependencies with {adapter.name}.", {"status": "ok", **result.to_dict()}


async def package_add(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await package_install({**args, "packages": args.get("packages") or []}, ctx)


async def _package_mutation(args: dict[str, Any], ctx: ToolContext, method: str) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PackageInstallInput(**{k: v for k, v in args.items() if v is not None})
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    adapter, err = _package_adapter(manager, ctx, model.manager)
    if err:
        return _refusal(err["code"], err["reason"])
    if not model.packages:
        return _refusal("INPUT_INVALID", "name at least one package")
    fn = getattr(adapter, method, None)
    if fn is None:
        return _refusal("NOT_SUPPORTED", f"{adapter.name} can't do that")
    result = await asyncio.to_thread(adapter.run, fn(root, model.packages), cwd=root, limits=manager.limits)
    if not result.ok:
        return _refusal("PACKAGE_OPERATION_FAILED", f"{adapter.name} reported a failure", output=result.output[-2000:])
    return f"Updated packages with {adapter.name}.", {"status": "ok", **result.to_dict()}


async def package_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _package_mutation(args, ctx, "remove_package")


async def package_update(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _package_mutation(args, ctx, "update_package")


async def package_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    adapter, err = _package_adapter(manager, ctx)
    if err:
        return _refusal(err["code"], err["reason"])
    argv = adapter.list_dependencies(root)
    if not argv:
        return "This package manager doesn't list dependencies.", {"status": "ok", "dependencies": []}
    result = await asyncio.to_thread(adapter.run, argv, cwd=root, limits=manager.limits)
    return f"Dependencies for {adapter.name}.", {"status": "ok", "manager": adapter.name, "output": result.output[-8000:]}


async def package_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PackageRunInput(**{k: v for k, v in args.items() if v is not None})
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    adapter, err = _package_adapter(manager, ctx, model.manager)
    if err:
        return _refusal(err["code"], err["reason"])
    if model.build:
        argv = adapter.build(root)
    elif model.test:
        argv = adapter.test(root)
    elif model.lint:
        argv = adapter.lint(root)
    elif model.script:
        argv = adapter.run_script(root, model.script, model.args)
    else:
        return _refusal("INPUT_INVALID", "say which script, or choose build/test/lint")
    result = await asyncio.to_thread(adapter.run, argv, cwd=root, limits=manager.limits)
    if not result.ok:
        return _refusal("SCRIPT_FAILED", f"{adapter.name} reported a failure (exit {result.exit_code})", output=result.output[-4000:])
    return f"Ran {adapter.name} successfully.", {"status": "ok", **result.to_dict()}


async def package_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await package_run({**args, "build": True}, ctx)


async def package_test(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await package_run({**args, "test": True}, ctx)


async def package_audit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    adapter, err = _package_adapter(manager, ctx)
    if err:
        return _refusal(err["code"], err["reason"])
    argv = adapter.audit(root)
    if not argv:
        return "This package manager has no audit command.", {"status": "ok", "audit": None}
    result = await asyncio.to_thread(adapter.run, argv, cwd=root, limits=manager.limits)
    return "Audit complete.", {"status": "ok", "manager": adapter.name, "output": result.output[-8000:], "exitCode": result.exit_code}


# ── environment handlers ─────────────────────────────────────────────────────────


async def environment_inspect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    data = manager.environment.metadata(root)
    secrets = [v["name"] for v in data.get("variables", []) if v.get("secret")]
    text = f"{data.get('count', 0)} variable(s) across {len(data.get('files', []))} file(s)"
    if secrets:
        text += f"; {len(secrets)} secret value(s) are hidden"
    return text + ".", {"status": "ok", **data}


async def environment_validate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    data = manager.environment.validate(root)
    if data.get("ok"):
        return "The environment is complete.", {"status": "ok", **data}
    return f"Missing environment value(s): {', '.join(data.get('missing', [])[:5])}.", {"status": "ok", **data}


async def environment_load(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    report = manager.environment.load(root)
    return f"Loaded {len(report.vars)} value(s) (secrets hidden).", {"status": "ok", **report.to_dict()}


async def environment_compare(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = EnvCompareInput(**{k: v for k, v in args.items() if v is not None})
    left = _confined(root, model.left)
    right = _confined(root, model.right)
    if left is None or right is None:
        return _refusal("PATH_OUTSIDE_WORKSPACE", "that file is outside the project")
    data = manager.environment.compare(left, right)
    return f"{len(data.get('onlyInLeft', []))} only-in-left, {len(data.get('onlyInRight', []))} only-in-right.", {"status": "ok", **data}


async def environment_set(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = EnvSetInput(**{k: v for k, v in args.items() if v is not None})
    path = _confined(root, model.file)
    if path is None:
        return _refusal("PATH_OUTSIDE_WORKSPACE", "that file is outside the project")
    if not _is_operator(ctx):
        return _refusal("OPERATOR_REQUIRED", "changing environment files needs the operator's approval")
    data = manager.environment.set(path, model.name, model.value)
    if data.get("status") != "ok":
        return _refusal(data.get("code", "ENV_SET_FAILED"), data.get("reason", "couldn't update that value"))
    return f"Set {model.name} (secret value hidden).", {"status": "ok", **data}


async def environment_unset(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = EnvNameInput(**{k: v for k, v in args.items() if v is not None})
    path = _confined(root, model.file)
    if path is None:
        return _refusal("PATH_OUTSIDE_WORKSPACE", "that file is outside the project")
    if not _is_operator(ctx):
        return _refusal("OPERATOR_REQUIRED", "changing environment files needs the operator's approval")
    data = manager.environment.unset(path, model.name)
    if data.get("status") != "ok":
        return _refusal(data.get("code", "ENV_UNSET_FAILED"), data.get("reason", "couldn't update that value"))
    return f"Removed {model.name}.", {"status": "ok", **data}


# ── port handlers ────────────────────────────────────────────────────────────────


async def port_check(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PortInput(**{k: v for k, v in args.items() if v is not None})
    if not model.port:
        return _refusal("INPUT_INVALID", "a port is required")
    data = await asyncio.to_thread(manager.ports.check, model.port)
    if data.get("inUse"):
        conflict = data.get("conflict") or {}
        return f"Port {model.port} is in use by {conflict.get('owner', 'another program')}.", {"status": "ok", **data}
    return f"Port {model.port} is free.", {"status": "ok", **data}


async def port_find_free(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PortInput(**{k: v for k, v in args.items() if v is not None})
    record = await asyncio.to_thread(manager.ports.allocate, preferred=model.preferred, owner="tool")
    return f"Free port: {record.port}.", {"status": "ok", "port": record.port, "record": record.to_dict()}


async def port_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    data = await asyncio.to_thread(manager.ports.summary)
    return f"{data.get('count', 0)} listening port(s).", {"status": "ok", **data}


async def port_identify_process(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = PortInput(**{k: v for k, v in args.items() if v is not None})
    if not model.port:
        return _refusal("INPUT_INVALID", "a port is required")
    conflict = await asyncio.to_thread(manager.ports.identify, model.port)
    if conflict is None:
        return f"Port {model.port} is free.", {"status": "ok", "inUse": False, "port": model.port}
    return f"Port {model.port} is held by {conflict.owner}.", {"status": "ok", "inUse": True, "conflict": conflict.to_dict()}


# ── health handlers ──────────────────────────────────────────────────────────────


async def health_check(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = HealthInput(**{k: v for k, v in args.items() if v is not None})
    if model.runtimeId:
        handle = manager._runtimes.get(model.runtimeId)  # noqa: SLF001
        if handle is None:
            return _refusal("NOT_FOUND", "there's no runtime with that id")
        root = Path(handle.descriptor.path) if handle.descriptor else _root(ctx)
        if root is None:
            return _refusal(*_NO_WORKSPACE)
        report = await asyncio.to_thread(manager.check_health, handle, root)
        return f"Health: {report.status.value}.", {"status": "ok", "health": report.to_dict()}
    from .models import HealthCheck

    if not model.kind or not model.target:
        return _refusal("INPUT_INVALID", "give a kind and a target")
    check = HealthCheck(kind=model.kind, target=model.target, timeout_s=model.timeoutS, name="adhoc")
    result = await asyncio.to_thread(manager.health.check, check)
    return f"Check {result.status.value}: {result.detail}", {"status": "ok", "result": result.to_dict()}


async def health_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = HealthInput(**{k: v for k, v in args.items() if v is not None})
    if not model.runtimeId:
        return _refusal("INPUT_INVALID", "a runtime id is required")
    data = manager.status(model.runtimeId)
    if data.get("status") == "not_found":
        return _refusal("NOT_FOUND", "there's no runtime with that id")
    health = data.get("runtime", {}).get("health", {})
    return f"Health: {health.get('status')}.", {"status": "ok", "health": health}


# ── schemas + registration ─────────────────────────────────────────────────────────


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def application_schemas() -> dict[str, dict[str, Any]]:
    runtime_id = {"runtimeId": {"type": "string"}}
    return {
        "runtime_detect": _obj({}),
        "runtime_capabilities": _obj({}),
        "runtime_inspect": _obj({}),
        "runtime_start": _obj({
            "name": {"type": "string"},
            "install": {"type": "boolean"},
            "build": {"type": "boolean"},
            "useCompose": {"type": "boolean"},
            "waitReady": {"type": "boolean"},
            "healthTimeoutS": {"type": "number"},
        }),
        "runtime_stop": _obj(runtime_id, ["runtimeId"]),
        "runtime_restart": _obj(runtime_id, ["runtimeId"]),
        "runtime_status": _obj(runtime_id, ["runtimeId"]),
        "runtime_health": _obj(runtime_id, ["runtimeId"]),
        "runtime_logs": _obj({"runtimeId": {"type": "string"}, "tail": {"type": "integer"}, "stream": {"type": "string"}, "service": {"type": "string"}, "filter": {"type": "string"}, "severity": {"type": "string"}, "errorsOnly": {"type": "boolean"}}),
        "runtime_cleanup": _obj(runtime_id, ["runtimeId"]),
        "runtime_reconcile": _obj({}),
        "runtime_diagnose": _obj(runtime_id, ["runtimeId"]),
        "runtime_recover": _obj({"runtimeId": {"type": "string"}, "maxAttempts": {"type": "integer"}}, ["runtimeId"]),
        "runtime_metrics": _obj(runtime_id, ["runtimeId"]),
        "package_detect": _obj({}),
        "package_version": _obj({"manager": {"type": "string"}}),
        "package_install": _obj({"manager": {"type": "string"}, "packages": {"type": "array", "items": {"type": "string"}}}),
        "package_add": _obj({"manager": {"type": "string"}, "packages": {"type": "array", "items": {"type": "string"}}}),
        "package_remove": _obj({"manager": {"type": "string"}, "packages": {"type": "array", "items": {"type": "string"}}}),
        "package_update": _obj({"manager": {"type": "string"}, "packages": {"type": "array", "items": {"type": "string"}}}),
        "package_list": _obj({"manager": {"type": "string"}}),
        "package_run": _obj({"script": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "build": {"type": "boolean"}, "test": {"type": "boolean"}, "lint": {"type": "boolean"}, "manager": {"type": "string"}}),
        "package_build": _obj({"manager": {"type": "string"}}),
        "package_test": _obj({"manager": {"type": "string"}}),
        "package_audit": _obj({"manager": {"type": "string"}}),
        "container_build": _obj({"tag": {"type": "string"}, "context": {"type": "string"}, "dockerfile": {"type": "string"}, "buildArgs": {"type": "object"}}, ["tag"]),
        "container_run": _obj({"image": {"type": "string"}, "name": {"type": "string"}, "command": {"type": "array", "items": {"type": "string"}}, "ports": {"type": "array", "items": {"type": "string"}}, "env": {"type": "object"}, "volumes": {"type": "array", "items": {"type": "string"}}, "detach": {"type": "boolean"}, "remove": {"type": "boolean"}, "network": {"type": "string"}}, ["image"]),
        "container_start": _obj({"container": {"type": "string"}}, ["container"]),
        "container_stop": _obj({"container": {"type": "string"}}, ["container"]),
        "container_restart": _obj({"container": {"type": "string"}}, ["container"]),
        "container_remove": _obj({"container": {"type": "string"}, "force": {"type": "boolean"}, "volumes": {"type": "boolean"}}, ["container"]),
        "container_exec": _obj({"container": {"type": "string"}, "command": {"type": "array", "items": {"type": "string"}}, "workdir": {"type": "string"}, "env": {"type": "object"}}, ["container", "command"]),
        "container_logs": _obj({"container": {"type": "string"}, "tail": {"type": "integer"}}, ["container"]),
        "container_inspect": _obj({"container": {"type": "string"}}, ["container"]),
        "container_stats": _obj({"container": {"type": "string"}}),
        "container_list": _obj({"all": {"type": "boolean"}}),
        "container_images": _obj({}),
        "container_health": _obj({"container": {"type": "string"}}, ["container"]),
        "container_pull": _obj({"image": {"type": "string"}}, ["image"]),
        "container_rmi": _obj({"image": {"type": "string"}, "force": {"type": "boolean"}}, ["image"]),
        "container_network": _obj({"action": {"type": "string"}, "name": {"type": "string"}, "container": {"type": "string"}}),
        "container_volume": _obj({"action": {"type": "string"}, "name": {"type": "string"}, "force": {"type": "boolean"}}),
        "compose_validate": _obj({"composeFile": {"type": "string"}}),
        "compose_config": _obj({"composeFile": {"type": "string"}}),
        "compose_build": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}}),
        "compose_up": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}, "detach": {"type": "boolean"}, "build": {"type": "boolean"}, "removeOrphans": {"type": "boolean"}}),
        "compose_down": _obj({"composeFile": {"type": "string"}, "volumes": {"type": "boolean"}, "removeOrphans": {"type": "boolean"}}),
        "compose_start": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}}),
        "compose_stop": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}}),
        "compose_restart": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}}),
        "compose_pull": _obj({"composeFile": {"type": "string"}}),
        "compose_rm": _obj({"composeFile": {"type": "string"}, "services": {"type": "array", "items": {"type": "string"}}}),
        "compose_ps": _obj({"composeFile": {"type": "string"}}),
        "compose_logs": _obj({"composeFile": {"type": "string"}, "service": {"type": "string"}, "tail": {"type": "integer"}}),
        "compose_exec": _obj({"service": {"type": "string"}, "command": {"type": "array", "items": {"type": "string"}}, "composeFile": {"type": "string"}}, ["service", "command"]),
        "environment_inspect": _obj({}),
        "environment_validate": _obj({}),
        "environment_load": _obj({}),
        "environment_compare": _obj({"left": {"type": "string"}, "right": {"type": "string"}}),
        "environment_set": _obj({"file": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "string"}}, ["name"]),
        "environment_unset": _obj({"file": {"type": "string"}, "name": {"type": "string"}}, ["name"]),
        "port_check": _obj({"port": {"type": "integer"}}),
        "port_find_free": _obj({"preferred": {"type": "integer"}}),
        "port_list": _obj({}),
        "port_identify_process": _obj({"port": {"type": "integer"}}),
        "health_check": _obj({"runtimeId": {"type": "string"}, "kind": {"type": "string"}, "target": {"type": "string"}, "timeoutS": {"type": "number"}}),
        "health_status": _obj({"runtimeId": {"type": "string"}}),
    }


_DESCRIPTIONS: dict[str, str] = {
    "runtime_detect": "Report which runtimes and tools (node, python, docker, …) are available on this computer. Read-only.",
    "runtime_capabilities": "Report the application runtime's adapters and capabilities. Read-only.",
    "runtime_inspect": "Inspect the open project and report its type, framework, package manager, services and ports. Read-only.",
    "runtime_start": "Start the application: install, build, start services and wait until it's healthy.",
    "runtime_stop": "Stop a running application cleanly.",
    "runtime_restart": "Restart a running application.",
    "runtime_status": "Report an application's state and health. Read-only.",
    "runtime_health": "Report an application's health. Read-only.",
    "runtime_logs": "Read a running application's output. Read-only.",
    "runtime_cleanup": "Stop an application and forget its transient state.",
    "runtime_reconcile": "Re-check the applications that were running before a restart. Read-only.",
    "runtime_diagnose": "Explain why an application isn't healthy. Read-only.",
    "runtime_recover": "Try to fix and restart an unhealthy application, within a bounded budget.",
    "runtime_metrics": "Report CPU, memory and uptime for a running application. Read-only.",
    "package_detect": "Report the project's package manager and lockfile. Read-only.",
    "package_version": "Report a package manager's version. Read-only.",
    "package_install": "Install the project's dependencies.",
    "package_add": "Add a dependency to the project.",
    "package_remove": "Remove a dependency from the project.",
    "package_update": "Update a dependency in the project.",
    "package_list": "List the project's dependencies. Read-only.",
    "package_run": "Run a package script (build/test/lint or a named script).",
    "package_build": "Build the project.",
    "package_test": "Run the project's tests.",
    "package_audit": "Audit the project's dependencies for known issues. Read-only.",
    "container_build": "Build a container image.",
    "container_run": "Run a container.",
    "container_start": "Start a stopped container.",
    "container_stop": "Stop a running container.",
    "container_restart": "Restart a container.",
    "container_remove": "Remove a container (needs approval).",
    "container_exec": "Run a command inside a container.",
    "container_logs": "Read a container's logs. Read-only.",
    "container_inspect": "Show a container's details. Read-only.",
    "container_stats": "Show a container's resource usage. Read-only.",
    "container_list": "List containers. Read-only.",
    "container_images": "List container images. Read-only.",
    "container_health": "Report a container's health. Read-only.",
    "container_pull": "Pull a container image.",
    "container_rmi": "Remove a container image (needs approval).",
    "container_network": "List/create/connect/remove container networks (removal needs approval).",
    "container_volume": "List/create/inspect/remove container volumes (removal needs approval).",
    "compose_validate": "Check a Compose file is valid. Read-only.",
    "compose_config": "Show the resolved Compose configuration. Read-only.",
    "compose_build": "Build the services in a Compose project.",
    "compose_up": "Start the services in a Compose project.",
    "compose_down": "Stop and remove a Compose project's services (needs approval).",
    "compose_start": "Start existing Compose services.",
    "compose_stop": "Stop Compose services.",
    "compose_restart": "Restart Compose services.",
    "compose_pull": "Pull the images a Compose project needs.",
    "compose_rm": "Remove stopped Compose service containers (needs approval).",
    "compose_ps": "List a Compose project's services and their status. Read-only.",
    "compose_logs": "Read a Compose service's logs. Read-only.",
    "compose_exec": "Run a command inside a Compose service.",
    "environment_inspect": "Report the project's environment variables (secret values hidden). Read-only.",
    "environment_validate": "Check the project's required environment values are present. Read-only.",
    "environment_load": "Load the project's environment (secret values hidden). Read-only.",
    "environment_compare": "Compare two environment files' keys (never values). Read-only.",
    "environment_set": "Set an environment value (needs approval).",
    "environment_unset": "Remove an environment value (needs approval).",
    "port_check": "Report whether a port is free and who holds it. Read-only.",
    "port_find_free": "Find a free port. Read-only.",
    "port_list": "List listening ports. Read-only.",
    "port_identify_process": "Identify who is using a port. Read-only.",
    "health_check": "Run a health check on a runtime or a single target. Read-only.",
    "health_status": "Report a runtime's health. Read-only.",
}

_HANDLERS: dict[str, Any] = {
    "runtime_detect": runtime_detect, "runtime_capabilities": runtime_capabilities,
    "runtime_inspect": runtime_inspect, "runtime_start": runtime_start,
    "runtime_stop": runtime_stop, "runtime_restart": runtime_restart,
    "runtime_status": runtime_status, "runtime_health": runtime_health,
    "runtime_logs": runtime_logs, "runtime_cleanup": runtime_cleanup,
    "runtime_reconcile": runtime_reconcile, "runtime_diagnose": runtime_diagnose,
    "runtime_recover": runtime_recover, "runtime_metrics": runtime_metrics,
    "package_detect": package_detect, "package_version": package_version,
    "package_install": package_install, "package_add": package_add,
    "package_remove": package_remove, "package_update": package_update,
    "package_list": package_list, "package_run": package_run,
    "package_build": package_build, "package_test": package_test,
    "package_audit": package_audit,
    "environment_inspect": environment_inspect, "environment_validate": environment_validate,
    "environment_load": environment_load, "environment_compare": environment_compare,
    "environment_set": environment_set, "environment_unset": environment_unset,
    "port_check": port_check, "port_find_free": port_find_free,
    "port_list": port_list, "port_identify_process": port_identify_process,
    "health_check": health_check, "health_status": health_status,
    **CONTAINER_HANDLERS,
    **K8S_INFRA_HANDLERS,
}


_HIGH_RISK = frozenset({
    "compose_down", "compose_rm", "container_remove", "container_rmi",
    "runtime_recover", "runtime_start", "runtime_restart",
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec", "helm_install",
    "helm_uninstall", "terraform_apply", "terraform_destroy",
    "deploy_run", "deploy_rollback", "deploy_delete",
})

#: The CRITICAL (destructive) tool names. They are external actions removed at
#: `plan_only` and additionally require explicit authorization at call time.
_CRITICAL_RISK = frozenset({
    "k8s_delete", "helm_uninstall", "terraform_destroy", "terraform_apply",
    "deploy_delete", "compose_down", "compose_rm", "container_remove", "container_rmi",
})


def register_application_tools(registry: Any) -> list[str]:
    """Register the application-runtime tools on the shared registry."""
    from ...tools import ToolDefinition

    schemas = {**application_schemas(), **k8s_infra_schemas()}
    descriptions = {**_DESCRIPTIONS, **K8S_INFRA_DESCRIPTIONS}
    added: list[str] = []
    for name in ALL_TOOL_NAMES:
        is_read = name in APP_RUNTIME_READ_TOOLS
        registry.register(ToolDefinition(
            name=name,
            description=descriptions[name],
            input_schema=schemas[name],
            handler=_HANDLERS[name],
            permission=("read" if is_read else "write"),
            risk=("low" if is_read else ("high" if name in _HIGH_RISK else "medium")),
            timeout_ms=(30_000 if is_read else 900_000),
            effect=(None if is_read else "external_action"),
        ))
        added.append(name)
    return added
