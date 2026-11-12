"""Sandbox profiles — the named isolation levels C6 enforces.

A *profile* is the promise a run makes about what spawned work may touch. The
backend is whatever physical primitive the host actually has (Docker, a process
Job Object, …). The two are deliberately separate:

  * a profile states the REQUIREMENT;
  * `resolve_profile` maps it onto a backend and reports, honestly, whether the
    host can keep the promise. When it cannot, the plan is `enforceable=False`
    with the exact missing guarantees named — callers must refuse, never fall
    back to a weaker boundary silently.

Profiles:
  * `read-only`         — the workspace is mounted read-only, no network,
                          secrets scrubbed;
  * `workspace-write`   — the workspace is writable, no network, secrets
                          scrubbed;
  * `network-allowlist` — workspace writable + egress ONLY through the
                          configured egress proxy (the proxy enforces the host
                          allowlist; a raw bridge is not an allowlist);
  * `full`              — no filesystem/network promise beyond process
                          isolation and resource limits.

This module is pure policy + planning. It never executes anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional

from .sandbox import SandboxSpec, get_sandbox

PROFILE_ENV = "BLACK_ECLIPSE_SANDBOX_PROFILE"
EGRESS_PROXY_ENV = "BLACK_ECLIPSE_EGRESS_PROXY"


class SandboxProfile(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    NETWORK_ALLOWLIST = "network-allowlist"
    FULL = "full"


_PROFILE_BY_VALUE = {p.value: p for p in SandboxProfile}
_ALIASES = {
    "readonly": SandboxProfile.READ_ONLY,
    "read_only": SandboxProfile.READ_ONLY,
    "ro": SandboxProfile.READ_ONLY,
    "write": SandboxProfile.WORKSPACE_WRITE,
    "workspace_write": SandboxProfile.WORKSPACE_WRITE,
    "workspace": SandboxProfile.WORKSPACE_WRITE,
    "allowlist": SandboxProfile.NETWORK_ALLOWLIST,
    "network_allowlist": SandboxProfile.NETWORK_ALLOWLIST,
    "network": SandboxProfile.NETWORK_ALLOWLIST,
    "unrestricted": SandboxProfile.FULL,
}

# The guarantees a backend must report for a profile to be enforceable.
REQUIRED_CAPABILITIES: dict[SandboxProfile, tuple[str, ...]] = {
    SandboxProfile.READ_ONLY: (
        "processIsolation", "filesystemIsolation", "networkIsolation", "secretIsolation",
    ),
    SandboxProfile.WORKSPACE_WRITE: (
        "processIsolation", "filesystemIsolation", "networkIsolation",
    ),
    SandboxProfile.NETWORK_ALLOWLIST: (
        "processIsolation", "filesystemIsolation", "networkIsolation", "egressProxy",
    ),
    SandboxProfile.FULL: ("processIsolation",),
}


def parse_profile(value: Any, *, default: SandboxProfile = SandboxProfile.WORKSPACE_WRITE) -> SandboxProfile:
    """Parse a profile name. Unknown or empty values fall back to `default`."""
    if isinstance(value, SandboxProfile):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in _PROFILE_BY_VALUE:
        return _PROFILE_BY_VALUE[raw]
    return _ALIASES.get(raw, default)


def configured_profile() -> Optional[SandboxProfile]:
    """The operator-configured profile, or None when the env does not set one."""
    raw = (os.environ.get(PROFILE_ENV) or "").strip()
    return parse_profile(raw) if raw else None


def egress_proxy() -> Optional[str]:
    value = (os.environ.get(EGRESS_PROXY_ENV) or "").strip()
    return value or None


@dataclass
class ProfilePlan:
    """One resolved plan: what to run, where, and whether the host can keep it."""

    profile: SandboxProfile
    backend: str
    spec: SandboxSpec
    workspace: Optional[str] = None
    allowlist: tuple[str, ...] = ()
    enforceable: bool = False
    missing: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "backend": self.backend,
            "enforceable": self.enforceable,
            "missing": list(self.missing),
            "reason": self.reason,
            "workspace": self.workspace,
            "allowlist": list(self.allowlist),
            "network": self.spec.allow_network,
            "mounts": [
                {"host": host, "container": container, "readOnly": ro}
                for host, container, ro in self.spec.mounts
            ],
        }


def _normalize_host(value: str) -> str:
    host = str(value or "").strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    # Strip a userinfo segment and a port. IPv6 literals are kept bracketed only
    # when they carry no port, which is the only form we accept here.
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.strip(".")


def allowlist_permits(host: str, allowlist: Iterable[str]) -> bool:
    """Whether `host` is covered by a host allowlist (exact or `*.domain`)."""
    target = _normalize_host(host)
    if not target:
        return False
    for pattern in allowlist:
        candidate = _normalize_host(pattern)
        if not candidate:
            continue
        if candidate.startswith("*."):
            if target.endswith(candidate[1:]) and target != candidate[2:]:
                return True
        elif target == candidate:
            return True
    return False


def path_within(path: str, root: str) -> bool:
    """True when `path` resolves inside `root` (defeats `..` and absolute escapes)."""
    if not root:
        return False
    try:
        base = os.path.realpath(root)
        target = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    except (OSError, ValueError):
        return False
    if os.name == "nt":
        base_cmp, target_cmp = base.lower(), target.lower()
    else:
        base_cmp, target_cmp = base, target
    return target_cmp == base_cmp or target_cmp.startswith(base_cmp + os.sep)


def _mounts(profile: SandboxProfile, workspace: Optional[str]) -> list[tuple[str, str, bool]]:
    if not workspace:
        return []
    read_only = profile is SandboxProfile.READ_ONLY
    return [(str(workspace), "/workspace", read_only)]


def resolve_profile(
    profile: Any,
    *,
    argv: Optional[list[str]] = None,
    workspace: Optional[str] = None,
    allowlist: Iterable[str] = (),
    timeout_s: int = 120,
    memory_mb: Optional[int] = None,
    pids: Optional[int] = None,
    sandbox: Any = None,
) -> ProfilePlan:
    """Map a profile onto the active backend and report enforceability.

    Never raises for an unavailable host: an unusable plan is returned with
    `enforceable=False` and the missing guarantees named, so the caller can
    produce an honest refusal.
    """
    resolved = parse_profile(profile)
    backend = sandbox or get_sandbox()
    caps = dict(backend.capabilities() or {})
    proxy = egress_proxy()
    caps["egressProxy"] = bool(proxy and caps.get("networkIsolation"))

    required = REQUIRED_CAPABILITIES[resolved]
    missing = tuple(name for name in required if not caps.get(name))

    env: dict[str, str] = {}
    network = resolved in (SandboxProfile.NETWORK_ALLOWLIST, SandboxProfile.FULL)
    if resolved is SandboxProfile.NETWORK_ALLOWLIST and proxy:
        env = {"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "ALL_PROXY": proxy}

    spec = SandboxSpec(
        argv=list(argv or ["true"]),
        cwd="/workspace" if workspace else None,
        env=env,
        allow_network=network,
        mounts=_mounts(resolved, workspace),
        secret_env={},
        timeout_s=max(1, int(timeout_s)),
        memory_mb=memory_mb,
        pids=pids,
    )
    reason = ""
    if missing:
        reason = (
            f"the host cannot enforce {resolved.value!r}: missing "
            + ", ".join(missing)
        )
    return ProfilePlan(
        profile=resolved,
        backend=str(getattr(backend, "name", "unknown")),
        spec=spec,
        workspace=str(workspace) if workspace else None,
        allowlist=tuple(_normalize_host(h) for h in allowlist if _normalize_host(h)),
        enforceable=not missing,
        missing=missing,
        reason=reason,
    )


def executor_guard(sandbox: Any = None) -> tuple[Optional[str], Optional[ProfilePlan]]:
    """The check an executor makes before it spawns anything (C6).

    Returns `(refusal, plan)`. `(None, None)` means no profile is configured and
    the executor keeps its existing behavior. `(reason, plan)` means the operator
    asked for an isolation promise this host cannot keep — the executor must
    refuse, even if its caller bypassed the gateway.
    """
    profile = configured_profile()
    if profile is None:
        return None, None
    plan = resolve_profile(profile, sandbox=sandbox)
    if not plan.enforceable:
        return (plan.reason or f"sandbox profile {profile.value!r} is not enforceable here"), plan
    return None, plan


def describe_profiles(sandbox: Any = None) -> list[dict[str, Any]]:
    """Per-profile enforceability on this host (for `/health` and docs)."""
    backend = sandbox or get_sandbox()
    caps = dict(backend.capabilities() or {})
    proxy = egress_proxy()
    caps["egressProxy"] = bool(proxy and caps.get("networkIsolation"))
    report: list[dict[str, Any]] = []
    for profile in SandboxProfile:
        missing = [name for name in REQUIRED_CAPABILITIES[profile] if not caps.get(name)]
        report.append({
            "profile": profile.value,
            "backend": str(getattr(backend, "name", "unknown")),
            "enforceable": not missing,
            "missing": missing,
        })
    return report


__all__ = [
    "EGRESS_PROXY_ENV",
    "PROFILE_ENV",
    "REQUIRED_CAPABILITIES",
    "ProfilePlan",
    "SandboxProfile",
    "allowlist_permits",
    "configured_profile",
    "describe_profiles",
    "egress_proxy",
    "executor_guard",
    "parse_profile",
    "path_within",
    "resolve_profile",
]
