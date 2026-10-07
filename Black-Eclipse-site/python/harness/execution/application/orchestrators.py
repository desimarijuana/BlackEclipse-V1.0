"""Kubernetes orchestration adapters — kubectl, helm, kustomize.

These are the `OrchestratorAdapter` implementations. They are NOT a set of
kubectl wrappers: each is a `CliAdapter` with a CLOSED operation table, so the
model never supplies an executable, a flag or a shell fragment. Every call runs
through the ONE sandbox with a scrubbed environment.

Kubernetes concepts never leak into the local runtime engine: the engine asks the
registry for an orchestrator and calls its operations. Adding OpenShift or a
service mesh later is one more adapter.

Destructive operations (`delete`, `scale to 0`, `drain`, `rollout undo`) carry a
CRITICAL risk band and are removed at `plan_only`; the runtime policy additionally
requires authorization.
"""

from __future__ import annotations

from typing import Any, Optional

from .cli_base import CliAdapter, CliOperation, is_safe_env_key, is_safe_name, is_safe_value
from .registry import (
    CAP_HELM_INSTALL,
    CAP_HELM_LIST,
    CAP_HELM_REPO,
    CAP_HELM_STATUS,
    CAP_HELM_TEMPLATE,
    CAP_HELM_UNINSTALL,
    CAP_K8S_APPLY,
    CAP_K8S_DELETE,
    CAP_K8S_DESCRIBE,
    CAP_K8S_EXEC,
    CAP_K8S_GET,
    CAP_K8S_LOGS,
    CAP_K8S_ROLLOUT,
    CAP_K8S_SCALE,
    CAP_KUSTOMIZE_BUILD,
)

#: A Kubernetes label selector / field selector / jsonpath / file path value.
def _selector_ok(value: Any) -> bool:
    return value is None or is_safe_value(str(value))


def _validate_get(args: dict[str, Any]) -> Optional[tuple[str, str]]:
    kind = str(args.get("kind") or "")
    if not kind or not is_safe_name(kind):
        return ("INVALID_ARG", "'kind' must be a resource kind (pod, service, …)")
    if args.get("namespace") is not None and not is_safe_name(str(args["namespace"])):
        return ("INVALID_NAME", "'namespace' is not a valid name")
    if not _selector_ok(args.get("selector")):
        return ("INVALID_ARG", "'selector' contains an unsafe value")
    if not _selector_ok(args.get("name")):
        return ("INVALID_NAME", "'name' is not a valid name")
    return None


def _validate_apply(args: dict[str, Any]) -> Optional[tuple[str, str]]:
    if not args.get("file"):
        return ("INPUT_INVALID", "a manifest file is required")
    if not is_safe_value(str(args["file"])):
        return ("INVALID_ARG", "'file' contains an unsafe value")
    return None


def _validate_name_args(args: dict[str, Any]) -> Optional[tuple[str, str]]:
    for field_name in ("name", "namespace", "container"):
        if args.get(field_name) is not None and not is_safe_name(str(args[field_name])):
            return ("INVALID_NAME", f"{field_name!r} is not a valid name")
    return None


