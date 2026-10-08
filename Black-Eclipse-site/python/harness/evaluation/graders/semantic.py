"""Deterministic semantic grader (no LLM judge).

Scores coverage of required/forbidden terms and token-overlap F1 against an
optional reference answer. This is deliberately lexical, not a model judge — the
standing gates never delegate pass/fail to an LLM. When a task needs a genuine
semantic judgment it belongs in the live tier and is reported unmeasured here.
"""

from __future__ import annotations

import re
from typing import Any

from . import GradeContext, Grader, GraderResult


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


class SemanticGrader(Grader):
    name = "semantic"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config)
        spec = config.get("semantic") or getattr(ctx.task, "metadata", {}).get("semantic") or {}
        must_include = list(spec.get("must_include") or config.get("must_include") or [])
        must_not_include = list(spec.get("must_not_include") or config.get("must_not_include") or [])
        reference = spec.get("reference") or config.get("reference")
        min_coverage = float(spec.get("min_coverage", config.get("min_coverage", 1.0)))

        if not must_include and not must_not_include and not reference:
            return GraderResult.unmeasured_result(self.name, "no semantic spec declared")

        output = ctx.final_output or ""
        lower = output.lower()
        failures: list[str] = []

        hits = [term for term in must_include if term.lower() in lower]
        coverage = len(hits) / len(must_include) if must_include else 1.0
        for term in must_include:
            if term.lower() not in lower:
                failures.append(f"missing required term {term!r}")
        for term in must_not_include:
            if term.lower() in lower:
                failures.append(f"forbidden term present {term!r}")

        f1 = None
        if reference:
            ref, got = set(_tokens(reference)), _tokens(output)
            common = len(ref & set(got))
            precision = common / len(got) if got else 0.0
            recall = common / len(ref) if ref else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        passed = coverage >= min_coverage and not failures
        score = coverage if f1 is None else (coverage + f1) / 2
        return GraderResult(self.name, score, passed,
                            details={"coverage": round(coverage, 4), "f1": None if f1 is None else round(f1, 4)},
                            failures=failures)
