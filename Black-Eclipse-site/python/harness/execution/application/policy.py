"""The runtime permission policy — risk bands and the ALLOW/ASK/DENY decision.

A simple, auditable table over operation names. The runtime NEVER bypasses the
existing authorization: this is consulted BEFORE a destructive action, and an ASK
yields a structured refusal unless an operator approval is supplied.

It is deliberately its own module so the size of the orchestrator stays bounded
and the policy is reviewable on its own.
"""

from __future__ import annotations

# Risk bands for runtime operations, matching the execution layer's model.
RISK_SAFE = "SAFE"
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"
_RISK_ORDER = {RISK_SAFE: 0, RISK_LOW: 1, RISK_MEDIUM: 2, RISK_HIGH: 3, RISK_CRITICAL: 4}

#: Operations that require explicit operator authorization (a foreign process is
#: never killed, a volume is never removed, an environment file is never written
#: without an operator act).
DESTRUCTIVE_OPERATIONS = frozenset(
    {
        "container.remove", "container.volume.remove", "container.image.remove",
        "compose.down", "compose.rm", "process.kill.foreign",
        "environment.set", "environment.unset",
        # Cluster / infra / cloud mutations.
        "k8s.apply", "k8s.delete", "k8s.scale", "k8s.exec",
        "helm.install", "helm.uninstall",
        "terraform.apply", "terraform.destroy",
        "cloud.deploy", "cloud.rollback", "cloud.delete",
    }
)


class RuntimePolicy:
    """The risk/permission policy for runtime operations."""

    def __init__(self, *, level: str = "allow") -> None:
        # level: "allow" (local dev default), "ask" (confirm destructive), "deny".
        self.level = level
        self._overrides: dict[str, str] = {}

    def set(self, operation: str, decision: str) -> None:
        self._overrides[str(operation)] = decision

    def risk_of(self, operation: str) -> str:
        if operation in DESTRUCTIVE_OPERATIONS:
            return RISK_CRITICAL
        if operation.startswith(("container.", "compose.", "process.kill")):
            return RISK_MEDIUM
        if operation.startswith(("dependencies.", "build.", "package.")):
            return RISK_LOW
        return RISK_SAFE

    def decide(self, operation: str, *, authorized: bool = False) -> tuple[bool, str, str]:
        """Return (allowed, decision, reason). Destructive ops require authorization."""
        decision = self._overrides.get(operation)
        if decision is None:
            decision = "ask" if (self.level == "ask" and operation in DESTRUCTIVE_OPERATIONS) else ("deny" if self.level == "deny" else "allow")
        if self.level == "deny" and operation in DESTRUCTIVE_OPERATIONS:
            decision = "deny"
        if decision == "allow":
            return True, "allow", ""
        if decision == "deny":
            return False, "deny", "this operation is turned off in this session"
        if authorized:
            return True, "allow", "operator approved"
        return False, "ask", "this operation needs the operator's approval first"


__all__ = [
    "DESTRUCTIVE_OPERATIONS",
    "RISK_CRITICAL",
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_SAFE",
    "RuntimePolicy",
]
