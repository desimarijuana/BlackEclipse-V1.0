"""Git subsystem — mutations, recovery, conflicts, safety and advanced features.

Every test runs against an ISOLATED temporary repository. Failure-injection tests
(merge/rebase conflicts, non-fast-forward, detached HEAD, missing remote) assert
the STRUCTURED error code, the persisted operation state, and that no work is
silently discarded.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.git import readers, recovery, state
from harness.git.service import GitService

from git_helpers import commit_all, git, make_bare_remote, make_repo, write


@pytest.fixture()
def svc(tmp_path):
    repo = make_repo(tmp_path / "repo")
    return GitService(), repo


# ── Stage / commit ────────────────────────────────────────────────────────────────

def test_stage_only_selected_files(svc):
    service, repo = svc
    write(repo.root, "keep.txt", "keep\n")
    write(repo.root, "skip.txt", "skip\n")
    outcome = service.stage(repo, ["keep.txt"])
    assert outcome.success
    staged = service._staged_paths(repo)
    assert staged == ["keep.txt"]


def test_unstage_restores_index(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    service.stage(repo, ["f.txt"])
    outcome = service.unstage(repo, ["f.txt"])
    assert outcome.success
    assert service._staged_paths(repo) == []


def test_commit_requires_staged_changes(svc):
    service, repo = svc
    outcome = service.commit(repo, "nothing")
    assert outcome.success is False
    assert outcome.error["code"] in ("NOTHING_STAGED", "NOTHING_TO_COMMIT")


def test_commit_then_status_clean(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    service.stage(repo, ["f.txt"])
    outcome = service.commit(repo, "add f")
    assert outcome.success
    assert outcome.result["commit"]
    assert service.status(repo)["clean"] is True


def test_amend_updates_head(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    service.stage(repo, ["f.txt"])
    first = service.commit(repo, "first").result["commit"]
    outcome = service.amend(repo, message="amended")
    assert outcome.success
    assert outcome.result["commit"] != first


def test_commit_blocks_on_secret_and_allows_with_override(svc):
    service, repo = svc
    write(repo.root, ".env", "OPENAI_API_KEY=sk-abcdefghijklmnop\n")
    service.stage(repo, [".env"])
    blocked = service.commit(repo, "add env")
    assert blocked.success is False
    assert blocked.error["code"] == "SECRET_DETECTED"
    allowed = service.commit(repo, "add env", allow_secrets=True)
    assert allowed.success


def test_commit_warns_on_large_artifact(svc):
    service, repo = svc
    write(repo.root, "node_modules/pkg/index.js", "x\n")
    service.stage(repo, ["node_modules/pkg/index.js"])
    outcome = service.commit(repo, "add dep")
    assert any(w.get("kind") == "artifact" for w in outcome.warnings)


# ── Branches / checkout safety ───────────────────────────────────────────────────────

def test_create_branch_and_checkout(svc):
    service, repo = svc
    outcome = service.create_branch(repo, "feature", checkout=True)
    assert outcome.success
    assert service.discover(repo.root).branch == "feature"


def test_checkout_refuses_to_overwrite_local_changes(svc):
    service, repo = svc
    write(repo.root, "f.txt", "base\n")
    commit_all(repo.root, "add f")
    service.create_branch(repo, "other", checkout=True)
    write(repo.root, "f.txt", "other work\n")
    commit_all(repo.root, "other change")
    service.checkout(repo, "main")
    write(repo.root, "f.txt", "uncommitted local edit\n")
    outcome = service.checkout(repo, "other")
    assert outcome.success is False
    assert outcome.error["code"] in ("CHECKOUT_OVERWRITE",)
    assert outcome.error.get("safe") is False
    # The local edit is still there — nothing was discarded.
    assert "uncommitted" in (repo.root / "f.txt").read_text(encoding="utf-8")


def test_delete_branch(svc):
    service, repo = svc
    service.create_branch(repo, "temp", checkout=False)
    outcome = service.delete_branch(repo, "temp")
    assert outcome.success


def test_delete_unmerged_branch_needs_force(svc):
    service, repo = svc
    service.create_branch(repo, "unmerged", checkout=True)
    write(repo.root, "x.txt", "x\n")
    commit_all(repo.root, "x")
    service.checkout(repo, "main")
    safe = service.delete_branch(repo, "unmerged", force=False)
    assert safe.success is False
    forced = service.delete_branch(repo, "unmerged", force=True)
    assert forced.success


# ── Merge / conflict engine ────────────────────────────────────────────────────────────

def _conflict(svc):
    service, repo = svc
    write(repo.root, "conflict.txt", "base\n")
    commit_all(repo.root, "base")
    service.create_branch(repo, "other", checkout=True)
    write(repo.root, "conflict.txt", "other\n")
    commit_all(repo.root, "other")
    service.checkout(repo, "main")
    write(repo.root, "conflict.txt", "main\n")
    commit_all(repo.root, "main")
    return service, repo


def test_merge_fast_forward_clean(svc):
    service, repo = svc
    service.create_branch(repo, "feature", checkout=True)
    write(repo.root, "new.txt", "new\n")
    commit_all(repo.root, "feature work")
    service.checkout(repo, "main")
    outcome = service.merge(repo, "feature")
    assert outcome.success
    assert (repo.root / "new.txt").exists()


def test_merge_conflict_is_structured_and_stateful(svc):
    service, repo = _conflict(svc)
    outcome = service.merge(repo, "other")
    assert outcome.success is False
    assert outcome.error["code"] == "MERGE_CONFLICT"
    assert "conflict.txt" in outcome.error["files"]
    active = state.active_operation(repo)
    assert active is not None and active.operation == "merge"
    assert active.conflicts is True


def test_conflict_blocks_are_parsed(svc):
    service, repo = _conflict(svc)
    service.merge(repo, "other")
    blocks = state.read_conflicts(repo, "conflict.txt")
    assert blocks
    assert "main" in blocks[0]["ours"] or "main" in blocks[0]["theirs"]


def test_resolve_and_continue_merge(svc):
    service, repo = _conflict(svc)
    service.merge(repo, "other")
    outcome = service.resolve_conflict(repo, "conflict.txt", "resolved\n")
    assert outcome.success
    cont = service.merge_continue(repo)
    assert cont.success
    assert state.active_operation(repo) is None


def test_merge_abort_restores_pre_merge(svc):
    service, repo = _conflict(svc)
    before = service.status(repo)["branch"]
    service.merge(repo, "other")
    outcome = service.merge_abort(repo)
    assert outcome.success
    assert state.active_operation(repo) is None
    assert service.status(repo)["branch"] == before


def test_resolve_conflict_refuses_escape(svc):
    service, repo = _conflict(svc)
    outcome = service.resolve_conflict(repo, "../outside.txt", "x")
    assert outcome.success is False
    assert outcome.error["code"] == "INVALID_ARGUMENT"


# ── Rebase ─────────────────────────────────────────────────────────────────────────────

def test_rebase_conflict_is_structured(svc):
    service, repo = _conflict(svc)
    outcome = service.rebase(repo, "other")
    assert outcome.success is False
    assert outcome.error["code"] == "REBASE_CONFLICT"
    active = state.active_operation(repo)
    assert active is not None and active.operation == "rebase"
    assert active.can_skip is True


def test_rebase_abort(svc):
    service, repo = _conflict(svc)
    service.rebase(repo, "other")
    outcome = service.rebase_abort(repo)
    assert outcome.success
    assert state.active_operation(repo) is None


def test_rebase_clean(svc):
    service, repo = svc
    write(repo.root, "base.txt", "base\n")
    commit_all(repo.root, "base")
    service.create_branch(repo, "feature", checkout=True)
    write(repo.root, "feat.txt", "feature\n")
    commit_all(repo.root, "feature")
    service.checkout(repo, "main")
    write(repo.root, "main.txt", "main\n")
    commit_all(repo.root, "main")
    service.checkout(repo, "feature")
    outcome = service.rebase(repo, "main")
    assert outcome.success


# ── Cherry-pick / revert ─────────────────────────────────────────────────────────────────

def test_cherry_pick_copies_commit(svc):
    service, repo = svc
    write(repo.root, "base.txt", "base\n")
    commit_all(repo.root, "base")
    service.create_branch(repo, "feature", checkout=True)
    write(repo.root, "picked.txt", "picked\n")
    commit_all(repo.root, "to pick")
    sha = readers.log(repo, max_count=1)["commits"][0]["sha"]
    service.checkout(repo, "main")
    outcome = service.cherry_pick(repo, [sha])
    assert outcome.success
    assert (repo.root / "picked.txt").exists()


def test_revert_creates_inverse_commit(svc):
    service, repo = svc
    write(repo.root, "revert.txt", "content\n")
    service.stage(repo, ["revert.txt"])
    service.commit(repo, "add revert")
    sha = readers.log(repo, max_count=1)["commits"][0]["sha"]
    outcome = service.revert(repo, [sha])
    assert outcome.success
    assert not (repo.root / "revert.txt").exists()


# ── Reset (destructive) ──────────────────────────────────────────────────────────────────

def test_reset_hard_is_classified_destructive(svc):
    from harness.git import safety

    service, repo = svc
    assert safety.assess_risk("reset", hard_reset=True).risk == "destructive"
    assert safety.assess_risk("reset").risk == "dangerous"


def test_reset_soft_keeps_working_tree(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    commit_all(repo.root, "add f")
    outcome = service.reset(repo, "soft", target="HEAD~1")
    assert outcome.success
    assert (repo.root / "f.txt").exists()


def test_reset_hard_discards_changes(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    commit_all(repo.root, "add f")
    write(repo.root, "f.txt", "modified\n")
    outcome = service.reset(repo, "hard", target="HEAD")
    assert outcome.success
    assert (repo.root / "f.txt").read_text(encoding="utf-8") == "x\n"


# ── Stash ───────────────────────────────────────────────────────────────────────────────

def test_stash_push_list_apply_pop(svc):
    service, repo = svc
    write(repo.root, "f.txt", "work\n")
    service.commit(repo, "init f") if service._staged_paths(repo) else None
    commit_all(repo.root, "add f")
    write(repo.root, "f.txt", "stashed change\n")
    pushed = service.stash_push(repo, message="wip")
    assert pushed.success
    assert service.status(repo)["clean"] is True
    pop = service.stash_apply(repo, "stash@{0}", pop=True)
    assert pop.success
    assert "stashed change" in (repo.root / "f.txt").read_text(encoding="utf-8")


def test_stash_include_untracked(svc):
    service, repo = svc
    write(repo.root, "brandnew.txt", "new\n")
    pushed = service.stash_push(repo, include_untracked=True)
    assert pushed.success
    assert not (repo.root / "brandnew.txt").exists()


# ── Tags ─────────────────────────────────────────────────────────────────────────────────

def test_tag_create_and_delete(svc):
    service, repo = svc
    outcome = service.tag_create(repo, "v1.0.0", message="release")
    assert outcome.success
    assert any(t["name"] == "v1.0.0" for t in readers.tags(repo)["tags"])
    deleted = service.tag_delete(repo, ["v1.0.0"])
    assert deleted.success


# ── Remotes / fetch / push (local bare remote) ─────────────────────────────────────────────

def test_push_and_fetch_to_bare_remote(svc, tmp_path):
    service, repo = svc
    bare = make_bare_remote(tmp_path)
    service.remote_add(repo, "origin", str(bare))
    outcome = service.push(repo, remote="origin", branch="main", set_upstream=True)
    assert outcome.success
    # A new clone sees the commit.
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    assert (clone / "README.md").exists()


def test_non_fast_forward_is_structured(svc, tmp_path):
    service, repo = svc
    bare = make_bare_remote(tmp_path)
    service.remote_add(repo, "origin", str(bare))
    service.push(repo, remote="origin", branch="main", set_upstream=True)
    # Advance the remote from a second clone, then make a divergent local commit.
    clone = tmp_path / "clone2"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    write(clone, "remote.txt", "remote\n")
    commit_all(clone, "remote work")
    git(clone, "push", "-q", "origin", "main")
    write(repo.root, "local.txt", "local\n")
    commit_all(repo.root, "local work")
    outcome = service.push(repo, remote="origin", branch="main")
    assert outcome.success is False
    assert outcome.error["code"] in ("NON_FAST_FORWARD", "REMOTE_REJECTED")


def test_fetch_missing_remote_is_structured(svc):
    service, repo = svc
    outcome = service.fetch(repo, remote="nope")
    assert outcome.success is False
    assert outcome.error["code"] in ("REMOTE_NOT_FOUND", "NETWORK_ERROR")


def test_remotes_redact_credentials(svc):
    service, repo = svc
    service.remote_add(repo, "secure", "https://user:secret-token@example.com/org/repo.git")
    data = readers.remotes(repo)
    entry = next(r for r in data["remotes"] if r["name"] == "secure")
    assert "secret-token" not in (entry.get("fetchUrl") or "")
    assert "redacted" in (entry.get("fetchUrl") or "")


# ── Journal ──────────────────────────────────────────────────────────────────────────────

def test_journal_records_and_redacts(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.git.journal import GitJournal

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        journal = GitJournal(store)
        op_id = journal.start(
            repository=str(tmp_path), operation="remote_add",
            argv=["git", "remote", "add", "o", "https://u:ghp_abcdefghijklmnop1234@host/r.git"],
            risk="caution", mutating=True, run_id="run1",
        )
        journal.finish(op_id, status="SUCCESS", affected_files=["a.txt"], duration_ms=5)
        row = journal.get(op_id)
        assert row["operation"] == "remote_add"
        assert "ghp_abcdefghijklmnop1234" not in " ".join(row["args"])
        assert "redacted" in " ".join(row["args"])
    finally:
        store.close()


def test_journal_never_stores_raw_secret(tmp_path):
    from harness.git.journal import sanitize_argv

    argv = sanitize_argv(["git", "push", "https://x:AKIAABCDEFGHIJKLMNOP@host/r.git"])
    assert all("AKIAABCDEFGHIJKLMNOP" not in token for token in argv)


# ── Recovery ──────────────────────────────────────────────────────────────────────────────

def test_recovery_options_lists_abort(svc):
    service, repo = _conflict(svc)
    service.merge(repo, "other")
    options = recovery.recovery_options(repo)
    assert options.can_abort is True
    tools = [o.get("tool") for o in options.operations]
    assert "merge_abort" in tools


def test_reconcile_clears_stale_record(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.git.journal import GitJournal

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        repo = make_repo(tmp_path / "repo")
        journal = GitJournal(store)
        journal.set_active(
            repository=str(repo.root), operation_id="x", operation="merge", status="IN_PROGRESS",
        )
        result = recovery.reconcile(repo, journal)
        assert result.consistent is False
        assert journal.get_active(str(repo.root)) is None
    finally:
        store.close()


# ── Advanced: worktrees / bisect / clean / hooks / LFS ────────────────────────────────────────

def test_worktree_add_and_remove(svc, tmp_path):
    service, repo = svc
    target = tmp_path / "wt"
    outcome = service.worktree_add(repo, str(target), detach=True)
    assert outcome.success
    assert target.exists()
    removed = service.worktree_remove(repo, str(target), force=True)
    assert removed.success


def test_clean_preview_then_clean(svc):
    service, repo = svc
    write(repo.root, "untracked.txt", "temp\n")
    preview = service.clean_preview(repo)
    assert "untracked.txt" in preview["wouldDelete"]
    outcome = service.clean(repo)
    assert outcome.success
    assert not (repo.root / "untracked.txt").exists()


def test_bisect_lifecycle(svc):
    service, repo = svc
    for i in range(4):
        write(repo.root, f"f{i}.txt", f"{i}\n")
        commit_all(repo.root, f"c{i}")
    log = readers.log(repo, max_count=10)["commits"]
    good = log[-1]["sha"]
    bad = log[0]["sha"]
    outcome = service.bisect_start(repo, bad=bad, good=[good])
    assert outcome.success
    assert state.active_operation(repo).operation == "bisect"
    reset = service.bisect_reset(repo)
    assert reset.success
    assert state.active_operation(repo) is None


def test_hooks_detection(svc):
    service, repo = svc
    hook = repo.git_dir / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    data = readers.hooks(repo)
    assert "pre-commit" in data["hooks"]


def test_ignore_check(svc):
    service, repo = svc
    write(repo.root, ".gitignore", "*.log\n")
    assert readers.ignore_check(repo, "debug.log")["ignored"] is True
    assert readers.ignore_check(repo, "keep.txt")["ignored"] is False


def test_lfs_detection(svc):
    service, repo = svc
    write(repo.root, ".gitattributes", "*.bin filter=lfs diff=lfs merge=lfs -text\n")
    data = readers.lfs_status(repo)
    assert data["available"] is True
    assert data["usesLfs"] is True


# ── Untrusted repository ────────────────────────────────────────────────────────────────────

def test_inspect_untrusted_reports_hooks(svc):
    from harness.git import safety

    service, repo = svc
    hook = repo.git_dir / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\ncurl evil\n", encoding="utf-8")
    report = safety.inspect_untrusted(repo)
    assert "pre-push" in report.hooks
    # The hook is reported, never executed.
    assert "curl" not in " ".join(report.hooks)


# ── Config ─────────────────────────────────────────────────────────────────────────────────────

def test_config_set_and_get(svc):
    service, repo = svc
    outcome = service.config_set(repo, "eclipse.testKey", "value1", scope="local")
    assert outcome.success
    from harness.git.executor import run

    result = run(repo.root, "config_get", {"key": "eclipse.testKey", "scope": ["--local"]})
    assert result.ok and result.stdout.strip() == "value1"
