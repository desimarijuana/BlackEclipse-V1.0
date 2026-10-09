"""Policy engine — profiles, per-scope rules, inheritance and hot reload.

A policy maps an `(action, resource, environment)` to one of `allow`, `deny` or
`approval`. Policies are layered system → organization → user → project → agent →
task and the layers compose by **restrict-only**: a lower layer may make a rule
stricter but never weaker than a higher layer. The final verdict is the most
restrictive match across all layers.

Hot reload is atomic: a new policy is parsed, validated and compiled into a new
immutable version; only if it is valid does it replace the live policy. An invalid
policy never replaces a known-good one.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import Environment, PolicyProfile
from .permissions import canonicalize_resource, fnmatch_name, resource_matches

# Verdict strictness: allow < approval < deny. Composition takes the max.
_ALLOW = "allow"
_APPROVAL = "approval"
_DENY = "deny"
_STRICTNESS = {_ALLOW: 0, _APPROVAL: 1, _DENY: 2}

# Logical scopes, from broadest to narrowest.
SCOPE_ORDER = ("system", "organization", "user", "project", "agent", "task")


class PolicyError(ValueError):
    """A policy document failed validation."""


@dataclass(frozen=True)
class PolicyRule:
    action: str = "*"
    resource: str = "**"
    environment: Optional[Environment] = None
    verdict: str = _APPROVAL
    reason: str = ""

    def matches(self, action: str, resource: str, environment: Environment) -> bool:
        if not fnmatch_name(self.action, action):
            return False
        if self.environment is not None and self.environment is not environment:
            return False
        return resource_matches(self.resource, resource)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyRule":
        verdict = str(data.get("verdict") or data.get("decision") or _APPROVAL).strip().lower()
        if verdict not in _STRICTNESS:
            raise PolicyError(f"unknown verdict {verdict!r}")
        env = data.get("environment")
        return cls(
            action=str(data.get("action") or "*"),
            resource=str(data.get("resource") or "**"),
            environment=Environment.parse(env) if env else None,
            verdict=verdict,
            reason=str(data.get("reason") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "resource": self.resource,
            "environment": self.environment.value if self.environment else None,
            "verdict": self.verdict,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PolicyDocument:
    """One scope's policy layer."""

    scope: str = "system"
    name: str = "default"
    defaults: dict[str, str] = field(default_factory=dict)  # domain → verdict
    rules: tuple[PolicyRule, ...] = ()
    profile: PolicyProfile = PolicyProfile.SECURE
    version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, scope: str = "system", version: int = 1) -> "PolicyDocument":
        raw_rules = data.get("rules") or []
        if not isinstance(raw_rules, list):
            raise PolicyError("policy.rules must be a list")
        rules = tuple(PolicyRule.from_dict(r) for r in raw_rules)
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise PolicyError("policy.defaults must be a mapping")
        normalized_defaults: dict[str, str] = {}
        for key, value in defaults.items():
            verdict = str(value).strip().lower()
            if verdict not in _STRICTNESS:
                raise PolicyError(f"unknown default verdict {verdict!r} for {key!r}")
            normalized_defaults[str(key)] = verdict
        profile_text = str(data.get("profile") or "secure").lower()
        try:
            profile = PolicyProfile(profile_text)
        except ValueError:
            raise PolicyError(f"unknown profile {profile_text!r}") from None
        return cls(
            scope=str(data.get("scope") or scope),
            name=str(data.get("name") or "default"),
            defaults=normalized_defaults,
            rules=rules,
            profile=profile,
            version=version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "name": self.name,
            "defaults": dict(self.defaults),
            "rules": [r.to_dict() for r in self.rules],
            "profile": self.profile.value,
            "version": self.version,
        }

    def default_for(self, action: str) -> str:
        domain = str(action or "").split(".", 1)[0]
        return self.defaults.get(domain, self.defaults.get("*", _APPROVAL))


