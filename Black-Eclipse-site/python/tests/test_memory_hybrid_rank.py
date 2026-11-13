"""W5.3 — hybrid retrieval wiring behind HARNESS_MEMORY_HYBRID."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory.eval import check_thresholds, run_evaluation
from harness.eclipse_memory.service import EclipseMemoryService
from harness.eclipse_memory.store import EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-hybrid-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _seed(service):
    service.write_memory(
        memory_type="semantic", content="The drawdown limit is 12 percent.",
        source="manual", scope="general", importance=0.5, confidence=0.8,
        allow_duplicate=True,
    )
    service.write_memory(
        memory_type="semantic",
        content="drawdown drawdown drawdown risk risk portfolio drawdown",
        source="manual", scope="general", importance=0.4, confidence=0.8,
        allow_duplicate=True,
    )
    # Deliberately unrelated and high-importance: hybrid must never admit it.
    service.write_memory(
        memory_type="semantic", content="The office is in Lisbon.",
        source="manual", scope="general", importance=1.0, confidence=0.9,
        allow_duplicate=True,
    )


def test_off_is_the_current_path(service, monkeypatch):
    monkeypatch.setenv("HARNESS_MEMORY_HYBRID", "off")
    _seed(service)
    outcome = service.retrieve(query="drawdown limit", scope="general", limit=8)
    assert outcome.diagnostics["hybrid"] is False
    assert outcome.diagnostics["bm25ByMemory"] == {}
    assert outcome.memories, "the lexical path must still recall"


def test_on_adds_bounded_bm25_and_keeps_the_gate(service, monkeypatch):
    monkeypatch.setenv("HARNESS_MEMORY_HYBRID", "on")
    _seed(service)
    outcome = service.retrieve(query="drawdown limit", scope="general", limit=8)
    assert outcome.diagnostics["hybrid"] is True
    assert outcome.diagnostics["bm25ByMemory"]
    assert outcome.memories
    selected = [m["content"] for m in outcome.memories]
    assert any("drawdown" in content for content in selected)
    # The unrelated, high-importance memory is still excluded by the relevance
    # gate even though hybrid ranking ran.
    assert not any("Lisbon" in content for content in selected)


def test_no_signal_query_does_not_admit_unrelated_memory(service, monkeypatch):
    monkeypatch.setenv("HARNESS_MEMORY_HYBRID", "on")
    _seed(service)
    outcome = service.retrieve(query="volatility surface", scope="general", limit=8)
    assert not any("Lisbon" in m["content"] for m in outcome.memories)


def test_labelled_eval_keeps_safety_thresholds_in_both_modes(monkeypatch):
    for mode in ("off", "on"):
        monkeypatch.setenv("HARNESS_MEMORY_HYBRID", mode)
        report = run_evaluation()
        verdict = check_thresholds(report)
        assert verdict["passed"], (mode, verdict["failures"], report["metrics"])
