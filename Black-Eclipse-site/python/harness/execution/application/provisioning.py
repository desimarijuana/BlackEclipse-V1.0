"""Provider readiness — what is installed, what is logged in, what is missing.

The one real limitation of the Application Runtime is *host provisioning*: a
Kubernetes / Terraform / cloud operation needs its CLI installed AND
authenticated. A missing tool is honest at call time (`ENGINE_UNAVAILABLE`), but
it is far better to say so at boot, before the agent ever tries.

This module turns the registry's availability probes plus the provider's own
ambient-credential status into a single, non-secret readiness report:

    {
      "ready": bool,                       # every REQUIRED provider is usable
      "providers": [ {name, kind, installed, version, authenticated, missing, hint}, … ],
      "missing": ["kubectl", "terraform"],  # not installed
      "unauthenticated": ["aws"],           # installed but no credential found
      "hints": ["install kubectl …", …]     # a plain next step per gap
    }

It NEVER reads or returns a secret value; it only reports whether a declared
credential env NAME is set. A provider with no declared credential env reports
`authenticated: null` ("unknown") rather than a fabricated `true`/`false`.
"""

from __future__ import annotations

from typing import Any, Optional

#: A plain, one-line install hint per missing tool. Data, not branching UI. Only
#: tools Eclipse actually drives are listed; an unknown tool gets a generic hint.
_INSTALL_HINTS: dict[str, str] = {
    "kubectl": "Install kubectl: https://kubernetes.io/docs/tasks/tools/",
    "helm": "Install Helm: https://helm.sh/docs/intro/install/",
    "kustomize": "Install kustomize: https://kubectl.docs.kubernetes.io/installation/kustomize/",
    "terraform": "Install Terraform: https://developer.hashicorp.com/terraform/install",
    "docker": "Install Docker: https://docs.docker.com/get-docker/",
    "podman": "Install Podman: https://podman.io/docs/installation",
    "aws": "Install the AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html",
    "az": "Install the Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli",
    "gcloud": "Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install",
    "wrangler": "Install Wrangler: npm i -g wrangler",
    "vercel": "Install the Vercel CLI: npm i -g vercel",
    "railway": "Install the Railway CLI: npm i -g @railway/cli",
    "render": "Install the Render CLI: https://render.com/docs/cli",
    "node": "Install Node.js: https://nodejs.org",
    "python": "Install Python: https://www.python.org/downloads/",
    "git": "Install Git: https://git-scm.com/downloads",
}

_AUTH_HINTS: dict[str, str] = {
    "aws": "Configure AWS credentials: aws configure",
    "azure": "Sign in to Azure: az login",
    "gcp": "Sign in to Google Cloud: gcloud auth login",
    "cloudflare": "Set CLOUDFLARE_API_TOKEN (or run `wrangler login`)",
    "vercel": "Run `vercel login` (or set VERCEL_TOKEN)",
    "railway": "Run `railway login` (or set RAILWAY_TOKEN)",
    "render": "Set RENDER_API_KEY",
}

#: provider NAME → the CLI binary that is probed, so an install hint can be found
#: when the adapter's name (`azure`) differs from its binary (`az`).
_BINARY_OF: dict[str, str] = {
    "azure": "az", "gcp": "gcloud", "cloudflare": "wrangler",
    "docker": "docker", "podman": "podman",
}


def _install_hint(name: str) -> str:
    binary = _BINARY_OF.get(name, name)
    return _INSTALL_HINTS.get(binary) or _INSTALL_HINTS.get(name) or f"Install {name}"