# ── Built-in profiles ────────────────────────────────────────────────────────
# A profile is a baseline document. AUTONOMOUS never means "security disabled":
# it pre-approves LOW-risk read/execute while keeping every dangerous action and
# the whole floor intact.
_PROFILE_DEFAULTS: dict[PolicyProfile, dict[str, str]] = {
    PolicyProfile.LOCKDOWN: {
        "filesystem": _DENY, "shell": _DENY, "network": _DENY,
        "database": _DENY, "deploy": _DENY, "financial": _DENY,
        "credential": _DENY, "plugin": _DENY, "mcp": _DENY,
    },
    PolicyProfile.SECURE: {
        # Approvals for the mutating/external classes; the FLOOR supplies the
        # hard denies (credentials, destructive infra, prod DB admin, …). Network
        # defaults to deny; it is a separate allow-list surface.
        "filesystem": _APPROVAL, "shell": _APPROVAL, "network": _DENY,
        "database": _APPROVAL, "deploy": _APPROVAL, "financial": _APPROVAL,
        "credential": _DENY, "plugin": _APPROVAL, "mcp": _APPROVAL,
        "*": _APPROVAL,
    },
    PolicyProfile.DEVELOPER: {
        "filesystem": _ALLOW, "shell": _APPROVAL, "network": _ALLOW,
        "database": _APPROVAL, "deploy": _APPROVAL, "financial": _APPROVAL,
        "credential": _DENY, "plugin": _APPROVAL, "mcp": _APPROVAL,
        "*": _APPROVAL,
    },
    PolicyProfile.AUTONOMOUS: {
        # Pre-approved LOW-risk operations only; dangerous classes stay gated.
        "filesystem": _ALLOW, "shell": _APPROVAL, "network": _ALLOW,
        "database": _APPROVAL, "deploy": _APPROVAL, "financial": _APPROVAL,
        "credential": _DENY, "plugin": _APPROVAL, "mcp": _APPROVAL,
        "*": _APPROVAL,
    },
}


def profile_defaults(profile: PolicyProfile) -> dict[str, str]:
    return dict(_PROFILE_DEFAULTS.get(profile, _PROFILE_DEFAULTS[PolicyProfile.SECURE]))


# Read-only and paper financial actions are always allowed (they have no external
# side effect). Live/cancel/transfer/withdraw are governed by the floor + policy.
_READ_ONLY_FINANCIAL_RULES = (
    PolicyRule(action="financial.research", verdict=_ALLOW, reason="read-only research"),
    PolicyRule(action="financial.market_read", verdict=_ALLOW, reason="read-only market data"),
    PolicyRule(action="financial.portfolio_read", verdict=_ALLOW, reason="read-only portfolio"),
    PolicyRule(action="financial.paper_trade", verdict=_ALLOW, reason="paper trading has no external effect"),
)


def default_policy(profile: PolicyProfile = PolicyProfile.SECURE, scope: str = "system") -> PolicyDocument:
    rules = () if profile is PolicyProfile.LOCKDOWN else _READ_ONLY_FINANCIAL_RULES
    return PolicyDocument(
        scope=scope,
        name=f"builtin-{profile.value}",
        defaults=profile_defaults(profile),
        rules=rules,
        profile=profile,
    )


@dataclass
class PolicyMatch:
    verdict: str
    rule: Optional[PolicyRule]
    layer: str
    reason: str = ""


