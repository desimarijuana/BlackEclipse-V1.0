"""The response-mode routing benchmark — measurable presentation quality.

The blueprint's Phase 6 requires evaluating whether the orchestrator chose the
RIGHT presentation, not merely whether a response rendered. This module is that
measurement for the deterministic classifier: a versioned, labelled set of real
user prompts (each with its expected mode) and a pure scorer that reports overall
accuracy plus per-mode precision/recall and the confusion pairs.

It runs the SAME `classify_response_mode` the runtime uses, so it measures the
shipped routing — it cannot drift from production. It is deterministic and needs
no model, so it is safe to run on every change (see
`python/tests/test_response_mode_benchmark.py`) and as a CLI:

    python -m harness.response_mode_benchmark

The model-assisted fallback (`response_mode_llm.py`) is non-deterministic and is
deliberately NOT benchmarked here; only the default deterministic path is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .response_mode import ResponseMode, ResponsePlan, classify_response_mode

# Bump when the case set changes so a stored score stays attached to the exact
# benchmark that produced it.
BENCHMARK_VERSION = "1"

Classifier = Callable[[str, Optional[list[Any]]], ResponsePlan]


@dataclass(frozen=True)
class RoutingCase:
    """One labelled prompt. `history` is the prior turns for a follow-up case."""

    query: str
    expected: ResponseMode
    history: tuple[dict[str, str], ...] = ()
    note: str = ""


# The benchmark. Cases are real-shaped user turns; the expected mode follows the
# classifier's documented signal design (see `response_mode.py`). Anti-cases —
# simple/ambiguous turns that MUST stay prose — are included deliberately, because
# a forced widget is the failure mode that matters most.
DEFAULT_CASES: tuple[RoutingCase, ...] = (
    # ── text: chat, lookups, ambiguity ──────────────────────────────────────
    RoutingCase("Hi Eclipse", "text"),
    RoutingCase("hello", "text"),
    RoutingCase("thanks!", "text"),
    RoutingCase("ok cool", "text"),
    RoutingCase("", "text"),
    RoutingCase("what is the price of AAPL", "text"),
    RoutingCase("what's the market cap of MSFT", "text"),
    RoutingCase("tell me something interesting about the market", "text"),
    RoutingCase("is now a good time to buy", "text"),
    RoutingCase("who is the CEO of NVDA", "text"),
    # ── explanation ─────────────────────────────────────────────────────────
    RoutingCase("Explain RSI", "explanation"),
    RoutingCase("How does RSI work", "explanation"),
    RoutingCase("Teach me Python", "explanation"),
    RoutingCase("Walk me through the difference between a market order and a limit order", "explanation"),
    RoutingCase("Explain why bond prices move inversely to yields", "explanation"),
    RoutingCase("Help me understand duration", "explanation"),
    RoutingCase("Build me a learning roadmap for options trading", "explanation"),
    # ── visualization ───────────────────────────────────────────────────────
    RoutingCase("Compare BTC and ETH", "visualization"),
    RoutingCase("Chart the 90-day returns of NVDA", "visualization"),
    RoutingCase("Show me the correlation between SPY and TLT", "visualization"),
    RoutingCase("What is the drawdown of my portfolio", "visualization"),
    RoutingCase("Rank the top S&P sectors by performance", "visualization"),
    RoutingCase("Plot the equity curve over time", "visualization"),
    RoutingCase("Show the distribution of daily returns", "visualization"),
    # ── simulation ──────────────────────────────────────────────────────────
    RoutingCase("Backtest my EMA crossover strategy", "simulation"),
    RoutingCase("What if I change the stop loss to 2%", "simulation"),
    RoutingCase("Run a Monte Carlo simulation of my portfolio", "simulation"),
    RoutingCase("Optimize the strategy parameters", "simulation"),
    RoutingCase("Stress test my portfolio against a rate shock", "simulation"),
    RoutingCase("Show me the sensitivity to the position size", "simulation"),
    # ── workflow ────────────────────────────────────────────────────────────
    RoutingCase("Why did my agent fail?", "workflow"),
    RoutingCase("Show the workflow for this research plan", "workflow"),
    RoutingCase("Show me the agent delegation for this run", "workflow"),
    RoutingCase("What is the execution trace of the last run", "workflow"),
    # ── composite: two rich modes genuinely co-occur ────────────────────────
    RoutingCase("Compare BTC and ETH and explain the difference", "composite"),
    RoutingCase("Backtest the strategy and chart the equity curve", "composite"),
    RoutingCase(
        "Explain my strategy and show how it changes if I change the stop loss",
        "composite",
    ),
    RoutingCase("Explain the dependencies between these tasks", "composite"),
    # ── follow-ups inherit the prior turn's mode ────────────────────────────
    RoutingCase(
        "do it",
        "visualization",
        history=({"role": "user", "content": "compare BTC and ETH"},),
    ),
    RoutingCase(
        "go ahead",
        "explanation",
        history=({"role": "user", "content": "explain RSI"},),
    ),
    RoutingCase(
        "proceed",
        "simulation",
        history=({"role": "user", "content": "backtest my strategy"},),
    ),
    RoutingCase(
        "do it",
        "text",
        history=({"role": "user", "content": "what is the price of AAPL"},),
    ),
)


@dataclass
class RoutingReport:
    """The scoring outcome: accuracy, per-mode recall/precision, confusion."""

    total: int
    correct: int
    # expected mode -> {predicted mode: count}
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    mismatches: list[tuple[str, str, str]] = field(default_factory=list)
    version: str = BENCHMARK_VERSION

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def recall(self, mode: str) -> float:
        row = self.confusion.get(mode) or {}
        actual = sum(row.values())
        return (row.get(mode, 0) / actual) if actual else 1.0

    def precision(self, mode: str) -> float:
        predicted = sum(
            row.get(mode, 0) for row in self.confusion.values()
        )
        correct = (self.confusion.get(mode) or {}).get(mode, 0)
        return (correct / predicted) if predicted else 1.0

    def modes(self) -> list[str]:
        return sorted(self.confusion)


def evaluate_routing(
    cases: Optional[tuple[RoutingCase, ...]] = None,
    classifier: Optional[Classifier] = None,
) -> RoutingReport:
    """Score the classifier over `cases` (default: `DEFAULT_CASES`). Pure."""
    cases = DEFAULT_CASES if cases is None else cases
    classify = classifier or (lambda q, h: classify_response_mode(q, h))
    report = RoutingReport(total=len(cases), correct=0)
    for case in cases:
        history = list(case.history) or None
        predicted = classify(case.query, history).mode
        row = report.confusion.setdefault(case.expected, {})
        row[predicted] = row.get(predicted, 0) + 1
        if predicted == case.expected:
            report.correct += 1
        else:
            report.mismatches.append((case.query, case.expected, predicted))
    return report


def format_report(report: RoutingReport) -> str:
    """A plain, human-readable report (used by the CLI and test failure output)."""
    lines = [
        f"response-mode routing benchmark v{report.version}",
        f"accuracy: {report.accuracy:.1%} ({report.correct}/{report.total})",
        "",
        f"{'mode':<15}{'recall':>8}{'precision':>11}",
    ]
    for mode in report.modes():
        lines.append(f"{mode:<15}{report.recall(mode):>8.0%}{report.precision(mode):>11.0%}")
    if report.mismatches:
        lines.append("")
        lines.append("mismatches:")
        for query, expected, predicted in report.mismatches:
            shown = query or "<empty>"
            lines.append(f"  expected {expected:<14} got {predicted:<14} :: {shown}")
    return "\n".join(lines)


def main() -> int:
    report = evaluate_routing()
    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())


__all__ = [
    "BENCHMARK_VERSION",
    "DEFAULT_CASES",
    "RoutingCase",
    "RoutingReport",
    "evaluate_routing",
    "format_report",
]
