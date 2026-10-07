"""Structured browser traces.

Every browser task produces a BrowserTrace: a bounded, ordered record of what the
agent SAW, what it DID, why, what changed, and why it failed. It is the raw
material for replay/debugging and for the observability/telemetry aggregates.

Traces are content-free where it counts: a step records the action, its safe
parameters (references and URLs, never a credential value), the observation
summary, and the verification verdict — never a full DOM dump or a secret. A
trace persists on the ONE agent-memory connection and is also emitted onto the
run's event bus as `browser.trace.*` so the live stream sees it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .store import new_trace_id


@dataclass
class TraceStep:
    index: int
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    started_at: float = 0.0
    duration_ms: int = 0
    screenshots: list[str] = field(default_factory=list)
    downloads: list[str] = field(default_factory=list)
    console: list[dict[str, Any]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    human_intervention: Optional[str] = None
    error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "action": self.action,
            "params": self.params,
            "observation": self.observation,
            "verification": self.verification,
            "provider": self.provider,
            "durationMs": self.duration_ms,
            "screenshots": self.screenshots,
            "downloads": self.downloads,
            "console": self.console,
            "network": self.network,
            "humanIntervention": self.human_intervention,
            "error": self.error,
        }


class BrowserTrace:
    """An ordered, bounded record for one browser task/session."""

    def __init__(
        self,
        *,
        session_id: str = "",
        run_id: str = "",
        task_id: str = "",
        provider: str = "",
        store: Any = None,
        max_steps: int = 200,
    ) -> None:
        self.id = new_trace_id()
        self.session_id = session_id
        self.run_id = run_id
        self.task_id = task_id
        self.provider = provider
        self.created_at = time.time()
        self.status = "open"
        self._steps: list[TraceStep] = []
        self._store = store
        self._max_steps = max(1, max_steps)

    @property
    def steps(self) -> list[TraceStep]:
        return list(self._steps)

    def next_step(self, action: str, params: Optional[dict[str, Any]] = None, provider: str = "") -> TraceStep:
        """Append a new step and return it for the caller to fill in."""
        step = TraceStep(
            index=len(self._steps),
            action=action,
            params=_safe_params(params or {}),
            provider=provider or self.provider,
            started_at=time.monotonic(),
        )
        self._steps.append(step)
        if len(self._steps) > self._max_steps:
            # A trace is BOUNDED: drop the oldest beyond the cap (the newest
            # activity is what debugging needs), but never grow unbounded.
            del self._steps[0]
            for offset, existing in enumerate(self._steps):
                existing.index = offset
        return step

    def finish_step(self, step: TraceStep) -> None:
        step.duration_ms = int((time.monotonic() - step.started_at) * 1000)

    def record(
        self,
        action: str,
        *,
        params: Optional[dict[str, Any]] = None,
        observation: Optional[dict[str, Any]] = None,
        verification: Optional[dict[str, Any]] = None,
        provider: str = "",
        error: Optional[dict[str, Any]] = None,
        screenshots: Optional[list[str]] = None,
        downloads: Optional[list[str]] = None,
        human_intervention: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> TraceStep:
        step = self.next_step(action, params, provider)
        step.observation = observation or {}
        step.verification = verification or {}
        step.error = error
        step.screenshots = screenshots or []
        step.downloads = downloads or []
        step.human_intervention = human_intervention
        if duration_ms is not None:
            step.duration_ms = int(duration_ms)
        else:
            self.finish_step(step)
        return step

    def close(self, status: str = "completed") -> None:
        self.status = status

    def summary(self) -> dict[str, Any]:
        actions = [s.action for s in self._steps]
        return {
            "traceId": self.id,
            "sessionId": self.session_id,
            "provider": self.provider,
            "status": self.status,
            "stepCount": len(self._steps),
            "actions": actions,
            "durationMs": int((time.time() - self.created_at) * 1000),
            "humanInterventions": sum(1 for s in self._steps if s.human_intervention),
            "failures": sum(1 for s in self._steps if s.error),
            "screenshots": [p for s in self._steps for p in s.screenshots],
            "downloads": [p for s in self._steps for p in s.downloads],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "runId": self.run_id,
            "taskId": self.task_id,
            "provider": self.provider,
            "status": self.status,
            "createdAt": self.created_at,
            "steps": [s.to_dict() for s in self._steps],
            "summary": self.summary(),
        }

    def persist(self) -> None:
        """Best-effort persistence; a store failure never breaks a browser action."""
        if self._store is None:
            return
        try:
            self._store.save_trace({
                "id": self.id, "sessionId": self.session_id, "runId": self.run_id,
                "taskId": self.task_id, "provider": self.provider, "status": self.status,
                "createdAt": _iso(self.created_at), "finishedAt": _iso(time.time()) if self.status != "open" else None,
                "steps": [s.to_dict() for s in self._steps], "summary": self.summary(),
            })
        except Exception:  # noqa: BLE001 - a trace must never break a browser action
            pass


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """Keep step params to a small, content-free allowlist.

    A credential value or a full page body must never land in a trace. Only
    primitive fields whose key is not secret-shaped are kept.
    """
    from ..session_index import redact_span  # noqa: PLC0415

    safe: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if not isinstance(value, (str, int, float, bool, type(None))):
            if isinstance(value, (list, tuple)) and all(isinstance(v, (str, int, float, bool)) for v in value):
                value = list(value)[:20]
            else:
                continue
        if isinstance(value, str):
            value = redact_span(value, "«redacted»")[:400]
        safe[str(key)] = value
    return safe


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


__all__ = ["BrowserTrace", "TraceStep"]
