"""Stuck-loop control (round 4, W10) — no progress is a first-class blocker.

Two rules, enforced deterministically:

  * a repeated failed action must never repeat UNCHANGED — the same
    (tool, arguments, failure signature) triple is recorded, and once it has
    failed it may not be retried identically again in the same run;
  * a loop with NO PROGRESS across N attempts (no success between them) is
    stuck — the caller escalates with the ACTUAL blocker (the last failure),
    not another attempt.

PURE: no I/O, no model. The tracker is per-run state; the hot path keeps one on
the run context, the task scheduler derives the same fact from its durable
execution history.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

#: An identical failed attempt may occur at most this many times (the first
#: failure is the observation; a second identical one is a blind repeat).
MAX_IDENTICAL_ATTEMPTS = 1
#: Failures since the last success before the loop is declared stuck.
MAX_NO_PROGRESS = 3


def attempt_digest(tool: str, args: Any) -> str:
    """A stable digest of one attempt's (tool, arguments) — no raw args stored."""
    try:
        payload = json.dumps(args, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001 - an unserializable arg still gets a digest
        payload = repr(args)
    raw = f"{tool}|{payload}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


@dataclass
class ProgressTracker:
    """Per-run progress facts: identical repeats + failures since a success."""

    max_identical: int = MAX_IDENTICAL_ATTEMPTS
    max_no_progress: int = MAX_NO_PROGRESS
    identical: dict[str, int] = field(default_factory=dict)
    no_progress: int = 0
    last_signature: Optional[str] = None
    last_blocker: str = ""
    successes: int = 0

    def note_failure(
        self, *, tool: str, args: Any, signature: str, blocker: str = "",
    ) -> None:
        key = f"{attempt_digest(tool, args)}|{signature}"
        self.identical[key] = self.identical.get(key, 0) + 1
        self.no_progress += 1
        self.last_signature = signature
        if blocker:
            self.last_blocker = blocker[:300]

    def note_success(self) -> None:
        self.successes += 1
        self.no_progress = 0

    def identical_repeats(self, *, tool: str, args: Any, signature: str) -> int:
        """How many times this EXACT attempt has already failed in this run."""
        key = f"{attempt_digest(tool, args)}|{signature}"
        return int(self.identical.get(key, 0))

    def stuck(self) -> Optional[str]:
        """A plain reason when the loop has made no progress, else None."""
        if self.no_progress >= max(2, int(self.max_no_progress)):
            return (
                f"no progress across {self.no_progress} attempts; the actual "
                f"blocker: {self.last_blocker or self.last_signature or 'unknown'}"
            )
        return None


__all__ = [
    "MAX_IDENTICAL_ATTEMPTS",
    "MAX_NO_PROGRESS",
    "ProgressTracker",
    "attempt_digest",
]
