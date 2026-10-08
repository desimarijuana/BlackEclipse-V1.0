"""Event filtering — exact, namespace/wildcard and predicate subscriptions.

Filtering happens BEFORE a handler runs so unnecessary agent/workflow work is
never triggered by an event the subscriber does not care about. A predicate
expression uses the SAME deterministic DSL as the Automation Engine conditions
(`automation.conditions`), reusing that evaluator rather than inventing a second
one: `payload.symbol == "BTCUSDT" and payload.changePercent > 5`.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .envelope import EclipseEvent


def _matches_pattern(pattern: str, event_type: str) -> bool:
    """Dot-aware glob: `*` matches within a segment; `prefix.**` matches the whole
    subtree. `task.*` matches `task.completed` but not `task.sub.created`;
    `task.**` matches both."""
    if pattern in ("*", "**"):
        return True
    if pattern.endswith(".**"):
        prefix = pattern[:-3]
        return event_type == prefix or event_type.startswith(f"{prefix}.")
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        rest = event_type[len(prefix) + 1 :] if event_type.startswith(f"{prefix}.") else None
        return rest is not None and "." not in rest
    if "*" in pattern:
        return fnmatch.fnmatchcase(event_type, pattern)
    return event_type == pattern


@dataclass
class EventFilter:
    """A subscription matcher. All specified conditions must hold (AND)."""

    patterns: tuple[str, ...] = ("*",)
    predicate: Optional[str] = None
    priority_at_least: Optional[str] = None
    source: Optional[str] = None
    predicate_fn: Optional[Callable[[EclipseEvent], bool]] = None

    _PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "critical": 3, "bulk": 1}

    def matches(self, event: EclipseEvent) -> bool:
        if not any(_matches_pattern(p, event.type) for p in self.patterns):
            return False
        if self.source and event.source != self.source:
            return False
        if self.priority_at_least:
            threshold = self._PRIORITY_RANK.get(self.priority_at_least, 0)
            if self._PRIORITY_RANK.get(event.priority, 1) < threshold:
                return False
        if self.predicate:
            if not self._evaluate_predicate(event):
                return False
        if self.predicate_fn is not None:
            try:
                if not self.predicate_fn(event):
                    return False
            except Exception:  # noqa: BLE001 - a broken predicate must not match everything
                return False
        return True

    def _evaluate_predicate(self, event: EclipseEvent) -> bool:
        try:
            from ..automation.conditions import ConditionContext, evaluate  # noqa: PLC0415

            facts = self._facts(event)
            result = evaluate(self.predicate or "", ConditionContext(values=facts, history={}))
            # UNAVAILABLE is treated as not-matching (fail-closed).
            return bool(result.truthy)
        except Exception:  # noqa: BLE001 - a malformed predicate filters the event out
            return False

    @staticmethod
    def _facts(event: EclipseEvent) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "event.type": event.type,
            "type": event.type,
            "source": event.source,
            "priority": event.priority,
        }
        for key, value in event.payload.items():
            facts[key] = value
            facts[f"payload.{key}"] = value
        if event.correlation_id:
            facts["correlationId"] = event.correlation_id
        return facts

    @classmethod
    def exact(cls, event_type: str, **kwargs: Any) -> "EventFilter":
        return cls(patterns=(event_type,), **kwargs)

    @classmethod
    def namespace(cls, prefix: str, **kwargs: Any) -> "EventFilter":
        # `prefix.**` matches the prefix and any depth beneath it (`market.price.updated`).
        return cls(patterns=(f"{prefix}.**",), **kwargs)

    @classmethod
    def any(cls, patterns: Sequence[str], **kwargs: Any) -> "EventFilter":
        return cls(patterns=tuple(patterns), **kwargs)


__all__ = ["EventFilter"]
