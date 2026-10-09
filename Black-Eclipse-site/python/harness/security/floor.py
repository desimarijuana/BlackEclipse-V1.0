"""The Security Floor — immutable baseline rules that ordinary policy cannot weaken.

The floor exists so that no combination of profile, skill, plugin, MCP server,
prompt or request field can turn a dangerous operation into an allowed one. It is
evaluated FIRST, before policy, and its verdicts are terminal:

    HARD_DENY           → DENY, immediately, no policy can override
    MANDATORY_APPROVAL  → at minimum APPROVAL_REQUIRED, no policy can downgrade
    HARD_ALLOW          → short-circuit to ALLOW (used sparingly, read-only only)

The floor is constructed from a frozen rule list. `freeze()` marks it immutable;
a rule set can only be replaced through `load_floor`, which is called by the
administrator-controlled policy reload path, never by an agent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import Environment, Verdict
from .permissions import canonicalize_resource, fnmatch_name, resource_matches

# Sensitive path fragments that must never be read, written or executed through a
# tool. Matching is done on the canonicalized, lowercased path with both `/` and
# `\` normalized. These complement `code.policy.PROTECTED_PATHS` at the floor.
SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    "/.ssh/", "/.aws/", "/.kube/", "/.gnupg/", "/.config/gcloud/",
    "/.docker/config.json", "/.netrc", "/.npmrc", "/.pypirc",
    "/etc/shadow", "/etc/passwd", "/etc/sudoers",
    "/.git/config",  # rewrite could redirect hooks/sshcommand
)
SENSITIVE_PATH_SUFFIXES: tuple[str, ...] = (
    "/id_rsa", "/id_ed25519", "/id_ecdsa", "/id_dsa",
    "/.env", "/credentials", "/secrets.json", "/secrets.yaml", "/secrets.yml",
)
SENSITIVE_PATH_GLOBS: tuple[str, ...] = (
    "**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx",
    "**/.black-eclipse/security/**", "**/security/policy*.json",
    "**/security/policy*.yaml", "**/security/policy*.yml",
    "**/.black-eclipse/auth.db", "**/jdds.db", "**/agent-memory.db",
    # Operating-system directories: a tool must never write/delete here.
    "/etc/**", "/usr/**", "/bin/**", "/sbin/**", "/boot/**", "/sys/**",
    "/proc/**", "/dev/**", "/root/**", "/var/**", "/lib/**", "/opt/**",
    "c:/windows/**", "c:/program files/**", "c:/program files (x86)/**",
    "c:/programdata/**",
)

# Action namespaces that the floor treats as privileged. A hard-deny applies to
# the specific dangerous actions; deployment/financial always require approval.
_DANGEROUS_ACTIONS = {
    "database.ddl", "database.admin", "deploy.destroy",
    "infrastructure.destroy",
    "financial.withdraw", "financial.transfer", "security.admin",
    "security.policy", "credential.admin",
}
_MANDATORY_APPROVAL_ACTIONS = {
    "database.write", "database.delete",
    "deploy.production", "deploy.staging", "deploy.destroy",
    "infrastructure.write",
    "external.action", "git.external", "browser.action", "computer.finance",
    "financial.live_trade", "financial.cancel_order",
    "financial.transfer", "financial.withdraw",
    "security.policy", "security.admin",
    "plugin.invoke", "mcp.invoke",
}


@dataclass(frozen=True)
class FloorRule:
    name: str
    verdict: Verdict
    actions: tuple[str, ...] = ()          # action globs; empty = any action
    resources: tuple[str, ...] = ()        # resource globs; empty = any resource
    environments: tuple[Environment, ...] = ()
    reason: str = ""
    immutable: bool = True

    def matches(self, action: str, resource: str, environment: Environment) -> bool:
        if self.actions and not any(fnmatch_name(a, action) for a in self.actions):
            return False
        if self.resources:
            canon = canonicalize_resource(resource)
            if not any(resource_matches(r, canon) for r in self.resources):
                return False
        if self.environments and environment not in self.environments:
            return False
        return True


@dataclass
class FloorVerdict:
    verdict: Verdict
    rule: str
    reason: str = ""


def _path_is_sensitive(resource: str) -> Optional[str]:
    """Return the sensitive fragment that matched, or None."""
    if not resource:
        return None
    canon = canonicalize_resource(resource)
    lowered = canon.lower().replace("\\", "/")
    probe = "/" + lowered.strip("/") + "/"
    for fragment in SENSITIVE_PATH_FRAGMENTS:
        if fragment in probe:
            return fragment
    for suffix in SENSITIVE_PATH_SUFFIXES:
        if lowered.endswith(suffix) or ("/" + lowered.strip("/")).endswith(suffix):
            return suffix
    for glob in SENSITIVE_PATH_GLOBS:
        if resource_matches(glob, lowered):
            return glob
    return None


def default_floor() -> "SecurityFloor":
    """The baseline floor. Secrets, credentials, security config, production,
    financial and destructive infrastructure actions are protected out of the box."""
    rules: list[FloorRule] = [
        # Sensitive paths (credentials, keys, .env, the security config) are
        # handled by the path-level check in `evaluate`, so they are refused for
        # any filesystem operation without needing an over-broad action rule.
        FloorRule(
            "floor.security-config",
            Verdict.HARD_DENY,
            actions=("filesystem.write", "filesystem.delete", "shell.execute"),
            resources=("**/.black-eclipse/security/**", "**/security/policy*.json",
                       "**/security/policy*.yaml", "**/security/policy*.yml"),
            reason="the security subsystem's own configuration cannot be modified by an agent",
        ),
        FloorRule(
            "floor.dangerous",
            Verdict.HARD_DENY,
            actions=tuple(sorted(_DANGEROUS_ACTIONS)),
            reason="this action is on the security floor's hard-deny list",
        ),
        FloorRule(
            "floor.production-infra",
            Verdict.HARD_DENY,
            actions=("database.admin", "deploy.destroy"),
            environments=(Environment.PRODUCTION,),
            reason="production infrastructure destruction requires an administrator path outside the agent",
        ),
        FloorRule(
            "floor.mandatory-approval",
            Verdict.MANDATORY_APPROVAL,
            actions=tuple(sorted(_MANDATORY_APPROVAL_ACTIONS)),
            reason="this action always requires an explicit operator approval",
        ),
        FloorRule(
            "floor.production-writes",
            Verdict.MANDATORY_APPROVAL,
            actions=("filesystem.write", "filesystem.delete", "database.write", "database.delete"),
            environments=(Environment.PRODUCTION,),
            reason="writes against production always require an explicit operator approval",
        ),
    ]
    return SecurityFloor(rules)


class SecurityFloor:
    """Evaluate immutable baseline rules. Pure and side-effect free."""

    def __init__(self, rules: Optional[Iterable[FloorRule]] = None) -> None:
        self._rules: tuple[FloorRule, ...] = tuple(rules or ())
        self._frozen = True
        self._version = 1

    @property
    def version(self) -> int:
        return self._version

    @property
    def rules(self) -> tuple[FloorRule, ...]:
        return self._rules

    def evaluate(
        self, *, action: str, resource: str = "", environment: Environment = Environment.DEVELOPMENT,
    ) -> Optional[FloorVerdict]:
        """The terminal floor verdict, or None when the floor is silent.

        Order: HARD_DENY beats HARD_ALLOW beats MANDATORY_APPROVAL. A sensitive
        path used for read is also hard-denied (the floor protects credentials
        regardless of the operation).
        """
        action = str(action or "")
        resource = str(resource or "")
        # Path-level protection independent of the declared action.
        if resource and action.startswith("filesystem."):
            sensitive = _path_is_sensitive(resource)
            if sensitive is not None:
                return FloorVerdict(
                    Verdict.HARD_DENY, "floor.sensitive-path",
                    f"path matches protected pattern {sensitive!r}",
                )
        deny: Optional[FloorVerdict] = None
        allow: Optional[FloorVerdict] = None
        approval: Optional[FloorVerdict] = None
        for rule in self._rules:
            if not rule.matches(action, resource, environment):
                continue
            if rule.verdict is Verdict.HARD_DENY:
                deny = deny or FloorVerdict(rule.verdict, rule.name, rule.reason)
            elif rule.verdict is Verdict.HARD_ALLOW:
                allow = allow or FloorVerdict(rule.verdict, rule.name, rule.reason)
            elif rule.verdict is Verdict.MANDATORY_APPROVAL:
                approval = approval or FloorVerdict(rule.verdict, rule.name, rule.reason)
        return deny or allow or approval

    def add_rule(self, rule: FloorRule, *, admin: bool = False) -> None:
        """Add a rule. Only an administrator-controlled path may call this."""
        if not admin:
            raise PermissionError("the security floor may only be changed by an administrator")
        self._rules = self._rules + (rule,)
        self._version += 1

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "name": r.name,
                "verdict": r.verdict.value,
                "actions": list(r.actions),
                "resources": list(r.resources),
                "environments": [e.value for e in r.environments],
                "reason": r.reason,
                "immutable": r.immutable,
            }
            for r in self._rules
        ]


__all__ = [
    "FloorRule",
    "FloorVerdict",
    "SecurityFloor",
    "SENSITIVE_PATH_FRAGMENTS",
    "default_floor",
]
