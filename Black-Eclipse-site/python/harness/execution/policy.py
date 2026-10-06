"""The execution policy engine — risk, isolation and secret decisions.

This module answers, deterministically and without side effects: may this
execution run, at what risk, with what network and filesystem reach, and with
which secrets? It sits ON TOP of the code capability's ONE policy authority
(`code/policy.py`): the autonomy/binding gate and the closed command vocabulary
still live there; this module only adds the execution-layer concerns the spec
names (command risk bands, network/filesystem policy, secret isolation).

The model can never silently upgrade its own permissions: the request's
`network_policy` / `filesystem_policy` are CEILINGS that are narrowed to what the
autonomy profile permits, and an attempt to widen beyond the profile is refused
with a stable code — never silently honoured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from ..code import policy as code_policy
from .models import (
    ExecutionRequest,
    FilesystemPolicy,
    NetworkPolicy,
    RiskLevel,
)

# ── Risk classification ─────────────────────────────────────────────────────
#
# Policy-driven, never LLM-driven. The bands are DATA: a program maps to a band,
# and the band decides whether an approval card is required. Unknown programs are
# `MEDIUM` (ask), so nothing new silently runs.

_SAFE_PROGRAMS = frozenset(
    {
        "python", "python3", "node", "deno", "bun", "tsc", "tsx", "ts-node",
        "pytest", "vitest", "jest", "mocha", "go", "cargo", "java", "javac",
        "dotnet", "sqlite3", "psql", "git", "echo", "ls", "dir", "cat", "type",
    }
)
_LOW_PROGRAMS = frozenset({"npm", "npx", "pnpm", "yarn", "pip", "pip3", "uv", "poetry", "make", "cmake"})
_HIGH_PROGRAMS = frozenset({"sudo", "runas", "reg", "regedit", "diskpart", "shutdown", "systemctl"})
_CRITICAL_PROGRAMS = frozenset({"mkfs", "format", "dd", "fdisk", "parted"})

RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.SAFE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def _program_name(argv: list[str]) -> str:
    first = argv[0] if argv else ""
    name = os.path.basename(str(first).replace("\\", "/")).casefold()
    for suffix in (".exe", ".cmd", ".bat", ".com", ".py", ".js"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def classify_program(argv: list[str]) -> RiskLevel:
    """Classify a resolved argv's risk band. Unknown → MEDIUM (ask)."""
    program = _program_name(argv)
    if not program:
        return RiskLevel.MEDIUM
    if program in _CRITICAL_PROGRAMS:
        return RiskLevel.CRITICAL
    if program in _HIGH_PROGRAMS:
        return RiskLevel.HIGH
    if program in code_policy.DENIED_PROGRAMS:
        return RiskLevel.CRITICAL
    if program in _SAFE_PROGRAMS:
        return RiskLevel.SAFE
    if program in _LOW_PROGRAMS:
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if RISK_ORDER[a] >= RISK_ORDER[b] else b


# ── Secret isolation ─────────────────────────────────────────────────────────

# Names that are never injected into a child, whatever a caller asks for. The
# list is a hard denylist: .env, cloud credentials, SSH/GitHub tokens, browser
# cookies, provider keys and DB passwords are refused by construction.
_FORBIDDEN_SECRETS = frozenset(
    {
        ".env", "aws_access_key_id", "aws_secret_access_key", "github_token",
        "gh_token", "ssh_auth_sock", "ssh_agent_pid", "database_url",
        "db_password", "cookie", "cookies", "api_key", "openai_api_key",
        "anthropic_api_key", "cron_secret", "harness_callback_token",
    }
)


def forbidden_secret_names() -> frozenset[str]:
    """The secret names that are never injectable."""
    return _FORBIDDEN_SECRETS


def sanitize_secrets(secrets: Optional[dict[str, str]]) -> dict[str, str]:
    """Drop any forbidden secret name. Returns only the injectable subset.

    There is no "vault" in this build: callers supply plain values, and anything
    named like a host secret is refused before it can reach a child. Values are
    never logged.
    """
    if not secrets:
        return {}
    out: dict[str, str] = {}
    for name, value in secrets.items():
        key = str(name).casefold()
        if key in _FORBIDDEN_SECRETS or key.endswith(".env"):
            continue
        out[str(name)] = str(value)
    return out


