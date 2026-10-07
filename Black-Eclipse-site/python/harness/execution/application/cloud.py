"""Cloud provider adapters — AWS, Azure, GCP, Cloudflare, Vercel, Railway, Render.

Each is a `CloudProviderAdapter` implementation: a `CliAdapter` with a CLOSED
operation table, so the model never supplies an executable, a flag or a shell
fragment. Every call runs through the ONE sandbox with a scrubbed environment —
credentials reach a provider CLI only through the provider's OWN standard
mechanism (ambient config/profile/instance role); this layer never passes a secret
argument and never reads one into a response.

The common operations are `deploy`, `status`, `logs`, `rollback` and `delete`.
`delete` and a `production` deploy are CRITICAL and require authorization.
Provider-specific behaviour lives in the adapter's operation table, never in the
agent planner.

Availability is honest: a provider whose CLI is absent reports
`ENGINE_UNAVAILABLE`, never a fabricated deployment.
"""

from __future__ import annotations

from typing import Any, Optional

from .cli_base import CliAdapter, CliOperation, is_safe_env_key, is_safe_name, is_safe_value
from .registry import (
    CAP_DEPLOY,
    CAP_DEPLOY_DELETE,
    CAP_DEPLOY_LOGS,
    CAP_DEPLOY_ROLLBACK,
    CAP_DEPLOY_STATUS,
)


def _validate_resource(args: dict[str, Any], fields: tuple[str, ...] = ("name", "service", "app", "region")) -> Optional[tuple[str, str]]:
    for field_name in fields:
        if args.get(field_name) is not None and not is_safe_name(str(args[field_name])):
            return ("INVALID_NAME", f"{field_name!r} is not a valid name")
    for key in (args.get("env") or {}):
        if not is_safe_env_key(str(key)):
            return ("INVALID_ARG", "'env' has an invalid key")
    return None


class CloudProviderCliAdapter(CliAdapter):
    """Base for a cloud provider whose common surface is a deploy CLI."""

    kind = "deployment"
    capabilities = frozenset(
        {CAP_DEPLOY, CAP_DEPLOY_STATUS, CAP_DEPLOY_LOGS, CAP_DEPLOY_ROLLBACK, CAP_DEPLOY_DELETE}
    )
    #: Environment variable NAMES a provider commonly needs. Used only to REPORT
    #: whether they are present (never their value).
    credential_env: tuple[str, ...] = ()

    def credential_status(self) -> dict[str, Any]:
        """Whether the provider's declared credential env vars are SET (not their values)."""
        import os

        present = [name for name in self.credential_env if os.environ.get(name)]
        return {
            "provider": self.name,
            "configured": bool(present) if self.credential_env else None,
            "present": present,
            "required": list(self.credential_env),
        }


