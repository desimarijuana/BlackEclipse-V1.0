"""State grader: judge the REAL resulting environment state.

State-changing tasks are never judged on the model's prose. The environment state
is authoritative; this grader compares it to ``task.expected_state`` with a deep
subset match (plus optional exact-key and file-hash assertions).
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(_subset(e, a) for a in actual) for e in expected)
    return expected == actual


class StateGrader(Grader):
    name = "state"

    def grade(self, ctx: GradeContext) -> GraderResult:
        expected = getattr(ctx.task, "expected_state", None) or {}
        if not expected:
            return GraderResult.unmeasured_result(self.name, "task declares no expected_state")
        actual = ctx.env_state or {}
        failures: list[str] = []
        checked = 0

        # Files: expected_state.files maps rel path -> sha256 OR {contains: "..."}.
        exp_files = expected.get("files")
        act_files = (actual.get("files") if isinstance(actual, dict) else None) or {}
        if exp_files:
            for rel, want in exp_files.items():
                checked += 1
                if isinstance(want, dict):
                    if "sha256" in want and act_files.get(rel) != want["sha256"]:
                        failures.append(f"file {rel}: hash mismatch")
                    if "contains" in want:
                        content = ctx.environment.read(rel) if hasattr(ctx.environment, "read") else None
                        if content is None or want["contains"] not in content:
                            failures.append(f"file {rel}: missing {want['contains']!r}")
                else:
                    if act_files.get(rel) != want:
                        failures.append(f"file {rel}: hash mismatch")

        # Everything else: deep subset on the inspected state.
        residual = {k: v for k, v in expected.items() if k != "files"}
        if residual:
            checked += 1
            if not _subset(residual, actual):
                failures.append("environment state does not contain the expected values")

        if checked == 0:
            return GraderResult.unmeasured_result(self.name, "no comparable state keys")
        passed = not failures
        return GraderResult(
            self.name, 1.0 if passed else 0.0, passed,
            details={"expected": expected, "observed": actual},
            failures=failures,
            evidence=[{"state": actual}],
        )
