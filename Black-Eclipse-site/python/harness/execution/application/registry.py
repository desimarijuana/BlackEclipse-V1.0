"""The runtime/provider registries — one place every adapter is declared.

The agent must never be tightly coupled to Docker or npm. This module owns the
central registry the runtime manager consults:

    RuntimeRegistry
    ├── PackageManagerRegistry     (npm, pnpm, yarn, bun, pip, uv, poetry, cargo, go, maven, gradle, …)
    ├── ContainerRuntimeRegistry   (DockerAdapter, PodmanAdapter)
    ├── ComposeRegistry            (DockerComposeAdapter, PodmanComposeAdapter)
    ├── OrchestratorRegistry       (future: Kubernetes)
    ├── InfrastructureRegistry     (future: Terraform)
    └── DeploymentRegistry         (future: AWS/Azure/GCP/Cloudflare/Vercel/Railway/Render)

Each adapter declares CAPABILITIES — a closed set of the operations it actually
implements — so a caller never asks an adapter for a meaningless operation. The
`Capability` set is the contract; the `supports()` helper is the only way to test
it. Adapters that are not installed report `available() == False` honestly and
are never silently substituted.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .models import (
    ApplicationDescriptor,
    HealthCheck,
    HealthResult,
    PortRecord,
    RuntimeDiagnosis,
)


class Capability(str):
    """Known adapter capabilities. A `str` subclass so it serializes plainly."""


# The closed capability vocabulary. Adapters declare the subset they implement.
CAP_DETECT = "detect"
CAP_INSTALL = "install"
CAP_INSTALL_PACKAGE = "install_package"
CAP_REMOVE_PACKAGE = "remove_package"
CAP_UPDATE_PACKAGE = "update_package"
CAP_LIST_DEPENDENCIES = "list_dependencies"
CAP_RUN_SCRIPT = "run_script"
CAP_BUILD = "build"
CAP_TEST = "test"
CAP_LINT = "lint"
CAP_AUDIT = "audit"
CAP_VERSION = "version"

CAP_CONTAINER_BUILD = "container.build"
CAP_CONTAINER_RUN = "container.run"
CAP_CONTAINER_LIFECYCLE = "container.lifecycle"
CAP_CONTAINER_EXEC = "container.exec"
CAP_CONTAINER_LOGS = "container.logs"
CAP_CONTAINER_INSPECT = "container.inspect"
CAP_CONTAINER_STATS = "container.stats"
CAP_CONTAINER_LIST = "container.list"
CAP_CONTAINER_REMOVE = "container.remove"
CAP_CONTAINER_IMAGES = "container.images"

CAP_COMPOSE_VALIDATE = "compose.validate"
CAP_COMPOSE_CONFIG = "compose.config"
CAP_COMPOSE_UP = "compose.up"
CAP_COMPOSE_DOWN = "compose.down"
CAP_COMPOSE_LIFECYCLE = "compose.lifecycle"
CAP_COMPOSE_LOGS = "compose.logs"
CAP_COMPOSE_EXEC = "compose.exec"
CAP_COMPOSE_PS = "compose.ps"

CAP_HEALTH = "health"
CAP_PORTS = "ports"

# ── Orchestration (Kubernetes / Helm / Kustomize) ──────────────────────────────
CAP_K8S_GET = "k8s.get"
CAP_K8S_APPLY = "k8s.apply"
CAP_K8S_DELETE = "k8s.delete"
CAP_K8S_LOGS = "k8s.logs"
CAP_K8S_EXEC = "k8s.exec"
CAP_K8S_SCALE = "k8s.scale"
CAP_K8S_ROLLOUT = "k8s.rollout"
CAP_K8S_DESCRIBE = "k8s.describe"

# ── Helm / Kustomize ────────────────────────────────────────────────────────────
CAP_HELM_LIST = "helm.list"
CAP_HELM_STATUS = "helm.status"
CAP_HELM_TEMPLATE = "helm.template"
CAP_HELM_INSTALL = "helm.install"
CAP_HELM_UNINSTALL = "helm.uninstall"
CAP_HELM_REPO = "helm.repo"
CAP_KUSTOMIZE_BUILD = "kustomize.build"

# ── Infrastructure (Terraform / Pulumi) ────────────────────────────────────────
CAP_TF_INIT = "terraform.init"
CAP_TF_VALIDATE = "terraform.validate"
CAP_TF_PLAN = "terraform.plan"
CAP_TF_APPLY = "terraform.apply"
CAP_TF_DESTROY = "terraform.destroy"
CAP_TF_OUTPUT = "terraform.output"
CAP_TF_STATE = "terraform.state"
CAP_TF_FMT = "terraform.fmt"

# ── Cloud providers (AWS/Azure/GCP/Cloudflare/Vercel/Railway/Render) ────────────
CAP_DEPLOY = "cloud.deploy"
CAP_DEPLOY_STATUS = "cloud.status"
CAP_DEPLOY_LOGS = "cloud.logs"
CAP_DEPLOY_ROLLBACK = "cloud.rollback"
CAP_DEPLOY_DELETE = "cloud.delete"

ALL_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        CAP_DETECT, CAP_INSTALL, CAP_INSTALL_PACKAGE, CAP_REMOVE_PACKAGE,
        CAP_UPDATE_PACKAGE, CAP_LIST_DEPENDENCIES, CAP_RUN_SCRIPT, CAP_BUILD,
        CAP_TEST, CAP_LINT, CAP_AUDIT, CAP_VERSION, CAP_CONTAINER_BUILD,
        CAP_CONTAINER_RUN, CAP_CONTAINER_LIFECYCLE, CAP_CONTAINER_EXEC,
        CAP_CONTAINER_LOGS, CAP_CONTAINER_INSPECT, CAP_CONTAINER_STATS,
        CAP_CONTAINER_LIST, CAP_CONTAINER_REMOVE, CAP_CONTAINER_IMAGES,
        CAP_COMPOSE_VALIDATE, CAP_COMPOSE_CONFIG, CAP_COMPOSE_UP, CAP_COMPOSE_DOWN,
        CAP_COMPOSE_LIFECYCLE, CAP_COMPOSE_LOGS, CAP_COMPOSE_EXEC, CAP_COMPOSE_PS,
        CAP_HEALTH, CAP_PORTS,
        CAP_K8S_GET, CAP_K8S_APPLY, CAP_K8S_DELETE, CAP_K8S_LOGS, CAP_K8S_EXEC,
        CAP_K8S_SCALE, CAP_K8S_ROLLOUT, CAP_K8S_DESCRIBE,
        CAP_HELM_LIST, CAP_HELM_STATUS, CAP_HELM_TEMPLATE, CAP_HELM_INSTALL,
        CAP_HELM_UNINSTALL, CAP_HELM_REPO, CAP_KUSTOMIZE_BUILD,
        CAP_TF_INIT, CAP_TF_VALIDATE, CAP_TF_PLAN, CAP_TF_APPLY, CAP_TF_DESTROY,
        CAP_TF_OUTPUT, CAP_TF_STATE, CAP_TF_FMT,
        CAP_DEPLOY, CAP_DEPLOY_STATUS, CAP_DEPLOY_LOGS, CAP_DEPLOY_ROLLBACK,
        CAP_DEPLOY_DELETE,
    }
)


def supports(adapter: Any, capability: str) -> bool:
    """Whether `adapter` declares `capability`. The ONE capability test."""
    caps = getattr(adapter, "capabilities", ()) or ()
    return capability in caps


# ── Package manager contract ──────────────────────────────────────────────────


@runtime_checkable
class PackageManagerAdapter(Protocol):
    """A package manager (npm/pip/cargo/…). Methods are optional by capability."""

    name: str
    language: str
    capabilities: frozenset[str]

    def detect(self, root: Any, descriptor: ApplicationDescriptor) -> bool:
        """Whether this manager fits the project's declared lockfile/manifest."""
        ...

    def available(self) -> bool:
        """Whether the manager's executable is present on this machine."""
        ...

    def version(self) -> str:
        """The manager's version string, or "" when unavailable."""
        ...


