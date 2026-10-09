"""Resource-scoped permissions — never a global boolean.

A permission is a triple `(permission, resource-glob, scope)` with optional
constraints (environment / session / task / expiry). The canonical textual form
is `<domain>.<permission>:<resource-glob>`, e.g.

    filesystem.write:/workspace/project/**
    shell.execute:python
    network.request:https://api.github.com/**

Matching is exact on the permission class and glob-based on the resource. The glob
supports `*` (within a path segment / any chars except `/`) and `**` (across
segments). Filesystem resources are canonicalized before matching so `a/../b` and
symlink tricks cannot smuggle a grant.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import Environment, Permission, new_id, now_ts


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a permission glob to a regex.

    `**` matches any characters including `/`; `*` matches any characters except
    `/`; `?` matches one character except `/`. Everything else is escaped. The
    whole match is anchored.
    """
    out = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def canonicalize_resource(resource: str) -> str:
    """Best-effort canonicalization for matching only.

    For path-like resources this normalizes separators and resolves `.`/`..`
    lexically (NOT via the filesystem, which could block). Authorities that need a
    real-path decision still call `code.policy.resolve_within`; this is only to
    make the permission glob match what the caller meant.
    """
    text = str(resource or "").strip()
    if not text:
        return ""
    # Only path-like resources (absolute, or with a separator) are normalized.
    if os.sep in text or "/" in text or "\\" in text:
        normalized = text.replace("\\", "/")
        # URL authority (scheme://) is left alone beyond separator normalization.
        if "://" in normalized:
            return normalized
        drive = ""
        if len(normalized) >= 2 and normalized[1] == ":":
            drive, normalized = normalized[:2], normalized[2:]
        absolute = normalized.startswith("/")
        parts: list[str] = []
        for part in normalized.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts and parts[-1] != "..":
                    parts.pop()
                elif not absolute:
                    parts.append("..")
                continue
            parts.append(part)
        result = "/".join(parts)
        if absolute:
            result = "/" + result if result else "/"
        return (drive + result) if drive else result
    return text


def resource_matches(pattern: str, resource: str) -> bool:
    """Whether a permission resource-glob covers a resource."""
    pattern = str(pattern or "").strip()
    resource = canonicalize_resource(resource)
    if pattern in ("", "*", "**"):
        return True
    if pattern == resource:
        return True
    try:
        if _glob_to_regex(pattern).match(resource):
            return True
    except re.error:
        return False
    # A bare domain should also cover its subdomains? No — that is an explicit
    # decision, not an implicit widening. Keep exact/glob only.
    return False


@dataclass
class PermissionGrant:
    """One concrete grant: permission class over a resource glob."""

    permission: Permission
    resource: str = "**"
    scope: str = ""  # workspace / resource scope; empty = session-scoped
    constraints: tuple[str, ...] = ()
    environment: Optional[Environment] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    issued_at: float = field(default_factory=now_ts)
    expires_at: Optional[float] = None
    revocable: bool = True
    revoked: bool = False
    grant_id: str = field(default_factory=lambda: new_id("perm"))
    source: str = "policy"

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= now_ts()

    @property
    def active(self) -> bool:
        return not self.revoked and not self.expired

    def to_text(self) -> str:
        return f"{self.permission.value}:{self.resource}"

    @classmethod
    def parse(cls, text: str, **kwargs: Any) -> "PermissionGrant":
        raw = str(text or "").strip()
        permission_text, _, resource = raw.partition(":")
        permission_text = permission_text.strip()
        # Accept both `write` and `filesystem.write`; the trailing segment names the
        # permission class.
        perm_name = permission_text.rsplit(".", 1)[-1]
        try:
            permission = Permission(perm_name)
        except ValueError:
            permission = Permission.ADMIN
        return cls(permission=permission, resource=(resource or "**").strip() or "**", **kwargs)

    def covers(
        self,
        permission: Any,
        resource: str,
        *,
        environment: Environment,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        scope: str = "",
    ) -> bool:
        if not self.active:
            return False
        if not isinstance(permission, Permission):
            try:
                permission = Permission(str(permission).rsplit(".", 1)[-1].lower())
            except ValueError:
                return False
        if permission is not self.permission:
            return False
        if self.environment is not None and self.environment is not environment:
            return False
        if self.session_id is not None and session_id is not None and self.session_id != session_id:
            return False
        if self.session_id is not None and session_id is None:
            return False
        if self.task_id is not None and task_id is not None and self.task_id != task_id:
            return False
        if self.scope and scope and self.scope != scope:
            return False
        if self.scope and not scope:
            return False
        return resource_matches(self.resource, resource)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.grant_id,
            "permission": self.permission.value,
            "resource": self.resource,
            "scope": self.scope,
            "constraints": list(self.constraints),
            "environment": self.environment.value if self.environment else None,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "revocable": self.revocable,
            "revoked": self.revoked,
            "source": self.source,
            "active": self.active,
        }


class PermissionSet:
    """A subject's collection of grants, with an `allows` query.

    A subject is allowed iff at least one active grant covers the requested
    permission/resource in the same scope. No grant ⇒ denied.
    """

    def __init__(self, grants: Optional[Iterable[PermissionGrant]] = None) -> None:
        self._grants: list[PermissionGrant] = list(grants or [])

    def add(self, grant: PermissionGrant) -> PermissionGrant:
        self._grants.append(grant)
        return grant

    def grant_text(self, text: str, **kwargs: Any) -> PermissionGrant:
        return self.add(PermissionGrant.parse(text, **kwargs))

    def remove(self, grant_id: str) -> bool:
        before = len(self._grants)
        self._grants = [g for g in self._grants if g.grant_id != grant_id]
        return len(self._grants) != before

    def revoke(self, grant_id: str) -> bool:
        for grant in self._grants:
            if grant.grant_id == grant_id and grant.revocable:
                grant.revoked = True
                return True
        return False

    def purge_expired(self) -> int:
        before = len(self._grants)
        self._grants = [g for g in self._grants if not g.expired]
        return before - len(self._grants)

    def covers(
        self,
        permission: Permission,
        resource: str = "**",
        *,
        environment: Environment = Environment.DEVELOPMENT,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        scope: str = "",
    ) -> Optional[PermissionGrant]:
        """The first active grant that covers the request, or None."""
        for grant in self._grants:
            if grant.covers(
                permission,
                resource,
                environment=environment,
                session_id=session_id,
                task_id=task_id,
                scope=scope,
            ):
                return grant
        return None

    def allows(self, permission: Permission, resource: str = "**", **kwargs: Any) -> bool:
        return self.covers(permission, resource, **kwargs) is not None

    def snapshot(self) -> list[dict[str, Any]]:
        return [g.to_dict() for g in self._grants]

    def __len__(self) -> int:
        return len(self._grants)


def fnmatch_name(pattern: str, value: str) -> bool:
    """Case-insensitive-ish exact/glob match for non-path resources (tool names,
    programs, domains). `*` is allowed; path semantics do not apply."""
    pattern = str(pattern or "").strip()
    value = str(value or "").strip()
    if pattern in ("", "*", "**"):
        return True
    if pattern == value:
        return True
    try:
        return fnmatch.fnmatchcase(value, pattern) or fnmatch.fnmatch(value, pattern)
    except Exception:  # noqa: BLE001 - a bad pattern never grants
        return False


__all__ = [
    "PermissionGrant",
    "PermissionSet",
    "canonicalize_resource",
    "fnmatch_name",
    "resource_matches",
]
