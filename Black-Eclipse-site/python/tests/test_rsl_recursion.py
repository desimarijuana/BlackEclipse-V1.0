"""RSL R7 — recursive candidates: typed proposals, selection and composition."""

from __future__ import annotations

import pytest

from harness.evaluation.store import EvaluationStore
from harness.evaluation.trajectory import Trajectory
from harness.evaluation.verdict_guard import VerdictLeakError
from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.composition import compose_verified, merge_verified_ops
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.proposer import (
    ProposalRefused,
    propose_many,
)
from harness.self_improvement.recursion import budgeted_k, run_recursive
from harness.self_improvement.selection import (
    anonymous_labels,
    build_selection,
)


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _candidate():
    return {
        "id": "evo_recursive",
        "signature": "sig-recursive",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "A repeated timeout needs a bounded fix.",
        "title": "Bound the timeout",
        "targetPath": "python/harness/rsl_fixture.py",
        "proposedOps": [{
            "op": "create",
            "path": "python/harness/rsl_fixture.py",
            "content": "VALUE = 1\n",
            "reason": "baseline fix",
        }],
        "status": "inert",
        "createdByRunId": "run-source",
    }


def _variants():
    return [
        {
            "kind": "invariant",
            "targetPath": "python/harness/rsl_fixture_a.py",
            "ops": [{
                "op": "create",
                "path": "python/harness/rsl_fixture_a.py",
                "content": "A = 1\n",
                "reason": "general bound",
            }],
        },
        {
            "kind": "domain",
            "targetPath": "python/harness/rsl_fixture_b.py",
            "ops": [{
                "op": "create",
                "path": "python/harness/rsl_fixture_b.py",
                "content": "B = 1\n",
                "reason": "domain bound",
            }],
        },
        {
            "kind": "domain",
            "targetPath": "python/harness/rsl_fixture_c.py",
            "ops": [{
                "op": "create",
                "path": "python/harness/rsl_fixture_c.py",
                "content": "C = 1\n",
                "reason": "third bound",
            }],
        },
    ]


def _verified(label, score, *, path, passed=True, answered=True):
    return {
        "id": f"candidate_{label.upper()}",
        "label": label.upper(),
        "kind": "invariant",
        "targetPath": path,
        "ops": [{
            "op": "create",
            "path": path,
            "content": f"{label} = 1\n",
            "reason": "fixture",
        }],
        "answered": answered,
        "passed": passed,
        "score": score,
        "benchmark": "MEASURED" if score is not None else "UNMEASURED",
    }


def test_anonymous_labels_are_seeded_and_order_independent():
    ids = ["v1", "v2", "v3", "v4"]
    first = anonymous_labels(ids, seed=7)
    assert first == anonymous_labels(ids, seed=7)
    assert first == anonymous_labels(list(reversed(ids)), seed=7)
    assert sorted(first.values()) == ["A", "B", "C", "D"]
    assert first != anonymous_labels(ids, seed=8)


def test_non_answers_are_dropped_with_a_cause():
    record = build_selection([
        _verified("a", None, path="python/harness/a.py"),
        {
            "id": "v2", "kind": "domain", "answered": False,
            "cause": "verification_error:RuntimeError",
            "targetPath": "python/harness/b.py", "ops": [],
        },
    ], seed=1)
    assert record["chosen"] == "candidate_A"
    assert [item["cause"] for item in record["dropped"]] == [
        "verification_error:RuntimeError",
    ]
    assert record["nCandidates"] == 1


def test_selection_falls_back_neutrally_to_the_base():
    record = build_selection([
        {
            "id": "v1", "kind": "invariant", "answered": True,
            "passed": False, "cause": "tests_failed",
            "targetPath": "python/harness/a.py", "ops": [],
        },
    ], seed=2)
    assert record["fallback"] is True
    assert record["chosen"] == "base"
    assert record["chosenLabel"] == "base"
    assert record["rejected"][0]["cause"] == "tests_failed"


def test_selection_refuses_a_verdict_leak():
    with pytest.raises(VerdictLeakError, match="expected_output"):
        build_selection([
            {
                "id": "expected_output", "kind": "invariant", "answered": True,
                "passed": True, "targetPath": "python/harness/a.py", "ops": [],
            },
        ], seed=1)