# ── Container runtime contract ─────────────────────────────────────────────────


@runtime_checkable
class ContainerRuntimeAdapter(Protocol):
    """A container engine (Docker, Podman). One abstraction, two engines."""

    name: str
    capabilities: frozenset[str]

    def detect(self) -> bool:
        ...

    def available(self) -> bool:
        ...

    def version(self) -> str:
        ...


@runtime_checkable
class ComposeAdapter(Protocol):
    """A compose front end on top of a container runtime."""

    name: str
    capabilities: frozenset[str]

    def available(self) -> bool:
        ...


# ── Orchestration / infrastructure / cloud contracts ────────────────────────────
#
# These protocols are the extension seam for Kubernetes, Terraform and cloud
# providers. They are now IMPLEMENTED by real adapters (`orchestrators.py`,
# `infrastructure.py`, `cloud.py`) on top of the shared `CliAdapter`. An adapter
# that implements one only needs `name` + `capabilities` + `available()` to be
# registerable; the runtime engine never hard-codes a Kubernetes, Terraform or
# cloud concept. A new provider is one more class, not a new engine.


@runtime_checkable
class OrchestratorAdapter(Protocol):
    """Kubernetes / Helm / Kustomize."""

    name: str
    capabilities: frozenset[str]

    def available(self) -> bool:
        ...

    def run_operation(self, operation: str, args: Any = None) -> Any:
        ...


