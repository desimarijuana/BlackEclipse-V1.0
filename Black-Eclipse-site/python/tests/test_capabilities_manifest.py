"""Generated capability manifests are validated before anything can activate."""

from __future__ import annotations

import pytest

from harness.capabilities.manifest import CapabilityManifest


def _raw(**overrides):
    base = {
        "id": "ulcer_index",
        "version": "1.0.0",
        "kind": "recipe",
        "title": "Ulcer Index",
        "description": "Downside risk measure from a price series.",
        "scope": "workspace",
        "inputs": [{"name": "prices", "kind": "series", "required": True}],
        "outputs": [{"name": "ulcerIndex", "kind": "scalar"}],
        "permissions": ["analysis.execute"],
        "effect": "read",
        "timeoutMs": 30000,
        "imports": ["math"],
        "tests": ["test_capability.py"],
        "acceptance": "A known price series yields the expected index within 1e-6.",
    }
    base.update(overrides)
    return base


def test_the_plan_example_is_a_valid_manifest():
    manifest = CapabilityManifest.from_dict(_raw())
    assert manifest.id == "ulcer_index"
    assert manifest.to_dict()["timeoutMs"] == 30000
    assert manifest.digest()


@pytest.mark.parametrize("overrides", [
    {"id": "Bad-Id"},
    {"version": "1.0"},
    {"imports": ["os"]},
    {"permissions": ["workspace.write"]},
    {"kind": "recipe", "effect": "write"},
    {"kind": "recipe", "inputs": []},
    {"tests": []},
])
def test_invalid_manifests_are_refused(overrides):
    with pytest.raises(Exception):
        CapabilityManifest.from_dict(_raw(**overrides))


def test_global_pure_recipe_is_valid_but_not_auto_promoted():
    manifest = CapabilityManifest.from_dict(_raw(scope="global"))
    assert manifest.scope == "global"
    assert manifest.source_policy_violations() == []


def test_a_protected_path_reference_is_flagged():
    manifest = CapabilityManifest.from_dict(_raw(
        acceptance="The generated code edits python/harness/code/policy.py.",
    ))
    assert manifest.source_policy_violations()
