"""The acquisition budget — enforced in Python, beside `ResearchBudget`.

The research budget bounds an ANSWER (searches/fetches/pages). This bounds a
DATASET: calls, rows, bytes written, wall clock. It is deliberately separate so
the claim-verified research path (`research/budget.py`) is untouched.

The byte ceiling is enforced HERE, at each flush — a single huge response, or a
model-chosen row count, cannot exceed it: the writer stops and the manifest marks
the file partial.
"""

from __future__ import annotations

import os
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


# ── the run-scoped ledger (several pulls in one turn) ───────────────────────
#
# The per-call budget above bounds ONE pull. A turn may make several (a second
# symbol batch, another series); this ledger accumulates them so a model cannot
# turn "bounded" into "bounded per call, unbounded per turn". It rides the run
# context (`RunUsage.of(ctx)`), so it is process-local and never durable state.

RUN_MAX_CALLS = 240
RUN_MAX_ROWS = 200_000
RUN_MAX_BYTES = 80 * 1024 * 1024
RUN_MAX_SECONDS = 2_400.0

_USAGE_ATTR = "_acquire_run_usage"


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


@dataclass
class RunUsage:
    """Cumulative acquisition usage for ONE run, with its own hard ceilings."""

    max_calls: int = RUN_MAX_CALLS
    max_rows: int = RUN_MAX_ROWS
    max_bytes: int = RUN_MAX_BYTES
    max_seconds: float = RUN_MAX_SECONDS
    calls: int = 0
    rows: int = 0
    bytes_written: int = 0
    started_at: float = field(default_factory=time.monotonic)
    exhausted: Optional[str] = None

    @classmethod
    def from_env(cls) -> "RunUsage":
        return cls(
            max_calls=_env_int("HARNESS_ACQUIRE_RUN_MAX_CALLS", RUN_MAX_CALLS),
            max_rows=_env_int("HARNESS_ACQUIRE_RUN_MAX_ROWS", RUN_MAX_ROWS),
            max_bytes=_env_int("HARNESS_ACQUIRE_RUN_MAX_BYTES", RUN_MAX_BYTES),
            max_seconds=_env_float("HARNESS_ACQUIRE_RUN_MAX_SECONDS", RUN_MAX_SECONDS),
        )

    @classmethod
    def of(cls, ctx: Any) -> "RunUsage":
        """The run's ledger, created on first use and carried on the context."""
        existing = getattr(ctx, _USAGE_ATTR, None)
        if isinstance(existing, cls):
            return existing
        usage = cls.from_env()
        try:
            setattr(ctx, _USAGE_ATTR, usage)
        except Exception:  # noqa: BLE001 - a frozen ctx still gets a working ledger
            pass
        return usage

    @property
    def elapsed_s(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def absorb(self, budget: AcquisitionBudget) -> None:
        """Fold one finished pull's usage in and re-check the run ceilings."""
        self.calls += max(0, int(budget.calls))
        self.rows += max(0, int(budget.rows))
        self.bytes_written += max(0, int(budget.bytes_written))
        if self.exhausted:
            return
        if self.calls >= self.max_calls:
            self.exhausted = f"reached this turn's collection limit ({self.max_calls} requests)"
        elif self.rows >= self.max_rows:
            self.exhausted = f"reached this turn's collection limit ({self.max_rows:,} rows)"
        elif self.bytes_written >= self.max_bytes:
            self.exhausted = (
                f"reached this turn's collection limit ({self.max_bytes // (1024 * 1024)} MB)"
            )
        elif self.elapsed_s >= self.max_seconds:
            self.exhausted = "reached this turn's collection time limit"

    def snapshot(self) -> dict[str, Any]:
        return {
            "maxCalls": self.max_calls,
            "callsUsed": self.calls,
            "maxRows": self.max_rows,
            "rowsUsed": self.rows,
            "maxBytes": self.max_bytes,
            "bytesUsed": self.bytes_written,
            "maxSeconds": self.max_seconds,
            "elapsedSeconds": round(self.elapsed_s, 1),
            "exhausted": self.exhausted,
        }


__all__ = [
    "AcquisitionBudget",
    "RUN_MAX_BYTES",
    "RUN_MAX_CALLS",
    "RUN_MAX_ROWS",
    "RUN_MAX_SECONDS",
    "RunUsage",
]
