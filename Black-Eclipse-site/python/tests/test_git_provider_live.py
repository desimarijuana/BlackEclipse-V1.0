"""Git subsystem — OPT-IN live provider integration tests.

These contact a REAL GitHub/GitLab/Bitbucket account and are SKIPPED unless the
operator provides a token in the environment AND opts in:

    BLACK_ECLIPSE_PROVIDER_IT=1     # explicit opt-in (never runs by default)
    GITHUB_TOKEN=...               # or GITLAB_TOKEN / BITBUCKET_TOKEN
    BLACK_ECLIPSE_PROVIDER_REPO=owner/repo   # a scratch repo the token can write

They are deliberately NOT part of `npm test`: a required network call and a real
credential must never gate the offline suite (the same rule as the live smoke
checks in `scripts/test-python.js`). Each test creates a throwaway branch, opens
and closes a PR/MR, and cleans the branch up — it never merges.

The mocked-HTTP provider tests in `test_git_integration.py` cover the request/
response mapping deterministically; these cover the real wire format.
"""

from __future__ import annotations

import os
import time

import pytest

from harness.git.vcs import ProviderRegistry
from harness.git.vcs.base import ProviderConfig, ProviderError, parse_remote

OPT_IN = os.environ.get("BLACK_ECLIPSE_PROVIDER_IT") == "1"
REPO = os.environ.get("BLACK_ECLIPSE_PROVIDER_REPO", "")

pytestmark = pytest.mark.skipif(
    not OPT_IN or not REPO,
    reason="live provider tests are opt-in: set BLACK_ECLIPSE_PROVIDER_IT=1 and BLACK_ECLIPSE_PROVIDER_REPO",
)

_TOKEN_ENVS = {
    "github": ("GITHUB_TOKEN", "GH_TOKEN"),
    "gitlab": ("GITLAB_TOKEN", "GL_TOKEN"),
    "bitbucket": ("BITBUCKET_TOKEN", "BITBUCKET_ACCESS_TOKEN"),
}


def _provider():
    """The first provider with a configured token for the repo's host."""
    registry = ProviderRegistry()
    for name, envs in _TOKEN_ENVS.items():
        if not any(os.environ.get(e) for e in envs):
            continue
        provider = registry.get(name)
        if provider is not None and provider.authenticated:
            return provider
    pytest.skip("no provider token configured")


def _unique_branch(prefix: str = "eclipse-it") -> str:
    return f"{prefix}/{int(time.time())}-{os.getpid()}"


def test_repository_is_readable():
    provider = _provider()
    repo = provider.get_repository(REPO)
    assert repo.full_name == REPO
    assert repo.default_branch


def test_branch_and_pull_request_lifecycle():
    provider = _provider()
    repo = provider.get_repository(REPO)
    branch = _unique_branch()
    created = None
    try:
        branch_ref = provider.create_branch(REPO, branch, from_sha="")
        assert branch_ref.name == branch

        pr = provider.create_pull_request(
            REPO, title=f"[eclipse-it] {branch}", source_branch=branch,
            target_branch=repo.default_branch, description="Automated integration check.",
        )
        created = pr
        assert pr.number > 0
        assert pr.source_branch == branch

        fetched = provider.get_pull_request(REPO, pr.number)
        assert fetched.number == pr.number

        # Checks + reviews must be readable (a real host returns something, even if
        # empty); never claim success — just that the wire mapping is valid.
        provider.get_checks(REPO, fetched.head_sha or repo.default_branch)
        provider.list_reviews(REPO, pr.number)
        provider.get_review_comments(REPO, pr.number)

        closed = provider.close_pull_request(REPO, pr.number)
        assert closed.status in ("closed", "merged")
    finally:
        # Best-effort: close an open PR and delete the branch we created.
        if created is not None and created.status == "open":
            try:
                provider.close_pull_request(REPO, created.number)
            except ProviderError:
                pass
        try:
            _delete_branch(provider, REPO, branch)
        except ProviderError:
            pass


def _delete_branch(provider, full_name, branch):
    """Delete a branch through the provider's raw API (not part of the protocol)."""
    http = getattr(provider, "_http", None)
    if http is None:
        return
    if provider.name == "github":
        base = provider.api_base
        http.delete(f"{base}/repos/{full_name}/git/refs/heads/{branch}")
    # GitLab/Bitbucket branch deletion is provider-specific; the scratch repo
    # tolerates a leftover branch, so a failure here is not fatal.


def test_ci_status_wire_mapping():
    provider = _provider()
    repo = provider.get_repository(REPO)
    checks = provider.get_checks(REPO, repo.default_branch)
    # A list is the contract; an empty list on a repo with no CI is honest.
    assert isinstance(checks, list)
    for check in checks:
        assert check.status
