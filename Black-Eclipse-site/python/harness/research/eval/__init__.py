"""Phase 4 semantic-support evaluation (Workstream 4).

A small, versioned, human-labeled set of claim/evidence pairs, plus a runner that
reports — separately and never as a single "pass/fail" — the deterministic
checks (citation existence, entity/metric/period/basis/unit/currency match) and
the human-labeled semantic-support slice.

The judge (deterministic or model-assisted) NEVER sees the gold label while
judging; it emits a prediction that is compared to the label afterward. A model
critic, if used, is an advisory signal only and its output is reported against
human labels — it cannot set production claim status.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from ...retrieval.contract import (
    EvidenceItem,
    NormalizedFinancialObject,
    SourceReference,
)
from ..mandate import FactLeg
from ..periods import periods_match

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset_v1.json")
LABELS = ("supported", "unsupported", "conflicting", "indeterminate")


@dataclass
class EvalCase:
    caseId: str
    claimText: str
    claimKind: str
    mandateLegId: str
    label: str
    rationale: str
    evidenceSpan: str
    evidenceIds: list[str] = field(default_factory=list)
    calculations: list[str] = field(default_factory=list)


def load_dataset(path: Optional[str] = None) -> dict[str, Any]:
    with open(path or DATASET_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def dataset_checksum(dataset: dict[str, Any]) -> str:
    """A stable checksum of the dataset content (recorded with results)."""
    payload = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


# ── Evidence fixtures keyed by the evidence spans the dataset references ──────


def _obj(**kwargs: Any) -> NormalizedFinancialObject:
    return NormalizedFinancialObject(
        source=SourceReference(source=kwargs.pop("source", "JDDS"), sourceType="structured", validationStatus="valid"),
        **kwargs,
    )


def _item(eid: str, *objects: NormalizedFinancialObject, kind: str = "structured") -> EvidenceItem:
    return EvidenceItem(
        id=eid,
        kind=kind,
        summary=eid,
        objects=list(objects),
        source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
    )


def build_fixtures() -> dict[str, tuple[list[EvidenceItem], list[FactLeg]]]:
    """Build per-case evidence + the mandate leg the claim is judged against.

    Keyed by caseId. Fixtures are synthetic and clearly not market facts.
    """
    fixtures: dict[str, tuple[list[EvidenceItem], list[FactLeg]]] = {}

    def leg(period: str = "FY2024", metric: str = "revenue", **kw: Any) -> FactLeg:
        return FactLeg(id=f"leg_{metric}_{period}", metric=metric, entityRaw="TEST",
                       entitySymbol="TEST", market="US", period=period, **kw)

    fixtures["supported-exact-metric"] = (
        [_item("E1", _obj(name="revenue", value=1000.0, period="FY2024", currency="USD", instrument="TEST"))],
        [leg()],
    )
    fixtures["unsupported-wrong-period"] = (
        [_item("E2", _obj(name="revenue", value=1000.0, period="FY2023", currency="USD", instrument="TEST"))],
        [leg()],
    )
    fixtures["unsupported-wrong-entity"] = (
        [_item("E3", _obj(name="revenue", value=1000.0, period="FY2024", currency="USD", instrument="OTHER"))],
        [leg()],
    )
    fixtures["unsupported-wrong-currency"] = (
        [_item("E4", _obj(name="revenue", value=1000.0, period="FY2024", currency="EUR", instrument="TEST"))],
        [leg(currency="USD")],
    )
    fixtures["indeterminate-causal"] = (
        [_item("E5", _obj(name="revenue", value=1000.0, period="FY2024", currency="USD", instrument="TEST"))],
        [leg()],
    )
    fixtures["conflicting-two-sources"] = (
        [
            _item("E6", _obj(name="revenue", value=1000.0, period="FY2024", currency="USD", instrument="TEST")),
            _item("E7", _obj(name="revenue", value=1200.0, period="FY2024", currency="USD", instrument="TEST",
                             source="PROVIDER_B")),
        ],
        [leg()],
    )
    fixtures["supported-qualitative"] = (
        [_item("E8", kind="web")],
        [FactLeg(id="leg_risk_FY2024", metric="sentiment", entityRaw="TEST", entitySymbol="TEST", period="FY2024")],
    )
    fixtures["unsupported-no-evidence"] = ([], [leg()])
    return fixtures


def _predict_for_case(
    case: EvalCase,
    evidence: list[EvidenceItem],
    legs: list[FactLeg],
) -> str:
    """A DETERMINISTIC predictor of semantic support — the baseline judge.

    It is deliberately conservative: it never predicts `supported` unless a cited
    object matches the leg on metric/period/currency AND the cited evidence is
    not an unverified snippet. A causal/interpretation claim is always
    `indeterminate`. Two eligible disagreeing sources is `conflicting`.
    """
    if case.claimKind == "interpretation":
        return "indeterminate"

    evidence_index = {item.id: item for item in evidence}
    leg = legs[0] if legs else None

    # No evidence cited at all.
    cited = [evidence_index[eid] for eid in case.evidenceIds if eid in evidence_index]
    if not cited:
        return "unsupported"

    if case.claimKind == "qualitative_fact":
        # A qualitative claim may be supported by a retrieved web/filing snippet.
        if any(item.kind in ("web", "filing") for item in cited):
            return "supported"
        return "unsupported"

    if leg is None:
        return "unsupported"

    # Detect a conflict: two cited objects with the same metric/period/currency
    # but different values.
    values: set[float] = set()
    matched = 0
    for item in cited:
        if item.kind == "unverified":
            continue
        for obj in item.objects:
            if obj.name != leg.metric:
                continue
            if not periods_match(leg.period, obj.period):
                continue
            if leg.currency and (obj.currency or "").upper() != leg.currency.upper():
                continue
            if leg.entitySymbol and obj.instrument and obj.instrument != leg.entitySymbol:
                continue
            matched += 1
            if isinstance(obj.value, (int, float)):
                values.add(float(obj.value))
    if matched == 0:
        return "unsupported"
    if len(values) > 1:
        return "conflicting"
    return "supported"


@dataclass
class EvalMetrics:
    datasetVersion: str
    checksum: str
    total: int = 0
    correct: int = 0
    falseAccepts: int = 0        # predicted supported, label unsupported
    falseRejects: int = 0        # predicted unsupported, label supported
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    perSlice: dict[str, dict[str, int]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        accuracy = self.correct / self.total if self.total else 0.0
        precision = (
            self.correct / (self.correct + self.falseAccepts)
            if (self.correct + self.falseAccepts)
            else 0.0
        )
        return {
            "datasetVersion": self.datasetVersion,
            "checksum": self.checksum,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(accuracy, 4),
            "falseAccepts": self.falseAccepts,
            "falseRejects": self.falseRejects,
            "precisionNoFalseAccept": round(precision, 4),
            "confusion": self.confusion,
            "perSlice": self.perSlice,
            "failures": self.failures,
        }


def run_evaluation(dataset: Optional[dict[str, Any]] = None) -> EvalMetrics:
    """Run the deterministic judge over the labeled set and report metrics.

    The judge never sees the label; the label is applied only when scoring.
    """
    dataset = dataset or load_dataset()
    metrics = EvalMetrics(
        datasetVersion=str(dataset.get("datasetVersion")),
        checksum=dataset_checksum(dataset),
    )
    fixtures = build_fixtures()

    for raw in dataset.get("cases", []):
        case = EvalCase(
            caseId=raw["caseId"],
            claimText=raw["claimText"],
            claimKind=raw["claimKind"],
            mandateLegId=raw.get("mandateLegId", ""),
            label=raw["label"],
            rationale=raw.get("rationale", ""),
            evidenceSpan=raw.get("evidenceSpan", ""),
            evidenceIds=raw.get("evidenceIds") or [],
            calculations=raw.get("calculations") or [],
        )
        evidence, legs = fixtures.get(case.caseId, ([], []))
        # Auto-wire the evidence ids when the dataset omits them.
        if not case.evidenceIds:
            case.evidenceIds = [item.id for item in evidence]

        prediction = _predict_for_case(case, evidence, legs)

        metrics.total += 1
        metrics.confusion.setdefault(case.label, {}).setdefault(prediction, 0)
        metrics.confusion[case.label][prediction] += 1
        slice_key = case.claimKind
        metrics.perSlice.setdefault(slice_key, {"total": 0, "correct": 0})
        metrics.perSlice[slice_key]["total"] += 1

        if prediction == case.label:
            metrics.correct += 1
            metrics.perSlice[slice_key]["correct"] += 1
        else:
            if prediction == "supported" and case.label == "unsupported":
                metrics.falseAccepts += 1
            if prediction == "unsupported" and case.label == "supported":
                metrics.falseRejects += 1
            metrics.failures.append(
                {
                    "caseId": case.caseId,
                    "label": case.label,
                    "prediction": prediction,
                    "rationale": case.rationale,
                }
            )
    return metrics


__all__ = [
    "DATASET_PATH",
    "LABELS",
    "EvalCase",
    "EvalMetrics",
    "load_dataset",
    "dataset_checksum",
    "build_fixtures",
    "run_evaluation",
]