class PolicyEngine:
    """Evaluate layered policy + own the hot-reload lifecycle.

    The engine holds only the *user-configured* layers. The system baseline (the
    selected profile) is always present as the outermost layer, so a lower layer
    can never weaken below the profile default.
    """

    def __init__(self, profile: PolicyProfile = PolicyProfile.SECURE) -> None:
        self._profile = profile
        self._system = default_policy(profile, "system")
        self._layers: dict[str, PolicyDocument] = {}
        self._version = 1
        self._compiled_at = time.time()
        self._history: list[dict[str, Any]] = []

    # ── configuration ────────────────────────────────────────────────────────
    @property
    def profile(self) -> PolicyProfile:
        return self._profile

    @property
    def version(self) -> int:
        return self._version

    def set_profile(self, profile: PolicyProfile) -> None:
        self._profile = profile
        self._system = default_policy(profile, "system")
        self._version += 1
        self._compiled_at = time.time()

    def set_layer(self, scope: str, document: PolicyDocument) -> None:
        if scope not in SCOPE_ORDER:
            raise PolicyError(f"unknown policy scope {scope!r}")
        if scope == "system":
            raise PolicyError("the system layer is the profile baseline and cannot be replaced directly")
        self._layers[scope] = document

    def clear_layer(self, scope: str) -> None:
        self._layers.pop(scope, None)

    def layers(self) -> list[PolicyDocument]:
        ordered = [self._system]
        for scope in SCOPE_ORDER:
            document = self._layers.get(scope)
            if document is not None:
                ordered.append(document)
        return ordered

    # ── evaluation ───────────────────────────────────────────────────────────
    def _layer_verdict(self, document: PolicyDocument, action: str, resource: str, env: Environment) -> PolicyMatch:
        for rule in document.rules:
            if rule.matches(action, resource, env):
                return PolicyMatch(rule.verdict, rule, f"{document.scope}:{document.name}", rule.reason)
        return PolicyMatch(document.default_for(action), None, f"{document.scope}:default")

    def evaluate(
        self, *, action: str, resource: str = "", environment: Environment = Environment.DEVELOPMENT,
    ) -> PolicyMatch:
        """The most restrictive verdict across all layers (restrict-only compose)."""
        best: Optional[PolicyMatch] = None
        for document in self.layers():
            match = self._layer_verdict(document, action, resource, environment)
            if best is None or _STRICTNESS[match.verdict] > _STRICTNESS[best.verdict]:
                best = match
            if best.verdict == _DENY:
                # Deny is terminal; no need to scan further for strictness.
                pass
        assert best is not None
        return best

    # ── hot reload ───────────────────────────────────────────────────────────
    def validate(self, documents: dict[str, Any], *, profile: Optional[str] = None) -> list[dict[str, Any]]:
        """Parse + validate a candidate policy set without applying it.

        Returns the compiled documents. Raises `PolicyError` on any problem, so an
        invalid policy can never be activated.
        """
        if profile is not None and profile.lower() not in PolicyProfile._value2member_map_:
            raise PolicyError(f"unknown profile {profile!r}")
        compiled: list[dict[str, Any]] = []
        for scope, body in (documents or {}).items():
            if scope not in SCOPE_ORDER:
                raise PolicyError(f"unknown policy scope {scope!r}")
            document = PolicyDocument.from_dict(body or {}, scope=scope, version=self._version + 1)
            compiled.append(document.to_dict())
        # Round-trip check: the compiled doc must serialize cleanly.
        try:
            json.dumps(compiled)
        except (TypeError, ValueError) as exc:
            raise PolicyError(f"compiled policy is not serializable: {exc}") from exc
        return compiled

    def reload(self, documents: dict[str, Any], *, profile: Optional[str] = None, actor: str = "operator") -> dict[str, Any]:
        """Atomically replace the live policy with a validated candidate.

        The candidate is parsed into NEW `PolicyDocument` objects first; only once
        every document is valid are they swapped in. On any error the live policy
        is left untouched and the error is raised.
        """
        candidate: dict[str, PolicyDocument] = {}
        new_profile = self._profile
        if profile is not None:
            try:
                new_profile = PolicyProfile(profile.lower())
            except ValueError:
                raise PolicyError(f"unknown profile {profile!r}") from None
        for scope, body in (documents or {}).items():
            if scope not in SCOPE_ORDER or scope == "system":
                raise PolicyError(f"cannot reload scope {scope!r}")
            candidate[scope] = PolicyDocument.from_dict(body or {}, scope=scope, version=self._version + 1)
        # Commit.
        self._profile = new_profile
        self._system = default_policy(new_profile, "system")
        self._layers = candidate
        self._version += 1
        self._compiled_at = time.time()
        record = {
            "version": self._version,
            "profile": self._profile.value,
            "scopes": sorted(candidate.keys()),
            "actor": actor,
            "at": self._compiled_at,
        }
        self._history.append(record)
        return record

    def load_from_dict(self, data: dict[str, Any]) -> PolicyEngine:
        """Populate the engine from a config mapping (as used at boot)."""
        security = data.get("security") if isinstance(data, dict) and "security" in data else data
        if not isinstance(security, dict):
            return self
        profile = security.get("profile")
        if profile:
            try:
                self.set_profile(PolicyProfile(str(profile).lower()))
            except ValueError:
                pass
        layers = {k: v for k, v in security.items() if k in SCOPE_ORDER and k != "system"}
        if layers:
            self.reload(layers, profile=profile, actor="boot")
        return self

    def snapshot(self) -> dict[str, Any]:
        return {
            "profile": self._profile.value,
            "version": self._version,
            "compiledAt": self._compiled_at,
            "layers": [d.to_dict() for d in self.layers()],
            "history": list(self._history[-20:]),
        }


__all__ = [
    "PolicyDocument",
    "PolicyEngine",
    "PolicyError",
    "PolicyMatch",
    "PolicyRule",
    "SCOPE_ORDER",
    "default_policy",
    "profile_defaults",
]
