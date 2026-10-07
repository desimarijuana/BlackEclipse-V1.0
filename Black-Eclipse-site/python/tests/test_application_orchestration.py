"""Orchestration / infrastructure / cloud adapters — unit tests.

Deterministic and offline: the CLI adapters are exercised through their TEST
SEAM (`runner=`) so no real kubectl/terraform/cloud binary is required. The
closed operation table, argument validation (injection resistance), availability
honesty and capability declarations are asserted directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.execution.application.cli_base import (
    CliAdapter,
    CliOperation,
    CliResult,
    is_safe_dns,
    is_safe_name,
    is_safe_value,
    validate_common,
)
from harness.execution.application.cloud import (
    AwsAdapter,
    AzureAdapter,
    CloudflareAdapter,
    GcpAdapter,
    RailwayAdapter,
    RenderAdapter,
    VercelAdapter,
    build_deployment_adapters,
)
from harness.execution.application.infrastructure import TerraformAdapter
from harness.execution.application.orchestrators import (
    HelmAdapter,
    KubernetesAdapter,
    KustomizeAdapter,
    build_orchestrator_adapters,
)
from harness.execution.application.registry import (
    CAP_DEPLOY,
    CAP_K8S_GET,
    CAP_TF_APPLY,
    ALL_CAPABILITIES,
)


def _runner(argv: list[str], timeout_s: int) -> CliResult:
    """A canned runner: echoes the argv as JSON so a test can assert on it."""
    return CliResult(ok=True, exit_code=0, argv=list(argv), output='{"ok": true}',
                     code="OK", duration_ms=1)


# ── the shared base ─────────────────────────────────────────────────────────────


def test_safe_value_rejects_shell_metacharacters():
    for bad in ("a; rm -rf /", "a && b", "a | b", "a`whoami`", "$(x)", "a\nb", "a>b", "a<b"):
        assert not is_safe_value(bad), bad
    for good in ("nginx:1.25", "registry.io/team/app@sha256", "web-1", "app=1", "a/b/c.yaml"):
        assert is_safe_value(good), good


def test_safe_name_and_dns():
    assert is_safe_name("web-1")
    assert not is_safe_name("-bad")
    assert is_safe_dns("my-service")
    assert not is_safe_dns("My_Service")


def test_unknown_operation_is_refused():
    kubectl = KubernetesAdapter(runner=_runner)
    result = kubectl.run_operation("not-a-real-op", {})
    assert result.ok is False and result.code == "UNKNOWN_OPERATION"


def test_engine_unavailable_is_honest(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    kubectl = KubernetesAdapter()
    assert kubectl.available() is False
    result = kubectl.run_operation("get", {"kind": "pods"})
    assert result.ok is False and result.code == "ENGINE_UNAVAILABLE"


def test_capability_contract_is_closed():
    for adapter in build_orchestrator_adapters() + [TerraformAdapter()] + build_deployment_adapters():
        assert getattr(adapter, "capabilities", frozenset())
        for capability in adapter.capabilities:
            assert capability in ALL_CAPABILITIES, f"{adapter.name}: {capability}"


# ── Kubernetes ──────────────────────────────────────────────────────────────────


def test_kubectl_get_builds_json_argv():
    kubectl = KubernetesAdapter(runner=_runner)
    result = kubectl.run_operation("get", {"kind": "pods", "namespace": "prod", "selector": "app=web"})
    assert result.ok
    assert result.argv[1:] == ["get", "pods", "-l", "app=web", "-n", "prod", "-o", "json"]
    assert result.data == {"ok": True}


def test_kubectl_rejects_injected_pod_name():
    kubectl = KubernetesAdapter(runner=_runner)
    result = kubectl.run_operation("logs", {"name": "web; rm -rf /"})
    assert result.ok is False and result.code == "INVALID_NAME"


def test_kubectl_apply_requires_a_file():
    kubectl = KubernetesAdapter(runner=_runner)
    assert kubectl.run_operation("apply", {}).code == "INPUT_INVALID"
    assert kubectl.run_operation("apply", {"file": "k8s/deploy.yaml"}).ok
    assert kubectl.run_operation("apply", {"file": "a;b"}).code == "INVALID_ARG"


def test_kubectl_scale_bounds_replicas():
    kubectl = KubernetesAdapter(runner=_runner)
    assert kubectl.run_operation("scale", {"kind": "deployment", "name": "web", "replicas": 3}).ok
    assert kubectl.run_operation("scale", {"kind": "deployment", "name": "web", "replicas": 99999}).code == "INVALID_ARG"


def test_kubectl_delete_is_critical_risk():
    kubectl = KubernetesAdapter(runner=_runner)
    assert kubectl.operations["delete"].risk == "CRITICAL"
    assert kubectl.operations["get"].read_only is True


def test_kubectl_exec_rejects_injection_in_command():
    kubectl = KubernetesAdapter(runner=_runner)
    result = kubectl.run_operation("exec", {"name": "web", "command": ["sh", "-c", "echo pwned; rm -rf /"]})
    assert result.ok is False


# ── Helm / Kustomize ─────────────────────────────────────────────────────────────


def test_helm_install_requires_release_and_chart():
    helm = HelmAdapter(runner=_runner)
    assert helm.run_operation("install", {"release": "app"}).code == "INVALID_ARG"
    assert helm.run_operation("install", {"release": "app", "chart": "oci://charts/x"}).ok


def test_helm_uninstall_is_critical():
    helm = HelmAdapter(runner=_runner)
    assert helm.operations["uninstall"].risk == "CRITICAL"


def test_kustomize_build_is_read_only():
    kustomize = KustomizeAdapter(runner=_runner)
    assert kustomize.operations["build"].read_only is True
    assert kustomize.run_operation("build", {"path": "k8s/overlays/prod"}).ok


# ── Terraform ────────────────────────────────────────────────────────────────────


def test_terraform_apply_and_destroy_are_critical():
    tf = TerraformAdapter(runner=_runner)
    assert tf.operations["apply"].risk == "CRITICAL"
    assert tf.operations["destroy"].risk == "CRITICAL"
    assert tf.operations["plan"].read_only is True
    assert tf.operations["validate"].read_only is True


def test_terraform_chdir_and_vars():
    tf = TerraformAdapter(runner=_runner)
    result = tf.run_operation("plan", {"dir": "terraform", "vars": {"region": "us-east-1"}})
    assert result.ok
    assert result.argv[1:] == ["-chdir", "terraform", "plan", "-input=false", "-no-color", "-var", "region=us-east-1"]


def test_terraform_rejects_bad_var_key():
    tf = TerraformAdapter(runner=_runner)
    result = tf.run_operation("plan", {"vars": {"bad key": "x"}})
    assert result.ok is False and result.code == "INVALID_ARG"


def test_terraform_output_parses_json():
    def runner(argv, timeout_s):
        return CliResult(ok=True, exit_code=0, argv=list(argv), output='{"endpoint": {"value": "https://x"}}')

    tf = TerraformAdapter(runner=runner)
    result = tf.run_operation("output", {})
    assert result.data == {"endpoint": {"value": "https://x"}}


# ── cloud providers ──────────────────────────────────────────────────────────────


def test_all_cloud_providers_declare_the_common_surface():
    for adapter in build_deployment_adapters():
        assert CAP_DEPLOY in adapter.capabilities, adapter.name
        assert "deploy" in adapter.operations
        assert "status" in adapter.operations
        assert "logs" in adapter.operations
        assert "rollback" in adapter.operations
        assert "delete" in adapter.operations
        assert adapter.operations["delete"].risk == "CRITICAL"


def test_aws_deploy_requires_a_stack():
    aws = AwsAdapter(runner=_runner)
    assert aws.run_operation("deploy", {}).code == "INVALID_ARG"
    result = aws.run_operation("deploy", {"stack": "web", "template": "infra/stack.yaml"})
    assert result.ok
    assert result.argv[1:] == ["cloudformation", "deploy", "--stack-name", "web",
                               "--template-file", "infra/stack.yaml", "--capabilities", "CAPABILITY_IAM"]


def test_vercel_delete_is_critical_and_validated():
    vercel = VercelAdapter(runner=_runner)
    assert vercel.operations["delete"].risk == "CRITICAL"
    assert vercel.run_operation("delete", {}).code == "INVALID_ARG"


def test_render_deploy_requires_a_service():
    render = RenderAdapter(runner=_runner)
    assert render.run_operation("deploy", {}).code == "INVALID_ARG"
    assert render.run_operation("deploy", {"service": "web"}).ok


def test_cloud_credential_status_reports_names_not_values(monkeypatch):
    monkeypatch.setenv("VERCEL_TOKEN", "super-secret")
    vercel = VercelAdapter(runner=_runner)
    status = vercel.credential_status()
    assert status["present"] == ["VERCEL_TOKEN"]
    assert "super-secret" not in str(status)
    assert status["required"] == ["VERCEL_TOKEN"]


def test_cloudflare_deploy_validates_env_name():
    cloudflare = CloudflareAdapter(runner=_runner)
    assert cloudflare.run_operation("deploy", {"envName": "production"}).ok
    assert cloudflare.run_operation("deploy", {"envName": "bad name!"}).code == "INVALID_NAME"
