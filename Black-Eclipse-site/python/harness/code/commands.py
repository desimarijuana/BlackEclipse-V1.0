"""The command-class table — the ONLY place a command is defined.

A command class names an intent (typecheck this worktree), not a program. The
argv is assembled here from a fixed template plus validated arguments. The model
never supplies an executable, a flag, or a shell fragment.

Why a table and not a matcher: a matcher over user-supplied strings is a policy
surface that grows with every new string. A table is closed, reviewable, diffable
in code review, and its size is the size of the capability.

Nothing in this module executes anything; `code/sandbox.py` owns execution.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# The vendored interpreter is referenced HERE and nowhere else. The bare `python`
# shim lacks langgraph/pytest, so it is never resolved from PATH.
VENDORED_RELPATH = "scripts/vendor/python/python.exe"
VENDORED_POSIX_RELPATH = "scripts/vendor/python/bin/python3"


def _repo_root() -> Path:
    from ..eclipse_memory.config import repo_root  # noqa: PLC0415

    return Path(repo_root())


def _resolve_executable(name: str) -> Optional[str]:
    """Resolve an executable to an absolute path, or None when absent.

    `scripts/vendor/...` is resolved against the repo root (it is gitignored and
    absent inside a worktree). Everything else is resolved on PATH via
    `shutil.which`. A missing executable makes its classes UNAVAILABLE — never
    silently substituted.
    """
    if name.startswith("scripts/"):
        candidate = _repo_root() / name
        if candidate.is_file():
            return str(candidate)
        if os.name == "posix" and name == VENDORED_RELPATH:
            posix = _repo_root() / VENDORED_POSIX_RELPATH
            if posix.is_file():
                return str(posix)
        return None
    return shutil.which(name)


@dataclass(frozen=True)
class ArgSpec:
    name: str
    # A closed set of allowed values, or None for a pattern-validated string.
    allowed: tuple[str, ...] = ()
    pattern: Optional[str] = None          # re.fullmatch, applied in code
    required: bool = False
    many: bool = False                     # the value is a list of strings


@dataclass(frozen=True)
class CommandClass:
    name: str                              # must be in policy.COMMAND_CLASSES
    executable: str                        # a key into EXECUTABLES below
    argv_template: Callable[[dict[str, Any], str], list[str]]
    args: tuple[ArgSpec, ...] = ()
    timeout_s: int = 300
    output_cap_bytes: int = 2_000_000
    network: bool = False
    cwd: str = "workspace"                 # always the worktree root
    effect: str = "read"                   # "read" | "write" | "external_action"


# The closed executable list. `resolve_executable` turns each into an absolute
# path at call time; a missing one makes its classes UNAVAILABLE.
EXECUTABLES: dict[str, str] = {
    "node": "node",
    "npm": "npm",
    "npx": "npx",
    "python": VENDORED_RELPATH,
    "pytest": VENDORED_RELPATH,             # invoked as: python -m pytest
    "git": "git",
}

# The argv templates receive the validated args and the resolved executable path,
# so the FIRST token is always an absolute, closed value — never model text.
COMMAND_CLASSES: dict[str, CommandClass] = {
    "typecheck": CommandClass(
        name="typecheck", executable="npx",
        argv_template=lambda a, exe: [exe, "tsc", "--noEmit"],
        timeout_s=300,
    ),
    "lint": CommandClass(
        name="lint", executable="npx",
        argv_template=lambda a, exe: [exe, "eslint", "."],
        timeout_s=300,
    ),
    "unit_test": CommandClass(
        name="unit_test", executable="npm",
        argv_template=lambda a, exe: [exe, "run", "test", "--", *a.get("files", [])],
        args=(ArgSpec(name="files", pattern=r"[\w./\\-]{1,200}", many=True),),
        timeout_s=600,
    ),
    "python_test": CommandClass(
        name="python_test", executable="pytest",
        argv_template=lambda a, exe: [exe, "-m", "pytest", *a.get("paths", []), "-q"],
        args=(ArgSpec(name="paths", pattern=r"[\w./\\-]{1,200}", many=True),),
        timeout_s=900,
    ),
    "build": CommandClass(
        name="build", executable="npm",
        argv_template=lambda a, exe: [exe, "run", "build"],
        timeout_s=900,
    ),
    "format_check": CommandClass(
        name="format_check", executable="npx",
        argv_template=lambda a, exe: [exe, "prettier", "--check", *a.get("files", [])],
        args=(ArgSpec(name="files", pattern=r"[\w./\\-]{1,200}", many=True),),
        timeout_s=120,
    ),
    "git_read": CommandClass(
        name="git_read", executable="git",
        argv_template=lambda a, exe: [exe, a["subcommand"], *a.get("extra", [])],
        args=(
            # CLOSED set: no `config`, no `remote`, no `push`, no `reset`, no
            # `clean`, no `checkout`, no `commit`, no `stash`. Absent by
            # construction, so unreachable by any argument.
            ArgSpec(name="subcommand", required=True,
                    allowed=("status", "log", "diff", "show", "ls-files", "rev-parse", "worktree")),
            ArgSpec(name="extra", pattern=r"[\w./\\^~:@{}[\]-]{1,200}", many=True),
        ),
        timeout_s=60,
    ),
    # OFF by default (operator flag). The only class with network=True; uses
    # --ignore-scripts so a postinstall script cannot run.
    "dependency_install": CommandClass(
        name="dependency_install", executable="npm",
        argv_template=lambda a, exe: [exe, "install", "--no-save", "--ignore-scripts", *a["packages"]],
        args=(ArgSpec(name="packages", pattern=r"[@\w./\\-]{1,200}", required=True, many=True),),
        timeout_s=600,
        network=True,
        effect="external_action",
    ),
}

# Classes that require an operator flag (default OFF) in addition to the actor's
# autonomy grant. `dependency_install` installs code from a registry.
OPERATOR_GATED_CLASSES = frozenset({"dependency_install"})


class CommandUnavailable(RuntimeError):
    """Raised when a class's executable is not present. Never silently substituted."""

    def __init__(self, code: str, reason: str, *, command_class: str = "") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.command_class = command_class


