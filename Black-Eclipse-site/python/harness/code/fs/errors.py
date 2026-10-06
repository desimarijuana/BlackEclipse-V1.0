"""Structured filesystem errors — the standard code vocabulary.

This is the ONE place a filesystem failure's machine code is defined. Every
operation in `code/fs/` raises `FsError`; every tool handler maps it to a
`{"status": "refused", "code": ..., "message": ...}` record the model can read.

The codes are the task's standard set plus the confinement codes the existing
`code/workspace.confine` already produces (mapped 1:1 in `resolver.py`), so a
single vocabulary reaches the agent regardless of which layer refused.

Nothing here decides anything and nothing here touches the disk. A plain
`reason` is always one sentence safe to show a human: it never contains
mechanism words, file contents, or a path outside the workspace.
"""

from __future__ import annotations

from typing import Any, Optional

# ── The standard code set ───────────────────────────────────────────────────

PATH_NOT_FOUND = "PATH_NOT_FOUND"
PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
PERMISSION_DENIED = "PERMISSION_DENIED"
FILE_EXISTS = "FILE_EXISTS"
DIRECTORY_EXISTS = "DIRECTORY_EXISTS"
NOT_A_FILE = "NOT_A_FILE"
NOT_A_DIRECTORY = "NOT_A_DIRECTORY"
INVALID_PATH = "INVALID_PATH"
INVALID_ENCODING = "INVALID_ENCODING"
BINARY_FILE = "BINARY_FILE"
UNSUPPORTED_BINARY_OPERATION = "UNSUPPORTED_BINARY_OPERATION"
TOO_LARGE = "TOO_LARGE"
STALE_FILE = "STALE_FILE"
AMBIGUOUS_PATCH = "AMBIGUOUS_PATCH"
PATCH_FAILED = "PATCH_FAILED"
PATCH_CONTEXT_MISMATCH = "PATCH_CONTEXT_MISMATCH"
DIFF_FAILED = "DIFF_FAILED"
TRANSACTION_FAILED = "TRANSACTION_FAILED"
ROLLBACK_FAILED = "ROLLBACK_FAILED"
SEARCH_FAILED = "SEARCH_FAILED"
INDEX_FAILED = "INDEX_FAILED"
WATCH_FAILED = "WATCH_FAILED"
WORKSPACE_UNBOUND = "WORKSPACE_UNBOUND"
DRY_RUN = "DRY_RUN"

# The confinement codes `code/workspace.confine` already emits. Kept identical so
# a caller can assert the same code whether the refusal came from the resolver or
# an fs operation.
CONFINEMENT_CODES = (
    "PATH_TRAVERSAL",
    "PATH_OUTSIDE_WORKSPACE",
    "SYMLINK_ESCAPE",
    "PROTECTED_PATH",
    "IGNORED_PATH",
    "NOT_FOUND",
)

ALL_CODES = frozenset({
    PATH_NOT_FOUND, PATH_NOT_ALLOWED, PERMISSION_DENIED, FILE_EXISTS,
    DIRECTORY_EXISTS, NOT_A_FILE, NOT_A_DIRECTORY, INVALID_PATH,
    INVALID_ENCODING, BINARY_FILE, UNSUPPORTED_BINARY_OPERATION, TOO_LARGE,
    STALE_FILE, AMBIGUOUS_PATCH, PATCH_FAILED, PATCH_CONTEXT_MISMATCH,
    DIFF_FAILED, TRANSACTION_FAILED, ROLLBACK_FAILED, SEARCH_FAILED,
    INDEX_FAILED, WATCH_FAILED, WORKSPACE_UNBOUND, DRY_RUN, *CONFINEMENT_CODES,
})

# One-sentence, human-safe hints for autonomous recovery. The tool result carries
# the code AND this hint so the agent knows the next move without guessing.
RECOVERY_HINTS: dict[str, str] = {
    STALE_FILE: "The file changed since it was read. Re-read the relevant region and retry.",
    AMBIGUOUS_PATCH: "The target text appears more than once. Add more surrounding context.",
    PATCH_CONTEXT_MISMATCH: "The surrounding context did not match. Re-read the file and retry.",
    PATH_NOT_FOUND: "The path does not exist. List the parent folder to find the right name.",
    FILE_EXISTS: "The file already exists. Use write_file with overwrite, or pick another name.",
    DIRECTORY_EXISTS: "The folder already exists. Continue, or pick another name.",
    PERMISSION_DENIED: "This task is not allowed to make that change.",
    PATH_NOT_ALLOWED: "That location is outside the task's folder.",
    BINARY_FILE: "That file is not readable text.",
    UNSUPPORTED_BINARY_OPERATION: "Binary files cannot be edited as text.",
}


class FsError(Exception):
    """A filesystem refusal with a stable code and a plain, recoverable reason.

    `code` is one of `ALL_CODES`. `reason` is a single sentence safe to show a
    human. `path` is the workspace-relative path involved, when known. `details`
    is a small content-free dict (counts, hashes, candidate lines) the agent can
    use to recover — never file contents.
    """

    def __init__(
        self,
        code: str,
        reason: str,
        *,
        path: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.path = path
        self.details = details or {}

    @property
    def recovery(self) -> str:
        return RECOVERY_HINTS.get(self.code, "")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "refused",
            "code": self.code,
            "message": self.reason,
            "path": self.path,
        }
        if self.recovery:
            payload["recovery"] = self.recovery
        if self.details:
            payload["details"] = self.details
        return payload


__all__ = [
    "ALL_CODES",
    "AMBIGUOUS_PATCH",
    "BINARY_FILE",
    "CONFINEMENT_CODES",
    "DIFF_FAILED",
    "DIRECTORY_EXISTS",
    "DRY_RUN",
    "FILE_EXISTS",
    "FsError",
    "INDEX_FAILED",
    "INVALID_ENCODING",
    "INVALID_PATH",
    "NOT_A_DIRECTORY",
    "NOT_A_FILE",
    "PATCH_CONTEXT_MISMATCH",
    "PATCH_FAILED",
    "PATH_NOT_ALLOWED",
    "PATH_NOT_FOUND",
    "PERMISSION_DENIED",
    "RECOVERY_HINTS",
    "ROLLBACK_FAILED",
    "SEARCH_FAILED",
    "STALE_FILE",
    "TOO_LARGE",
    "TRANSACTION_FAILED",
    "UNSUPPORTED_BINARY_OPERATION",
    "WATCH_FAILED",
    "WORKSPACE_UNBOUND",
]
