"""Round 3 / W8 (ADR-H296) - the published benchmarks are GENERATED.

The point of publishing a number is that a reader can CHECK it. That only
works if the file cannot be quietly improved by hand, so the committed file
must match a FRESH generation - except for the two volatile lines (the run
id and the commit), which change on every generation by design.

The live tier is published as NOT MEASURED until a live run has been
recorded. A live number nobody has run is a rumour, and a rumour in a
benchmark table is worse than an empty row.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))

PUBLISHED = os.path.join(REPO, "docs", "harness", "benchmarks.md")

# The two lines that legitimately differ between two generations.
VOLATILE = (
    re.compile(r"^- run: `evalrun-\d+`$", re.M),
    re.compile(r"^- git commit: `[^`]+`$", re.M),
    # The timing-derived measurements are MEASUREMENTS, not verdicts: the
    # offline gate runs a real loop against a real sandbox, so a latency or a
    # reliability figure legitimately differs between two generations. Masking
    # them keeps the gate on the DECISIONS (the pass rates, the unmeasured
    # list, the gate verdict) and off the clock.
    re.compile(r"^\| (latency|reliability) \| [^|]* \|$", re.M),
)


def _mask(text: str) -> str:
    for pattern in VOLATILE:
        text = pattern.sub("<volatile>", text)
    return text


def test_the_published_benchmarks_are_generated_not_hand_edited() -> None:
    from harness.evaluation.report import write_benchmarks

    with tempfile.TemporaryDirectory(prefix="be-bench-") as tmp:
        generated = write_benchmarks(os.path.join(tmp, "benchmarks.md"))
        with open(generated, encoding="utf-8") as handle:
            fresh = handle.read()
    with open(PUBLISHED, encoding="utf-8") as handle:
        committed = handle.read()
    assert _mask(committed) == _mask(fresh), (
        "docs/harness/benchmarks.md is stale or was hand-edited. "
        "Regenerate it: npm run eval:benchmarks"
    )


def test_the_live_tier_is_published_as_not_measured_until_it_is() -> None:
    """The live tier must not carry a number nobody ran."""
    with open(PUBLISHED, encoding="utf-8") as handle:
        text = handle.read()
    live = text.split("## Live tier")[-1]
    assert "NOT MEASURED" in live or "gate:" in live, (
        "the live tier must be published as NOT MEASURED (or carry a real, "
        "provenance-stamped run) - never as a number nobody ran"
    )


def test_the_published_file_carries_its_provenance() -> None:
    """A number without its dataset, commit and grader version is a rumour."""
    with open(PUBLISHED, encoding="utf-8") as handle:
        text = handle.read()
    for required in ("- dataset: ", "- agent version: ", "- git commit: ", "- grader version: "):
        assert required in text, f"the published file is missing {required!r}"
