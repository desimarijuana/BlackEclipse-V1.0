"""Round 4 (W3.1) — the versioned UI routing benchmark.

Every case is deterministic and model-free: the same classifier the runtime uses
is run against the builtin catalog and compared with the recorded verdict. This
is the first tier of the routing benchmark; the end-to-end scripted-graph tier
lands with W3.2's gate dimensions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.ui.catalog import UiCatalog
from harness.ui.mode import classify_request

_CASES_PATH = Path(__file__).resolve().parents[1] / "harness" / "ui" / "routing_benchmark_v1.json"


def _dataset() -> dict:
    return json.loads(_CASES_PATH.read_text(encoding="utf-8"))


def _cases() -> list[dict]:
    return _dataset()["cases"]


def test_the_benchmark_is_versioned_and_reviewed():
    dataset = _dataset()
    assert dataset["datasetId"] == "ui-routing-v1"
    assert dataset["version"] >= 1
    assert dataset["reviewed"] is True
    assert len({case["id"] for case in dataset["cases"]}) == len(dataset["cases"])


@pytest.mark.parametrize("case", _cases(), ids=[case["id"] for case in _cases()])
def test_routing_case(case):
    decision = classify_request(case["text"], catalog=UiCatalog())
    assert decision.mode.value == case["expectedMode"], case["text"]
    assert decision.capability_gap is case["expectedGap"], case["text"]
