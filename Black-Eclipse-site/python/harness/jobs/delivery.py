"""Delivery adapters for finished job runs (Phase 6 §6.8).

One narrow interface, two implementations in this phase:

  * `in_app`   — rides the existing event bus (the SSE surface the TS notifier
                 consumes), publishing a `job.delivered` event with a plain
                 summary. No new notification system.
  * `artifact` — writes a saved report under
                 `.black-eclipse/artifacts/<runId>/summary.md`, reusing the
                 existing research/receipt rendering conventions.

The messaging adapter is Phase 11; the interface exists now so that phase adds an
adapter rather than refactoring the job model.

A delivery failure NEVER fails the job run — it is reported on the run row.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from ..events import EventBus
from ..persistence import now_iso
from .model import JobDefinition


@dataclass
class DeliverySummary:
    """The plain, user-facing outcome of a job run.

    `answer` is the run's final text; `outcome_line` is a one-line human sentence
    ("Ran at 7:30am · 12 seconds · delivered") assembled by the scheduler. Neither
    carries an exit code or a digest.
    """

    title: str
    answer: str
    outcome_line: str
    status: str
    run_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryOutcome:
    adapter: str
    ok: bool
    reason: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {"adapter": self.adapter, "ok": self.ok, "reason": self.reason, **self.detail}


class DeliveryAdapter(Protocol):
    name: str

    async def deliver(
        self, job: JobDefinition, run_id: str, summary: DeliverySummary
    ) -> DeliveryOutcome: ...


class InAppAdapter:
    """Publishes the delivery on the shared event bus (the SSE surface)."""

    name = "in_app"

    def __init__(self, bus: Optional[EventBus]) -> None:
        self._bus = bus

    async def deliver(
        self, job: JobDefinition, run_id: str, summary: DeliverySummary
    ) -> DeliveryOutcome:
        if self._bus is None:
            return DeliveryOutcome(self.name, False, "the app isn't listening right now")
        try:
            self._bus.publish({
                "id": f"job_{run_id}_{now_iso()}",
                "runId": None,
                "type": "job.delivered",
                "seq": 0,
                "at": now_iso(),
                "data": {
                    "jobId": job.id,
                    "name": job.name,
                    "title": summary.title,
                    "outcome": summary.outcome_line,
                    "status": summary.status,
                    "runId": summary.run_id,
                    "answer": summary.answer[:4000],
                },
            })
            return DeliveryOutcome(self.name, True)
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a run
            return DeliveryOutcome(self.name, False, str(exc))


class ArtifactAdapter:
    """Saves the run's answer as a report under `.black-eclipse/artifacts/`."""

    name = "artifact"

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root

    def _artifacts_dir(self, run_id: str) -> Path:
        if self._root is not None:
            base = Path(self._root)
        else:
            override = os.environ.get("BLACK_ECLIPSE_CODE_ROOT")
            if override:
                base = Path(override)
            else:
                from ..code.workspace import default_root  # noqa: PLC0415

                found = default_root()
                base = Path(found) if found else Path.cwd()
        return base / ".black-eclipse" / "artifacts" / run_id

    async def deliver(
        self, job: JobDefinition, run_id: str, summary: DeliverySummary
    ) -> DeliveryOutcome:
        try:
            directory = self._artifacts_dir(run_id)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "summary.md"
            body = (
                f"# {summary.title}\n\n"
                f"{summary.outcome_line}\n\n"
                f"{summary.answer}\n"
            )
            path.write_text(body, encoding="utf-8")
            # A RELATIVE path is reported so no absolute location leaks.
            rel = path.name if self._root is None else str(path)
            return DeliveryOutcome(self.name, True, detail={"artifact": rel})
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a run
            return DeliveryOutcome(self.name, False, str(exc))


def default_adapters(bus: Optional[EventBus], artifact_root: Optional[Path] = None) -> dict[str, DeliveryAdapter]:
    return {
        "in_app": InAppAdapter(bus),
        "artifact": ArtifactAdapter(artifact_root),
    }


__all__ = [
    "ArtifactAdapter",
    "DeliveryAdapter",
    "DeliveryOutcome",
    "DeliverySummary",
    "InAppAdapter",
    "default_adapters",
]
