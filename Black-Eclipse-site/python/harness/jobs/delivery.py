"""Delivery adapters for finished job runs (Phase 6 §6.8, extended Phase 11).

One narrow interface, three implementations:

  * `in_app`    — rides the existing event bus (the SSE surface the TS notifier
                  consumes), publishing a `job.delivered` event with a plain
                  summary. No new notification system.
  * `artifact`  — writes a saved report under
                  `.black-eclipse/artifacts/<runId>/`, reusing the existing
                  research/receipt rendering conventions (§6.2).
  * `messaging` — hands the surface a TEMPLATE KEY plus parameters, resolved
                  through `src/lib/i18n/`. Never composes prose here (§6.1).

A delivery failure NEVER fails the job run — it is reported on the run row, PER
TARGET (§6.3). There is no rolled-up boolean anywhere: `deliver_all` returns one
`DeliveryOutcome` per configured target.

Phase 11 adds `messaging` and the artifact file contract; the `DeliveryAdapter`
protocol itself is Phase 6's and is reused unchanged.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from ..events import EventBus
from ..persistence import now_iso
from .model import JobDefinition, JobDeliveryTarget

# A hard bound on any detail handed to a surface.
MAX_DETAIL_CHARS = 2_000

# Structured reason codes (never a bare string). §6.3.
NO_DESTINATION = "NO_DESTINATION"
DELIVERY_FAILED = "DELIVERY_FAILED"
REFUSED = "REFUSED"

__all__ = [
    "ArtifactAdapter",
    "DELIVERY_FAILED",
    "DeliveryAdapter",
    "DeliveryOutcome",
    "DeliverySummary",
    "InAppAdapter",
    "MAX_DETAIL_CHARS",
    "MessagingAdapter",
    "NO_DESTINATION",
    "REFUSED",
    "artifact_dir_for",
    "default_adapters",
    "deliver_all",
]


@dataclass
class DeliverySummary:
    """The plain, user-facing outcome of a job run.

    `answer` is the run's final text; `outcome_line` is a one-line human sentence
    ("Ran at 7:30am · 12 seconds · delivered") assembled by the scheduler. Neither
    carries an exit code or a digest.

    `message_key` + `message_params` are the Phase 11 addition: the messaging
    adapter hands a surface a KEY + parameters, never a composed sentence, so the
    message is translatable and the jargon gate can see every word of it.
    """

    title: str
    answer: str
    outcome_line: str
    status: str
    run_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
    message_key: Optional[str] = None
    message_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryOutcome:
    """One delivery target's outcome. NEVER collapsed into a single boolean."""

    adapter: str
    ok: bool
    reason: Optional[str] = None
    # The user's chosen destination label (Phase 11). None for the older adapters.
    target: Optional[str] = None
    reason_code: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "target": self.target,
            "ok": self.ok,
            "reason": self.reason,
            "reasonCode": self.reason_code,
            **self.detail,
        }


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
            return DeliveryOutcome(
                self.name, False, "the app isn't listening right now",
                reason_code=DELIVERY_FAILED,
            )
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
            return DeliveryOutcome(
                self.name, False, str(exc)[:MAX_DETAIL_CHARS], reason_code=DELIVERY_FAILED,
            )


