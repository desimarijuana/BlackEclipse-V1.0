"""Phase 5 escalation evaluation (source hierarchy + false-acceptance).

Runs the *deterministic* web-fact validator over the labeled escalation set and
reports, separately: acceptance precision (no false accepts), expected source
tier/kind, and coverage of the labelled cases. The judge never sees the label.

A false accept here is the safety failure that matters most — a fabricated or
unsupported web value being admitted as a fact. The metric is reported, not
marketed as semantic accuracy.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..mandate import parse_mandate
from ..web_facts import ExtractedFact, WebPageContent, validate_fact

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset_escalation_v1.json")

# Canonical metric id → a phrasing the deterministic mandate parser recognises.
_METRIC_PHRASES = {
    "revenue": "revenue",
    "netIncome": "net income",
    "operatingIncome": "operating income",
    "freeCashFlow": "free cash flow",
    "eps": "eps",
}


def load_escalation_dataset(path: str | None = None) -> dict[str, Any]:
    with open(path or DATASET_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def dataset_checksum(dataset: dict[str, Any]) -> str:
    payload = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


@dataclass
class EscalationMetrics:
    datasetVersion: str
    checksum: str
    total: int = 0
    correct: int = 0
    falseAccepts: int = 0
    falseRejects: int = 0
    tierCorrect: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        accuracy = self.correct / self.total if self.total else 0.0
        accepted_predictions = self.correct + self.falseAccepts
        precision = self.correct / accepted_predictions if accepted_predictions else 1.0
        return {
            "datasetVersion": self.datasetVersion,
            "checksum": self.checksum,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "falseAccepts": self.falseAccepts,
            "falseRejects": self.falseRejects,
            "tierCorrect": self.tierCorrect,
            "failures": self.failures,
        }


def run_escalation_evaluation(dataset: dict[str, Any] | None = None) -> EscalationMetrics:
    dataset = dataset or load_escalation_dataset()
    metrics = EscalationMetrics(
        datasetVersion=str(dataset.get("datasetVersion")),
        checksum=dataset_checksum(dataset),
    )
    for case in dataset.get("cases", []):
        phrase = _METRIC_PHRASES.get(case["metric"], case["metric"])
        query = (
            f"Compare {case['entity']} {phrase} for {case['legPeriod']} in {case['currency']}"
        )
        if case.get("basis"):
            query += f" {case['basis']}"
        mandate = parse_mandate(query, ticker=case["entity"])
        tier = case["pageTier"]
        page = WebPageContent(
            pageId="p1", url=f"https://example-{tier}.test/report",
            title="Report", publishedAt=None, tier=tier, text=case["pageText"],
        )
        fact = ExtractedFact(
            metric=case["metric"],
            value=case["factValue"],
            currency=case.get("factCurrency", case["currency"]),
            unit=case.get("factUnit"),
            period=case.get("factPeriod", case["legPeriod"]),
            basis=case.get("factBasis", case.get("basis")),
            pageId="p1",
            sourceSpan=case["factSpan"],
            documentTitle="Report",
        )
        permitted = set(case.get("stageTiers") or [tier])
        result = validate_fact(fact, {"p1": page}, mandate.factLegs, permitted_tiers=permitted)
        predicted = result.ok
        expected = bool(case["expectedAccepted"])

        metrics.total += 1
        if predicted == expected:
            metrics.correct += 1
        elif predicted and not expected:
            metrics.falseAccepts += 1
        elif not predicted and expected:
            metrics.falseRejects += 1

        if predicted:
            kind = "filing" if tier in ("primary", "official") else "web"
            if kind == case.get("expectedEvidenceKind"):
                metrics.tierCorrect += 1

        if predicted != expected:
            metrics.failures.append(
                {
                    "caseId": case["caseId"],
                    "expected": expected,
                    "predicted": predicted,
                    "reason": result.reason,
                    "rationale": case["rationale"],
                }
            )
    return metrics


__all__ = [
    "DATASET_PATH",
    "EscalationMetrics",
    "load_escalation_dataset",
    "dataset_checksum",
    "run_escalation_evaluation",
]
