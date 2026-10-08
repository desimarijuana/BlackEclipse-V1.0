"""Manifest + semver validation for the Plugin Platform."""

from __future__ import annotations

import pytest

from harness.plugins import semver
from harness.plugins.errors import ManifestError
from harness.plugins.loader import read_manifest
from harness.plugins.manifest import SDK_VERSION, parse_manifest
from plugins_helpers import BUNDLED


def _base(**over) -> dict:
    data = {
        "id": "demo-plugin",
        "name": "Demo",
        "version": "1.2.3",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
    }
    data.update(over)
    return data


def test_valid_manifest_parses():
    manifest = parse_manifest(_base(permissions=["network", "events.publish"]))
    assert manifest.id == "demo-plugin"
    assert manifest.sdk_version == SDK_VERSION
    assert manifest.version == "1.2.3"


@pytest.mark.parametrize("bad", [
    _base(id="Bad_ID"),
    _base(version="1.2"),
    _base(version="not-a-version"),
    _base(runtime={}),
    _base(runtime={"type": "python"}),
    _base(permissions=["root"]),
    _base(unknown_field=True),
    _base(sdk={"version": ">=99.0.0"}),
    _base(eclipse={"min_version": "9.9.9", "max_version": "1.0.0"}),
])
def test_invalid_manifests_are_rejected(bad):
    with pytest.raises(Exception):
        parse_manifest(bad)


def test_duplicate_contributions_rejected():
    with pytest.raises(Exception):
        parse_manifest(_base(contributes={"tools": [{"name": "t"}, {"name": "t"}]}))


def test_duplicate_config_keys_rejected():
    with pytest.raises(Exception):
        parse_manifest(_base(configuration=[{"key": "a"}, {"key": "a"}]))


def test_dependency_self_reference_rejected():
    with pytest.raises(Exception):
        parse_manifest(_base(dependencies=[{"id": "demo-plugin", "version": "^1.0.0"}]))


def test_enum_config_requires_values():
    with pytest.raises(Exception):
        parse_manifest(_base(configuration=[{"key": "mode", "type": "enum"}]))


def test_read_manifest_reports_first_error(tmp_path):
    bad = tmp_path / "plugins" / "broken"
    bad.mkdir(parents=True)
    (bad / "plugin.yaml").write_text("id: Bad_ID\nname: x\nversion: 1.0.0\nruntime: {}\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        read_manifest(bad)


def test_bundled_hello_world_manifest_is_valid():
    manifest, _raw = read_manifest(BUNDLED / "hello-world")
    assert manifest.id == "hello-world"
    assert {t.name for t in manifest.contributes.tools} == {"greet", "fetch_status", "echo"}
    assert "hello.ping" in manifest.contributes.events.subscribes
    assert manifest.secret_keys() == ["apiKey"]


@pytest.mark.parametrize("version,rng,expected", [
    ("1.2.3", "^1.0.0", True),
    ("2.0.0", "^1.0.0", False),
    ("1.2.3", ">=1.0.0 <2.0.0", True),
    ("2.0.0-alpha", ">=2.0.0-alpha", True),
    ("2.0.0-alpha", "^1.0.0", False),
    ("1.2.9", "~1.2.0", True),
    ("1.5.0", "~1.2.0", False),
    ("0.3.4", "^0.3.0", True),
    ("0.4.0", "^0.3.0", False),
    ("1.0.0", "*", True),
])
def test_semver_ranges(version, rng, expected):
    assert semver.satisfies(version, rng) is expected


def test_semver_ordering_and_invalid():
    assert semver.compare("1.0.0", "1.0.1") < 0
    assert semver.compare("1.0.0", "1.0.0") == 0
    assert semver.is_valid("1.0.0-alpha.1+build.9")
    assert not semver.is_valid("1.0")
