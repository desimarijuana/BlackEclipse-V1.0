"""Final-answer enforcement for finance facts (Universal Financial Data Accuracy, §22/§23/§28).

A parallel of `code/verify.enforce_run_answer`: before the run is marked complete,
the answer is checked against the validated finance facts the run actually
retrieved. The rule is NOT "strip the number" — suppression hides a real, sourced
value. The rule is **honesty**: when the run's own data-quality analysis excluded a
metric (an ambiguous definition, no period, a superseded value), or found a
cross-source conflict, the answer must say so; otherwise an unqualified answer
would present an ambiguous figure as clean.

It is deterministic and makes no model call. A run that retrieved no finance facts
and asserted nothing yields no blob — never a fabricated caveat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Phrases that already disclose an ambiguity/conflict, so we do not add a second.
_HONESTY_MARKERS = (
    "ambiguous", "not stated", "unclear", "sources disagree", "disagree",
    "definition", "withheld", "could not verify", "unverified", "not verified",
    "stale", "not comparable", "saved snapshot", "unavailable",
)


@dataclass
class FinanceEnforcement:
    """The outcome of checking an answer against the run's finance analysis."""

    required_disclosures: list[str] = field(default_factory=list)
    presented_excluded: list[str] = field(default_factory=list)
    missing_disclosures: list[str] = field(default_factory=list)


def _answer_discloses(answer: str, marker_scope: str) -> bool:
    """Whether the answer already carries an honesty marker near this metric.

    A generic marker ("ambiguous", "sources disagree") anywhere is accepted only
    when it is in the same sentence as the metric — a disclosure about a different
    metric must not excuse this one.
    """
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        lowered = sentence.lower()
        if not any(marker in lowered for marker in _HONESTY_MARKERS):
            continue
        if _metric_named(lowered, marker_scope):
            return True
    return False


def _metric_named(answer_lowered: str, metric: str) -> bool:
    """Whether a metric label appears in the text (proximity not required)."""
    human = metric.replace("-", " ").replace("_", " ").strip().lower()
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", human).lower()
    return any(probe and probe in answer_lowered for probe in {human, spaced})


def _mentions_metric(answer_lowered: str, metric: str) -> bool:
    """Whether the answer asserts a number for this metric.

    Matches the metric label (humanised) near a digit, so an answer that merely
    names the concept without a value is not treated as asserting it.
    """
    human = metric.replace("-", " ").strip().lower()
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", human).lower()
    for probe in {human, spaced, human.replace("_", " ")}:
        if not probe:
            continue
        if re.search(rf"{re.escape(probe)}[^\n]{{0,40}}?\d", answer_lowered):
            return True
    return False


def enforce_finance_answer(answer: str, analysis: Optional[dict[str, Any]]) -> FinanceEnforcement:
    """Check an answer against the run's accumulated finance analysis.

    Returns the disclosures the answer OWES and the ones it is missing. This does
    not rewrite the answer; the caller decides how to surface a missing disclosure
    (append a note, or flag the run). Pure and testable.
    """
    result = FinanceEnforcement()
    if not analysis:
        return result

    excluded = [str(x) for x in (analysis.get("excluded") or [])]
    notes = [str(x) for x in (analysis.get("notes") or [])]
    conflicts = analysis.get("conflicts") or []

    lowered = answer.lower()

    # 1. An excluded metric that the answer asserts a value for is a missing
    #    disclosure: the answer presents an ambiguous/unverified figure as clean.
    for metric in excluded:
        if _mentions_metric(lowered, metric):
            result.presented_excluded.append(metric)

    # 2. A cross-source conflict must be disclosed when the answer states the metric.
    conflict_metrics = sorted({str(c.get("metric")) for c in conflicts if c.get("metric")})
    for metric in conflict_metrics:
        if _mentions_metric(lowered, metric) and "disagree" not in lowered and "conflict" not in lowered:
            result.required_disclosures.append(f"sources disagree on {metric}")

    # 3. An asserted, excluded metric with no conflict is still owed a disclosure,
    #    UNLESS the answer already discloses it in the same sentence.
    for metric in result.presented_excluded:
        if not _answer_discloses(answer, metric):
            result.required_disclosures.append(
                f"{metric}: its accounting definition or provenance is unresolved"
            )

    # Deduplicate while preserving order.
    seen: set[str] = set()
    result.required_disclosures = [
        d for d in result.required_disclosures if not (d in seen or seen.add(d))
    ]
    result.missing_disclosures = list(result.required_disclosures)
    return result


def disclosure_note(required: list[str]) -> str:
    """A plain sentence an answer can append when it owes a disclosure."""
    if not required:
        return ""
    return "Data caveat: " + "; ".join(required) + "."


__all__ = ["FinanceEnforcement", "disclosure_note", "enforce_finance_answer"]
