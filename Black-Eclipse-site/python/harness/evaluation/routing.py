"""Routing benchmark metrics for the standing gate (round 4, W3.2).

The classifier-tier benchmark (`harness/ui/routing_benchmark_v1.json`) is the
measurement source. It is deterministic and model-free, so the offline gate can
run it on every release. The result is injected into the suite aggregates with
its source recorded in `SuiteResult.routing` — these are NOT agent-trial
dimensions and the report says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

_DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "ui" / "routing_benchmark_v1.json"


def run_routing_evaluation(
    path: Optional[Union[str, Path]] = None,
) -> dict[str, Any]:
    """Run every recorded routing case through the real classifier."""
    from ..ui.catalog import UiCatalog  # noqa: PLC0415
    from ..ui.mode import classify_request  # noqa: PLC0415

    dataset_path = Path(path) if path is not None else _DEFAULT_DATASET
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = list(dataset.get("cases") or [])
    catalog = UiCatalog()
    failures: list[dict[str, Any]] = []
    escalation_total = 0
    escalation_ok = 0

    for case in cases:
        decision = classify_request(str(case.get("text") or ""), catalog=catalog)
        mode_ok = decision.mode.value == case.get("expectedMode")
        gap_ok = decision.capability_gap is bool(case.get("expectedGap"))
        if not (mode_ok and gap_ok):
            failures.append({
                "id": case.get("id"),
                "expectedMode": case.get("expectedMode"),
                "expectedGap": case.get("expectedGap"),
                "actualMode": decision.mode.value,
                "actualGap": decision.capability_gap,
                "reasons": list(decision.reasons),
            })
        if case.get("expectedMode") != "compose":
            escalation_total += 1
            if mode_ok:
                escalation_ok += 1

    total = len(cases)
    misroute_rate = (len(failures) / total) if total else None
    escalation_correct = (escalation_ok / escalation_total) if escalation_total else None
    return {
        "datasetId": dataset.get("datasetId"),
        "version": dataset.get("version"),
        "cases": total,
        "misroute_rate": misroute_rate,
        "escalation_correct": escalation_correct,
        "failures": failures,
        "passed": not failures,
    }


__all__ = ["run_routing_evaluation"]