# Plain, user-facing copy for every command refusal code: (one sentence, a next
# step). This is DATA, not branching UI, and it mirrors `src/lib/i18n`. It is
# asserted against `policy.PLAIN_LANGUAGE_DENYLIST` by the plain-language gate —
# a refusal names the job, never the mechanism. The internal `reason` (operator
# facing) stays in the exception; this is what a person sees.
COMMAND_REFUSAL_COPY: dict[str, dict[str, str]] = {
    "COMMAND_NOT_ALLOWLISTED": {
        "reason": "That isn’t a check I’m allowed to run.",
        "recovery": "I can run a check for you instead — tests, types, lint, a build, or the project’s history.",
    },
    "COMMAND_NOT_ENABLED": {
        "reason": "I’m not allowed to add software to the project in this session.",
        "recovery": "Ask the person who set this up to allow adding software, then try again.",
    },
    "COMMAND_EXECUTABLE_MISSING": {
        "reason": "The tool I’d need for that check isn’t installed on this computer.",
        "recovery": "Install the missing tool, then ask me to run the check again.",
    },
    "COMMAND_ARG_INVALID": {
        "reason": "One of the details for that check wasn’t something I could use.",
        "recovery": "Ask again with simpler details, or tell me what you’d like checked in plain words.",
    },
    "SANDBOX_UNAVAILABLE": {
        "reason": "I can’t run checks safely on this computer right now, so I won’t run them.",
        "recovery": "Run the check on a computer where Eclipse can isolate it.",
    },
    "PROFILE_DENIED": {
        "reason": "I’m not set up to run checks in this session.",
        "recovery": "Ask for the check in a session that is allowed to run them.",
    },
    "WORKSPACE_UNBOUND": {
        "reason": "There’s no project open for me to run a check in.",
        "recovery": "Open a project first, then ask for the check again.",
    },
    "COMMAND_REFUSED": {
        "reason": "I didn’t run that check because it isn’t one I’m allowed to run.",
        "recovery": "Ask for a check instead — tests, types, lint or a build.",
    },
}


def refusal_copy(code: str) -> dict[str, str]:
    """The plain sentence + recovery for a refusal code (fallback: generic)."""
    return COMMAND_REFUSAL_COPY.get(code, COMMAND_REFUSAL_COPY["COMMAND_REFUSED"])


