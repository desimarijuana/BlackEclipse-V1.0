"""Agent tools for orchestration (Kubernetes), infrastructure (Terraform) and
cloud deployment (AWS/Azure/GCP/Cloudflare/Vercel/Railway/Render).

Every handler is a thin adapter over the process-wide `ApplicationRuntimeManager`.
It resolves the registry adapter, runs ONE closed operation, and returns a
structured result. The autonomy boundary is structural: the mutating operations
(`k8s_apply`, `k8s_delete`, `k8s_scale`, `k8s_exec`, `terraform_apply`,
`terraform_destroy`, `cloud_deploy`, `cloud_rollback`, `cloud_delete`,
`deploy_run`) live in the write set removed at `plan_only`; the read-only surface
stays. Production deploys and deletes additionally require authorization.

The model never supplies an executable, a flag or a shell fragment: it names an
OPERATION and structured arguments.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...tools import ToolContext
from ._tool_common import (
    CloudDeployInput,
    InfraOpInput,
    K8sOpInput,
    _NO_RUNTIME,
    _PROFILE_DENIED,
    grants_execute as _grants_execute,
    manager as _manager,
    refusal as _refusal,
    root as _root,
)


def _result(text: str, result: Any) -> tuple[str, Any]:
    if isinstance(result, dict):
        if result.get("status") == "refused":
            return _refusal(result.get("code", "REFUSED"), result.get("reason", "not available"))
        return text, {"status": "ok", **result}
    if not getattr(result, "ok", False):
        return _refusal(getattr(result, "code", "OPERATION_FAILED"),
                        getattr(result, "reason", "") or (result.output[-800:] if getattr(result, "output", "") else "operation failed"),
                        operation=getattr(result, "operation", ""))
    return text, {"status": "ok", **result.to_dict()}


# ── Kubernetes / Helm / Kustomize ────────────────────────────────────────────────


async def k8s_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    result = await asyncio.to_thread(manager.run_orchestrator, "config", {})
    return _result("Kubernetes context.", result)


async def k8s_get(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    result = await asyncio.to_thread(manager.run_orchestrator, "get", {
        "kind": model.kind, "name": model.name, "namespace": model.namespace,
        "selector": model.selector,
    })
    return _result(f"Got {model.kind}.", result)


async def k8s_get_pods(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    result = await asyncio.to_thread(manager.run_orchestrator, "get_pods", {
        "namespace": model.namespace, "selector": model.selector,
    })
    return _result("Listed pods.", result)


async def k8s_describe(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    result = await asyncio.to_thread(manager.run_orchestrator, "describe", {
        "kind": model.kind, "name": model.name, "namespace": model.namespace,
    })
    return _result(f"Described {model.kind} {model.name}.", result)


async def k8s_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if not model.name:
        return _refusal("INPUT_INVALID", "a pod name is required")
    result = await asyncio.to_thread(manager.run_orchestrator, "logs", {
        "name": model.name, "namespace": model.namespace, "container": model.container,
        "tail": model.tail, "previous": model.previous,
    })
    return _result(f"Logs for {model.name}.", result)


async def k8s_apply(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if not model.file:
        return _refusal("INPUT_INVALID", "a manifest file (relative to the project) is required")
    result = await asyncio.to_thread(manager.run_orchestrator, "apply", {
        "file": model.file, "namespace": model.namespace, "dryRun": model.dryRun,
    })
    return _result("Applied the manifest.", result)


async def k8s_delete(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    # Destructive: require explicit authorization via the runtime policy.
    allowed, _decision, reason = manager.policy.decide("k8s.delete", authorized=bool(getattr(ctx, "authorized", False)))
    if not allowed:
        return _refusal("AUTHORIZATION_REQUIRED", reason)
    result = await asyncio.to_thread(manager.run_orchestrator, "delete", {
        "kind": model.kind, "name": model.name, "namespace": model.namespace, "force": model.force,
    })
    return _result("Deleted the resource.", result)


async def k8s_scale(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if model.replicas is None:
        return _refusal("INPUT_INVALID", "a replica count is required")
    result = await asyncio.to_thread(manager.run_orchestrator, "scale", {
        "kind": model.kind or "deployment", "name": model.name,
        "namespace": model.namespace, "replicas": model.replicas,
    })
    return _result(f"Scaled {model.name} to {model.replicas}.", result)


async def k8s_rollout(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    result = await asyncio.to_thread(manager.run_orchestrator, "rollout", {
        "action": model.action or "status", "kind": model.kind or "deployment",
        "name": model.name, "namespace": model.namespace,
    })
    return _result("Rollout status.", result)


async def k8s_exec(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if not model.name or not model.command:
        return _refusal("INPUT_INVALID", "a pod name and a command are required")
    result = await asyncio.to_thread(manager.run_orchestrator, "exec", {
        "name": model.name, "namespace": model.namespace, "container": model.container,
        "command": model.command,
    })
    return _result("Executed in the pod.", result)


async def helm_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    result = await asyncio.to_thread(manager.run_orchestrator, "list", {"namespace": args.get("namespace")}, adapter="helm")
    return _result("Listed helm releases.", result)


async def helm_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _helm_op(args, ctx, "status", "release")


async def helm_install(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _helm_op(args, ctx, "install", "release")


async def helm_uninstall(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    allowed, _decision, reason = manager.policy.decide("k8s.delete", authorized=bool(getattr(ctx, "authorized", False)))
    if not allowed:
        return _refusal("AUTHORIZATION_REQUIRED", reason)
    return await _helm_op(args, ctx, "uninstall", "release")


async def _helm_op(args: dict[str, Any], ctx: ToolContext, op: str, required_field: str) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    payload = {k: v for k, v in args.items() if v is not None}
    if not payload.get(required_field):
        return _refusal("INPUT_INVALID", f"{required_field} is required")
    result = await asyncio.to_thread(manager.run_orchestrator, op, payload, adapter="helm")
    return _result(f"Helm {op}.", result)


async def kustomize_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    result = await asyncio.to_thread(manager.run_orchestrator, "build", {"path": args.get("path") or "."}, adapter="kustomize")
    return _result("Kustomize build.", result)


async def k8s_port_forward(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Start `kubectl port-forward` as a MANAGED process (not a one-shot op).

    The forward runs through the terminal process manager, so it is tree-killed,
    cancellable and visible in the Processes UI. A local port of 0 is resolved to a
    free one first.
    """
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if not model.name:
        return refusal("INPUT_INVALID", "a pod name is required")
    resource = model.name if "/" in model.name else f"pod/{model.name}"
    local_port = model.localPort
    if local_port:
        record = manager.ports.allocate(preferred=local_port, owner="port-forward")
        local_port = record.port
    result = await asyncio.to_thread(
        manager.managed_cli.port_forward,
        resource=resource, namespace=model.namespace, local_port=local_port,
        remote_port=model.remotePort or local_port, address=model.address,
    )
    if not result.ok:
        return refusal(result.code, result.reason)
    return f"Port-forward running on local port {result.local_port}.", {"status": "ok", **result.to_dict()}


