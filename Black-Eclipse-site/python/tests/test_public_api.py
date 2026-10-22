"""Round 3 / W10 (ADR-H298) - the harness has a PUBLIC surface, and it is honest.

The defect this file is the gate for: everything the harness can do was
reachable only from inside this repository. There was no declared surface, so
another harness could not use it without reading the source to find out what
was safe to touch, and there was no way to take Eclipse's finance tools
somewhere else.

The rules this file asserts:

1. The public surface is EXACTLY what `harness.public` declares - a closed
   list, so a consumer can depend on it.
2. Every exported tool declares its PERMISSION and its EFFECT CLASS. A tool
   that cannot be classified is NOT published, because a consumer cannot
   honour a rule it cannot read.
3. The published manifest is GENERATED - it cannot drift away from the
   registry that actually exists.
4. The package carries NO app data, no vault and no credentials: the
   published thing is the RUNTIME, and the data belongs to the installation
   that runs it.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))

REGISTRY_FILE = os.path.join(REPO, "docs", "harness", "tool-registry.json")
PYPROJECT = os.path.join(REPO, "pyproject.toml")


# ── 1. the surface is closed ───────────────────────────────────────────────


def test_the_public_surface_is_exactly_what_it_declares() -> None:
    import harness.public as public

    assert sorted(public.__all__) == [
        "AgenticService",
        "ModelSettings",
        "PUBLISHABLE_EFFECTS",
        "RunInput",
        "RunRequest",
        "RunResult",
        "TOOL_MANIFEST_VERSION",
        "ToolDefinition",
        "ToolRegistry",
        "export_tool_schemas",
        "tool_manifest",
    ]
    for name in public.__all__:
        assert hasattr(public, name), f"{name} is declared but missing"


def test_the_public_surface_does_not_reach_into_the_app() -> None:
    """The public module must not import the app, the vault or the TS side."""
    import harness.public as public

    source = open(public.__file__, encoding="utf-8").read()
    for forbidden in ("harness.deps", "src.", "eclipse_memory.store", "jdds"):
        assert forbidden not in source, f"the public surface reaches into {forbidden!r}"


# ── 2. every exported tool is classifiable ─────────────────────────────────


def test_every_exported_tool_declares_its_permission_and_effect() -> None:
    from harness.public import PUBLISHABLE_EFFECTS, export_tool_schemas

    tools = export_tool_schemas()
    assert tools, "the manifest is empty"
    for tool in tools:
        assert tool["permission"] in ("read", "write", "external_action"), tool["name"]
        if tool["permission"] != "read":
            assert tool["effect"] in PUBLISHABLE_EFFECTS, (
                f"{tool['name']} is published with an effect a consumer cannot honour: "
                f"{tool['effect']!r}"
            )
        assert tool["name"] and tool["description"]


def test_an_unclassifiable_write_tool_is_not_published() -> None:
    """A write-ish tool with no effect class is WITHHELD, not published."""
    from harness.public import export_tool_schemas
    from harness.tools import ToolDefinition, ToolRegistry

    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="ambiguous_writer", description="Writes, but says what it writes?",
        input_schema={"type": "object", "properties": {}},
        handler=None, permission="write", risk="low",
    ))
    registry.register(ToolDefinition(
        name="plain_reader", description="Reads.",
        input_schema={"type": "object", "properties": {}},
        handler=None, permission="read", risk="low",
    ))
    names = {tool["name"] for tool in export_tool_schemas(registry)}
    assert "ambiguous_writer" not in names, "an unclassifiable write tool was published"
    assert "plain_reader" in names


def test_no_tool_description_carries_a_memory_address() -> None:
    """A description with an object repr is noise for the model AND unstable.

    The `analysis_run` description interpolated the FUNCTION instead of its
    result, so it advertised `<function recipe_catalogue_text at 0x...>` to the
    model - the recipes it could actually run were never named. This guards
    the whole surface: no published description may contain an address.
    """
    from harness.public import export_tool_schemas

    for tool in export_tool_schemas():
        assert "0x" not in tool["description"], (
            f"{tool['name']} advertises an object repr instead of prose: "
            f"{tool['description'][:120]!r}"
        )


# ── 3. the manifest is generated, and it does not drift ───────────────────


def test_the_published_manifest_matches_a_fresh_generation() -> None:
    from harness.public import tool_manifest

    with open(REGISTRY_FILE, encoding="utf-8") as handle:
        committed = json.load(handle)
    fresh = tool_manifest()
    assert committed["digest"] == fresh["digest"], (
        "docs/harness/tool-registry.json is stale or was hand-edited. "
        "Regenerate it: npm run eval:registry"
    )
    assert committed["toolCount"] == fresh["toolCount"]


def test_the_manifest_is_versioned_and_digested() -> None:
    with open(REGISTRY_FILE, encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["manifestVersion"]
    assert len(manifest["digest"]) == 16
    assert manifest["toolCount"] == len(manifest["tools"])


# ── 4. the package carries no data ────────────────────────────────────────


def test_the_package_carries_no_app_data_no_vault_no_credentials() -> None:
    """The published thing is the RUNTIME. The data belongs to the install."""
    with open(PYPROJECT, "rb") as handle:
        pyproject = tomllib.load(handle)

    # No data files are shipped.
    package_data = pyproject.get("tool", {}).get("setuptools", {}).get("package-data", {})
    for package, patterns in package_data.items():
        for pattern in patterns:
            assert not any(
                token in pattern.lower()
                for token in (".db", "jdds", "secret", "key", "env", "credential")
            ), f"{package}: {pattern} looks like data, not runtime"

    # The description says what it is, and does not claim to be the app.
    description = pyproject["project"]["description"].lower()
    assert "runtime" in description
    assert "app" not in description.replace("application", "")

    # The package is named for the harness, and the app stays private.
    assert pyproject["project"]["name"] == "black-eclipse-harness"
    assert pyproject["project"]["version"]

    # No dependency on a provider SDK by default: a consumer that only wants
    # the tool surface should not install an SDK for a model it never calls.
    for dependency in pyproject["project"]["dependencies"]:
        assert "langchain-openai" not in dependency
        assert "langchain-anthropic" not in dependency
    assert "providers" in pyproject["project"]["optional-dependencies"]
