"""The self-build acceptance eval (Phase 22 / S6).

Two rules are pinned here: a missing contract is a FAIL with its check id, and a
skipped command is never a pass. The human grade is `UNKNOWN`, never invented.
"""

from __future__ import annotations

from pathlib import Path

from harness.code import selfbuild_eval as ev


def test_the_repository_passes_its_own_acceptance_fixtures():
    report = ev.run_selfbuild_eval(Path(__file__).resolve().parents[2])
    assert report["total"] == len(ev.TASKS) >= 6
    assert report["passed"] == report["total"], [
        (task["id"], [c for c in task["checks"] if c["status"] != "passed"])
        for task in report["tasks"] if not task["passed"]
    ]
    assert all(task["humanGrade"] == "UNKNOWN" for task in report["tasks"])
    assert "humanGrade" in report["unmeasured"]


def test_a_missing_file_fails_with_its_check_id(tmp_path):
    task = ev.SelfBuildTask("t", "goal", (
        ev.Check("files", "files_exist", paths=("a.py", "b.py")),
    ))
    report = ev.run_selfbuild_eval(tmp_path, tasks=(task,))
    assert report["passed"] == 0
    assert report["tasks"][0]["checks"][0]["id"] == "files"
    assert "a.py" in report["tasks"][0]["checks"][0]["detail"]
    assert report["passRate"] == 0.0


def test_a_present_file_and_needle_pass(tmp_path):
    (tmp_path / "a.py").write_text("def load_project_rules():\n    pass\n", encoding="utf-8")
    task = ev.SelfBuildTask("t", "goal", (
        ev.Check("files", "files_exist", paths=("a.py",)),
        ev.Check("api", "file_contains", needles=(("a.py", "def load_project_rules"),)),
    ))
    report = ev.run_selfbuild_eval(tmp_path, tasks=(task,))
    assert report["passed"] == 1
    assert report["passRate"] == 1.0


def test_a_command_is_skipped_by_default_and_never_a_pass(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    task = ev.SelfBuildTask("t", "goal", (
        ev.Check("files", "files_exist", paths=("a.py",)),
        ev.Check("run", "command", argv=("python", "-c", "print(1)")),
    ))
    skipped = ev.run_selfbuild_eval(tmp_path, tasks=(task,))
    statuses = {c["id"]: c["status"] for c in skipped["tasks"][0]["checks"]}
    assert statuses["run"] == "skipped"
    assert skipped["passed"] == 1  # a skipped non-required check does not fail

    called: list[list[str]] = []

    def runner(argv, _root):
        called.append(argv)
        return 2

    failed = ev.run_selfbuild_eval(
        tmp_path, tasks=(task,), run_commands=True, runner=runner,
    )
    assert called == [["python", "-c", "print(1)"]]
    assert failed["passed"] == 0
    assert {c["id"]: c["status"] for c in failed["tasks"][0]["checks"]}["run"] == "failed"