class AwsAdapter(CloudProviderCliAdapter):
    name = "aws"
    binary = "aws"
    credential_env = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE", "AWS_REGION")

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("--version",), risk="SAFE", timeout_s=15, read_only=True),
        "identity": CliOperation(
            name="identity", subcommand=("sts", "get-caller-identity"),
            json_output=("--output", "json"), json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
        "status": CliOperation(
            name="status", subcommand=("cloudformation", "describe-stacks"),
            argv=lambda a: [*(["--stack-name", str(a["stack"])] if a.get("stack") else [])],
            validator=lambda a: _validate_resource(a, ("stack", "region")),
            json_output=("--output", "json"), json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("cloudformation", "deploy"),
            argv=lambda a: [
                "--stack-name", str(a["stack"]),
                *(["--template-file", str(a["template"])] if a.get("template") else []),
                *(["--capabilities", str(a["capabilities"])] if a.get("capabilities") else ["--capabilities", "CAPABILITY_IAM"]),
                *(["--no-fail-on-empty-changeset"] if a.get("noFailOnEmpty") else []),
            ],
            validator=lambda a: (None if is_safe_name(str(a.get("stack") or "")) and
                                 (a.get("template") is None or is_safe_value(str(a["template"])))
                                 else ("INVALID_ARG", "a valid stack and template are required")),
            risk="HIGH", timeout_s=3600,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logs", "tail"),
            argv=lambda a: [str(a["group"]), *(["--since", str(a["since"])] if a.get("since") else []),
                            *(["--format", "short"] if a.get("short") else [])],
            validator=lambda a: (None if is_safe_value(str(a.get("group") or "")) else ("INVALID_ARG", "a log group is required")),
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("cloudformation", "rollback-stack"),
            argv=lambda a: ["--stack-name", str(a["stack"])],
            validator=lambda a: (None if is_safe_name(str(a.get("stack") or "")) else ("INVALID_NAME", "a stack is required")),
            risk="HIGH", timeout_s=600,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("cloudformation", "delete-stack"),
            argv=lambda a: ["--stack-name", str(a["stack"])],
            validator=lambda a: (None if is_safe_name(str(a.get("stack") or "")) else ("INVALID_NAME", "a stack is required")),
            risk="CRITICAL", timeout_s=1800,
        ),
    }


class AzureAdapter(CloudProviderCliAdapter):
    name = "azure"
    binary = "az"
    credential_env = ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID")

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("version",), json_output=("--output", "json"),
                                json_parse=True, risk="SAFE", timeout_s=15, read_only=True),
        "identity": CliOperation(
            name="identity", subcommand=("account", "show"),
            json_output=("--output", "json"), json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
        "status": CliOperation(
            name="status", subcommand=("group", "show"),
            argv=lambda a: ["--name", str(a["group"])],
            validator=lambda a: (None if is_safe_name(str(a.get("group") or "")) else ("INVALID_NAME", "a group is required")),
            json_output=("--output", "json"), json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("deployment", "group", "create"),
            argv=lambda a: ["--resource-group", str(a["group"]), "--template-file", str(a["template"]),
                            *(["--parameters", str(a["parameters"])] if a.get("parameters") else [])],
            validator=lambda a: (None if is_safe_name(str(a.get("group") or "")) and is_safe_value(str(a.get("template") or ""))
                                 else ("INVALID_ARG", "a valid group and template are required")),
            risk="HIGH", timeout_s=3600,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("monitor", "log", "show"),
            argv=lambda a: ["--resource", str(a["resource"])],
            validator=lambda a: (None if is_safe_value(str(a.get("resource") or "")) else ("INVALID_ARG", "a resource is required")),
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("deployment", "group", "cancel"),
            argv=lambda a: ["--resource-group", str(a["group"]), "--name", str(a["deployment"])],
            validator=lambda a: (None if is_safe_name(str(a.get("group") or "")) and is_safe_name(str(a.get("deployment") or ""))
                                 else ("INVALID_NAME", "group and deployment are required")),
            risk="HIGH", timeout_s=300,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("group", "delete"),
            argv=lambda a: ["--name", str(a["group"]), "--yes"],
            validator=lambda a: (None if is_safe_name(str(a.get("group") or "")) else ("INVALID_NAME", "a group is required")),
            risk="CRITICAL", timeout_s=1800,
        ),
    }


