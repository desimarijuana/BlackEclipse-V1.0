"""Concurrency + race tests.

Security decisions may occur concurrently, so the single-use approval claim must
authorize exactly one caller, capability revocation must take effect immediately,
and a policy reload during evaluation must never crash or weaken a decision.
"""

from __future__ import annotations

import os
import tempfile
import threading

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-conc-"), "agent-memory.db"),
)

from harness.security.gateway import SecurityGateway
from harness.security.models import (
    ACTION_FS_DELETE,
    AuthorizationRequest,
    Decision,
    PolicyProfile,
)


def _gateway():
    from harness.persistence import AgentMemoryStore
    from harness.mcp.approvals import ApprovalStore

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-sec-conc-db-"), "agent-memory.db"))
    approvals = ApprovalStore(store)
    return SecurityGateway(store=store, approvals=approvals, profile=PolicyProfile.SECURE), approvals


def test_simultaneous_approval_claim_is_single_use():
    gw, approvals = _gateway()
    request = AuthorizationRequest(action="filesystem.write", resource="src/x.py")
    # Create the pending approval.
    pending = gw.authorize(request)
    assert pending.decision is Decision.APPROVAL_REQUIRED
    approvals.decide(pending.approval_id, approve=True)

    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        decision = gw.authorize(request, claim_approval=True)
        with lock:
            results.append(decision.allowed)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    assert results.count(False) == 7


def test_capability_revoked_during_action_is_denied_next():
    gw = SecurityGateway(profile=PolicyProfile.SECURE)
    cap = gw.issue_capability(subject="agent", action=ACTION_FS_DELETE,
                              resource="build/**", scope="ws", ttl_seconds=60)
    first = gw.authorize(AuthorizationRequest(action=ACTION_FS_DELETE, resource="build/tmp",
                                              workspace="ws", actor="agent"))
    assert first.decision is Decision.ALLOW
    gw.revoke_capability(cap.id)
    second = gw.authorize(AuthorizationRequest(action=ACTION_FS_DELETE, resource="build/tmp",
                                               workspace="ws", actor="agent"))
    assert second.decision is not Decision.ALLOW


def test_policy_reload_during_concurrent_evaluation_does_not_crash():
    gw = SecurityGateway(profile=PolicyProfile.DEVELOPER)
    errors: list[Exception] = []
    stop = threading.Event()

    def evaluator():
        try:
            while not stop.is_set():
                gw.authorize(AuthorizationRequest(action="filesystem.read", resource="a.py"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reloader():
        try:
            for _ in range(20):
                gw.reload_policy({"project": {"defaults": {"filesystem": "allow"}}})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    workers = [threading.Thread(target=evaluator) for _ in range(4)]
    for w in workers:
        w.start()
    reloader()
    stop.set()
    for w in workers:
        w.join()
    assert errors == []


def test_concurrent_session_cleanup_revokes_capabilities():
    gw = SecurityGateway(profile=PolicyProfile.SECURE)
    ctx = gw.open_session(session_id="race", workspace_id="ws", agent_id="agent")
    gw.issue_capability(subject="agent", action=ACTION_FS_DELETE, resource="ws/**",
                        scope="ws", ttl_seconds=60, session_id="race")
    gw.close_session("race")
    d = gw.authorize(
        AuthorizationRequest(action=ACTION_FS_DELETE, resource="ws/f", workspace="ws", actor="agent"),
        context=ctx,
    )
    assert d.decision is Decision.DENY
