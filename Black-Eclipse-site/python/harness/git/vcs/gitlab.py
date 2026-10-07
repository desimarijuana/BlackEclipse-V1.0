"""The GitLab provider — REST v4, where a "merge request" is the PR concept.

GitLab authenticates with a `PRIVATE-TOKEN` header. The internal model's
`VCSPullRequest` maps onto a GitLab merge request: `number` is the MR `iid`.
Reviews map onto GitLab approvals + notes; checks map onto pipelines/jobs.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import ProviderError, VCSProvider
from .http import HttpClient
from .models import (
    VCSBranch, VCSCheck, VCSCommit, VCSPullRequest, VCSRepository, VCSReview,
    VCSWorkflowRun,
)

API_BASE = "https://gitlab.com/api/v4"


def _map_state(mr: dict[str, Any]) -> str:
    state = str(mr.get("state") or "opened")
    if state == "merged":
        return "merged"
    return "open" if state == "opened" else "closed"


def _map_mr(data: dict[str, Any]) -> VCSPullRequest:
    author = data.get("author") or {}
    merge_status = str(data.get("detailed_merge_status") or data.get("merge_status") or "")
    mergeable: Optional[bool]
    if merge_status in ("", "not_approved", "checking", "unchecked"):
        mergeable = None
    else:
        mergeable = merge_status in ("can_be_merged", "mergeable")
    return VCSPullRequest(
        provider="gitlab",
        number=int(data.get("iid") or 0),
        title=str(data.get("title") or ""),
        description=str(data.get("description") or ""),
        source_branch=str(data.get("source_branch") or ""),
        target_branch=str(data.get("target_branch") or ""),
        author=str(author.get("username") or ""),
        status=_map_state(data),
        draft=bool(data.get("draft") or data.get("work_in_progress")),
        mergeable=mergeable,
        merged=_map_state(data) == "merged",
        url=str(data.get("web_url") or ""),
        head_sha=str(data.get("sha") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        labels=[str(x) for x in (data.get("labels") or [])],
        extra={"projectId": data.get("project_id")},
    )


class GitLabProvider(VCSProvider):
    name = "gitlab"
    supports_checks = True
    supports_workflows = True

    def __init__(self, *, token: Optional[str] = None, host: str = "", base_url: str = "") -> None:
        super().__init__(token=token, host=host or "gitlab.com", base_url=base_url)
        self.api_base = (base_url.rstrip("/") + "/api/v4" if base_url
                         else (API_BASE if self.host.casefold() == "gitlab.com"
                               else f"https://{self.host}/api/v4"))
        headers = {"PRIVATE-TOKEN": self._token} if self._token else {}
        self._http = HttpClient(token="", extra_headers=headers)

    def _require_auth(self) -> None:
        if not self.authenticated:
            raise ProviderError("AUTHENTICATION_FAILED", "No sign-in is configured for this service.")

    @staticmethod
    def _project(full_name: str) -> str:
        return HttpClient.quote(full_name)

    # ── Repositories / branches / commits ─────────────────────────────────────
    def get_repository(self, full_name: str) -> VCSRepository:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/projects/{self._project(full_name)}").json() or {}
        return VCSRepository(
            provider="gitlab", full_name=str(data.get("path_with_namespace") or full_name),
            name=str(data.get("name") or ""),
            owner=str((data.get("namespace") or {}).get("full_path") or ""),
            default_branch=str(data.get("default_branch") or "main"),
            private=str(data.get("visibility") or "private") != "public",
            url=str(data.get("web_url") or ""),
        )

    def list_repositories(self, *, limit: int = 50) -> list[VCSRepository]:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/projects?membership=true&per_page={min(limit, 100)}").json() or []
        return [
            VCSRepository(
                provider="gitlab", full_name=str(p.get("path_with_namespace") or ""),
                name=str(p.get("name") or ""),
                owner=str((p.get("namespace") or {}).get("full_path") or ""),
                default_branch=str(p.get("default_branch") or "main"),
                private=str(p.get("visibility") or "private") != "public",
                url=str(p.get("web_url") or ""),
            )
            for p in data
        ]

    def get_branches(self, full_name: str) -> list[VCSBranch]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/repository/branches"
        ).json() or []
        return [
            VCSBranch(name=str(b.get("name") or ""), sha=str((b.get("commit") or {}).get("id") or ""),
                      protected=bool(b.get("protected")))
            for b in data
        ]

    def get_commits(self, full_name: str, *, ref: str = "", limit: int = 30) -> list[VCSCommit]:
        self._require_auth()
        params = f"?per_page={min(limit, 100)}" + (f"&ref_name={ref}" if ref else "")
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/repository/commits{params}"
        ).json() or []
        return [
            VCSCommit(sha=str(c.get("id") or ""), message=str(c.get("message") or ""),
                      author=str(c.get("author_name") or ""), date=str(c.get("committed_date") or ""))
            for c in data
        ]

    def create_branch(self, full_name: str, name: str, *, from_sha: str = "") -> VCSBranch:
        self._require_auth()
        ref = from_sha
        if not ref:
            repo = self.get_repository(full_name)
            commits = self.get_commits(full_name, ref=repo.default_branch, limit=1)
            ref = commits[0].sha if commits else "main"
        body = {"branch": name, "ref": ref}
        data = self._http.post(
            f"{self.api_base}/projects/{self._project(full_name)}/repository/branches", data=body
        ).json() or {}
        return VCSBranch(name=name, sha=str((data.get("commit") or {}).get("id") or ref))

    # ── Merge requests ───────────────────────────────────────────────────────────
    def create_pull_request(self, full_name: str, *, title: str, source_branch: str,
                            target_branch: str, description: str = "", draft: bool = False) -> VCSPullRequest:
        self._require_auth()
        body = {
            "source_branch": source_branch, "target_branch": target_branch,
            "title": ("Draft: " + title) if draft else title, "description": description,
        }
        data = self._http.post(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests", data=body
        ).json() or {}
        return _map_mr(data)

    def get_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}"
        ).json() or {}
        pr = _map_mr(data)
        try:
            pr.checks = self.get_checks(full_name, pr.head_sha)
        except ProviderError:
            pr.checks = []
        return pr

    def list_pull_requests(self, full_name: str, *, state: str = "open", limit: int = 30) -> list[VCSPullRequest]:
        self._require_auth()
        state_param = {"open": "opened", "closed": "closed", "merged": "merged"}.get(state, "opened")
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests"
            f"?state={state_param}&per_page={min(limit, 100)}"
        ).json() or []
        return [_map_mr(m) for m in data]

    def update_pull_request(self, full_name: str, number: int, *, title: Optional[str] = None,
                            description: Optional[str] = None, state: Optional[str] = None,
                            target_branch: Optional[str] = None) -> VCSPullRequest:
        self._require_auth()
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if target_branch is not None:
            body["target_branch"] = target_branch
        if state == "closed":
            body["state_event"] = "close"
        elif state == "open":
            body["state_event"] = "reopen"
        data = self._http.put(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}", data=body
        ).json() or {}
        return _map_mr(data)

    def close_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        return self.update_pull_request(full_name, number, state="closed")

    def merge_pull_request(self, full_name: str, number: int, *, method: str = "merge",
                           delete_branch: bool = False) -> VCSPullRequest:
        self._require_auth()
        body: dict[str, Any] = {}
        if method in ("squash", "rebase"):
            body["squash"] = method == "squash"
        data = self._http.put(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}/merge", data=body
        ).json() or {}
        if str(data.get("state") or "") != "merged":
            raise ProviderError("CONFLICT", "The change could not be merged automatically.", recoverable=True)
        if delete_branch:
            try:
                pr = self.get_pull_request(full_name, number)
                if pr.source_branch:
                    self._http.delete(
                        f"{self.api_base}/projects/{self._project(full_name)}/repository/branches/"
                        f"{HttpClient.quote(pr.source_branch)}"
                    )
            except ProviderError:
                pass
        return self.get_pull_request(full_name, number)

    def request_review(self, full_name: str, number: int, reviewers: list[str]) -> dict[str, Any]:
        self._require_auth()
        requested: list[str] = []
        for who in reviewers:
            if not who:
                continue
            users = self._http.get(f"{self.api_base}/users?username={HttpClient.quote(who)}").json() or []
            if not users:
                continue
            user_id = users[0].get("id")
            try:
                self._http.put(
                    f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}"
                    f"/reviewers?reviewer_ids[]={user_id}", data={}
                )
                requested.append(who)
            except ProviderError:
                continue
        return {"requested": requested}

    def list_reviews(self, full_name: str, number: int) -> list[VCSReview]:
        self._require_auth()
        # GitLab expresses review as approvals; surface the approval state as a review.
        reviews: list[VCSReview] = []
        try:
            approvals = self._http.get(
                f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}/approvals"
            ).json() or {}
        except ProviderError:
            approvals = {}
        for who in approvals.get("approved_by", []) or []:
            user = (who or {}).get("user") or {}
            reviews.append(VCSReview(
                id=str(user.get("id") or ""), author=str(user.get("username") or ""),
                state="approved", body="", submitted_at="",
            ))
        return reviews

    def get_review_comments(self, full_name: str, number: int) -> list[dict[str, Any]]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}/notes"
            "?per_page=100&sort=asc"
        ).json() or []
        return [
            {
                "id": str(n.get("id") or ""), "path": str((n.get("position") or {}).get("new_path") or ""),
                "line": (n.get("position") or {}).get("new_line"),
                "body": str(n.get("body") or ""), "author": str((n.get("author") or {}).get("username") or ""),
                "createdAt": str(n.get("created_at") or ""),
            }
            for n in data if not n.get("system")
        ]

    def reply_review_comment(self, full_name: str, number: int, comment_id: str,
                             body: str) -> dict[str, Any]:
        self._require_auth()
        # GitLab does not thread a reply; post a new note referencing the original.
        data = self._http.post(
            f"{self.api_base}/projects/{self._project(full_name)}/merge_requests/{number}/notes",
            data={"body": body},
        ).json() or {}
        return {"id": str(data.get("id") or ""), "url": ""}

    # ── Pipelines / jobs ──────────────────────────────────────────────────────────
    def get_checks(self, full_name: str, ref: str) -> list[VCSCheck]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/pipelines?ref={HttpClient.quote(ref)}"
            "&per_page=10"
        ).json() or []
        checks: list[VCSCheck] = []
        for pipeline in data:
            status = str(pipeline.get("status") or "")
            checks.append(VCSCheck(
                name=f"pipeline #{pipeline.get('id')}", status=_pipeline_status(status),
                conclusion="" if status in ("running", "pending", "created") else status,
                url=str(pipeline.get("web_url") or ""),
            ))
        return checks

    def get_workflows(self, full_name: str) -> list[dict[str, Any]]:
        # GitLab's CI is defined in .gitlab-ci.yml, not a workflow registry.
        return []

    def get_workflow_runs(self, full_name: str, *, ref: str = "", limit: int = 20) -> list[VCSWorkflowRun]:
        self._require_auth()
        params = f"?per_page={min(limit, 100)}" + (f"&ref={HttpClient.quote(ref)}" if ref else "")
        data = self._http.get(
            f"{self.api_base}/projects/{self._project(full_name)}/pipelines{params}"
        ).json() or []
        return [
            VCSWorkflowRun(
                id=str(p.get("id") or ""), name=f"pipeline #{p.get('id')}",
                status=_pipeline_status(str(p.get("status") or "")), conclusion=str(p.get("status") or ""),
                branch=str(p.get("ref") or ""), url=str(p.get("web_url") or ""),
                created_at=str(p.get("created_at") or ""),
            )
            for p in data
        ]

    def get_job_logs(self, full_name: str, job_id: str) -> dict[str, Any]:
        self._require_auth()
        # A build trace can be large; the client caps the response size.
        url = f"{self.api_base}/projects/{self._project(full_name)}/jobs/{job_id}/trace"
        response = self._http.get(url)
        return {"jobId": job_id, "log": response.body[-20_000:]}

    def rerun_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(
            f"{self.api_base}/projects/{self._project(full_name)}/pipelines/{run_id}/retry", data={}
        )
        return {"rerun": run_id}

    def cancel_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(
            f"{self.api_base}/projects/{self._project(full_name)}/pipelines/{run_id}/cancel", data={}
        )
        return {"cancelled": run_id}


def _pipeline_status(status: str) -> str:
    return {
        "created": "queued", "waiting_for_resource": "queued", "preparing": "queued",
        "pending": "queued", "running": "in_progress", "success": "completed",
        "failed": "completed", "canceled": "completed", "skipped": "completed",
        "manual": "queued", "scheduled": "queued",
    }.get(status, "queued")


__all__ = ["GitLabProvider"]
