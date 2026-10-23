"""Typed operators and the novelty veto for RSL proposals."""

from __future__ import annotations

import pytest

from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.operators import (
    OPERATORS,
    classify_ops,
    classify_snapshot,
    jaccard_novelty,
    op_signature,
    tokens_for_ops,
)
from harness.self_improvement.proposer import ProposalRefused, propose_many


def _candidate():
    return {
        "id": "evo_ops",
        "signature": "sig-ops",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "A repeated timeout needs a bounded fix.",
        "targetPath": "python/harness/rsl_fixture.py",
        "proposedOps": [{
            "op": "create",
            "path": "python/harness/rsl_fixture.py",
            "content": "VALUE = 1\n",
            "reason": "baseline",
        }],
        "status": "inert",
        "createdByRunId": "run-source",
    }


def _create(path: str, content: str = "X = 1\n"):
    return {
        "kind": "invariant",
        "targetPath": path,
        "ops": [{
            "op": "create",
            "path": path,
            "content": content,
            "reason": "fixture",
        }],
    }


def test_the_operator_registry_is_closed_and_typed():
    assert "code_patch" in OPERATORS
    assert "prompt" in OPERATORS
    assert classify_ops("python/harness/x.py", [{"op": "create", "path": "x"}]) == "code_patch"
    assert classify_ops("", [{"systemPrompt": "new"}]) == "prompt"
    assert classify_ops("", [{"guardrails": ["require_citation"]}]) == "guardrail"


def test_snapshot_classification_names_every_changed_surface():
    base = HarnessSnapshot(systemPrompt="base", toolNames=("a",))
    candidate = HarnessSnapshot(
        systemPrompt="base",
        toolNames=("a",),
        toolGuidance="use a first",
        skillManifest="top3",
        guardrails=("require_citation",),
    )
    change = classify_snapshot(base, candidate)
    assert change["fields"] == ["guardrails", "skillManifest", "toolGuidance"]
    assert change["operators"] == ["context_policy", "guardrail", "tool_guidance"]
    assert change["tokens"]


def test_novelty_is_zero_for_identity_and_one_for_disjoint_ops():
    a = tokens_for_ops("python/harness/a.py", [{"op": "create", "path": "a.py"}])
    assert jaccard_novelty(a, [a]) == 0.0
    b = tokens_for_ops("python/harness/b.py", [{"op": "create", "path": "b.py"}])
    assert jaccard_novelty(b, [a]) == 1.0


def test_identical_variants_are_vetoed_when_novelty_is_on():
    variants = [
        _create("python/harness/rsl_fixture_a.py"),
        _create("python/harness/rsl_fixture_a.py", "Y = 2\n"),
        _create("python/harness/rsl_fixture_b.py"),
    ]
    proposals = propose_many(
        _candidate(), 3, variants=variants, novelty_min=0.5,
    )
    assert [item.targetPath for item in proposals] == [
        "python/harness/rsl_fixture_a.py",
        "python/harness/rsl_fixture_b.py",
    ]


def test_novelty_off_keeps_every_variant():
    variants = [
        _create("python/harness/rsl_fixture_a.py"),
        _create("python/harness/rsl_fixture_a.py", "Y = 2\n"),
    ]
    proposals = propose_many(_candidate(), 2, variants=variants)
    assert len(proposals) == 2
    assert all(item.operator == "code_patch" for item in proposals)


def test_a_tabu_signature_is_excluded():
    variant = _create("python/harness/rsl_fixture_a.py")
    first = propose_many(_candidate(), 1, variants=[variant])[0]
    signature = op_signature(first.targetPath, first.ops)
    with pytest.raises(ProposalRefused) as refused:
        propose_many(
            _candidate(), 1, variants=[variant],
            exclude_signatures=[signature],
        )
    assert refused.value.code == "PROPOSAL_ALL_DUPLICATES"


def test_all_tabu_variants_refuse_rather_than_shrinking_silently():
    variants = [
        _create("python/harness/rsl_fixture_a.py"),
        _create("python/harness/rsl_fixture_b.py"),
    ]
    signatures = [
        op_signature(item.targetPath, item.ops)
        for item in propose_many(_candidate(), 2, variants=variants)
    ]
    with pytest.raises(ProposalRefused) as refused:
        propose_many(
            _candidate(), 2, variants=variants,
            exclude_signatures=signatures,
        )
    assert refused.value.code == "PROPOSAL_ALL_DUPLICATES"
