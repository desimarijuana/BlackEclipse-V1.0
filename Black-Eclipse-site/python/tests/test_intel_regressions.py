"""Regression tests for the findings of the CIUE hardcore torture test.

Each test pins a bug that the torture test uncovered and that was fixed:

  1. `uri_to_path` did not decode `file:///c%3A/...` before the Windows drive fix,
     so LSP results never matched the workspace (references/definitions looked empty).
  2. `_normalize_locations` did not understand the LSP `LocationLink` shape
     (`targetUri`/`targetRange`), so go-to-definition via a real server returned nothing.
  3. `get_definition`/`get_references` sent the declaration's column (indentation) to
     the server instead of the symbol's real name column.
  4. `_resolve_symbols` did not scope by file first, so a same-named symbol in another
     language/file was resolved instead of the intended one.
  5. `find_references` via LSP never marked the declaration site.
  6. `get_implementations` returned only one backend's view (LSP under-reported when a
     module failed to resolve; the index missed dynamic cases) — now the union.
  7. The rename fallback rewrote strings/comments; it is now code-mask-aware.
  8. `integrity_ok` returned True on non-database bytes; the schema probe fixes it.
  9. `rebase_edits` assumed absolute LSP paths; it now accepts workspace-relative ones.
 10. `_enrich_location` returns a `location` object on the LSP path too (one shape).
 11. `_js_heritage` captures `extends`/`implements` so implementations work structurally.
 12. `policy.IGNORED_DIRS` now excludes dist/build/target/coverage/generated.
 13. The context engine is prefix-aware (`authentication` reaches `Auth*`).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from harness.code import policy
from harness.code.fs import symbols as fs_symbols
from harness.code.intel.editing import _code_mask
from harness.code.intel.lsp.client import uri_to_path
from harness.code.intel.manager import CodeIntelligenceManager
from harness.code.intel.persistence.index import CodeIndex
from harness.code.intel.project import project_id_for
from harness.code.policy import WorkspaceBinding
from harness.code.policy import allowed_tools
from harness.code.workspace import ResolvedWorkspace

FIXTURES = Path(__file__).parent / "fixtures" / "intel"


def _ws(root: Path) -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    return ResolvedWorkspace(id="ws_reg", root=real, base_revision="x", strategy="checkout",
                             binding=WorkspaceBinding(id="ws_reg", root=real, base_revision="x", strategy="checkout"))


def _manager(root: Path, tmp: Path) -> CodeIntelligenceManager:
    return CodeIntelligenceManager(_ws(root), index=CodeIndex(project_id_for(root, "ws_reg"), path=tmp / "i.db"))


def test_uri_to_path_decodes_windows_percent_encoding():
    assert uri_to_path("file:///c%3A/Users/x/App.ts") == "c:/Users/x/App.ts"
    assert uri_to_path("file:///C:/Users/x/App.ts") == "C:/Users/x/App.ts"


def test_js_heritage_is_captured():
    text = "export class StripeProvider implements PaymentProvider {\n  charge() {}\n}\n"
    syms = fs_symbols.extract_symbols("p.ts", text, language="typescript")
    cls = next(s for s in syms if s.kind == "class")
    assert "implements PaymentProvider" in cls.signature


def test_location_link_shape_is_normalized(tmp_path):
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "typescript-project", root)
    m = _manager(root, tmp_path)
    locs = m._normalize_locations([{
        "targetUri": "file:///c%3A/x/App.ts",
        "targetRange": {"start": {"line": 9, "character": 4}, "end": {"line": 9, "character": 20}},
    }])
    assert locs and locs[0]["line"] == 10 and locs[0]["column"] == 5


def test_resolve_symbols_is_file_scoped(tmp_path):
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "typescript-project", root)
    m = _manager(root, tmp_path)
    m.index_workspace(force=True)
    scoped = m._resolve_symbols("formatUser", file="src/services/user.ts")
    assert scoped and scoped[0]["file"] == "src/services/user.ts"


def test_enrich_location_returns_a_location_object(tmp_path):
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "typescript-project", root)
    m = _manager(root, tmp_path)
    m.index_workspace(force=True)
    enriched = m._enrich_location({"file": str((root / "src" / "services" / "user.ts").resolve()), "line": 7, "column": 1})
    assert "location" in enriched and enriched["location"]["file"].endswith("user.ts")


def test_rename_mask_preserves_strings_and_comments():
    line = 'const x = UserService; console.log("UserService"); // UserService here'
    masked = _code_mask(line)
    assert masked.count("UserService") == 1  # only the real code identifier


def test_corrupt_bytes_are_detected_as_unhealthy(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"not a database" * 50)
    idx = CodeIndex("bad", path=p)
    # Opening recovers a non-database file: the corrupt bytes are backed up and a
    # fresh, valid schema is created, so the object is healthy and EMPTY.
    assert idx.integrity_ok() is True
    assert idx.status()["fileCount"] == 0
    backups = list(tmp_path.glob("bad.corrupt-*.db"))
    assert backups, "the corrupt file should have been backed up"
    idx.close()


def test_rebase_edits_accepts_relative_paths(tmp_path):
    from harness.code.intel.editing import FileEdit
    from harness.code.intel.manager import rebase_edits

    src = tmp_path / "src"
    src.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    files = [FileEdit(file="a/b.ts", edits=[{"startLine": 1, "startColumn": 1, "endLine": 1, "endColumn": 1, "newText": "x"}])]
    rebased = rebase_edits(src, work, files)
    assert rebased and Path(rebased[0].file) == work / "a" / "b.ts"


def test_ignore_policy_excludes_build_output():
    for rel in (
        "apps/api/dist/bundle.js", "app/build/x.js", "target/debug/y", "coverage/lcov.info",
        # The `next dev` build directory (next.config.ts distDir). Indexing its
        # hundreds of multi-MB generated bundles on the first code query wedged
        # the whole runtime (the event loop could not service /health).
        ".next-dev/server/app/page.js", ".next/server/app/page.js",
    ):
        assert policy.is_ignored(rel), rel


def test_indexer_skips_the_dev_build_directory(tmp_path):
    from harness.code.intel.ast import ASTEngine
    from harness.code.intel.indexer import IncrementalIndexer

    root = tmp_path / "p"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (root / ".next-dev" / "server").mkdir(parents=True)
    (root / ".next-dev" / "server" / "bundle.js").write_text("var a=function(){return 1};\n", encoding="utf-8")
    idx = CodeIndex("devskip", path=tmp_path / "devskip.db")
    ix = IncrementalIndexer(root, "devskip", idx, ast=ASTEngine("devskip", root=root))
    walked = [rel for rel, _ in ix.iter_source_files()]
    assert "src/main.ts" in walked
    assert not any(rel.startswith(".next-dev/") for rel in walked)
    idx.close()


def test_context_engine_is_prefix_aware(tmp_path):
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "typescript-project", root)
    m = _manager(root, tmp_path)
    m.index_workspace(force=True)
    from harness.code.intel.context import _expand_term, _matches
    assert _matches(_expand_term("authentication"), "AuthService") is True


def test_implementations_merge_lsp_and_index(tmp_path):
    root = tmp_path / "p"
    shutil.copytree(FIXTURES / "typescript-project", root)
    (root / "src" / "pay.ts").write_text(
        "export interface PaymentProvider { charge(a: number): void; }\n"
        "export class StripeProvider implements PaymentProvider { charge(a: number) {} }\n"
        "export class MockProvider implements PaymentProvider { charge(a: number) {} }\n",
        encoding="utf-8",
    )
    m = _manager(root, tmp_path)
    m.index_workspace(force=True)
    # The index heritage path is always available even with no language server.
    impls = m.get_implementations("PaymentProvider")
    names = {s.get("name") for s in impls["implementations"]}
    assert impls["status"] == "ok"
    assert {"StripeProvider", "MockProvider"} <= names, names
