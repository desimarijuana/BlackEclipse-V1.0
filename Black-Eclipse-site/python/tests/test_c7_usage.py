"""C7: process USE sampling and orphan sweeping are real, or honest."""

from __future__ import annotations

from harness.observability.context import ObservationContext
from harness.observability.core import ObservabilityHub
from harness.observability.usage import process_usage, reset_usage_sampler


def _hub() -> ObservabilityHub:
    from harness.observability.config import ObservabilityConfig

    return ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )


def test_process_usage_is_real_or_honestly_unavailable():
    reset_usage_sampler()
    usage = process_usage()
    assert isinstance(usage, dict)
    assert "available" in usage
    if usage["available"]:
        assert usage["memoryBytes"] is None or usage["memoryBytes"] > 0
        assert usage["threads"] >= 1


def test_refresh_records_use_gauges_when_available():
    reset_usage_sampler()
    hub = _hub()
    usage = hub.refresh_use_metrics()
    gauges = hub.metrics.snapshot()["gauges"]
    assert "eclipse_runs_active_sampled" in gauges
    assert "eclipse_worker_utilization" in gauges
    if usage.get("available"):
        assert "eclipse_process_threads" in gauges
        # Working set can be unreadable on a hardened/older platform; the gauge
        # is present only when the value is real.
        if usage.get("memoryBytes") is not None:
            assert "eclipse_process_memory_bytes" in gauges


def test_orphan_sweep_counts_a_run_that_never_reachd_a_terminal_state():
    hub = _hub()
    hub.emit("onRunStart", context=ObservationContext(run_id="orphan_1"))
    swept = hub.sweep_orphans(max_age_s=0)
    assert swept == 1
    report = hub.release_report()
    assert report["runs"]["orphaned"] == 1
    assert report["runs"]["active"] == 0
    orphans = next(s for s in report["slos"]["objectives"] if s["name"] == "orphan_rate")
    assert orphans["healthy"] is False
