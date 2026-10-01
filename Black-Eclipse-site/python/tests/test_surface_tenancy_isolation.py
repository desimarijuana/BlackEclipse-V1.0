"""Phase 11 G2 — cross-tenant isolation across the four new surfaces.

This MIRRORS `test_identity_tenancy_boundary.py` rather than restating it: the
identity/tenancy boundary still reports `authentication=False`,
`multiUserSafe=False`, `tenancy='single-user-local'`,
`scopeFiltering='caller-supplied-labels'`. On top of that, each new surface —
jobs, code tasks, artifacts and code workspaces — carries a `scopeId` FILTER:

  * a read with a different `scopeId` returns nothing (and is refused/emptied);
  * a request-BODY `scopeId` grants NO access to a mutation — `require_operator`
    remains the only authorization.

A scope label never widens what is permitted.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-surface-tenancy-"), "agent-memory.db"),
)
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(
    tempfile.mkdtemp(prefix="be-surface-cfg-"), "mcp-servers.json"
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


def _main():
    from harness import main as main_module

    return main_module


@pytest.fixture(scope="module")
def client():
    with TestClient(_main().app) as test_client:
        yield test_client


# ── The boundary is unchanged ─────────────────────────────────────────────────


def test_identity_boundary_is_unchanged_by_phase_11():
    boundary = _main().identity_boundary()
    assert boundary["authentication"] is False
    assert boundary["multiUserSafe"] is False
    assert boundary["tenancy"] == "single-user-local"
    assert boundary["scopeFiltering"] == "caller-supplied-labels"


# ── Jobs ─────────────────────────────────────────────────────────────────────


def test_jobs_are_filtered_by_scope(client):
    from harness.jobs.model import JobDefinition, JobTarget
    from harness.persistence import now_iso

    store = _main().service.jobs_store()
    now = now_iso()
    job = JobDefinition(
        id="job_scope_alpha", name="Alpha brief", kind="manual",
        target=JobTarget(kind="objective", objective="x"),
        scope_id="alpha", created_at=now, updated_at=now,
    )
    store.save_job(job)

    alpha = client.get("/jobs", params={"scopeId": "alpha"}).json()["jobs"]
    beta = client.get("/jobs", params={"scopeId": "beta"}).json()["jobs"]
    assert any(j["id"] == "job_scope_alpha" for j in alpha)
    assert not any(j["id"] == "job_scope_alpha" for j in beta)
    store.delete_job("job_scope_alpha")


def test_body_scope_id_does_not_authorize_a_job_mutation(monkeypatch):
    # A remote caller supplying scopeId in the body still cannot create a job.
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    with TC(_main().app, client=("203.0.113.9", 5555)) as remote:
        res = remote.post("/jobs", json={
            "kind": "manual", "scopeId": "admin",
            "target": {"kind": "objective", "objective": "x"},
        })
    assert res.status_code == 403


# ── Code tasks ───────────────────────────────────────────────────────────────


def test_code_tasks_are_isolated_by_scope(client):
    service = _main().service
    tasks = service.code_tasks()
    now = _main().now_iso()
    for run_id, scope in (("task_alpha", "alpha"), ("task_beta", "beta")):
        service.store.create_run(run_id, "code-agent", {"query": "x"}, user_id=scope)
        tasks.record_created(run_id, workspace_id=None, autonomy="plan_only", scope_id=scope)

    alpha = {t["id"] for t in tasks.list(scope_id="alpha")}
    beta = {t["id"] for t in tasks.list(scope_id="beta")}
    assert "task_alpha" in alpha and "task_alpha" not in beta
    assert "task_beta" in beta and "task_beta" not in alpha


# ── Code workspaces ──────────────────────────────────────────────────────────


def test_code_workspaces_are_not_enumerable_across_scopes(client):
    service = _main().service
    store = service.code_store
    store.save_workspace("ws_alpha", "/tmp/a", "rev", "worktree", scope_id="alpha")
    store.save_workspace("ws_beta", "/tmp/b", "rev", "worktree", scope_id="beta")

    alpha = {w["id"] for w in store.list_workspaces(scope_id="alpha")}
    beta = {w["id"] for w in store.list_workspaces(scope_id="beta")}
    assert "ws_alpha" in alpha and "ws_alpha" not in beta
    assert "ws_beta" in beta and "ws_beta" not in alpha
    # A direct read across scopes returns nothing at all.
    assert store.get_workspace("ws_alpha", scope_id="beta") is None


# ── Artifacts ────────────────────────────────────────────────────────────────


def test_artifacts_are_refused_across_scopes(client, tmp_path, monkeypatch):
    from harness.jobs.delivery import ArtifactAdapter, DeliverySummary

    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from harness.jobs.model import JobDefinition, JobTarget
    from harness.persistence import now_iso

    service = _main().service
    store = service.jobs_store()
    now = now_iso()
    job = JobDefinition(
        id="job_art", name="Alpha report", kind="manual",
        target=JobTarget(kind="objective", objective="x"),
        scope_id="alpha", created_at=now, updated_at=now,
    )
    store.save_job(job)
    run = store.start_run("job_art", triggered_by="manual", scheduled_for=now,
                          run_id="run_art_alpha", scope_id="alpha")
    store.finish_run(run["id"], status="ok", run_id="run_art_alpha")

    summary = DeliverySummary(title="Alpha report", answer="hi", outcome_line="Ran",
                              status="ok", run_id="run_art_alpha")
    import asyncio
    asyncio.run(ArtifactAdapter(None).deliver(job, "run_art_alpha", summary))

    ok = client.get(f"/jobs/job_art/runs/{run['id']}/artifact", params={"scopeId": "alpha"})
    assert ok.status_code == 200
    assert ok.json()["artifact"]["report.md"]

    refused = client.get(f"/jobs/job_art/runs/{run['id']}/artifact", params={"scopeId": "beta"})
    assert refused.status_code == 404

    store.delete_job("job_art")


# ── A remote read is refused regardless of scope ─────────────────────────────


def test_every_operator_gated_new_read_route_refuses_a_non_operator(monkeypatch):
    # `/jobs` and `/code/workspaces` carry `require_operator` (the jobs convention
    # and the code workspace read). A directly reachable runtime must not expose
    # them to an unauthenticated caller, whatever scopeId the body carries.
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    with TC(_main().app, client=("203.0.113.9", 5555)) as remote:
        assert remote.get("/jobs", params={"scopeId": "alpha"}).status_code == 403
        assert remote.get("/code/workspaces", params={"scopeId": "alpha"}).status_code == 403
