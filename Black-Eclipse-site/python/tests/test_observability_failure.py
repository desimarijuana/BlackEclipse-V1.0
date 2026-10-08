"""Failure-mode tests — telemetry outages must never break the runtime."""

from __future__ import annotations

import time

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.exporters import BaseExporter, BoundedExporter


class _FlakyExporter(BaseExporter):
    name = "flaky"

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.attempts = 0
        self.received: list[list[dict]] = []

    def export(self, kind, records):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("backend down")
        self.received.append(records)


class _DeadExporter(BaseExporter):
    name = "dead"

    def export(self, kind, records):
        raise ConnectionError("collector unreachable")


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_flaky_exporter_retries_then_succeeds():
    exporter = _FlakyExporter(fail_times=1)
    wrapped = BoundedExporter(exporter, batch_size=1, batch_interval_s=0.05, max_retries=3)
    try:
        assert wrapped.submit("span", {"traceId": "t1"}) is True
        assert _wait_for(lambda: exporter.received)
        assert wrapped.stats.retried >= 1
        assert wrapped.stats.exported >= 1
    finally:
        wrapped.close()


def test_dead_exporter_opens_circuit_and_runtime_continues():
    exporter = _DeadExporter()
    wrapped = BoundedExporter(
        exporter, batch_size=1, batch_interval_s=0.05,
        max_retries=0, circuit_failure_threshold=2, circuit_reset_s=30.0,
    )
    try:
        for i in range(5):
            wrapped.submit("span", {"traceId": f"t{i}"})
        assert _wait_for(lambda: not wrapped.healthy())
        snapshot = wrapped.snapshot()
        assert snapshot["dropped"] >= 1
        assert snapshot["failed"] >= 1
        assert snapshot["circuitOpen"] is True
        wrapped.force_circuit_reset()
        assert wrapped.healthy() is True
    finally:
        wrapped.close()


def test_submit_is_non_blocking_under_backpressure():
    class _SlowExporter(BaseExporter):
        name = "slow"

        def export(self, kind, records):
            time.sleep(0.2)

    wrapped = BoundedExporter(_SlowExporter(), queue_size=64, batch_size=1, batch_interval_s=0.05, max_retries=0)
    try:
        started = time.monotonic()
        for i in range(200):
            wrapped.submit("span", {"i": i})
        elapsed = time.monotonic() - started
        assert elapsed < 1.0
        assert wrapped.stats.dropped > 0
    finally:
        wrapped.close()


def test_hub_survives_dead_exporter_backend():
    hub = ObservabilityHub(ObservabilityConfig(jsonl_dir=""), capture_inmemory=True, start_exporters=False)
    hub.add_exporter(_DeadExporter())
    for _ in range(10):
        hub.emit("onToolEnd", tool_name="x", status="OK", duration_ms=10.0)
    assert hub.diagnostics()["observedHooks"]["onToolEnd"] == 10


def test_hub_disabled_config_is_harmless():
    hub = ObservabilityHub(ObservabilityConfig(enabled=False), capture_inmemory=True, start_exporters=False)
    event = hub.emit("onRunEnd", status="OK", duration_ms=1.0)
    assert event.hook == "onRunEnd"
