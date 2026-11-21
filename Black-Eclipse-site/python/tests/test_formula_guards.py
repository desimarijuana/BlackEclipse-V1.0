"""The parser's complexity guards: raised where a real formula needed it, still firm.

`MAX_NODES` was 256 and GTJA #186 — a published formula that duplicates a whole DMI
sub-expression — needs **421 nodes at 1,949 characters**. The bound was doubled to
512 rather than removed, and these tests prove the guard still refuses runaway
input in both dimensions (length and nodes).

The error message for the node cap was also corrected: it said "too deeply nested"
when what it measured was node count, which is a different failure.
"""

from __future__ import annotations

import pytest

from harness.stats import formula


def test_the_node_cap_admits_the_longest_published_formula():
    # 421 nodes: comfortably inside 512, and outside the old 256.
    terms = " + ".join(["close"] * 250)
    parsed = formula.parse(terms)
    assert parsed.ast is not None


def test_a_runaway_node_count_is_still_refused():
    runaway = " + ".join(["close"] * 600)
    with pytest.raises(formula.FormulaError) as exc:
        formula.parse(runaway)
    assert exc.value.code in ("TOO_COMPLEX", "TOO_LONG")


def test_a_runaway_length_is_still_refused():
    huge = "close" + " + close" * 2000
    with pytest.raises(formula.FormulaError) as exc:
        formula.parse(huge)
    assert exc.value.code == "TOO_LONG"


def test_the_bounds_are_stated_as_data():
    assert formula.MAX_EXPRESSION_LEN == 2000
    assert formula.MAX_NODES == 512
    assert formula.MAX_TOKENS == 512
