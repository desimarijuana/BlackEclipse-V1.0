"""The Eclipse Security subsystem — one coherent authorization architecture.

Public surface:
    SecurityGateway      the ONE decision path (`authorize` / `require` / `check`)
    AuthorizationRequest / AuthorizationDecision / Decision
    Permission / RiskLevel / SecurityContext / Capability

See `docs/harness/security.md` for the architecture and `bootstrap.py` for wiring.
"""

from __future__ import annotations

from .approval import ApprovalEngine, ApprovalTicket
from .audit import AuditLog, AuditSink
from .capabilities import Capability, CapabilityEngine, CapabilityError
from .classification import classify_tool, effect_tool_names
from .config import SecurityConfig
from .context import IsolationViolation, SessionRegistry
from .floor import FloorRule, SecurityFloor, default_floor
from .gateway import SecurityGateway
from .identity import (
    ANONYMOUS,
    Identity,
    multi_tenant_required,
    require_identity,
    require_tenant,
    resolve_identity,
    sign_identity,
    verify_identity_token,
)
from .models import (
    Actor,
    ApprovalRequired,
    ApprovalType,
    AuthorizationDecision,
    AuthorizationRequest,
    Decision,
    Environment,
    Permission,
    PolicyProfile,
    RiskLevel,
    SecurityContext,
    SecurityDenied,
    Verdict,
)
from .network import NetworkDenied, NetworkPolicyEngine, NetworkRule
from .permissions import PermissionGrant, PermissionSet
from .policy import PolicyDocument, PolicyEngine, PolicyError, PolicyRule
from .risk import RiskEngine
from .sandbox import (
    DockerSandbox,
    ExecutionSandbox,
    LocalSandbox,
    SandboxResult,
    SandboxSpec,
    SandboxUnavailable,
    UnavailableSandbox,
    get_sandbox,
)
from .secrets import (
    CliSecretProvider,
    OsKeychainProvider,
    SecretAccessDenied,
    SecretGrant,
    SecretRegistry,
    SecretsManager,
)

__all__ = [
    "ANONYMOUS",
    "Actor",
    "ApprovalEngine",
    "ApprovalRequired",
    "ApprovalTicket",
    "ApprovalType",
    "AuditLog",
    "AuditSink",
    "AuthorizationDecision",
    "AuthorizationRequest",
    "Capability",
    "CapabilityEngine",
    "CapabilityError",
    "CliSecretProvider",
    "Decision",
    "DockerSandbox",
    "Environment",
    "ExecutionSandbox",
    "FloorRule",
    "Identity",
    "IsolationViolation",
    "LocalSandbox",
    "NetworkDenied",
    "NetworkPolicyEngine",
    "NetworkRule",
    "OsKeychainProvider",
    "Permission",
    "PermissionGrant",
    "PermissionSet",
    "PolicyDocument",
    "PolicyEngine",
    "PolicyError",
    "PolicyProfile",
    "PolicyRule",
    "RiskEngine",
    "RiskLevel",
    "SandboxResult",
    "SandboxSpec",
    "SandboxUnavailable",
    "SecretAccessDenied",
    "SecretGrant",
    "SecretRegistry",
    "SecretsManager",
    "SecurityConfig",
    "SecurityContext",
    "SecurityDenied",
    "SecurityFloor",
    "SecurityGateway",
    "SessionRegistry",
    "UnavailableSandbox",
    "Verdict",
    "classify_tool",
    "default_floor",
    "effect_tool_names",
    "get_sandbox",
    "multi_tenant_required",
    "require_identity",
    "require_tenant",
    "resolve_identity",
    "sign_identity",
    "verify_identity_token",
]
