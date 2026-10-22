"""The operator digest: what the loop did, what it cost, where it drifts."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.self_improvement.report import build_digest, render_markdown


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def test_the_digest_reports_unknown_instead_of_zero(store):
    digest = build_digest(store, days=7)
    assert digest["days"] == 7
    experiments = digest["experiments"]
    # No experiment has run: the measures are UNKNOWN (None), never a fake 0.
    assert experiments["rsl_experiments"] == 0
    assert experiments["rsl_accepted"] == 0
    assert experiments["cost_usd"] is None
    assert experiments["cost_per_accepted"] is None
    assert experiments["regression_rate"] is None
    assert digest["candidates"] == {}
    assert digest["recentCandidates"] == []
    assert digest["lessons"] == []


def test_the_digest_summarises_recorded_experiments(store):
    from harness.evaluation.store import EvaluationStore

    EvaluationStore(store).create_run(
        id="rsl-run-1",
        suite="rsl-recursion",
        datasetName="rsl-recursion",
        datasetVersion="1",
        datasetChecksum="abc",
        tier=0,
        invoker="rsl-recursion",
        agentVersion="v1",
        config={"kind": "rsl-recursion", "costUsd": 0.5},
        metadata={
            "kind": "rsl-recursion",
            "decision": "composed",
            "benchmark": "MEASURED",
        },
        status="completed",
    )

    digest = build_digest(store, days=7)
    experiments = digest["experiments"]
    assert experiments["rsl_experiments"] == 1
    assert experiments["rsl_accepted"] == 1
    assert experiments["cost_usd"] == 0.5
    assert experiments["cost_per_accepted"] == 0.5

    markdown = render_markdown(digest)
    assert "# RSL digest" in markdown
    assert "rsl_accepted" in markdown
    assert "UNKNOWN" in markdown  # the measures that were never measured


def test_the_digest_counts_candidates(store):
    from harness.code.evolution_store import EvolutionStore

    evolution = EvolutionStore(store)
    evolution.save_candidate({
        "signature": "sig-digest-1", "sourceCategory": "drift",
        "observedCount": 1, "problemStatement": "a drop", "status": "inert",
    })
    digest = build_digest(store, days=7)
    assert digest["candidates"].get("inert") == 1
    assert digest["recentCandidates"][0]["id"]
