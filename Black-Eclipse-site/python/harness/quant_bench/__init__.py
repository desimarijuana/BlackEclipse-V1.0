"""QuantBench — the measurable contract for quant mode.

The suite answers one question: *is Eclipse's quant output defensible?* It is
versioned, deterministic where possible, and splits into:

  * `routing`         — did the turn reach the right tier/kind?
  * `honesty`         — did the answer refuse fabrication, name its artifacts and
                        avoid guarantees?
  * `math`            — deterministic invariants (causality, costs, partial fills,
                        carry, manifest stability);
  * `workflow`        — a full-cycle answer used the required tools in order;
  * `reproducibility` — the same inputs produce the same metrics and digest.

Run it with `python -m harness.quant_bench`. A failure is a regression, not a
style preference.
"""

from __future__ import annotations

from .cases import CASES, QuantBenchCase
from .runner import run_benchmark, score_case

__all__ = ["CASES", "QuantBenchCase", "run_benchmark", "score_case"]
