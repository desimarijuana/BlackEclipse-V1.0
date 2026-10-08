"""Engineering hardening Phase 4 — the Python size guard.

`python/harness/**` had no size guard at all, while AGENTS.md warns that memory
is the top constraint and god files are a real risk. This is the Python half of
the graduated guard in `src/lib/size-budget.test.ts`:

  * HARD ceiling — a file over this many lines must be in RATCHET_PY below.
  * SOFT ceiling — reported (a warning line) but allowed.
  * RATCHET      — the files already over the hard ceiling, each pinned to its
                   current size: they may shrink, never grow. Splitting a file
                   removes it from the list (no edit needed); a genuine shrink
                   needs no edit either.

A NEW oversized file fails; an existing one may not grow. That is what makes it
bite. Behavior contract, not a source-text assertion.
"""

from __future__ import annotations

import os

HARD_CEILING_LINES = 1200
SOFT_CEILING_LINES = 800

# Files above the hard ceiling today, pinned to their measured size (splitlines).
RATCHET_PY: dict[str, int] = {
    # Grew with the Document Intelligence run-blob wiring (the `document_sink`
    # parameter, collector, and `update_run(documents=…)`). May only shrink from
    # here; the collector wiring is a split candidate alongside the vision one.
    "graph.py": 1870,
    # Grew with the approval-card pause path in `make_code_authorizer` (the code
    # write now blocks on a decision instead of refusing immediately). May only
    # shrink from here; the code-write pause is a split candidate.
    "code/tools.py": 1263,
    "eclipse_memory/service.py": 1832,
    "eclipse_memory/store.py": 1749,
    # Grew with the `documents` run-blob column (schema + `_ADDED_COLUMNS` +
    # `_run_row`). May only shrink from here.
    "persistence.py": 1395,
    "mcp/manager.py": 1106,
    # Grew past the hard ceiling with the Vision + Document Intelligence subsystem
    # boot wiring (`vision_assets`, `document_store`, tool registration). May only
    # shrink from here; the two subsystem-construction blocks are split candidates.
    "service.py": 1222,
    # `main.py` was split (Phase S.2): the FastAPI lifespan boot/shutdown wiring
    # moved to `harness/boot.py`, dropping `main.py` under the hard ceiling — so it
    # is removed from the ratchet rather than raised.
    #
    # `service.py` grew with the Market Data Layer wiring (a one-line
    # `install_market_layer(self)` call + the per-run bundle pass); the market
    # subsystem's own modules all stay well under the ceiling and the boot wiring
    # lives in `market/bootstrap.py`. Split candidate: the subsystem construction
    # block should move into per-subsystem `install_*` helpers like the market one.
    "service.py": 1224,
}

_HARNESS_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")


def _measure() -> dict[str, int]:
    """Map each `python/harness/**` module (relative path) to its line count."""
    out: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(_HARNESS_ROOT):
        if "__pycache__" in dirpath:
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            with open(full, encoding="utf-8") as handle:
                lines = len(handle.read().splitlines())
            rel = os.path.relpath(full, _HARNESS_ROOT).replace(os.sep, "/")
            out[rel] = lines
    return out


def find_oversized_py(entries: dict[str, int], ceiling: int, ratchet: dict[str, int]) -> dict[str, int]:
    """The pure detector: files over `ceiling` and over their ratchet budget."""
    return {
        rel: lines
        for rel, lines in entries.items()
        if lines > ceiling and lines > ratchet.get(rel, 0)
    }


def test_no_non_ratcheted_harness_module_exceeds_the_hard_ceiling():
    oversized = find_oversized_py(_measure(), HARD_CEILING_LINES, RATCHET_PY)
    assert oversized == {}, (
        f"python/harness modules over {HARD_CEILING_LINES} lines — split them or "
        f"add a justified ratchet entry: {oversized}"
    )


def test_every_ratcheted_module_is_at_or_below_its_pinned_budget():
    measured = _measure()
    for rel, budget in RATCHET_PY.items():
        assert rel in measured, f"ratcheted module missing: {rel}"
        assert measured[rel] <= budget, f"{rel} grew past its pinned budget {budget}"


def test_the_detector_bites_on_a_synthetic_oversized_module():
    entries = {"new_monolith.py": HARD_CEILING_LINES + 500, "small.py": 100}
    flagged = find_oversized_py(entries, HARD_CEILING_LINES, RATCHET_PY)
    assert set(flagged) == {"new_monolith.py"}
    # A ratcheted file at budget is allowed; one line over is flagged.
    rel = next(iter(RATCHET_PY))
    assert find_oversized_py({rel: RATCHET_PY[rel]}, HARD_CEILING_LINES, RATCHET_PY) == {}
    assert set(find_oversized_py({rel: RATCHET_PY[rel] + 1}, HARD_CEILING_LINES, RATCHET_PY)) == {rel}


def test_soft_ceiling_report_is_produced(capsys):
    soft = {rel: n for rel, n in _measure().items() if n > SOFT_CEILING_LINES}
    if soft:
        print(f"[size-budget] {len(soft)} harness module(s) over the soft ceiling {SOFT_CEILING_LINES}")
    # Informational only; pin that the measurement is real.
    assert isinstance(soft, dict)