class GcpAdapter(CloudProviderCliAdapter):
    name = "gcp"
    binary = "gcloud"
    credential_env = ("GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_CORE_PROJECT", "GOOGLE_CLOUD_PROJECT")

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("version",), risk="SAFE", timeout_s=15, read_only=True),
        "identity": CliOperation(
            name="identity", subcommand=("auth", "list", "--filter", "status:ACTIVE", "--format", "json"),
            json_parse=True, risk="LOW", timeout_s=30, read_only=True,
        ),
        "status": CliOperation(
            name="status", subcommand=("run", "services", "describe"),
            argv=lambda a: [str(a["service"]), "--format", "json"],
            validator=lambda a: (None if is_safe_name(str(a.get("service") or "")) else ("INVALID_NAME", "a service is required")),
            json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("run", "deploy"),
            argv=lambda a: [str(a["service"]), "--source", str(a.get("source") or "."),
                            *(["--region", "us-central1"] if not a.get("region") else ["--region", str(a["region"])]),
                            "--quiet"],
            validator=lambda a: (None if is_safe_name(str(a.get("service") or "")) and is_safe_value(str(a.get("source") or "."))
                                 else ("INVALID_ARG", "a valid service and source are required")),
            risk="HIGH", timeout_s=3600,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logging", "read"),
            argv=lambda a: [str(a["filter"]), "--limit", str(int(a.get("limit") or 100)), "--format", "json"],
            validator=lambda a: (None if is_safe_value(str(a.get("filter") or "")) else ("INVALID_ARG", "a filter is required")),
            json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("run", "services", "update-traffic"),
            argv=lambda a: [str(a["service"]), "--to-revisions", str(a["revision"])],
            validator=lambda a: (None if is_safe_name(str(a.get("service") or "")) and is_safe_value(str(a.get("revision") or ""))
                                 else ("INVALID_NAME", "service and revision are required")),
            risk="HIGH", timeout_s=600,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("run", "services", "delete"),
            argv=lambda a: [str(a["service"]), "--quiet"],
            validator=lambda a: (None if is_safe_name(str(a.get("service") or "")) else ("INVALID_NAME", "a service is required")),
            risk="CRITICAL", timeout_s=900,
        ),
    }


class CloudflareAdapter(CloudProviderCliAdapter):
    name = "cloudflare"
    binary = "wrangler"
    credential_env = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("--version",), risk="SAFE", timeout_s=15, read_only=True),
        "status": CliOperation(
            name="status", subcommand=("deployments", "list"),
            json_output=("--json",), json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("deploy",),
            argv=lambda a: [*(["--env", str(a["envName"])] if a.get("envName") else [])],
            validator=lambda a: _validate_resource(a, ("envName",)),
            risk="HIGH", timeout_s=1800,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("tail",),
            argv=lambda a: [*(["--format", "json"] if a.get("json") else [])],
            risk="LOW", timeout_s=30, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("rollback",),
            argv=lambda a: [*([str(a["deployment"])] if a.get("deployment") else [])],
            risk="HIGH", timeout_s=600,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("delete",),
            argv=lambda a: [*(["--name", str(a["name"])] if a.get("name") else [])],
            risk="CRITICAL", timeout_s=600,
        ),
    }


class VercelAdapter(CloudProviderCliAdapter):
    name = "vercel"
    binary = "vercel"
    credential_env = ("VERCEL_TOKEN",)

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("--version",), risk="SAFE", timeout_s=15, read_only=True),
        "status": CliOperation(
            name="status", subcommand=("ls",),
            json_output=("--json",), json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("deploy",),
            argv=lambda a: ["--yes",
                            *(["--prod"] if a.get("prod") else []),
                            *([str(a["path"])] if a.get("path") else [])],
            validator=lambda a: _validate_resource(a, ("path",)),
            risk="HIGH", timeout_s=1800,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logs",),
            argv=lambda a: [*([str(a["deployment"])] if a.get("deployment") else [])],
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("rollback",),
            argv=lambda a: [str(a["deployment"])],
            validator=lambda a: (None if is_safe_value(str(a.get("deployment") or "")) else ("INVALID_ARG", "a deployment is required")),
            risk="HIGH", timeout_s=600,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("remove",),
            argv=lambda a: [str(a["deployment"]), "--yes"],
            validator=lambda a: (None if is_safe_value(str(a.get("deployment") or "")) else ("INVALID_ARG", "a deployment is required")),
            risk="CRITICAL", timeout_s=600,
        ),
    }


