"""The per-run UI-focus prompt block (Phase B-rest)."""

from __future__ import annotations

from harness.graph import _ui_focus_block


def test_absent_context_is_empty():
    assert _ui_focus_block(None) == ""
    assert _ui_focus_block({}) == ""
    assert _ui_focus_block({"ui": {}}) == ""
    assert _ui_focus_block({"ui": {"page": {}}}) == ""


def test_named_page_renders_blueprint_id_and_title():
    block = _ui_focus_block({"ui": {"page": {"blueprintId": "uibp_1", "title": "Rates Desk"}}})
    assert "Rates Desk" in block
    assert "uibp_1" in block
    assert "ui_get_current_page" in block


def test_path_alone_is_enough():
    block = _ui_focus_block({"ui": {"page": {"path": "/rates"}}})
    assert "/rates" in block
    # No id ⇒ no id-specific instruction, but the label still names the page.
    assert "blueprintId" not in block
