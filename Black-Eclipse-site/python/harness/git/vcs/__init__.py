"""The VCS provider layer.

Registration happens on import so `git/vcs/__init__.py` is the ONE place a
provider is added. The `ProviderRegistry` constructs providers lazily from
operator configuration (which declares env-var NAMES, never token values).

    GitHubProvider, GitLabProvider, BitbucketProvider
        ↓  all implement
    VCSProvider  (normalized models; provider-specific extras ride in `extra`)

Local Git is NOT here: `git/service.py` owns it. A provider is only ever reached
for a remote collaboration action.
"""

from __future__ import annotations

from .base import (
    ProviderConfig,
    ProviderError,
    ProviderRegistry,
    RemoteRef,
    VCSProvider,
    parse_remote,
    read_token,
)
from .bitbucket import BitbucketProvider
from .github import GitHubProvider
from .gitlab import GitLabProvider
from .http import HttpClient
from .models import (
    VCSBranch,
    VCSCheck,
    VCSCommit,
    VCSPullRequest,
    VCSRepository,
    VCSReview,
    VCSWorkflowRun,
)

# Register the shipped providers exactly once.
ProviderRegistry.register("github", GitHubProvider)
ProviderRegistry.register("gitlab", GitLabProvider)
ProviderRegistry.register("bitbucket", BitbucketProvider)

__all__ = [
    "BitbucketProvider",
    "GitHubProvider",
    "GitLabProvider",
    "HttpClient",
    "ProviderConfig",
    "ProviderError",
    "ProviderRegistry",
    "RemoteRef",
    "VCSBranch",
    "VCSCheck",
    "VCSCommit",
    "VCSPullRequest",
    "VCSProvider",
    "VCSRepository",
    "VCSReview",
    "VCSWorkflowRun",
    "parse_remote",
    "read_token",
]
