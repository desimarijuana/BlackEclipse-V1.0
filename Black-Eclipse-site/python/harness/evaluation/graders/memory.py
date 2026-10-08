"""Memory-capability grader.

Tests both directions: the agent must REMEMBER what it should and must NOT
remember what it should not. It reads the environment's memory state and the final
answer, so "created the right memory" and "suppressed the wrong one" are both
gradeable.
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


class MemoryGrader(Grader):
    name = "memory"

    def grade(self, ctx: GradeContext) -> GraderResult:
        expected = dict(getattr(ctx.task, "expected_state", {}).get("memory") or {})
        config = dict(self.config.get("memory") or getattr(ctx.task, "metadata", {}).get("memory") or {})
        forbidden = dict(config.get("forbidden") or {})
        expect_recall = list(config.get("expect_recall") or [])
        stale = list(config.get("stale") or [])

        env_state = ctx.env_state or {}
        entries = dict(env_state.get("entries") or {}) if isinstance(env_state, dict) else {}

        if not expected and not forbidden and not expect_recall and not entries:
            return GraderResult.unmeasured_result(self.name, "no memory state to grade")

        failures: list[str] = []

        # Correct creation.
        for key, value in expected.items():
            if entries.get(key) != value:
                failures.append(f"expected memory {key}={value!r}, got {entries.get(key)!r}")
        # Correct suppression.
        for key, value in forbidden.items():
            if key in entries and entries.get(key) == value:
                failures.append(f"must not remember {key}={value!r}")
        # Retrieval: the recalled value must appear in the answer.
        for key in expect_recall:
            want = expected.get(key) or entries.get(key)
            if want is not None and str(want) not in (ctx.final_output or ""):
                failures.append(f"expected {key} to be recalled in the answer")
        # Stale memories must not be surfaced as current.
        for key in stale:
            if key in (ctx.final_output or ""):
                failures.append(f"stale memory {key} was surfaced")

        passed = not failures
        checks = len(expected) + len(forbidden) + len(expect_recall) + len(stale)
        score = 1.0 - len(failures) / checks if checks else 1.0
        return GraderResult(self.name, score, passed,
                            details={"entries": entries, "expected": expected, "forbidden": forbidden},
                            failures=failures)
