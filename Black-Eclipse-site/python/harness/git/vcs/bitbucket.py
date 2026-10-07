"""The Bitbucket Cloud provider — REST 2.0.

Bitbucket authenticates with an app password / access token sent as a Bearer
token (or Basic `user:app-password`). The internal model's `VCSPullRequest` maps
onto a Bitbucket pull request; `number` is the PR `id`. Reviews map onto the PR's
participants; checks map onto commit statuses and Pipelines.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import ProviderError, VCSProvider
from .http import HttpClient
from .models import (
    VCSBranch, VCSCheck, VCSCommit, VCSPullRequest, VCSRepository, VCSReview,
    VCSWorkflowRun,
)

API_BASE = "https://api.bitbucket.org/2.0"


def _map_state(pr: dict[str, Any]) -> str:
    state = str(pr.get("state") or "OPEN").casefold()
    if state == "merged":
        return "merged"
    return "open" if state == "open" else "closed"


def _map_pr(data: dict[str, Any]) -> VCSPullRequest:
    source = data.get("source") or {}
    dest = data.get("destination") or {}
    author = data.get("author") or {}
    return VCSPullRequest(
        provider="bitbucket",
        number=int(data.get("id") or 0),
        title=str(data.get("title") or ""),
        description=str(data.get("summary") or {}).get("raw") if isinstance(data.get("summary"), dict) else str(data.get("description") or ""),
        source_branch=str((source.get("branch") or {}).get("name") or ""),
        target_branch=str((dest.get("branch") or {}).get("name") or ""),
        author=str(author.get("display_name") or author.get("nickname") or ""),
        status=_map_state(data),
        draft=bool(data.get("draft")),
        mergeable=None,
        merged=_map_state(data) == "merged",
        url=str((data.get("links") or {}).get("html", {}).get("href") or ""),
        head_sha=str((source.get("commit") or {}).get("hash") or ""),
        created_at=str(data.get("created_on") or ""),
        updated_at=str(data.get("updated_on") or ""),
        labels=[str(r.get("name")) for r in (data.get("reviewers") or []) if r.get("name")],
        extra={"workspace": (data.get("workspace") or {}).get("slug")},
    )


class BitbucketProvider(VCSProvider):
    name = "bitbucket"
    supports_checks = True
    supports_workflows = True

    def __init__(self, *, token: Optional[str] = None, host: str = "", base_url: str = "") -> None:
        super().__init__(token=token, host=host or "bitbucket.org", base_url=base_url)
        self.api_base = (base_url.rstrip("/") + "/2.0" if base_url else API_BASE)
        self._http = HttpClient(token=self._token)

    def _require_auth(self) -> None:
        if not self.authenticated:
            raise ProviderError("AUTHENTICATION_FAILED", "No sign-in is configured for this service.")

    @staticmethod
    def _repo(full_name: str) -> str:
        return "/".join(HttpClient.quote(p) for p in full_name.split("/", 1))

    # ── Repositories / branches / commits ─────────────────────────────────────
    def get_repository(self, full_name: str) -> VCSRepository:
        self._require_auth()
        data = self._http.get(f"{self.api_base}/repositories/{self._repo(full_name)}").json() or {}
        return VCSRepository(
            provider="bitbucket", full_name=str(data.get("full_name") or full_name),
            name=str(data.get("name") or ""), owner=str((data.get("workspace") or {}).get("slug") or ""),
            default_branch=str((data.get("mainbranch") or {}).get("name") or "main"),
            private=bool(data.get("is_private")),
            url=str((data.get("links") or {}).get("html", {}).get("href") or ""),
        )

    def list_repositories(self, *, limit: int = 50) -> list[VCSRepository]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories?role=member&pagelen=" + str(min(limit, 100))
        ).json() or {}
        return [
            VCSRepository(
                provider="bitbucket", full_name=str(r.get("full_name") or ""),
                name=str(r.get("name") or ""), owner=str((r.get("workspace") or {}).get("slug") or ""),
                default_branch=str((r.get("mainbranch") or {}).get("name") or "main"),
                private=bool(r.get("is_private")),
                url=str((r.get("links") or {}).get("html", {}).get("href") or ""),
            )
            for r in (data.get("values") or [])
        ]

    def get_branches(self, full_name: str) -> list[VCSBranch]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/refs/branches?pagelen=100"
        ).json() or {}
        return [
            VCSBranch(name=str(b.get("name") or ""),
                      sha=str((b.get("target") or {}).get("hash") or ""))
            for b in (data.get("values") or [])
        ]

    def get_commits(self, full_name: str, *, ref: str = "", limit: int = 30) -> list[VCSCommit]:
        self._require_auth()
        suffix = f"/{HttpClient.quote(ref)}" if ref else ""
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/commits{suffix}?pagelen=" + str(min(limit, 100))
        ).json() or {}
        return [
            VCSCommit(sha=str(c.get("hash") or ""), message=str(c.get("message") or ""),
                      author=str((c.get("author") or {}).get("raw") or ""), date=str(c.get("date") or ""))
            for c in (data.get("values") or [])
        ]

    def create_branch(self, full_name: str, name: str, *, from_sha: str = "") -> VCSBranch:
        self._require_auth()
        target = from_sha
        if not target:
            repo = self.get_repository(full_name)
            commits = self.get_commits(full_name, ref=repo.default_branch, limit=1)
            target = commits[0].sha if commits else ""
        if not target:
            raise ProviderError("VALIDATION_FAILED", "The starting revision is unknown.")
        body = {"name": name, "target": {"hash": target}}
        data = self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/refs/branches", data=body
        ).json() or {}
        return VCSBranch(name=name, sha=str((data.get("target") or {}).get("hash") or target))

    # ── Pull requests ────────────────────────────────────────────────────────────
    def create_pull_request(self, full_name: str, *, title: str, source_branch: str,
                            target_branch: str, description: str = "", draft: bool = False) -> VCSPullRequest:
        self._require_auth()
        body = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": target_branch}},
            "summary": {"raw": description},
            "draft": draft,
        }
        data = self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests", data=body
        ).json() or {}
        return _map_pr(data)

    def get_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}"
        ).json() or {}
        pr = _map_pr(data)
        try:
            pr.checks = self.get_checks(full_name, pr.head_sha) if pr.head_sha else []
        except ProviderError:
            pr.checks = []
        return pr

    def list_pull_requests(self, full_name: str, *, state: str = "open", limit: int = 30) -> list[VCSPullRequest]:
        self._require_auth()
        state_param = {"open": "OPEN", "closed": "DECLINED", "merged": "MERGED"}.get(state, "OPEN")
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests"
            f"?state={state_param}&pagelen={min(limit, 100)}"
        ).json() or {}
        return [_map_pr(p) for p in (data.get("values") or [])]

    def update_pull_request(self, full_name: str, number: int, *, title: Optional[str] = None,
                            description: Optional[str] = None, state: Optional[str] = None,
                            target_branch: Optional[str] = None) -> VCSPullRequest:
        self._require_auth()
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["summary"] = {"raw": description}
        if target_branch is not None:
            body["destination"] = {"branch": {"name": target_branch}}
        if body:
            data = self._http.put(
                f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}", data=body
            ).json() or {}
        else:
            data = {}
        if state == "closed":
            return self.close_pull_request(full_name, number)
        return _map_pr(data) if data else self.get_pull_request(full_name, number)

    def close_pull_request(self, full_name: str, number: int) -> VCSPullRequest:
        self._require_auth()
        self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}/decline", data={}
        )
        return self.get_pull_request(full_name, number)

    def merge_pull_request(self, full_name: str, number: int, *, method: str = "merge",
                           delete_branch: bool = False) -> VCSPullRequest:
        self._require_auth()
        strategy = {"merge": "merge_commit", "squash": "squash", "rebase": "rebase_fast_forward"}.get(method, "merge_commit")
        data = self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}/merge",
            data={"merge_strategy": strategy, "close_source_branch": delete_branch},
        ).json() or {}
        if _map_state(data) != "merged":
            raise ProviderError("CONFLICT", "The change could not be merged automatically.", recoverable=True)
        return self.get_pull_request(full_name, number)

    def request_review(self, full_name: str, number: int, reviewers: list[str]) -> dict[str, Any]:
        self._require_auth()
        # Bitbucket reviewers are accounts (uuid); a username lookup is required.
        requested: list[str] = []
        for who in reviewers:
            if not who:
                continue
            try:
                self._http.put(
                    f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}"
                    f"?fields=reviewers",
                    data={"reviewers": [{"uuid": who}]},
                )
                requested.append(who)
            except ProviderError:
                continue
        return {"requested": requested}

    def list_reviews(self, full_name: str, number: int) -> list[VCSReview]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}"
            "?fields=participants"
        ).json() or {}
        reviews: list[VCSReview] = []
        for participant in data.get("participants") or []:
            user = participant.get("user") or {}
            approved = bool(participant.get("approved"))
            role = str(participant.get("role") or "")
            state = "approved" if approved else ("changes_requested" if role == "REVIEWER" else "pending")
            reviews.append(VCSReview(
                id=str(user.get("uuid") or user.get("nickname") or ""),
                author=str(user.get("display_name") or user.get("nickname") or ""),
                state=state, body="", submitted_at="",
            ))
        return reviews

    def get_review_comments(self, full_name: str, number: int) -> list[dict[str, Any]]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}/comments?pagelen=100"
        ).json() or {}
        comments: list[dict[str, Any]] = []
        for c in data.get("values") or []:
            user = c.get("user") or {}
            inline = c.get("inline") or {}
            comments.append({
                "id": str(c.get("id") or ""), "path": str(inline.get("path") or ""),
                "line": inline.get("to"),
                "body": str((c.get("content") or {}).get("raw") or ""),
                "author": str(user.get("display_name") or user.get("nickname") or ""),
                "createdAt": str(c.get("created_on") or ""),
            })
        return comments

    def reply_review_comment(self, full_name: str, number: int, comment_id: str,
                             body: str) -> dict[str, Any]:
        self._require_auth()
        data = self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pullrequests/{number}/comments",
            data={"content": {"raw": body}, "parent": {"id": int(comment_id) if comment_id.isdigit() else None}},
        ).json() or {}
        return {"id": str(data.get("id") or ""), "url": ""}

    # ── Statuses / pipelines ─────────────────────────────────────────────────────
    def get_checks(self, full_name: str, ref: str) -> list[VCSCheck]:
        self._require_auth()
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/commit/{HttpClient.quote(ref)}/statuses"
            "?pagelen=100"
        ).json() or {}
        checks: list[VCSCheck] = []
        for s in data.get("values") or []:
            state = str(s.get("state") or "").casefold()
            checks.append(VCSCheck(
                name=str(s.get("key") or s.get("name") or "status"),
                status="completed" if state in ("successful", "failed", "stopped") else "in_progress",
                conclusion={"successful": "success", "failed": "failure", "stopped": "cancelled"}.get(state, ""),
                url=str(s.get("url") or ""), details=str(s.get("description") or ""),
            ))
        return checks

    def get_workflows(self, full_name: str) -> list[dict[str, Any]]:
        return []

    def get_workflow_runs(self, full_name: str, *, ref: str = "", limit: int = 20) -> list[VCSWorkflowRun]:
        self._require_auth()
        suffix = f"?target.ref_name={HttpClient.quote(ref)}&" if ref else "?"
        data = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pipelines{suffix}"
            f"pagelen={min(limit, 100)}"
        ).json() or {}
        return [
            VCSWorkflowRun(
                id=str(p.get("uuid") or ""), name=f"pipeline {p.get('build_number')}",
                status=str(p.get("state", {}).get("name") or ""),
                conclusion=str((p.get("state", {}).get("result") or {}).get("name") or ""),
                branch=str((p.get("target") or {}).get("ref_name") or ""),
                url=str((p.get("links") or {}).get("html", {}).get("href") or ""),
                created_at=str(p.get("created_on") or ""),
            )
            for p in (data.get("values") or [])
        ]

    def get_job_logs(self, full_name: str, job_id: str) -> dict[str, Any]:
        self._require_auth()
        response = self._http.get(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pipelines/{job_id}/steps"
        )
        return {"jobId": job_id, "log": response.body[-20_000:]}

    def rerun_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pipelines/{run_id}/stopPipeline", data={}
        )
        return {"rerun": run_id}

    def cancel_workflow(self, full_name: str, run_id: str) -> dict[str, Any]:
        self._require_auth()
        self._http.post(
            f"{self.api_base}/repositories/{self._repo(full_name)}/pipelines/{run_id}/stopPipeline", data={}
        )
        return {"cancelled": run_id}


__all__ = ["BitbucketProvider"]
