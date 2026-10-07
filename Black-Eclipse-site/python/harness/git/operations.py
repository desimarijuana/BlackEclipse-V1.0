"""The closed Git operation table — the ONLY place a git argv is defined.

A `GitOp` names an intent (`stage these files`), not a program. Its argv is
assembled from a fixed template plus VALIDATED values. The model never supplies
an executable, a flag, or a shell fragment: a value that looks like an option
(leading `-`), a pathspec-magic prefix (`:`), a NUL byte, or an out-of-range
value is refused here, before any process is started.

Why a table and not a matcher: a matcher over model-supplied strings is a policy
surface that grows with every new string. A table is closed, reviewable and
diffable, and its size is the size of the capability. This mirrors
`code/commands.py` exactly, extended to the full Git write surface.

Nothing here executes anything; `git/executor.py` owns execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import INVALID_ARGUMENT, UNSAFE_COMMAND, GitError

# ── Risk levels (machine-readable; the safety engine consumes them) ──────────
#
#   safe         — read-only; changes nothing.
#   caution      — mutates local state but is reversible or non-destructive.
#   dangerous    — can move/rewrite history or discard the index.
#   destructive  — discards uncommitted work or deletes refs/data.
#   critical     — can destroy remote history or is irreversible.
RISK_ORDER: tuple[str, ...] = ("safe", "caution", "dangerous", "destructive", "critical")

# Operations at or above this level always require an explicit approval.
CONFIRMATION_LEVEL = "dangerous"


def risk_level(value: str) -> int:
    try:
        return RISK_ORDER.index(value)
    except ValueError:
        return len(RISK_ORDER)  # an unknown level is treated as the highest risk


def requires_confirmation(risk: str) -> bool:
    return risk_level(risk) >= risk_level(CONFIRMATION_LEVEL)


# ── Value validation ──────────────────────────────────────────────────────────

# A plain ref / branch / tag name. Conservative: rejects a leading dash (option
# injection), whitespace, `..`, `@{`, a trailing `.lock`/`/`/`.`, and control
# bytes. Git's own `check-ref-format` is the final authority at execution time.
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/\-]{0,199}$")
# A revision expression (sha, HEAD~2, main...feature, tag^{commit}).
_REV_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/~^@{}\-]{0,199}$")
# A date expression (--since/--until): a strict, option-free token.
_DATE_RE = re.compile(r"^[A-Za-z0-9 :+TZ.\-]{1,40}$")
# A glob/pattern for grep/log filtering: no leading dash, no control bytes.
_PATTERN_RE = re.compile(r"^[^\x00-\x1f]{1,200}$")
# A git config key.
_CONFIG_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,254}$")


def is_plain_ref(name: str) -> bool:
    text = str(name or "").strip()
    if not _REF_RE.match(text):
        return False
    if ".." in text or "@{" in text or text.endswith((".", "/", ".lock")):
        return False
    return True


def is_plain_rev(spec: str) -> bool:
    text = str(spec or "").strip()
    if not _REV_RE.match(text):
        return False
    if text.startswith("-") or "\x00" in text:
        return False
    # A revision may use `..`/`...`/`^`/`~` but never a ref-injection `@{`.
    return True


def _reject_option_like(kind: str, value: str, name: str) -> None:
    """A value that begins with `-` (or pathspec magic `:`) is a flag, not data."""
    if kind in ("path", "message"):
        if kind == "path" and value.startswith(":"):
            raise GitError(INVALID_ARGUMENT, f"{name!r} uses an unsupported path form.")
        return
    if value.startswith("-"):
        raise GitError(UNSAFE_COMMAND, f"{name!r} may not start with a dash.")


@dataclass(frozen=True)
class GitArg:
    """One validated value an operation accepts.

    `kind` selects the validator: text | ref | rev | path | message | mode | int
    | date | pattern | config_key | enum.
    """

    name: str
    kind: str = "text"
    required: bool = False
    many: bool = False
    allowed: tuple[str, ...] = ()
    min_int: int = 0
    max_int: int = 1_000_000
    max_len: int = 2_000


def _validate_one(spec: GitArg, value: Any) -> Any:
    if value is None:
        if spec.required:
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is required.")
        return None
    if isinstance(value, bool):
        raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is not a valid value.")
    if spec.kind == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} must be a whole number.")
        if number < spec.min_int or number > spec.max_int:
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is out of range.")
        return number
    text = str(value)
    if "\x00" in text:
        raise GitError(INVALID_ARGUMENT, f"{spec.name!r} contains an invalid character.")
    if len(text) > spec.max_len:
        raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is too long.")
    if spec.kind == "enum":
        if text not in spec.allowed:
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is not an allowed value.")
        return text
    if spec.kind == "ref":
        if not is_plain_ref(text):
            raise GitError(UNSAFE_COMMAND, f"{spec.name!r} is not a plain name.")
        return text
    if spec.kind == "rev":
        if not is_plain_rev(text):
            raise GitError(UNSAFE_COMMAND, f"{spec.name!r} is not a plain version name.")
        return text
    if spec.kind == "date":
        if not _DATE_RE.match(text):
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is not a usable date.")
        return text
    if spec.kind == "config_key":
        if not _CONFIG_KEY_RE.match(text):
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is not a config key.")
        return text
    if spec.kind == "pattern":
        if not _PATTERN_RE.match(text) or text.startswith("-"):
            raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is not a usable pattern.")
        return text
    if spec.kind == "refspec":
        # A refspec may carry `:` (src:dst); a leading `+` is a FORCE push and is
        # never expressible — a force is only ever the explicit `forceWithLease`
        # flag, which the authorizer elevates to `critical`.
        if text.startswith("+") or text.startswith("-") or "\x00" in text or " " in text:
            raise GitError(UNSAFE_COMMAND, f"{spec.name!r} is not a plain refspec.")
        return text
    _reject_option_like(spec.kind, text, spec.name)
    return text


def validate_op_args(op: "GitOp", raw: dict[str, Any]) -> dict[str, Any]:
    """Validate model-supplied args against the op's GitArgs. Raises on any."""
    spec_by_name = {spec.name: spec for spec in op.args}
    unknown = set(raw or {}) - set(spec_by_name)
    if unknown:
        raise GitError(INVALID_ARGUMENT, f"unknown argument(s): {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    for name, spec in spec_by_name.items():
        value = (raw or {}).get(name)
        if spec.many:
            if value is None:
                if spec.required:
                    raise GitError(INVALID_ARGUMENT, f"{spec.name!r} is required.")
                out[name] = []
                continue
            if not isinstance(value, (list, tuple)):
                raise GitError(INVALID_ARGUMENT, f"{spec.name!r} must be a list.")
            if len(value) > 2_000:
                raise GitError(INVALID_ARGUMENT, f"{spec.name!r} has too many entries.")
            out[name] = [_validate_one(spec, item) for item in value]
        else:
            validated = _validate_one(spec, value)
            if validated is not None:
                out[name] = validated
    return out


@dataclass(frozen=True)
class GitOp:
    name: str
    build: Callable[[dict[str, Any]], list[str]]
    args: tuple[GitArg, ...] = ()
    mutating: bool = False
    effect: str = "read"                 # read | write | external_action
    network: bool = False                # contacts a remote
    risk: str = "safe"
    timeout_s: int = 30
    # A short, operator-facing description; never shown to the model verbatim.
    summary: str = ""


# ── Common builders (the executable is ALWAYS an absolute, closed token) ──────
#
# A builder receives the VALIDATED args plus the resolved absolute git path,
# passed as `_git`. The FIRST token is therefore never model text.

def _git_prefix(exe: str) -> list[str]:
    # `-c core.longpaths=true` on every invocation: on Windows, an unconfigured
    # git aborts a checkout with deep paths (the scaffold-kit templates exceed
    # MAX_PATH). Passing it per-command avoids mutating the operator's config,
    # exactly as `code/worktree.py` already does.
    return [exe, "-c", "core.longpaths=true", "-c", "advice.detachedHead=false"]


def _after(exe: str, *tokens: str) -> list[str]:
    return _git_prefix(exe) + list(tokens)


def _with_dash_dash(tokens: list[str]) -> list[str]:
    """Insert `--` before trailing path values so a path can never be a flag."""
    return tokens


__all__ = [
    "CONFIRMATION_LEVEL",
    "GitArg",
    "GitOp",
    "RISK_ORDER",
    "is_plain_ref",
    "is_plain_rev",
    "requires_confirmation",
    "risk_level",
    "validate_op_args",
]
