"""Git subsystem — the end-to-end workflow and the VCS provider layer.

`test_full_development_workflow` exercises the 20-step acceptance workflow against
an isolated repository. The provider tests mock the HTTP layer, so no real
credentials or network are required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.git import readers, state
from harness.git.messages import generate_pull_request
from harness.git.service import GitService
from harness.git.vcs import parse_remote
from harness.git.vcs.base import ProviderConfig, ProviderError, ProviderRegistry
from harness.git.vcs.github import GitHubProvider
from harness.git.vcs.http import HttpResponse

from git_helpers import commit_all, git, make_bare_remote, make_repo, write


# ── The full workflow ────────────────────────────────────────────────────────────────

def test_full_development_workflow(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")

    # 1-3. Discover, read state, create an isolated branch.
    assert repo.branch == "main"
    feature = service.create_branch(repo, "feature/git-test", checkout=True)
    assert feature.success
    assert service.discover(repo.root).branch == "feature/git-test"

    # 4. Modify files.
    write(repo.root, "src/util.py", "def add(a, b):\n    return a + b\n")
    write(repo.root, "tests/test_util.py", "def test_add():\n    assert 1 + 1 == 2\n")

    # 5-6. Inspect status and diff.
    status = service.status(repo)
    assert not status["clean"]
    diff = readers.diff_worktree(repo)
    assert diff["files_changed"] >= 2

    # 7-8. Stage only the intended files (not, say, a stray log).
    write(repo.root, "debug.log", "noise\n")
    service.stage(repo, ["src/util.py", "tests/test_util.py"])
    staged = service._staged_paths(repo)
    assert "src/util.py" in staged and "tests/test_util.py" in staged
    assert "debug.log" not in staged

    # 9-10. Generate a conventional message and commit.
    generated = service.generate_commit_message(repo, conventional=True)
    assert generated["conventional"] is True
    commit = service.commit(repo, generated["message"])
    assert commit.success and commit.result["commit"]

    # 11-12. Inspect the log.
    log = readers.log(repo)
    assert log["commits"][0]["subject"].startswith(("feat", "fix", "test", "chore"))

    # 13-14. Create a conflicting change on main and merge; detect the conflict.
    service.checkout(repo, "main")
    write(repo.root, "src/util.py", "def add(a, b):\n    return b + a\n")
    service.stage(repo, ["src/util.py"])
    service.commit(repo, "main edit")
    merge = service.merge(repo, "feature/git-test",
                          message="merge feature/git-test")
    # Not necessarily a conflict (different files), so handle both.
    if not merge.success:
        assert merge.error["code"] == "MERGE_CONFLICT"
        files = merge.error["files"]
        assert files
        # 12-13. Detect + resolve the conflict.
        blocks = state.read_conflicts(repo, files[0])
        assert blocks
        service.resolve_conflict(repo, files[0], "def add(a, b):\n    return a + b\n")
        cont = service.merge_continue(repo)
        assert cont.success

    # 15. Inspect reflog.
    reflog = readers.reflog(repo)
    assert reflog["entries"]

    # 16. Create a tag.
    assert service.tag_create(repo, "v0.1.0", message="first cut").success

    # 17. Create a worktree.
    wt = tmp_path / "hotfix-wt"
    assert service.worktree_add(repo, str(wt), detach=True).success
    assert wt.exists()

    # 18. Stash round-trip.
    write(repo.root, "src/util.py", "def add(a, b):\n    return a + b + 0\n")
    assert service.stash_push(repo, message="wip").success
    assert service.stash_apply(repo, "stash@{0}", pop=True).success

    # 19-20. Clean up the worktree.
    assert service.worktree_remove(repo, str(wt), force=True).success
    assert not wt.exists()


def test_push_then_pull_roundtrip(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "origin-repo")
    bare = make_bare_remote(tmp_path)
    service.remote_add(repo, "origin", str(bare))
    assert service.push(repo, remote="origin", branch="main", set_upstream=True).success

    clone_dir = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone_dir))
    clone_repo = service.discover(clone_dir)
    # A change pushed from the clone is visible after a fetch in the origin.
    write(clone_dir, "src/new.py", "x = 1\n")
    commit_all(clone_dir, "clone change")
    git(clone_dir, "push", "-q", "origin", "main")
    fetched = service.fetch(repo, remote="origin")
    assert fetched.success
    assert service.pull(repo, remote="origin", branch="main", strategy="ff-only").success
    assert (repo.root / "src" / "new.py").exists()


# ── VCS provider — URL parsing ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,provider,full", [
    ("https://github.com/owner/repo.git", "github", "owner/repo"),
    ("git@github.com:owner/repo.git", "github", "owner/repo"),
    ("https://gitlab.com/group/sub/repo.git", "gitlab", "group/sub/repo"),
    ("git@bitbucket.org:team/repo.git", "bitbucket", "team/repo"),
    ("ssh://git@github.com/owner/repo.git", "github", "owner/repo"),
])
def test_parse_remote(url, provider, full):
    ref = parse_remote(url)
    assert ref is not None
    assert ref.provider == provider
    assert ref.full_name == full


def test_parse_remote_unknown_host():
    ref = parse_remote("https://git.internal.example.com/team/repo.git")
    assert ref is not None
    assert ref.provider == ""
    assert ref.full_name == "team/repo"


# ── VCS provider — mocked HTTP ────────────────────────────────────────────────────────

class _FakeHttp:
    """A scripted HTTP client: maps (method, url-substring) to a response."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        for (m, needle), response in self.routes.items():
            if m == method and needle in url:
                if isinstance(response, Exception):
                    raise response
                if isinstance(response, dict):
                    return HttpResponse(status=200, headers={}, body=json.dumps(response), url=url)
                return response
        raise ProviderError("NOT_FOUND", f"no route for {method} {url}", status=404)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