class KubernetesAdapter(CliAdapter):
    """`kubectl` with a closed operation table."""

    kind = "orchestrator"
    name = "kubectl"
    binary = "kubectl"
    aliases = ("k8s", "kubernetes")
    capabilities = frozenset(
        {CAP_K8S_GET, CAP_K8S_APPLY, CAP_K8S_DELETE, CAP_K8S_LOGS,
         CAP_K8S_EXEC, CAP_K8S_SCALE, CAP_K8S_ROLLOUT, CAP_K8S_DESCRIBE}
    )

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("version", "--client", "-o", "json"),
                                risk="SAFE", timeout_s=15, read_only=True),
        "get": CliOperation(
            name="get", subcommand=("get",),
            argv=lambda a: [
                str(a["kind"]),
                *([str(a["name"])] if a.get("name") else []),
                *(["-l", str(a["selector"])] if a.get("selector") else []),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                *(["--field-selector", str(a["fieldSelector"])] if a.get("fieldSelector") else []),
            ],
            validator=_validate_get,
            json_output=("-o", "json"), json_parse=True,
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "describe": CliOperation(
            name="describe", subcommand=("describe",),
            argv=lambda a: [str(a["kind"]), str(a["name"]),
                            *(["-n", str(a["namespace"])] if a.get("namespace") else [])],
            validator=lambda a: _validate_get({**a, "selector": None}),
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logs",),
            argv=lambda a: [str(a["name"]),
                            *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            *(["-c", str(a["container"])] if a.get("container") else []),
                            *(["--tail", str(int(a["tail"]))] if a.get("tail") is not None else []),
                            *(["--previous"] if a.get("previous") else [])],
            validator=_validate_name_args,
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "get_pods": CliOperation(
            name="get_pods", subcommand=("get", "pods"),
            argv=lambda a: [*(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            *(["-l", str(a["selector"])] if a.get("selector") else [])],
            validator=lambda a: (None if (a.get("namespace") is None or is_safe_name(str(a["namespace"])))
                                 and _selector_ok(a.get("selector"))
                                 else ("INVALID_NAME", "namespace/selector is invalid")),
            json_output=("-o", "json"), json_parse=True,
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "apply": CliOperation(
            name="apply", subcommand=("apply",),
            argv=lambda a: [
                *(["-f", str(a["file"])] if a.get("file") else []),
                *(["-k", str(a["kustomize"])] if a.get("kustomize") else []),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                *(["--dry-run=server"] if a.get("dryRun") else []),
            ],
            validator=_validate_apply,
            risk="HIGH", timeout_s=300,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("delete",),
            argv=lambda a: [
                str(a["kind"]),
                *([str(a["name"])] if a.get("name") else []),
                *(["-f", str(a["file"])] if a.get("file") else []),
                *(["-l", str(a["selector"])] if a.get("selector") else []),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                *(["--force"] if a.get("force") else []),
            ],
            validator=lambda a: (None if is_safe_name(str(a.get("kind") or "")) and
                                 all(_selector_ok(a.get(k)) for k in ("name", "selector", "file"))
                                 else ("INVALID_ARG", "delete arguments are invalid")),
            risk="CRITICAL", timeout_s=300,
        ),
        "scale": CliOperation(
            name="scale", subcommand=("scale",),
            argv=lambda a: [
                str(a["kind"]), str(a["name"]), "--replicas", str(int(a["replicas"])),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
            ],
            validator=lambda a: _validate_name_args(a) or (
                None if isinstance(a.get("replicas"), (int, float)) and 0 <= int(a["replicas"]) <= 1000
                else ("INVALID_ARG", "'replicas' must be between 0 and 1000")
            ),
            risk="HIGH", timeout_s=120,
        ),
        "rollout": CliOperation(
            name="rollout", subcommand=("rollout",),
            argv=lambda a: [
                str(a.get("action") or "status"), str(a.get("kind") or "deployment"),
                str(a.get("name") or ""),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
            ],
            validator=lambda a: (None if (a.get("action") in (None, "status", "restart", "undo", "history", "pause", "resume"))
                                 and _validate_name_args(a) is None
                                 else ("INVALID_ARG", "'action' is not a known rollout action")),
            risk="MEDIUM", timeout_s=180,
        ),
        "exec": CliOperation(
            name="exec", subcommand=("exec",),
            argv=lambda a: [
                str(a["name"]),
                *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                *(["-c", str(a["container"])] if a.get("container") else []),
                "--", *[str(t) for t in (a.get("command") or [])],
            ],
            validator=lambda a: _validate_name_args(a) or (
                None if (a.get("command") and all(is_safe_value(str(t)) or str(t).startswith("-")
                                                  for t in a["command"]))
                else ("INVALID_ARG", "a safe command is required")
            ),
            risk="HIGH", timeout_s=120,
        ),
        "port_forward": CliOperation(
            name="port_forward", subcommand=("port-forward",),
            # A port-forward is long-running; callers run it as a managed process,
            # so this operation is documented but refused here (structured).
            argv=lambda a: [],
            validator=lambda a: ("NOT_SUPPORTED", "use a managed process for port-forward"),
            risk="MEDIUM", timeout_s=10, read_only=True,
        ),
        "config": CliOperation(
            name="config", subcommand=("config", "view"),
            json_output=("-o", "json"), json_parse=True,
            risk="LOW", timeout_s=20, read_only=True,
        ),
        "contexts": CliOperation(
            name="contexts", subcommand=("config", "get-contexts"),
            json_output=("-o", "json"), json_parse=True,
            risk="LOW", timeout_s=20, read_only=True,
        ),
    }


class HelmAdapter(CliAdapter):
    """`helm` with a closed operation table."""

    kind = "orchestrator"
    name = "helm"
    binary = "helm"
    capabilities = frozenset(
        {CAP_HELM_LIST, CAP_HELM_STATUS, CAP_HELM_INSTALL, CAP_HELM_UNINSTALL,
         CAP_HELM_TEMPLATE, CAP_HELM_REPO}
    )

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("version", "--short"), risk="SAFE", timeout_s=15, read_only=True),
        "list": CliOperation(
            name="list", subcommand=("list", "-o", "json"),
            argv=lambda a: [*(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            *(["-A"] if a.get("allNamespaces") else [])],
            json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
        "status": CliOperation(
            name="status", subcommand=("status",),
            argv=lambda a: [str(a["release"]), *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            "-o", "json"],
            validator=lambda a: (None if is_safe_name(str(a.get("release") or "")) else ("INVALID_NAME", "a valid release is required")),
            json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
        "template": CliOperation(
            name="template", subcommand=("template",),
            argv=lambda a: [str(a["release"]), str(a["chart"]),
                            *(["-f", str(a["values"])] if a.get("values") else []),
                            *(["-n", str(a["namespace"])] if a.get("namespace") else [])],
            validator=lambda a: (None if is_safe_name(str(a.get("release") or "")) and is_safe_value(str(a.get("chart") or ""))
                                 else ("INVALID_ARG", "release and chart are required")),
            risk="LOW", timeout_s=120, read_only=True,
        ),
        "install": CliOperation(
            name="install", subcommand=("upgrade", "--install"),
            argv=lambda a: [str(a["release"]), str(a["chart"]),
                            *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            *(["--create-namespace"] if a.get("createNamespace") else []),
                            *(["-f", str(a["values"])] if a.get("values") else []),
                            *(["--set", *[f"{k}={v}" for k, v in (a.get("set") or {}).items()]] if a.get("set") else []),
                            *(["--atomic"] if a.get("atomic") else []),
                            *(["--wait"] if a.get("wait") else [])],
            validator=lambda a: (None if is_safe_name(str(a.get("release") or "")) and is_safe_value(str(a.get("chart") or ""))
                                 and all(is_safe_env_key(str(k)) for k in (a.get("set") or {}))
                                 else ("INVALID_ARG", "release/chart/set are invalid")),
            risk="HIGH", timeout_s=600,
        ),
        "uninstall": CliOperation(
            name="uninstall", subcommand=("uninstall",),
            argv=lambda a: [str(a["release"]), *(["-n", str(a["namespace"])] if a.get("namespace") else []),
                            *(["--keep-history"] if a.get("keepHistory") else [])],
            validator=lambda a: (None if is_safe_name(str(a.get("release") or "")) else ("INVALID_NAME", "a valid release is required")),
            risk="CRITICAL", timeout_s=300,
        ),
        "repo": CliOperation(
            name="repo", subcommand=("repo", "list", "-o", "json"),
            json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
    }


class KustomizeAdapter(CliAdapter):
    """`kustomize` with a closed operation table (read-only build)."""

    kind = "orchestrator"
    name = "kustomize"
    binary = "kustomize"
    capabilities = frozenset({CAP_KUSTOMIZE_BUILD})

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("version",), risk="SAFE", timeout_s=15, read_only=True),
        "build": CliOperation(
            name="build", subcommand=("build",),
            argv=lambda a: [str(a.get("path") or ".")],
            validator=lambda a: (None if _selector_ok(a.get("path")) else ("INVALID_ARG", "'path' contains an unsafe value")),
            risk="LOW", timeout_s=120, read_only=True,
        ),
    }


def build_orchestrator_adapters() -> list[CliAdapter]:
    """The shipped orchestration adapters (Kubernetes, Helm, Kustomize)."""
    return [KubernetesAdapter(), HelmAdapter(), KustomizeAdapter()]


__all__ = [
    "HelmAdapter",
    "KubernetesAdapter",
    "KustomizeAdapter",
    "build_orchestrator_adapters",
]