# ── Contracts ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExecutionDecision:
    """The policy engine's verdict for one execution request."""

    allowed: bool
    code: str = "OK"
    reason: str = ""
    risk: RiskLevel = RiskLevel.SAFE
    network_policy: NetworkPolicy = NetworkPolicy.NONE
    filesystem_policy: FilesystemPolicy = FilesystemPolicy.WORKSPACE_READ_WRITE
    secrets: dict[str, str] = field(default_factory=dict)
    require_approval: bool = False
    error_class: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "code": self.code, "reason": self.reason,
            "risk": self.risk.value,
            "networkPolicy": self.network_policy.value,
            "filesystemPolicy": self.filesystem_policy.value,
            "secretNames": sorted(self.secrets.keys()),
            "requireApproval": self.require_approval,
            "errorClass": self.error_class,
        }


# Plain, user-facing refusal copy for the execution layer's stable codes.
REFUSAL_COPY: dict[str, dict[str, str]] = {
    "EXECUTION_DISABLED": {
        "reason": "Running code isn't turned on for this session.",
        "recovery": "Turn it on in settings, then ask again.",
    },
    "PROFILE_DENIED": {
        "reason": "This session isn't set up to run code.",
        "recovery": "Ask in a session that is allowed to run code.",
    },
    "WORKSPACE_UNBOUND": {
        "reason": "There's no project open for me to run code in.",
        "recovery": "Open a project first, then ask again.",
    },
    "NETWORK_NOT_PERMITTED": {
        "reason": "That would need internet access, which this session doesn't allow.",
        "recovery": "Install what it needs outside the session, then ask again.",
    },
    "RISK_REQUIRES_APPROVAL": {
        "reason": "That's a risky thing to run, so I need your permission first.",
        "recovery": "Approve the step when I ask, and I'll continue.",
    },
    "SECRET_FORBIDDEN": {
        "reason": "That step asked for a credential I won't hand over.",
        "recovery": "Remove the credential from the request; Eclipse keeps secrets out of runs.",
    },
    "UNKNOWN_LANGUAGE": {
        "reason": "I don't know how to run that kind of code yet.",
        "recovery": "Use a language Eclipse supports: Python, JavaScript, TypeScript, SQL or a shell command.",
    },
    "SANDBOX_UNAVAILABLE": {
        "reason": "I can't run code safely on this computer right now, so I won't run it.",
        "recovery": "Run it on a computer where Eclipse can isolate it.",
    },
}


def refusal_copy(code: str) -> dict[str, str]:
    return REFUSAL_COPY.get(code, {"reason": "I didn't run that.", "recovery": "Try a different request."})


_AUTONOMY_NETWORK: dict[str, NetworkPolicy] = {
    "plan_only": NetworkPolicy.NONE,
    "edit_verify": NetworkPolicy.NONE,
    "approve_external": NetworkPolicy.ALLOWLIST,
}
_AUTONOMY_FS: dict[str, FilesystemPolicy] = {
    "plan_only": FilesystemPolicy.READ_ONLY,
    "edit_verify": FilesystemPolicy.WORKSPACE_READ_WRITE,
    "approve_external": FilesystemPolicy.WORKSPACE_READ_WRITE,
}
# Approval is required at or above this band for a RUN-capable profile.
_APPROVAL_BAND = RiskLevel.HIGH


def _network_ceiling(autonomy: Optional[str]) -> NetworkPolicy:
    return _AUTONOMY_NETWORK.get(str(autonomy), NetworkPolicy.NONE)


def _fs_ceiling(autonomy: Optional[str]) -> FilesystemPolicy:
    return _AUTONOMY_FS.get(str(autonomy), FilesystemPolicy.READ_ONLY)


def _narrow_network(requested: NetworkPolicy, ceiling: NetworkPolicy) -> NetworkPolicy:
    order = [NetworkPolicy.NONE, NetworkPolicy.LOCAL_ONLY, NetworkPolicy.ALLOWLIST, NetworkPolicy.FULL]
    return requested if order.index(requested) <= order.index(ceiling) else ceiling