async def k8s_logs_follow(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Start `kubectl logs -f` as a managed process (streamed, cancellable)."""
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    model = K8sOpInput(**{k: v for k, v in args.items() if v is not None})
    if not model.name:
        return refusal("INPUT_INVALID", "a pod name is required")
    result = await asyncio.to_thread(
        manager.managed_cli.logs_follow,
        name=model.name, namespace=model.namespace, container=model.container,
    )
    if not result.ok:
        return refusal(result.code, result.reason)
    return f"Following logs for {model.name}.", {"status": "ok", **result.to_dict()}


# ── Terraform ────────────────────────────────────────────────────────────────────


async def terraform_init(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "init")


async def terraform_validate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "validate")


async def terraform_fmt(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "fmt")


async def terraform_plan(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "plan")


async def terraform_output(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "output")


async def terraform_state(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _tf_op(args, ctx, "state")


async def terraform_apply(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    allowed, _decision, reason = manager.policy.decide("terraform.apply", authorized=bool(getattr(ctx, "authorized", False)))
    if not allowed:
        return _refusal("AUTHORIZATION_REQUIRED", reason)
    return await _tf_op(args, ctx, "apply")


async def terraform_destroy(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    allowed, _decision, reason = manager.policy.decide("terraform.destroy", authorized=bool(getattr(ctx, "authorized", False)))
    if not allowed:
        return _refusal("AUTHORIZATION_REQUIRED", reason)
    return await _tf_op(args, ctx, "destroy")


async def _tf_op(args: dict[str, Any], ctx: ToolContext, op: str) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal("WORKSPACE_UNBOUND", "there's no project open")
    payload = {k: v for k, v in args.items() if v is not None}
    payload.setdefault("dir", _terraform_dir(root, payload.pop("dir", "")))
    result = await asyncio.to_thread(manager.run_infrastructure, op, payload)
    return _result(f"Terraform {op}.", result)


def _terraform_dir(root: Any, requested: str) -> str:
    """The project-relative terraform directory (defaults to `terraform/` or root)."""
    from pathlib import Path

    base = Path(root)
    if requested:
        candidate = (base / requested).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            return "."
        return str(candidate.relative_to(base.resolve()))
    if (base / "terraform").is_dir():
        return "terraform"
    if list(base.glob("*.tf")):
        return "."
    return "."


# ── Cloud deploy ─────────────────────────────────────────────────────────────────


async def cloud_providers(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    data = manager.registry.deployments.describe()
    return f"{len(data)} cloud provider(s).", {"status": "ok", "providers": data}


async def deploy_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return _refusal("WORKSPACE_UNBOUND", "there's no project open")
    model = CloudDeployInput(**{k: v for k, v in args.items() if v is not None})
    # A production deploy requires explicit authorization.
    authorized = bool(getattr(ctx, "authorized", False)) or str(getattr(ctx, "autonomy", "")) == "approve_external"
    outcome = await asyncio.to_thread(
        manager.deployment.deploy, root,
        provider=model.provider, environment=model.environment, service=model.service,
        install=model.install, build=model.build, test=model.test, authorize=authorized,
        extra_args=model.args,
    )
    data = outcome.to_dict()
    if outcome.status == "failed":
        err = outcome.error or {}
        return _refusal(err.get("code", "DEPLOY_FAILED"), err.get("message", "the deployment failed"), deployment=data)
    return f"Deployment {outcome.status} to {model.provider or 'the provider'}.", {"status": "ok", "deployment": data}


async def deploy_promote(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Promote staging → production, with a health-gated rollback.

    Staging is always attempted first; crossing to production needs authorization
    (the `approve_external` profile or an explicit operator act). A failed
    production deploy is rolled back.
    """
    if not _grants_execute(ctx):
        return refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return refusal(*_NO_RUNTIME)
    root = _root(ctx)
    if root is None:
        return refusal("WORKSPACE_UNBOUND", "there's no project open")
    model = CloudDeployInput(**{k: v for k, v in args.items() if v is not None})
    authorized = bool(getattr(ctx, "authorized", False)) or str(getattr(ctx, "autonomy", "")) == "approve_external"
    data = await asyncio.to_thread(
        manager.deployment.promote, root,
        provider=model.provider, service=model.service,
        authorize_production=authorized, install=model.install, build=model.build,
        extra_args=model.args,
    )
    status = data.get("status")
    if status in ("staging_failed", "rolled_back"):
        return refusal(str(status).upper(), data.get("reason", "the promotion failed"), promotion=data)
    return f"Promotion: {status}.", {"status": "ok", "promotion": data}


async def deploy_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _cloud_op(args, ctx, "status")


async def deploy_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _cloud_op(args, ctx, "logs")


async def deploy_rollback(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = CloudDeployInput(**{k: v for k, v in args.items() if v is not None})
    result = await asyncio.to_thread(manager.deployment.rollback, provider=model.provider, service=model.service)
    return _result("Rolled back.", result)


async def deploy_delete(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_execute(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    allowed, _decision, reason = manager.policy.decide("cloud.delete", authorized=bool(getattr(ctx, "authorized", False)))
    if not allowed:
        return _refusal("AUTHORIZATION_REQUIRED", reason)
    model = CloudDeployInput(**{k: v for k, v in args.items() if v is not None})
    adapter = manager.registry.deployments.get(model.provider)
    if adapter is None:
        return _refusal("PROVIDER_UNAVAILABLE", f"{model.provider} isn't configured")
    result = await asyncio.to_thread(adapter.run_operation, "delete", {"service": model.service})
    return _result("Deleted the deployment.", result)


async def _cloud_op(args: dict[str, Any], ctx: ToolContext, op: str) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = CloudDeployInput(**{k: v for k, v in args.items() if v is not None})
    fn = manager.deployment.status if op == "status" else manager.deployment.logs
    result = await asyncio.to_thread(fn, provider=model.provider, service=model.service)
    return _result(f"Deploy {op}.", result)


K8S_INFRA_HANDLERS: dict[str, Any] = {
    "k8s_status": k8s_status, "k8s_get": k8s_get, "k8s_get_pods": k8s_get_pods,
    "k8s_describe": k8s_describe, "k8s_logs": k8s_logs, "k8s_apply": k8s_apply,
    "k8s_delete": k8s_delete, "k8s_scale": k8s_scale, "k8s_rollout": k8s_rollout,
    "k8s_exec": k8s_exec,
    "helm_list": helm_list, "helm_status": helm_status, "helm_install": helm_install,
    "helm_uninstall": helm_uninstall, "kustomize_build": kustomize_build,
    "k8s_port_forward": k8s_port_forward, "k8s_logs_follow": k8s_logs_follow,
    "terraform_init": terraform_init, "terraform_validate": terraform_validate,
    "terraform_fmt": terraform_fmt, "terraform_plan": terraform_plan,
    "terraform_apply": terraform_apply, "terraform_destroy": terraform_destroy,
    "terraform_output": terraform_output, "terraform_state": terraform_state,
    "cloud_providers": cloud_providers, "deploy_run": deploy_run,
    "deploy_promote": deploy_promote,
    "deploy_status": deploy_status, "deploy_logs": deploy_logs,
    "deploy_rollback": deploy_rollback, "deploy_delete": deploy_delete,
}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


K8S_INFRA_DESCRIPTIONS: dict[str, str] = {
    "k8s_status": "Report the current Kubernetes context. Read-only.",
    "k8s_get": "Get Kubernetes resources (pods, services, deployments, …). Read-only.",
    "k8s_get_pods": "List pods in a namespace. Read-only.",
    "k8s_describe": "Describe one Kubernetes resource. Read-only.",
    "k8s_logs": "Read a pod's logs. Read-only.",
    "k8s_apply": "Apply a Kubernetes manifest from the project.",
    "k8s_delete": "Delete a Kubernetes resource (needs approval).",
    "k8s_scale": "Scale a Kubernetes workload.",
    "k8s_rollout": "Inspect or act on a Kubernetes rollout. Read-only for status.",
    "k8s_exec": "Run a command inside a pod.",
    "helm_list": "List Helm releases. Read-only.",
    "helm_status": "Show a Helm release's status. Read-only.",
    "helm_install": "Install or upgrade a Helm release.",
    "helm_uninstall": "Uninstall a Helm release (needs approval).",
    "kustomize_build": "Render a kustomization to YAML. Read-only.",
    "k8s_port_forward": "Forward a local port to a pod as a managed process (visible + cancellable).",
    "k8s_logs_follow": "Follow a pod's logs as a managed process (streamed + cancellable).",
    "terraform_init": "Initialise a Terraform working directory.",
    "terraform_validate": "Check a Terraform configuration. Read-only.",
    "terraform_fmt": "Format Terraform files. Read-only.",
    "terraform_plan": "Plan Terraform changes (no apply). Read-only.",
    "terraform_apply": "Apply Terraform changes (needs approval).",
    "terraform_destroy": "Destroy Terraform-managed infrastructure (needs approval).",
    "terraform_output": "Read Terraform outputs. Read-only.",
    "terraform_state": "List Terraform state resources. Read-only.",
    "cloud_providers": "List the configured cloud deploy providers. Read-only.",
    "deploy_run": "Deploy the project to a cloud provider (validate→build→deploy→verify).",
    "deploy_promote": "Promote staging → production with a health-gated rollback (needs approval for production).",
    "deploy_status": "Report a cloud deployment's status. Read-only.",
    "deploy_logs": "Read a cloud deployment's logs. Read-only.",
    "deploy_rollback": "Roll back a cloud deployment.",
    "deploy_delete": "Delete a cloud deployment (needs approval).",
}

_K8S_OP_PROPS = {
    "kind": {"type": "string"}, "name": {"type": "string"}, "namespace": {"type": "string"},
    "selector": {"type": "string"}, "container": {"type": "string"}, "tail": {"type": "integer"},
    "previous": {"type": "boolean"}, "file": {"type": "string"}, "dryRun": {"type": "boolean"},
    "force": {"type": "boolean"}, "replicas": {"type": "integer"}, "action": {"type": "string"},
    "command": {"type": "array", "items": {"type": "string"}},
}
_INFRA_PROPS = {
    "dir": {"type": "string"}, "vars": {"type": "object"}, "target": {"type": "string"},
    "planFile": {"type": "string"}, "out": {"type": "string"}, "name": {"type": "string"},
    "autoApprove": {"type": "boolean"}, "upgrade": {"type": "boolean"},
    "reconfigure": {"type": "boolean"}, "check": {"type": "boolean"},
    "recursive": {"type": "boolean"}, "destroy": {"type": "boolean"},
}
_CLOUD_PROPS = {
    "provider": {"type": "string"}, "environment": {"type": "string"},
    "service": {"type": "string"}, "stack": {"type": "string"}, "template": {"type": "string"},
    "path": {"type": "string"}, "region": {"type": "string"}, "group": {"type": "string"},
    "install": {"type": "boolean"}, "build": {"type": "boolean"}, "test": {"type": "boolean"},
    "args": {"type": "object"},
}


def k8s_infra_schemas() -> dict[str, dict[str, Any]]:
    return {
        "k8s_status": _obj({}),
        "k8s_get": _obj(_K8S_OP_PROPS),
        "k8s_get_pods": _obj(_K8S_OP_PROPS),
        "k8s_describe": _obj(_K8S_OP_PROPS),
        "k8s_logs": _obj(_K8S_OP_PROPS),
        "k8s_apply": _obj(_K8S_OP_PROPS),
        "k8s_delete": _obj(_K8S_OP_PROPS),
        "k8s_scale": _obj(_K8S_OP_PROPS),
        "k8s_rollout": _obj(_K8S_OP_PROPS),
        "k8s_exec": _obj(_K8S_OP_PROPS),
        "helm_list": _obj({"namespace": {"type": "string"}}),
        "helm_status": _obj({"release": {"type": "string"}, "namespace": {"type": "string"}}, ["release"]),
        "helm_install": _obj({"release": {"type": "string"}, "chart": {"type": "string"}, "namespace": {"type": "string"},
                              "values": {"type": "string"}, "set": {"type": "object"}, "createNamespace": {"type": "boolean"},
                              "atomic": {"type": "boolean"}, "wait": {"type": "boolean"}}, ["release", "chart"]),
        "helm_uninstall": _obj({"release": {"type": "string"}, "namespace": {"type": "string"}, "keepHistory": {"type": "boolean"}}, ["release"]),
        "kustomize_build": _obj({"path": {"type": "string"}}),
        "k8s_port_forward": _obj({"name": {"type": "string"}, "namespace": {"type": "string"},
                                  "localPort": {"type": "integer"}, "remotePort": {"type": "integer"},
                                  "address": {"type": "string"}}, ["name"]),
        "k8s_logs_follow": _obj({"name": {"type": "string"}, "namespace": {"type": "string"},
                                 "container": {"type": "string"}}, ["name"]),
        "terraform_init": _obj(_INFRA_PROPS),
        "terraform_validate": _obj(_INFRA_PROPS),
        "terraform_fmt": _obj(_INFRA_PROPS),
        "terraform_plan": _obj(_INFRA_PROPS),
        "terraform_apply": _obj(_INFRA_PROPS),
        "terraform_destroy": _obj(_INFRA_PROPS),
        "terraform_output": _obj(_INFRA_PROPS),
        "terraform_state": _obj(_INFRA_PROPS),
        "cloud_providers": _obj({}),
        "deploy_run": _obj(_CLOUD_PROPS),
        "deploy_promote": _obj(_CLOUD_PROPS),
        "deploy_status": _obj(_CLOUD_PROPS),
        "deploy_logs": _obj(_CLOUD_PROPS),
        "deploy_rollback": _obj(_CLOUD_PROPS),
        "deploy_delete": _obj(_CLOUD_PROPS),
    }


__all__ = ["K8S_INFRA_DESCRIPTIONS", "K8S_INFRA_HANDLERS", "k8s_infra_schemas"]
