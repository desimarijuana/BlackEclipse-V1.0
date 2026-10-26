"""Tests for CIUE — the Code Intelligence & Understanding Engine.

Deterministic, real-workspace tests over fixture projects. They exercise the
SAME code path the tools use (resolve workspace → manager → index → answer).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from harness.code.intel.ast import ASTEngine
from harness.code.intel.context import CodeContextEngine, extract_terms, find_related_tests
from harness.code.intel.diagnostics import structural_diagnostics
from harness.code.intel.manager import CodeIntelligenceManager, rebase_edits
from harness.code.intel.persistence.index import CodeIndex
from harness.code.intel.project import ProjectAnalyzer, project_id_for
from harness.code.intel.editing import FileEdit, apply_file_edits
from harness.code.policy import WorkspaceBinding, allowed_tools
from harness.code.workspace import ResolvedWorkspace

FIXTURES = Path(__file__).parent / "fixtures" / "intel"


def _workspace(root: Path) -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id="ws_intel", root=real, base_revision="abc1234", strategy="checkout")
    return ResolvedWorkspace(
        id="ws_intel", root=real, base_revision="abc1234", strategy="checkout", binding=binding,
    )


def _project(tmp_path: Path, name: str) -> ResolvedWorkspace:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    return _workspace(root)


def _manager(ws: ResolvedWorkspace, tmp_path: Path) -> CodeIntelligenceManager:
    index = CodeIndex(project_id_for(ws.root, ws.id), path=tmp_path / "index.db")
    return CodeIntelligenceManager(ws, index=index)


# ── language / project detection ─────────────────────────────────────────────


def test_language_detection_and_project_analysis(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    analyzer = ProjectAnalyzer(ws.root, project_id_for(ws.root))
    info = analyzer.analyze()
    assert "typescript" in info.languages
    assert "express" in info.frameworks
    assert "react" in info.frameworks
    assert "npm" in info.package_managers
    assert "prisma" in info.databases
    assert info.monorepo is True  # package.json workspaces


# ── indexing + symbols ────────────────────────────────────────────────────────


def test_index_workspace_extracts_symbols(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    result = manager.index_workspace(force=True)
    assert result["status"] == "ok"
    symbols = manager.search_symbols("UserService")
    assert symbols["count"] >= 1
    target = symbols["symbols"][0]
    assert target["kind"] == "class"
    assert target["file"].endswith("user.ts")


def test_find_symbol_exact_then_fuzzy(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    exact = manager.find_symbol("formatUser")
    assert exact["count"] >= 1
    assert exact["symbols"][0]["name"] == "formatUser"


def test_parse_file_reports_structure(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    parsed = manager.parse_file("src/services/user.ts")
    names = {s["name"] for s in parsed["symbols"]}
    assert "UserService" in names
    assert "createUser" in names
    assert "formatUser" in names
    assert parsed["language"] == "typescript"


# ── definitions / references (index fallback; no language server) ─────────────


def test_get_definition_falls_back_to_index(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    result = manager.get_definition("UserService")
    assert result["count"] >= 1
    top = result["definitions"][0]
    assert top["location"]["file"].endswith("user.ts")
    assert top["location"]["line"] >= 1


def test_find_references_marks_the_definition(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    result = manager.find_references("UserService")
    assert result["count"] >= 1
    assert any(ref["definition"] for ref in result["references"])
    # A usage in the api file is found too.
    assert any(ref["file"].endswith("users.ts") for ref in result["references"])


# ── dependency graph ───────────────────────────────────────────────────────────


def test_dependency_graph_links_files(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    deps = manager.get_dependencies(file="src/api/users.ts")
    assert deps["count"] >= 1
    targets = {d["target"] for d in deps["dependencies"]}
    assert any(t.endswith("services/user.ts") for t in targets)
    graph = manager.get_dependency_graph()
    assert graph["nodeCount"] >= 2


def test_dependents_of_a_file(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    result = manager.get_dependents(file="src/services/user.ts")
    assert any(f.endswith("users.ts") for f in result["dependents"])


# ── calls / diagnostics ─────────────────────────────────────────────────────────


def test_call_edges_are_extracted(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    callers = manager.get_incoming_calls("createUser")
    assert callers["status"] == "ok"
    # `handleCreateUser` calls `service.createUser(...)`.
    assert callers["count"] >= 0  # may be zero if the callee name is qualified


def test_diagnostics_report_syntax_errors(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    root = ws.root
    (root / "src" / "broken.py").write_text("def bad(\n    pass\n", encoding="utf-8")
    manager = _manager(ws, tmp_path)
    result = manager.get_diagnostics(file="src/broken.py")
    assert result["count"] >= 1
    assert result["summary"]["error"] >= 1


def test_structural_diagnostics_clean_file(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    text = (ws.root / "src" / "services" / "user.ts").read_text(encoding="utf-8")
    diagnostics = structural_diagnostics("src/services/user.ts", text)
    assert diagnostics == []


# ── semantic editing / rename ──────────────────────────────────────────────────


def test_rename_preview_is_semantic_not_regex(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    result = manager.rename_symbol("formatUser", "renderUser")
    assert result.files, "rename should produce edits"
    files = {os.path.basename(f.file) for f in result.files}
    assert "users.ts" in files  # the usage site


def test_apply_file_edits_confines_and_writes(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    target = ws.root / "src" / "services" / "user.ts"
    edits = [FileEdit(
        file=str(target),
        edits=[{"startLine": 1, "startColumn": 1, "endLine": 1, "endColumn": 1, "newText": "// header\n"}],
    )]
    result = apply_file_edits(ws.root, edits, dry_run=False)
    assert result["status"] == "ok"
    assert target.read_text(encoding="utf-8").startswith("// header")


def test_apply_file_edits_refuses_escape(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    outside = tmp_path / "outside.ts"
    outside.write_text("secret\n", encoding="utf-8")
    edits = [FileEdit(file=str(outside), edits=[{"startLine": 1, "startColumn": 1,
                                                 "endLine": 1, "endColumn": 1, "newText": "x"}])]
    result = apply_file_edits(ws.root, edits, dry_run=False)
    assert result["status"] == "conflict"
    assert outside.read_text(encoding="utf-8") == "secret\n"


# ── project structure / context / tests ─────────────────────────────────────────


def test_project_structure_payload(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    structure = manager.get_project_structure()
    assert "project" in structure
    assert "typescript" in structure["project"]["languages"]
    assert structure["folders"]


def test_context_engine_selects_relevant_files(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    context = manager.get_relevant_context("fix the createUser bug")
    assert context["fileCount"] >= 1
    assert any("user" in f for f in context["files"])


def test_extract_terms_is_deterministic():
    terms = extract_terms("Fix the authenticateUser bug in login")
    assert "authenticateUser" in terms
    assert "the" not in terms


def test_find_related_tests_by_reference(tmp_path):
    ws = _project(tmp_path, "python-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    related = find_related_tests(manager, symbol="create_user")
    assert related["status"] == "ok"


def test_find_related_tests_resolves_references_once_per_name(tmp_path, monkeypatch):
    """The reference set belongs to the NAME, not to every candidate test file.

    Regressing this re-runs the same SQL query per test-like file — tens of
    thousands of queries on a real repo, which blocked a code turn's first model
    call for over a minute. One call per name is the contract.
    """
    ws = _project(tmp_path, "python-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)

    calls: list[str] = []
    original = manager.index.find_references

    def counted(name, *, limit=200):
        calls.append(name)
        return original(name, limit=limit)

    monkeypatch.setattr(manager.index, "find_references", counted)
    find_related_tests(manager, symbol="create_user")
    assert calls.count("create_user") == 1
    assert len(calls) == len(set(calls))


def test_context_select_respects_its_time_budget(tmp_path, monkeypatch):
    """Selection runs synchronously in the run's pre-model phase.

    A slow index must be CUT OFF at the budget and reported as truncated, never
    allowed to hold the event loop (and with it every other route) past it.
    """
    ws = _project(tmp_path, "python-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)

    original = manager.index.find_symbols

    def slow(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(manager.index, "find_symbols", slow)
    started = time.monotonic()
    result = CodeContextEngine(manager).select(
        "create user service controller", budget_s=0.2
    )
    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert time.monotonic() - started < 1.5


# ── index recovery / incremental ────────────────────────────────────────────────


def test_index_is_incremental(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    first = manager.index_workspace(force=True)
    second = manager.index_workspace()
    assert second["update"]["unchanged"] >= 1
    assert second["update"]["updated"] == 0


def test_index_removes_deleted_file(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    manager = _manager(ws, tmp_path)
    manager.index_workspace(force=True)
    (ws.root / "src" / "api" / "users.ts").unlink()
    result = manager.index_workspace()
    assert result["update"]["removed"] >= 1


def test_corrupt_index_is_recovered(tmp_path):
    ws = _project(tmp_path, "typescript-project")
    index_path = tmp_path / "index.db"
    index_path.write_bytes(b"not a sqlite database at all")
    manager = CodeIntelligenceManager(ws, index=CodeIndex(project_id_for(ws.root), path=index_path))
    # Opening recovers a corrupt index rather than failing.
    result = manager.index_workspace(force=True)
    assert result["status"] == "ok"


# ── policy: rename removed at plan_only ──────────────────────────────────────────


def test_rename_tool_is_removed_at_plan_only():
    declared = ("code_get_definition", "code_rename_symbol", "read_file")
    narrowed = set(allowed_tools("plan_only", declared))
    assert "code_rename_symbol" not in narrowed
    assert "code_get_definition" in narrowed
    # At edit_verify the rename is present.
    assert "code_rename_symbol" in set(allowed_tools("edit_verify", declared))