class RailwayAdapter(CloudProviderCliAdapter):
    name = "railway"
    binary = "railway"
    credential_env = ("RAILWAY_TOKEN", "RAILWAY_API_TOKEN")

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("--version",), risk="SAFE", timeout_s=15, read_only=True),
        "status": CliOperation(name="status", subcommand=("status",), risk="LOW", timeout_s=60, read_only=True),
        "deploy": CliOperation(
            name="deploy", subcommand=("up",),
            argv=lambda a: [*(["--service", str(a["service"])] if a.get("service") else []),
                            *(["--detach"] if a.get("detach") else []), "--ci"],
            validator=lambda a: _validate_resource(a, ("service",)),
            risk="HIGH", timeout_s=1800,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logs",),
            argv=lambda a: [*(["-s", str(a["service"])] if a.get("service") else [])],
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("redeploy",),
            argv=lambda a: [*(["-s", str(a["service"])] if a.get("service") else []),
                            *(["--yes"] if a.get("yes") else [])],
            risk="HIGH", timeout_s=900,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("down",),
            argv=lambda a: [*(["-s", str(a["service"])] if a.get("service") else []), "--yes"],
            risk="CRITICAL", timeout_s=600,
        ),
    }


class RenderAdapter(CloudProviderCliAdapter):
    name = "render"
    binary = "render"
    credential_env = ("RENDER_API_KEY",)

    operations: dict[str, CliOperation] = {
        "version": CliOperation(name="version", subcommand=("--version",), risk="SAFE", timeout_s=15, read_only=True),
        "status": CliOperation(
            name="status", subcommand=("services",),
            argv=lambda a: [*([str(a["service"])] if a.get("service") else [])],
            validator=lambda a: _validate_resource(a, ("service",)),
            json_output=("--output", "json"), json_parse=True, risk="LOW", timeout_s=60, read_only=True,
        ),
        "deploy": CliOperation(
            name="deploy", subcommand=("deploys", "create"),
            argv=lambda a: [str(a["service"]), *(["--wait"] if a.get("wait") else [])],
            validator=lambda a: (None if is_safe_value(str(a.get("service") or "")) else ("INVALID_ARG", "a service is required")),
            risk="HIGH", timeout_s=1800,
        ),
        "logs": CliOperation(
            name="logs", subcommand=("logs",),
            argv=lambda a: [str(a["service"]), *(["--limit", str(int(a["limit"]))] if a.get("limit") else [])],
            validator=lambda a: (None if is_safe_value(str(a.get("service") or "")) else ("INVALID_ARG", "a service is required")),
            risk="LOW", timeout_s=60, read_only=True,
        ),
        "rollback": CliOperation(
            name="rollback", subcommand=("deploys", "rollback"),
            argv=lambda a: [str(a["service"]), *([str(a["deploy"])] if a.get("deploy") else [])],
            validator=lambda a: (None if is_safe_value(str(a.get("service") or "")) else ("INVALID_ARG", "a service is required")),
            risk="HIGH", timeout_s=900,
        ),
        "delete": CliOperation(
            name="delete", subcommand=("services", "delete"),
            argv=lambda a: [str(a["service"]), "--confirm"],
            validator=lambda a: (None if is_safe_value(str(a.get("service") or "")) else ("INVALID_ARG", "a service is required")),
            risk="CRITICAL", timeout_s=600,
        ),
    }


def build_deployment_adapters() -> list[CliAdapter]:
    return [AwsAdapter(), AzureAdapter(), GcpAdapter(), CloudflareAdapter(),
            VercelAdapter(), RailwayAdapter(), RenderAdapter()]


__all__ = [
    "AwsAdapter",
    "AzureAdapter",
    "CloudProviderCliAdapter",
    "CloudflareAdapter",
    "GcpAdapter",
    "RailwayAdapter",
    "RenderAdapter",
    "VercelAdapter",
    "build_deployment_adapters",
]
