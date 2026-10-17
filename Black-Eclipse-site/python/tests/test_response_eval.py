"""Parity test for the safe scalar evaluator (Python ↔ TypeScript).

Both evaluators run the SAME fixture corpus
(`src/lib/response/__fixtures__/evaluate-cases.json`), so a change to one that
breaks agreement with the other fails CI. The renderer uses the TS evaluator; the
harness validates with this one.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from harness.response_eval import EVAL_FUNCTIONS, evaluate_expression, validate_expression

_FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "lib", "response", "__fixtures__", "evaluate-cases.json",
)


def _cases() -> list[dict]:
    with open(_FIXTURES, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["expression"])
def test_parity_with_typescript_fixtures(case: dict) -> None:
    result = evaluate_expression(case["expression"], case["vars"])
    expected = case["expected"]
    if expected is None:
        assert result is None, (case, result)
    else:
        assert result is not None, case
        assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (case, result)


def test_unknown_function_is_rejected_by_validation() -> None:
    assert validate_expression("totally_made_up(1)")["ok"] is False


def test_unknown_variable_is_rejected_when_a_known_set_is_given() -> None:
    assert validate_expression("a + b", {"a"})["ok"] is False


def test_known_expression_validates() -> None:
    result = validate_expression("clamp(entry * x, 0, 100)", {"entry", "x"})
    assert result["ok"] is True
    assert result["functions"] == ["clamp"]


def test_rounding_is_half_away_from_zero() -> None:
    # Python's built-in round() is banker's rounding; the evaluator must NOT use it.
    assert evaluate_expression("round(2.5)", {}) == 3
    assert evaluate_expression("round(-2.5)", {}) == -3


def test_whitelist_excludes_dangerous_names() -> None:
    assert "eval" not in EVAL_FUNCTIONS
    assert "import" not in EVAL_FUNCTIONS
