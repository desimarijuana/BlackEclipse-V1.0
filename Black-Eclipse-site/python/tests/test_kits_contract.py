"""Phase 9 G1 — the kit contract validates, and a kit without its acceptance test
(or with an undeclared output) fails to load.
"""

from __future__ import annotations

import json
import os

import pytest

from harness.code.kits import get_kit, list_kits, load_catalog, load_kit, render_kit
from harness.code.kits.loader import KitLoadError
from harness.code.kits.model import KitManifest


def test_the_eight_named_kits_are_shipped():
    ids = {k["id"] for k in list_kits()}
    assert ids == {
        "market_data_adapter", "mcp_server", "ratio_calculator", "backtest_strategy",
        "chart_indicator", "portfolio_module", "data_ingestion_pipeline", "research_workflow",
    }


def test_every_kit_declares_a_closed_output_set_and_an_acceptance_rule():
    for kit in load_catalog():
        assert kit.manifest.produces, kit.id
        assert kit.manifest.acceptance, kit.id
        assert kit.manifest.summary_key.startswith("kit."), kit.id


def test_a_kit_without_its_acceptance_test_fails_to_load(tmp_path):
    # A kit folder with a valid manifest but no test_kit_<id>.py in python/tests.
    folder = tmp_path / "orphan_kit"
    (folder / "templates").mkdir(parents=True)
    (folder / "kit.json").write_text(json.dumps({
        "id": "orphan_kit",
        "title": "Orphan",
        "summary_key": "kit.orphan.summary",
        "produces": ["x.py"],
        "checks": [{"command_class": "python_test"}],
        "acceptance": "it does something",
    }), encoding="utf-8")
    (folder / "templates" / "x.py.tmpl").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(KitLoadError) as info:
        load_kit(str(folder))
    assert info.value.code == "KIT_NO_ACCEPTANCE_TEST"


def test_a_missing_template_for_a_declared_output_fails_the_load(tmp_path, monkeypatch):
    # The acceptance-test check passes (a stub test file is placed in the tests
    # dir); the declared-but-template-less output is then a KIT_TEMPLATE_MISSING.
    from harness.code.kits import loader as loader_mod

    folder = tmp_path / "declared_kit"
    (folder / "templates").mkdir(parents=True)
    (folder / "kit.json").write_text(json.dumps({
        "id": "declared_kit",
        "title": "Declared",
        "summary_key": "kit.declared.summary",
        "produces": ["a.py", "b.py"],
        "checks": [{"command_class": "python_test"}],
        "acceptance": "x",
    }), encoding="utf-8")
    (folder / "templates" / "a.py.tmpl").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(loader_mod, "_acceptance_test_exists", lambda _kit_id: True)
    with pytest.raises(KitLoadError) as info:
        load_kit(str(folder))
    assert info.value.code == "KIT_TEMPLATE_MISSING"


def test_a_manifest_rejects_an_absolute_or_traversing_output():
    with pytest.raises(Exception):
        KitManifest(
            id="bad", title="Bad", summary_key="kit.bad.summary",
            produces=["/etc/passwd"], checks=[], acceptance="x",
        )
    with pytest.raises(Exception):
        KitManifest(
            id="bad", title="Bad", summary_key="kit.bad.summary",
            produces=["../../escape.py"], checks=[], acceptance="x",
        )


def test_render_is_closed_to_the_declared_set():
    # Rendering returns exactly the declared (rendered) output paths.
    rendered = render_kit("ratio_calculator", {"ratio_name": "roe", "description": "return on equity"})
    assert set(rendered) == {
        "python/harness/research/ratios_roe.py",
        "python/tests/test_ratios_roe.py",
    }


def test_unknown_kit_is_a_structured_refusal():
    assert get_kit("does_not_exist") is None
    with pytest.raises(KitLoadError) as info:
        render_kit("does_not_exist", {})
    assert info.value.code == "KIT_UNKNOWN"
