"""Central filesystem permission system — one authority, all fs tools consult it.

The rule from `code/policy.py` is preserved exactly: the autonomy profile is the
base grant and a caller-supplied config can only NARROW, never widen. This module
adds the per-CAPABILITY view the file tools need (read/write/create/delete/move/
copy/rename/watch/search) without re-implementing path safety — it delegates to
`policy.decide_write` and `policy.resolve_within`.

No tool hard-codes a permission decision. A tool names the capability it needs,
calls `require`, and maps the `FsError` to its result.
"""

from __future__ import annotations

from typing import Any, FrozenSet, Optional

from .. import policy
from .errors import PERMISSION_DENIED, PATH_NOT_ALLOWED, FsError

# The complete capability vocabulary (the task's list).
READ = "read"
WRITE = "write"
CREATE = "create"
DELETE = "delete"
MOVE = "move"
COPY = "copy"
RENAME = "rename"
WATCH = "watch"
SEARCH = "search"

CAPABILITIES: tuple[str, ...] = (
    READ, WRITE, CREATE, DELETE, MOVE, COPY, RENAME, WATCH, SEARCH,
)

# Which code-policy verb each capability needs. Every mutating capability needs
# `code.write`; the read-side needs `code.read`.
_CAPABILITY_VERB: dict[str, str] = {
    READ: "code.read",
    SEARCH: "code.read",
    WATCH: "code.read",
    WRITE: "code.write",
    CREATE: "code.write",
    DELETE: "code.write",
    MOVE: "code.write",
    COPY: "code.write",
    RENAME: "code.write",
}

# Capabilities that resolve a path through the protected/ignored/escape gate.
_PATH_CAPABILITIES: FrozenSet[str] = frozenset({
    WRITE, CREATE, DELETE, MOVE, COPY, RENAME,
})

_MUTATING: FrozenSet[str] = frozenset({WRITE, CREATE, DELETE, MOVE, COPY, RENAME})


def resolve_config(raw: Optional[dict[str, Any]]) -> dict[str, bool]:
    """Normalize an operator-supplied `filesystem` permission block.

    Only known capabilities are read; an unknown key is ignored (it can never
    grant anything). A missing key leaves the capability to the autonomy profile.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    for name, value in raw.items():
        if name in CAPABILITIES:
            out[name] = bool(value)
    return out


def grants_for(autonomy: Optional[str]) -> FrozenSet[str]:
    """The code verbs an autonomy profile holds. Unknown profile → nothing."""
    return policy.code_grants(str(autonomy)) if autonomy else frozenset()


def has_verb(autonomy: Optional[str], verb: str) -> bool:
    return verb in grants_for(autonomy)


def capability_enabled(
    autonomy: Optional[str],
    capability: str,
    config: Optional[dict[str, Any]] = None,
) -> bool:
    """Whether the profile grants the capability AND the config does not deny it.

    Config is a STRICT narrowing: `{"delete": False}` denies delete even for a
    profile that holds code.write. A config cannot enable a capability the
    profile does not grant.
    """
    verb = _CAPABILITY_VERB.get(capability)
    if verb is None:
        return False
    if not has_verb(autonomy, verb):
        return False
    normalized = resolve_config(config)
    if capability in normalized and not normalized[capability]:
        return False
    return True


def require(
    actor: Any,
    binding: Any,
    capability: str,
    rel_path: str = "",
    *,
    config: Optional[dict[str, Any]] = None,
) -> None:
    """Authorize one capability on one path, or raise `FsError`.

    Read-side capabilities check the profile only. Mutating capabilities run the
    full `policy.decide_write` gate (profile + protected + ignored + confinement)
    so a protected path is refused before any byte is touched — exactly as the
    existing patch engine does.
    """
    autonomy = getattr(actor, "autonomy", None)
    if not capability_enabled(autonomy, capability, config):
        raise FsError(
            PERMISSION_DENIED,
            "This task is not allowed to make that change.",
            path=rel_path,
        )
    if capability in _PATH_CAPABILITIES:
        decision = policy.decide_write(actor, binding, rel_path)
        if not decision.allowed:
            # Map the policy's own code onto the standard vocabulary where it
            # names a workspace boundary (the finer codes stay as-is).
            code = decision.code
            if code in ("OUTSIDE_WORKSPACE", "PATH_OUTSIDE_WORKSPACE"):
                code = PATH_NOT_ALLOWED
            raise FsError(code, decision.reason, path=rel_path)


__all__ = [
    "CAPABILITIES",
    "COPY",
    "CREATE",
    "DELETE",
    "MOVE",
    "READ",
    "RENAME",
    "SEARCH",
    "WATCH",
    "WRITE",
    "capability_enabled",
    "grants_for",
    "has_verb",
    "require",
    "resolve_config",
]
