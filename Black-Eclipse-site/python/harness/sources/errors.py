"""Typed failures for the source layer.

Every refusal is a small, named code so the UI and the agent can distinguish
"you asked for something outside a root" from "the budget ran out" from "that
format cannot be parsed". Nothing is silently swallowed: a partial result says
it is partial.
"""

from __future__ import annotations

from typing import Any, Optional


class SourceError(Exception):
    """A source-layer failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

    def __str__(self) -> str:  # pragma: no cover - defensive formatting only
        return f"{self.code}: {self.message}"


CODES = {
    "ROOT_NOT_FOUND": "the root path does not exist",
    "ROOT_NOT_DIRECTORY": "a root must be a directory",
    "ROOT_LIMIT": "the maximum number of roots is reached",
    "ROOT_UNKNOWN": "the root is not registered",
    "PATH_OUTSIDE_ROOT": "the path escapes its registered root",
    "FILE_NOT_FOUND": "the file is not in the catalog",
    "FILE_GONE": "the file no longer exists on disk",
    "FILE_TOO_LARGE": "the file is over the configured ceiling",
    "READ_LIMIT": "the read window exceeds the ceiling",
    "UNSUPPORTED": "this format is not parseable; it is catalogued as opaque",
    "BUDGET_EXCEEDED": "the operation ran out of its time or byte budget",
    "QUERY_TIMEOUT": "the query exceeded its timeout",
    "QUERY_REFUSED": "the SQL statement is not a read-only single statement",
    "SCAN_BUSY": "a scan is already running for this root",
    "SEMANTIC_UNAVAILABLE": "no embedding provider is configured",
    "CANCELLED": "the operation was cancelled",
}


__all__ = ["SourceError", "CODES"]
