"""MCP config variable interpolation (Phase 6, Milestone 1).

A committed/shared `mcp-servers.json` may reference `${VAR}`, `${env:VAR}` and the
editor built-ins `${workspaceFolder}`, `${userHome}`, `${pathSeparator}` — the
same vocabulary Cursor / Claude / VS Code use, so a snippet can be moved here
unchanged.

One pure function does the substitution. The resolution order is:

  1. the process environment (for a bare `${VAR}` or `${env:VAR}`);
  2. the built-ins (`${workspaceFolder}` -> repo root, `${userHome}` -> the user
     profile, `${pathSeparator}` -> the OS path separator).

Fail-closed rule: a **remote** `url`/`auth` value with an unresolved reference
must refuse the connection and name the variable — never send a literal
`${VAR}` (a guaranteed 401 that reads as a bad credential). Local stdio
`args`/`env` keep the literal placeholder when a variable is unset, exactly as
the editors do. An *empty* variable is treated as unset for the remote rule so a
blank env var cannot silently produce a broken URL.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..eclipse_memory.config import repo_root

# `${...}` with no nesting (the editors do not nest).
_VAR_RE = re.compile(r"\$\{([^}]+)\}")

BUILTIN_KEYS = ("workspaceFolder", "userHome", "pathSeparator")


class InterpolationError(ValueError):
    """A remote value referenced a variable that could not be resolved."""

    def __init__(self, variable: str, field: str) -> None:
        super().__init__(
            f"unresolved variable ${{{variable}}} in remote {field!r}: "
            "set it in the environment before connecting"
        )
        self.variable = variable
        self.field = field


def _builtin(key: str) -> Optional[str]:
    if key == "workspaceFolder":
        return repo_root()
    if key == "userHome":
        return os.path.expanduser("~")
    if key == "pathSeparator":
        return os.sep
    return None


def _resolve_key(key: str, env: dict[str, str]) -> Optional[str]:
    """Resolve one `${...}` key, or None when it cannot be resolved.

    A present-but-empty value counts as unresolved on the remote path; the
    caller decides whether that is fatal (remote) or a literal fallback (local).
    """
    key = key.strip()
    if key.startswith("env:"):
        key = key[4:].strip()
    builtin = _builtin(key)
    if builtin is not None:
        return builtin
    value = env.get(key)
    return value if value else None


def interpolate(text: str, env: Optional[dict[str, str]] = None) -> tuple[str, list[str]]:
    """Substitute variables in one string.

    Returns `(result, unresolved)`. The result keeps the literal `${VAR}` for any
    variable that could not be resolved (the local-stdio behavior); `unresolved`
    names each such variable so a remote caller can fail closed.
    """
    if not text or "${" not in text:
        return text, []
    env = dict(os.environ if env is None else env)
    unresolved: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        raw = match.group(1)
        key = raw[4:].strip() if raw.strip().startswith("env:") else raw.strip()
        value = _resolve_key(raw, env)
        if value is None:
            if key not in unresolved:
                unresolved.append(key)
            return match.group(0)
        return value

    return _VAR_RE.sub(_sub, text), unresolved


def interpolate_remote(text: str, field: str, env: Optional[dict[str, str]] = None) -> str:
    """Interpolate a remote `url`/`auth` value, refusing an unresolved reference."""
    result, unresolved = interpolate(text, env)
    if unresolved:
        raise InterpolationError(unresolved[0], field)
    return result


__all__ = [
    "interpolate",
    "interpolate_remote",
    "InterpolationError",
    "BUILTIN_KEYS",
]
