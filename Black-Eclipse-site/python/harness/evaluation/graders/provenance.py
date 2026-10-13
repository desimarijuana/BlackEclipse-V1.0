"""Provenance grader.

The answer must say WHERE its material facts came from: the declared provenance
labels (e.g. ``retrieved`` / ``computed`` / ``collected``) must appear, every
required source must have actually been used (a completed call) AND cited in the
answer, and an overclaim (e.g. calling collected data "verified") fails.

Deterministic and structural: labels/claims are declared by the task, and
"used" is read from the real trajectory, never from the model's prose alone.
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


class ProvenanceGrader(Grader):
    name = "provenance"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config)
        output = ctx.final_output or ""
        lower = output.lower()
        failures: list[str] = []
        checks = 0
        cited: list[str] = []

        for label in config.get("require_labels") or []:
            checks += 1
            if str(label).lower() not in lower:
                failures.append(f"provenance label missing: {label!r}")

        for source in config.get("required_sources") or []:
            checks += 1
            name = str(source)
            used = any(
                str((c.get("args") or {}).get("service") or "") == name
                and c.get("status") == "completed"
                for c in ctx.tool_calls
            )
            if used and name.lower() in lower:
                cited.append(name)
            elif not used:
                failures.append(f"source {name!r} was never used by a completed call")
            else:
                failures.append(f"source {name!r} was used but not cited in the answer")

        for claim in config.get("forbidden_claims") or []:
            checks += 1
            if str(claim).lower() in lower:
                failures.append(f"overclaim present: {claim!r}")

        if config.get("require_tool_provenance"):
            checks += 1
            if not any(c.get("status") == "completed" for c in ctx.tool_calls):
                failures.append("no completed source call backs the answer")

        if checks == 0:
            return GraderResult.unmeasured_result(self.name, "no provenance contract configured")
        score = max(0.0, 1.0 - len(failures) / checks)
        return GraderResult(
            self.name, score, not failures,
            details={"checks": checks, "cited_sources": cited},
            failures=failures,
            evidence=[{"cited": cited}],
        )
