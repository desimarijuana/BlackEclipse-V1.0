"""Phase 4 hardening — deterministic evidence matching + stable identifiers.

Regression coverage for the Workstream 1 corrections:
  * missing required unit/currency/basis/instrument/identity → NOT covered
  * canonical period matching (no annual↔quarter, no malformed/adjacent year)
  * stable, content-sensitive evidence/calculation ids across processes
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from harness.research.calculations import period_change, sharpe
from harness.research.coverage import build_coverage, evaluate_leg
from harness.research.ids import calculation_digest, evidence_digest, stable_digest
from harness.research.mandate import FactLeg, parse_mandate
from harness.research.periods import parse_period, periods_match
from harness.retrieval.contract import (
    EvidenceItem,
    InstrumentIdentity,
    NormalizedFinancialObject,
    SourceReference,
)

REPO_PYTHON = Path(__file__).resolve().parents[1]


def obj(
    name="revenue",
    value=1000.0,
    *,
    period="FY2024",
    basis=None,
    unit=None,
    currency=None,
    instrument="TEST",
    identity=None,
    data_timestamp="2024-12-31",
    published_at=None,
    source_type="structured",
):
    return NormalizedFinancialObject(
        name=name,
        value=value,
        period=period,
        basis=basis,
        unit=unit,
        currency=currency,
        instrument=instrument,
        identity=identity,
        dataTimestamp=data_timestamp,
        publishedAt=published_at,
        source=SourceReference(source="JDDS", sourceType=source_type, validationStatus="valid"),
    )


def ev(eid, objects, *, kind="structured"):
    return EvidenceItem(
        id=eid,
        kind=kind,
        summary=eid,
        objects=objects,
        source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
    )


def leg(**kwargs):
    base = dict(id="leg1", metric="revenue", entityRaw="TEST", entitySymbol="TEST")
    base.update(kwargs)
    return FactLeg(**base)


# ── required metadata must be present ───────────────────────────────────────


def test_missing_required_unit_is_qualified_not_covered():
    # A required unit the evidence omits leaves the value valid but unconfirmed:
    # `qualified`, never `covered`.
    coverage = evaluate_leg(leg(unit="%"), [ev("e1", [obj(unit=None)])])
    assert coverage.status == "qualified"
    assert "unit" in (coverage.reason or "")


def test_present_mismatched_unit_is_not_covered():
    coverage = evaluate_leg(leg(unit="%"), [ev("e1", [obj(unit="USD")])])
    assert coverage.status in ("unknown", "unavailable")
    assert coverage.status != "covered"


def test_missing_required_currency_is_unknown():
    # Currency is blocking: an unconfirmed currency cannot be presented at all.
    coverage = evaluate_leg(leg(currency="EUR"), [ev("e1", [obj(currency=None)])])
    assert coverage.status == "unknown"


def test_missing_required_basis_is_qualified_not_covered():
    coverage = evaluate_leg(leg(basis="standalone"), [ev("e1", [obj(basis=None)])])
    assert coverage.status == "qualified"


def test_missing_required_instrument_is_unknown_not_wildcard():
    coverage = evaluate_leg(
        leg(entitySymbol="TEST"), [ev("e1", [obj(instrument=None)])]
    )
    assert coverage.status == "unknown"
    assert "identity" in (coverage.reason or "")


def test_canonical_identity_market_mismatch_not_covered():
    identity = InstrumentIdentity(market="PK", symbol="TEST", currency="PKR")
    lc = leg(entitySymbol="TEST", market="US")
    coverage = evaluate_leg(lc, [ev("e1", [obj(identity=identity, instrument=None)])])
    assert coverage.status != "covered"


def test_canonical_identity_match_is_covered():
    identity = InstrumentIdentity(market="US", symbol="TEST", currency="USD")
    lc = leg(entitySymbol="TEST", market="US")
    coverage = evaluate_leg(lc, [ev("e1", [obj(identity=identity, instrument=None)])])
    assert coverage.status == "covered"


# ── canonical period parsing ────────────────────────────────────────────────


def test_parse_period_shapes():
    assert parse_period("FY2024").key == "FY2024"
    assert parse_period("2024").key == "FY2024"
    assert parse_period("FY2024-Q1").key == "FY2024-Q1"
    assert parse_period("Q1 2024").key == "FY2024-Q1"
    assert parse_period("1Q2024").key == "FY2024-Q1"
    assert parse_period("2024-03-31").granularity == "date"
    assert parse_period("2024-01-01..2024-03-31").granularity == "range"
    assert parse_period("garbage") is None
    assert parse_period("20244") is None  # adjacent digit run is not a year
    assert parse_period(None) is None


def test_annual_does_not_match_quarter():
    assert periods_match("FY2024", "FY2024-Q4") is False
    assert periods_match("FY2024", "FY2024-Q1") is False


def test_quarter_matches_quarter_alias():
    assert periods_match("FY2024-Q1", "Q1 2024") is True
    assert periods_match("FY2024-Q1", "FY2024-Q1") is True


def test_annual_does_not_match_adjacent_year():
    assert periods_match("FY2024", "FY2025") is False
    assert periods_match("FY2024", "FY2023") is False


def test_unknown_required_period_never_matches():
    assert periods_match("garbage", "FY2024") is False
    assert periods_match("FY2024", "garbage") is False


def test_timestamp_can_satisfy_annual_when_not_explicit_label():
    # A date timestamp is an admissible realisation of the annual period it is in.
    assert periods_match("FY2024", "2024-12-31", candidate_is_timestamp=True) is True
    assert periods_match("FY2024", "2023-12-31", candidate_is_timestamp=True) is False
    # ...but an explicit fiscal label never cross-matches.
    assert periods_match("FY2024", "FY2024-Q4", candidate_is_timestamp=False) is False


def test_coverage_annual_leg_not_satisfied_by_quarter_row():
    mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
    items = [
        ev("q23", [obj(value=100.0, period="FY2023-Q1")]),
        ev("q24", [obj(value=200.0, period="FY2024-Q1")]),
    ]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)


# ── stable identifiers ──────────────────────────────────────────────────────


def test_stable_digest_is_reproducible_and_content_sensitive():
    assert stable_digest({"a": 1}) == stable_digest({"a": 1})
    assert stable_digest({"a": 1}) != stable_digest({"a": 2})
    # Key order must not change the digest.
    assert stable_digest({"a": 1, "b": 2}) == stable_digest({"b": 2, "a": 1})


def test_evidence_digest_includes_content_not_just_id():
    e1 = ev("same_id", [obj(value=100.0)])
    e2 = ev("same_id", [obj(value=200.0)])
    assert evidence_digest(e1) != evidence_digest(e2)
    assert evidence_digest(e1) == evidence_digest(ev("same_id", [obj(value=100.0)]))


def test_calculation_digest_distinguishes_values_same_dates():
    same_dates = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-12-31", "value": 120.0},
    ]
    changed_value_same_dates = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-12-31", "value": 130.0},
    ]
    r1 = period_change(100.0, 120.0, observations=same_dates)
    r2 = period_change(100.0, 130.0, observations=changed_value_same_dates)
    assert r1.calculationId != r2.calculationId
    assert calculation_digest(r1) == r1.calculationId


def test_calculation_id_reproducible_within_process():
    a = sharpe(
        [{"date": f"2024-01-{i + 1:02d}", "value": v} for i, v in enumerate([100, 101.5, 100.8, 103.0, 104.2])],
        risk_free_rate=0.02,
    )
    b = sharpe(
        [{"date": f"2024-01-{i + 1:02d}", "value": v} for i, v in enumerate([100, 101.5, 100.8, 103.0, 104.2])],
        risk_free_rate=0.02,
    )
    assert a.calculationId == b.calculationId


def test_identifiers_stable_across_processes():
    """The whole point: no salted `hash()` — same input, same id in a new process."""
    script = (
        "import sys; sys.path.insert(0, r'%s');"
        "from harness.research.calculations import period_change;"
        "from harness.research.ids import stable_digest;"
        "r = period_change(100.0, 120.0, observations=[{'date':'2024-01-01','value':100.0},{'date':'2024-12-31','value':120.0}]);"
        "print(r.calculationId);"
        "print(stable_digest({'x': [1, 2, 3]}))" % str(REPO_PYTHON)
    )
    runs = []
    for _ in range(2):
        out = subprocess.check_output([sys.executable, "-c", script], text=True).strip().splitlines()
        runs.append(tuple(out))
    assert runs[0] == runs[1], "identifiers must not depend on per-process hash salt"