def _adapter_entry(adapter: Any, *, kind: str, credential_status: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """One provider's readiness row. Never raises; an unprobeable adapter is unknown."""
    name = str(getattr(adapter, "name", "") or getattr(adapter, "binary", "?"))
    try:
        installed = bool(adapter.available())
    except Exception:  # noqa: BLE001 - an unavailable probe is "not installed"
        installed = False
    try:
        version = str(adapter.version() or "") if installed else ""
    except Exception:  # noqa: BLE001
        version = ""
    authenticated: Optional[bool] = None
    present: list[str] = []
    required: list[str] = []
    if credential_status is None and hasattr(adapter, "credential_status"):
        try:
            credential_status = adapter.credential_status()
        except Exception:  # noqa: BLE001
            credential_status = None
    if isinstance(credential_status, dict):
        authenticated = credential_status.get("configured")
        present = list(credential_status.get("present") or [])
        required = list(credential_status.get("required") or [])
    row: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "installed": installed,
        "version": version,
        "authenticated": authenticated,
        "credentialsPresent": present,
        "credentialsRequired": required,
        "missing": [] if installed else [name],
        "hint": "" if installed else _install_hint(name),
    }
    if installed and authenticated is False:
        row["hint"] = _AUTH_HINTS.get(name, f"Sign in to {name}")
    return row


def provider_readiness(registry: Any, *, required: Optional[list[str]] = None) -> dict[str, Any]:
    """Build the non-secret readiness report from a `RuntimeRegistry`.

    `required` names the providers the caller considers necessary (e.g. the ones
    a project declares). When omitted, `ready` means "every provider that is
    installed is also authenticated"; a not-installed provider is a gap, not a
    hard failure unless it was explicitly required.
    """
    providers: list[dict[str, Any]] = []
    for adapter in registry.containers._by_name.values():  # noqa: SLF001 - the registry is ours
        providers.append(_adapter_entry(adapter, kind="container"))
    for adapter in registry.orchestrators._by_name.values():  # noqa: SLF001
        providers.append(_adapter_entry(adapter, kind="orchestrator"))
    for adapter in registry.infrastructure._by_name.values():  # noqa: SLF001
        providers.append(_adapter_entry(adapter, kind="infrastructure"))
    for adapter in registry.deployments._by_name.values():  # noqa: SLF001
        providers.append(_adapter_entry(adapter, kind="deployment"))

    missing = sorted({row["name"] for row in providers if not row["installed"]})
    unauthenticated = sorted({row["name"] for row in providers if row["installed"] and row["authenticated"] is False})
    hints: list[str] = []
    seen_hints: set[str] = set()
    for row in providers:
        if row["hint"] and row["hint"] not in seen_hints:
            seen_hints.add(row["hint"])
            hints.append(row["hint"])

    if required:
        ready = all(
            next((r for r in providers if r["name"] == name), None) is not None
            and next(r for r in providers if r["name"] == name)["installed"]
            and next(r for r in providers if r["name"] == name)["authenticated"] is not False
            for name in required
        )
        required_missing = [name for name in required if name in missing]
    else:
        ready = not unauthenticated
        required_missing = []

    return {
        "ready": ready,
        "providers": providers,
        "missing": missing,
        "unauthenticated": unauthenticated,
        "requiredMissing": required_missing,
        "hints": hints,
    }


def required_providers_for(descriptor: Any) -> list[str]:
    """The providers a discovered application implies (from its files).

    A compose/Docker project implies `docker`; a `k8s/` or `helm/` folder implies
    `kubectl`/`helm`; a `*.tf` implies `terraform`. This is a hint for the
    readiness gate, never a hard requirement.
    """
    from pathlib import Path

    required: list[str] = []
    root = Path(getattr(descriptor, "path", "") or ".")
    if getattr(descriptor, "compose", False) or getattr(descriptor, "docker", False):
        required.append("docker")
    if root.is_dir():
        if (root / "k8s").is_dir() or (root / "kubernetes").is_dir() or list(root.glob("*.k8s.yaml")):
            required.append("kubectl")
        if (root / "helm").is_dir() or (root / "Chart.yaml").is_file() or list(root.glob("**/Chart.yaml")):
            required.append("helm")
        if list(root.glob("*.tf")) or (root / "terraform").is_dir():
            required.append("terraform")
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [name for name in required if not (name in seen or seen.add(name))]


__all__ = [
    "provider_readiness",
    "required_providers_for",
]