def test_propose_many_types_and_caps_k():
    proposals = propose_many(_candidate(), 2, variants=_variants())
    assert [proposal.kind for proposal in proposals] == ["invariant", "domain"]
    assert [proposal.id for proposal in proposals] == ["v1", "v2"]
    assert proposals[0].targetPath == "python/harness/rsl_fixture_a.py"

    trivial = propose_many(_candidate(), 1)
    assert len(trivial) == 1
    assert trivial[0].kind == "invariant"
    assert trivial[0].targetPath == "python/harness/rsl_fixture.py"


def test_propose_many_refuses_missing_variants_and_frozen_targets():
    with pytest.raises(ProposalRefused) as missing:
        propose_many(_candidate(), 2)
    assert missing.value.code == "PROPOSAL_NO_VARIANTS"

    with pytest.raises(ProposalRefused) as frozen:
        propose_many(_candidate(), 1, variants=[{
            "kind": "invariant",
            "targetPath": "python/tests/test_rsl_recursion.py",
            "ops": [{
                "op": "create",
                "path": "python/tests/test_rsl_recursion.py",
                "content": "x = 1\n",
            }],
        }])
    assert frozen.value.code == "RSL_FROZEN_TARGET"


def test_propose_many_refuses_an_untyped_variant():
    with pytest.raises(ProposalRefused) as invalid:
        propose_many(_candidate(), 1, variants=[{
            "kind": "everything",
            "targetPath": "python/harness/rsl_fixture_a.py",
            "ops": [{"op": "create", "path": "python/harness/rsl_fixture_a.py", "content": "A=1\n"}],
        }])
    assert invalid.value.code == "PROPOSAL_INVALID_KIND"

    with pytest.raises(ProposalRefused) as bad_op:
        propose_many(_candidate(), 1, variants=[{
            "kind": "invariant",
            "targetPath": "python/harness/rsl_fixture_a.py",
            "ops": ["not-an-operation"],
        }])
    assert bad_op.value.code == "PROPOSAL_INVALID_VARIANT"


@pytest.mark.asyncio
async def test_recursive_k_gt_1_records_a_selection(store):
    eval_store = EvaluationStore(store)
    calls = []

    def verify(proposal):
        calls.append(proposal.kind)
        return {"passed": True, "benchmark": "UNMEASURED"}

    result = await run_recursive(
        _candidate(),
        verify_fn=verify,
        k=2,
        variants=_variants(),
        seed=3,
        eval_store=eval_store,
    )
    assert result["refused"] is False
    assert result["k"] == 2
    assert calls == ["invariant", "domain"]
    assert result["selection"]["k"] == 2
    assert result["selection"]["nCandidates"] == 2
    assert result["composition"]["decision"] == "no_gain"
    assert result["benchmark"] == "UNMEASURED"

    run = eval_store.get_run(result["runId"])
    assert run is not None
    assert run["status"] == "completed"
    assert run["config"]["kind"] == "rsl-recursion"
    assert run["config"]["k"] == 2
    assert run["metadata"]["selection"]["chosen"] in ("v1", "v2")
    assert run["metadata"]["composition"]["decision"] == "no_gain"


@pytest.mark.asyncio
async def test_budget_stops_at_the_remaining_allowance(store):
    calls = []

    def verify(proposal):
        calls.append(proposal.id)
        return {"passed": True, "benchmark": "UNMEASURED"}

    result = await run_recursive(
        _candidate(), verify_fn=verify, k=3, variants=_variants(),
        max_per_day=3, started_today=2,
    )
    assert result["refused"] is False
    assert result["requestedK"] == 3
    assert result["k"] == 1
    assert calls == ["v1"]

    refused = await run_recursive(
        _candidate(), verify_fn=verify, k=3, variants=_variants(),
        max_per_day=3, started_today=3,
    )
    assert refused["refused"] is True
    assert refused["reason"] == "daily_budget"
    assert calls == ["v1"]


def test_budgeted_k_is_honest_about_zero_remaining():
    assert budgeted_k(3, max_per_day=3, started_today=2) == {
        "requested": 3, "allowed": 1, "remaining": 1, "refused": False,
    }
    assert budgeted_k(3, max_per_day=3, started_today=5)["refused"] is True
    assert budgeted_k(2)["allowed"] == 2


