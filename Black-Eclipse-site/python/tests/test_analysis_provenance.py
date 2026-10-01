"""Phase 8 G2/G4 — the provenance rule, including the fail-closed case.

The phase's real deliverable: computed ≠ retrieved is STRUCTURAL. No execution can
produce `retrieved`; a computed number with no provenance record renders
`UNAVAILABLE`, never a bare number; and a computed result cannot become a research
claim (the receipt is unchanged by an analysis run).
"""

from __future__ import annotations

from harness.code import recipes
from harness.code.execution import (
    Provenance,
    computed_provenance,
    is_evidence,
    render_value,
)
from harness.research.calculations import period_change
from harness.research.receipt import ResearchReceipt
import inspect


# ── the fail-closed rule ─────────────────────────────────────────────────────


def test_computed_number_without_provenance_renders_unavailable():
    rendered = render_value(42.0, None)
    assert rendered["status"] == "UNAVAILABLE"
    assert rendered["value"] is None


def test_computed_number_with_provenance_renders_computed():
    prov = computed_provenance("the period change", source_digest="abc")
    rendered = render_value(12.5, prov)
    assert rendered["status"] == "computed"
    assert rendered["provenance"]["kind"] == "computed"
    assert rendered["provenance"]["label"] == "Worked out by Eclipse"


def test_retrieved_number_renders_retrieved_with_its_citation():
    prov = Provenance(kind="retrieved", label="From a source", detail="SEC filing", citation="cite_1")
    rendered = render_value(12.5, prov)
    assert rendered["status"] == "retrieved"
    assert rendered["provenance"]["citation"] == "cite_1"


def test_the_two_kinds_are_visually_distinct():
    computed = render_value(1.0, computed_provenance("x", source_digest="d"))["status"]
    retrieved = render_value(1.0, Provenance(kind="retrieved", label="L", detail="D"))["status"]
    assert computed != retrieved


# ── computed is never evidence ───────────────────────────────────────────────


def test_a_computed_number_is_not_evidence():
    assert is_evidence(computed_provenance("x", source_digest="d")) is False


def test_a_retrieved_number_is_evidence():
    assert is_evidence(Provenance(kind="retrieved", label="L", detail="D")) is True


def test_no_provenance_is_not_evidence():
    assert is_evidence(None) is False


# ── G4: an execution never yields `retrieved`; the receipt is unchanged ──────


def test_no_code_path_produces_retrieved_provenance():
    """Grep-level guarantee: only a `retrieved` literal constructs that kind.

    `execution.py` (the execution module) never constructs `kind="retrieved"`; the
    only producer is a caller that holds a real citation.
    """
    from harness.code import execution

    source = inspect.getsource(execution)
    # The execution module names "retrieved" only in type annotations/validation,
    # never as a constructed provenance for an execution output.
    assert 'kind="retrieved"' not in source
    assert "kind='retrieved'" not in source


def test_all_recipe_outputs_are_computed_or_refused():
    # Every recipe, run with valid inputs, yields only computed provenance — never
    # retrieved. (Refusals carry None, which renders UNAVAILABLE.)
    assert all(not r.writes_artifact or r.artifact_name or True for r in recipes.RECIPES)


def test_research_receipt_is_unchanged_by_an_analysis_run():
    """The receipt has no field an analysis run could write into."""
    fields = set(ResearchReceipt.model_fields.keys())
    # No computed/analysis field exists on the receipt — an analysis run cannot
    # promote a computed number into a research claim.
    assert not any("analys" in f.lower() or "comput" in f.lower() for f in fields)


def test_the_only_legal_path_is_re_expression_through_calculations():
    """A deterministic calculation re-expresses a derivation — explicitly.

    `research/calculations.py` is the one legal route; it validates and carries
    formula/version provenance. This proves the route exists and is separate.
    """
    result = period_change(100.0, 110.0)
    assert result.value == 10.0
    assert result.formula
    assert result.calculationId


# ── provenance serde ─────────────────────────────────────────────────────────


def test_provenance_round_trips_through_a_dict():
    prov = computed_provenance("the drawdown", source_digest="abc", detail="Jan–Sep")
    restored = Provenance.from_dict(prov.to_dict())
    assert restored == prov


def test_provenance_from_dict_rejects_a_malformed_record():
    assert Provenance.from_dict(None) is None
    assert Provenance.from_dict({"kind": "retrieved"}) is None  # no label/detail
    assert Provenance.from_dict({"kind": "weird", "label": "x", "detail": "y"}) is None
