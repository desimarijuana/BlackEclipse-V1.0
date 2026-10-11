"""Factor & Alpha Research Lab.

A deterministic, reusable factor-research service built on the SAME NumPy core
and conventions as the statistical engine. Public surface:

  * `FACTOR_ENGINE_VERSION` — recorded in every response.
  * `FactorError`           — structured, non-fabricating error.
  * `FACTOR_TOOLS`          — the agent-tool names.
  * the `engine` functions  — the authoritative quantitative implementations.

The engine is pure NumPy + the standard library so it runs under the vendored
interpreter with no heavy scientific dependency added. Distribution tail
probabilities are reused from `harness.stats.dist`.
"""

from __future__ import annotations

from .engine import FACTOR_ENGINE_VERSION, FactorError

__all__ = ["FACTOR_ENGINE_VERSION", "FactorError"]
