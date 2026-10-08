"""Tool accuracy grader.

Measures tool selection, argument correctness, sequencing, efficiency, failure
rate and recovery, plus forbidden-tool usage, from the captured trajectory. Every
signal is structured (tool.requested / tool.completed / tool.failed), so the grade
never depends on prose.
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    return expected == actual


def _sequence_accuracy(expected: list[str], actual: list[str]) -> float:
    """Longest-common-subsequence length / len(expected), order-correct."""
    if not expected:
        return 1.0
    m, n = len(expected), len(actual)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if expected[i - 1] == actual[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n] / m


class ToolGrader(Grader):
    name = "tool"

    def grade(self, ctx: GradeContext) -> GraderResult:
        expected_tools = list(getattr(ctx.task, "expected_tools", ()) or ())
        required = list(getattr(ctx.task, "required_tools", ()) or ())
        forbidden = set(getattr(ctx.task, "forbidden_tools", ()) or ())
        config = {**(ctx.config or {}), **self.config}
        min_sequence = float(config.get("min_sequence_accuracy", 1.0 if expected_tools else 0.0))
        min_args = float(config.get("min_argument_accuracy", 1.0))
        max_failure_rate = float(config.get("max_failure_rate", 1.0))

        calls = list(ctx.tool_calls)
        names = [c.get("name") for c in calls if c.get("name")]
        failures: list[str] = []

        if not calls and not expected_tools and not required:
            return GraderResult.unmeasured_result(self.name, "no tools expected and none recorded")

        # Forbidden tools.
        used_forbidden = sorted(set(names) & forbidden)
        for tool in used_forbidden:
            failures.append(f"forbidden tool used: {tool}")

        # Required tools.
        missing_required = [t for t in required if t not in names]
        for tool in missing_required:
            failures.append(f"required tool missing: {tool}")

        # Selection accuracy over required ∪ expected.
        target = list(dict.fromkeys(expected_tools or required))
        selected = [t for t in target if t in names]
        selection_accuracy = len(selected) / len(target) if target else 1.0

        sequence_accuracy = _sequence_accuracy(expected_tools, names)

        # Arguments: expected_tool_calls is a list of {name, args} subsets.
        expected_calls = config.get("expected_tool_calls") or getattr(ctx.task, "metadata", {}).get("expected_tool_calls") or []
        if expected_calls:
            matched = 0
            for spec in expected_calls:
                name, args = spec.get("name"), spec.get("args") or {}
                hit = any(c.get("name") == name and _subset(args, c.get("args") or {}) for c in calls)
                if hit:
                    matched += 1
                else:
                    failures.append(f"tool call {name} {args} not found")
            argument_accuracy = matched / len(expected_calls)
        else:
            argument_accuracy = 1.0

        # Efficiency: penalise extra calls beyond the expected count.
        expected_count = len(expected_calls) or len(expected_tools)
        if expected_count:
            extra = max(0, len(calls) - expected_count)
            efficiency = max(0.0, 1.0 - extra / max(1, expected_count))
        else:
            efficiency = 1.0

        failure_rate = (sum(1 for c in calls if c.get("status") == "failed") / len(calls)) if calls else 0.0

        # Recovery: a failed call whose tool later succeeds.
        recovery = True
        failed_names = {c["name"] for c in calls if c.get("status") == "failed"}
        succeeded_names = {c["name"] for c in calls if c.get("status") == "completed"}
        if failed_names:
            recovery = bool(failed_names & succeeded_names) or bool(succeeded_names)

        score = (
            0.35 * selection_accuracy
            + 0.25 * sequence_accuracy
            + 0.25 * argument_accuracy
            + 0.10 * efficiency
            + 0.05 * (1.0 - failure_rate)
        )
        passed = (
            not used_forbidden
            and not missing_required
            and sequence_accuracy >= min_sequence
            and argument_accuracy >= min_args
            and failure_rate <= max_failure_rate
        )
        details = {
            "tool_selection_accuracy": round(selection_accuracy, 4),
            "argument_accuracy": round(argument_accuracy, 4),
            "tool_sequence_accuracy": round(sequence_accuracy, 4),
            "tool_efficiency": round(efficiency, 4),
            "tool_failure_rate": round(failure_rate, 4),
            "recovery": recovery,
            "calls": names,
        }
        return GraderResult(self.name, score, passed, details=details, failures=failures,
                            evidence=[{"sequence": names}])
