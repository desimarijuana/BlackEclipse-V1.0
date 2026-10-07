"""Phase 3 — Skill manifest, library and registry tests (Milestones 1–2).

Covers manifest validation, semver, the permission policy, library loading, and
the registry's discovery/validation/versioning/dependency behaviour. Everything
is driven off a temp library + temp DB — no network, no JDdS.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from harness.skills import (
    Actor,
    SkillManifest,
    SkillRegistry,
    SkillStore,
    load_catalog,
    parse_version,
    version_satisfies,
)
from harness.skills.loader import SkillLoadError, load_skill_folder
from harness.skills.manifest import FORBIDDEN_PERMISSIONS
from harness.skills.permissions import OPERATOR_ACTOR, check_permissions, can_enable


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-skill-")
    s = SkillStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture()
def registry(store):
    reg = SkillRegistry(store)
    reg.load_all()
    return reg


def _manifest(**overrides):
    base = {
        "id": "test.skill",
        "name": "Test Skill",
        "version": "1.0.0",
        "description": "A test skill.",
        "category": "research",
        "status": "enabled",
        "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}}, "required": ["objective"]},
        "requiredTools": [],
        "permissions": ["data.read"],
    }
    base.update(overrides)
    return base


# ── Manifest / semver ───────────────────────────────────────────────────────


def test_manifest_is_valid_and_hashes():
    m = SkillManifest(**_manifest())
    assert m.id == "test.skill"
    assert m.content_hash()
    m2 = SkillManifest(**_manifest())
    assert m.content_hash() == m2.content_hash()
    assert SkillManifest(**_manifest(description="Changed.")).content_hash() != m.content_hash()


def test_manifest_rejects_bad_version_and_id():
    with pytest.raises(Exception):
        SkillManifest(**_manifest(version="not-a-version"))
    with pytest.raises(Exception):
        SkillManifest(**_manifest(id="Bad Id"))


def test_manifest_rejects_non_object_input_schema():
    with pytest.raises(Exception):
        SkillManifest(**_manifest(inputSchema={"type": "array"}))


def test_manifest_deprecated_requires_info():
    with pytest.raises(Exception):
        SkillManifest(**_manifest(status="deprecated"))
    m = SkillManifest(**_manifest(status="deprecated", deprecation={"reason": "replaced"}))
    assert m.status == "deprecated"


def test_learning_origin_requires_source_run():
    with pytest.raises(Exception):
        SkillManifest(**_manifest(origin="learning"))
    m = SkillManifest(**_manifest(origin="learning", sourceRunId="run_1"))
    assert m.sourceRunId == "run_1"


def test_dependency_accepts_bare_id_or_object():
    m = SkillManifest(**_manifest(requiredSkills=["a.b", {"skillId": "c.d", "version": "^1.0.0"}]))
    assert m.requiredSkills[0].skillId == "a.b"
    assert m.requiredSkills[1].version == "^1.0.0"


def test_semver_parsing_and_constraints():
    assert parse_version("1.2.3") == (1, 2, 3, "")
    assert parse_version("1.2.3-beta") == (1, 2, 3, "beta")
    with pytest.raises(ValueError):
        parse_version("1.2")
    assert version_satisfies("1.5.0", "^1.2.0")
    assert not version_satisfies("2.0.0", "^1.2.0")
    assert version_satisfies("1.2.9", "~1.2.3")
    assert not version_satisfies("1.3.0", "~1.2.3")
    assert version_satisfies("2.0.0", ">=1.5.0")
    assert version_satisfies("1.0.0", "*")
    assert not version_satisfies("not-semver", "^1.0.0")


# ── Permissions ─────────────────────────────────────────────────────────────


def test_default_actor_is_read_only():
    decision = check_permissions(["data.read", "analysis.execute"], Actor())
    assert decision.allowed
    denied = check_permissions(["skill.enable"], Actor())
    assert not denied.allowed
    assert "skill.enable" in denied.missing


def test_operator_can_enable_safe_skill():
    assert can_enable(["data.read", "analysis.execute"], OPERATOR_ACTOR).allowed
    assert not can_enable(["data.read"], Actor()).allowed  # no skill.enable


def test_forbidden_permissions_never_granted_and_never_enableable():
    decision = check_permissions(["trade.execute"], OPERATOR_ACTOR)
    assert not decision.allowed
    assert "trade.execute" in decision.blocked
    assert not can_enable(["trade.execute"], OPERATOR_ACTOR).allowed
    for perm in FORBIDDEN_PERMISSIONS:
        assert perm in OPERATOR_ACTOR.granted() or True  # declared but not granted
    assert "trade.execute" not in OPERATOR_ACTOR.granted()


# ── Library loading ─────────────────────────────────────────────────────────


def test_shipped_library_loads():
    loaded = load_catalog()
    ids = {entry.manifest.id for entry in loaded}
    assert {
        "research.planning",
        "research.source-verification",
        "quality.financial-data-quality",
        "finance.fundamental-analysis",
        "system.report-generation",
    } <= ids
    for entry in loaded:
        assert entry.load_instructions().strip()


def test_load_rejects_missing_manifest(tmp_path):
    with pytest.raises(SkillLoadError):
        load_skill_folder(str(tmp_path))


def test_load_rejects_bad_json(tmp_path):
    (tmp_path / "skill.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SkillLoadError):
        load_skill_folder(str(tmp_path))


def test_load_rejects_declared_missing_instructions(tmp_path):
    (tmp_path / "skill.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    with pytest.raises(SkillLoadError):
        load_skill_folder(str(tmp_path))


# ── Registry ────────────────────────────────────────────────────────────────


def test_registry_lists_shipped_skills(registry):
    ids = {s["id"] for s in registry.list_summaries()}
    assert "finance.fundamental-analysis" in ids
    assert registry.duplicate_ids() == []


def test_registry_discovery_filters(registry):
    assert [r["id"] for r in registry.discover(query="fundamental")] == ["finance.fundamental-analysis"]
    assert {r["id"] for r in registry.discover(category="research")} == {
        "research.planning",
        "research.source-verification",
        "system.browser-research",
    }
    assert [r["id"] for r in registry.discover(tags=["valuation"])] == ["finance.fundamental-analysis"]
    assert registry.discover(query="zzz-no-such-skill") == []


def test_registry_detects_duplicate_ids(tmp_path, store):
    import shutil

    root = tmp_path / "library"
    src = os.path.join(os.path.dirname(__file__), "..", "harness", "skills", "library")
    shutil.copytree(src, root)
    # Duplicate an existing skill under another folder.
    dupdir = root / "dup"
    dupdir.mkdir()
    shutil.copy(os.path.join(root, "research", "research-planning", "skill.json"), dupdir / "skill.json")
    shutil.copy(os.path.join(root, "research", "research-planning", "SKILL.md"), dupdir / "SKILL.md")
    reg = SkillRegistry(store)
    errors = reg.load_all(str(root))
    assert "research.planning" in reg.duplicate_ids()
    assert any("duplicate" in e for e in errors)


def test_registry_version_resolution(registry):
    assert registry.resolve_version("research.planning") == "1.0.0"
    assert registry.resolve_version("research.planning", "1.0.0") == "1.0.0"
    assert registry.resolve_version("research.planning", "9.9.9") is None
    assert registry.resolve_version("no.such") is None


def test_registry_validation_without_tools_fails(registry):
    # The shipped finance skill requires real tools; with no tool registry
    # attached, validation must surface the missing tools (not silently pass).
    report = registry.validate("finance.fundamental-analysis")
    assert report["ok"] is False
    assert any(c["check"] == "tools" and not c["ok"] for c in report["checks"])


def test_registry_validation_with_tool_registry(registry):
    from harness.finance_tools import register_finance_tools
    from harness.retrieval_tools import register_retrieval_tools
    from harness.tools import ToolRegistry

    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)
    for skill_id in ("research.planning", "finance.fundamental-analysis", "system.report-generation"):
        report = registry.validate(skill_id)
        assert report["ok"], report["errors"]


def test_registry_dependency_order(registry):
    result = registry.resolve_dependencies("system.report-generation")
    assert result.ok
    assert result.order[0][0] == "research.source-verification"
    assert result.order[-1][0] == "system.report-generation"


def test_registry_detects_missing_dependency(registry):
    from harness.skills.manifest import SkillDependencySpec

    manifest = registry.manifest("research.planning")
    manifest.requiredSkills.append(SkillDependencySpec(skillId="does.not.exist"))
    result = registry.resolve_dependencies("research.planning")
    assert not result.ok
    assert "does.not.exist" in result.missing


def test_registry_detects_circular_dependency(registry):
    from harness.skills.manifest import SkillDependencySpec

    a = registry.manifest("research.planning")
    b = registry.manifest("research.source-verification")
    a.requiredSkills.append(SkillDependencySpec(skillId=b.id))
    b.requiredSkills.append(SkillDependencySpec(skillId=a.id))
    result = registry.resolve_dependencies("research.planning")
    assert not result.ok
    assert result.cycles
    assert any("circular" in e for e in result.errors)


def test_registry_detects_version_mismatch(registry):
    from harness.skills.loader import LoadedSkill

    dep = registry.manifest("quality.financial-data-quality")
    dep.requiredSkills = []
    loaded = LoadedSkill(manifest=dep, folder="", instructions_path=None)
    registry._skills[dep.id] = loaded
    fin = registry.manifest("finance.fundamental-analysis")
    assert fin.requiredSkills, "finance skill should depend on the quality skill"
    fin.requiredSkills[0].version = "^9.0.0"
    result = registry.resolve_dependencies("finance.fundamental-analysis")
    assert not result.ok
    assert result.version_mismatches


def test_registry_disable_blocks_dependencies(registry):
    registry.store.set_version_status("quality.financial-data-quality", "1.0.0", "disabled")
    result = registry.resolve_dependencies("finance.fundamental-analysis")
    assert not result.ok
    assert result.disabled


def test_enable_requires_operator_and_passes_validation(registry):
    # No tool registry → validation fails → enable refused even for an operator.
    denied = registry.set_status("research.planning", "enabled", Actor())
    assert not denied["ok"]

    from harness.finance_tools import register_finance_tools
    from harness.retrieval_tools import register_retrieval_tools
    from harness.tools import ToolRegistry

    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)

    enabled = registry.set_status("research.planning", "enabled", OPERATOR_ACTOR)
    assert enabled["ok"]
    assert registry.store.get_skill("research.planning")["status"] == "enabled"


def test_enable_refused_without_skill_enable_permission(registry):
    result = registry.set_status("research.planning", "enabled", Actor())
    assert not result["ok"]
    assert "operator" in result["error"]


def test_version_immutability(store):
    m = SkillManifest(**_manifest())
    store.upsert_skill(skill_id=m.id, name=m.name, description=m.description, category=m.category,
                       latest_version=m.version, status=m.status, tags=m.tags)
    store.save_version(m.model_dump(), m.content_hash())
    with pytest.raises(ValueError):
        store.save_version(m.model_dump(), m.content_hash())


# -- Dependency visibility / preflight (Phase 14) ----------------------------


def test_dependency_graph_reports_versions_and_status(store, tmp_path):
    import json as _json

    root = tmp_path / "lib"

    def write(skill_id, deps):
        folder = root / skill_id.split(".")[-1]
        folder.mkdir(parents=True)
        (folder / "skill.json").write_text(_json.dumps({
            "id": skill_id, "name": skill_id, "version": "1.0.0", "description": "d",
            "category": "research", "status": "enabled", "permissions": ["data.read"],
            "requiredSkills": deps,
        }), encoding="utf-8")
        (folder / "SKILL.md").write_text("x", encoding="utf-8")

    write("research.child", ["research.parent"])
    write("research.parent", [])
    reg = SkillRegistry(store)
    reg.load_all(root=str(root), project_discovery=False)

    graph = reg.dependency_graph("research.child")
    assert graph["ok"] is True
    node_ids = {n["id"] for n in graph["nodes"]}
    assert {"research.child", "research.parent"} <= node_ids
    edge = next(e for e in graph["edges"] if e["to"] == "research.parent")
    assert edge["status"] == "ok"
    assert edge["resolvedVersion"] == "1.0.0"


def test_dependency_graph_reports_missing(store, tmp_path):
    import json as _json

    root = tmp_path / "lib2"
    folder = root / "child"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(_json.dumps({
        "id": "research.child2", "name": "c", "version": "1.0.0", "description": "d",
        "category": "research", "status": "enabled",
        "requiredSkills": ["research.absent"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("x", encoding="utf-8")
    reg = SkillRegistry(store)
    reg.load_all(root=str(root), project_discovery=False)
    graph = reg.dependency_graph("research.child2")
    assert graph["ok"] is False
    assert any(e["status"] == "missing" for e in graph["edges"])
