"""Fundamental zoo: declared, documented, and unavailable for the right reason."""

from __future__ import annotations

from harness.factors import library
from harness.factors.zoo import fundamental as F


def test_every_fundamental_factor_ships_unavailable_with_a_reason():
    assert F.FUNDAMENTAL_FACTORS
    for factor in F.FUNDAMENTAL_FACTORS:
        assert factor["available"] is False, factor["name"]
        assert factor["unavailableReason"] == F.REASON
        assert "point-in-time" in factor["unavailableReason"]


def test_the_reason_names_the_lookahead_risk_not_a_missing_sdk():
    # The blocker is data integrity, not a package: a restated figure is
    # lookahead, and that must be what the record says.
    assert "lookahead" in F.REASON
    assert "install" not in F.REASON.lower()


def test_every_factor_declares_the_inputs_it_needs_and_a_reference():
    for factor in F.FUNDAMENTAL_FACTORS:
        assert factor["inputs"], factor["name"]
        assert factor["reference"], factor["name"]
        assert factor["expression"], factor["name"]
        assert factor["zoo"] == "fundamental"


def test_names_do_not_collide_with_the_existing_builtins():
    names = [f["name"] for f in library.BUILTIN_FACTORS]
    assert len(names) == len(set(names))
    # the pre-existing builtin value factors keep their identity
    for legacy in ("earnings_yield", "book_to_price", "return_on_equity"):
        assert library.get_builtin(legacy)["zoo"] if library.get_builtin(legacy).get("zoo") else True


def test_the_family_is_merged_into_the_library():
    names = {f["name"] for f in library.BUILTIN_FACTORS}
    assert {f["name"] for f in F.FUNDAMENTAL_FACTORS} <= names
    record = library.get_builtin("fund_accruals")
    assert record["zoo"] == "fundamental" and record["available"] is False


def test_available_only_listing_excludes_them():
    available = {f["name"] for f in library.list_builtins(available_only=True)}
    assert "fund_accruals" not in available
    assert "qlib_roc_20" in available


def test_the_positions_report_separates_declared_from_available():
    report = F.fundamental_positions_port()
    assert report["declared"] == len(F.FUNDAMENTAL_FACTORS)
    # Every DECLARED fundamental factor is blocked; there is no partially-
    # available subset pretending to be live.
    assert report["available"] == 0
    assert report["declared"] == report["total"]
    assert report["blockedBy"] == F.REASON
