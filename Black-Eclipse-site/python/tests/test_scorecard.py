"""The self-build scorecard (Phase 22 / S6).

The tests pin the two rules that matter: a missing dimension is `UNKNOWN`, never
`0`, and a build is a run with a `session.created` boundary (a Code task or a
chat build). `project_root` narrows the card to one project.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from harness.code.scorecard import UNKNOWN, build_scorecard
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage


def _store(tmp_path):
    return AgentMemoryStore(str(tmp_path / "agent-memory.db"))


def _run(store, run_id="r1", *, agent="code-agent", steps=3, tokens=100, created=None):
    store.create_run(run_id, agent, {"query": "build it"})
    if created is not None:
        store._db.execute(
            "UPDATE HarnessRun SET createdAt=? WHERE id=?", (created.isoformat(), run_id),
        )
        store._db.commit()
    store.update_run(run_id, modelSteps=steps, totalTokens=tokens, provider="p", model="m")
    return RunLineage(store)


def test_a_chat_build_counts_and_the_project_filter_narrows_it(tmp_path):
    from harness.code.store import CodeWorkspaceStore

    store = _store(tmp_path)
    try:
        for run_id, folder in (("chat_a", "a"), ("chat_b", "b")):
            lineage = _run(store, run_id, agent="eclipse-agent")
            lineage.save_checkpoint(run_id, "session.created", {"goal": run_id})
            (tmp_path / folder).mkdir(exist_ok=True)
            CodeWorkspaceStore(store).save_workspace(
                f"ws_{folder}", str(tmp_path / folder / ".black-eclipse" / "code-workspaces" / f"ws_{folder}"),
                "HEAD", "worktree", run_id=run_id, checkout_root=str(tmp_path / folder),
            )

        assert build_scorecard(store)["metrics"]["builds"] == 2
        scoped = build_scorecard(store, project_root=str(tmp_path / "a"))
        assert scoped["metrics"]["builds"] == 1
        assert scoped["projectRoot"] == str(tmp_path / "a")
    finally:
        store.close()


def test_an_empty_store_reports_unknown_not_zero(tmp_path):
    store = _store(tmp_path)
    try:
        card = build_scorecard(store)
        metrics = card["metrics"]
        assert metrics["builds"] == 0
        assert metrics["successRate"] == UNKNOWN
        assert metrics["averageSteps"] == UNKNOWN
        assert metrics["totalTokens"] == UNKNOWN
        assert metrics["costUsd"] == UNKNOWN
        assert "humanEditsAfterLanding" in card["unmeasured"]
    finally:
        store.close()


def test_a_landed_first_pass_build_is_counted_once(tmp_path):
    store = _store(tmp_path)
    try:
        lineage = _run(store)
        lineage.save_checkpoint("r1", "task.created", {"workspaceId": "w"})
        lineage.save_checkpoint("r1", "session.created", {"goal": "x"})
        lineage.save_checkpoint("r1", "patch.applied", {"files": ["a.py"]})
        lineage.save_checkpoint("r1", "land.verified", {"ok": True, "full": True})
        lineage.save_checkpoint("r1", "land.verified", {"ok": False, "full": True})
        lineage.save_checkpoint("r1", "land.promoted", {"rollbackId": "rb"})
        card = build_scorecard(store)
        metrics = card["metrics"]
        assert metrics["builds"] == 1
        assert metrics["checked"] == 1
        assert metrics["firstPassChecks"] == 1
        assert metrics["landed"] == 1
        assert metrics["successRate"] == 1.0
        assert metrics["firstPassRate"] == 1.0
        assert metrics["averageSteps"] == 3.0
        assert metrics["totalTokens"] == 100
        assert card["byModel"][0]["model"] == "m"
        assert card["byModel"][0]["builds"] == 1
    finally:
        store.close()


def test_a_rollback_is_counted_and_a_failed_first_check_is_not_a_pass(tmp_path):
    store = _store(tmp_path)
    try:
        lineage = _run(store, "r2")
        lineage.save_checkpoint("r2", "session.created", {"goal": "x"})
        lineage.save_checkpoint("r2", "land.verified", {"ok": False, "full": True})
        lineage.save_checkpoint("r2", "land.promoted", {"rollbackId": "rb"})
        lineage.save_checkpoint("r2", "land.rolled_back", {"rollbackId": "rb"})
        metrics = build_scorecard(store)["metrics"]
        assert metrics["landed"] == 1
        assert metrics["rolledBack"] == 1
        assert metrics["firstPassChecks"] == 0
        assert metrics["rollbackRate"] == 1.0
    finally:
        store.close()


def test_non_code_runs_and_old_runs_are_ignored(tmp_path):
    store = _store(tmp_path)
    try:
        old = datetime.now(timezone.utc) - timedelta(days=90)
        _run(store, "chat", agent="eclipse-agent")
        lineage = _run(store, "old", created=old)
        lineage.save_checkpoint("old", "session.created", {"goal": "x"})
        card = build_scorecard(store, window_days=30)
        assert card["metrics"]["builds"] == 0
        assert card["metrics"]["runs"] == 0
    finally:
        store.close()
