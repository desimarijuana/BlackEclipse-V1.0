"""The verdict-leak tripwire (Harness² borrowings, first slice)."""

from __future__ import annotations

import pytest

from harness.evaluation.verdict_guard import (
    VerdictLeakError,
    assert_no_verdict_leaks,
    assert_text_has_no_verdict_leaks,
    find_marker_in_text,
    find_verdict_leaks,
)


def test_clean_tree_passes(tmp_path):
    (tmp_path / "task.md").write_text("Fix the failing integration.\n", encoding="utf-8")
    (tmp_path / "rollouts").mkdir()
    (tmp_path / "rollouts" / "base.md").write_text(
        '{"events": [{"type": "run.completed"}]}\n', encoding="utf-8"
    )
    assert find_verdict_leaks(tmp_path) == []
    assert_no_verdict_leaks(tmp_path)


def test_content_marker_raises_with_location(tmp_path):
    lesson = tmp_path / "lesson.md"
    lesson.write_text("The candidate reached pass_rate 0.9 after the edit.\n", encoding="utf-8")
    hits = find_verdict_leaks(tmp_path)
    assert len(hits) == 1 and "lesson.md" in hits[0] and "pass_rate" in hits[0]
    with pytest.raises(VerdictLeakError, match="pass_rate"):
        assert_no_verdict_leaks(tmp_path)


def test_name_marker_raises_even_when_content_clean(tmp_path):
    (tmp_path / "expected_output.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(VerdictLeakError, match="expected_output"):
        assert_no_verdict_leaks(tmp_path)


def test_binary_suffix_is_not_scanned(tmp_path):
    (tmp_path / "chart.png").write_bytes(b"weighted_composite")
    assert_no_verdict_leaks(tmp_path)


def test_text_api(tmp_path):
    assert_text_has_no_verdict_leaks("A clean lesson with no outcomes baked in.")
    with pytest.raises(VerdictLeakError, match="expected_state"):
        assert_text_has_no_verdict_leaks("expected_state: {score: 1}", label="lesson body")
    assert find_marker_in_text("weightedComplement") is None
    assert find_marker_in_text("weighted_composite 0.91") == "weighted_composite"


def test_missing_directory_is_clean(tmp_path):
    assert find_verdict_leaks(tmp_path / "does-not-exist") == []
    assert_no_verdict_leaks(tmp_path / "does-not-exist")
