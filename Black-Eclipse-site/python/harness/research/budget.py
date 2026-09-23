"""Bounded research budget (Phase 5).

Every escalation path — structured lookup, web search, page fetch, extraction —
draws from one explicit, configurable budget. When the budget is exhausted the
flow stops and records *which paths were attempted and why it stopped*, rather
than silently continuing or looping.

The budget is a plain counter object: `allow()` returns False once a resource is
capped, and `exhausted` records the first limit that was hit so the receipt can
name it. Time is checked lazily via `deadline`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ResearchBudget:
    """Caps for one research run. All limits are inclusive maxima."""

    maxSearches: int = 4
    maxFetches: int = 8
    maxPages: int = 6
    maxSeconds: float = 90.0
    maxModelTokens: int = 24_000

    searches: int = 0
    fetches: int = 0
    pages: int = 0
    modelTokens: int = 0
    startedAt: float = field(default_factory=time.monotonic)
    exhausted: Optional[str] = None
    attempted: list[str] = field(default_factory=list)

    def _record(self) -> None:
        if self.exhausted:
            return
        if self.searches > self.maxSearches:
            self.exhausted = "maxSearches"
        elif self.fetches > self.maxFetches:
            self.exhausted = "maxFetches"
        elif self.pages > self.maxPages:
            self.exhausted = "maxPages"
        elif self.modelTokens > self.maxModelTokens:
            self.exhausted = "maxModelTokens"
        elif self.elapsed_seconds() > self.maxSeconds:
            self.exhausted = "maxSeconds"

    def allow_search(self) -> bool:
        if self.searches >= self.maxSearches or self.timed_out:
            self._record_refusal()
            return False
        self.searches += 1
        self.attempted.append(f"web_search#{self.searches}")
        self._record()
        return True

    def allow_fetch(self) -> bool:
        if self.fetches >= self.maxFetches or self.timed_out:
            self._record_refusal()
            return False
        self.fetches += 1
        self.attempted.append(f"web_fetch#{self.fetches}")
        self._record()
        return True

    def _record_refusal(self) -> None:
        """Record WHICH limit stopped the flow, even before a count is exceeded."""
        if self.exhausted:
            return
        if self.timed_out:
            self.exhausted = "maxSeconds"
        elif self.searches >= self.maxSearches:
            self.exhausted = "maxSearches"
        elif self.fetches >= self.maxFetches:
            self.exhausted = "maxFetches"
        elif self.modelTokens >= self.maxModelTokens:
            self.exhausted = "maxModelTokens"

    def note_page(self) -> None:
        self.pages += 1
        self._record()

    def note_tokens(self, count: int) -> None:
        self.modelTokens += max(0, int(count or 0))
        self._record()

    def note(self, label: str) -> None:
        """Record a non-counted path attempt (structured lookup, escalation)."""
        self.attempted.append(label)

    @property
    def timed_out(self) -> bool:
        return self.elapsed_seconds() > self.maxSeconds

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.startedAt

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.maxSeconds - self.elapsed_seconds())

    def snapshot(self) -> dict[str, Any]:
        """A serializable summary for the receipt and events."""
        return {
            "limits": {
                "maxSearches": self.maxSearches,
                "maxFetches": self.maxFetches,
                "maxPages": self.maxPages,
                "maxSeconds": self.maxSeconds,
                "maxModelTokens": self.maxModelTokens,
            },
            "used": {
                "searches": self.searches,
                "fetches": self.fetches,
                "pages": self.pages,
                "modelTokens": self.modelTokens,
                "elapsedSeconds": round(self.elapsed_seconds(), 3),
            },
            "exhausted": self.exhausted,
            "attempted": self.attempted,
        }


__all__ = ["ResearchBudget"]
