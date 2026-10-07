"""The GitHub provider — REST v3 (and the Actions/Checks endpoints).

Authentication is a token read from an operator-declared environment variable;
the provider holds it only to build request headers and never exposes it. Every
method returns the normalized `vcs.models` types.

GitHub is the reference provider; the GitLab and Bitbucket providers follow the
same shape. Functionality that is specific to GitHub (GraphQL, Actions) is added
here without widening the base protocol beyond `get_checks`/`get_workflows`.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import ProviderError, VCSProvider
from .http import HttpClient
from .models import (
    VCSBranch, VCSCheck, VCSCommit, VCSPullRequest, VCSRepository, VCSReview,
    VCSWorkflowRun,
)

API_BASE = "https://api.github.com"


def _map_state(pr: dict[str, Any]) -> str:
    if pr.get("merged_at") or pr.get("merged"):
        return "merged"
    state = str(pr.get("state") or "open")
    return "closed" if state == "closed" else "open"


def _map_pr(data: dict[str, Any], *, provider: str = "github", checks=None) -> VCSPullRequest:
    base = data.get("base") or {}
    head = data.get("head") or {}
    user = data.get("user") or {}
    return VCSPullRequest(
        provider=provider,
        number=int(data.get("number") or 0),
        title=str(data.get("title") or ""),
        description=str(data.get("body") or ""),
        source_branch=str(head.get("ref") or ""),
        target_branch=str(base.get("ref") or ""),
        author=str(user.get("login") or ""),
        status=_map_state(data),
        draft=bool(data.get("draft")),
        mergeable=data.get("mergeable") if isinstance(data.get("mergeable"), bool) else None,
        merged=bool(data.get("merged") or data.get("merged_at")),
        url=str(data.get("html_url") or ""),
        head_sha=str(head.get("sha") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        labels=[str((lbl or {}).get("name") or "") for lbl in (data.get("labels") or [])],
        checks=list(checks or []),
        extra={"nodeId": data.get("node_id"), "mergeStateStatus": data.get("mergeable_state")},
    )


class GitHubProvider(VCSProvider):
    name = "github"
    supports_checks = True
    supports_workflows = True

    def __init__(self, *, token: Optional[str] = None, host: str = "", base_url: str = "") -> None:
        super().__init__(token=token, host=host or "github.com", base_url=base_url)
        is_public = not self.host or self.host.casefold() == "github.com"
        self.api_base = (base_url.rstrip("/") + "/api/v3" if base_url else
                         (API_BASE if is_public else f"https://{self.host}/api/v3"))
        self._http = HttpClient(
            token=self._token,
            extra_headers={"X-GitHub-Api-Version": "2022-11-28"},
        )

    def _require_auth(self) -> None:
        if not self.authenticated:
            raise ProviderError("AUTHENTICATION_FAILED", "No sign-in is configured for this service.")

    # ── Repositories ──────────────────────────────────────────────────────────
    def get_repository(self, full_name: str) -> VCSRepository:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}").json() or {}
        return VCSRepository(
            provider="github", full_name=str(data.get("full_name") or full_name),
            name=str(data.get("name") or ""), owner=str((data.get("owner") or {}).get("login") or ""),
            default_branch=str(data.get("default_branch") or "main"),
            private=bool(data.get("private")), url=str(data.get("html_url") or ""),
        )

    def list_repositories(self, *, limit: int = 50) -> list[VCSRepository]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/user/repos?per_page={min(limit, 100)}").json() or []
        return [
            VCSRepository(
                provider="github", full_name=str(r.get("full_name") or ""),
                name=str(r.get("name") or ""), owner=str((r.get("owner") or {}).get("login") or ""),
                default_branch=str(r.get("default_branch") or "main"),
                private=bool(r.get("private")), url=str(r.get("html_url") or ""),
            )
            for r in data
        ]

    # ── Branches / commits ─────────────────────────────────────────────────────
    def get_branches(self, full_name: str) -> list[VCSBranch]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}/branches?per_page=100").json() or []
        return [
            VCSBranch(
                name=str(b.get("name") or ""),
                sha=str((b.get("commit") or {}).get("sha") or ""),
                protected=bool(b.get("protected")),
            )
            for b in data
        ]

    def get_commits(self, full_name: str, *, ref: str = "", limit: int = 30) -> list[VCSCommit]:
        self._require_auth()
        params = f"?per_page={min(limit, 100)}" + (f"&sha={ref}" if ref else "")
        data = self._http.get(f"{self.api_base}/repos/{full_name}/commits{params}").json() or []
        return [
            VCSCommit(
                sha=str(c.get("sha") or ""),
                message=str((c.get("commit") or {}).get("message") or ""),
                author=str(((c.get("commit") or {}).get("author") or {}).get("name") or ""),
                date=str(((c.get("commit") or {}).get("author") or {}).get("date") or ""),
            )
            for c in data
        ]

    def create_branch(self, full_name: str, name: str, *, from_sha: str = "") -> VCSBranch:
        self._require_auth()
        if not from_sha:
            repo = self.get_repository(full_name)
            commits = self.get_commits(full_name, ref=repo.default_branch, limit=1)
            from_sha = commits[0].sha if commits else ""
        body = {"ref": f"refs/heads/{name}", "sha": from_sha}
        data = self._http.post(f"{self.api_base}/repos/{full_name}/git/refs", data=body).json() or {}
        return VCSBranch(name=name, sha=str((data.get("object") or {}).get("sha") or from_sha))

    # ── Pull requests ────────────────────────────────────────────────────────────
    def create_pull_request(self, full_name: str, *, title: str, source_branch: str,
                            target_branch: str, description: str = "", draft: bool = False) -> VCSPullRequest:
        self._require_auth()
        body = {
            "title": title, "head": source_branch, "base": target_branch,
            "body": description, "draft": draft,
        }
        data = self._http.post(f"{self.api_base}/repos/{full_name}/pulls", data=body).json() or {}
        return _map_pr(data)

    def get_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}/pulls/{number}").json() or {}
        pr = _map_pr(data)
        try:
            pr.checks = self.get_checks(full_name, pr.head_sha) if pr.head_sha else []
        except ProviderError:
            pr.checks = []
        return pr

    def list_pull_requests(self, full_name: str, *, state: str = "open", limit: int = 30) -> list[VCSPullRequest]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repos/{full_name}/pulls?state={state}&per_page={min(limit, 100)}"
        ).json() or []
        return [_map_pr(p) for p in data]

    def update_pull_request(self, full_name: str, number: int, *, title: Optional[str] = None,
                            description: Optional[str] = None, state: Optional[str] = None,
                            target_branch: Optional[str] = None) -> VCSPullRequest:
        self._require_auth()
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["body"] = description
        if state is not None:
            body["state"] = state
        if target_branch is not None:
            body["base"] = target_branch
        data = self._http.patch(f"{self.api_base}/repos/{full_name}/pulls/{number}", data=body).json() or {}
        return _map_pr(data)

    def close_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        return self.update_pull_request(full_name, number, state="closed")

    def merge_pull_request(self, full_name: str, number: int, *, method: str = "merge",
                           delete_branch: bool = False) -> VCSPullRequest:
        self._require_auth()
        body = {"merge_method": method if method in ("merge", "squash", "rebase") else "merge"}
        data = self._http.put(f"{self.api_base}/repos/{full_name}/pulls/{number}/merge", data=body).json() or {}
        if not data.get("merged"):
            raise ProviderError("CONFLICT", "The change could not be merged automatically.", recoverable=True)
        if delete_branch:
            try:
                pr = self.get_pull_request(full_name, number)
                if pr.source_branch:
                    self._http.delete(f"{self.api_base}/repos/{full_name}/git/refs/heads/{pr.source_branch}")
            except ProviderError:
                pass
        return self.get_pull_request(full_name, number)

    def request_review(self, full_name: str, number: int, reviewers: list[str]) -> dict[str, Any]:
        self._require_auth()
        body = {"reviewers": [r for r in reviewers if r]}
        data = self._http.post(f"{self.api_base}/repos/{full_name}/pulls/{number}/requested_reviewers", data=body).json() or {}
        return {"requested": [str((u or {}).get("login") or "") for u in (data.get("requested_reviewers") or [])]}

    def list_reviews(self, full_name: str, number: int) -> list[VCSReview]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}/pulls/{number}/reviews").json() or []
        return [
            VCSReview(
                id=str(r.get("id") or ""), author=str((r.get("user") or {}).get("login") or ""),
                state=str(r.get("state") or "").casefold(), body=str(r.get("body") or ""),
                submitted_at=str(r.get("submitted_at") or ""),
            )
            for r in data
        ]

    def get_review_comments(self, full_name: str, number: int) -> list[dict[str, Any]]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}/pulls/{number}/comments").json() or []
        return [
            {
                "id": str(c.get("id") or ""), "path": str(c.get("path") or ""),
                "line": c.get("line"), "body": str(c.get("body") or ""),
                "author": str((c.get("user") or {}).get("login") or ""),
                "createdAt": str(c.get("created_at") or ""),
            }
            for c in data
        ]

    def reply_review_comment(self, full_name: str, number: int, comment_id: str,
                             body: str) -> dict[str, Any]:
        self._require_auth()
        data = self._http.post(
            f"{self.api_base}/repos/{full_name}/pulls/{number}/comments/{comment_id}/replies",
            data={"body": body},
        ).json() or {}
        return {"id": str(data.get("id") or ""), "url": str(data.get("html_url") or "")}

    # ── Checks / Actions ─────────────────────────────────────────────────────────
    def get_checks(self, full_name: str, ref: str) -> list[VCSCheck]:
        self._require_auth()
        checks: list[VCSCheck] = []
        runs = self._http.get(
            f"{self.api_base}/repos/{full_name}/commits/{ref}/check-runs?per_page=100"
        ).json() or {}
        for run in runs.get("check_runs", []) or []:
            checks.append(VCSCheck(
                name=str(run.get("name") or ""),
                status=str(run.get("status") or ""),
                conclusion=str(run.get("conclusion") or ""),
                url=str(run.get("html_url") or ""),
                details=str((run.get("output") or {}).get("summary") or "")[:400],
            ))
        statuses = self._http.get(f"{self.api_base}/repos/{full_name}/commits/{ref}/status").json() or {}
        for s in statuses.get("statuses", []) or []:
            checks.append(VCSCheck(
                name=str(s.get("context") or ""),
                status="completed", conclusion=str(s.get("state") or ""),
                url=str(s.get("target_url") or ""), details=str(s.get("description") or ""),
            ))
        return checks

    def get_workflows(self, full_name: str) -> list[dict[str, Any]]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repos/{full_name}/actions/workflows").json() or {}
        return [
            {"id": str(w.get("id") or ""), "name": str(w.get("name") or ""),
             "path": str(w.get("path") or ""), "state": str(w.get("state") or "")}
            for w in (data.get("workflows") or [])
        ]

    def get_workflow_runs(self, full_name: str, *, ref: str = "", limit: int = 20) -> list[VCSWorkflowRun]:
        self._require_auth()
        params = f"?per_page={min(limit, 100)}" + (f"&branch={ref}" if ref else "")
        data = self._http.get(f"{self.api_base}/repos/{full_name}/actions/runs{params}").json() or {}
        return [
            VCSWorkflowRun(
                id=str(r.get("id") or ""), name=str(r.get("name") or ""),
                status=str(r.get("status") or ""), conclusion=str(r.get("conclusion") or ""),
                branch=str(r.get("head_branch") or ""), url=str(r.get("html_url") or ""),
                created_at=str(r.get("created_at") or ""),
            )
            for r in (data.get("workflow_runs") or [])
        ]

    def get_job_logs(self, full_name: str, job_id: str) -> dict[str, Any]:
        self._require_auth()
        response = self._http.get(f"{self.api_base}/repos/{full_name}/actions/jobs/{job_id}/logs")
        return {"jobId": job_id, "log": response.body[-20_000:]}

    def rerun_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(f"{self.api_base}/repos/{full_name}/actions/runs/{run_id}/rerun", data={})
        return {"rerun": run_id}

    def cancel_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(f"{self.api_base}/repos/{full_name}/actions/runs/{run_id}/cancel", data={})
        return {"cancelled": run_id}


__all__ = ["GitHubProvider"]