@runtime_checkable
class InfrastructureAdapter(Protocol):
    """Terraform / Pulumi."""

    name: str
    capabilities: frozenset[str]

    def available(self) -> bool:
        ...

    def run_operation(self, operation: str, args: Any = None) -> Any:
        ...


@runtime_checkable
class CloudProviderAdapter(Protocol):
    """AWS / Azure / GCP / Cloudflare / Vercel / Railway / Render."""

    name: str
    capabilities: frozenset[str]

    def available(self) -> bool:
        ...

    def run_operation(self, operation: str, args: Any = None) -> Any:
        ...


# ── Registries ────────────────────────────────────────────────────────────────


class PackageManagerRegistry:
    """The process-wide table of package-manager adapters, keyed by name."""

    def __init__(self) -> None:
        self._by_name: dict[str, PackageManagerAdapter] = {}
        self._by_language: dict[str, list[str]] = {}

    def register(self, adapter: PackageManagerAdapter) -> None:
        name = str(adapter.name).casefold()
        self._by_name[name] = adapter
        self._by_language.setdefault(str(adapter.language).casefold(), []).append(name)

    def get(self, name: str) -> Optional[PackageManagerAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def for_language(self, language: str) -> list[PackageManagerAdapter]:
        return [self._by_name[n] for n in self._by_language.get(str(language or "").casefold(), [])]

    def detect(self, root: Any, descriptor: ApplicationDescriptor) -> Optional[PackageManagerAdapter]:
        """The adapter that fits the project. A DECLARED or lockfile manager is
        authoritative: if the project declares pnpm (or ships `pnpm-lock.yaml`),
        the pnpm adapter is returned even when pnpm is absent, so the caller
        reports the honest "pnpm is unavailable" instead of silently switching."""
        declared = str(getattr(descriptor, "package_manager", "") or "").casefold()
        if declared:
            adapter = self._by_name.get(declared)
            if adapter is not None:
                return adapter
        candidates: list[PackageManagerAdapter] = []
        for adapter in self._by_name.values():
            try:
                if adapter.detect(root, descriptor):
                    candidates.append(adapter)
            except Exception:  # noqa: BLE001 - a broken adapter must not break detection
                continue
        if not candidates:
            return None
        for adapter in candidates:
            try:
                if adapter.available():
                    return adapter
            except Exception:  # noqa: BLE001
                continue
        return candidates[0]

    def describe(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for adapter in self._by_name.values():
            try:
                available = bool(adapter.available())
            except Exception:  # noqa: BLE001
                available = False
            out.append(
                {
                    "name": adapter.name,
                    "language": getattr(adapter, "language", ""),
                    "available": available,
                    "capabilities": sorted(getattr(adapter, "capabilities", ()) or ()),
                }
            )
        return out


class ContainerRuntimeRegistry:
    """The table of container engines (Docker, Podman)."""

    def __init__(self) -> None:
        self._by_name: dict[str, ContainerRuntimeAdapter] = {}

    def register(self, adapter: ContainerRuntimeAdapter) -> None:
        self._by_name[str(adapter.name).casefold()] = adapter

    def get(self, name: str) -> Optional[ContainerRuntimeAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def detect(self, *, prefer: str = "") -> Optional[ContainerRuntimeAdapter]:
        """The preferred available engine, else the first available one."""
        if prefer:
            preferred = self.get(prefer)
            if preferred is not None and _safe_available(preferred):
                return preferred
        for name in self.names():
            adapter = self._by_name[name]
            if _safe_available(adapter):
                return adapter
        return None

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name,
                "available": _safe_available(a),
                "version": _safe_version(a),
                "capabilities": sorted(getattr(a, "capabilities", ()) or ()),
            }
            for a in self._by_name.values()
        ]


class ComposeRegistry:
    """The table of compose front ends keyed by container-engine name."""

    def __init__(self) -> None:
        self._by_name: dict[str, ComposeAdapter] = {}

    def register(self, adapter: ComposeAdapter) -> None:
        self._by_name[str(adapter.name).casefold()] = adapter

    def get(self, name: str) -> Optional[ComposeAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def for_engine(self, engine: str) -> Optional[ComposeAdapter]:
        """The compose adapter that drives `engine` (Docker → docker compose)."""
        key = str(engine or "").casefold()
        for adapter in self._by_name.values():
            if str(getattr(adapter, "engine", "")).casefold() == key:
                return adapter
        return self._by_name.get(key)

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name, "available": _safe_available(a),
                "capabilities": sorted(getattr(a, "capabilities", ()) or ()),
            }
            for a in self._by_name.values()
        ]


