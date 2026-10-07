"""The Application Runtime layer — understand, prepare, run and observe apps.

This package gives Eclipse an actual Application Runtime, not a bag of shell
wrappers. It reuses the existing infrastructure rather than duplicating it:

  * the terminal subsystem owns persistent processes and ports;
  * `code/sandbox.py` is the ONE bounded execution primitive;
  * `code/policy.py` owns autonomy/binding/command vocabulary;
  * `agent-memory.db` is the runtime state store (via `ApplicationRuntimeStore`).

The central registry (`RuntimeRegistry`) holds provider-agnostic adapters:
package managers, container runtimes (Docker/Podman), compose, and the (future)
Kubernetes/Terraform/cloud seams. The `ApplicationRuntimeManager` owns the
lifecycle; adapters own the concrete behaviour.

Entry points:

    from harness.execution.application import (
        ApplicationRuntimeManager, build_runtime_registry, discover_application,
    )
"""

from __future__ import annotations

from .compose import ComposeAdapter, ComposeResult, DockerComposeAdapter, PodmanComposeAdapter
from .container import ContainerResult, ContainerRuntimeAdapter, DockerAdapter, PodmanAdapter
from .cli_base import CliAdapter, CliOperation, CliResult
from .cloud import (
    AwsAdapter,
    AzureAdapter,
    CloudflareAdapter,
    GcpAdapter,
    RailwayAdapter,
    RenderAdapter,
    VercelAdapter,
    build_deployment_adapters,
)
from .deployment import DeploymentEngine, DeploymentOutcome, DeploymentTarget
from .diagnostics import RuntimeDiagnosticsEngine
from .cache import DiscoveryCache
from .infrastructure import TerraformAdapter
from .orchestrators import HelmAdapter, KubernetesAdapter, KustomizeAdapter
from .discovery import (
    ApplicationDiscovery,
    ComposeService,
    build_service_graph,
    discover_application,
)
from .environment import (
    EnvVar,
    EnvironmentDetector,
    EnvironmentManager,
    EnvironmentReport,
    is_secret_name,
)
from .events import EVENT_NAMES, RuntimeEventEmitter, make_emitter
from .health import HealthCheckEngine
from .manager import ApplicationRuntimeManager, RuntimePolicy, build_runtime_registry
from .policy import DESTRUCTIVE_OPERATIONS
from .models import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    ApplicationDescriptor,
    ApplicationState,
    DiagnosticCategory,
    HealthCheck,
    HealthReport,
    HealthResult,
    HealthStatus,
    PortRecord,
    RecoveryAttempt,
    RecoveryStrategy,
    RuntimeDiagnosis,
    RuntimeHandle,
    ServiceGraph,
    ServiceKind,
    ServiceNode,
    is_active,
    is_terminal,
    new_application_id,
    new_runtime_id,
)
from .package_managers import (
    BasePackageManager,
    build_package_manager_registry,
)
from .ports import PortConflict, PortManager
from .recovery import RecoveryEngine, RecoveryOutcome, recovery_budget
from .registry import (
    Capability,
    CloudProviderAdapter,
    ComposeRegistry,
    ContainerRuntimeRegistry,
    DeploymentRegistry,
    InfrastructureAdapter,
    InfrastructureRegistry,
    OrchestratorAdapter,
    OrchestratorRegistry,
    PackageManagerAdapter,
    PackageManagerRegistry,
    RuntimeRegistry,
    supports,
)
from .state import ApplicationStateMachine
from .store import ApplicationRuntimeStore

__all__ = [
    "ACTIVE_STATES",
    "ApplicationDescriptor",
    "ApplicationDiscovery",
    "ApplicationRuntimeManager",
    "ApplicationRuntimeStore",
    "ApplicationState",
    "ApplicationStateMachine",
    "AwsAdapter",
    "AzureAdapter",
    "BasePackageManager",
    "Capability",
    "CliAdapter",
    "CliOperation",
    "CliResult",
    "CloudProviderAdapter",
    "CloudflareAdapter",
    "DiscoveryCache",
    "DeploymentEngine",
    "DeploymentOutcome",
    "DeploymentTarget",
    "GcpAdapter",
    "HelmAdapter",
    "KubernetesAdapter",
    "KustomizeAdapter",
    "RailwayAdapter",
    "RenderAdapter",
    "TerraformAdapter",
    "VercelAdapter",
    "ComposeAdapter",
    "ComposeRegistry",
    "ComposeResult",
    "ComposeService",
    "ContainerResult",
    "ContainerRuntimeAdapter",
    "ContainerRuntimeRegistry",
    "DeploymentRegistry",
    "DiagnosticCategory",
    "DockerAdapter",
    "DockerComposeAdapter",
    "EVENT_NAMES",
    "EnvVar",
    "EnvironmentDetector",
    "EnvironmentManager",
    "EnvironmentReport",
    "HealthCheck",
    "HealthCheckEngine",
    "HealthReport",
    "HealthResult",
    "HealthStatus",
    "InfrastructureAdapter",
    "InfrastructureRegistry",
    "OrchestratorAdapter",
    "OrchestratorRegistry",
    "PackageManagerAdapter",
    "PackageManagerRegistry",
    "PodmanAdapter",
    "PodmanComposeAdapter",
    "PortConflict",
    "PortManager",
    "PortRecord",
    "RecoveryAttempt",
    "RecoveryEngine",
    "RecoveryOutcome",
    "RecoveryStrategy",
    "RuntimeDiagnosis",
    "RuntimeDiagnosticsEngine",
    "RuntimeEventEmitter",
    "RuntimeHandle",
    "RuntimePolicy",
    "RuntimeRegistry",
    "ServiceGraph",
    "ServiceKind",
    "ServiceNode",
    "TERMINAL_STATES",
    "build_package_manager_registry",
    "build_runtime_registry",
    "build_service_graph",
    "discover_application",
    "is_active",
    "is_secret_name",
    "is_terminal",
    "make_emitter",
    "new_application_id",
    "new_runtime_id",
    "recovery_budget",
    "supports",
]
