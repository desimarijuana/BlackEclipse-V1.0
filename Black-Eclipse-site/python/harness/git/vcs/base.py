"""The VCS provider abstraction.

Local Git and remote hosting are separate concerns. This is the remote half: a
small protocol every hosting provider implements, plus a remote-URL parser and a
provider registry. A provider authenticates with a token read from an
operator-configured environment variable — the token is held on the provider
instance and is NEVER returned from any method, logged, or journaled.

A provider is chosen from the repository's remote URL host (github/gitlab/
bitbucket), or by an explicit override. When no provider matches, or no token is
configured, `provider_for` returns None and the caller reports it honestly — a
remote operation is never faked.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import (
    VCSBranch, VCSCheck, VCSCommit, VCSPullRequest, VCSRepository, VCSReview,
    VCSWorkflowRun,
)

# ── Errors ─────────────────────────────────────────────────────────────────────

class ProviderError(Exception):
    """A structured provider failure. `code` is stable and testable."""

    def __init__(self, code: str, message: str, *, status: Optional[int] = None,
                 recoverable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code, "message": self.message, "recoverable": self.recoverable,
        }
        if self.status is not None:
            out["status"] = self.status
        return out


AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
PERMISSION_DENIED = "PERMISSION_DENIED"
NOT_FOUND = "NOT_FOUND"
RATE_LIMITED = "RATE_LIMITED"
CONFLICT = "CONFLICT"
VALIDATION_FAILED = "VALIDATION_FAILED"
NETWORK_ERROR = "NETWORK_ERROR"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# ── Remote reference ────────────────────────────────────────────────────────────

_SSH_RE = re.compile(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+?)(?:\.git)?$")
_URL_RE = re.compile(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?$")

_PROVIDER_HOSTS: tuple[tuple[str, str], ...] = (
    ("github", "github"),
    ("gitlab", "gitlab"),
    ("bitbucket", "bitbucket"),
)


@dataclass(frozen=True)
class RemoteRef:
    host: str
    owner: str
    repo: str
    provider: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_remote(url: str) -> Optional[RemoteRef]:
    """Parse a git remote URL into `(host, owner, repo, provider)`, or None.

    Handles https, ssh (`git@host:owner/repo`), `ssh://`, and a self-hosted host.
    The provider is inferred from the host; an unknown host yields provider="".
    """
    text = str(url or "").strip()
    if not text:
        return None
    match = _SSH_RE.match(text)
    host = owner_path = ""
    if match and "://" not in text:
        host = match.group("host")
        owner_path = match.group("path")
    else:
        m2 = _URL_RE.match(text)
        if not m2:
            return None
        host = m2.group("host")
        owner_path = m2.group("path")
    owner_path = owner_path.strip("/")
    segments = owner_path.split("/")
    if len(segments) < 2:
        return None
    owner = "/".join(segments[:-1])
    repo = segments[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    provider = ""
    lowered = host.casefold()
    for needle, name in _PROVIDER_HOSTS:
        if needle in lowered:
            provider = name
            break
    return RemoteRef(host=host, owner=owner, repo=repo, provider=provider)


# ── Provider protocol ───────────────────────────────────────────────────────────

class VCSProvider:
    """The remote-hosting protocol. Not every method fits every host equally;
    a method a host cannot support raises `ProviderError(NOT_IMPLEMENTED)`."""

    name = "base"
    supports_checks = False
    supports_workflows = False

    def __init__(self, *, token: Optional[str] = None, host: str = "", base_url: str = "") -> None:
        self._token = token or ""
        self.host = host
        self.base_url = base_url or self._default_base_url(host)

    @staticmethod
    def _default_base_url(host: str) -> str:
        return f"https://{host}" if host else ""

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    def describe(self) -> dict[str, Any]:
        """A content-free description. NEVER includes the token."""
        return {
            "provider": self.name, "host": self.host,
            "authenticated": self.authenticated, "baseUrl": self.base_url,
            "supportsChecks": self.supports_checks,
            "supportsWorkflows": self.supports_workflows,
        }

    # Required capabilities (every provider implements these).
    def get_repository(self, full_name: str) -> VCSRepository: ...
    def list_repositories(self, *, limit: int = 50) -> list[VCSRepository]: ...
    def get_branches(self, full_name: str) -> list[VCSBranch]: ...
    def get_commits(self, full_name: str, *, ref: str = "", limit: int = 30) -> list[VCSCommit]: ...
    def create_branch(self, full_name: str, name: str, *, from_sha: str = "") -> VCSBranch: ...
    def create_pull_request(self, full_name: str, *, title: str, source_branch: str,
                            target_branch: str, description: str = "", draft: bool = False) -> VCSPullRequest: ...
    def get_pull_request(self, full_name: str, number: int) -> VCSPullRequest: ...
    def list_pull_requests(self, full_name: str, *, state: str = "open",
                           limit: int = 30) -> list[VCSPullRequest]: ...
    def update_pull_request(self, full_name: str, number: int, *, title: Optional[str] = None,
                            description: Optional[str] = None, state: Optional[str] = None,
                            target_branch: Optional[str] = None) -> VCSPullRequest: ...
    def close_pull_request(self, full_name: str, number: int) -> VCSPullRequest: ...
    def merge_pull_request(self, full_name: str, number: int, *, method: str = "merge",
                           delete_branch: bool = False) -> VCSPullRequest: ...
    def request_review(self, full_name: str, number: int, reviewers: list[str]) -> dict[str, Any]: ...
    def list_reviews(self, full_name: str, number: int) -> list[VCSReview]: ...
    def get_review_comments(self, full_name: str, number: int) -> list[dict[str, Any]]: ...
    def reply_review_comment(self, full_name: str, number: int, comment_id: str,
                             body: str) -> dict[str, Any]: ...

    # Optional capabilities.
    def get_checks(self, full_name: str, ref: str) -> list[VCSCheck]:
        raise ProviderError(NOT_IMPLEMENTED, "This host does not report checks.")

    def get_workflows(self, full_name: str) -> list[dict[str, Any]]:
        raise ProviderError(NOT_IMPLEMENTED, "This host does not report workflows.")

    def get_workflow_runs(self, full_name: str, *, ref: str = "", limit: int = 20) -> list[VCSWorkflowRun]:
        raise ProviderError(NOT_IMPLEMENTED, "This host does not report workflow runs.")

    def get_job_logs(self, full_name: str, job_id: str) -> dict[str, Any]:
        raise ProviderError(NOT_IMPLEMENTED, "This host does not expose job logs.")

    def rerun_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        raise ProviderError(NOT_IMPLEMENTED, "This host cannot rerun workflows.")

    def cancel_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        raise ProviderError(NOT_IMPLEMENTED, "This host cannot cancel workflows.")


# ── Registry / resolution ────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """Operator configuration for one host. The token ENV NAME only — never a value."""

    provider: str
    host: str = ""
    token_env: str = ""
    base_url: str = ""
    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


# Default token env-var names when the operator config names none.
_DEFAULT_TOKEN_ENVS: dict[str, tuple[str, ...]] = {
    "github": ("GITHUB_TOKEN", "GH_TOKEN"),
    "gitlab": ("GITLAB_TOKEN", "GL_TOKEN", "CI_JOB_TOKEN"),
    "bitbucket": ("BITBUCKET_TOKEN", "BITBUCKET_ACCESS_TOKEN"),
}
_DEFAULT_HOSTS: dict[str, str] = {
    "github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org",
}


def read_token(config: ProviderConfig) -> Optional[str]:
    """Resolve a token from the operator-declared env var(s). Never logged."""
    candidates: list[str] = []
    if config.token_env:
        candidates.append(config.token_env)
    candidates.extend(_DEFAULT_TOKEN_ENVS.get(config.provider, ()))
    for name in candidates:
        value = os.environ.get(name)
        if value:
            return value
    return None


class ProviderRegistry:
    """Constructs and caches one provider instance per host/provider name."""

    _FACTORIES: dict[str, type] = {}

    def __init__(self, configs: Optional[list[ProviderConfig]] = None) -> None:
        self._configs: dict[str, ProviderConfig] = {}
        for cfg in configs or []:
            self._configs[cfg.provider] = cfg
        self._cache: dict[str, VCSProvider] = {}

    @classmethod
    def register(cls, name: str, factory: type) -> None:
        cls._FACTORIES[name] = factory

    def configure(self, config: ProviderConfig) -> None:
        self._configs[config.provider] = config
        self._cache.pop(config.provider, None)

    def provider_for_remote(self, url: str) -> Optional[VCSProvider]:
        remote = parse_remote(url)
        if remote is None:
            return None
        return self.get(remote.provider or "", host=remote.host)

    def get(self, name: str, *, host: str = "") -> Optional[VCSProvider]:
        if not name:
            return None
        key = f"{name}:{host}"
        if key in self._cache:
            return self._cache[key]
        factory = self._FACTORIES.get(name)
        if factory is None:
            return None
        cfg = self._configs.get(name) or ProviderConfig(
            provider=name, host=host or _DEFAULT_HOSTS.get(name, ""),
        )
        if not cfg.enabled:
            return None
        token = read_token(cfg)
        provider = factory(token=token, host=host or cfg.host, base_url=cfg.base_url)
        self._cache[key] = provider
        return provider


__all__ = [
    "AUTHENTICATION_FAILED",
    "CONFLICT",
    "NETWORK_ERROR",
    "NOT_FOUND",
    "NOT_IMPLEMENTED",
    "PERMISSION_DENIED",
    "PROVIDER_UNAVAILABLE",
    "ProviderConfig",
    "ProviderError",
    "ProviderRegistry",
    "RATE_LIMITED",
    "RemoteRef",
    "VALIDATION_FAILED",
    "VCSProvider",
    "parse_remote",
    "read_token",
]