class OrchestratorRegistry:
    """Future: Kubernetes / Helm / Kustomize adapters."""

    def __init__(self) -> None:
        self._by_name: dict[str, OrchestratorAdapter] = {}

    def register(self, adapter: OrchestratorAdapter) -> None:
        self._by_name[str(adapter.name).casefold()] = adapter

    def get(self, name: str) -> Optional[OrchestratorAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": a.name, "available": _safe_available(a), "capabilities": sorted(getattr(a, "capabilities", ()) or ())} for a in self._by_name.values()]


class InfrastructureRegistry:
    """Future: Terraform / Pulumi adapters."""

    def __init__(self) -> None:
        self._by_name: dict[str, InfrastructureAdapter] = {}

    def register(self, adapter: InfrastructureAdapter) -> None:
        self._by_name[str(adapter.name).casefold()] = adapter

    def get(self, name: str) -> Optional[InfrastructureAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": a.name, "available": _safe_available(a), "capabilities": sorted(getattr(a, "capabilities", ()) or ())} for a in self._by_name.values()]


class DeploymentRegistry:
    """Future: cloud provider adapters."""

    def __init__(self) -> None:
        self._by_name: dict[str, CloudProviderAdapter] = {}

    def register(self, adapter: CloudProviderAdapter) -> None:
        self._by_name[str(adapter.name).casefold()] = adapter

    def get(self, name: str) -> Optional[CloudProviderAdapter]:
        return self._by_name.get(str(name or "").casefold())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": a.name, "available": _safe_available(a), "capabilities": sorted(getattr(a, "capabilities", ()) or ())} for a in self._by_name.values()]


class RuntimeRegistry:
    """The central registry: every provider kind under one object."""

    def __init__(self) -> None:
        self.packages = PackageManagerRegistry()
        self.containers = ContainerRuntimeRegistry()
        self.compose = ComposeRegistry()
        self.orchestrators = OrchestratorRegistry()
        self.infrastructure = InfrastructureRegistry()
        self.deployments = DeploymentRegistry()

    def register(self, adapter: Any) -> None:
        """Register an adapter into the sub-registry that matches its type.

        Dispatch is by the adapter's declared shape (container vs package vs
        compose), so a new provider kind is additive and the core never changes.
        `kind` is authoritative when present; the legacy capability heuristics
        remain for the container/compose/package adapters that predate it.
        """
        kind = getattr(adapter, "kind", "")
        if kind == "orchestrator":
            self.orchestrators.register(adapter)
        elif kind == "infrastructure":
            self.infrastructure.register(adapter)
        elif kind == "deployment":
            self.deployments.register(adapter)
        elif kind == "compose" or hasattr(adapter, "compose_subcommands"):
            self.compose.register(adapter)
        elif kind == "container" or hasattr(adapter, "container_subcommands"):
            self.containers.register(adapter)
        elif kind == "package" or hasattr(adapter, "install_dependencies"):
            self.packages.register(adapter)

    def describe(self) -> dict[str, Any]:
        return {
            "packageManagers": self.packages.describe(),
            "containerRuntimes": self.containers.describe(),
            "compose": self.compose.describe(),
            "orchestrators": self.orchestrators.describe(),
            "infrastructure": self.infrastructure.describe(),
            "deployments": self.deployments.describe(),
        }

    def capabilities(self) -> dict[str, Any]:
        """The unified capability matrix: what the runtime can do right now."""
        return {
            "package": {a.name: sorted(a.capabilities) for a in self.packages._by_name.values() if _safe_available(a)},  # noqa: SLF001
            "container": {a.name: sorted(a.capabilities) for a in self.containers._by_name.values() if _safe_available(a)},  # noqa: SLF001
            "compose": {a.name: sorted(a.capabilities) for a in self.compose._by_name.values() if _safe_available(a)},  # noqa: SLF001
            "orchestrator": {a.name: sorted(a.capabilities) for a in self.orchestrators._by_name.values()},  # noqa: SLF001
            "infrastructure": {a.name: sorted(a.capabilities) for a in self.infrastructure._by_name.values()},  # noqa: SLF001
            "deployment": {a.name: sorted(a.capabilities) for a in self.deployments._by_name.values()},  # noqa: SLF001
        }


def _safe_available(adapter: Any) -> bool:
    try:
        return bool(adapter.available())
    except Exception:  # noqa: BLE001 - an unavailable probe is not available
        return False


def _safe_version(adapter: Any) -> str:
    try:
        return str(adapter.version() or "")
    except Exception:  # noqa: BLE001
        return ""


__all__ = [
    "ALL_CAPABILITIES",
    "CAP_AUDIT",
    "CAP_BUILD",
    "CAP_COMPOSE_CONFIG",
    "CAP_COMPOSE_DOWN",
    "CAP_COMPOSE_EXEC",
    "CAP_COMPOSE_LIFECYCLE",
    "CAP_COMPOSE_LOGS",
    "CAP_COMPOSE_PS",
    "CAP_COMPOSE_UP",
    "CAP_COMPOSE_VALIDATE",
    "CAP_CONTAINER_BUILD",
    "CAP_CONTAINER_EXEC",
    "CAP_CONTAINER_IMAGES",
    "CAP_CONTAINER_INSPECT",
    "CAP_CONTAINER_LIFECYCLE",
    "CAP_CONTAINER_LIST",
    "CAP_CONTAINER_LOGS",
    "CAP_CONTAINER_REMOVE",
    "CAP_CONTAINER_RUN",
    "CAP_CONTAINER_STATS",
    "CAP_DETECT",
    "CAP_DEPLOY",
    "CAP_DEPLOY_DELETE",
    "CAP_DEPLOY_LOGS",
    "CAP_DEPLOY_ROLLBACK",
    "CAP_DEPLOY_STATUS",
    "CAP_HEALTH",
    "CAP_HELM_INSTALL",
    "CAP_HELM_LIST",
    "CAP_HELM_REPO",
    "CAP_HELM_STATUS",
    "CAP_HELM_TEMPLATE",
    "CAP_HELM_UNINSTALL",
    "CAP_INSTALL",
    "CAP_INSTALL_PACKAGE",
    "CAP_K8S_APPLY",
    "CAP_K8S_DELETE",
    "CAP_K8S_DESCRIBE",
    "CAP_K8S_EXEC",
    "CAP_K8S_GET",
    "CAP_K8S_LOGS",
    "CAP_K8S_ROLLOUT",
    "CAP_K8S_SCALE",
    "CAP_KUSTOMIZE_BUILD",
    "CAP_LINT",
    "CAP_LIST_DEPENDENCIES",
    "CAP_PORTS",
    "CAP_REMOVE_PACKAGE",
    "CAP_RUN_SCRIPT",
    "CAP_TEST",
    "CAP_TF_APPLY",
    "CAP_TF_DESTROY",
    "CAP_TF_FMT",
    "CAP_TF_INIT",
    "CAP_TF_OUTPUT",
    "CAP_TF_PLAN",
    "CAP_TF_STATE",
    "CAP_TF_VALIDATE",
    "CAP_UPDATE_PACKAGE",
    "CAP_VERSION",
    "Capability",
    "CloudProviderAdapter",
    "ComposeAdapter",
    "ComposeRegistry",
    "ContainerRuntimeAdapter",
    "ContainerRuntimeRegistry",
    "DeploymentRegistry",
    "InfrastructureAdapter",
    "InfrastructureRegistry",
    "OrchestratorAdapter",
    "OrchestratorRegistry",
    "PackageManagerAdapter",
    "PackageManagerRegistry",
    "RuntimeRegistry",
    "supports",
]
