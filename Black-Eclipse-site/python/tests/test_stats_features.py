"""Feature registry — versioning, dependencies, validation, preview, cycles."""

from __future__ import annotations

import numpy as np
import pytest

from harness.persistence import AgentMemoryStore
from harness.stats.base import StatsError
from harness.stats.feature_registry import FeatureDefinition, FeatureRegistry, bump_semver
from harness.stats.store import StatsStore


@pytest.fixture()
def registry(tmp_path) -> FeatureRegistry:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return FeatureRegistry(StatsStore(ams, artifact_root=str(tmp_path / "art")))


def test_bump_semver():
    assert bump_semver("1.2.3", "patch") == "1.2.4"
    assert bump_semver("1.2.3", "minor") == "1.3.0"
    assert bump_semver("1.2.3", "major") == "2.0.0"


def test_save_version_and_rollback(registry):
    f = registry.save(name="Mom", definition=FeatureDefinition(expression="close/lag(close,5)-1"),
                      owner="me", category="momentum")
    assert f["latestVersion"] == "1.0.0"
    f2 = registry.save(name="Mom", definition=FeatureDefinition(expression="close/lag(close,3)-1"),
                       feature_id=f["id"], bump="minor", owner="me")
    assert f2["latestVersion"] == "1.1.0"
    assert len(registry.versions(f["id"])) == 2
    registry.rollback(f["id"], "1.0.0")
    assert registry.get(f["id"])["feature"]["latestVersion"] == "1.0.0"
    # rollback does not erase the newer version
    assert len(registry.versions(f["id"])) == 2


def test_clone(registry):
    f = registry.save(name="A", definition=FeatureDefinition(expression="close-1"), owner="me")
    clone = registry.clone(f["id"], name="A copy")
    assert clone["id"] != f["id"]
    assert clone["latestVersion"] == "1.0.0"


def test_compare_identical(registry):
    f = registry.save(name="A", definition=FeatureDefinition(expression="close-1"), owner="me")
    registry.save(name="A", definition=FeatureDefinition(expression="close-2"), feature_id=f["id"])
    cmp = registry.compare(f["id"], "1.0.0", "1.0.1")
    assert cmp["identical"] is False


def test_dependencies_from_feature_reference(registry):
    base = registry.save(name="BaseMom", definition=FeatureDefinition(expression="close/lag(close,5)-1"))
    top = registry.save(name="ScaledMom", definition=FeatureDefinition(expression="zscore(BaseMom)"))
    deps = registry.dependencies(top["id"])
    assert "BaseMom" in deps["direct"]
    assert "BaseMom" in deps["graph"]


def test_preview_resolves_feature_dependency(registry):
    registry.save(name="BaseMom", definition=FeatureDefinition(expression="close/lag(close,2)-1"))
    top = registry.save(name="ScaledMom", definition=FeatureDefinition(expression="zscore(BaseMom)"))
    sample = {"close": list(np.linspace(100, 120, 30))}
    out = registry.preview(feature_id=top["id"], sample=sample)
    assert out["summary"]["finite"] > 0
    assert "BaseMom" in out["resolvedDependencies"]


def test_validate_reports_checks(registry):
    f = registry.save(name="Mom", definition=FeatureDefinition(expression="close/lag(close,5)-1"))
    result = registry.validate(feature_id=f["id"], sample={"close": list(range(1, 30))})
    assert result["status"] in ("valid", "warning")
    checks = {c["check"] for c in result["checks"]}
    assert {"syntax", "execution"}.issubset(checks)


def test_invalid_syntax_rejected(registry):
    with pytest.raises(Exception):
        registry.save(name="Bad", definition=FeatureDefinition(expression="close +"))


def test_unknown_variable_in_validation(registry):
    result = registry.validate(definition=FeatureDefinition(expression="nonsense_var + 1"),
                               sample={"close": [1.0, 2.0, 3.0, 4.0]})
    assert result["status"] == "invalid"


def test_pipeline_multi_step(registry):
    f = registry.save(name="Pipeline", definition=FeatureDefinition(pipeline=[
        {"name": "ret", "expression": "close/lag(close,1)-1"},
        {"name": "vol", "expression": "rolling_std(ret, 5)"},
    ]))
    out = registry.preview(feature_id=f["id"], sample={"close": list(np.linspace(100, 110, 40))})
    assert out["outputName"] == "vol"
    assert out["summary"]["finite"] > 0


def test_cycle_detection(registry):
    # A depends on B, B depends on A -> preview must reject
    a = registry.save(name="Afeat", definition=FeatureDefinition(expression="Bfeat + 1"))
    registry.save(name="Bfeat", definition=FeatureDefinition(expression="Afeat + 1"))
    with pytest.raises(StatsError):
        registry.preview(feature_id=a["id"], sample={"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
