"""The adapter lane authors a REVIEWABLE, DISABLED broker/API plugin draft.

It validates with the same manifest contract the loader uses, names credentials
but never stores a value, and stops before install/enable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from harness.capabilities.adapter import author_adapter
from harness.capabilities.tools import capability_adapter
from harness.plugins.manifest import PluginManifest
from harness.tools import ToolContext


_TOOLS = [
    {"name": "get_positions", "method": "GET", "path": "/v1/positions",
     "description": "Read the account's open positions."},
    {"name": "place_order", "method": "POST", "path": "/v1/orders",
     "description": "Submit an order."},
]


def _author(root: Path, **overrides):
    kwargs = {
        "need": "read positions and submit orders at my broker",
        "base_url": "https://api.example.com",
        "tools": _TOOLS,
        "root": root,
        "kind": "broker",
        "credential_names": ["BROKER_API_KEY"],
        "adapter_id": "example-broker",
        "label": "Example broker",
    }
    kwargs.update(overrides)
    return author_adapter(**kwargs)


def test_a_draft_is_written_disabled_and_validates_as_a_plugin(tmp_path: Path):
    draft = _author(tmp_path)

    directory = tmp_path / ".black-eclipse" / "adapters" / "example-broker"
    assert Path(draft.directory) == directory
    assert sorted(path.name for path in directory.iterdir()) == [
        "README.md", "plugin.py", "plugin.yaml",
    ]

    manifest = yaml.safe_load((directory / "plugin.yaml").read_text(encoding="utf-8"))
    PluginManifest.model_validate(manifest)
    assert manifest["permissions"] == ["network"]
    assert manifest["authentication"] == {"type": "none"}
    assert [tool["permission"] for tool in manifest["contributes"]["tools"]] == [
        "read", "external_action",
    ]
    assert [field["key"] for field in manifest["configuration"]] == [
        "baseUrl", "BROKER_API_KEY",
    ]
    assert manifest["configuration"][1]["type"] == "secret"

    source = (directory / "plugin.py").read_text(encoding="utf-8")
    assert "ctx.http.get(" in source and "ctx.http.post(" in source
    assert "get_positions" in source and "place_order" in source

    assert draft.to_dict()["installed"] is False
    assert draft.to_dict()["enabled"] is False
    assert draft.credentials == ["BROKER_API_KEY"]


def test_credential_names_are_the_only_credential_artifacts(tmp_path: Path):
    secret = "sk-abcdefghijklmnopqrstuvwxyz012345"
    with pytest.raises(ValueError, match="credential values"):
        _author(tmp_path, credential_names=[secret])
    assert not (tmp_path / ".black-eclipse" / "adapters" / "example-broker").exists()

    draft = _author(tmp_path)
    for path in Path(draft.directory).iterdir():
        text = path.read_text(encoding="utf-8")
        assert secret not in text


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.example.com",
        "https://user:pass@api.example.com",
        "https://api.example.com?x=1",
    ],
)
def test_base_url_is_https_only_and_carries_no_credentials(tmp_path: Path, base_url: str):
    with pytest.raises(ValueError):
        _author(tmp_path, base_url=base_url)


def test_invalid_or_duplicate_tools_are_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="invalid tool name"):
        _author(tmp_path, tools=[{"name": "not a name", "path": "/x"}])
    with pytest.raises(ValueError, match="duplicate tool name"):
        _author(tmp_path, tools=[{"name": "a", "path": "/a"}, {"name": "a", "path": "/b"}])
    with pytest.raises(ValueError, match="GET or POST"):
        _author(tmp_path, tools=[{"name": "a", "method": "DELETE", "path": "/a"}])


def test_an_existing_draft_is_never_overwritten(tmp_path: Path):
    _author(tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        _author(tmp_path)


def _ctx(root: Path) -> ToolContext:
    return ToolContext(
        run_id="run_adapter",
        log=lambda *_: None,
        workspace=SimpleNamespace(root=root, id="ws_adapter"),
    )


def test_the_tool_writes_a_draft_and_keeps_activation_operator_owned(tmp_path: Path):
    text, data = asyncio.run(capability_adapter({
        "need": "read my broker positions",
        "baseUrl": "https://api.example.com",
        "kind": "broker",
        "adapterId": "example-broker",
        "credentialNames": ["BROKER_API_KEY"],
        "tools": [{"name": "get_positions", "method": "GET", "path": "/positions"}],
    }, _ctx(tmp_path)))

    assert data["status"] == "drafted"
    assert data["installed"] is False and data["enabled"] is False
    assert "NOT installed" in text
    assert (tmp_path / ".black-eclipse" / "adapters" / "example-broker" / "plugin.yaml").is_file()


def test_the_tool_refuses_mcp_and_credential_values(tmp_path: Path):
    _, data = asyncio.run(capability_adapter({
        "need": "connect an MCP server",
        "baseUrl": "https://api.example.com",
        "kind": "mcp",
        "tools": [{"name": "get_positions", "path": "/positions"}],
    }, _ctx(tmp_path)))
    assert data["code"] == "INPUT_INVALID"

    _, data = asyncio.run(capability_adapter({
        "need": "read my broker positions",
        "baseUrl": "https://api.example.com",
        "kind": "broker",
        "adapterId": "example-broker",
        "credentialNames": ["sk-abcdefghijklmnopqrstuvwxyz012345"],
        "tools": [{"name": "get_positions", "path": "/positions"}],
    }, _ctx(tmp_path)))
    assert data["code"] == "CREDENTIAL_VALUE"
