"""The labelled quant-intent benchmark is a regression guard, not a score to game."""

from __future__ import annotations

from harness.quant_intent_benchmark import CASES, VERSION, run_benchmark


def test_benchmark_runs_every_case_and_holds_the_contract() -> None:
    report = run_benchmark()
    assert report.version == VERSION
    assert report.total == len(CASES)
    assert report.accuracy >= 0.95, report.to_dict()
    assert report.false_positive_lookups == 0, report.to_dict()
    assert report.trade_violations == 0, report.to_dict()
    assert report.failures == [], report.to_dict()


def test_benchmark_catches_a_regression() -> None:
    """A classifier that always says `none` must fail the positive cases."""

    from harness.quant_intent import QuantIntent

    def broken(query: str, *args, **kwargs) -> QuantIntent:
        return QuantIntent(tier="none", kind="lookup", confidence="certain")

    report = run_benchmark(classifier=broken)
    assert report.accuracy < 0.95
    assert report.failures