def _narrow_fs(requested: FilesystemPolicy, ceiling: FilesystemPolicy) -> FilesystemPolicy:
    # ISOLATED is the most restrictive; READ_ONLY next; WORKSPACE_RW is broadest.
    order = [FilesystemPolicy.ISOLATED, FilesystemPolicy.READ_ONLY, FilesystemPolicy.WORKSPACE_READ_WRITE]
    index = min(order.index(requested), order.index(ceiling))
    return order[index]


class ExecutionPolicyEngine:
    """Evaluate an execution request against the run's policy.

    The engine is stateless. `evaluate` consults `code.policy.code_grants` for the
    profile, classifies the request's risk band from its argv template, narrows
    the requested network/filesystem policy to the profile ceiling, and sanitizes
    secrets. It never executes anything.
    """

    def evaluate_request(
        self,
        actor: Any,
        binding: Optional[Any],
        request: ExecutionRequest,
        *,
        argv: Optional[list[str]] = None,
        execution_enabled: bool = True,
    ) -> ExecutionDecision:
        """Return the verdict for `request`. `argv` is the resolved command, if known."""
        if not execution_enabled:
            return ExecutionDecision(False, "EXECUTION_DISABLED", refusal_copy("EXECUTION_DISABLED")["reason"])

        if binding is None:
            return ExecutionDecision(False, "WORKSPACE_UNBOUND", refusal_copy("WORKSPACE_UNBOUND")["reason"])

        autonomy = getattr(actor, "autonomy", None)
        workspace_id = getattr(actor, "workspace_id", None)
        if not workspace_id or workspace_id != getattr(binding, "id", None):
            return ExecutionDecision(False, "PROFILE_DENIED", refusal_copy("PROFILE_DENIED")["reason"])
        grants = code_policy.code_grants(str(autonomy))
        if "code.execute" not in grants:
            return ExecutionDecision(False, "PROFILE_DENIED", refusal_copy("PROFILE_DENIED")["reason"])

        # Risk band from the resolved argv (or the declared runtime when unknown).
        tokens = list(argv or [])
        risk = classify_program(tokens) if tokens else RiskLevel.LOW

        # Network / filesystem: the request asks; the profile caps.
        network = _narrow_network(request.network_policy, _network_ceiling(str(autonomy)))
        filesystem = _narrow_fs(request.filesystem_policy, _fs_ceiling(str(autonomy)))

        # Secret isolation: forbidden names are dropped, never injected. If the
        # caller explicitly asked for a forbidden secret, refuse rather than
        # silently drop it (so the agent learns the value was refused).
        requested_secrets = request.secrets or {}
        for name in requested_secrets:
            key = str(name).casefold()
            if key in forbidden_secret_names() or key.endswith(".env"):
                return ExecutionDecision(
                    False, "SECRET_FORBIDDEN",
                    refusal_copy("SECRET_FORBIDDEN")["reason"],
                    risk=risk, error_class="SECURITY_ERROR",
                )
        secrets = sanitize_secrets(requested_secrets)

        # A `dependency_install`-style request (network=True) must be permitted by
        # the profile's network ceiling; a NONE ceiling refuses it.
        if request.network_policy != NetworkPolicy.NONE and network == NetworkPolicy.NONE:
            return ExecutionDecision(
                False, "NETWORK_NOT_PERMITTED",
                refusal_copy("NETWORK_NOT_PERMITTED")["reason"],
                risk=risk, error_class="SECURITY_ERROR",
            )

        require_approval = RISK_ORDER[risk] >= RISK_ORDER[_APPROVAL_BAND]

        return ExecutionDecision(
            True, "OK", "This is allowed inside the task's own folder.",
            risk=risk, network_policy=network, filesystem_policy=filesystem,
            secrets=secrets, require_approval=require_approval,
        )


__all__ = [
    "ExecutionDecision",
    "ExecutionPolicyEngine",
    "REFUSAL_COPY",
    "RISK_ORDER",
    "classify_program",
    "forbidden_secret_names",
    "refusal_copy",
    "sanitize_secrets",
]
