"""The acquisition budget — enforced in Python, beside `ResearchBudget`.

The research budget bounds an ANSWER (searches/fetches/pages). This bounds a
DATASET: calls, rows, bytes written, wall clock. It is deliberately separate so
the claim-verified research path (`research/budget.py`) is untouched.

The byte ceiling is enforced HERE, at each flush — a single huge response, or a
model-chosen row count, cannot exceed it: the writer stops and the manifest marks
the file partial.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AcquisitionBudget:
    max_calls: int = 60
    max_rows: int = 50_000
    max_bytes_written: int = 20 * 1024 * 1024
    max_seconds: float = 600.0

    calls: int = 0
    rows: int = 0
    bytes_written: int = 0
    started_at: float = field(default_factory=time.monotonic)
    exhausted: Optional[str] = None     # a plain reason, set at the ceiling

    # ── checks ──────────────────────────────────────────────────────────────
    @property
    def elapsed_s(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def allow_call(self) -> bool:
        if self.exhausted:
            return False
        if self.calls >= self.max_calls:
            self.exhausted = f"reached the collection limit ({self.max_calls} requests)"
            return False
        if self.elapsed_s >= self.max_seconds:
            self.exhausted = "reached the collection time limit"
            return False
        return True

    def record_call(self) -> None:
        self.calls += 1

    def record_rows(self, n: int) -> None:
        self.rows += max(0, int(n))
        if self.rows >= self.max_rows and not self.exhausted:
            self.exhausted = f"reached the collection limit ({self.max_rows:,} rows)"

    def record_bytes(self, n: int) -> None:
        self.bytes_written += max(0, int(n))
        if self.bytes_written >= self.max_bytes_written and not self.exhausted:
            self.exhausted = (
                f"reached the collection limit ({self.max_bytes_written // (1024 * 1024)} MB)"
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "maxCalls": self.max_calls,
            "callsUsed": self.calls,
            "maxRows": self.max_rows,
            "rowsUsed": self.rows,
            "maxBytes": self.max_bytes_written,
            "bytesUsed": self.bytes_written,
            "maxSeconds": self.max_seconds,
            "elapsedSeconds": round(self.elapsed_s, 1),
            "exhausted": self.exhausted,
        }


__all__ = ["AcquisitionBudget"]