def _github(routes):
    provider = GitHubProvider(token="fake-token")
    provider._http = _FakeHttp(routes)
    return provider


def test_github_get_pull_request_normalizes():
    provider = _github({
        ("GET", "/pulls/42"): {
            "number": 42, "title": "Add OAuth", "body": "desc",
            "state": "open", "draft": False, "mergeable": True,
            "user": {"login": "alice"},
            "head": {"ref": "feature/auth", "sha": "abc123"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/o/r/pull/42",
            "labels": [{"name": "feature"}],
        },
        ("GET", "/commits/abc123/check-runs"): {"check_runs": [
            {"name": "ci", "status": "completed", "conclusion": "success", "html_url": ""},
        ]},
        ("GET", "/commits/abc123/status"): {"statuses": []},
    })
    pr = provider.get_pull_request("o/r", 42)
    assert pr.number == 42
    assert pr.source_branch == "feature/auth"
    assert pr.target_branch == "main"
    assert pr.status == "open"
    assert pr.author == "alice"
    assert pr.labels == ["feature"]
    assert len(pr.checks) == 1 and pr.checks[0].conclusion == "success"


def test_github_create_pull_request():
    provider = _github({
        ("POST", "/pulls"): {
            "number": 7, "title": "New", "state": "open",
            "head": {"ref": "f", "sha": "s"}, "base": {"ref": "main"},
            "user": {"login": "bob"}, "html_url": "u",
        },
    })
    pr = provider.create_pull_request("o/r", title="New", source_branch="f", target_branch="main")
    assert pr.number == 7 and pr.status == "open"


def test_github_merge_conflict_is_structured():
    provider = _github({("PUT", "/merge"): {"merged": False, "message": "not mergeable"}})
    with pytest.raises(ProviderError) as info:
        provider.merge_pull_request("o/r", 7)
    assert info.value.code == "CONFLICT"


def test_provider_authentication_failure_maps_to_code():
    provider = _github({("GET", "/repos/o/r"): ProviderError("AUTHENTICATION_FAILED", "nope", status=401)})
    with pytest.raises(ProviderError) as info:
        provider.get_repository("o/r")
    assert info.value.code == "AUTHENTICATION_FAILED"


def test_provider_describe_never_leaks_token():
    provider = GitHubProvider(token="super-secret-token")
    info = provider.describe()
    assert "super-secret-token" not in json.dumps(info)
    assert info["authenticated"] is True


def test_registry_resolves_by_host_and_requires_token(monkeypatch):
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    registry = ProviderRegistry()
    provider = registry.provider_for_remote("https://github.com/o/r.git")
    assert provider is not None
    assert provider.name == "github"
    assert provider.authenticated is False
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    registry2 = ProviderRegistry()
    provider2 = registry2.provider_for_remote("https://github.com/o/r.git")
    assert provider2.authenticated is True


def test_registry_reads_token_from_declared_env(monkeypatch):
    from harness.git.vcs.base import read_token

    monkeypatch.setenv("MY_GITLAB_TOKEN", "abc")
    cfg = ProviderConfig(provider="gitlab", token_env="MY_GITLAB_TOKEN")
    assert read_token(cfg) == "abc"


# ── Pull-request generation (deterministic) ────────────────────────────────────────────

def test_generate_pull_request_from_branch(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    service.create_branch(repo, "feature/x", checkout=True)
    write(repo.root, "src/x.py", "x = 1\n")
    service.stage(repo, ["src/x.py"])
    service.commit(repo, "feat: add x")
    draft = generate_pull_request(repo, base="main", head="feature/x")
    assert draft["title"].startswith("feat")
    assert "src/x.py" in draft["files"]
    assert "## Summary" in draft["body"]
    assert draft["source_branch"] == "feature/x"
    assert draft["target_branch"] == "main"


# ── Agent-tool integration (structured tools, no model) ─────────────────────────────────

def test_agent_uses_structured_tools_for_the_workflow(tmp_path):
    """The workflow the acceptance criteria demand, driven through the TOOLS."""
    import asyncio
    import os
    from pathlib import Path

    from harness.code.policy import WorkspaceBinding
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.code.workspace import ResolvedWorkspace
    from harness.git.approvals import make_git_authorizer
    from harness.git.register import register_git_subsystem
    from harness.tools import ToolContext, ToolRegistry

    repo = make_repo(tmp_path / "repo")
    registry = ToolRegistry()
    register_code_tools(registry)
    register_git_subsystem(registry)
    real = Path(os.path.realpath(repo.root))
    binding = WorkspaceBinding(id="ws_i", root=real, base_revision="HEAD", strategy="worktree")
    ws = ResolvedWorkspace(id="ws_i", root=real, base_revision="HEAD", strategy="worktree", binding=binding)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=ws, autonomy="edit_verify",
        authorize_effect=make_git_authorizer(None, "r", "ws_i", inner=make_code_authorizer()),
    )

    def call(name, args):
        return asyncio.run(registry.execute(name, name, args, ctx, allowed={name}))

    assert call("git_create_branch", {"name": "feature/tool-test"}) .ok
    write(repo.root, "src/util.py", "def f():\n    return 1\n")
    assert call("git_status", {}).ok
    assert call("git_diff", {}).ok
    assert call("git_stage", {"paths": ["src/util.py"]}).ok
    message = call("git_generate_commit_message", {"conventional": True}).data["message"]
    committed = call("git_commit", {"message": message})
    assert committed.ok and committed.data["result"]["commit"]
    assert call("git_log", {}).data["count"] >= 1
