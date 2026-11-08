"""Shared context helpers and input models for the Application Runtime tools.

Extracted so `tools.py` (runtime/package/environment/port/health) and
`container_tools.py` (container/compose) share ONE definition of the refusal
helper, the manager/root resolvers and the pydantic input models — no duplication,
no import cycle (both import from here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ...code import policy
from ...tools import ToolContext
from . import runtime as runtime_mod

# ── tool name sets (the autonomy boundary needs these) ──────────────────────────

APP_RUNTIME_WRITE_TOOLS: tuple[str, ...] = (
    "runtime_start", "runtime_stop", "runtime_restart", "runtime_cleanup",
    "runtime_recover",
    "workspace_start", "workspace_stop",
    "package_install", "package_add", "package_remove", "package_update",
    "package_run", "package_build", "package_test",
    "container_build", "container_run", "container_start", "container_stop",
    "container_restart", "container_exec", "container_remove", "container_pull",
    "container_rmi", "container_network", "container_volume",
    "compose_build", "compose_up", "compose_down", "compose_start",
    "compose_stop", "compose_restart", "compose_exec", "compose_pull", "compose_rm",
    "environment_set", "environment_unset",
)

APP_RUNTIME_READ_TOOLS: tuple[str, ...] = (
    "runtime_detect", "runtime_capabilities", "runtime_inspect", "runtime_status",
    "runtime_health", "runtime_logs", "runtime_reconcile", "runtime_diagnose",
    "runtime_metrics", "runtime_metrics_history",
    "workspace_graph",
    "package_detect", "package_version", "package_list", "package_audit",
    "container_logs", "container_inspect", "container_stats", "container_list",
    "container_images", "container_health",
    "compose_validate", "compose_config", "compose_ps", "compose_logs",
    "environment_inspect", "environment_validate", "environment_load",
    "environment_compare",
    "port_check", "port_find_free", "port_list", "port_identify_process",
    "health_check", "health_status",
    # Orchestration / infrastructure / cloud read-only surface.
    "k8s_status", "k8s_get", "k8s_get_pods", "k8s_describe", "k8s_logs",
    "k8s_rollout", "helm_list", "helm_status", "kustomize_build",
    "terraform_init", "terraform_validate", "terraform_fmt", "terraform_plan",
    "terraform_output", "terraform_state",
    "cloud_providers", "deploy_status", "deploy_logs",
)

#: Orchestration / infrastructure / cloud mutations (removed at `plan_only`).
APP_RUNTIME_K8S_WRITE_TOOLS: tuple[str, ...] = (
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec",
    "helm_install", "helm_uninstall",
    "terraform_apply", "terraform_destroy",
    "deploy_run", "deploy_rollback", "deploy_delete", "deploy_promote",
    "k8s_port_forward", "k8s_logs_follow",
)

ALL_TOOL_NAMES = APP_RUNTIME_WRITE_TOOLS + APP_RUNTIME_READ_TOOLS + APP_RUNTIME_K8S_WRITE_TOOLS

_NO_RUNTIME = ("RUNTIME_UNAVAILABLE", "the application runtime isn't available right now")
_PROFILE_DENIED = ("PROFILE_DENIED", "this session isn't set up to run applications")
_NO_WORKSPACE = ("WORKSPACE_UNBOUND", "there's no project open to run")


def refusal(code: str, reason: str, **extra: Any) -> tuple[str, Any]:
    text = f"REFUSED ({code}): {reason}"
    # A failed script's OUTPUT is the diagnostic. Dropping it forced the agent to
    # re-run the same command through `terminal_run` just to see why it failed
    # (measured 2026-11-06: `package_test` refused with exit 1 and no output).
    output = extra.get("output")
    if isinstance(output, str) and output.strip():
        text += "\n--- output (data) ---\n" + output.strip()[:4000]
    return (text, {"status": "refused", "code": code, "reason": reason, **extra})


def manager() -> Any:
    return runtime_mod.get_application_runtime()


def grants_execute(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "code.execute" in policy.code_grants(str(autonomy)))


def binding(ctx: ToolContext) -> Any:
    from ...execution.service import workspace_binding

    return workspace_binding(ctx)


def root(ctx: ToolContext) -> Optional[Path]:
    resolved = binding(ctx)
    if resolved is None:
        return None
    candidate = Path(getattr(resolved, "root", "") or "")
    return candidate if candidate.is_dir() else None


def workspace_id(ctx: ToolContext) -> Optional[str]:
    resolved = binding(ctx)
    return getattr(resolved, "id", None) if resolved is not None else None


def actor(ctx: ToolContext) -> Any:
    from ...execution.service import make_actor

    return make_actor(ctx)


def is_operator(ctx: ToolContext) -> bool:
    if bool(getattr(ctx, "operator", False)):
        return True
    return str(getattr(ctx, "autonomy", "")) == "approve_external" and bool(getattr(ctx, "direct", False))


def is_abs(value: str) -> bool:
    import os

    return os.path.isabs(str(value))


def confined(root_path: Path, rel: str) -> Optional[Path]:
    """Resolve an environment file inside the workspace.

    `.env*` files are PROTECTED paths by policy, so this does NOT use
    `resolve_within` (which would refuse them). It allows a bare env-file name at
    the project root, or a path that resolves inside the root; traversal, an
    absolute path, or an escape is refused.
    """
    import os

    name = str(rel or "").strip()
    if not name or "\x00" in name:
        return None
    if os.path.isabs(name):
        return None
    if any(part == ".." for part in name.replace("\\", "/").split("/")):
        return None
    root_resolved = Path(root_path).resolve()
    candidate = (root_resolved / name).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def default_compose_file(root_path: Path) -> str:
    for name in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"):
        if (Path(root_path) / name).is_file():
            return name
    return ""


# ── input models ───────────────────────────────────────────────────────────────


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartInput(_Base):
    name: str = Field(default="", max_length=200)
    install: bool = True
    build: bool = False
    useCompose: Optional[bool] = None  # noqa: N815
    waitReady: bool = True  # noqa: N815
    healthTimeoutS: float = Field(default=30.0, ge=1.0, le=600.0)  # noqa: N815


class RuntimeIdInput(_Base):
    runtimeId: str = Field(..., min_length=1, max_length=128)  # noqa: N815


class LogsInput(_Base):
    runtimeId: str = Field(default="", max_length=128)  # noqa: N815
    tail: int = Field(default=200, ge=0, le=10_000)
    stream: Optional[str] = Field(default=None, max_length=16)
    service: str = Field(default="", max_length=200)
    filter: str = Field(default="", max_length=200)
    severity: str = Field(default="", max_length=32)
    errorsOnly: bool = False  # noqa: N815


class RecoverInput(_Base):
    runtimeId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    maxAttempts: Optional[int] = Field(default=None, ge=1, le=10)  # noqa: N815


class PackageInstallInput(_Base):
    manager: str = Field(default="", max_length=32)
    packages: list[str] = Field(default_factory=list, max_length=64)


class PackageRunInput(_Base):
    script: str = Field(default="", max_length=200)
    args: list[str] = Field(default_factory=list, max_length=64)
    build: bool = False
    test: bool = False
    lint: bool = False
    manager: str = Field(default="", max_length=32)


class ContainerBuildInput(_Base):
    tag: str = Field(..., min_length=1, max_length=255)
    context: str = Field(default=".", max_length=1_000)
    dockerfile: str = Field(default="", max_length=500)
    buildArgs: dict[str, str] = Field(default_factory=dict)  # noqa: N815


class ContainerRunInput(_Base):
    image: str = Field(..., min_length=1, max_length=255)
    name: str = Field(default="", max_length=255)
    command: list[str] = Field(default_factory=list, max_length=64)
    ports: list[str] = Field(default_factory=list, max_length=32)
    env: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list, max_length=32)
    detach: bool = True
    remove: bool = False
    network: str = Field(default="", max_length=128)


class ContainerIdInput(_Base):
    container: str = Field(..., min_length=1, max_length=255)
    force: bool = False
    volumes: bool = False
    tail: int = Field(default=200, ge=0, le=10_000)


class ContainerExecInput(_Base):
    container: str = Field(..., min_length=1, max_length=255)
    command: list[str] = Field(..., min_length=1, max_length=64)
    workdir: str = Field(default="", max_length=1_000)
    env: dict[str, str] = Field(default_factory=dict)


class ContainerListInput(_Base):
    all: bool = True


class ComposeActionInput(_Base):
    composeFile: str = Field(default="", max_length=500)  # noqa: N815
    services: list[str] = Field(default_factory=list, max_length=64)
    detach: bool = True
    build: bool = False
    volumes: bool = False
    removeOrphans: bool = True  # noqa: N815


class ComposeLogsInput(_Base):
    composeFile: str = Field(default="", max_length=500)  # noqa: N815
    service: str = Field(default="", max_length=200)
    tail: int = Field(default=200, ge=0, le=10_000)


class ComposeExecInput(_Base):
    service: str = Field(..., min_length=1, max_length=200)
    command: list[str] = Field(..., min_length=1, max_length=64)
    composeFile: str = Field(default="", max_length=500)  # noqa: N815


class EnvSetInput(_Base):
    file: str = Field(default=".env", max_length=100)
    name: str = Field(..., min_length=1, max_length=128)
    value: str = Field(default="", max_length=8_000)


class EnvNameInput(_Base):
    file: str = Field(default=".env", max_length=100)
    name: str = Field(..., min_length=1, max_length=128)


class EnvCompareInput(_Base):
    left: str = Field(default=".env", max_length=500)
    right: str = Field(default=".env.example", max_length=500)


class PortInput(_Base):
    port: int = Field(default=0, ge=0, le=65_535)
    preferred: int = Field(default=0, ge=0, le=65_535)


class HealthInput(_Base):
    runtimeId: str = Field(default="", max_length=128)  # noqa: N815
    kind: str = Field(default="", max_length=32)
    target: str = Field(default="", max_length=2_000)
    timeoutS: float = Field(default=3.0, ge=0.1, le=60.0)  # noqa: N815


class K8sOpInput(_Base):
    kind: str = Field(default="", max_length=64)
    name: str = Field(default="", max_length=255)
    namespace: str = Field(default="", max_length=128)
    selector: str = Field(default="", max_length=512)
    container: str = Field(default="", max_length=255)
    tail: int = Field(default=200, ge=0, le=100_000)
    previous: bool = False
    file: str = Field(default="", max_length=1_000)
    dryRun: bool = False  # noqa: N815
    force: bool = False
    replicas: Optional[int] = Field(default=None, ge=0, le=1_000)
    action: str = Field(default="", max_length=32)
    command: list[str] = Field(default_factory=list, max_length=64)
    localPort: int = Field(default=0, ge=0, le=65_535)  # noqa: N815
    remotePort: int = Field(default=0, ge=0, le=65_535)  # noqa: N815
    address: str = Field(default="127.0.0.1", max_length=64)


class InfraOpInput(_Base):
    dir: str = Field(default="", max_length=1_000)
    vars: dict[str, str] = Field(default_factory=dict)
    target: str = Field(default="", max_length=512)
    planFile: str = Field(default="", max_length=512)  # noqa: N815
    out: str = Field(default="", max_length=512)
    name: str = Field(default="", max_length=255)
    autoApprove: bool = False  # noqa: N815
    upgrade: bool = False
    reconfigure: bool = False
    check: bool = False
    recursive: bool = False
    destroy: bool = False


class CloudDeployInput(_Base):
    provider: str = Field(default="", max_length=64)
    environment: str = Field(default="staging", max_length=32)
    service: str = Field(default="", max_length=255)
    stack: str = Field(default="", max_length=255)
    template: str = Field(default="", max_length=1_000)
    path: str = Field(default="", max_length=1_000)
    region: str = Field(default="", max_length=64)
    group: str = Field(default="", max_length=255)
    install: bool = True
    build: bool = True
    test: bool = False
    args: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ALL_TOOL_NAMES",
    "APP_RUNTIME_K8S_WRITE_TOOLS",
    "APP_RUNTIME_READ_TOOLS",
    "APP_RUNTIME_WRITE_TOOLS",
    "actor",
    "binding",
    "confined",
    "default_compose_file",
    "grants_execute",
    "is_abs",
    "is_operator",
    "manager",
    "refusal",
    "root",
    "workspace_id",
]
