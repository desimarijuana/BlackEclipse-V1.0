"""Observer hook system — backend-neutral fan-out of `HookEvent`s.

An `Observer` is any object with an `observe(event)` method (or a plain
callable). `ObserverHub` registers observers, dispatches each event to all of
them, and — critically — NEVER lets a failing observer affect the runtime: every
call is wrapped, timed and counted, and a broken observer is quarantined after
repeated failures.

Subclasses may implement named hooks (`on_run_start`, `on_llm_end`, …); the base
class dispatches by converting the hook name to its snake_case method name.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from .events import HookEvent

log = logging.getLogger("harness.observability.observers")

_QUARANTINE_AFTER = 25


def _snake(hook: str) -> str:
    out = []
    for i, ch in enumerate(hook):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


class Observer:
    """Base observer. Override any `on_*` method; unhandled hooks are no-ops."""

    name: str = "observer"

    def observe(self, event: HookEvent) -> None:
        handler = getattr(self, _snake(event.hook), None)
        if handler is None:
            return
        handler(event)

    # Named hooks (default no-ops so subclasses pick what they need).
    def on_run_start(self, event: HookEvent) -> None: ...
    def on_run_end(self, event: HookEvent) -> None: ...
    def on_agent_start(self, event: HookEvent) -> None: ...
    def on_agent_end(self, event: HookEvent) -> None: ...
    def on_plan_start(self, event: HookEvent) -> None: ...
    def on_plan_end(self, event: HookEvent) -> None: ...
    def on_task_start(self, event: HookEvent) -> None: ...
    def on_task_end(self, event: HookEvent) -> None: ...
    def on_llm_start(self, event: HookEvent) -> None: ...
    def on_llm_end(self, event: HookEvent) -> None: ...
    def on_llm_error(self, event: HookEvent) -> None: ...
    def on_tool_start(self, event: HookEvent) -> None: ...
    def on_tool_end(self, event: HookEvent) -> None: ...
    def on_tool_error(self, event: HookEvent) -> None: ...
    def on_queue_enqueue(self, event: HookEvent) -> None: ...
    def on_queue_start(self, event: HookEvent) -> None: ...
    def on_queue_end(self, event: HookEvent) -> None: ...
    def on_queue_error(self, event: HookEvent) -> None: ...
    def on_job_start(self, event: HookEvent) -> None: ...
    def on_job_end(self, event: HookEvent) -> None: ...
    def on_job_retry(self, event: HookEvent) -> None: ...
    def on_job_failure(self, event: HookEvent) -> None: ...
    def on_event_published(self, event: HookEvent) -> None: ...
    def on_event_consumed(self, event: HookEvent) -> None: ...
    def on_event_processed(self, event: HookEvent) -> None: ...
    def on_event_failed(self, event: HookEvent) -> None: ...
    def on_plugin_start(self, event: HookEvent) -> None: ...
    def on_plugin_end(self, event: HookEvent) -> None: ...
    def on_plugin_error(self, event: HookEvent) -> None: ...
    def on_a2a_message_sent(self, event: HookEvent) -> None: ...
    def on_a2a_message_received(self, event: HookEvent) -> None: ...
    def on_memory_read(self, event: HookEvent) -> None: ...
    def on_memory_write(self, event: HookEvent) -> None: ...
    def on_memory_search(self, event: HookEvent) -> None: ...
    def on_skill_loaded(self, event: HookEvent) -> None: ...
    def on_skill_executed(self, event: HookEvent) -> None: ...
    def on_research_start(self, event: HookEvent) -> None: ...
    def on_research_end(self, event: HookEvent) -> None: ...
    def on_evidence_retrieved(self, event: HookEvent) -> None: ...
    def on_evidence_validated(self, event: HookEvent) -> None: ...
    def on_recovery_start(self, event: HookEvent) -> None: ...
    def on_recovery_end(self, event: HookEvent) -> None: ...
    def on_approval(self, event: HookEvent) -> None: ...
    def on_security_event(self, event: HookEvent) -> None: ...
    def on_anomaly(self, event: HookEvent) -> None: ...
    def on_slo_violation(self, event: HookEvent) -> None: ...
    def on_loop_detected(self, event: HookEvent) -> None: ...
    def on_error(self, event: HookEvent) -> None: ...
    def on_span(self, event: HookEvent) -> None: ...


class FunctionObserver(Observer):
    """Adapter wrapping a plain `(event) -> None` callable."""

    def __init__(self, fn: Callable[[HookEvent], None], name: str = "function") -> None:
        self._fn = fn
        self.name = name

    def observe(self, event: HookEvent) -> None:
        self._fn(event)


class ObserverHub:
    def __init__(self) -> None:
        self._observers: list[Observer] = []
        self._failures: dict[str, int] = {}
        self._quarantined: set[str] = set()
        self._calls = 0
        self._errors = 0

    def register(self, observer: Observer | Callable[[HookEvent], None], *, name: Optional[str] = None) -> Callable[[], None]:
        if not isinstance(observer, Observer):
            observer = FunctionObserver(observer, name=name or "function")
        elif name:
            observer.name = name
        self._observers.append(observer)

        def _remove() -> None:
            if observer in self._observers:
                self._observers.remove(observer)

        return _remove

    def unregister(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    @property
    def observers(self) -> list[Observer]:
        return list(self._observers)

    def count(self) -> int:
        return len(self._observers)

    def dispatch(self, event: HookEvent) -> None:
        for observer in list(self._observers):
            if observer.name in self._quarantined:
                continue
            self._calls += 1
            try:
                observer.observe(event)
                self._failures.pop(observer.name, None)
            except Exception:  # noqa: BLE001 - a broken observer must not break a run
                self._errors += 1
                failures = self._failures.get(observer.name, 0) + 1
                self._failures[observer.name] = failures
                log.warning("observer %r failed on %s", observer.name, event.hook, exc_info=True)
                if failures >= _QUARANTINE_AFTER:
                    self._quarantined.add(observer.name)
                    log.error("observer %r quarantined after %d failures", observer.name, failures)

    def stats(self) -> dict[str, Any]:
        return {
            "registered": len(self._observers),
            "calls": self._calls,
            "errors": self._errors,
            "quarantined": sorted(self._quarantined),
            "failures": dict(self._failures),
        }


__all__ = ["Observer", "FunctionObserver", "ObserverHub"]
