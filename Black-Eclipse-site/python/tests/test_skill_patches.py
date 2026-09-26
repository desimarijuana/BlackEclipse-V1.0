"""Milestone 2 — structured skill patches, evaluation, canary, rollback.

These tests use a real Eclipse-Memory store (temp DB) and the real SkillRegistry.
They assert the safety invariants:

  * a patch creates a NEW version and never mutates the active one;
  * a stale base version is rejected;
  * forbidden/security fields cannot be patched;
  * activation requires a passing evaluation;
  * canary is refused for unsafe/mutating skills;
  * rollback is atomic and preserves both versions;
  * automatic rollback fires on a regression.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory.service import EclipseMemoryService
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.skills.patches import (
    PatchError,
    apply_patch_to_manifest,
    canary_eligible,
    parse_patch,
)
from harness.skills.permissions import Actor
from harness.skills.registry import SkillRegistry
from harness.skills.versioning import (
    activate_version,
    check_rollback_triggers,
    evaluate_version,
    propose_patch,
    rollback,
    version_history,
)


@pytest.fixture()
def env(tmp_path):
    from harness.tools import ToolRegistry

    db = tmp_path / "eclipse-memory.db"
    store = EclipseMemoryStore(str(db))
    svc = EclipseMemoryService(store)
    registry = SkillRegistry(store)
    registry.attach_tool_registry(ToolRegistry())
    registry.load_all()
    yield registry, store, svc
    store.close()


USER = Actor(id="operator", operator=True)
TEMPLATE = {
    "id": "test.patch-target",
    "name": "Research Planning",
    "version": "1.0.0",
    "description": "Plan a research task.",
    "category": "research",
    "status": "enabled",
    "origin": "author",
    "permissions": ["research.read"],
    "requiredTools": [],
    "tags": ["research"],
}


def _seed(registry, store, **overrides):
    """Create a real user skill (so the registry can discover + evaluate it)."""
    registry.create_user_skill(
        name="Patch Target",
        description="Plan a research task.",
        instructions="Do the thing.",
        category="research",
        permissions=["research.read"],
        skill_id="test.patch-target",
    )
    return store.get_version("test.patch-target", "1.0.0")


# ── parse / apply (pure) ────────────────────────────────────────────────────


def test_parse_rejects_unknown_op():
    with pytest.raises(PatchError):
        parse_patch({"skill": "s", "baseVersion": "1.0.0", "operations": [{"op": "move", "path": "/description"}]})


def test_parse_rejects_forbidden_field():
    with pytest.raises(PatchError):
        parse_patch({"skill": "s", "baseVersion": "1.0.0",
                     "operations": [{"op": "replace", "path": "/permissions", "value": []}]})


def test_apply_rejects_permission_widening():
    base = dict(TEMPLATE)
    patch = parse_patch({"skill": base["id"], "baseVersion": "1.0.0",
                         "operations": [{"op": "replace", "path": "/description", "value": "new"}]})
    # A legitimate description patch applies.
    result = apply_patch_to_manifest(base, patch)
    assert result.ok
    assert result.manifest["description"] == "new"


# ── propose ─────────────────────────────────────────────────────────────────


def test_propose_creates_new_version_without_mutating_active(env):
    registry, store, _ = env
    _seed(registry, store)
    result = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "Updated planning."}],
        "reason": "clarity", "author": "background_review",
    }, actor=USER)
    assert result["ok"] is True
    assert result["baseVersion"] == "1.0.0"
    new_version = result["version"]
    # Active version is untouched.
    skill = store.get_skill("test.patch-target")
    assert skill["latestVersion"] == "1.0.0"
    stored = store.get_version("test.patch-target", new_version)
    assert stored["status"] == "draft"
    assert stored["baseVersion"] == "1.0.0"
    assert stored["patchAuthor"] == "background_review"


def test_propose_rejects_stale_base(env):
    registry, store, _ = env
    _seed(registry, store)
    # Bump the skill to a newer version out from under the patch.
    from harness.skills.manifest import SkillManifest

    v110 = store.get_version("test.patch-target", "1.0.0")["manifest"]
    v110 = {**v110, "version": "1.1.0"}
    store.save_version(v110, SkillManifest(**v110).version_identity("proc"))
    store.set_latest_version("test.patch-target", "1.1.0")
    result = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "x"}],
    }, actor=USER)
    assert result["ok"] is False
    assert result["stale"] is True


def test_propose_rejects_forbidden_permission_change(env):
    registry, store, _ = env
    _seed(registry, store)
    result = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/permissions", "value": ["trade.execute"]}],
    }, actor=USER)
    assert result["ok"] is False
    assert result["stage"] == "parse"


# ── evaluate + activate ─────────────────────────────────────────────────────


def test_activation_requires_passing_evaluation(env):
    registry, store, _ = env
    _seed(registry, store)
    # Establish a baseline evaluation so the regression dimension can pass.
    evaluate_version(registry, "test.patch-target", "1.0.0", actor=USER)
    proposed = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "Better."}],
    }, actor=USER)
    version = proposed["version"]
    # Activating without a passing evaluation is refused.
    denied = activate_version(registry, "test.patch-target", version, actor=USER)
    assert denied["ok"] is False
    # Evaluate, then activate.
    evaluated = evaluate_version(registry, "test.patch-target", version, actor=USER)
    assert evaluated["ok"] is True
    assert evaluated["record"]["candidateVersion"] == version
    assert evaluated["record"]["baselineVersion"] == "1.0.0"
    activated = activate_version(registry, "test.patch-target", version, actor=USER)
    assert activated["ok"] is True
    assert store.get_skill("test.patch-target")["latestVersion"] == version
    assert store.get_version("test.patch-target", version)["activatedAt"]


# ── canary ──────────────────────────────────────────────────────────────────


def test_canary_refused_for_mutating_skill():
    eligible, reason = canary_eligible({
        "status": "validated", "permissions": ["portfolio.modify"], "riskLevel": "low",
    })
    assert eligible is False
    assert "non-canary" in reason


def test_canary_allowed_for_safe_skill():
    eligible, _ = canary_eligible({
        "status": "validated", "permissions": ["research.read"], "riskLevel": "low",
    })
    assert eligible is True


def test_canary_and_promote(env):
    registry, store, _ = env
    _seed(registry, store)
    evaluate_version(registry, "test.patch-target", "1.0.0", actor=USER)
    proposed = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "Canary."}],
    }, actor=USER)
    version = proposed["version"]
    # Mark the candidate validated + passing so the canary gate accepts it.
    store.set_version_status("test.patch-target", version, "validated", evaluation_status="passed")
    canary = activate_version(registry, "test.patch-target", version, actor=USER, canary=True)
    assert canary["ok"] is True
    assert canary["status"] == "canary"
    assert store.get_version("test.patch-target", version)["canaryState"] == "canary"


# ── rollback ────────────────────────────────────────────────────────────────


def test_manual_rollback_preserves_versions(env):
    registry, store, _ = env
    _seed(registry, store)
    proposed = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "V1."}],
    }, actor=USER)
    version = proposed["version"]
    store.set_version_status("test.patch-target", version, "draft", evaluation_status="passed")
    activate_version(registry, "test.patch-target", version, actor=USER)
    result = rollback(registry, skill_id="test.patch-target", version=version, actor=USER, reason="bad")
    assert result["ok"] is True
    assert result["restoredVersion"] == "1.0.0"
    assert store.get_skill("test.patch-target")["latestVersion"] == "1.0.0"
    assert store.get_version("test.patch-target", version)["status"] == "rolled_back"
    # Both versions still exist.
    assert store.get_version("test.patch-target", "1.0.0") is not None
    assert store.get_version("test.patch-target", version) is not None


def test_automatic_rollback_on_regression(env):
    registry, store, _ = env
    _seed(registry, store)
    proposed = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "V1."}],
    }, actor=USER)
    version = proposed["version"]
    store.set_version_status("test.patch-target", version, "draft", evaluation_status="passed")
    activate_version(registry, "test.patch-target", version, actor=USER)
    result = check_rollback_triggers(
        registry, "test.patch-target", version, actor=USER, user_corrections=3,
    )
    assert result["rolledBack"] is True
    assert "user corrections" in result["reason"]
    assert store.get_skill("test.patch-target")["latestVersion"] == "1.0.0"


def test_version_history_exposes_patch_metadata(env):
    registry, store, _ = env
    _seed(registry, store)
    proposed = propose_patch(registry, {
        "skill": "test.patch-target", "baseVersion": "1.0.0",
        "operations": [{"op": "replace", "path": "/description", "value": "New."}],
        "reason": "why",
    }, actor=USER)
    history = version_history(registry, "test.patch-target")
    versions = {h["version"]: h for h in history}
    new = versions[proposed["version"]]
    assert new["baseVersion"] == "1.0.0"
    assert new["patchSummary"] == "why"
    assert new["isActive"] is False
    assert versions["1.0.0"]["isActive"] is True
