"""Stable failure signatures and recurrence detection.

A signature is a short, deterministic fingerprint of *the kind of failure*, not
of a single occurrence. Two runs that both fail with a validation error on the
same tool, and a run that fails twice in a row with the same provider timeout,
must produce the SAME signature — that is what lets the recovery engine tell a
recurring root cause from an unrelated failure with similar wording (spec §6.2).

The message is normalized before hashing (case, digits, absolute paths and
volatile ids collapsed) so `timeout after 1201ms` and `timeout after 1198ms`
share a signature. The signature never includes a raw secret because it is built
only from caller-supplied, already-sanitized fields, and the digest is one-way.

`RecurrenceTracker` is the in-memory recurrence/loop counter (the failure-domain
analogue of `observability.anomaly.LoopDetector`). It is intentionally NOT the
anomaly detector: that one runs on *all* operations for telemetry, while this one
runs only on failures inside the recovery controller and feeds a bounded
recovery policy.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Optional

_WS = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX = re.compile(r"\b[0-9a-f]{16,}\b")
_PATH = re.compile(r"(?:[a-zA-Z]:[\\/]|/)[^\s:]+")


def normalize_message(message: Optional[str]) -> str:
    """Collapse a message to its stable, secret-free shape for hashing."""
    text = (message or "").strip().lower()
    if not text:
        return ""
    text = _UUID.sub("<id>", text)
    text = _HEX.sub("<hex>", text)
    text = _PATH.sub("<path>", text)
    text = _DIGITS.sub("<n>", text)
    text = _WS.sub(" ", text)
    return text[:200]


def failure_signature(
    *,
    kind: Any,
    code: str = "",
    source: str = "",
    subsystem: str = "",
    location: Optional[str] = None,
    message: Optional[str] = None,
) -> str:
    """A stable fingerprint of a failure kind. Never empty, always 16 hex chars."""
    kind_value = getattr(kind, "value", str(kind))
    parts = "|".join(
        (
            str(kind_value),
            (code or "").strip().lower(),
            (subsystem or "").strip().lower(),
            (source or "").strip().lower(),
            (location or "").strip().lower()[:120],
            normalize_message(message),
        )
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RecurrenceVerdict:
    signature: str
    count: int
    window: int
    repeated: bool


class RecurrenceTracker:
    """Counts identical failure signatures in a bounded sliding window.

    `observe` returns a verdict after every failure; a `repeated` verdict means
    the same signature has now appeared at least `threshold` times within the
    last `window` failures — a recurring root cause, not a coincidence.
    """

    def __init__(self, *, threshold: int = 3, window: int = 8) -> None:
        self.threshold = max(2, int(threshold))
        self.window = max(self.threshold, int(window))
        self._recent: deque[str] = deque(maxlen=self.window)
        self._counts: dict[str, int] = defaultdict(int)

    def observe(self, signature: str) -> RecurrenceVerdict:
        self._recent.append(signature)
        count = sum(1 for s in self._recent if s == signature)
        repeated = count >= self.threshold
        if repeated:
            self._counts[signature] += 1
        return RecurrenceVerdict(
            signature=signature, count=count, window=self.window, repeated=repeated
        )

    def reset(self) -> None:
        self._recent.clear()
        self._counts.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "window": self.window,
            "tracked": len(self._counts),
            "recent": list(self._recent),
        }


__all__ = [
    "RecurrenceTracker",
    "RecurrenceVerdict",
    "failure_signature",
    "normalize_message",
]
