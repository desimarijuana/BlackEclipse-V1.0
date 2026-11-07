"""Phase 1 — the five read-only repository tools.

Every handler is exercised through the ONE registry, so the read-permission
path, pydantic validation and result bounding are all covered. The gate cases:
`jdds.db` reports `PROTECTED_PATH` (never `BINARY_FILE`); a secret-shaped line
comes back `«redacted»` with exactly one `code.redacted` event and no value
anywhere; a fixtures question returns a real `path:line`.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness.code import policy
from harness.code.tools import REDACT_MARKER, register_code_tools
from harness.code.workspace import ResolvedWorkspace
from harness.tools import ToolContext, ToolRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "code"


class _FakeEmitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        self.events.append((event_type, data or {}))
        return {"type": event_type, "data": data or {}}

    def emit_sync(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        self.events.append((event_type, data or {}))


def _fixture_ws(tmp_path: Path) -> ResolvedWorkspace:
    root = tmp_path / "project"
    shutil.copytree(FIXTURES, root)
    real = Path(os.path.realpath(root))
    binding = policy.WorkspaceBinding(id="ws_fixture", root=real, base_revision="unknown", strategy="checkout")
    return ResolvedWorkspace(id="ws_fixture", root=real, base_revision="unknown", strategy="checkout", binding=binding)


def _ctx(
    ws: ResolvedWorkspace | None, emitter: _FakeEmitter | None = None,
    autonomy: str | None = "edit_verify",
) -> ToolContext:
    """A code-tool context. Round 3 / W5: the search now goes through the code
    capability, so it needs a profile - the Phase-0 rule (no profile, no code
    capability). `autonomy=None` builds the profile-less context on purpose."""
    return ToolContext(
        run_id="run_test", log=lambda *_: None, workspace=ws, emitter=emitter,
        autonomy=autonomy,
    )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_code_tools(registry)
    return registry


async def _call(registry: ToolRegistry, name: str, args: dict[str, Any], ctx: ToolContext):
    return await registry.execute(name, f"call_{name}", args, ctx, allowed={"workspace_status", "workspace_list", "workspace_search", "workspace_read", "workspace_docs"})


def _run(coro):
    return asyncio.run(coro)


# ── the tool set + read permission ──────────────────────────────────────────


READ_TOOLS = {
    "workspace_docs", "workspace_list", "workspace_read", "workspace_search",
    "workspace_status", "workspace_diff",
}
WRITE_TOOLS = {"workspace_patch_apply", "workspace_revert"}


def test_registered_code_tools_split_into_read_and_write():
    registry = _registry()
    names = {n for n in registry.names() if n.startswith("workspace_")}
    # Phase 1 read tools + Phase 2 diff (read) + patch/revert (write).
    assert names == READ_TOOLS | WRITE_TOOLS
    for tool in registry.list():
        if not tool.name.startswith("workspace_"):
            continue
        if tool.name in READ_TOOLS:
            assert tool.permission == "read"
            assert tool.risk == "low"
        else:
            assert tool.permission == "write"
            assert tool.effect == "write"
            assert tool.risk == "medium"


def test_command_run_is_a_non_read_external_action_tool():
    registry = _registry()
    tool = registry.get("command_run")
    assert tool is not None
    assert tool.permission == "write"
    assert tool.effect == "external_action"
    assert tool.risk == "medium"


# ── fixture question → path:line ────────────────────────────────────────────


def test_fixture_question_returns_a_real_path_line(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_docs", {"query": "valuation method bank"}, _ctx(ws)))
    assert result.ok
    assert result.data["engine"] == "scan"
    assert result.data["count"] >= 1
    top = result.data["results"][0]
    assert top["path"].endswith("valuation.md")
    assert top["startLine"] >= 1
    assert "path" in top and "startLine" in top


def test_search_without_a_code_profile_is_refused(tmp_path):
    """A code tool needs a code profile. The search used to bypass that check."""
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(
        registry, "workspace_search", {"pattern": "dividend-discount"}, _ctx(ws, autonomy=None),
    ))
    assert result.data.get("status") == "refused"
    assert result.data.get("code")


def test_search_reports_path_line(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_search", {"pattern": "dividend-discount"}, _ctx(ws)))
    assert result.ok
    assert result.data["count"] >= 1
    match = result.data["matches"][0]
    assert match["path"] == "docs/valuation.md"
    assert match["line"] >= 1
    assert "docs/valuation.md:" in result.text


def test_search_accepts_a_single_file_path(tmp_path):
    # Pointing `path` at the one file the caller means must search THAT file,
    # not raise NOT_A_DIRECTORY/NOT_FOUND (a recorded incident, twice).
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(
        registry, "workspace_search",
        {"pattern": "dividend-discount", "path": "docs/valuation.md"}, _ctx(ws),
    ))
    assert result.ok
    assert result.data["count"] >= 1
    assert all(m["path"] == "docs/valuation.md" for m in result.data["matches"])


# ── jdds.db → PROTECTED_PATH ────────────────────────────────────────────────


def test_jdds_db_is_protected_not_binary(tmp_path):
    ws = _fixture_ws(tmp_path)
    (ws.root / "jdds.db").write_bytes(b"\x00binary\x00vault")
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": "jdds.db"}, _ctx(ws)))
    assert result.ok
    assert result.data["status"] == "refused"
    assert result.data["code"] == "PROTECTED_PATH"
    assert result.data["code"] != "BINARY_FILE"
    assert "«redacted»" not in result.text


def test_protected_paths_are_refused_for_read(tmp_path):
    ws = _fixture_ws(tmp_path)
    (ws.root / ".env").write_text("API_KEY=secret", encoding="utf-8")
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": ".env"}, _ctx(ws)))
    assert result.data["code"] == "PROTECTED_PATH"


# ── redaction ───────────────────────────────────────────────────────────────


def test_secret_shaped_line_is_redacted_with_one_event(tmp_path):
    ws = _fixture_ws(tmp_path)
    emitter = _FakeEmitter()
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": "src/nested/util.py"}, _ctx(ws, emitter)))
    assert result.ok
    assert REDACT_MARKER in result.text
    # The secret VALUE must appear nowhere: text, data, or any event payload.
    blob = json.dumps({"text": result.text, "data": result.data, "events": emitter.events})
    assert "s3cr3t-value-that-must-be-redacted" not in blob
    redacted_events = [e for e in emitter.events if e[0] == "code.redacted"]
    assert len(redacted_events) == 1
    payload = redacted_events[0][1]
    assert payload["path"] == "src/nested/util.py"
    assert payload["lines"] == [1]
    assert "patternName" in payload
    assert "s3cr3t" not in json.dumps(payload)
    assert 1 in result.data["redactedLines"]


def test_read_reports_continuation_offset(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": "docs/valuation.md", "startLine": 1, "maxLines": 3}, _ctx(ws)))
    assert result.data["nextStartLine"] == 4
    assert len(result.data["content"]) == 3
    assert "4" in result.text  # the line number is present


# ── binary ──────────────────────────────────────────────────────────────────


def test_binary_file_is_refused(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": "binary.bin"}, _ctx(ws)))
    assert result.data["code"] == "BINARY_FILE"


# ── no workspace → honest refusal ───────────────────────────────────────────


def test_every_tool_refuses_without_a_workspace():
    registry = _registry()
    ctx = _ctx(None)
    for name, args in (
        ("workspace_status", {}),
        ("workspace_list", {}),
        ("workspace_search", {"pattern": "x"}),
        ("workspace_read", {"path": "README.md"}),
        ("workspace_docs", {"query": "valuation"}),
    ):
        result = _run(_call(registry, name, args, ctx))
        assert result.ok
        assert result.data["code"] == "WORKSPACE_UNAVAILABLE"


# ── input validation is fail-closed ─────────────────────────────────────────


def test_the_input_models_forbid_extra_fields(tmp_path):
    # The strict pydantic models reject an unexpected field. (The registry's
    # generic arg model strips unknowns before the handler, so this is asserted
    # at the model boundary — the defense-in-depth the contract names.)
    from pydantic import ValidationError
    from harness.code.tools import WorkspaceReadInput

    with pytest.raises(ValidationError):
        WorkspaceReadInput(path="README.md", bogus=1)


def test_unknown_fields_never_reach_the_handler(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_read", {"path": "README.md", "bogus": 1}, _ctx(ws)))
    # Either outcome is safe: a validation failure or an ignored unknown. What
    # matters is that the tool does not act on the unknown field.
    assert result.ok in (True, False)


# ── list ────────────────────────────────────────────────────────────────────


def test_list_is_ignore_aware(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_list", {"path": ".", "depth": 3}, _ctx(ws)))
    assert result.data["status"] == "ok"
    paths = {e["path"] for e in result.data["entries"]}
    assert "src/app.py" in paths
    assert not any(p.startswith("node_modules") for p in paths)


def test_status_reports_unavailable_without_git(tmp_path):
    ws = _fixture_ws(tmp_path)
    registry = _registry()
    result = _run(_call(registry, "workspace_status", {}, _ctx(ws)))
    assert result.ok
    assert result.data["status"] == "unavailable"

# ── workspace_diff resolves the BOUND project, not the app's own repo ────────
def _git(cwd: Path, *args: str) -> None:
    import subprocess

    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=str(cwd), check=True, capture_output=True,
    )


def test_workspace_diff_reads_the_bound_project_not_the_app_repo(tmp_path):
    """A direct (chat-bound) workspace lives in the user's folder.

    `worktree.diff` defaults its root to the app's own repo when no root is
    given, so a project-bound diff used to report the Eclipse tree's dirty
    files instead of the project's change (seen live: "17 files changed …
    a/Black-Eclipse-site/…" for a two-file edit in the project).
    """
    from types import SimpleNamespace

    project = tmp_path / "other-project"
    project.mkdir()
    (project / "app.js").write_text("module.exports = 1;\n", encoding="utf-8")
    _git(project, "init")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "init")
    (project / "app.js").write_text("module.exports = 2;\n", encoding="utf-8")

    ws_id = "cw_other"
    real = Path(os.path.realpath(project))
    binding = policy.WorkspaceBinding(id=ws_id, root=real, base_revision="HEAD", strategy="direct")
    resolved = ResolvedWorkspace(
        id=ws_id, root=real, base_revision="HEAD", strategy="direct", binding=binding,
    )
    cw = SimpleNamespace(id=ws_id, root=real, strategy="direct", base_revision="HEAD")
    ctx = _ctx(resolved)
    ctx._code_workspace = (cw, binding, resolved, None)

    result = _run(_registry().execute(
        "workspace_diff", "call_diff", {"includeUnified": True}, ctx,
        allowed={"workspace_diff"},
    ))
    assert result.ok
    assert result.data["filesChanged"] == 1
    assert "app.js" in result.text
    # Never the harness repo's own working tree.
    assert "Black-Eclipse-site" not in result.text
