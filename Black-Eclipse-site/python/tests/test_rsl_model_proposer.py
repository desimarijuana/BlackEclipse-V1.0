"""Model-proposer contracts: strict JSON, existing validators, opt-in wiring."""

from __future__ import annotations

import json

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.proposer import CandidateProposal, ProposalRefused
from harness.self_improvement.proposer_model import (
    model_settings_from_env,
    propose_variants,
)


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _candidate(**overrides):
    candidate = {
        "id": "evo_prop",
        "signature": "sig-prop",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "The same timeout recurs.",
        "targetPath": "python/harness/rsl_fixture.py",
    }
    candidate.update(overrides)
    return candidate


def _variant(ops=None, *, kind="invariant", target="python/harness/rsl_fixture.py"):
    return {
        "kind": kind,
        "targetPath": target,
        "rationale": "bounded fix",
        "ops": ops or [{
            "op": "replace",
            "path": target,
            "old": "VALUE = 1",
            "new": "VALUE = 2",
            "reason": "fix the timeout",
        }],
    }


async def _json_invoke(prompt):
    return json.dumps({"variants": [_variant()]})


@pytest.mark.asyncio
async def test_valid_model_variants_become_validated_proposals():
    proposals = await propose_variants(
        _candidate(), k=2, invoke=_json_invoke,
    )

    assert len(proposals) == 1
    assert isinstance(proposals[0], CandidateProposal)
    assert proposals[0].kind == "invariant"
    assert proposals[0].targetPath == "python/harness/rsl_fixture.py"
    assert proposals[0].ops[0]["op"] == "replace"


@pytest.mark.asyncio
async def test_invalid_json_is_refused():
    with pytest.raises(ProposalRefused) as exc:
        await propose_variants(_candidate(), invoke=lambda prompt: "not json")
    assert exc.value.code == "MODEL_PROPOSER_INVALID"


@pytest.mark.asyncio
async def test_missing_variants_are_refused():
    with pytest.raises(ProposalRefused) as exc:
        await propose_variants(_candidate(), invoke=lambda prompt: '{"variants": []}')
    assert exc.value.code == "MODEL_PROPOSER_INVALID"


@pytest.mark.asyncio
async def test_frozen_target_is_refused_by_the_existing_guard():
    bad = _variant(target="python/tests/test_frozen.py")
    with pytest.raises(ProposalRefused) as exc:
        await propose_variants(
            _candidate(), invoke=lambda prompt: json.dumps({"variants": [bad]}),
        )
    assert exc.value.code == "RSL_FROZEN_TARGET"


@pytest.mark.asyncio
async def test_provider_failure_is_an_honest_refusal():
    def broken(prompt):
        raise RuntimeError("no provider")

    with pytest.raises(ProposalRefused) as exc:
        await propose_variants(_candidate(), invoke=broken)
    assert exc.value.code == "MODEL_PROPOSER_UNAVAILABLE"


def test_model_settings_prefer_rsl_over_job_env():
    settings = model_settings_from_env({
        "HARNESS_JOB_PROVIDER": "job-provider",
        "HARNESS_JOB_MODEL": "job-model",
        "HARNESS_RSL_PROVIDER": "rsl-provider",
        "HARNESS_RSL_MODEL": "rsl-model",
    })
    assert settings.provider == "rsl-provider"
    assert settings.model == "rsl-model"


@pytest.mark.asyncio
async def test_propose_mode_persists_model_children_only_when_enabled(store):
    evolution = EvolutionStore(store)
    parent = evolution.save_candidate({
        "signature": "sig-parent",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "The same timeout recurs.",
        "status": "inert",
    })
    calls = []

    async def fake_model(candidate, k, actor):
        calls.append(candidate["id"])
        return [CandidateProposal(
            id="v1", kind="invariant", targetPath="python/harness/rsl_fixture.py",
            ops=({
                "op": "create", "path": "python/harness/rsl_fixture.py",
                "content": "VALUE = 2\n", "reason": "fix",
            },),
        )]

    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="propose", model_proposer=True),
        run_store=store, evolution=evolution, model_propose_fn=fake_model,
    )
    result = await loop.tick()

    assert calls == [parent["id"]]
    assert len(result["proposed"]) == 1
    child = evolution.get_candidate(result["proposed"][0])
    assert child["status"] == "proposed"
    assert child["targetPath"] == "python/harness/rsl_fixture.py"
    assert child["proposedOps"][0]["op"] == "create"


@pytest.mark.asyncio
async def test_propose_mode_never_calls_the_model_when_disabled(store):
    evolution = EvolutionStore(store)
    evolution.save_candidate({
        "signature": "sig-parent",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "The same timeout recurs.",
        "status": "inert",
    })
    calls = []

    def fake_model(*args, **kwargs):
        calls.append(True)
        return []

    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="propose", model_proposer=False),
        run_store=store, evolution=evolution, model_propose_fn=fake_model,
    )
    result = await loop.tick()

    assert result["proposed"] == []
    assert calls == []


@pytest.mark.asyncio
async def test_model_refusal_is_recorded_not_raised(store):
    evolution = EvolutionStore(store)
    parent = evolution.save_candidate({
        "signature": "sig-parent",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "The same timeout recurs.",
        "status": "inert",
    })

    def fake_model(candidate, k, actor):
        raise ProposalRefused("MODEL_PROPOSER_UNAVAILABLE", "no provider")

    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="propose", model_proposer=True),
        run_store=store, evolution=evolution, model_propose_fn=fake_model,
    )
    result = await loop.tick()

    assert result["proposed"] == []
    assert result["refused"][0]["candidateId"] == parent["id"]
    assert result["refused"][0]["code"] == "MODEL_PROPOSER_UNAVAILABLE"
