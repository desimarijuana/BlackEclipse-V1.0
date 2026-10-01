"""Phase 3 — the bounded execution primitive (sandbox.py).

Proves the non-negotiable behaviours: a scrubbed environment, a wall-clock
timeout that kills the whole tree, an honest output cap, and a refusal when no
isolation primitive exists (never an unsandboxed fallback).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from harness.code import commands, sandbox
from harness.code.sandbox import RunSpec, SandboxUnavailable, build_env

FIXTURES = Path(__file__).parent / "fixtures" / "code"
VENDORED = commands.executable_path(commands.COMMAND_CLASSES["python_test"])


def _spec(argv, *, timeout_s=30, cap=100_000, cwd=None, network=False):
    return RunSpec(
        argv=argv, cwd=cwd or FIXTURES, env=build_env(),
        timeout_s=timeout_s, output_cap_bytes=cap, network=network,
    )


def _run_fixture(name, *, timeout_s=30, cap=100_000):
    return sandbox.run(_spec([VENDORED, str(FIXTURES / name)], timeout_s=timeout_s, cap=cap))


# ── environment scrub ───────────────────────────────────────────────────────


def test_build_env_excludes_secrets(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "super-secret")
    monkeypatch.setenv("HARNESS_CALLBACK_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    env = build_env()
    for name in ("CRON_SECRET", "HARNESS_CALLBACK_TOKEN", "OPENAI_API_KEY"):
        assert name not in env
    assert env.get("PYTHONIOENCODING") == "utf-8"


def test_fixture_echoing_secret_finds_nothing(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "super-secret")
    monkeypatch.setenv("HARNESS_CALLBACK_TOKEN", "tok")
    result = _run_fixture("echo_secret.py")
    assert result.exit_code == 0
    assert "super-secret" not in result.output
    assert "CRON_SECRET=ABSENT" in result.output
    assert "HARNESS_CALLBACK_TOKEN=ABSENT" in result.output


# ── benign / failing ────────────────────────────────────────────────────────


def test_benign_fixture_exit_zero():
    result = sandbox.run(_spec([VENDORED, "-m", "pytest", "benign_check.py", "-q"]))
    assert result.exit_code == 0
    assert "1 passed" in result.output


def test_failing_fixture_exit_nonzero():
    result = sandbox.run(_spec([VENDORED, "-m", "pytest", "failing_check.py", "-q"]))
    assert result.exit_code != 0
    assert "failed" in result.output.lower()


# ── timeout + process-tree kill (no orphan) ─────────────────────────────────


def _count_python_children() -> int:
    """A best-effort count of python processes, for the orphan assertion.

    Uses `tasklist` (the same tool the acceptance gate uses) rather than `wmic`,
    which is absent on newer Windows builds.
    """
    if os.name != "nt":
        return 0
    import subprocess

    for image in ("python.exe", "python3.exe"):
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:  # noqa: BLE001
            continue
        lines = [ln for ln in out.stdout.splitlines() if image in ln]
        if out.returncode == 0:
            return len(lines)
    return -1


def test_infinite_loop_is_killed_timed_out():
    result = _run_fixture("infinite_check.py", timeout_s=2)
    assert result.timed_out is True
    assert result.killed is True
    # The tree was killed; the call returned promptly (well under a hang).
    assert result.duration_ms < 30_000


def test_kill_leaves_no_orphan_python_process():
    before = _count_python_children()
    result = _run_fixture("infinite_check.py", timeout_s=1)
    assert result.timed_out is True
    time.sleep(1.0)
    after = _count_python_children()
    if before < 0 or after < 0:
        pytest.skip("process enumeration unavailable on this host")
    # The killed child must not persist as a new python process.
    assert after <= before


# ── output cap honesty ──────────────────────────────────────────────────────


def test_flood_output_is_truncated_with_total_chars():
    result = _run_fixture("flood_check.py", cap=50_000)
    assert result.truncated is True
    assert result.total_chars > 50_000
    assert len(result.output) <= 50_000


# ── cancellation ────────────────────────────────────────────────────────────


def test_cancellation_kills_the_tree():
    cancel = threading.Event()
    cancel.set()
    result = sandbox.run(_spec([VENDORED, str(FIXTURES / "infinite_check.py")], timeout_s=30),
                         cancel_event=cancel)
    assert result.cancelled is True
    assert result.killed is True


# ── missing isolation primitive → refuse, never run ─────────────────────────


def test_sandbox_unavailable_refuses_never_runs():
    class _Unavailable:
        name = "unavailable"
        guarantees = ()

        def run(self, spec, *, cancel_event=None):
            raise SandboxUnavailable("no isolation primitive on this host")

    original = sandbox.select_backend
    sandbox.set_backend(_Unavailable())
    try:
        with pytest.raises(SandboxUnavailable):
            sandbox.run(_spec([VENDORED, str(FIXTURES / "benign_check.py")]))
    finally:
        sandbox.set_backend(None)
        assert sandbox.select_backend() is not None


def test_select_backend_reports_a_real_name():
    backend = sandbox.select_backend()
    assert backend.name in ("windows-job", "posix-rlimit")
    assert "process_tree_kill" in backend.guarantees
