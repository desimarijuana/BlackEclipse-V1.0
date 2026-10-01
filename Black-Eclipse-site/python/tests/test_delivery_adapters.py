"""Phase 11 G1/G1b — delivery adapters, per-target outcomes.

A job configured with several targets records ONE OUTCOME PER TARGET (never a
rolled-up boolean). The artifact adapter writes the §6.2 file contract with a path
derived from the server-assigned run id. The messaging adapter carries a template
KEY + parameters, and refuses with `NO_DESTINATION` when no destination is chosen.
A delivery failure never fails the job run.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness.jobs.delivery import (
    DELIVERY_FAILED,
    NO_DESTINATION,
    ArtifactAdapter,
    DeliveryOutcome,
    DeliverySummary,
    MessagingAdapter,
    default_adapters,
    deliver_all,
)
from harness.jobs.model import JobDefinition, JobDelivery, JobDeliveryTarget, JobTarget
from harness.persistence import now_iso


class FakeBus:
    """A minimal event bus that records published events (or raises on demand)."""

    def __init__(self, fail_types: tuple[str, ...] = ()) -> None:
        self.events: list[dict] = []
        self.fail_types = fail_types

    def publish(self, event: dict) -> None:
        if event.get("type") in self.fail_types:
            raise RuntimeError("transport unavailable")
        self.events.append(event)


def _job(*, targets, adapter="in_app", destination=None) -> JobDefinition:
    now = now_iso()
    return JobDefinition(
        id="job_phase11",
        name="Overnight market brief",
        kind="manual",
        target=JobTarget(kind="objective", objective="brief me"),
        delivery=JobDelivery(adapter=adapter, destination=destination, targets=targets),
        created_at=now,
        updated_at=now,
    )


def _summary() -> DeliverySummary:
    return DeliverySummary(
        title="Overnight market brief",
        answer="Three things changed overnight.",
        outcome_line="Ran at 07:30 · delivered",
        status="ok",
        run_id="run_abc",
        meta={"receipt": {"runId": "run_abc", "finalStatus": "accepted"}},
        message_key="jobs.delivery.message.doneCount",
        message_params={"jobName": "Overnight market brief", "changeCount": 3},
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ── G1 — one outcome per target ──────────────────────────────────────────────


def test_all_three_targets_each_get_an_outcome(tmp_path):
    bus = FakeBus()
    job = _job(targets=[
        JobDeliveryTarget(destination="In the app", adapter="in_app"),
        JobDeliveryTarget(destination="Save it as a report", adapter="artifact"),
        JobDeliveryTarget(destination="My phone", adapter="messaging"),
    ])
    adapters = default_adapters(bus, tmp_path / "artifacts")
    outcomes = asyncio.run(deliver_all(job, "run_abc", _summary(), adapters))

    assert len(outcomes) == 3  # ONE PER TARGET, never rolled up
    by_adapter = {o["adapter"]: o for o in outcomes}
    assert set(by_adapter) == {"in_app", "artifact", "messaging"}
    assert by_adapter["in_app"]["ok"] is True
    assert by_adapter["artifact"]["ok"] is True
    assert by_adapter["messaging"]["ok"] is True
    assert by_adapter["messaging"]["templateKey"] == "jobs.delivery.message.doneCount"
    # The user's chosen labels are carried, not the adapter names.
    assert {o["target"] for o in outcomes} == {"In the app", "Save it as a report", "My phone"}


def test_artifact_writes_the_file_contract_with_a_derived_path(tmp_path):
    job = _job(targets=[JobDeliveryTarget(destination="Save it as a report", adapter="artifact")])
    adapters = default_adapters(None, tmp_path / "artifacts")
    outcomes = asyncio.run(deliver_all(job, "run_derived", _summary(), adapters))
    assert outcomes[0]["ok"] is True
    directory = tmp_path / "artifacts" / ".black-eclipse" / "artifacts" / "run_derived"
    assert (directory / "report.md").is_file()
    assert (directory / "receipt.json").is_file()
    assert (directory / "meta.json").is_file()
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    assert meta["runId"] == "run_derived"
    assert meta["jobName"] == "Overnight market brief"
    assert "report.md" in (directory / "report.md").name
    # The reported path is RELATIVE — no absolute location leaks.
    assert outcomes[0]["artifact"].startswith(".black-eclipse/")


def test_artifact_path_is_derived_and_a_malicious_run_id_cannot_traverse(tmp_path):
    adapter = ArtifactAdapter(tmp_path / "artifacts")
    summary = _summary()
    # A run id with traversal characters is sanitized to a safe leaf.
    outcome = asyncio.run(adapter.deliver(_job(targets=[]), "../../etc", summary))
    assert outcome.ok is True
    leaf = tmp_path / "artifacts" / ".black-eclipse" / "artifacts"
    assert leaf.is_dir()
    # No directory escaped the artifacts root.
    escaped = tmp_path / "artifacts" / "etc"
    assert not escaped.exists()


def test_a_failing_messaging_target_does_not_fail_the_other_targets(tmp_path):
    # The bus rejects the message event only; in_app and artifact must still succeed.
    bus = FakeBus(fail_types=("job.message",))
    job = _job(targets=[
        JobDeliveryTarget(destination="In the app", adapter="in_app"),
        JobDeliveryTarget(destination="Save it as a report", adapter="artifact"),
        JobDeliveryTarget(destination="My phone", adapter="messaging"),
    ])
    adapters = default_adapters(bus, tmp_path / "artifacts")
    outcomes = asyncio.run(deliver_all(job, "run_abc", _summary(), adapters))
    by_adapter = {o["adapter"]: o for o in outcomes}
    assert by_adapter["in_app"]["ok"] is True
    assert by_adapter["artifact"]["ok"] is True
    assert by_adapter["messaging"]["ok"] is False
    assert by_adapter["messaging"]["reasonCode"] == DELIVERY_FAILED


def test_one_raising_adapter_does_not_stop_the_others(tmp_path):
    class Exploding:
        name = "messaging"

        async def deliver(self, job, run_id, summary):
            raise RuntimeError("boom")

    bus = FakeBus()
    job = _job(targets=[
        JobDeliveryTarget(destination="In the app", adapter="in_app"),
        JobDeliveryTarget(destination="My phone", adapter="messaging"),
    ])
    adapters = {"in_app": default_adapters(bus)["in_app"], "messaging": Exploding()}
    outcomes = asyncio.run(deliver_all(job, "run_x", _summary(), adapters))
    by_adapter = {o["adapter"]: o for o in outcomes}
    assert by_adapter["in_app"]["ok"] is True
    assert by_adapter["messaging"]["ok"] is False
    assert by_adapter["messaging"]["reasonCode"] == DELIVERY_FAILED


# ── G1b — no destination refuses, never improvises ───────────────────────────


def test_messaging_without_a_destination_refuses_with_no_destination():
    job = _job(targets=[JobDeliveryTarget(destination="My phone", adapter="messaging")],
               adapter="messaging", destination=None)
    adapter = MessagingAdapter(FakeBus())
    outcome = asyncio.run(adapter.deliver(job, "run_x", _summary()))
    assert outcome.ok is False
    assert outcome.reason_code == NO_DESTINATION


def test_messaging_never_composes_a_sentence():
    # The adapter hands the surface a KEY + params — never prose composed here.
    bus = FakeBus()
    job = _job(targets=[JobDeliveryTarget(destination="My phone", adapter="messaging")],
               adapter="messaging", destination="My phone")
    adapter = MessagingAdapter(bus)
    summary = _summary()
    outcome = asyncio.run(adapter.deliver(job, "run_x", summary))
    assert outcome.ok is True
    event = next(e for e in bus.events if e["type"] == "job.message")
    assert event["data"]["templateKey"] == "jobs.delivery.message.doneCount"
    assert event["data"]["params"] == {"jobName": "Overnight market brief", "changeCount": 3}
    # No message body / sentence is present on the event — only the key + params.
    assert "message" not in event["data"]
    assert "body" not in event["data"]


# ── old-row-safe: a job with no new fields delivers exactly as before ────────


def test_a_job_saved_before_phase_11_yields_one_target(tmp_path):
    bus = FakeBus()
    job = _job(targets=[], adapter="artifact", destination=None)
    assert job.delivery.effective_targets()[0].adapter == "artifact"
    adapters = default_adapters(bus, tmp_path / "artifacts")
    outcomes = asyncio.run(deliver_all(job, "run_old", _summary(), adapters))
    assert len(outcomes) == 1
    assert outcomes[0]["adapter"] == "artifact"
    assert outcomes[0]["ok"] is True


def test_delivery_outcome_public_carries_target_and_reason_code():
    outcome = DeliveryOutcome("messaging", False, "nope", target="My phone",
                               reason_code=NO_DESTINATION)
    public = outcome.public()
    assert public["target"] == "My phone"
    assert public["reasonCode"] == NO_DESTINATION
    assert public["ok"] is False
