"""Generic terminal execution — the opencode-style command tool, gated.

This is the ONE place a model-supplied command may run without a fixed command
class. It exists because the user explicitly asked for real terminal access
("allow access etc"), and it is built so the safety rule (README §3.5) still
holds: a command is classified BEFORE it runs, and the classification is
enforced in Python, never by a prompt.

Three classes, exactly as chosen:

  * ``allow`` — a program on the safe allowlist (interpreters, build tools, git,
    and read-only coreutils). Runs directly.
  * ``ask``   — anything else that is not destructive. Requires a per-workspace
    single-use approval; the effect authorizer refuses without one.
  * ``deny``  — destructive shapes (`rm -rf /`, `format`, `shutdown`, `sudo`,
    a download piped to a shell, ...). Hard-blocked, never approvable.

Execution is argv-based with NO shell (`shlex.split`), so a `; rm -rf` or a
`$(...)` in the command is inert text, not a second command. It runs through
`code/sandbox.py`, so the wall-clock, output and process-tree bounds apply
unchanged, in the bound workspace, with the scrubbed environment.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import policy
from . import sandbox
from .sandbox import RunSpec

MAX_COMMAND_CHARS = 4_000
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 900

# Programs that run without a prompt. Interpreters and build tools an agent
# legitimately needs, plus read-only inspection tools. Deliberately EXCLUDES
# network downloaders and shells (a shell would defeat the no-shell guarantee).
SAFE_PROGRAMS: frozenset[str] = frozenset({
    # interpreters / runtimes
    "python", "python3", "py", "node", "deno", "bun", "tsx", "ts-node",
    "ruby", "php", "java", "go", "cargo", "rustc", "dotnet",
    # package managers
    "npm", "npx", "pnpm", "yarn", "pip", "pip3", "uv", "poetry", "pipenv",
    # test / build / lint
    "pytest", "jest", "vitest", "mocha", "tsc", "eslint", "ruff", "black",
    "mypy", "prettier", "make", "cmake", "gradle", "mvn",
    # VCS (read-only-ish; write subcommands are still classified, see below)
    "git",
    # read-only inspection (POSIX + Windows aliases)
    "ls", "dir", "pwd", "cd", "cat", "type", "head", "tail", "wc",
    "find", "grep", "rg", "which", "where", "echo", "print", "tree",
    "stat", "file", "du", "sort", "uniq", "cut", "sed", "awk", "tr",
    # safe mutators the user expects a coding agent to use
    "mkdir", "touch", "cp", "copy", "mv", "move", "ln", "tee",
})

# Subcommands that escalate a `git` invocation from read to write. A write git
# command is not auto-allowed even though `git` is safe.
_GIT_WRITE_SUBCOMMANDS = frozenset({
    "push", "reset", "clean", "rebase", "merge", "checkout", "switch",
    "commit", "add", "rm", "mv", "stash", "cherry-pick", "revert", "filter-branch",
})

# Programs that are ALWAYS refused, regardless of arguments. A downloader run
# directly (not piped) is `ask`, but the names below are destructive/exfil
# shaped and never run.
DENY_PROGRAMS: frozenset[str] = frozenset({
    "rm", "rmdir", "del", "erase", "format", "mkfs", "fdisk", "diskpart",
    "shutdown", "reboot", "halt", "poweroff", "reg", "regedit", "net",
    "sudo", "su", "runas", "takeown", "icacls", "cacls", "attrib",
    "dd", "shred", "wipefs", "mkswap",
    "curl", "wget", "invoke-webrequest", "iwr", "certutil", "bitsadmin",
    # a shell would let the caller smuggle an arbitrary second command
    "sh", "bash", "zsh", "fish", "cmd", "powershell", "pwsh", "csh", "ksh",
})

# Argument substrings that turn a would-be-safe command destructive.
_DENY_ARGS = ("rm -rf /", "rm -rf /*", "--no-preserve-root", "> /dev/sd", "mkfs.")

# Shell metacharacters. There is NO shell, so a pipeline/chain/redirect cannot
# work as written; refuse it rather than silently run the literal tokens as a
# different command than the caller wrote.
_METACHAR_TOKENS = frozenset({"|", "||", "&&", ";", "&", ">", ">>", "<", "<<"})
_METACHAR_RAW = ("$(", "`")


def _program_of(tokens: list[str]) -> str:
    first = tokens[0] if tokens else ""
    name = os.path.basename(str(first).replace("\\", "/")).casefold()
    for suffix in (".exe", ".cmd", ".bat", ".com", ".py", ".sh"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


@dataclass(frozen=True)
class CommandVerdict:
    kind: str          # "allow" | "ask" | "deny"
    program: str
    reason: str        # one plain sentence, safe to show a person

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "program": self.program, "reason": self.reason}


def classify(command: str) -> CommandVerdict:
    """Classify a command string into allow / ask / deny. Deterministic, pure."""
    text = str(command or "").strip()
    if not text:
        return CommandVerdict("deny", "", "There was no command to run.")
    if len(text) > MAX_COMMAND_CHARS:
        return CommandVerdict("deny", "", "That command is too long to run.")
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        # Unbalanced quotes etc. — refuse rather than guess the tokenization.
        return CommandVerdict("deny", "", "That command could not be read safely.")
    if not tokens:
        return CommandVerdict("deny", "", "There was no command to run.")
    program = _program_of(tokens)
    lowered = text.casefold()
    # No shell: a pipeline / chain / redirect / substitution cannot run as
    # written, so refuse instead of running the literal tokens as some other
    # command than the one the caller wrote.
    if any(tok in _METACHAR_TOKENS for tok in tokens) or any(m in text for m in _METACHAR_RAW):
        return CommandVerdict("deny", program, "That command chains several commands together, which I can't run safely.")
    if any(bad in lowered for bad in _DENY_ARGS):
        return CommandVerdict("deny", program, "That command could damage the computer, so I did not run it.")
    if program in DENY_PROGRAMS:
        return CommandVerdict("deny", program, "That command can damage the computer or fetch things I can't run, so I did not run it.")
    if program in ("git",) and len(tokens) > 1:
        sub = str(tokens[1]).casefold().lstrip("-")
        if sub in _GIT_WRITE_SUBCOMMANDS:
            return CommandVerdict("ask", program, "That changes the project's history and needs your go-ahead.")
    if program in SAFE_PROGRAMS:
        return CommandVerdict("allow", program, "That command is safe to run.")
    return CommandVerdict("ask", program, "That command isn't one I run automatically, so it needs your go-ahead.")


def build_run_spec(
    command: str, *, cwd: Path, timeout_s: Optional[int] = None,
    env_extra: Optional[dict[str, str]] = None,
) -> RunSpec:
    """Build a RunSpec for an allowed command. Raises ValueError on a bad one.

    The cwd is the bound workspace root; the caller has already confirmed it.
    """
    verdict = classify(command)
    if verdict.kind == "deny":
        raise ValueError(verdict.reason)
    tokens = shlex.split(command, posix=True)
    if not tokens:
        raise ValueError("There was no command to run.")
    timeout = int(timeout_s or DEFAULT_TIMEOUT_S)
    timeout = max(1, min(timeout, MAX_TIMEOUT_S))
    base_env = {k: os.environ[k] for k in policy.SECRET_ENV_ALLOWLIST if k in os.environ}
    if env_extra:
        base_env.update({str(k): str(v) for k, v in env_extra.items()})
    return RunSpec(
        argv=list(tokens),
        cwd=Path(cwd),
        env=base_env,
        timeout_s=timeout,
        output_cap_bytes=sandbox.MAX_OUTPUT_CAP_BYTES,
        network=False,
    )


__all__ = [
    "CommandVerdict",
    "DEFAULT_TIMEOUT_S",
    "DENY_PROGRAMS",
    "MAX_COMMAND_CHARS",
    "MAX_TIMEOUT_S",
    "SAFE_PROGRAMS",
    "build_run_spec",
    "classify",
]
