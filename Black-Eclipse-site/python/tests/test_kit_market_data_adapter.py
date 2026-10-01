"""Phase 9 acceptance test for the `market_data_adapter` kit."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.code.kits import get_kit, render_kit
from harness.code.kits.loader import KitLoadError

_INPUTS = {"source_name": "acme_feed", "data_type": "current_quote"}


def _write_tree(tmp_path: Path, rendered: dict[str, str]) -> None:
    for rel, text in rendered.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def test_kit_loads_and_declares_its_outputs():
    kit = get_kit("market_data_adapter")
    assert kit is not None
    assert "python/harness/retrieval/{{module_name}}.py" in kit.manifest.produces


def test_rendered_outputs_are_within_the_declared_set():
    rendered = render_kit("market_data_adapter", _INPUTS)
    assert set(rendered) == {
        "python/harness/retrieval/acme_feed.py",
        "python/tests/test_acme_feed.py",
    }


def test_wrong_data_type_choice_is_refused():
    with pytest.raises(KitLoadError) as info:
        render_kit("market_data_adapter", {"source_name": "acme", "data_type": "wibble"})
    assert info.value.code == "KIT_INPUT_INVALID"
