"""Phase 6 NVDA labeled regression evaluation.

A small, labeled, offline regression built from NVIDIA's actual SEC XBRL
figures (transcribed with source metadata, never memory-derived). It validates
the RESEARCH PIPELINE's deterministic coverage handling against issuer-reported
FY2024/FY2025 values and the classic stale-vault failure:

  * a period-end-date candidate covers the annual leg it falls inside,
  * the vault's FY2019 row does NOT satisfy a FY2024 leg,
  * a wrong calendar year does not cover,
  * a currency mismatch does not cover.

Metrics reported: coverage accuracy, precision, false accepts, false rejects,
and source-tier compliance. This measures the labeled cases only — it is not a
semantic-accuracy claim.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..coverage import evaluate_leg
from ..mandate import FactLeg
from ..periods import periods_match
from ...retrieval.contract import EvidenceItem, NormalizedFinancialObject, SourceReference

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset_nvda_v1.json")


def load_nvda_dataset(path: str | None = None) -> dict[str, Any]:
    with open(path or DATASET_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def dataset_checksum(dataset: dict[str, Any]) -> str:
    payload = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


@dataclass
class NvdaMetrics:
    datasetVersion: str
    checksum: str
    total: int = 0
    correct: int = 0
    falseAccepts: int = 0
    falseRejects: int = 0
    tierCompliant: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        accuracy = self.correct / self.total if self.total else 0.0
        accepted = self.correct + self.falseAccepts
        precision = self.correct / accepted if accepted else 1.0
        return {
            "datasetVersion": self.datasetVersion,
            "checksum": self.checksum,
            "total": self.total,
            "correct": self.correct,
            "coverageAccuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "falseAccepts": self.falseAccepts,
            "falseRejects": self.falseRejects,
            "tierCompliant": self.tierCompliant,
            "failures": self.failures,
        }


def _leg_from(case: dict[str, Any]) -> FactLeg:
    leg = case["leg"]
    return FactLeg(
        id=case["caseId"], metric=leg["metric"], entityRaw="NVDA", entitySymbol="NVDA",
        market="US", period=leg.get("period"), currency=leg.get("currency"),
        basis=leg.get("basis"), required=True,
    )


def _evidence_from(case: dict[str, Any]) -> EvidenceItem:
    c = case["candidate"]
    tier = c.get("tier", "structured")
    kind = "filing" if tier in ("primary", "official") else "structured"
    source = SourceReference(source="SEC EDGAR" if tier == "primary" else "JDDS", sourceType=tier)
    obj = NormalizedFinancialObject(
        name=c["metric"], value=c["value"], currency=c.get("currency"),
        period=c.get("period"), dataTimestamp=c.get("periodEnd"),
        instrument="NVDA", basis=c.get("basis"), source=source,
    )
    return EvidenceItem(id=case["caseId"], kind=kind, summary="nvda", objects=[obj], source=source)


def run_nvda_evaluation(dataset: dict[str, Any] | None = None) -> NvdaMetrics:
    dataset = dataset or load_nvda_dataset()
    metrics = NvdaMetrics(
        datasetVersion=str(dataset.get("datasetVersion")),
        checksum=dataset_checksum(dataset),
    )
    for case in dataset.get("cases", []):
        leg = _leg_from(case)
        evidence = [_evidence_from(case)]
        coverage = evaluate_leg(leg, evidence, asof=None, conflicts=[])
        predicted = coverage.status in ("covered", "qualified")
        expected = bool(case["expectCovered"])

        metrics.total += 1
        if predicted == expected:
            metrics.correct += 1
        elif predicted and not expected:
            metrics.falseAccepts += 1
        elif not predicted and expected:
            metrics.falseRejects += 1

        tier = case["candidate"].get("tier")
        if predicted and tier in ("primary", "official", "structured"):
            metrics.tierCompliant += 1

        if predicted != expected:
            metrics.failures.append({
                "caseId": case["caseId"],
                "expected": expected,
                "predicted": predicted,
                "status": coverage.status,
                "reason": coverage.reason,
                "rationale": case["rationale"],
            })
    return metrics


__all__ = ["DATASET_PATH", "NvdaMetrics", "load_nvda_dataset", "dataset_checksum", "run_nvda_evaluation"]
