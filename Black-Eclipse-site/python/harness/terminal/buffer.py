"""The bounded output store for a process or session.

A terminal subsystem cannot retain unlimited output in memory, and the agent must
never be handed 100 MB of build logs. This module provides the two primitives the
rest of the subsystem reads through:

  * ``RingBuffer`` — a thread-safe, line- and byte-bounded store where every
    appended line carries a monotonic SEQUENCE number. A consumer polls with
    ``since_sequence`` and never sees a line twice.
  * ``truncate_for_model`` — the head+tail+sentinel view used when a tool result
    is too large to hand the model whole, with a cursor to fetch the rest.

No process, no I/O, no platform behavior: pure, deterministic, testable.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Optional

from .types import OutputChunk, StreamName

#: Defaults chosen to be a fraction of the model context, not the memory ceiling.
DEFAULT_MAX_LINES = 10_000
DEFAULT_MAX_BYTES = 1_000_000
_MAX_LINE_CHARS = 16_384


def _split_lines(text: str) -> list[str]:
    """Split into lines WITHOUT dropping the final partial line's terminator.

    A pump reads arbitrary chunks; a chunk usually ends mid-line. We keep the
    text lines as-is (terminators preserved) so reassembly is lossless; the
    caller joins them again.
    """
    if not text:
        return []
    parts = text.splitlines(keepends=True)
    # A string ending in "\n" yields no trailing empty entry from splitlines;
    # a chunk that is exactly "\n" yields ["\n"]. Both are correct here.
    return parts


class RingBuffer:
    """A bounded, sequenced, thread-safe output buffer.

    Ordering: lines are appended under a lock, so sequence order equals arrival
    order per buffer. stdout and stderr may be pumped by two threads; the lock
    serializes them into one total order. They are NEVER concatenated into one
    stream — each line keeps its ``stream``.
    """

    def __init__(
        self,
        *,
        max_lines: int = DEFAULT_MAX_LINES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._max_lines = max(1, int(max_lines))
        self._max_bytes = max(1, int(max_bytes))
        self._lines: Deque[OutputChunk] = deque()
        self._lock = threading.Lock()
        self._seq = 0
        self._bytes = 0
        self._dropped_lines = 0
        self._dropped_bytes = 0
        self._total_lines = 0
        self._total_bytes = 0

    # ── Writes ───────────────────────────────────────────────────────────────

    def append(self, stream: str, text: str, timestamp: str) -> list[OutputChunk]:
        """Append text as one or more sequenced chunks. Returns the new chunks."""
        new: list[OutputChunk] = []
        with self._lock:
            for raw in _split_lines(text):
                line = raw if len(raw) <= _MAX_LINE_CHARS else raw[:_MAX_LINE_CHARS]
                self._seq += 1
                chunk = OutputChunk(
                    sequence=self._seq,
                    stream=str(stream),
                    timestamp=timestamp,
                    data=line,
                )
                nbytes = len(line.encode("utf-8", "replace"))
                self._lines.append(chunk)
                self._bytes += nbytes
                self._total_lines += 1
                self._total_bytes += nbytes
                new.append(chunk)
            self._trim_locked()
        return new

    def note(self, text: str, timestamp: str) -> OutputChunk:
        """Append a subsystem note (start/exit/signal) on the SYSTEM stream."""
        chunks = self.append(StreamName.SYSTEM.value, text if text.endswith("\n") else text + "\n", timestamp)
        return chunks[-1]

    def _trim_locked(self) -> None:
        while self._lines and (
            len(self._lines) > self._max_lines or self._bytes > self._max_bytes
        ):
            oldest = self._lines.popleft()
            nbytes = len(oldest.data.encode("utf-8", "replace"))
            self._bytes -= nbytes
            self._dropped_lines += 1
            self._dropped_bytes += nbytes

    # ── Reads ────────────────────────────────────────────────────────────────

    def read(
        self,
        *,
        stream: Optional[str] = None,
        since_sequence: Optional[int] = None,
        cursor: Optional[int] = None,
        tail: Optional[int] = None,
        lines: Optional[int] = None,
        byte_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Read a window of the buffer.

        Precedence: ``since_sequence``/``cursor`` (fetch what is new) wins over
        ``tail``; ``tail`` then ``lines`` bounds a window; ``byte_limit`` caps the
        payload regardless. The returned ``nextSequence`` is the cursor to pass
        next time to avoid duplicates.
        """
        with self._lock:
            start_seq = since_sequence if since_sequence is not None else cursor
            selected: list[OutputChunk] = []
            for chunk in self._lines:
                if stream is not None and chunk.stream != stream:
                    continue
                if start_seq is not None and chunk.sequence <= start_seq:
                    continue
                selected.append(chunk)
            available = len(selected)
            if start_seq is None and tail is not None and tail >= 0:
                selected = selected[-tail:] if tail else []
            elif lines is not None and lines >= 0:
                selected = selected[:lines]
            if byte_limit is not None and byte_limit >= 0:
                kept: list[OutputChunk] = []
                used = 0
                for chunk in selected:
                    nbytes = len(chunk.data.encode("utf-8", "replace"))
                    if kept and used + nbytes > byte_limit:
                        break
                    kept.append(chunk)
                    used += nbytes
                selected = kept
            next_seq = selected[-1].sequence if selected else (start_seq or 0)
            dropped = self._dropped_lines
            return {
                "chunks": [c.to_dict() for c in selected],
                "text": "".join(c.data for c in selected),
                "count": len(selected),
                "available": available,
                "nextSequence": next_seq,
                "droppedLines": dropped,
                "totalLines": self._total_lines,
                "totalBytes": self._total_bytes,
            }

    def snapshot(self) -> dict[str, Any]:
        """Counts and cursors, without copying the text."""
        with self._lock:
            return {
                "lines": len(self._lines),
                "bytes": self._bytes,
                "lastSequence": self._seq,
                "droppedLines": self._dropped_lines,
                "droppedBytes": self._dropped_bytes,
                "totalLines": self._total_lines,
                "totalBytes": self._total_bytes,
            }


def truncate_for_model(
    text: str,
    *,
    head: int = 50,
    tail: int = 200,
    max_chars: int = 16_000,
) -> tuple[str, bool]:
    """Head + tail + cursor sentinel for an over-large tool result.

    Returns ``(rendered, truncated)``. Under the bound the text is returned
    byte-identical; over it, the first ``head`` and last ``tail`` lines are shown
    with an unmistakable NON-JSON marker. This is the "first N / last N / cursor"
    rule (§71) and it deliberately lives with the buffer, not in each tool.
    """
    total = len(text)
    all_lines = text.splitlines()
    if total <= max_chars and len(all_lines) <= head + tail:
        return text, False
    if len(all_lines) <= head + tail and total <= max_chars:
        return text, False
    head_lines = all_lines[:head]
    tail_lines = all_lines[-tail:] if tail else []
    omitted = max(0, len(all_lines) - len(head_lines) - len(tail_lines))
    marker = (
        f"\n\n[OUTPUT TRUNCATED: {len(all_lines)} lines total; showing the first "
        f"{len(head_lines)} and last {len(tail_lines)} lines. "
        f"{omitted} lines are not shown here — read them with the output cursor.]"
    )
    rendered = "\n".join(head_lines) + marker + ("\n" + "\n".join(tail_lines) if tail_lines else "")
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars] + marker
    return rendered, True


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "RingBuffer",
    "truncate_for_model",
]
