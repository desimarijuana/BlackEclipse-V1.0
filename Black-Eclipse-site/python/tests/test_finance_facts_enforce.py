"""Universal financial-fact enforcement — the final-answer gate (§22/§23/§28).

The answer must not present a value from an EXCLUDED fact, or one side of a
cross-source conflict, as a clean figure. The enforcement appends a disclosure; it
never silently strips a number. All synthetic; no ticker-specific logic.
"""

from __future__ import annotations

from harness.finance_facts.enforce import disclosure_note, enforce_finance_answer


def _analysis(excluded=None, notes=None, conflicts=None, presentable=True):
    return {
        "presentable": presentable,
        "excluded": excluded or [],
        "notes": notes or [],
        "conflicts": conflicts or [],
    }


def test_a_clean_answer_owes_nothing():
    verdict = enforce_finance_answer("Apple's price is 240 USD.", _analysis())
    assert verdict.required_disclosures == []


def test_asserting_an_excluded_metric_owes_a_disclosure():
    # `revenue` was excluded (ambiguous definition) but the answer asserts it.
    verdict = enforce_finance_answer(
        "The company's revenue was 2.7 trillion TRY in FY2025.",
        _analysis(excluded=["revenue"], presentable=False),
    )
    assert verdict.presented_excluded == ["revenue"]
    assert verdict.required_disclosures
    assert any("revenue" in d for d in verdict.required_disclosures)


def test_an_already_disclosed_answer_owes_nothing_new():
    verdict = enforce_finance_answer(
        "The company's revenue was 2.7 trillion TRY, but the accounting definition is ambiguous.",
        _analysis(excluded=["revenue"], presentable=False, notes=["definition ambiguous"]),
    )
    assert verdict.presented_excluded == ["revenue"]
    # The answer already says it is ambiguous → no NEW required disclosure.
    assert verdict.required_disclosures == []


def test_asserting_one_side_of_a_conflict_owes_a_disclosure():
    conflicts = [{"metric": "price", "sourceA": "JDDS", "sourceB": "yfinance"}]
    verdict = enforce_finance_answer(
        "The price is 130 USD.",
        _analysis(conflicts=conflicts),
    )
    assert any("disagree" in d and "price" in d for d in verdict.required_disclosures)


def test_an_answer_that_discloses_the_conflict_owes_nothing():
    conflicts = [{"metric": "price", "sourceA": "JDDS", "sourceB": "yfinance"}]
    verdict = enforce_finance_answer(
        "Two sources disagree: the price is 130 USD on one and 100 USD on another.",
        _analysis(conflicts=conflicts),
    )
    assert verdict.required_disclosures == []


def test_no_finance_analysis_is_a_noop():
    assert enforce_finance_answer("anything", None).required_disclosures == []


def test_a_metric_named_without_a_value_is_not_treated_as_asserted():
    # The answer names `revenue` conceptually but does not assert a figure.
    verdict = enforce_finance_answer(
        "Revenue is an important metric for this sector.",
        _analysis(excluded=["revenue"], presentable=False),
    )
    assert verdict.presented_excluded == []


def test_disclosure_note_is_a_plain_sentence():
    note = disclosure_note(["sources disagree on price", "revenue: unresolved"])
    assert note.startswith("Data caveat:")
    assert note.endswith(".")
    assert disclosure_note([]) == ""
