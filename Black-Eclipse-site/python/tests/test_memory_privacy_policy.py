"""Memory policy and privacy controls (Phase 6) — local-user switches with hard
safety floors.

Correctness:
  * memory can be turned completely off (even explicit requests refuse);
  * automatic learning can be off independently of explicit requests;
  * retention duration applies only to automatic memory;
  * per-category capture/recall policy can TIGHTEN (never widen) behaviour;
  * semantic indexing is recorded as an intent but changes nothing (deferred);
  * secrets/credentials/dumps/financial facts are still refused under every
    policy setting — a setting cannot bypass a safety floor;
  * new policy keys survive a store reopen (migration/persistence).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.policy import PolicyError, category_policy, derived_flags


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-privacy-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _write(service, content="A durable fact", **kw):
    kw.setdefault("memory_type", "semantic")
    kw.setdefault("source", "manual")
    kw.setdefault("scope", "general")
    return service.write_memory(content=content, **kw)


# ── Defaults / new keys ─────────────────────────────────────────────────────


def test_new_privacy_defaults(service):
    settings = service.policy.get_all()
    assert settings["memory_enabled"] is True
    assert settings["semantic_indexing_enabled"] is False
    assert settings["capture_policy"] == {}
    assert settings["recall_policy"] == {}
    assert settings["memory_in_diagnostics"] is True


def test_derived_flags_honour_memory_enabled():
    flags = derived_flags({"memory_enabled": False, "memory_mode": "automatic_selective",
                           "skill_learning_mode": "automatic_selective"})
    assert flags["auto_capture_enabled"] is False
    assert flags["auto_suggest_enabled"] is False


def test_category_policy_rejects_invalid_value(service):
    with pytest.raises(PolicyError):
        service.policy.set("capture_policy", {"preference": "sometimes"})


# ── Memory completely off ───────────────────────────────────────────────────


def test_memory_off_refuses_even_explicit_save(service):
    service.policy.set("memory_enabled", False)
    from harness.eclipse_memory.service import MemoryWriteError

    with pytest.raises(MemoryWriteError):
        _write(service, source="explicit_user", memory_type="preference",
               scope="user", scope_id="u1")
    assert service.store.list_memories(include_inactive=True) == []


def test_memory_off_is_not_bypassed_by_the_gate(service):
    # decide_turn may still emit a save decision; the write pipeline refuses it.
    service.policy.set("memory_enabled", False)
    decision = service.decide_turn("remember that I prefer concise answers", user_id="u1")
    outcome = service.commit_decision(decision, user_id="u1")
    assert outcome.get("ok") is False
    assert service.store.list_memories(include_inactive=True) == []


def test_memory_on_after_re_enable(service):
    service.policy.set("memory_enabled", False)
    service.policy.set("memory_enabled", True)
    memory = _write(service)
    assert memory["status"] == "active"


# ── Automatic learning off ──────────────────────────────────────────────────


def test_automatic_learning_off_keeps_explicit(service):
    service.policy.set("memory_mode", "off")
    # Automatic incidental capture creates nothing.
    decision = service.decide_turn("I prefer concise answers", user_id="u1")
    assert decision.outcome in ("history_only", "ignore")
    # Explicit still works.
    explicit = service.decide_turn("remember that I prefer concise answers", user_id="u1")
    assert explicit.outcome == "save"


# ── Category capture policy ─────────────────────────────────────────────────


def test_capture_policy_deny_tightens(service):
    service.policy.set("capture_policy", {"preference": "deny"})
    from harness.eclipse_memory.service import MemoryWriteError

    with pytest.raises(MemoryWriteError):
        _write(service, memory_type="preference", source="explicit_user",
               scope="user", scope_id="u1")
    # A different category is unaffected.
    assert _write(service, memory_type="semantic")["status"] == "active"


def test_capture_policy_cannot_bypass_a_correction(service):
    # A correction supersedes in place and is exempt from category capture policy
    # (blocking an explicit correction would be worse than the over-broad rule).
    service.policy.set("capture_policy", {"correction": "deny"})
    result = service.record_correction(wrong="x", correction="y", scope="user")
    assert result["memory"]["memoryType"] == "correction"


# ── Category recall policy ──────────────────────────────────────────────────


def test_recall_policy_deny_removes_from_results(service):
    _write(service, content="A semantic fact about shipping lanes", memory_type="semantic", scope="general")
    service.policy.set("recall_policy", {"semantic": "deny"})
    result = service.retrieve(query="shipping lanes", actor_scope="user")
    assert all(m["memoryType"] != "semantic" for m in result.memories)
    assert any(e["reason"] == "recall denied by policy" for e in result.diagnostics["excluded"])


def test_recall_policy_cannot_widen_scope(service):
    # Even with recall policy "allow", another user's scoped memory is never
    # returned — recall policy is not an authorization bypass.
    service.write_memory(
        memory_type="semantic", content="u2's private fact", source="manual",
        scope="user", scope_id="u2",
    )
    service.policy.set("recall_policy", {"semantic": "allow"})
    result = service.retrieve(query="private fact", actor_scope="user", scope_id="u1")
    assert all(m.get("scopeId") != "u2" for m in result.memories)


# ── Safety floors hold under every setting ──────────────────────────────────


def test_safety_floors_cannot_be_disabled(service):
    # Enabling everything possible must not permit a secret / financial fact.
    service.policy.set("memory_enabled", True)
    service.policy.set("capture_policy", {"semantic": "allow"})
    from harness.eclipse_memory.decision import authorize_proposal

    secret = authorize_proposal(
        content="password hunter2", provenance="ui_save", user_id="u1",
    )
    assert secret.outcome == "ignore"
    financial = authorize_proposal(
        content="AAPL share price is 190.50", provenance="ui_save", user_id="u1",
    )
    assert financial.outcome == "ignore"
    assert financial.financial is True


# ── Persistence / migration ─────────────────────────────────────────────────


def test_new_policy_keys_persist_across_reopen(service):
    service.policy.set("memory_enabled", False)
    service.policy.set("recall_policy", {"semantic": "deny"})
    path = service.store.path
    service.close()
    reopened = EclipseMemoryService(EclipseMemoryStore(path))
    try:
        settings = reopened.policy.get_all()
        assert settings["memory_enabled"] is False
        assert settings["recall_policy"] == {"semantic": "deny"}
    finally:
        reopened.close()


def test_unknown_category_value_falls_back_safely(service):
    # A hand-edited invalid value is not honoured (treated as unspecified).
    service.store._db.execute(
        "INSERT INTO MemoryPolicy (key, value, updatedAt) VALUES ('recall_policy', ?, ?)",
        ('{"semantic": "banana"}', "2026-01-01T00:00:00.000Z"),
    )
    service.store._db.commit()
    settings = service.policy.get_all()
    assert category_policy(settings, "recall_policy", "semantic") == ""
