"""Acceptance fixtures for self-build features (Phase 22 / S6).

This is deliberately NOT a model benchmark and does NOT claim the agent can
build these from scratch. It is the acceptance half of that claim: for each
self-build capability, the exact files and contracts that must exist after a
candidate change. Run it against a worktree to grade a candidate; run it against
the repo as a regression check.

The human diff grade is recorded as ``UNKNOWN`` - the eval never invents a
quality score. Commands are OFF by default (a release run can turn them on);
a skipped command is reported as skipped, never as a pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# ── Contracts ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    id: str
    kind: str  # "files_exist" | "file_contains" | "command"
    paths: tuple[str, ...] = ()
    needles: tuple[tuple[str, str], ...] = ()  # (path, required substring)
    argv: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelfBuildTask:
    id: str
    goal: str
    checks: tuple[Check, ...]
    human_grade: str = "UNKNOWN"


# ── Fixtures: the acceptance contract for each shipped capability ───────────

TASKS: tuple[SelfBuildTask, ...] = (
    SelfBuildTask(
        "project-memory",
        "Load the repository's own rules into a code turn.",
        (
            Check("files", "files_exist", paths=(
                "python/harness/code/project_memory.py",
                "python/tests/test_project_memory.py",
            )),
            Check("api", "file_contains", needles=(
                ("python/harness/code/project_memory.py", "def load_project_rules"),
                ("python/harness/code/project_memory.py", "They are CONTEXT"),
                ("python/harness/graph_context.py", "load_project_rules"),
            )),
        ),
    ),
    SelfBuildTask(
        "build-session",
        "Give a build a durable session with a budget ladder.",
        (
            Check("files", "files_exist", paths=(
                "python/harness/code/session.py",
                "python/tests/test_build_session.py",
            )),
            Check("api", "file_contains", needles=(
                ("python/harness/code/session.py", "BUDGET_LADDER"),
                ("python/harness/code/session.py", "def derive_phase"),
                ("python/harness/schemas.py", "maxSteps"),
            )),
        ),
    ),
    SelfBuildTask(
        "maintenance-door",
        "Change an authority file offline, with a rollback.",
        (
            Check("files", "files_exist", paths=(
                "python/harness/code/maintenance.py",
                "scripts/self-maintenance.js",
                "python/tests/test_maintenance.py",
            )),
            Check("api", "file_contains", needles=(
                ("python/harness/code/maintenance.py", "def run_maintenance"),
                ("python/harness/code/maintenance.py", "AUTHORITY_PATHS"),
                ("python/harness/code/selfhost.py", "def plan_landing"),
            )),
        ),
    ),
    SelfBuildTask(
        "land-pipeline",
        "Prove a change with the project's own checks before landing.",
        (
            Check("files", "files_exist", paths=(
                "python/harness/code/land.py",
                "python/tests/test_land.py",
            )),
            Check("api", "file_contains", needles=(
                ("python/harness/code/land.py", "def run_land_plan"),
                ("python/harness/code/land.py", "def docs_obligation"),
                ("python/harness/routers/code.py", "/land/verify"),
            )),
        ),
    ),
    SelfBuildTask(
        "builder-surface",
        "Review a build in one place, with per-file changes and a gate.",
        (
            Check("files", "files_exist", paths=(
                "src/lib/code/diff-sections.ts",
                "src/components/screens/code/land-checks.tsx",
                "src/components/screens/code/scorecard-strip.tsx",
            )),
            Check("api", "file_contains", needles=(
                ("src/lib/code/diff-sections.ts", "export function splitUnifiedDiff"),
                ("src/components/screens/code/land-checks.tsx", "verifyLanding"),
                ("src/components/screens/code/task-detail.tsx", "LandChecks"),
            )),
        ),
    ),
    SelfBuildTask(
        "self-build-scorecard",
        "Measure self-builds honestly, per model, without faking a number.",
        (
            Check("files", "files_exist", paths=(
                "python/harness/code/scorecard.py",
                "python/tests/test_scorecard.py",
                "src/app/api/code/scorecard/route.ts",
            )),
            Check("api", "file_contains", needles=(
                ("python/harness/code/scorecard.py", "def build_scorecard"),
                ("python/harness/code/scorecard.py", '"byModel"'),
                ("python/harness/code/scorecard.py", 'UNKNOWN = "UNKNOWN"'),
            )),
        ),
    ),
)


# ── Runner ──────────────────────────────────────────────────────────────────


def _check_task(
    task: SelfBuildTask, root: Path, *, run_commands: bool,
    runner: Optional[Callable[[list[str], Path], int]] = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for check in task.checks:
        if check.kind == "files_exist":
            missing = [path for path in check.paths if not (root / path).is_file()]
            results.append({
                "id": check.id,
                "status": "failed" if missing else "passed",
                "detail": f"missing: {', '.join(missing)}" if missing else "all files present",
            })
            continue
        if check.kind == "file_contains":
            missing: list[str] = []
            for path, needle in check.needles:
                target = root / path
                try:
                    text = target.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    missing.append(f"{path} (missing)")
                    continue
                if needle not in text:
                    missing.append(f"{path} lacks {needle!r}")
            results.append({
                "id": check.id,
                "status": "failed" if missing else "passed",
                "detail": "; ".join(missing) if missing else "contract present",
            })
            continue
        if check.kind == "command":
            if not run_commands:
                results.append({
                    "id": check.id, "status": "skipped",
                    "detail": "commands are off by default; pass --commands",
                })
                continue
            code = (runner or _run_command)(list(check.argv), root)
            results.append({
                "id": check.id,
                "status": "passed" if code == 0 else "failed",
                "detail": f"exit {code}",
            })
            continue
        results.append({
            "id": check.id, "status": "failed",
            "detail": f"unknown check kind {check.kind!r}",
        })
    passed = all(item["status"] != "failed" for item in results)
    return {
        "id": task.id,
        "goal": task.goal,
        "passed": passed,
        "checks": results,
        # The quality of the change is a human judgement, not a number here.
        "humanGrade": task.human_grade,
    }


def _run_command(argv: list[str], root: Path) -> int:
    try:
        return subprocess.run(
            argv, cwd=str(root), capture_output=True, text=True,
            timeout=900, shell=False,
        ).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def run_selfbuild_eval(
    root: Path | str,
    *,
    tasks: tuple[SelfBuildTask, ...] = TASKS,
    run_commands: bool = False,
    runner: Optional[Callable[[list[str], Path], int]] = None,
) -> dict[str, Any]:
    """Grade a worktree against the acceptance fixtures. Deterministic."""
    base = Path(root)
    results = [
        _check_task(task, base, run_commands=run_commands, runner=runner)
        for task in tasks
    ]
    passed = sum(1 for item in results if item["passed"])
    return {
        "root": str(base),
        "tasks": results,
        "passed": passed,
        "total": len(results),
        "passRate": round(passed / len(results), 3) if results else "UNKNOWN",
        "unmeasured": ["humanGrade"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.code.selfbuild_eval")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--commands", action="store_true")
    args = parser.parse_args(argv)
    report = run_selfbuild_eval(args.root, run_commands=args.commands)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Self-build acceptance: {report['passed']}/{report['total']} passed")
        for task in report["tasks"]:
            mark = "PASS" if task["passed"] else "FAIL"
            print(f"  [{mark}] {task['id']}: {task['goal']}")
            for check in task["checks"]:
                if check["status"] != "passed":
                    print(f"        {check['status']}: {check['detail']}")
    return 0 if report["passed"] == report["total"] else 2


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "Check",
    "SelfBuildTask",
    "TASKS",
    "main",
    "run_selfbuild_eval",
]
