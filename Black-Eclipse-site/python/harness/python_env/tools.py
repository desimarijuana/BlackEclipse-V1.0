"""Agent tools for the managed analysis package environment."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .paths import installed_modules, installed_packages, lock_digest, pip_cache, read_lock, site_packages
from .provisioner import install, remove


def _root(ctx: ToolContext) -> Optional[Path]:
    workspace = getattr(ctx, "workspace", None)
    root = getattr(workspace, "root", None)
    if root:
        return Path(root)
    try:
        from ..code.workspace import default_root  # noqa: PLC0415

        return default_root()
    except Exception:  # noqa: BLE001
        return None


def _refusal(code: str, reason: str, **extra: Any) -> tuple[str, Any]:
    return f"REFUSED ({code}): {reason}", {"ok": False, "code": code, "reason": reason, **extra}


async def python_env_install(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    packages = args.get("packages")
    if not isinstance(packages, list) or not packages:
        return _refusal("PACKAGE_SPEC_REQUIRED", "name at least one Python package")
    from ..code.execution import interpreter_path  # noqa: PLC0415

    result = install(
        packages,
        interpreter=interpreter_path(),
        root=_root(ctx),
        timeout_s=int(args.get("timeoutS") or 600),
    )
    data = result.to_dict()
    if not result.ok:
        return _refusal(result.code, result.reason, **data)
    names = ", ".join(str(item.get("name")) for item in result.packages if item.get("name"))
    return (
        f"Installed into the analysis environment: {names}. "
        "The packages are now importable by analysis_run.",
        {"status": "installed", **data},
    )


async def python_env_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    packages = args.get("packages")
    if not isinstance(packages, list) or not packages:
        return _refusal("PACKAGE_SPEC_REQUIRED", "name at least one Python package")
    result = remove(packages, root=_root(ctx))
    data = result.to_dict()
    if not result.ok:
        return _refusal(result.code, result.reason, **data)
    return (
        f"Removed from the analysis environment: {', '.join(result.removed)}.",
        {"status": "removed", **data},
    )


async def python_env_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    root = _root(ctx)
    packages = installed_packages(root)
    if not packages:
        return "The analysis environment has no installed packages.", {
            "status": "ok", "packages": [], "modules": [], "lockDigest": lock_digest(root),
        }
    lines = [f"{len(packages)} package(s) in the analysis environment:"]
    for package in packages:
        lines.append(f"  - {package.get('name')} {package.get('version')}")
    return "\n".join(lines), {
        "status": "ok", "packages": packages,
        "modules": installed_modules(root), "lockDigest": lock_digest(root),
    }


async def python_env_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    root = _root(ctx)
    packages = installed_packages(root)
    lock = read_lock(root)
    target = site_packages(root)
    from ..code.execution import interpreter_path  # noqa: PLC0415

    data = {
        "status": "ok",
        "target": str(target),
        "cache": str(pip_cache(root)),
        "packageCount": len(packages),
        "modules": installed_modules(root),
        "lockDigest": lock_digest(root),
        "updatedAt": lock.get("updatedAt"),
        "interpreter": interpreter_path(),
    }
    return (
        f"Analysis environment: {len(packages)} package(s); "
        f"target exists={target.is_dir()}.",
        data,
    )


def register_python_env_tools(registry: ToolRegistry) -> list[str]:
    names = ("python_env_install", "python_env_remove", "python_env_list", "python_env_status")
    existing = [name for name in names if registry.get(name) is not None]
    if existing:
        return []
    registry.register(ToolDefinition(
        name="python_env_install",
        description=(
            "Install Python packages into Eclipse's isolated analysis environment so "
            "analysis_run can import them. Requires a single-use operator approval; "
            "the install is cached and recorded in a lock file. Use plain package "
            "names with optional versions, never URLs or paths."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
                "timeoutS": {"type": "integer"},
            },
            "required": ["packages"],
            "additionalProperties": False,
        },
        handler=python_env_install,
        permission="write", risk="medium", timeout_ms=660_000, effect="external_action",
    ))
    registry.register(ToolDefinition(
        name="python_env_remove",
        description=(
            "Remove packages from Eclipse's isolated analysis environment and update "
            "the lock file. Requires a single-use operator approval."
        ),
        input_schema={
            "type": "object",
            "properties": {"packages": {"type": "array", "items": {"type": "string"}}},
            "required": ["packages"],
            "additionalProperties": False,
        },
        handler=python_env_remove,
        permission="write", risk="low", timeout_ms=120_000, effect="write",
    ))
    registry.register(ToolDefinition(
        name="python_env_list",
        description="List packages installed in Eclipse's analysis environment. Read-only.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=python_env_list,
        permission="read", risk="low", timeout_ms=30_000,
    ))
    registry.register(ToolDefinition(
        name="python_env_status",
        description="Report the analysis environment target, cache, lock digest and interpreter. Read-only.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=python_env_status,
        permission="read", risk="low", timeout_ms=30_000,
    ))
    return list(names)


__all__ = [
    "python_env_install",
    "python_env_list",
    "python_env_remove",
    "python_env_status",
    "register_python_env_tools",
]
