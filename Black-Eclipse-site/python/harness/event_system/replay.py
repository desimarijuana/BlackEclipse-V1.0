"""Explicit, safe event replay.

Replay MUST NOT accidentally re-execute dangerous external side effects. Three
modes:

    observe     read the events and return them; nothing is delivered.
    simulation  report which subscribers WOULD run; nothing is delivered.
    full        re-publish the events to real subscribers. Operators only, and
                destructive/financial event types require explicit confirmation.

A replayed event is a NEW event (new id, `replay=True`, `metadata.originalId`
set), so consumer idempotency keys on the new id and the replay actually fires,
while the id-based global dedup does not swallow it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .bus import EventBus
from .envelope import EclipseEvent, new_event_id
from .store import EventStore

REPLAY_MODES = ("observe", "simulation", "full")
_DESTRUCTIVE_TYPES = frozenset({
    "risk.threshold.breached",
    "portfolio.position.added",
    "portfolio.position.updated",
    "portfolio.position.removed",
    "model.requested",
    "tool.called",
    "tool.requested",
})
_DESTRUCTIVE_PREFIXES = ("browser.", "computer.", "git.", "terminal.", "code.")


class ReplayError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ReplayResult:
    mode: str
    count: int
    event_ids: list[str] = field(default_factory=list)
    matched_subscribers: list[str] = field(default_factory=list)
    delivered: int = 0
    skipped: int = 0
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "count": self.count,
            "eventIds": self.event_ids,
            "matchedSubscribers": self.matched_subscribers,
            "delivered": self.delivered,
            "skipped": self.skipped,
            "dryRun": self.dry_run,
        }


class ReplayService:
    def __init__(self, store: EventStore, bus: EventBus) -> None:
        self._store = store
        self._bus = bus

    def query(
        self,
        *,
        event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        types: Optional[list[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 200,
    ) -> list[EclipseEvent]:
        if event_id:
            event = self._store.get(event_id)
            return [event] if event else []
        if types:
            collected: list[EclipseEvent] = []
            for event_type in types:
                collected.extend(self._store.query(
                    type=event_type, correlation_id=correlation_id, task_id=task_id,
                    workflow_id=workflow_id, trace_id=trace_id, since=since, until=until,
                    limit=limit, ascending=True,
                ))
            collected.sort(key=lambda e: e.timestamp)
            return collected[:limit]
        return self._store.query(
            correlation_id=correlation_id, task_id=task_id, workflow_id=workflow_id,
            trace_id=trace_id, since=since, until=until, limit=limit, ascending=True,
        )

    async def replay(
        self,
        events: list[EclipseEvent],
        *,
        mode: str = "observe",
        authorized: bool = False,
        confirm_destructive: bool = False,
    ) -> ReplayResult:
        if mode not in REPLAY_MODES:
            raise ReplayError("INVALID_MODE", f"{mode!r} is not one of {REPLAY_MODES}")
        if mode == "full" and not authorized:
            raise ReplayError("UNAUTHORIZED", "full replay requires operator authorization")
        destructive = [e for e in events if _is_destructive(e.type)]
        if mode == "full" and destructive and not confirm_destructive:
            raise ReplayError(
                "CONFIRM_REQUIRED",
                f"{len(destructive)} event(s) are destructive/financial; set confirmDestructive to replay",
            )

        result = ReplayResult(mode=mode, count=len(events), event_ids=[e.id for e in events])
        result.dry_run = mode != "full"
        if mode == "observe":
            return result

        matched: set[str] = set()
        for event in events:
            for sub in self._bus.subscriptions():
                if sub.enabled and sub.event_filter.matches(event):
                    matched.add(sub.consumer_id)
        result.matched_subscribers = sorted(matched)
        if mode == "simulation":
            return result

        for event in events:
            replayed = _as_replay(event)
            if replayed is None:
                result.skipped += 1
                continue
            await self._bus.publish(replayed)
            result.delivered += 1
            self._bus.metrics.inc("replayed")
        return result


def _as_replay(event: EclipseEvent) -> Optional[EclipseEvent]:
    clone = EclipseEvent.from_dict(event.to_dict())
    clone.id = new_event_id()
    clone.replay = True
    clone.metadata = {**event.metadata, "originalId": event.id, "replayed": True}
    return clone


def _is_destructive(event_type: str) -> bool:
    return event_type in _DESTRUCTIVE_TYPES or any(
        event_type.startswith(prefix) for prefix in _DESTRUCTIVE_PREFIXES
    )


__all__ = ["REPLAY_MODES", "ReplayError", "ReplayResult", "ReplayService"]
