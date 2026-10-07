"""The Git subsystem's structured error model.

Git reports failure as human-readable stderr. A model cannot act on prose, so
this module defines ONE closed vocabulary of machine codes and maps the common
Git failures onto it. `GitError` carries a stable `code`, a plain single-sentence
`reason` safe to show a person (no mechanism term from
`code.policy.PLAIN_LANGUAGE_DENYLIST`), a `recoverable` flag, and optional
`files`/`hint`.

Nothing here runs anything. The mapper is a pure function of
(operation, exit code, stderr) so it is unit-testable without a repository.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# ── The closed code vocabulary ───────────────────────────────────────────────

REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
NOT_A_REPOSITORY = "NOT_A_REPOSITORY"
DIRTY_WORKTREE = "DIRTY_WORKTREE"
CHECKOUT_OVERWRITE = "CHECKOUT_OVERWRITE"
MERGE_CONFLICT = "MERGE_CONFLICT"
REBASE_CONFLICT = "REBASE_CONFLICT"
CHERRY_PICK_CONFLICT = "CHERRY_PICK_CONFLICT"
REVERT_CONFLICT = "REVERT_CONFLICT"
NON_FAST_FORWARD = "NON_FAST_FORWARD"
REMOTE_REJECTED = "REMOTE_REJECTED"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
PERMISSION_DENIED = "PERMISSION_DENIED"
BRANCH_NOT_FOUND = "BRANCH_NOT_FOUND"
REMOTE_NOT_FOUND = "REMOTE_NOT_FOUND"
TAG_NOT_FOUND = "TAG_NOT_FOUND"
DETACHED_HEAD = "DETACHED_HEAD"
OPERATION_IN_PROGRESS = "OPERATION_IN_PROGRESS"
NO_OPERATION_IN_PROGRESS = "NO_OPERATION_IN_PROGRESS"
LOCKED_REPOSITORY = "LOCKED_REPOSITORY"
INDEX_LOCKED = "INDEX_LOCKED"
NETWORK_ERROR = "NETWORK_ERROR"
HOOK_FAILED = "HOOK_FAILED"
SECRET_DETECTED = "SECRET_DETECTED"
LARGE_FILE_DETECTED = "LARGE_FILE_DETECTED"
PROTECTED_BRANCH = "PROTECTED_BRANCH"
FORCE_PUSH_REQUIRES_AUTHORIZATION = "FORCE_PUSH_REQUIRES_AUTHORIZATION"
DESTRUCTIVE_REQUIRES_AUTHORIZATION = "DESTRUCTIVE_REQUIRES_AUTHORIZATION"
NOTHING_TO_COMMIT = "NOTHING_TO_COMMIT"
NOTHING_STAGED = "NOTHING_STAGED"
PATHSPEC_NO_MATCH = "PATHSPEC_NO_MATCH"
BRANCH_EXISTS = "BRANCH_EXISTS"
UNMERGED_PATHS = "UNMERGED_PATHS"
UNCOMMITTED_CHANGES = "UNCOMMITTED_CHANGES"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
INVALID_REVISION = "INVALID_REVISION"
UNSAFE_COMMAND = "UNSAFE_COMMAND"
GIT_UNAVAILABLE = "GIT_UNAVAILABLE"
GIT_FAILED = "GIT_FAILED"

ALL_CODES: frozenset[str] = frozenset(
    {
        REPOSITORY_NOT_FOUND, NOT_A_REPOSITORY, DIRTY_WORKTREE, CHECKOUT_OVERWRITE,
        MERGE_CONFLICT, REBASE_CONFLICT, CHERRY_PICK_CONFLICT, REVERT_CONFLICT,
        NON_FAST_FORWARD, REMOTE_REJECTED, AUTHENTICATION_FAILED, PERMISSION_DENIED,
        BRANCH_NOT_FOUND, REMOTE_NOT_FOUND, TAG_NOT_FOUND, DETACHED_HEAD,
        OPERATION_IN_PROGRESS, NO_OPERATION_IN_PROGRESS, LOCKED_REPOSITORY,
        INDEX_LOCKED, NETWORK_ERROR, HOOK_FAILED, SECRET_DETECTED,
        LARGE_FILE_DETECTED, PROTECTED_BRANCH, FORCE_PUSH_REQUIRES_AUTHORIZATION,
        DESTRUCTIVE_REQUIRES_AUTHORIZATION, NOTHING_TO_COMMIT, NOTHING_STAGED,
        PATHSPEC_NO_MATCH, BRANCH_EXISTS, UNMERGED_PATHS, UNCOMMITTED_CHANGES,
        INVALID_ARGUMENT, INVALID_REVISION, UNSAFE_COMMAND, GIT_UNAVAILABLE,
        GIT_FAILED,
    }
)

# Codes that mean "the operation can be resumed/retried after a decision",
# versus those that are terminal for the current attempt.
RECOVERABLE: frozenset[str] = frozenset(
    {
        MERGE_CONFLICT, REBASE_CONFLICT, CHERRY_PICK_CONFLICT, REVERT_CONFLICT,
        DIRTY_WORKTREE, CHECKOUT_OVERWRITE, UNCOMMITTED_CHANGES, UNMERGED_PATHS,
        NON_FAST_FORWARD, REMOTE_REJECTED, NETWORK_ERROR, LOCKED_REPOSITORY,
        INDEX_LOCKED, OPERATION_IN_PROGRESS,
    }
)

# One plain, human-safe recovery hint per code. Names the JOB, never a mechanism
# term; ends with a full stop. Mirrors `code/commands.COMMAND_REFUSAL_COPY`.
RECOVERY_HINTS: dict[str, str] = {
    REPOSITORY_NOT_FOUND: "There is no project folder to work in. Open one first.",
    NOT_A_REPOSITORY: "This folder is not set up to track versions yet. Set that up first.",
    DIRTY_WORKTREE: "There are unsaved changes here. Save, set them aside, or discard them before switching.",
    CHECKOUT_OVERWRITE: "Switching would overwrite work that is not saved. Save or set it aside first.",
    MERGE_CONFLICT: "Some files disagree. Resolve each one, then continue.",
    REBASE_CONFLICT: "Some files disagree while replaying changes. Resolve each one, then continue.",
    CHERRY_PICK_CONFLICT: "Some files disagree while copying a change. Resolve each one, then continue.",
    REVERT_CONFLICT: "Some files disagree while undoing a change. Resolve each one, then continue.",
    NON_FAST_FORWARD: "The version on the server moved ahead. Bring the latest down first, then send again.",
    REMOTE_REJECTED: "The server turned the change down. Bring the latest down and try again.",
    AUTHENTICATION_FAILED: "The server did not accept the sign-in. Check the account it is connected to.",
    PERMISSION_DENIED: "The account does not have permission for that here.",
    BRANCH_NOT_FOUND: "There is no line of work with that name here.",
    REMOTE_NOT_FOUND: "There is no server configured with that name.",
    TAG_NOT_FOUND: "There is no marker with that name here.",
    DETACHED_HEAD: "You are not on a named line of work right now. Pick one first.",
    OPERATION_IN_PROGRESS: "Another multi-step operation is still open. Finish or cancel it first.",
    NO_OPERATION_IN_PROGRESS: "There is no multi-step operation to finish right now.",
    LOCKED_REPOSITORY: "The folder is in use by another process. Wait a moment and try again.",
    INDEX_LOCKED: "The folder is in use by another process. Wait a moment and try again.",
    NETWORK_ERROR: "The server could not be reached. Check the connection and try again.",
    HOOK_FAILED: "A project check stopped the action. Read its message and fix what it names.",
    SECRET_DETECTED: "Something that looks like a password or key is in the change. Remove it or confirm it is safe.",
    LARGE_FILE_DETECTED: "A very large file is in the change. Keep it out, or store it the large-file way.",
    PROTECTED_BRANCH: "That line of work is protected. Make the change on its own line instead.",
    FORCE_PUSH_REQUIRES_AUTHORIZATION: "Overwriting the server's history needs explicit approval.",
    DESTRUCTIVE_REQUIRES_AUTHORIZATION: "That action can discard work and needs explicit approval.",
    NOTHING_TO_COMMIT: "There is nothing waiting to be saved.",
    NOTHING_STAGED: "Nothing has been chosen to save yet. Choose what to include first.",
    PATHSPEC_NO_MATCH: "That path does not match anything here.",
    BRANCH_EXISTS: "A line of work with that name already exists.",
    UNMERGED_PATHS: "Some files still disagree. Resolve them before saving.",
    UNCOMMITTED_CHANGES: "There are unsaved changes here.",
    INVALID_ARGUMENT: "One of the details was not something I could use. Ask again more simply.",
    INVALID_REVISION: "That version name is not one I recognize.",
    UNSAFE_COMMAND: "That action is not one Eclipse is allowed to take.",
    GIT_UNAVAILABLE: "Git is not installed on this computer, so version tracking cannot be used.",
    GIT_FAILED: "The version operation did not complete. Check the details and try again.",
}


class GitError(Exception):
    """A structured Git failure. `code` is stable and asserted by tests."""

    def __init__(
        self,
        code: str,
        reason: str = "",
        *,
        recoverable: Optional[bool] = None,
        files: Optional[Iterable[str]] = None,
        hint: str = "",
        stderr: str = "",
        exit_code: Optional[int] = None,
    ) -> None:
        super().__init__(reason)
        self.code = code if code in ALL_CODES else GIT_FAILED
        self.reason = reason or RECOVERY_HINTS.get(self.code, RECOVERY_HINTS[GIT_FAILED])
        self.recoverable = RECOVERABLE.__contains__(self.code) if recoverable is None else recoverable
        self.files = list(files or [])
        self.hint = hint or RECOVERY_HINTS.get(self.code, "")
        # Raw stderr and exit code are for the journal/operator — never the model.
        self.stderr = stderr
        self.exit_code = exit_code

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.reason,
            "recoverable": self.recoverable,
            "files": list(self.files),
        }
        if self.hint:
            out["hint"] = self.hint
        if include_raw:
            if self.exit_code is not None:
                out["exitCode"] = self.exit_code
            if self.stderr:
                out["detail"] = self.stderr[-2_000:]
        return out


def failure(
    code: str,
    *, reason: str = "", files: Optional[Iterable[str]] = None,
    recoverable: Optional[bool] = None, hint: str = "",
    stderr: str = "", exit_code: Optional[int] = None,
) -> dict[str, Any]:
    """A structured failure payload for a tool result (never raises)."""
    return {
        "success": False,
        "error": GitError(
            code, reason, recoverable=recoverable, files=files, hint=hint,
            stderr=stderr, exit_code=exit_code,
        ).to_dict(),
    }


# ── Stderr → code mapper ──────────────────────────────────────────────────────
#
# Ordered rules, most specific first. Each is (substring(s), code). The mapper is
# intentionally conservative: when nothing matches it returns GIT_FAILED rather
# than guessing, so a new Git message is visible rather than mislabelled.

_STDERR_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("not a git repository", "not a git repo"), NOT_A_REPOSITORY),
    (("no such remote", "does not appear to be a git repository"), REMOTE_NOT_FOUND),
    (("couldn't find remote ref", "remote branch"), BRANCH_NOT_FOUND),
    (("pathspec", "' did not match", "did not match any"), PATHSPEC_NO_MATCH),
    (("could not resolve host", "unable to access", "connection timed out",
      "could not read from remote", "network is unreachable", "operation timed out",
      "failed to connect", "connection reset"), NETWORK_ERROR),
    (("authentication failed", "could not read username", "permission denied (publickey",
      "invalid username or password", "authorization failed", "terminal prompts disabled",
      "401 unauthorized"), AUTHENTICATION_FAILED),
    (("protected branch", "gh006", "push declined", "pre-receive hook declined",
      "not allowed to push"), PERMISSION_DENIED),
    (("non-fast-forward", "fetch first", "failed to push some refs",
      "updates were rejected because", "cannot lock ref"), NON_FAST_FORWARD),
    (("cannot lock ref", "unable to create", "another git process",
      "index.lock", "unable to lock"), INDEX_LOCKED),
    (("nothing to commit", "no changes added to commit"), NOTHING_TO_COMMIT),
    (("no staged changes", "nothing added to commit"), NOTHING_STAGED),
    (("pathspec",), PATHSPEC_NO_MATCH),
    (("is not a valid object name", "unknown revision", "bad revision",
      "ambiguous argument"), INVALID_REVISION),
    (("already exists", "a branch named"), BRANCH_EXISTS),
    (("does not have any commits yet", "unborn", "bad default revision"), BRANCH_NOT_FOUND),
    (("you have unstaged changes", "your local changes", "would be overwritten"), CHECKOUT_OVERWRITE),
    (("you have unmerged", "unmerged paths", "fix conflicts"), UNMERGED_PATHS),
    (("hook declined", "pre-commit", "pre-push", "commit-msg hook"), HOOK_FAILED),
    (("there is no merge", "no cherry-pick", "no rebase", "no revert in progress"), NO_OPERATION_IN_PROGRESS),
    (("merge in progress", "rebase in progress", "cherry-pick in progress",
      "you are in the middle of"), OPERATION_IN_PROGRESS),
    (("lock file already exists", "index.lock"), LOCKED_REPOSITORY),
)


def classify_stderr(stderr: str) -> str:
    """Map Git stderr to the closest machine code, or GIT_FAILED."""
    lowered = (stderr or "").casefold()
    for needles, code in _STDERR_RULES:
        if any(needle.casefold() in lowered for needle in needles):
            return code
    return GIT_FAILED


# ── Operation → conflict code (so a failed op names the RIGHT conflict) ───────

_CONFLICT_BY_OPERATION: dict[str, str] = {
    "merge": MERGE_CONFLICT,
    "rebase": REBASE_CONFLICT,
    "cherry_pick": CHERRY_PICK_CONFLICT,
    "revert": REVERT_CONFLICT,
}


def conflict_code(operation: str) -> str:
    return _CONFLICT_BY_OPERATION.get(operation, GIT_FAILED)


__all__ = [
    "ALL_CODES",
    "RECOVERABLE",
    "RECOVERY_HINTS",
    "GitError",
    "classify_stderr",
    "conflict_code",
    "failure",
]
