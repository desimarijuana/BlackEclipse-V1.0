"""Round 3 / W5 (ADR-H284) - ONE search primitive per question, on a fast engine.

The defect this file is the gate for: the harness had FOUR tools for TWO
questions, and the two the model reached for FIRST were the slow ones.

- `workspace_search` ran its OWN naive Python walk, while the fs subsystem's
  `search_text` was ALREADY ripgrep-first. The slow one had the friendlier
  name and sat first in every surface.
- `search_files` and `find_files` were always ONE implementation with two
  front-doors - `search_files` is literally `find_files(include=[pattern])` -
  and only `find_files` carried the exclude/extension/directory filters.

So the search surface was: two names for a name search, two names for a
content search, and the content search's first-listed name was the slow one.

The rules this file asserts:

1. A surface carries ONE content search and ONE name search.
2. The content search is ripgrep-first, and it ALWAYS reports which engine
   answered - a slow result is explainable rather than mysterious.
3. The deprecated names still WORK (deprecation is advisory), they now run on
   the same engine, and the registry warns once per run naming the replacement.
4. The canonical name search carries every filter the old one had, so nothing
   is lost in the consolidation.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fs_helpers  # noqa: E402

from harness.agents import CHAT_CODE_TOOLS, CODE_AGENT_TOOLS, CODE_NAVIGATOR_TOOLS  # noqa: E402
from harness.code import fs_tools, tools as code_tools  # noqa: E402
from harness.code.fs.search import ripgrep_path  # noqa: E402
from harness.tools import ToolContext, ToolRegistry  # noqa: E402

# The two questions a model actually asks.
CONTENT_SEARCHES = ("search_text", "workspace_search")
NAME_SEARCHES = ("search_files", "find_files")


# ── the rule: ONE primitive per question ───────────────────────────────────


@pytest.mark.parametrize("surface", [CODE_NAVIGATOR_TOOLS, CODE_AGENT_TOOLS, CHAT_CODE_TOOLS])
def test_a_surface_carries_one_content_search_and_one_name_search(surface) -> None:
    content = [n for n in surface if n in CONTENT_SEARCHES]
    names = [n for n in surface if n in NAME_SEARCHES]
    assert content == ["search_text"], f"the surface carries {content}"
    assert names == ["search_files"], f"the surface carries {names}"


def test_the_canonical_names_are_not_deprecated() -> None:
    registry = ToolRegistry()
    code_tools.register_code_tools(registry)
    for name in ("search_text", "search_files"):
        tool = registry.get(name)
        assert tool is not None, f"{name} is not registered"
        assert tool.deprecated is False, f"{name} must not be deprecated"
        assert tool.replacement is None


# ── the rule: the deprecated names still work, and warn ────────────────────


def test_the_deprecated_names_are_registered_and_named_their_replacement() -> None:
    registry = ToolRegistry()
    code_tools.register_code_tools(registry)
    for name, replacement in (("workspace_search", "search_text"), ("find_files", "search_files")):
        tool = registry.get(name)
        assert tool is not None, f"{name} is not registered"
        assert tool.deprecated is True
        assert tool.replacement == replacement


def test_the_registry_warns_once_per_run_for_a_deprecated_tool() -> None:
    registry = ToolRegistry()
    code_tools.register_code_tools(registry)
    warnings: list[str] = []
    ctx = ToolContext(run_id="r1", log=lambda m, d=None: warnings.append(m))
    tool = registry.get("workspace_search")
    assert tool is not None
    from harness.tools import _warn_deprecated

    _warn_deprecated(registry, tool, ctx)
    _warn_deprecated(registry, tool, ctx)
    assert len(warnings) == 1, "the warning must fire once per run"
    assert "search_text" in warnings[0]


# ── the rule: the engine is always reported ────────────────────────────────


def test_the_content_search_reports_its_engine(tmp_path) -> None:
    root = fs_helpers.tree(tmp_path)
    service = fs_helpers.make_service(root)
    result = service.search_text("beta")
    assert result["status"] == "ok"
    assert result["engine"] in ("ripgrep", "python-scan")
    # The engine is the FAST one when ripgrep is available.
    if ripgrep_path() is not None:
        assert result["engine"] == "ripgrep"
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_the_deprecated_alias_runs_on_the_same_engine(tmp_path) -> None:
    """The old name still works - and it is no longer the slow one."""
    root = fs_helpers.tree(tmp_path)
    service = fs_helpers.make_service(root)
    canonical = service.search_text("beta")

    ws = fs_helpers.make_ws(root)
    ctx = ToolContext(run_id="r2", log=lambda m, d=None: None, workspace=ws, autonomy="edit_verify")
    text, payload = await code_tools._search({"pattern": "beta"}, ctx)

    assert payload["status"] == "ok"
    assert payload["engine"] == canonical["engine"], (
        "the alias must run on the same engine as the canonical search"
    )
    assert payload["count"] == canonical["count"]
    assert payload["engine"] in ("ripgrep", "python-scan")
    assert "beta" in text or payload["count"] >= 1


@pytest.mark.asyncio
async def test_the_deprecated_alias_still_reports_a_refusal_as_a_refusal(tmp_path) -> None:
    root = fs_helpers.tree(tmp_path)
    ws = fs_helpers.make_ws(root)
    ctx = ToolContext(run_id="r3", log=lambda m, d=None: None, workspace=ws, autonomy="edit_verify")
    _text, payload = await code_tools._search({"pattern": "beta", "path": "nope/"}, ctx)
    assert payload["status"] == "refused"
    assert payload["code"]


# ── the rule: nothing is lost in the consolidation ─────────────────────────


def test_the_canonical_name_search_carries_every_filter(tmp_path) -> None:
    """`find_files`' filters moved onto `search_files` - nothing was dropped."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.ts").write_text("a\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("b\n", encoding="utf-8")
    (root / "src" / "skip.ts").write_text("skip\n", encoding="utf-8")
    service = fs_helpers.make_service(root)

    everything = service.search_files("*.ts")
    assert everything["status"] == "ok"
    paths = {entry["path"] for entry in everything["files"]}
    assert any(p.endswith("a.ts") for p in paths)

    # The extension filter.
    only_py = service.search_files("*", extensions=[".py"])
    paths = {entry["path"] for entry in only_py["files"]}
    assert paths and all(p.endswith(".py") for p in paths), paths

    # The exclude filter.
    without = service.search_files("*", extensions=[".ts"], exclude=["**/skip.ts"])
    paths = {entry["path"] for entry in without["files"]}
    assert not any(p.endswith("skip.ts") for p in paths), paths

    # The filesOnly filter.
    files_only = service.search_files("*", files_only=True)
    assert files_only["status"] == "ok"


def test_the_canonical_name_search_still_finds_by_glob(tmp_path) -> None:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.ts").write_text("a\n", encoding="utf-8")
    service = fs_helpers.make_service(root)
    result = service.search_files("**/*.ts")
    assert result["status"] == "ok"
    assert result["count"] >= 1
    assert result["pattern"] == "**/*.ts"
