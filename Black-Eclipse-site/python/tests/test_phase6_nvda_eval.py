"""Phase 6 — NVDA labeled regression test.

Loads the labeled dataset built from NVIDIA's actual SEC XBRL figures and runs
the deterministic coverage evaluator. Asserts the pipeline handles issuer-
reported FY2024/FY2025 periods correctly and never lets the stale vault FY2019
row satisfy a FY2024 leg. No network access; values come from the fixture.
"""

from __future__ import annotations

from harness.research.eval.nvda import (
    load_nvda_dataset,
    run_nvda_evaluation,
)


def test_nvda_dataset_is_source_labeled():
    dataset = load_nvda_dataset()
    assert dataset["ticker"] == "NVDA"
    assert dataset["filing"]["form"] == "10-K"
    # Issuer-reported values, with the filing that carries them.
    assert {p["label"] for p in dataset["periods"]} == {"FY2024", "FY2025"}
    note = dataset["sourceNote"]
    assert "CIK 0001045810" in note
    assert "never memory-derived" in note


def test_nvda_regression_no_false_accepts_and_covers_the_real_periods():
    metrics = run_nvda_evaluation()
    data = metrics.to_dict()
    assert data["total"] >= 5
    assert data["falseAccepts"] == 0
    assert data["falseRejects"] == 0
    assert data["coverageAccuracy"] == 1.0
    assert data["tierCompliant"] >= 2  # primary-tier rows counted


def test_nvda_stale_fy2019_case_is_classified_not_covered():
    dataset = load_nvda_dataset()
    stale = next(c for c in dataset["cases"] if c["caseId"] == "stale-fy2019-does-not-cover-fy2024")
    assert stale["expectCovered"] is False
    # The FY2019 period end (2019-01-27) does not fall inside FY2024.
    assert stale["candidate"]["periodEnd"] == "2019-01-27"
