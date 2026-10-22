"""The surface lab: deterministic variants, honest ranking, no invented winner."""

from __future__ import annotations

import pytest

from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.surface_lab import (
    compare_variants,
    propose_variants,
    render_markdown,
)


def _base() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolNames=("eval_service_call",),
        maxSteps=8,
        maxToolCalls=20,
    )


def _lessons(count: int = 2) -> list[dict]:
    return [
        {
            "id": f"lesson-{index}",
            "cue": f"cue {index}",
            "proposedLesson": f"lesson {index} says do the bounded thing",
        }
        for index in range(count)
    ]


def test_variants_are_derived_from_the_adopted_lessons():
    variants = propose_variants(_base(), _lessons(2))
    assert [variant.name for variant in variants] == [
        "lesson-1", "lesson-3", "lesson-cues",
        "policy-no-manifest", "guardrail-citation",
    ]
    # The lab searches the WHOLE surface, not only the prompt.
    assert variants[3].snapshot.skillManifest == "none"
    assert variants[4].snapshot.guardrails == ("require_citation",)
    assert "lesson 0 says do the bounded thing" in variants[0].snapshot.toolGuidance
    assert variants[0].derived_from == ["lesson-0"]
    # The base prompt is never changed - only bounded guidance is added.
    assert variants[0].snapshot.systemPrompt == "You are Eclipse."
    assert variants[0].snapshot.toolNames == ("eval_service_call",)


def test_without_a_lesson_there_is_no_variant():
    assert propose_variants(_base(), []) == []
    assert propose_variants(_base(), [{"id": "x", "proposedLesson": ""}]) == []


def test_the_guidance_stays_bounded():
    lessons = [{
        "id": "big", "cue": "c", "proposedLesson": "x" * 10_000,
    }]
    variant = propose_variants(_base(), lessons)[0]
    assert len(variant.snapshot.toolGuidance) <= 4_000


def _row(name: str, *, before: float, after: float, measured: bool = True,
         regressions: list | None = None):
    return {
        "name": name,
        "kind": "toolGuidance",
        "derivedFrom": ["lesson-0"],
        "runId": f"run-{name}",
        "decisionRecord": {
            "measured": measured,
            "targetBefore": before,
            "targetAfter": after,
            "regressions": regressions or [],
        },
    }


def test_a_measured_gain_wins():
    result = compare_variants(1.0, [
        _row("flat", before=1.0, after=1.0),
        _row("better", before=1.0, after=1.25),
    ])
    assert result["winner"] == "better"
    assert result["variants"][0]["verdict"] == "improved"


def test_a_critical_regression_vetoes_the_average_gain():
    result = compare_variants(1.0, [
        _row("regressed", before=1.0, after=1.5, regressions=[
            {"dimension": "safety_score", "critical": True},
        ]),
    ])
    assert result["winner"] is None
    assert result["variants"][0]["verdict"] == "vetoed"
    assert result["variants"][0]["criticalRegressions"]


def test_an_unmeasured_variant_never_wins():
    result = compare_variants(1.0, [
        _row("unmeasured", before=1.0, after=9.0, measured=False),
    ])
    assert result["winner"] is None
    assert result["variants"][0]["verdict"] == "unmeasured"
    assert "UNKNOWN" in render_markdown(result)


@pytest.mark.asyncio
async def test_the_live_tier_reaches_the_invoker_with_explicit_settings(
    tmp_path, monkeypatch,
):
    """The live tier must pass the real provider/model down - and never guess one."""
    from harness.evaluation.candidate_invoker import CandidateAgentInvoker
    from harness.persistence import AgentMemoryStore
    from harness.schemas import ModelSettings
    from harness.self_improvement import verifier as verifier_module
    from harness.self_improvement.surface_lab import run_lab

    seen: list[dict] = []

    class _Recorder(CandidateAgentInvoker):
        def __init__(self, store, snapshot, **kwargs):
            seen.append(dict(kwargs))
            # The recorded settings are what matters here; the run itself stays
            # deterministic (no provider is contacted in a test).
            super().__init__(store, snapshot, **{**kwargs, "live": False})

    monkeypatch.setattr(verifier_module, "CandidateAgentInvoker", _Recorder)

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        settings = ModelSettings(provider="openai", model="gpt-x")
        lab = await run_lab(
            store, [_task_fixture()], _base(), _lessons(1),
            trials=1, split="validation", live=True, model_settings=settings,
        )
        assert lab["variants"]
        assert seen, "the invoker must have been built"
        assert any(row.get("live") is True for row in seen)
        assert any(row.get("model_settings") is settings for row in seen)
    finally:
        store.close()


def _task_fixture():
    from harness.evaluation.tasks import EvaluationTask

    return EvaluationTask.from_dict({
        "id": "lab.live",
        "version": 1,
        "name": "lab task",
        "description": "lab fixture",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "Reply READY."},
        "expected_output": {"equals": "READY"},
        "graders": [{"name": "exact"}],
        "metadata": {
            "tier": 0,
            "suites": ["core"],
            "agent_script": [{"type": "final", "content": "READY"}],
        },
    })


@pytest.mark.asyncio
async def test_the_lab_never_invents_a_winner_on_the_scripted_tier(tmp_path):
    """The scripted tier replays a fixed answer, so a prompt change moves
    nothing. The lab must report 'flat', not a winner."""
    from harness.evaluation.tasks import EvaluationTask
    from harness.persistence import AgentMemoryStore
    from harness.self_improvement.surface_lab import run_lab

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        task = EvaluationTask.from_dict({
            "id": "lab.one",
            "version": 1,
            "name": "lab task",
            "description": "lab fixture",
            "category": "core",
            "difficulty": "easy",
            "input": {"prompt": "Reply READY."},
            "expected_output": {"equals": "READY"},
            "graders": [{"name": "exact"}],
            "metadata": {
                "tier": 0,
                "suites": ["core"],
                "agent_script": [{"type": "final", "content": "READY"}],
            },
        })
        lab = await run_lab(
            store, [task], _base(), _lessons(2), trials=1, split="validation",
        )
        assert lab["variants"], "the lab must report the variants it tried"
        assert all(row["measured"] for row in lab["variants"])
        assert all(row["verdict"] == "flat" for row in lab["variants"])
        assert lab["winner"] is None
    finally:
        store.close()
