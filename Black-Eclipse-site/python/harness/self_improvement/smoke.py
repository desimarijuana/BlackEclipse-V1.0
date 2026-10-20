"""Operator-run RSL smoke test — real conductor, real evaluator, throwaway data.

This is intentionally NOT a production run and NOT a mock of the loop:

* a disposable git repository contains a failing owning test and the candidate
  operation that fixes it; the conductor verifies the change in a real worktree;
* a second, surface candidate runs the same scripted evaluation baseline/candidate
  path and records an honest MEASURED decision (likely a rejection — the scripted
  tier cannot improve on a fixed script by narrowing a snapshot);
* both candidates, attempts and experiments live in a temp `agent-memory.db`;
  the developer's checkout and databases are never touched.

Run it with `npm run rsl:smoke`.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..code.evolution_store import EvolutionStore
from ..evaluation.store import EvaluationStore
from ..persistence import AgentMemoryStore
from .config import RSLConfig
from .loop import RSLLoop
from .models import HarnessSnapshot


class _Ctx:
    """The minimal ToolContext the worktree verifier reads."""

    def __init__(self, store: AgentMemoryStore, run_id: str) -> None:
        from ..code.store import CodeWorkspaceStore
        from ..code.verify import VerificationLedger

        self.run_id = run_id
        self.memory_store = store
        self.code_store = CodeWorkspaceStore(store)
        self.code_ledger = VerificationLedger(run_id)
        self.workspace = None
        self.autonomy = "approve_external"


class _SmokeService:
    """The narrow service surface the conductor needs for a smoke run."""

    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self._rsl_loop: Any = None

    def evolution_store(self) -> EvolutionStore:
        return EvolutionStore(self.store)

    def evolution_context(self, *, run_id: str) -> _Ctx:
        return _Ctx(self.store, run_id)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _git_repo(root: Path) -> None:
    _write(root / "python" / "harness" / "__init__.py", "")
    _write(root / "python" / "harness" / "rsl_smoke_target.py", "VALUE = 1\n")
    _write(
        root / "python" / "tests" / "conftest.py",
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n",
    )
    _write(
        root / "python" / "tests" / "test_rsl_smoke_target.py",
        "from harness.rsl_smoke_target import VALUE\n"
        "\n"
        "def test_value():\n"
        "    assert VALUE == 2\n",
    )
    _write(root / ".gitignore", ".black-eclipse/\n")
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "rsl-smoke@example.invalid"],
        ["git", "config", "user.name", "RSL Smoke"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "rsl smoke fixture"],
    ):
        subprocess.run(argv, cwd=root, env=env, check=True, capture_output=True)


def _surface_config() -> dict[str, Any]:
    base = HarnessSnapshot(
        systemPrompt="You are Eclipse.", toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    candidate = HarnessSnapshot(
        systemPrompt="You are Eclipse, smoke candidate.",
        toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    return {
        "base": base.to_dict(),
        "snapshot": candidate.to_dict(),
        "dataset": "benchmark_v1",
        "taskIds": ["core.echo.001"],
        "split": "validation",
        "targetDimension": "task_success",
        "trials": 1,
        "seed": 7,
        "baselineRunId": None,
    }


async def run_smoke() -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="be-rsl-smoke-"))
    previous_root = os.environ.get("BLACK_ECLIPSE_CODE_ROOT")
    os.environ["BLACK_ECLIPSE_CODE_ROOT"] = str(root)
    store = AgentMemoryStore(str(root / "agent-memory.db"))
    try:
        _git_repo(root)
        evolution = EvolutionStore(store)
        eval_store = EvaluationStore(store)
        service = _SmokeService(store)
        loop = RSLLoop(
            service=service,
            config=RSLConfig(mode="verify", trials=1, max_experiments_per_day=3),
        )
        service._rsl_loop = loop

        code_candidate = evolution.save_candidate({
            "signature": "rsl-smoke-code",
            "sourceCategory": "timeout",
            "observedCount": 3,
            "problemStatement": (
                "RSL smoke: the smoke target still carries the old value, so its "
                "owning test fails."
            ),
            "targetPath": "python/harness/rsl_smoke_target.py",
            "proposedOps": [{
                "op": "replace",
                "path": "python/harness/rsl_smoke_target.py",
                "old": "VALUE = 1",
                "new": "VALUE = 2",
                "reason": "make the owning test pass",
            }],
            "status": "proposed",
        })
        code_result = await loop.tick()
        code_after = evolution.get_candidate(code_candidate["id"]) or {}
        code_run = eval_store.get_run(str(code_result.get("runId") or "")) or {}
        if code_after.get("status") != "evaluated_ok":
            raise AssertionError(
                f"code candidate did not pass: {code_after.get('status')}; "
                f"attempts={evolution.list_attempts(code_candidate['id'])}"
            )
        if code_result.get("benchmark") != "UNMEASURED":
            raise AssertionError(f"code benchmark must be UNMEASURED: {code_result}")
        if (code_run.get("metadata") or {}).get("testsPassed") is not True:
            raise AssertionError("code experiment did not record a passing owning test")

        surface_candidate = evolution.save_candidate({
            "signature": "rsl-smoke-surface",
            "sourceCategory": "operator",
            "observedCount": 1,
            "problemStatement": "RSL smoke: a bounded surface snapshot benchmark.",
            "subjectType": "surface",
            "surfaceConfig": _surface_config(),
            "status": "proposed",
        })
        surface_result = await loop.tick()
        surface_after = evolution.get_candidate(surface_candidate["id"]) or {}
        surface_run = eval_store.get_run(str(surface_result.get("runId") or "")) or {}
        surface_meta = surface_run.get("metadata") or {}
        if surface_result.get("benchmark") != "MEASURED":
            raise AssertionError(f"surface benchmark was not measured: {surface_result}")
        if surface_meta.get("surface") is not True:
            raise AssertionError("surface experiment metadata is incomplete")
        if not surface_meta.get("baselineRunId"):
            raise AssertionError("surface experiment did not record its baseline")
        if surface_after.get("status") not in {"evaluated_ok", "evaluated_bad"}:
            raise AssertionError(f"surface candidate has no decision: {surface_after.get('status')}")
        attempts = evolution.list_attempts(surface_candidate["id"])
        if not attempts:
            raise AssertionError("surface experiment did not record an attempt")

        status = loop.status()
        return {
            "code": {
                "candidateId": code_candidate["id"],
                "status": code_after.get("status"),
                "runId": code_result.get("runId"),
                "benchmark": code_result.get("benchmark"),
                "decision": code_result.get("decision"),
            },
            "surface": {
                "candidateId": surface_candidate["id"],
                "status": surface_after.get("status"),
                "runId": surface_result.get("runId"),
                "benchmark": surface_result.get("benchmark"),
                "decision": surface_result.get("decision"),
                "baselineRunId": surface_meta.get("baselineRunId"),
            },
            "budget": status,
        }
    finally:
        try:
            store.close()
        finally:
            if previous_root is None:
                os.environ.pop("BLACK_ECLIPSE_CODE_ROOT", None)
            else:
                os.environ["BLACK_ECLIPSE_CODE_ROOT"] = previous_root
            shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    try:
        result = asyncio.run(run_smoke())
    except Exception as exc:  # noqa: BLE001 - the CLI reports, never hides
        print(f"RSL smoke: FAIL — {type(exc).__name__}: {exc}")
        return 1
    code = result["code"]
    surface = result["surface"]
    print("RSL smoke: PASS")
    print(
        f"  code:    {code['candidateId']} -> {code['status']} "
        f"({code['benchmark']}, {code['decision']}) run={code['runId']}"
    )
    print(
        f"  surface: {surface['candidateId']} -> {surface['status']} "
        f"({surface['benchmark']}, {surface['decision']}) run={surface['runId']} "
        f"baseline={surface['baselineRunId']}"
    )
    budget = result["budget"]
    print(
        f"  budget:  {budget.get('startedToday')}/"
        f"{budget.get('maxExperimentsPerDay')} today; "
        f"mode={budget.get('mode')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