class ArtifactAdapter:
    """Saves the run's report under `.black-eclipse/artifacts/<runId>/` (§6.2).

    Files: `report.md` (the rendered answer), `receipt.json` (the bounded
    ResearchReceipt when the run produced one), `meta.json` (job + scope labels +
    the template keys). The path is DERIVED from the server-assigned run id.
    """

    name = "artifact"

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root

    async def deliver(
        self, job: JobDefinition, run_id: str, summary: DeliverySummary
    ) -> DeliveryOutcome:
        try:
            directory = artifact_dir_for(run_id, self._root)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "report.md").write_text(
                f"# {summary.title}\n\n{summary.outcome_line}\n\n{summary.answer}\n",
                encoding="utf-8",
            )
            receipt = summary.meta.get("receipt")
            if receipt is not None:
                (directory / "receipt.json").write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8",
                )
            meta = {
                "jobId": job.id,
                "jobName": job.name,
                "runId": run_id,
                "producedAt": now_iso(),
                "scopeId": job.scope_id,
                "templateKeys": [summary.message_key] if summary.message_key else [],
            }
            (directory / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            # A RELATIVE path is reported so no absolute location leaks to the UI.
            rel = f".black-eclipse/artifacts/{directory.name}"
            return DeliveryOutcome(self.name, True, detail={"artifact": rel})
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a run
            return DeliveryOutcome(
                self.name, False, str(exc)[:MAX_DETAIL_CHARS], reason_code=DELIVERY_FAILED,
            )


class MessagingAdapter:
    """Send the job's summary to the user's chosen destination (§6.1).

    The body is a TEMPLATE KEY plus parameters — never composed prose and never a
    hardcoded string here. The surface resolves the key through `src/lib/i18n/` so
    a message is translatable and the jargon gate can see every word of it.

    Refuses (never improvises) when no destination is configured:
        DeliveryOutcome(ok=False, reasonCode="NO_DESTINATION")
    """

    name = "messaging"

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus

    async def deliver(
        self, job: JobDefinition, run_id: str, summary: DeliverySummary
    ) -> DeliveryOutcome:
        destination = job.delivery.destination
        if not destination:
            return DeliveryOutcome(
                self.name, False,
                "No destination was chosen for this job, so there was nowhere to send it.",
                reason_code=NO_DESTINATION,
            )
        key = summary.message_key
        if not key:
            return DeliveryOutcome(
                self.name, False, "There was no message to send.",
                target=destination, reason_code=REFUSED,
            )
        try:
            if self._bus is not None:
                # The surface renders the key; the runtime never composes the text.
                self._bus.publish({
                    "id": f"msg_{run_id}_{now_iso()}",
                    "runId": None,
                    "type": "job.message",
                    "seq": 0,
                    "at": now_iso(),
                    "data": {
                        "target": destination,
                        "templateKey": key,
                        "params": dict(summary.message_params),
                        "runId": summary.run_id,
                    },
                })
            return DeliveryOutcome(
                self.name, True, target=destination, detail={"templateKey": key},
            )
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a run
            return DeliveryOutcome(
                self.name, False, str(exc)[:MAX_DETAIL_CHARS],
                target=destination, reason_code=DELIVERY_FAILED,
            )


def artifact_dir_for(run_id: str, root: Optional[Path] = None) -> Path:
    """The artifacts directory for `run_id` — DERIVED, never caller-supplied.

    `run_id` is a server-assigned id; the leaf is sanitized to a conservative
    filename so a malformed id can never traverse. The result is confined with the
    same path policy the code capability uses (`policy.resolve_within`).
    """
    from ..code import policy  # noqa: PLC0415
    from ..code.workspace import default_root  # noqa: PLC0415

    if root is not None:
        base = Path(root)
    else:
        override = os.environ.get("BLACK_ECLIPSE_CODE_ROOT")
        if override:
            base = Path(override)
        else:
            found = default_root()
            base = Path(found) if found else Path.cwd()
    safe = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in "-_")
    if not safe:
        raise ValueError("run id has no usable characters")
    artifacts = base / ".black-eclipse" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    if root is None:
        # Confine against the artifacts parent (the code capability's path policy).
        return policy.resolve_within(artifacts, safe)
    return artifacts / safe


async def deliver_all(
    job: JobDefinition,
    run_id: str,
    summary: DeliverySummary,
    adapters: Optional[dict[str, DeliveryAdapter]] = None,
) -> list[dict[str, Any]]:
    """Deliver to EVERY configured target, recording one outcome PER TARGET.

    A failure on one target never short-circuits the others and never fails the
    job run. Returns the list of `DeliveryOutcome.public()` dicts, in target order.
    """
    pool = adapters if adapters is not None else default_adapters(None)
    outcomes: list[dict[str, Any]] = []
    for target in job.delivery.effective_targets():
        adapter = pool.get(target.adapter)
        if adapter is None:
            outcomes.append(DeliveryOutcome(
                target.adapter, False, "That way of telling you isn't available.",
                target=target.destination, reason_code=REFUSED,
            ).public())
            continue
        # Bind the target's own destination onto the job the adapter sees, so the
        # messaging adapter can tell a chosen destination from a missing one. The
        # adapter never reads anything else from the copy.
        bound = job.model_copy(update={
            "delivery": job.delivery.model_copy(update={"destination": target.destination}),
        })
        try:
            outcome = await adapter.deliver(bound, run_id, summary)
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a run
            outcome = DeliveryOutcome(
                target.adapter, False, str(exc)[:MAX_DETAIL_CHARS],
                target=target.destination, reason_code=DELIVERY_FAILED,
            )
        if outcome.target is None:
            outcome.target = target.destination
        outcomes.append(outcome.public())
    return outcomes


def default_adapters(
    bus: Optional[EventBus], artifact_root: Optional[Path] = None
) -> dict[str, DeliveryAdapter]:
    return {
        "in_app": InAppAdapter(bus),
        "artifact": ArtifactAdapter(artifact_root),
        "messaging": MessagingAdapter(bus),
    }