def _validate_arg(spec: ArgSpec, raw: Any) -> Any:
    if raw is None:
        if spec.required:
            raise CommandUnavailable("COMMAND_ARG_INVALID", f"{spec.name!r} is required")
        return [] if spec.many else None
    values = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for value in values:
        text = str(value)
        if "\x00" in text:
            raise CommandUnavailable("COMMAND_ARG_INVALID", f"{spec.name!r} contains a NUL byte")
        # A path argument may never traverse above the worktree — the class's
        # `cwd` is the worktree root, so `..` would reach the operator's checkout.
        if ".." in text.replace("\\", "/").split("/"):
            raise CommandUnavailable(
                "COMMAND_ARG_INVALID", f"{spec.name!r} points outside the task's folder"
            )
        if spec.allowed and text not in spec.allowed:
            raise CommandUnavailable("COMMAND_ARG_INVALID", f"{spec.name!r} is not an allowed value")
        if spec.pattern and not re.fullmatch(spec.pattern, text):
            raise CommandUnavailable("COMMAND_ARG_INVALID", f"{spec.name!r} is not a valid value")
        out.append(text)
    if spec.many:
        return out
    return out[0] if out else (None if not spec.required else _missing(spec))


def _missing(spec: ArgSpec) -> Any:
    raise CommandUnavailable("COMMAND_ARG_INVALID", f"{spec.name!r} is required")


def validate_args(command_class: CommandClass, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Validate model-supplied args against the class's ArgSpecs. Raises on any."""
    spec_by_name = {spec.name: spec for spec in command_class.args}
    unknown = set(raw_args or {}) - set(spec_by_name)
    if unknown:
        raise CommandUnavailable(
            "COMMAND_ARG_INVALID",
            f"unknown argument(s): {', '.join(sorted(unknown))}",
            command_class=command_class.name,
        )
    validated: dict[str, Any] = {}
    for name, spec in spec_by_name.items():
        value = _validate_arg(spec, (raw_args or {}).get(name))
        if value not in (None, []):
            validated[name] = value
    return validated


def executable_path(command_class: CommandClass) -> str:
    """The absolute executable path, or raise CommandUnavailable."""
    name = EXECUTABLES.get(command_class.executable)
    if not name:
        raise CommandUnavailable(
            "COMMAND_NOT_ALLOWLISTED",
            f"no executable is declared for {command_class.name!r}",
            command_class=command_class.name,
        )
    resolved = _resolve_executable(name)
    if not resolved:
        raise CommandUnavailable(
            "COMMAND_EXECUTABLE_MISSING",
            f"the tool for {command_class.name!r} is not installed here",
            command_class=command_class.name,
        )
    return resolved


def resolve_class(name: str, *, operator_flags: Optional[dict[str, bool]] = None) -> CommandClass:
    """Return the class (argv-ready), or raise CommandUnavailable.

    Raises when the class is unknown, its executable is absent, or it is
    operator-gated and the flag is off.
    """
    from . import policy  # noqa: PLC0415

    command_class = COMMAND_CLASSES.get(str(name))
    if command_class is None or command_class.name not in policy.COMMAND_CLASSES:
        raise CommandUnavailable("COMMAND_NOT_ALLOWLISTED", f"unknown command class {name!r}")
    if command_class.name in OPERATOR_GATED_CLASSES:
        flags = operator_flags or {}
        if not bool(flags.get(command_class.name)):
            raise CommandUnavailable(
                "COMMAND_NOT_ENABLED",
                f"{command_class.name!r} is not enabled by the operator",
                command_class=command_class.name,
            )
    executable_path(command_class)  # raises when absent
    return command_class


def build_argv(command_class: CommandClass, raw_args: dict[str, Any]) -> list[str]:
    """Validate args and assemble the argv. The executable is absolute/closed."""
    validated = validate_args(command_class, raw_args or {})
    exe = executable_path(command_class)
    argv = command_class.argv_template(validated, exe)
    if not argv or not isinstance(argv, list) or not all(isinstance(t, str) for t in argv):
        raise CommandUnavailable("COMMAND_MALFORMED", f"{command_class.name!r} produced no argv")
    return argv


__all__ = [
    "ArgSpec",
    "COMMAND_CLASSES",
    "COMMAND_REFUSAL_COPY",
    "CommandClass",
    "CommandUnavailable",
    "EXECUTABLES",
    "OPERATOR_GATED_CLASSES",
    "VENDORED_RELPATH",
    "build_argv",
    "executable_path",
    "refusal_copy",
    "resolve_class",
    "validate_args",
]
