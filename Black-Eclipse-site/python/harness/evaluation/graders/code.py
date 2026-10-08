"""Code-correctness grader.

The agent's code must actually execute. The task declares the checks (compile /
typecheck / lint / unit / integration / runtime / security); this grader runs them
in the environment and asserts the exit codes. It never evaluates code by asking a
model — when there is no runnable check the result is UNKNOWN, not a prose pass.
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


class CodeGrader(Grader):
    name = "code"

    def grade(self, ctx: GradeContext) -> GraderResult:
        checks = list(
            self.config.get("checks")
            or getattr(ctx.task, "metadata", {}).get("checks")
            or []
        )
        if not checks:
            return GraderResult.unmeasured_result(self.name, "task declares no executable checks")
        if ctx.environment is None or not hasattr(ctx.environment, "execute"):
            return GraderResult.unmeasured_result(self.name, "no executable environment")

        results: list[dict[str, Any]] = []
        failures: list[str] = []
        for check in checks:
            if isinstance(check, str):
                check = {"command": check.split(), "expect_exit": 0}
            command = check.get("command")
            if isinstance(command, str):
                command = command.split()
            expect = int(check.get("expect_exit", 0))
            kind = check.get("kind", "runtime")
            outcome = ctx.environment.execute("run", command=command, timeout=check.get("timeout", 60))
            ok = outcome.get("exit_code") == expect
            results.append({
                "kind": kind,
                "command": command,
                "exit_code": outcome.get("exit_code"),
                "expected": expect,
                "passed": ok,
            })
            if not ok:
                failures.append(
                    f"{kind} failed: exit {outcome.get('exit_code')} (expected {expect})"
                )

        passed_count = sum(1 for r in results if r["passed"])
        passed = passed_count == len(results)
        return GraderResult(
            self.name, passed_count / len(results) if results else 0.0, passed,
            details={"checks": results}, failures=failures,
            evidence=[{"checks": results}],
        )
