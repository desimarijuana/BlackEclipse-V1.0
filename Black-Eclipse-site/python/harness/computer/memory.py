"""Computer Use ↔ Eclipse-Memory integration.

Computer Use stores useful SEMANTIC knowledge — application layouts, known UI
patterns, successful workflows and recovery paths — in `eclipse-memory`, NOT in
JDdS. It deliberately does NOT store screenshots or raw pixel data: memory holds
knowledge, not frames.

Every write is EXPLICIT and inspectable (the design forbids uncontrolled
self-modifying behaviour): `remember_application`, `remember_workflow` and
`remember_recovery` are called by the `computer_remember` tool, never silently by
the action loop. All calls are best-effort — a missing memory service is a no-op,
never a crash.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("harness.computer.memory")

# The memory scope used for desktop knowledge, so recall can filter to it.
SCOPE = "computer"
# The `source` must be one Eclipse-Memory PERMITS (see `VALID_SOURCES` in
# `eclipse_memory/service.py`). A desktop workflow/recovery learned from a real
# run is an `execution_lesson` — the correct existing vocabulary, not a new one.
SOURCE = "execution_lesson"


class ComputerMemory:
    """A thin, fail-safe wrapper over the Eclipse-Memory service."""

    def __init__(self, service: Any = None) -> None:
        self._service = service

    @property
    def available(self) -> bool:
        return self._service is not None

    def remember(
        self,
        *,
        kind: str,
        content: str,
        application: str = "",
        subject: Optional[str] = None,
        structured: Optional[dict[str, Any]] = None,
        scope_id: Optional[str] = None,
        confidence: float = 0.6,
    ) -> dict[str, Any]:
        """Persist one learned desktop fact. Returns {stored, id, reason}."""
        if self._service is None:
            return {"stored": False, "reason": "memory is unavailable"}
        memory_type = {"workflow": "procedural", "recovery": "procedural"}.get(kind, "semantic")
        subject = subject or (application or "desktop")
        try:
            result = self._service.write_memory(
                memory_type=memory_type,
                content=content,
                source=SOURCE,
                scope=SCOPE,
                scope_id=scope_id or (application or None),
                subject=subject,
                structured_data={"kind": kind, "application": application, **(structured or {})},
                confidence=confidence,
                importance=0.6,
                verification="unverified",
                created_by="computer_use",
            )
            return {"stored": True, "id": (result or {}).get("id"), "reason": "recorded"}
        except Exception as exc:  # noqa: BLE001 - a memory write must never break a task
            log.warning("computer memory write failed", exc_info=True)
            return {"stored": False, "reason": str(exc)[:200]}

    def recall(self, *, query: str, application: str = "", limit: int = 5) -> list[dict[str, Any]]:
        """Recall learned desktop knowledge for an application/objective."""
        if self._service is None:
            return []
        try:
            result = self._service.retrieve(query=query, scope=SCOPE, scope_id=application or None, limit=limit)
            return list(getattr(result, "memories", []) or [])
        except Exception:  # noqa: BLE001 - a recall failure is simply no knowledge
            return []

    def describe(self) -> dict[str, Any]:
        return {"available": self.available, "scope": SCOPE, "source": SOURCE}


__all__ = ["ComputerMemory", "SCOPE", "SOURCE"]
