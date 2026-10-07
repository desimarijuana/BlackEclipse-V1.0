"""The controlled Git execution engine.

Every git child process in the subsystem flows through `run`. It:

  * resolves the `git` executable to an ABSOLUTE path (never a bare name — a
    Windows `.cmd` shim cannot be spawned by `subprocess` and a bare name could
    be shadowed on PATH);
  * assembles argv from a CLOSED `GitOp` builder plus VALIDATED values only;
  * runs with NO shell, a scrubbed environment (`policy.SECRET_ENV_ALLOWLIST`),
    an explicit cwd, a bounded wall-clock timeout and a hard output cap;
  * captures stdout and stderr separately (stderr is operator-facing detail,
    never model-facing prose);
  * maps a non-zero exit to a structured `GitError` via `errors.classify_stderr`;
  * never raises for an ordinary git failure — it returns a `GitResult`.

`run` is synchronous. Git operations are short-lived; an agent tool calls it via
`asyncio.to_thread` so a slow fetch cannot block the event loop.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..code import policy
from . import errors
from .catalog import CATALOG
from .errors import GitError
from .operations import GitOp, validate_op_args

GIT_TIMEOUT_S = 60
GIT_NETWORK_TIMEOUT_S = 180
MAX_OUTPUT_BYTES = 4_000_000        # matches code/sandbox MAX_OUTPUT_CAP_BYTES
MAX_STDERR_BYTES = 64_000
# A hard ceiling on the number of argv tokens an op may produce. A build that
# exceeds this is a bug, and this bounds a pathological pathspec list.
MAX_ARGV_TOKENS = 4_000

_GIT_CACHE: Optional[str] = None


def resolve_git() -> Optional[str]:
    """The absolute path to `git`, or None when it is not installed.

    Resolved once and cached. Windows `.exe`/`.cmd` are resolved by
    `shutil.which`; a bare name is never returned, so `subprocess` can spawn it.
    """
    global _GIT_CACHE
    if _GIT_CACHE is not None:
        return _GIT_CACHE or None
    found = shutil.which("git")
    _GIT_CACHE = found or ""
    return found or None


def set_git_path(path: Optional[str]) -> None:
    """TEST SEAM: force the resolved git path (or None to re-detect)."""
    global _GIT_CACHE
    _GIT_CACHE = path or ""


def _scrubbed_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    """ONLY `policy.SECRET_ENV_ALLOWLIST` keys; proxy + harness secrets dropped.

    Mirrors `code/sandbox.build_env`. GIT_TERMINAL_PROMPT=0 makes a missing
    credential FAIL instead of hanging on an interactive prompt — the runtime has
    no TTY, so a prompt would otherwise block until the timeout.
    """
    env = {k: os.environ[k] for k in policy.SECRET_ENV_ALLOWLIST if k in os.environ}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY",
                "NO_PROXY", "no_proxy", "CRON_SECRET", "HARNESS_CALLBACK_TOKEN"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    # Fail closed on an interactive credential prompt; never hang.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"  # never take the index lock for a read
    # The runtime has no TTY. Any git command that would open an editor (a plain
    # merge/commit, `rebase --continue`) must instead take the deterministic
    # default. Without these, a merge blocks forever on `vi`/`notepad`.
    env["GIT_EDITOR"] = "true"
    env["GIT_SEQUENCE_EDITOR"] = "true"
    env["GIT_MERGE_AUTOEDIT"] = "no"
    env["GIT_PAGER"] = "cat"
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


@dataclass
class GitResult:
    """The outcome of one git invocation. `ok` is the ONLY success signal."""

    ok: bool
    argv: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: int = 0
    truncated: bool = False
    total_chars: int = 0
    code: str = ""
    error: Optional[GitError] = None

    def raise_for_error(self) -> "GitResult":
        if not self.ok and self.error is not None:
            raise self.error
        return self

    def stdout_bytes(self) -> bytes:
        return self.stdout.encode("utf-8")


def build_argv(op_name: str, raw_args: Optional[dict[str, Any]], *, git_path: Optional[str] = None) -> tuple[GitOp, list[str]]:
    """Validate args and assemble the argv for one named op.

    Raises `GitError` for an unknown op, an invalid value, an unsafe token, or
    when git is not installed. The first argv token is ALWAYS the absolute git
    path with the fixed `-c` prefix; it is never model text.
    """
    op = CATALOG.get(str(op_name))
    if op is None:
        raise GitError(errors.UNSAFE_COMMAND, "That version operation is not one Eclipse can perform.")
    validated = validate_op_args(op, raw_args or {})
    exe = git_path or resolve_git()
    if not exe:
        raise GitError(errors.GIT_UNAVAILABLE, "Git is not installed on this computer.")
    argv = op.build(validated, exe)
    if not argv or not all(isinstance(t, str) and t for t in argv):
        raise GitError(errors.GIT_FAILED, "The version operation could not be prepared.")
    if len(argv) > MAX_ARGV_TOKENS:
        raise GitError(errors.INVALID_ARGUMENT, "That operation has too many parts.")
    return op, argv


def run(
    repo_root: Path,
    op_name: str,
    raw_args: Optional[dict[str, Any]] = None,
    *,
    timeout_s: Optional[int] = None,
    input_text: Optional[str] = None,
    env_extra: Optional[dict[str, str]] = None,
    network: Optional[bool] = None,
    git_path: Optional[str] = None,
) -> GitResult:
    """Run one named git operation in `repo_root`. Never raises a git failure."""
    try:
        op, argv = build_argv(op_name, raw_args, git_path=git_path)
    except GitError as exc:
        return GitResult(ok=False, argv=[], code=exc.code, error=exc)

    effective_timeout = timeout_s or op.timeout_s or GIT_TIMEOUT_S
    if network is None:
        network = op.network
    if network:
        effective_timeout = max(effective_timeout, GIT_NETWORK_TIMEOUT_S)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(repo_root),
            env=_scrubbed_env(env_extra),
            shell=False,
            capture_output=True,
            timeout=effective_timeout,
            input=(input_text.encode("utf-8") if input_text is not None else None),
        )
    except subprocess.TimeoutExpired as exc:
        return GitResult(
            ok=False, argv=argv, exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            code=errors.NETWORK_ERROR if network else errors.GIT_FAILED,
            error=GitError(
                errors.NETWORK_ERROR if network else errors.GIT_FAILED,
                "The version operation took too long and was stopped.",
                stderr=f"timeout after {effective_timeout}s",
            ),
        )
    except (OSError, ValueError) as exc:
        return GitResult(
            ok=False, argv=argv, exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            code=errors.GIT_UNAVAILABLE,
            error=GitError(
                errors.GIT_UNAVAILABLE,
                "Git could not be started on this computer.",
                stderr=str(exc),
            ),
        )

    raw_stdout = completed.stdout or b""
    raw_stderr = completed.stderr or b""
    total = len(raw_stdout)
    truncated = total > MAX_OUTPUT_BYTES
    stdout = raw_stdout[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    stderr = raw_stderr[:MAX_STDERR_BYTES].decode("utf-8", "replace")
    duration_ms = int((time.monotonic() - started) * 1000)

    if completed.returncode == 0:
        return GitResult(
            ok=True, argv=argv, stdout=stdout, stderr=stderr,
            exit_code=0, duration_ms=duration_ms, truncated=truncated, total_chars=total,
        )

    code = errors.classify_stderr(stderr)
    return GitResult(
        ok=False, argv=argv, stdout=stdout, stderr=stderr,
        exit_code=completed.returncode, duration_ms=duration_ms,
        truncated=truncated, total_chars=total, code=code,
        error=GitError(code, stderr=stderr, exit_code=completed.returncode),
    )


def run_ok(
    repo_root: Path, op_name: str, raw_args: Optional[dict[str, Any]] = None, **kwargs: Any,
) -> GitResult:
    """Like `run`, but raises `GitError` on failure (for internal call sites)."""
    return run(repo_root, op_name, raw_args, **kwargs).raise_for_error()


__all__ = [
    "GIT_NETWORK_TIMEOUT_S",
    "GIT_TIMEOUT_S",
    "GitResult",
    "MAX_ARGV_TOKENS",
    "MAX_OUTPUT_BYTES",
    "build_argv",
    "resolve_git",
    "run",
    "run_ok",
    "set_git_path",
]
