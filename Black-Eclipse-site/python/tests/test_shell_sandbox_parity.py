"""W6 — the real-shell surface uses the isolation primitives, not raw Popen."""

from __future__ import annotations

import time

from harness.code import shell
from harness.code.sandbox import RawResult, SandboxUnavailable


def test_shell_run_builds_a_sandbox_spec(monkeypatch):
    captured = {}

    def fake_run(spec):
        captured["spec"] = spec
        return RawResult(
            exit_code=0, timed_out=False, killed=False, cancelled=False,
            output="hello\n", truncated=False, total_chars=6, duration_ms=12,
            backend="test",
        )

    monkeypatch.setattr("harness.code.sandbox.run", fake_run)
    result = shell.run("echo hello", cwd=shell.Path("."), timeout_s=5)

    spec = captured["spec"]
    assert spec.argv[-1] == "echo hello"
    assert "HARNESS_CALLBACK_TOKEN" not in spec.env
    assert spec.network is False
    assert spec.timeout_s == 5
    assert result.stdout == "hello\n"
    assert result.status == "success"
    assert result.exit_code == 0


def test_shell_run_maps_timeout_kill_and_refusal(monkeypatch):
    monkeypatch.setattr(
        "harness.code.sandbox.run",
        lambda spec: RawResult(
            exit_code=None, timed_out=True, killed=True, cancelled=False,
            output="", truncated=False, total_chars=0, duration_ms=99,
            backend="test",
        ),
    )
    timed = shell.run("sleep 99", cwd=shell.Path("."), timeout_s=1)
    assert timed.timed_out is True and timed.status == "timeout"

    def refuse(spec):
        raise SandboxUnavailable("no primitive")

    monkeypatch.setattr("harness.code.sandbox.run", refuse)
    refused = shell.run("echo x", cwd=shell.Path("."))
    assert refused.status == "failed"
    assert refused.stderr.startswith("SANDBOX_UNAVAILABLE")
    assert refused.exit_code is None


def test_shell_spawn_uses_the_isolation_spawner(monkeypatch):
    class _Proc:
        pid = 1234
        stdout = None
        stderr = None

        def poll(self):
            return None

        def wait(self, timeout=None):  # noqa: ARG002
            return 0

    class _Spawned:
        proc = _Proc()
        killed = False

        def kill_tree(self):
            self.killed = True

    spawned = _Spawned()
    seen = {}

    def fake_spawn(spec):
        seen["spec"] = spec
        return spawned

    monkeypatch.setattr("harness.terminal.spawn.spawn_process", fake_spawn)
    handle = shell.spawn("echo hi", cwd=shell.Path("."))
    try:
        assert seen["spec"].argv[-1] == "echo hi"
        assert handle._spawned is spawned
        assert shell.kill(handle.pid) is True
        assert spawned.killed is True
    finally:
        shell._PROCESSES.pop(handle.pid, None)
