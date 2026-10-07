"""Normalized VCS models.

GitHub/GitLab/Bitbucket disagree about names (pull request vs merge request),
identifiers, and shapes. These dataclasses are the ONE internal model the agent
and the UI read. Each provider maps its API onto them; provider-specific extras
ride along in an `extra` dict rather than polluting the common shape — a provider
is never forced into an artificial abstraction it does not fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _clean(mapping: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in mapping.items() if v is not None}


@dataclass
class VCSRepository:
    provider: str
    full_name: str                      # "owner/name"
    name: str
    owner: str
    default_branch: str = "main"
    private: bool = False
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "provider": self.provider, "fullName": self.full_name, "name": self.name,
            "owner": self.owner, "defaultBranch": self.default_branch,
            "private": self.private, "url": self.url, "extra": self.extra or None,
        })


@dataclass
class VCSBranch:
    name: str
    sha: str = ""
    protected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _clean({"name": self.name, "sha": self.sha, "protected": self.protected or None})


@dataclass
class VCSCommit:
    sha: str
    message: str = ""
    author: str = ""
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"sha": self.sha, "message": self.message, "author": self.author, "date": self.date}


@dataclass
class VCSReview:
    id: str
    author: str = ""
    state: str = ""                     # approved | changes_requested | commented | pending
    body: str = ""
    submitted_at: str = ""
    comments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "id": self.id, "author": self.author, "state": self.state,
            "body": self.body, "submittedAt": self.submitted_at,
            "comments": self.comments or None,
        })


@dataclass
class VCSCheck:
    name: str
    status: str = ""                    # queued | in_progress | completed
    conclusion: str = ""               # success | failure | neutral | cancelled | skipped
    url: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "name": self.name, "status": self.status,
            "conclusion": self.conclusion, "url": self.url, "details": self.details,
        })


@dataclass
class VCSWorkflowRun:
    id: str
    name: str = ""
    status: str = ""
    conclusion: str = ""
    branch: str = ""
    url: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "id": self.id, "name": self.name, "status": self.status,
            "conclusion": self.conclusion, "branch": self.branch,
            "url": self.url, "createdAt": self.created_at,
        })


@dataclass
class VCSPullRequest:
    """The normalized PR/MR. GitLab merge requests map onto this exactly."""

    provider: str
    number: int
    title: str
    description: str = ""
    source_branch: str = ""
    target_branch: str = ""
    author: str = ""
    status: str = "open"               # open | closed | merged
    draft: bool = False
    mergeable: Optional[bool] = None
    merged: bool = False
    url: str = ""
    head_sha: str = ""
    created_at: str = ""
    updated_at: str = ""
    checks: list[VCSCheck] = field(default_factory=list)
    reviews: list[VCSReview] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """The provider's own word for this object (PR vs MR)."""
        return "mr" if self.provider == "gitlab" else "pr"

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "provider": self.provider, "number": self.number, "title": self.title,
            "description": self.description, "sourceBranch": self.source_branch,
            "targetBranch": self.target_branch, "author": self.author,
            "status": self.status, "draft": self.draft, "mergeable": self.mergeable,
            "merged": self.merged, "url": self.url, "headSha": self.head_sha,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
            "checks": [c.to_dict() for c in self.checks] or None,
            "reviews": [r.to_dict() for r in self.reviews] or None,
            "labels": self.labels or None, "extra": self.extra or None,
        })


__all__ = [
    "VCSBranch",
    "VCSCheck",
    "VCSCommit",
    "VCSPullRequest",
    "VCSRepository",
    "VCSReview",
    "VCSWorkflowRun",
]
