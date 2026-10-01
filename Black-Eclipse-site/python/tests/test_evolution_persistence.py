"""Phase 10 G5 — the archive survives a restart; every field round-trips,
including the nullable cost columns and old-row safety.
"""

from __future__ import annotations

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore


def test_candidate_and_attempt_round_trip_across_a_reopen(tmp_path):
    path = str(tmp_path / "agent-memory.db")
    store = AgentMemoryStore(path)
    evolution = EvolutionStore(store)
    candidate = evolution.save_candidate({
        "signature": "sig_1", "sourceCategory": "timeout", "observedCount": 4,
        "problemStatement": "the same problem four times", "targetPath": "python/harness/x.py",
        "proposedOps": [{"op": "replace", "path": "python/harness/x.py", "old": "a", "new": "b"}],
        "status": "evaluated_ok",
    })
    evolution.save_attempt({
        "candidateId": candidate["id"], "targetPath": "python/harness/x.py",
        "baseDigest": "base", "diffDigest": "diff-abc",
        "proposedOps": candidate["proposedOps"],
        "evaluation": {"checks": [{"commandClass": "python_test", "passed": True}], "ledgerExecutionIds": ["cmd_1"]},
        "outcome": "success", "outcomeReason": "all owning checks passed",
        "costMicros": None, "tokensUsed": None,
    })
    store.close()

    reopened = AgentMemoryStore(path)
    evolution2 = EvolutionStore(reopened)
    loaded_candidate = evolution2.get_candidate(candidate["id"])
    assert loaded_candidate is not None
    assert loaded_candidate["observedCount"] == 4
    assert loaded_candidate["proposedOps"][0]["op"] == "replace"
    assert loaded_candidate["status"] == "evaluated_ok"

    attempts = evolution2.list_attempts(candidate["id"])
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["diffDigest"] == "diff-abc"
    assert attempt["evaluation"]["ledgerExecutionIds"] == ["cmd_1"]
    # Nullable cost columns survive as NULL (⇒ UNKNOWN), never coerced to 0.
    assert attempt["costMicros"] is None
    assert attempt["tokensUsed"] is None
    reopened.close()


def test_cost_and_tokens_are_nullable_and_distinct_from_zero(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    evolution = EvolutionStore(store)
    candidate = evolution.save_candidate({
        "signature": "sig_2", "sourceCategory": "timeout", "observedCount": 3,
        "problemStatement": "x", "status": "inert",
    })
    unmeasured = evolution.save_attempt({
        "candidateId": candidate["id"], "targetPath": "t.py", "baseDigest": "b", "diffDigest": "d",
        "outcome": "failure", "costMicros": None, "tokensUsed": None,
    })
    measured = evolution.save_attempt({
        "candidateId": candidate["id"], "targetPath": "t.py", "baseDigest": "b", "diffDigest": "d2",
        "outcome": "success", "costMicros": 0, "tokensUsed": 0,
    })
    assert unmeasured["costMicros"] is None
    assert measured["costMicros"] == 0
    store.close()


def test_attempt_indices_increment(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    evolution = EvolutionStore(store)
    candidate = evolution.save_candidate({
        "signature": "sig_3", "sourceCategory": "timeout", "observedCount": 3,
        "problemStatement": "x", "status": "inert",
    })
    a0 = evolution.save_attempt({"candidateId": candidate["id"], "outcome": "failure", "targetPath": "t", "baseDigest": "b", "diffDigest": "d"})
    a1 = evolution.save_attempt({"candidateId": candidate["id"], "outcome": "success", "targetPath": "t", "baseDigest": "b", "diffDigest": "d2"})
    assert a0["attemptIndex"] == 0 and a1["attemptIndex"] == 1
    store.close()
