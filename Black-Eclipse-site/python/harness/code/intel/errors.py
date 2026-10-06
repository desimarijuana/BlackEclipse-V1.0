"""Structured errors for the Code Intelligence & Understanding Engine (CIUE).

One vocabulary for every CIUE refusal, mirroring `code/fs/errors.py`: a stable
machine `code`, a one-sentence plain `reason`, an optional `recovery` hint and a
small content-free `details` dict. Nothing here decides anything; a backend that
cannot answer raises `IntelError`, and the manager maps it to a readable result.

`IntelUnavailable` distinguishes "this backend cannot answer" (a normal fallback
signal) from "this request is invalid" (`IntelError`). A backend absence is never
an exception the agent sees — the manager degrades and names the engine.
"""

from __future__ import annotations

from typing import Any, Optional

# ── Request / backend codes ──────────────────────────────────────────────────
INVALID_PATH = "INVALID_PATH"
NOT_FOUND = "NOT_FOUND"
NO_WORKSPACE = "WORKSPACE_UNAVAILABLE"
UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
SERVER_MISSING = "LANGUAGE_SERVER_MISSING"
SERVER_FAILED = "LANGUAGE_SERVER_FAILED"
SERVER_TIMEOUT = "LANGUAGE_SERVER_TIMEOUT"
SERVER_UNAVAILABLE = "LANGUAGE_SERVER_UNAVAILABLE"
PROJECT_INVALID = "PROJECT_CONFIGURATION_INVALID"
INDEX_FAILED = "INDEX_FAILED"
INDEX_CORRUPT = "INDEX_CORRUPT"
PARSE_FAILED = "PARSE_FAILED"
AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"
EDIT_CONFLICT = "EDIT_CONFLICT"
BINARY_FILE = "BINARY_FILE"
TOO_LARGE = "TOO_LARGE"
DISABLED = "CODE_INTELLIGENCE_DISABLED"

ALL_CODES = frozenset({
    INVALID_PATH, NOT_FOUND, NO_WORKSPACE, UNSUPPORTED_LANGUAGE, BACKEND_UNAVAILABLE,
    SERVER_MISSING, SERVER_FAILED, SERVER_TIMEOUT, SERVER_UNAVAILABLE, PROJECT_INVALID,
    INDEX_FAILED, INDEX_CORRUPT, PARSE_FAILED, AMBIGUOUS_SYMBOL, EDIT_CONFLICT,
    BINARY_FILE, TOO_LARGE, DISABLED,
})

RECOVERY_HINTS: dict[str, str] = {
    SERVER_MISSING: "The language tool isn't installed here. Structural understanding still works.",
    SERVER_FAILED: "The language tool didn't start. Eclipse fell back to structural analysis.",
    SERVER_TIMEOUT: "The language tool took too long. Retry, or use structural analysis.",
    SERVER_UNAVAILABLE: "No language tool is available for this project yet.",
    UNSUPPORTED_LANGUAGE: "That language isn't recognized. Text and structure search still work.",
    AMBIGUOUS_SYMBOL: "Several symbols match. Give the file and line, or a qualifier.",
    PARSE_FAILED: "The file couldn't be parsed. It may be incomplete or malformed.",
    INDEX_CORRUPT: "The code index was unreadable and has been rebuilt from source.",
    NOT_FOUND: "There's no such file or symbol in this project.",
    BINARY_FILE: "That file isn't readable text.",
}


class IntelError(Exception):
    """A CIUE refusal with a stable code and a recoverable, plain reason."""

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


class IntelUnavailable(IntelError):
    """A backend cannot answer this request — a fallback signal, not a failure.

    `engine` names the backend that declined (e.g. "lsp", "tree-sitter"), so the
    manager can try the next source and record which one answered.
    """

    def __init__(self, engine: str, reason: str, *, code: str = BACKEND_UNAVAILABLE) -> None:
        super().__init__(code, reason)
        self.engine = engine


__all__ = [
    "ALL_CODES",
    "AMBIGUOUS_SYMBOL",
    "BACKEND_UNAVAILABLE",
    "BINARY_FILE",
    "DISABLED",
    "EDIT_CONFLICT",
    "INDEX_CORRUPT",
    "INDEX_FAILED",
    "IntelError",
    "IntelUnavailable",
    "INVALID_PATH",
    "NOT_FOUND",
    "NO_WORKSPACE",
    "PARSE_FAILED",
    "PROJECT_INVALID",
    "RECOVERY_HINTS",
    "SERVER_FAILED",
    "SERVER_MISSING",
    "SERVER_TIMEOUT",
    "SERVER_UNAVAILABLE",
    "TOO_LARGE",
    "UNSUPPORTED_LANGUAGE",
]
