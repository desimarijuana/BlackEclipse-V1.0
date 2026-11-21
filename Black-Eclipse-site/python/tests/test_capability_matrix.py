"""The generated broker capability matrix must match the registry, always."""

from __future__ import annotations

from pathlib import Path

from harness.trade import capability_matrix as cm


def _rows() -> list[dict]:
    return [
        {
            "id": "alpha",
            "label": "Alpha",
            "auth": "credentials",
            "modes": ["demo", "live"],
            "assetClasses": ["equity"],
            "capabilities": ["account", "orders", "positions", "quote"],
            "execution": True,
            "available": True,
        },
        {
            "id": "beta",
            "label": "Beta",
            "auth": "bridge",
            "modes": ["demo"],
            "assetClasses": [],
            "capabilities": ["account", "positions"],
            "execution": False,
            "available": False,
            "unavailableReason": "PACKAGE_MISSING",
        },
    ]


def test_render_table_is_deterministic_and_names_every_kind():
    first = cm.render_table(_rows())
    second = cm.render_table(_rows())
    assert first == second
    assert "`alpha`" in first and "`beta`" in first
    assert "yes" in first
    assert "no (read-only)" in first


def test_unavailable_reason_is_shown_not_hidden():
    table = cm.render_table(_rows())
    assert "no — PACKAGE_MISSING" in table


def test_empty_registry_still_renders_a_row():
    assert "none registered" in cm.render_table([])


def test_splice_replaces_the_existing_block():
    doc = f"intro\n\n{cm.BEGIN}\n\nold\n\n{cm.END}\n\noutro\n"
    new_block = cm.render_table(_rows())
    out = cm.splice(doc, new_block)
    assert "old" not in out
    assert out.count(cm.BEGIN) == 1
    assert out.count(cm.END) == 1
    assert out.startswith("intro")
    assert out.rstrip().endswith("outro")


def test_splice_appends_when_the_page_has_no_block():
    out = cm.splice("intro\n", cm.render_table(_rows()))
    assert cm.BEGIN in out and cm.END in out
    assert "## Declared broker kinds (generated)" in out


def test_check_reports_a_stale_page(tmp_path: Path):
    page = tmp_path / "trading.md"
    page.write_text(cm.splice("intro\n", "stale content"), encoding="utf-8")
    problems = cm.check(page)
    assert problems and "stale" in problems[0]


def test_check_passes_on_a_fresh_page(tmp_path: Path):
    page = tmp_path / "trading.md"
    page.write_text(cm.splice("intro\n", cm.render_table(cm.kind_rows())), encoding="utf-8")
    assert cm.check(page) == []


def test_check_reports_a_missing_block(tmp_path: Path):
    page = tmp_path / "trading.md"
    page.write_text("# no markers here\n", encoding="utf-8")
    problems = cm.check(page)
    assert problems and "no generated block" in problems[0]


def test_live_registry_renders_real_kinds():
    """The committed page is generated from the real registry, not a fixture."""
    rows = cm.kind_rows()
    ids = {row["id"] for row in rows}
    assert {"alpaca", "ibkr", "mt4_bridge", "mt5"} <= ids
    table = cm.render_table(rows)
    assert "`mt5`" in table
