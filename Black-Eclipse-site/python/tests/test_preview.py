"""Running the user's project (Phase 24 / P2).

The plan is pure and fixed-command. The manager never invents a port: it watches
the process tree and only reports a URL when a port actually answers.
"""

from __future__ import annotations

import json

from harness.code import preview as pv


def _pkg(tmp_path, scripts: dict) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")


def test_a_package_dev_script_is_the_plan(tmp_path):
    _pkg(tmp_path, {"dev": "next dev", "start": "next start", "test": "vitest"})
    plan = pv.plan_preview(tmp_path)
    assert plan.source == "detected"
    assert plan.command == "npm run dev"
    assert plan.root == str(tmp_path)


def test_start_is_used_when_there_is_no_dev_script(tmp_path):
    _pkg(tmp_path, {"preview": "vite preview"})
    assert pv.plan_preview(tmp_path).command == "npm run preview"


def test_a_project_override_wins(tmp_path):
    override = tmp_path / ".black-eclipse"
    override.mkdir()
    (override / "preview.json").write_text(
        json.dumps({"command": "python -m myapp --dev", "label": "Run the app"}),
        encoding="utf-8",
    )
    plan = pv.plan_preview(tmp_path)
    assert plan.source == "project"
    assert plan.command == "python -m myapp --dev"
    assert plan.label == "Run the app"


def test_a_makefile_target_is_discovered(tmp_path):
    (tmp_path / "Makefile").write_text("dev:\n\tpython app.py\n", encoding="utf-8")
    plan = pv.plan_preview(tmp_path)
    assert plan.source == "detected"
    assert plan.command == "make dev"


def test_an_unrecognised_project_has_no_plan(tmp_path):
    plan = pv.plan_preview(tmp_path)
    assert plan.source == "none"
    assert plan.command == ""


class _Terminal:
    def __init__(self, ports, state="RUNNING"):
        self.ports = ports
        self.state = state

    def get_process(self, _process_id):
        return {"state": self.state, "ports": list(self.ports)}


class _Execution:
    def __init__(self, terminal):
        self.terminal = terminal
        self.started: list[dict] = []
        self.stopped: list[str] = []

    def start_service(self, **kwargs):
        self.started.append(kwargs)
        return {"status": "ok", "service": {"serviceId": "svc_1", "processId": "p1"}}

    def stop_service(self, service_id):
        self.stopped.append(service_id)
        return {"status": "ok"}

    def get_service_logs(self, _service_id, tail=200):
        return {"logs": "ready on 3000"}


def _manager(execution, monkeypatch, *, http_ok=True):
    monkeypatch.setattr(pv, "_http_ok", lambda _url, timeout_s=2.0: http_ok)
    tick = [0.0]
    clock = lambda: tick.__setitem__(0, tick[0] + 1.0) or tick[0]  # noqa: E731
    return pv.PreviewManager(execution, sleep=lambda _s: None, clock=clock)


def test_start_reports_the_port_that_answers(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    execution = _Execution(_Terminal([3000]))
    manager = _manager(execution, monkeypatch)

    result = manager.start("task_1", tmp_path)
    assert result["status"] == "ok"
    assert result["ready"] is True
    assert result["url"] == "http://127.0.0.1:3000"
    assert execution.started[0]["cwd"] == str(tmp_path)
    assert execution.started[0]["command"] == "npm run dev"

    status = manager.status("task_1")
    assert status["running"] is True

    stopped = manager.stop("task_1")
    assert stopped["stopped"] is True
    assert execution.stopped == ["svc_1"]


def test_a_process_that_never_listens_is_not_ready(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    manager = _manager(_Execution(_Terminal([])), monkeypatch)
    result = manager.start("task_2", tmp_path)
    assert result["status"] == "ok"
    assert result["ready"] is False
    assert result["url"] == ""


def test_a_crashed_process_is_not_ready(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    manager = _manager(_Execution(_Terminal([], state="CRASHED")), monkeypatch)
    result = manager.start("task_3", tmp_path)
    assert result["ready"] is False
    assert manager.status("task_3")["running"] is False


def test_idle_status_names_the_command_before_it_runs(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    manager = _manager(_Execution(_Terminal([])), monkeypatch)
    status = manager.status("task_idle", root=tmp_path)
    assert status["status"] == "idle"
    assert status["plan"]["command"] == "npm run dev"
    assert status["plan"]["source"] == "detected"


def test_idle_status_without_a_command_says_so(tmp_path, monkeypatch):
    manager = _manager(_Execution(_Terminal([])), monkeypatch)
    status = manager.status("task_none", root=tmp_path)
    assert status["plan"]["source"] == "none"


def _clock():
    tick = [0.0]

    def now():
        tick[0] += 1.0
        return tick[0]

    return now


def test_change_mode_runs_the_worktree_with_linked_deps(tmp_path, monkeypatch):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _pkg(worktree, {"dev": "next dev"})
    checkout = tmp_path / "co"
    (checkout / "node_modules").mkdir(parents=True)

    execution = _Execution(_Terminal([3000]))
    linked: list[tuple[str, str]] = []
    unlinked: list[str] = []
    manager = pv.PreviewManager(
        execution, sleep=lambda _s: None, clock=_clock(),
        link=lambda target, source: linked.append((str(target), str(source))) or True,
        unlink=lambda path: unlinked.append(str(path)),
    )
    monkeypatch.setattr(pv, "_http_ok", lambda _url, timeout_s=2.0: True)

    result = manager.start("task_x", checkout, mode="change", run_root=worktree, deps_from=checkout)
    assert result["status"] == "ok"
    assert result["mode"] == "change"
    assert result["ready"] is True
    assert execution.started[0]["cwd"] == str(worktree)
    assert linked and linked[0][0].endswith("node_modules")

    manager.stop("task_x")
    assert unlinked


def test_change_mode_without_a_prepared_change_is_refused(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    manager = _manager(_Execution(_Terminal([3000])), monkeypatch)
    result = manager.start("task_y", tmp_path, mode="change", run_root=None)
    assert result["status"] == "refused"
    assert result["code"] == "PREVIEW_CHANGE_GONE"


def test_switching_mode_stops_the_previous_server(tmp_path, monkeypatch):
    _pkg(tmp_path, {"dev": "next dev"})
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _pkg(worktree, {"dev": "next dev"})
    execution = _Execution(_Terminal([3000]))
    manager = pv.PreviewManager(
        execution, sleep=lambda _s: None, clock=_clock(),
        link=lambda _t, _s: True, unlink=lambda _p: None,
    )
    monkeypatch.setattr(pv, "_http_ok", lambda _url, timeout_s=2.0: True)

    assert manager.start("task_z", tmp_path)["mode"] == "checkout"
    assert manager.start(
        "task_z", tmp_path, mode="change", run_root=worktree, deps_from=tmp_path,
    )["mode"] == "change"
    assert execution.stopped == ["svc_1"]


def test_no_command_is_an_honest_refusal(tmp_path, monkeypatch):
    manager = _manager(_Execution(_Terminal([])), monkeypatch)
    result = manager.start("task_4", tmp_path)
    assert result["status"] == "refused"
    assert result["code"] == "PREVIEW_NO_COMMAND"
