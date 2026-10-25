"""Graph health watch: thresholds, thin data, and transition-only alerts."""

from __future__ import annotations

from types import SimpleNamespace

from harness.graph_runtime import health_watch
from harness.graph_runtime.health_watch import GraphHealthWatcher, evaluate_health


def _health(total=10, failure=0.0, queue_p95=None):
    return {
        "runs": {"total": total, "failureRate": failure},
        "queueWaitMs": {"p95": queue_p95},
    }


def test_thin_data_is_insufficient_not_healthy():
    verdict = evaluate_health(_health(total=2), min_runs=5)
    assert verdict["status"] == "insufficient"
    assert "need 5" in verdict["reasons"][0]


def test_failure_rate_and_queue_wait_degrade_health():
    verdict = evaluate_health(_health(failure=0.6), failure_rate=0.5, min_runs=5)
    assert verdict["status"] == "degraded"
    assert "failure rate" in verdict["reasons"][0]

    verdict = evaluate_health(_health(queue_p95=90_000), queue_p95_ms=60_000, min_runs=5)
    assert verdict["status"] == "degraded"
    assert "queue wait" in verdict["reasons"][0]


def test_healthy_is_quiet():
    assert evaluate_health(_health(failure=0.1, queue_p95=100), min_runs=5) == {
        "status": "healthy", "reasons": [],
    }


class _FakeStore:
    def __init__(self, health, status="unmeasured"):
        self._health = health
        self._status = status
        self.saved = []

    def health(self, *, window_hours):
        return self._health

    def watch_state(self):
        return {"status": self._status, "reasons": [], "checkedAt": None}

    def save_watch_state(self, status, reasons):
        self.saved.append((status, reasons))
        self._status = status


def test_watcher_publishes_only_on_transitions(monkeypatch):
    events = []
    monkeypatch.setattr(health_watch, "publish_event", lambda name, payload: events.append((name, payload)))
    store = _FakeStore(_health(failure=0.8))
    watcher = GraphHealthWatcher(SimpleNamespace(graphs=SimpleNamespace(_store=store)), interval_seconds=0)

    first = watcher.check()
    assert first["status"] == "degraded"
    assert first["transition"] == "degraded"
    assert events[0][0] == "graph.health_degraded"

    second = watcher.check()
    assert second["transition"] is None
    assert len(events) == 1

    store._health = _health(failure=0.0)
    recovered = watcher.check()
    assert recovered["transition"] == "healthy"
    assert events[-1][0] == "graph.health_recovered"