@pytest.mark.asyncio
async def test_composition_only_claims_a_measured_gain():
    verified = [
        _verified("a", 0.5, path="python/harness/compose_a.py"),
        _verified("b", 0.6, path="python/harness/compose_b.py"),
    ]

    async def beats(_composed):
        return {"passed": True, "benchmark": "MEASURED", "score": 0.8}

    async def ties(_composed):
        return {"passed": True, "benchmark": "MEASURED", "score": 0.6}

    won = await compose_verified(verified, measure=beats)
    assert won["decision"] == "composed"
    assert won["benchmark"] == "MEASURED"
    assert won["composedScore"] == 0.8

    tied = await compose_verified(verified, measure=ties)
    assert tied["decision"] == "no_gain"
    assert tied["benchmark"] == "UNMEASURED"

    unmeasured = await compose_verified(verified, measure=lambda _c: {
        "passed": True, "benchmark": "UNMEASURED", "score": 0.9,
    })
    assert unmeasured["decision"] == "no_gain"

    without_measure = await compose_verified(verified)
    assert without_measure["decision"] == "no_gain"


@pytest.mark.asyncio
async def test_composition_never_merges_unverified_or_conflicting_ops():
    passed = _verified("a", 0.5, path="python/harness/compose_a.py")
    failed = _verified("b", 0.6, path="python/harness/compose_b.py", passed=False)
    selected = await compose_verified([passed, failed])
    assert selected["decision"] == "selected"
    assert selected["chosenLabel"] == "A"

    conflict_a = _verified("a", 0.5, path="python/harness/same.py")
    conflict_b = _verified("b", 0.6, path="python/harness/same.py")
    assert merge_verified_ops([conflict_a, conflict_b]) is None
    conflict = await compose_verified([conflict_a, conflict_b])
    assert conflict["decision"] == "selected"
    assert conflict["chosenLabel"] == "B"


@pytest.mark.asyncio
async def test_loop_uses_configured_k_and_budget(store):
    eval_store = EvaluationStore(store)
    evolution = EvolutionStore(store)
    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="verify", k=2, max_experiments_per_day=3),
        run_store=store,
        evolution=evolution,
        eval_store=eval_store,
    )
    calls = []

    def verify(proposal):
        calls.append(proposal.id)
        return {"passed": True, "benchmark": "UNMEASURED"}

    result = await loop.run_recursive(
        _candidate(), verify_fn=verify, variants=_variants(), seed=1,
    )
    assert result["refused"] is False
    assert result["k"] == 2
    assert calls == ["v1", "v2"]
    assert len(result["attemptIds"]) == 2
    assert evolution.experiments_started_since("1970-01-01T00:00:00.000Z") == 2
    run = eval_store.get_run(result["runId"])
    assert run["config"]["k"] == 2

    second = await loop.run_recursive(
        _candidate(), verify_fn=verify, variants=_variants(), seed=1,
    )
    assert second["k"] == 1
    assert calls == ["v1", "v2", "v1"]
    assert evolution.experiments_started_since("1970-01-01T00:00:00.000Z") == 3


@pytest.mark.asyncio
async def test_recursive_entry_point_is_dark_outside_verify_mode(store):
    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="observe", k=2),
        run_store=store,
        evolution=EvolutionStore(store),
        eval_store=EvaluationStore(store),
    )
    result = await loop.run_recursive(
        _candidate(), verify_fn=lambda proposal: {"passed": True},
        variants=_variants(),
    )
    assert result["refused"] is True
    assert result["reason"] == "mode"

    busy = RSLLoop(
        service=None,
        config=RSLConfig(mode="verify", k=2),
        run_store=store,
        evolution=EvolutionStore(store),
        eval_store=EvaluationStore(store),
    )
    busy._busy = True
    try:
        refused = await busy.run_recursive(
            _candidate(), verify_fn=lambda proposal: {"passed": True},
            variants=_variants(),
        )
    finally:
        busy._busy = False
    assert refused["refused"] is True
    assert refused["reason"] == "busy"


@pytest.mark.asyncio
async def test_contrast_bundle_is_guarded_before_recording(tmp_path):
    def verify(_proposal):
        return {"passed": True, "benchmark": "UNMEASURED"}

    leaky = Trajectory.from_events(
        [
            {"type": "run.started", "at": "t1", "data": {}},
            {"type": "model.requested", "at": "t2", "data": {"note": "pass_rate 0.9"}},
            {"type": "run.completed", "at": "t3", "data": {}},
        ],
        run_id="run-leaky",
        task_id="task",
        trial_id="trial",
    )
    with pytest.raises(VerdictLeakError, match="pass_rate"):
        await run_recursive(
            _candidate(),
            verify_fn=verify,
            k=1,
            seed=1,
            trajectories={"base": leaky, "A": leaky},
            evidence_dir=tmp_path / "bundle",
        )
