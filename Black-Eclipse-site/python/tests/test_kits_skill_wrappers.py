"""Phase 9 §6.4 — the kit skill wrappers load, stay INERT, and grant nothing.

Each kit has a thin draft skill so it is reachable through the existing
`skill_invoke` path with the existing permission model. A wrapper can never grant
a permission or enable itself.
"""

from __future__ import annotations

from harness.skills.loader import load_catalog

_EXPECTED = {
    "system.market-data-source", "system.tool-server", "system.financial-ratio",
    "system.backtest-strategy", "system.chart-indicator", "system.portfolio-analysis",
    "system.data-import", "system.research-routine",
}


def test_the_eight_wrappers_are_shipped_and_inert():
    loaded = {entry.manifest.id: entry for entry in load_catalog()}
    assert _EXPECTED <= set(loaded)
    for skill_id in _EXPECTED:
        manifest = loaded[skill_id].manifest
        assert manifest.status == "draft", skill_id
        assert manifest.is_executable is False, skill_id
        assert manifest.is_active is False, skill_id


def test_a_wrapper_requires_the_scaffold_tool_and_no_operator_permission():
    loaded = {entry.manifest.id: entry for entry in load_catalog()}
    for skill_id in _EXPECTED:
        manifest = loaded[skill_id].manifest
        assert "scaffold_kit" in manifest.requiredTools, skill_id
        # A wrapper never declares an operator-only permission.
        for permission in manifest.permissions:
            assert permission not in ("skill.create", "skill.enable", "skill.disable", "skill.review"), skill_id
