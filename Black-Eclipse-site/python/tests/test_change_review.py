"""Phase 19 G3/G4 — the change-quality rules fire, and an unevaluable rule is
never reported as clean. Hermetic: a temp repo root, constructed diffs.
"""

from __future__ import annotations

from harness.code.review import DiffFile, DiffView, review_change


def _write(root, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rules(result) -> set[str]:
    return {f.rule for f in result.findings}


def test_a_clean_diff_produces_no_findings_and_nothing_unevaluated(tmp_path):
    _write(tmp_path, "src/foo.ts", "export const x = 1;\n")
    _write(tmp_path, "docs/CHANGELOG.md", "# Change Log\n- did a thing\n")
    view = DiffView(files=[
        DiffFile(path="src/foo.ts", status="modified", added_lines=("export const x = 2;",)),
        DiffFile(path="docs/CHANGELOG.md", status="modified", added_lines=("- did a thing",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    assert result.findings == []
    assert result.unevaluated == []
    assert result.files_reviewed == 2


def test_protected_path_finding_agrees_with_the_policy(tmp_path):
    from harness.code import policy

    _write(tmp_path, "python/harness/code/policy.py", "# the policy module\n")
    # The enforcement mechanism and the report must agree on the SAME rule.
    assert policy.is_protected("python/harness/code/policy.py") is True

    view = DiffView(files=[
        DiffFile(path="python/harness/code/policy.py", status="modified", added_lines=("x = 1",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    protected = [f for f in result.findings if f.rule == "protected-path"]
    assert protected and protected[0].severity == "blocking"


def test_size_ratchet_fires_on_a_pinned_file_that_grew(tmp_path):
    _write(tmp_path, "python/harness/graph.py", "x\n" * 1300)
    _write(tmp_path, "python/tests/test_size_budget.py", 'RATCHET_PY = {\n    "graph.py": 1290,\n}\n')
    view = DiffView(files=[
        DiffFile(path="python/harness/graph.py", status="modified", added_lines=("x",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    assert "size-ratchet" in _rules(result)


def test_size_ratchet_fires_on_an_unpinned_oversized_file(tmp_path):
    _write(tmp_path, "python/harness/newbig.py", "x\n" * 1300)
    view = DiffView(files=[
        DiffFile(path="python/harness/newbig.py", status="added", added_lines=("x",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    assert "size-ratchet" in _rules(result)


def test_new_module_reachable_fires_until_something_uses_it(tmp_path):
    _write(tmp_path, "python/harness/widget.py", "y = 1\n")
    view = DiffView(files=[
        DiffFile(path="python/harness/widget.py", status="added", added_lines=("y = 1",)),
    ])
    first = review_change(view, repo_root=tmp_path)
    assert "new-module-reachable" in _rules(first)

    _write(tmp_path, "python/harness/consumer.py", "import widget\n")
    second = review_change(view, repo_root=tmp_path)
    assert "new-module-reachable" not in _rules(second)


def test_string_is_key_fires_on_a_raw_user_facing_sentence(tmp_path):
    _write(tmp_path, "src/panel.tsx", "const a = 1;\n")
    view = DiffView(files=[
        DiffFile(path="src/panel.tsx", status="modified",
                 added_lines=("        >Your portfolio is ready to review today<",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    findings = [f for f in result.findings if f.rule == "string-is-key"]
    assert findings and findings[0].line == 1


def test_doc_obligation_and_test_touched(tmp_path):
    _write(tmp_path, "src/foo.ts", "x\n")
    _write(tmp_path, "python/tests/test_foo.py", "def test_x():\n    pass\n")
    view = DiffView(files=[
        DiffFile(path="src/foo.ts", status="modified", added_lines=("x",)),
        DiffFile(path="python/tests/test_foo.py", status="modified", added_lines=("pass",)),
    ])
    result = review_change(view, repo_root=tmp_path)
    assert {"doc-obligation", "test-touched"} <= _rules(result)


def test_an_unreadable_file_is_unevaluated_not_clean(tmp_path):
    view = DiffView(files=[
        DiffFile(path="src/blob.bin", status="modified", added_lines=(), unreadable=True),
    ])
    result = review_change(view, repo_root=tmp_path)
    # The file itself is reported as unevaluated, never silently swept; the only
    # finding is the repo-wide change-log obligation (a non-test change).
    assert result.unevaluated and "blob.bin" in result.unevaluated[0]
    assert _rules(result) <= {"doc-obligation"}


def test_an_empty_diff_is_never_reported_as_clean(tmp_path):
    result = review_change(DiffView(), repo_root=tmp_path)
    assert result.findings == []
    assert result.unevaluated == ["there was no change to review"]
