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
from .effect_tokens import (
    EffectTokenBroker,
    EffectVerdict,
    enforce_call,
    issue_for_call,
    token_mode,
)
from .floor import FloorRule, SecurityFloor, default_floor
from .gateway import SecurityGateway
from .identity import (
    ANONYMOUS,
    Identity,
    front_door_requires_auth,
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
from .native import NativeSandbox
from .permissions import PermissionGrant, PermissionSet
from .policy import PolicyDocument, PolicyEngine, PolicyError, PolicyRule
from .profiles import (
    ProfilePlan,
    SandboxProfile,
    describe_profiles,
    resolve_profile,
)
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
from .tenant_store import (
    TenantIdError,
    TenantStoreRegistry,
    default_tenant_root,
    normalize_tenant,
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
    "EffectTokenBroker",
    "EffectVerdict",
    "FloorRule",
    "Identity",
    "IsolationViolation",
    "LocalSandbox",
    "NetworkDenied",
    "NetworkPolicyEngine",
    "NetworkRule",
    "NativeSandbox",
    "OsKeychainProvider",
    "Permission",
    "PermissionGrant",
    "PermissionSet",
    "PolicyDocument",
    "PolicyEngine",
    "PolicyError",
    "PolicyProfile",
    "PolicyRule",
    "ProfilePlan",
    "RiskEngine",
    "RiskLevel",
    "SandboxResult",
    "SandboxProfile",
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
    "TenantIdError",
    "TenantStoreRegistry",
    "Verdict",
    "classify_tool",
    "default_floor",
    "default_tenant_root",
    "describe_profiles",
    "effect_tool_names",
    "enforce_call",
    "get_sandbox",
    "issue_for_call",
    "resolve_profile",
    "token_mode",
    "front_door_requires_auth",
    "multi_tenant_required",
    "normalize_tenant",
    "require_identity",
    "require_tenant",
    "resolve_identity",
    "sign_identity",
    "verify_identity_token",
]
