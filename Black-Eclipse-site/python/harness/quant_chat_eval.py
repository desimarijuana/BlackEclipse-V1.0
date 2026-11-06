"""Live-chat eval fixtures for the quant contract.

The deterministic unit tests prove the protocol TEXT. This module grades a REAL
chat answer and its tool calls against the same contract, so a live run can be
checked without a UI:

    {"query": "...", "output": "...", "toolNames": ["model_catalog", ...]}

one JSON object per line on stdin:

    python -m harness.quant_chat_eval < answers.jsonl

It never calls a model itself and never invents a metric; it only grades what the
run produced.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .quant_intent import classify_quant_intent, evaluate_quant_outcome


@dataclass(frozen=True)
class ChatCase:
    id: str
    query: str
    tier: str
    required_tools: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = (
        "guaranteed return", "risk-free profit", "tomorrow will be exactly",
    )


CASES: tuple[ChatCase, ...] = (
    ChatCase(
        id="forecast-gold",
        query="forecast gold for tomorrow",
        tier="standard",
        required_tools=("analysis_run",),
    ),
    ChatCase(
        id="build-strategy",
        query="build a gold momentum strategy",
        tier="deep",
        required_tools=("model_catalog", "run_backtest"),
    ),
    ChatCase(
        id="reuse-model",
        query="reuse the model from last week",
        tier="standard",
        required_tools=("model_catalog",),
    ),
)


def _find_case(query: str) -> Optional[ChatCase]:
    text = str(query or "").strip().lower()
    for case in CASES:
        if text == case.query.lower():
            return case
    return None


def grade_answer(
    query: str, output: str, tool_names: Iterable[str],
) -> dict[str, Any]:
    """Grade one live answer. A missing case is graded by tier only."""
    case = _find_case(query)
    intent = classify_quant_intent(query)
    tier = case.tier if case else intent.tier
    names = {str(name) for name in tool_names if name}
    text = str(output or "")
    failures: list[str] = []

    if intent.tier != tier:
        failures.append(f"classifier expected {tier}, got {intent.tier}")
    if tier in ("standard", "deep") and "artifacts:" not in text.lower():
        failures.append("missing the final Artifacts: line")
    if case:
        for tool in case.required_tools:
            if tool not in names:
                failures.append(f"missing required tool {tool}")
        lowered = text.lower()
        for phrase in case.forbidden_phrases:
            if phrase in lowered:
                failures.append(f"forbidden claim {phrase!r}")
    outcome = evaluate_quant_outcome(intent.to_dict(), names, text)
    if outcome is not None and not outcome["complete"]:
        failures.extend(f"missing {item}" for item in outcome["missing"])

    return {
        "query": query,
        "tier": tier,
        "artifactLine": "artifacts:" in text.lower(),
        "toolNames": sorted(names),
        "passed": not failures,
        "failures": failures,
    }


def grade_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    results = [
        grade_answer(
            str(record.get("query") or ""),
            str(record.get("output") or ""),
            record.get("toolNames") or (),
        )
        for record in records
    ]
    failures = [result for result in results if not result["passed"]]
    return {
        "version": "quant-chat-v1",
        "total": len(results),
        "passed": len(results) - len(failures),
        "failures": failures,
        "results": results,
    }


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - CLI
    records = []
    for line in sys.stdin:
        line = line.strip()
        if line:
            records.append(json.loads(line))
    report = grade_records(records)
    print(json.dumps(report, indent=2))
    return 0 if not report["failures"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
