"""Generate docs/harness/scorecard.json from a real evaluation run + C7 report.

This is the C8.5 writer: no dimension value is typed by hand. It runs the
offline evaluation gate (scripted tier for speed) and the C7 probe, then fills
only the dimensions that produced a measurement. Run from the repository:

    python/scorecard_from_runs.py [--out docs/harness/scorecard.json]

The Node wrapper (`npm run scorecard:from-runs`) also regenerates the markdown.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parent
ROOT = PYTHON_DIR.parent
DEFAULT_OUT = ROOT / "docs" / "harness" / "scorecard.json"

from harness.evaluation.gate import run_offline_gate  # noqa: E402
from harness.evaluation.scorecard import regenerate  # noqa: E402
from harness.observability.probe import run_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the scorecard from runs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--base", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--suite", choices=("builtin",), default="builtin")
    args = parser.parse_args(argv)

    base = json.loads(args.base.read_text(encoding="utf-8"))
    suite = run_offline_gate()
    release = run_probe(runs=20)
    generated = regenerate(base, suite=suite, release=release)
    args.out.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    measured = [d["id"] for d in generated["dimensions"] if d.get("status") == "measured"]
    print(f"[scorecard] wrote {args.out} — measured: {', '.join(measured)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
