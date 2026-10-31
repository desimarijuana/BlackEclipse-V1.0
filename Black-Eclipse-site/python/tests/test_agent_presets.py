"""Custom agent presets — storage, version pinning and effect validation."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from harness.agent_presets import AgentPresetStore


class _Store:
    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:")
        self._db.row_factory = sqlite3.Row


class _Registry:
    def __init__(self) -> None:
        self._tools = {
            "get_quote": SimpleNamespace(permission="read", description="quote", risk="low"),
            "research_search": SimpleNamespace(permission="read", description="search", risk="low"),
            "write_file": SimpleNamespace(permission="write", description="write", risk="high"),
            "deploy_run": SimpleNamespace(permission="external_action", description="deploy", risk="high"),
        }

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str):
        return self._tools.get(name)


def _payload(**overrides):
    base = {
        "name": "Gold analyst",
        "description": "Intraday gold reader",
        "systemPrompt": "You are a disciplined gold analyst.",
        "tools": ["get_quote", "research_search"],
        "maxSteps": 6,
    }
    base.update(overrides)
    return base


def _store() -> AgentPresetStore:
    return AgentPresetStore(_Store(), _Registry())


def test_create_pins_version_one_and_lists_the_preset():
    store = _store()
    preset = store.create(_payload())
    assert preset["version"] == 1
    assert preset["tools"] == ["get_quote", "research_search"]
    assert preset["contentHash"].startswith("ap_")
    listed = store.list()
    assert [item["id"] for item in listed] == [preset["id"]]
    assert listed[0]["toolCount"] == 2


def test_editing_appends_a_version_and_the_old_snapshot_is_immutable():
    store = _store()
    first = store.create(_payload())
    second = store.update(first["id"], _payload(systemPrompt="A new prompt."))
    assert second is not None and second["version"] == 2
    assert store.get(first["id"], 1)["systemPrompt"] == "You are a disciplined gold analyst."
    assert store.get(first["id"], 2)["systemPrompt"] == "A new prompt."
    assert [v["version"] for v in store.versions(first["id"])] == [2, 1]


def test_unknown_tool_is_refused():
    with pytest.raises(ValueError, match="unknown tool"):
        _store().create(_payload(tools=["not_a_tool"]))


def test_effectful_tool_requires_an_explicit_acknowledgement():
    store = _store()
    with pytest.raises(ValueError, match="Allow effectful"):
        store.create(_payload(tools=["write_file"]))
    preset = store.create(_payload(tools=["write_file"], allowEffectful=True))
    assert preset["allowEffectful"] is True
    assert "write" in store.list()[0]["effects"]


def test_step_bound_is_enforced():
    with pytest.raises(ValueError, match="maxSteps"):
        _store().create(_payload(maxSteps=0))
    with pytest.raises(ValueError, match="maxSteps"):
        _store().create(_payload(maxSteps=33))


def test_archive_hides_the_preset_but_keeps_its_versions():
    store = _store()
    preset = store.create(_payload())
    assert store.archive(preset["id"]) is True
    assert store.list() == []
    assert store.versions(preset["id"])[0]["version"] == 1
    assert store.update(preset["id"], _payload()) is None


def test_tool_catalog_reports_the_effect_class():
    catalog = {item["name"]: item for item in _store().catalog()}
    assert catalog["get_quote"]["permission"] == "read"
    assert catalog["write_file"]["permission"] == "write"
