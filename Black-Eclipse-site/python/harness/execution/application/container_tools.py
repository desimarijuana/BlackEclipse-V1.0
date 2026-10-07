"""Container and Compose agent tools.

Split out of `tools.py` to stay under the module size ceiling. Every handler is a
thin adapter over the process-wide `ApplicationRuntimeManager`; it resolves the
container/compose engine and returns a structured result. Destructive operations
remove/rm/down are `external_action` tools removed at `plan_only`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...tools import ToolContext
from ._tool_common import (
    ComposeActionInput,
    ComposeExecInput,
    ComposeLogsInput,
    ContainerBuildInput,
    ContainerExecInput,
    ContainerIdInput,
    ContainerListInput,
    ContainerRunInput,
    default_compose_file,
    is_abs,
    manager as _manager,
    refusal,
    root as _root,
    _NO_RUNTIME,
    _NO_WORKSPACE,
)


def _container(manager: Any) -> tuple[Any, Any]:
    engine = manager.container()
    if engine is None:
        return None, refusal("ENGINE_UNAVAILABLE", "no container engine (Docker or Podman) is available")
    return engine, None


def _container_ok(result: Any, action: str) -> tuple[str, Any]:
    if not result.ok:
        detail = result.reason or result.output[-1500:]
        return refusal(result.code or "CONTAINER_OPERATION_FAILED", f"couldn't {action}: {detail}", operation=result.operation)
    return f"{action.capitalize()} succeeded.", {"status": "ok", **result.to_dict()}


def _compose(manager: Any) -> tuple[Any, Any]:
    adapter = manager.compose_adapter()
    if adapter is None:
        return None, refusal("ENGINE_UNAVAILABLE", "no container engine with compose is available")
    return adapter, None


# ── container handlers ─────────────────────────────────────────────────────────


async def container_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerBuildInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    context = Path(model.context) if is_abs(model.context) else root / model.context
    result = await _to_thread(engine.build, context=context, tag=model.tag, dockerfile=model.dockerfile, args=model.buildArgs)
    return _container_ok(result, "build the image")


async def container_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerRunInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(
        engine.run, image=model.image, name=model.name, command=model.command,
        ports=model.ports, env=model.env, detach=model.detach, rm=model.remove,
        volumes=model.volumes, network=model.network,
    )
    return _container_ok(result, "run the container")


async def container_start(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _container_lifecycle(args, ctx, "start")


async def container_stop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _container_lifecycle(args, ctx, "stop")


async def container_restart(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _container_lifecycle(args, ctx, "restart")


async def _container_lifecycle(args: dict[str, Any], ctx: ToolContext, verb: str) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(getattr(engine, verb), model.container)
    return _container_ok(result, f"{verb} the container")


async def container_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.remove, model.container, force=model.force, volumes=model.volumes)
    return _container_ok(result, "remove the container")


async def container_exec(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerExecInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.exec, model.container, model.command, workdir=model.workdir, env=model.env)
    if not result.ok:
        return refusal(result.code or "EXEC_FAILED", "the command in the container failed", output=result.output[-2000:])
    return "Executed in the container.", {"status": "ok", **result.to_dict()}


async def container_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.logs, model.container, tail=model.tail)
    return f"Logs for {model.container}:\n{result.output[-4000:] or 'No output.'}", {"status": "ok", **result.to_dict()}


async def container_inspect(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.inspect, model.container)
    return f"Inspected {model.container}.", {"status": "ok", **result.to_dict()}


async def container_stats(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.stats, model.container or "")
    return "Container stats.", {"status": "ok", **result.to_dict()}


async def container_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerListInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.ps, all=model.all)
    return f"{len(result.data or [])} container(s).", {"status": "ok", **result.to_dict()}


async def container_images(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.images)
    return f"{len(result.data or [])} image(s).", {"status": "ok", **result.to_dict()}


async def container_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ContainerIdInput(**{k: v for k, v in args.items() if v is not None})
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.healthcheck, model.container)
    data = result.data if isinstance(result.data, dict) else {}
    status = data.get("Health", {}).get("Status", data.get("Status", "unknown"))
    return f"Container {model.container}: {status}.", {"status": "ok", **result.to_dict()}


async def container_pull(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    image = str(args.get("image", "")).strip()
    if not image:
        return refusal("INPUT_INVALID", "an image name is required")
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.pull, image)
    return _container_ok(result, "pull the image")


async def container_rmi(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    image = str(args.get("image", "")).strip()
    if not image:
        return refusal("INPUT_INVALID", "an image name is required")
    engine, err = _container(manager)
    if err:
        return err
    result = await _to_thread(engine.rmi, image, force=bool(args.get("force", False)))
    return _container_ok(result, "remove the image")


async def container_network(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    engine, err = _container(manager)
    if err:
        return err
    action = str(args.get("action", "ls")).strip().casefold()
    name = str(args.get("name", "")).strip()
    container = str(args.get("container", "")).strip()
    if action == "create":
        result = await _to_thread(engine.network_create, name)
    elif action == "connect":
        result = await _to_thread(engine.network_connect, name, container)
    elif action == "disconnect":
        result = await _to_thread(engine.network_disconnect, name, container)
    elif action == "rm":
        result = await _to_thread(engine.network_rm, name)
    else:
        result = await _to_thread(engine.network_ls)
    return "Networks.", {"status": "ok", **result.to_dict()}


async def container_volume(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    engine, err = _container(manager)
    if err:
        return err
    action = str(args.get("action", "ls")).strip().casefold()
    name = str(args.get("name", "")).strip()
    if action == "create":
        result = await _to_thread(engine.volume_create, name)
    elif action == "inspect":
        result = await _to_thread(engine.volume_inspect, name)
    elif action == "rm":
        result = await _to_thread(engine.volume_rm, name, force=bool(args.get("force", False)))
    else:
        result = await _to_thread(engine.volume_ls)
    return "Volumes.", {"status": "ok", **result.to_dict()}


# ── compose handlers ────────────────────────────────────────────────────────────


async def compose_validate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeActionInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    result = await _to_thread(compose.validate, cwd=root, compose_file=compose_file)
    return ("The compose file is valid." if result.ok else "The compose file isn't valid."), {"status": "ok", **result.to_dict()}


async def compose_config(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeActionInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    result = await _to_thread(compose.config, cwd=root, compose_file=compose_file)
    return "Compose configuration.", {"status": "ok", **result.to_dict()}


async def _compose_action(args: dict[str, Any], ctx: ToolContext, verb: str) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeActionInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    dispatch = {
        "build": lambda: compose.build(cwd=root, compose_file=compose_file, services=model.services),
        "up": lambda: compose.up(cwd=root, compose_file=compose_file, detach=model.detach, build=model.build, services=model.services, remove_orphans=model.removeOrphans),
        "down": lambda: compose.down(cwd=root, compose_file=compose_file, volumes=model.volumes, remove_orphans=model.removeOrphans),
        "start": lambda: compose.start(cwd=root, compose_file=compose_file, services=model.services),
        "stop": lambda: compose.stop(cwd=root, compose_file=compose_file, services=model.services),
        "restart": lambda: compose.restart(cwd=root, compose_file=compose_file, services=model.services),
        "pull": lambda: compose.pull(cwd=root, compose_file=compose_file),
        "rm": lambda: compose.rm(cwd=root, compose_file=compose_file, services=model.services, force=True),
    }
    action = dispatch.get(verb)
    if action is None:
        return refusal("UNKNOWN_ACTION", f"unknown compose action {verb!r}")
    result = await _to_thread(action)
    if not result.ok:
        return refusal(result.code or "COMPOSE_FAILED", f"compose {verb} failed: {result.reason or result.output[-1500:]}", operation=result.operation)
    return f"Compose {verb} succeeded.", {"status": "ok", **result.to_dict()}


async def compose_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "build")


async def compose_up(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "up")


async def compose_down(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "down")


async def compose_start(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "start")


async def compose_stop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "stop")


async def compose_restart(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "restart")


async def compose_pull(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "pull")


async def compose_rm(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _compose_action(args, ctx, "rm")


async def compose_ps(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeActionInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    result = await _to_thread(compose.ps, cwd=root, compose_file=compose_file, all=True)
    return f"{len(result.services)} service(s).", {"status": "ok", **result.to_dict()}


async def compose_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeLogsInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    result = await _to_thread(compose.logs, cwd=root, compose_file=compose_file, service=model.service, tail=model.tail)
    return f"Compose logs:\n{result.output[-4000:] or 'No output.'}", {"status": "ok", **result.to_dict()}


async def compose_exec(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = ComposeExecInput(**{k: v for k, v in args.items() if v is not None})
    compose, err = _compose(manager)
    if err:
        return err
    root = _root(ctx)
    if root is None:
        return refusal(*_NO_WORKSPACE)
    compose_file = model.composeFile or default_compose_file(root)
    result = await _to_thread(compose.exec, cwd=root, compose_file=compose_file, service=model.service, command=model.command)
    if not result.ok:
        return refusal(result.code or "EXEC_FAILED", "the command in the service failed", output=result.output[-2000:])
    return "Executed in the service.", {"status": "ok", **result.to_dict()}


CONTAINER_HANDLERS: dict[str, Any] = {
    "container_build": container_build, "container_run": container_run,
    "container_start": container_start, "container_stop": container_stop,
    "container_restart": container_restart, "container_remove": container_remove,
    "container_exec": container_exec, "container_logs": container_logs,
    "container_inspect": container_inspect, "container_stats": container_stats,
    "container_list": container_list, "container_images": container_images,
    "container_health": container_health, "container_pull": container_pull,
    "container_rmi": container_rmi, "container_network": container_network,
    "container_volume": container_volume,
    "compose_validate": compose_validate, "compose_config": compose_config,
    "compose_build": compose_build, "compose_up": compose_up, "compose_down": compose_down,
    "compose_start": compose_start, "compose_stop": compose_stop,
    "compose_restart": compose_restart, "compose_pull": compose_pull,
    "compose_rm": compose_rm, "compose_ps": compose_ps, "compose_logs": compose_logs,
    "compose_exec": compose_exec,
}


async def _to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(fn, *args, **kwargs)


__all__ = ["CONTAINER_HANDLERS"]
