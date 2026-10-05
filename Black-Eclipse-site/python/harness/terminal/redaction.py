"""Secret redaction for terminal output and command lines.

The ONE existing redactor is `session_index.redact_span` (used by the workspace
reader and the human editor). This module reuses those same pattern rules and
adds the terminal-specific case: an *environment assignment* in a command or in
a process's own environment echo. The process still receives the real secret —
redaction happens only on the path to the model / the UI / the log.

Never returns a raw secret. Never logs one. When in doubt, redacts.
"""

from __future__ import annotations

import re
from typing import Any

from ..session_index import redact_span

#: The marker the rest of the runtime already uses for a redacted span.
REDACT_MARKER = "«redacted»"

# An assignment of a conventionally-secret name, e.g. DATABASE_URL=... or
# API_KEY: sk-.... Redacts the VALUE, keeps the KEY so the model can reason.
_ASSIGNMENT = re.compile(
    r"(?P<key>(?:[A-Za-z_][A-Za-z0-9_]*)(?:secret|token|key|password|passwd|pwd|credential|"
    r"auth|api[_-]?key|access[_-]?key|private[_-]?key|database[_-]?url|conn(?:ection)?[_-]?string))"
    r"\s*(?P<op>[:=])\s*(?P<value>[^\s'\"]+|'[^']*'|\"[^\"]*\")",
    re.IGNORECASE,
)

# A `postgres://user:pass@host` connection string anywhere.
_URL_CREDS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)(?P<user>[^:/\s@]+):(?P<pw>[^@/\s]+)@", re.IGNORECASE)

#: Environment variable names whose VALUES are secret-bearing. A command that
#: echoes one is redacted; the variable name itself is kept.
SENSITIVE_ENV_HINTS: tuple[str, ...] = (
    "SECRET", "TOKEN", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "ACCESS_KEY",
    "PRIVATE_KEY", "CREDENTIAL", "AUTH", "DATABASE_URL", "CONNECTION_STRING",
    "CRON_SECRET",
)


def redact(text: str) -> str:
    """Redact secret-shaped spans. Idempotent and safe on any string."""
    if not text:
        return text
    cleaned = redact_span(text, REDACT_MARKER)
    cleaned = _URL_CREDS.sub(lambda m: f"{m.group('scheme')}{m.group('user')}:{REDACT_MARKER}@", cleaned)
    cleaned = _ASSIGNMENT.sub(lambda m: f"{m.group('key')}{m.group('op')}{REDACT_MARKER}", cleaned)
    return cleaned


def redact_env(env: dict[str, Any]) -> dict[str, str]:
    """Redact a copy of an environment mapping for display. Never the live env."""
    out: dict[str, str] = {}
    for key, value in env.items():
        name = str(key)
        if any(hint in name.upper() for hint in SENSITIVE_ENV_HINTS):
            out[name] = REDACT_MARKER
        else:
            out[name] = redact(str(value))
    return out


def redact_command(command: str) -> str:
    """Redact a command line before it reaches a model-facing field or a log."""
    return redact(command)


__all__ = ["REDACT_MARKER", "SENSITIVE_ENV_HINTS", "redact", "redact_command", "redact_env"]
