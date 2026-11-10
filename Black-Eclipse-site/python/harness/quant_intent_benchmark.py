"""Labelled benchmark for the deterministic quant-intent classifier.

The benchmark is intentionally separate from the evaluation gate: it measures
the classifier itself (tier + kind), so a prompt or routing change cannot hide a
regression behind an unrelated run score. Like `response_mode_benchmark.py`, the
cases are versioned here and the runtime classifier is the thing under test.

Run: `python -m harness.quant_intent_benchmark`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .quant_intent import QuantIntent, classify_quant_intent

VERSION = "quant-intent-v1"


@dataclass(frozen=True)
class QuantCase:
    query: str
    tier: str
    kind: Optional[str] = None
    mode: Optional[str] = None
    note: str = ""


# A mix of positive asks, anti-cases, explicit framing and execution turns. The
# anti-cases are the important half: a forced model on a lookup is a worse
# failure than a missed quant turn.
CASES: tuple[QuantCase, ...] = (
    QuantCase("what is the price of gold", "none", note="lookup"),
    QuantCase("gold quote", "none", note="lookup"),
    QuantCase("latest gold news", "none", note="news"),
    QuantCase("summarize this 10-K", "none", note="document lookup"),
    QuantCase("explain the Sharpe ratio", "none", note="concept"),
    QuantCase("how does a backtest work", "none", note="concept"),
    QuantCase("what is a moving average", "none", note="concept"),
    QuantCase("show me AAPL earnings", "none", note="lookup"),
    QuantCase("compare AAPL and MSFT", "none", note="ordinary comparison"),
    QuantCase("what is quantitative easing", "none", note="concept"),
    QuantCase("gold", "none", note="bare symbol"),
    QuantCase("AAPL", "none", note="bare symbol"),
    QuantCase("analyze gold", "none", note="vague, no method"),
    QuantCase("how is gold doing", "none", note="conversational"),
    QuantCase("should I buy gold", "none", note="advice, not execution"),
    QuantCase("build a dashboard", "none", note="UI, not quant"),
    QuantCase("write alpha.py that prints ALPHA_OK", "none", note="code task"),
    QuantCase(
        "Build a small package: write alpha.py and beta.py, run both, then write report.txt",
        "none", note="code task with alpha/beta filenames",
    ),
    QuantCase("create model.py with a helper function", "none", note="code task"),
    QuantCase("forecast gold for tomorrow", "standard", "forecast"),
    QuantCase("will gold rise tomorrow", "standard", "forecast"),
    QuantCase("what will gold do next week", "standard", "forecast"),
    QuantCase("gold price prediction", "standard", "forecast"),
    QuantCase("where will EURUSD be next month", "standard", "forecast"),
    QuantCase("make a forecast", "standard", "forecast", note="missing inputs"),
    QuantCase("predict", "standard", "forecast", note="missing inputs"),
    QuantCase("run a monte carlo on my portfolio", "standard", "analysis"),
    QuantCase("stress test my portfolio", "standard", "risk"),
    QuantCase("compute the correlation between gold and the dollar", "light"),
    QuantCase("calculate the 20-day volatility of gold", "light", "risk"),
    QuantCase("compute the drawdown of my portfolio", "light", "risk"),
    QuantCase("calculate the beta of AAPL", "light"),
    QuantCase("build me a quant model", "deep", "model"),
    QuantCase("train a model to predict gold", "deep", "model"),
    QuantCase("create a factor model", "deep", "factor"),
    QuantCase("design a momentum strategy for gold", "deep", "strategy"),
    QuantCase("backtest my strategy", "deep", "strategy"),
    QuantCase("run a walk-forward test on my strategy", "deep", "strategy"),
    QuantCase("optimize my strategy parameters", "deep", "strategy"),
    QuantCase("build a DCF for Newmont", "deep", "financial_model"),
    QuantCase("make me a three-statement model for AAPL", "deep", "financial_model"),
    QuantCase("create a factor for value", "deep", "factor"),
    QuantCase("build a reusable model for volatility", "deep", "model"),
    QuantCase("write a backtest in Python", "deep", "strategy"),
    QuantCase("create a machine learning model for fraud", "deep", "model"),
    QuantCase("test my strategy", "standard", "strategy"),
    QuantCase("walk-forward my strategy", "deep", "strategy"),
    QuantCase("run robustness on my strategy", "deep", "strategy"),
    QuantCase("optimize my portfolio", "standard", "analysis"),
    QuantCase("reuse the model from last week", "standard", "model"),
    QuantCase("show me the model catalog", "standard", "model"),
    QuantCase("what models do we have", "standard", "model"),
    QuantCase("list my strategies", "standard", "model"),
    QuantCase("act as a quant trader", "standard", note="explicit framing"),
    QuantCase("be quantitative about this", "standard", note="explicit framing"),
    QuantCase("use quantitative methods", "standard", note="explicit framing"),
    QuantCase("buy 0.01 lot XAUUSD", "none", "trade", note="execution"),
    QuantCase("close my XAUUSD position", "none", "trade", note="execution"),
    QuantCase("forecast gold for tomorrow", "none", mode="off", note="override off"),
    QuantCase("look at gold", "standard", mode="on", note="override on"),
    # Discovery: methods, ideation, mining and current setups.
    QuantCase("what methods can I use to trade gold", "standard", "discovery"),
    QuantCase("which strategies work on EURUSD", "standard", "discovery"),
    QuantCase("show me the strategy library", "standard", "discovery"),
    QuantCase("find and invent new quantitative trading methods", "deep", "discovery"),
    QuantCase("mine methods for gold", "deep", "discovery"),
    QuantCase("scan the market for setups on EURUSD", "deep", "discovery"),
    QuantCase("what should I trade today", "standard", "discovery"),
)


@dataclass
class QuantBenchmarkReport:
    version: str = VERSION
    total: int = 0
    passed: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    false_positive_lookups: int = 0
    trade_violations: int = 0

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "total": self.total,
            "passed": self.passed,
            "accuracy": round(self.accuracy, 4),
            "falsePositiveLookups": self.false_positive_lookups,
            "tradeViolations": self.trade_violations,
            "failures": list(self.failures),
        }


def run_benchmark(
    classifier: Callable[..., QuantIntent] = classify_quant_intent,
    cases: tuple[QuantCase, ...] = CASES,
) -> QuantBenchmarkReport:
    report = QuantBenchmarkReport(total=len(cases))
    for case in cases:
        intent = classifier(case.query, mode=case.mode)
        ok = intent.tier == case.tier and (
            case.kind is None or intent.kind == case.kind
        )
        if ok:
            report.passed += 1
            continue
        report.failures.append({
            "query": case.query,
            "expected": f"{case.tier}/{case.kind or '*'}",
            "actual": f"{intent.tier}/{intent.kind}",
            "note": case.note,
        })
        if case.tier == "none" and intent.tier != "none":
            report.false_positive_lookups += 1
        if case.kind == "trade" and intent.kind != "trade":
            report.trade_violations += 1
    return report


def main() -> int:
    report = run_benchmark()
    print(f"Quant intent benchmark {report.version}")
    print(f"  accuracy: {report.passed}/{report.total} = {report.accuracy:.1%}")
    print(f"  false-positive non-quant turns: {report.false_positive_lookups}")
    print(f"  trade-precedence violations: {report.trade_violations}")
    for failure in report.failures:
        print(
            f"  [MISS] {failure['query']!r}: expected {failure['expected']}, "
            f"got {failure['actual']} ({failure['note']})"
        )
    return 0 if report.accuracy == 1.0 and not report.failures else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
