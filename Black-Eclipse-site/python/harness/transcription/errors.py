"""Truthful, user-facing transcription failure classes.

Kept in its own module so the local engine and the HTTP provider path can both
raise it without importing each other.
"""

from __future__ import annotations


class TranscriptionError(Exception):
    """A truthful, user-facing failure class."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
