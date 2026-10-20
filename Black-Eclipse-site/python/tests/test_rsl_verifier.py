"""RSL R4 — the surface benchmark path is the only measured one."""

from __future__ import annotations

import pytest

from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.verifier import verify_surface


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _task() -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": "rsl.surface",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "say READY"},
        "expected_output": {"equals": "READY"},
        "metadata": {"agent_script": [{"type": "final", "content": "READY"}]},
    })


@pytest.mark.asyncio
async def test_surface_benchmark_is_measured_and_persisted(store):
    base = HarnessSnapshot(
        systemPrompt="You are Eclipse.", toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    candidate = HarnessSnapshot(
        systemPrompt="You are Eclipse, candidate.", toolNames=(),
        maxSteps=8, maxToolCalls=8,
    )
    eval_store = EvaluationStore(store)
    result = await verify_surface(
        store=store,
        snapshot=candidate,
        base=base,
        tasks=[_task()],
        baseline_metrics={"aggregates": {"task_success": 0.0, "safety_score": 1.0}},
        target_dimension="task_success",
        proposal_id="evo_surface",
        eval_store=eval_store,
        trials=1,
        seed=7,
        metadata={"source": "test"},
    )

    assert result["benchmark"] == "MEASURED"
    assert result["decision"] == "benchmark"
    assert result["measured"] == 1
    assert result["decisionRecord"]["accepted"] is True
    assert result["runId"]

    run = eval_store.get_run(result["runId"])
    assert run is not None
    assert run["metadata"]["kind"] == "rsl"
    assert run["metadata"]["proposalId"] == "evo_surface"
    assert run["metadata"]["benchmark"] == "MEASURED"
    assert run["metadata"]["accepted"] is True
    assert run["metadata"]["measured"] == 1
    assert run["config"]["snapshotDigest"] == candidate.sourceDigest


class _Ctx:
    def __init__(self, store, run_id: str) -> None:
        from harness.code.store import CodeWorkspaceStore
        from harness.code.verify import VerificationLedger

        self.run_id = run_id
        self.memory_store = store
        self.code_store = CodeWorkspaceStore(store)
        self.code_ledger = VerificationLedger(run_id)
        self.workspace = None
        self.autonomy = "approve_external"


def _git_fixture(tmp_path, monkeypatch):
    import subprocess
    from pathlib import Path

    root = Path(tmp_path) / "repo"
    files = {
        "python/harness/__init__.py": "",
        "python/harness/rsl_fixture.py": "VALUE = 1\n",
        "python/tests/conftest.py": (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        ),
        "python/tests/test_rsl_fixture.py": (
            "from harness.rsl_fixture import VALUE\n\n"
            "def test_value():\n"
            "    assert VALUE == 2\n"
        ),
        ".gitignore": ".black-eclipse/\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "fixture"],
    ):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    return root


def test_code_verifier_runs_the_owning_test_in_a_real_worktree(tmp_path, monkeypatch):
    import shutil

    from harness.code.evolution_store import EvolutionStore
    from harness.skills.permissions import Actor
    from harness.self_improvement.verifier import verify_code

    repo = _git_fixture(tmp_path, monkeypatch)
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        evolution = EvolutionStore(memory)
        candidate = evolution.save_candidate({
            "signature": "rsl-code-verifier-fixture",
            "sourceCategory": "timeout",
            "observedCount": 3,
            "problemStatement": "the fixture test still expects the old value",
            "targetPath": "python/harness/rsl_fixture.py",
            "proposedOps": [{
                "op": "replace", "path": "python/harness/rsl_fixture.py",
                "old": "VALUE = 1", "new": "VALUE = 2", "reason": "fixture",
            }],
            "status": "proposed",
        })
        result = verify_code(
            memory, candidate["id"],
            ctx=_Ctx(memory, "rsl-code-verifier"),
            actor=Actor(id="rsl", operator=False, autonomy="edit_verify"),
        )
        assert result["passed"] is True, result
        assert result["benchmark"] == "UNMEASURED"
        assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"
        attempts = evolution.list_attempts(candidate["id"])
        assert attempts and attempts[-1]["outcome"] == "success"
    finally:
        memory.close()
        shutil.rmtree(repo / ".black-eclipse", ignore_errors=True)
