"""Generic terminal classification (Phase D).

The classifier is the whole safety surface for arbitrary commands. These tests
pin the three classes: safe tools allow, unknown tools ask, destructive shapes
deny — and that tokenization is shell-free, so a smuggled second command is
inert text rather than an executed one.
"""

from __future__ import annotations

import os
from pathlib import Path

from harness.code import terminal


def test_safe_interpreters_are_allowed():
    for cmd in ("python app.py", "python3 -m pytest", "node index.js", "npm test", "git status", "ls -la"):
        assert terminal.classify(cmd).kind == "allow", cmd


def test_unknown_program_asks():
    v = terminal.classify("frobnicate --go")
    assert v.kind == "ask"
    assert v.program == "frobnicate"


def test_git_write_subcommand_asks():
    assert terminal.classify("git status").kind == "allow"
    assert terminal.classify("git push origin main").kind == "ask"
    assert terminal.classify("git reset --hard").kind == "ask"


def test_destructive_programs_denied():
    for cmd in ("rm -rf /", "format C:", "shutdown -h now", "reg add HKCU", "sudo rm x", "dd if=/dev/zero of=/dev/sda"):
        assert terminal.classify(cmd).kind == "deny", cmd


def test_shells_and_downloaders_denied():
    for cmd in ("bash -c 'x'", "sh script.sh", "powershell Get-Process", "cmd /c dir", "curl http://x", "wget http://x"):
        assert terminal.classify(cmd).kind == "deny", cmd


def test_shell_smuggling_is_inert_text():
    # No shell means the `;` does not start a second command. The classification
    # is on the FIRST program; the rest are arguments.
    v = terminal.classify("python -c 'print(1)' ; rm -rf /")
    # Either the deny-arg scan catches it, or it is treated as python with args;
    # in no case is `rm` executed as its own program.
    assert v.kind in ("ask", "deny")


def test_pipe_to_shell_denied():
    assert terminal.classify("cat x | bash").kind == "deny"


def test_empty_command_denied():
    assert terminal.classify("   ").kind == "deny"


def test_too_long_command_denied():
    assert terminal.classify("python " + "a" * (terminal.MAX_COMMAND_CHARS + 10)).kind == "deny"


def test_build_run_spec_sets_no_network_and_env(tmp_path):
    spec = terminal.build_run_spec("python app.py", cwd=tmp_path, timeout_s=30)
    assert spec.argv == ["python", "app.py"]
    assert spec.network is False
    assert spec.timeout_s == 30
    assert "PATH" in spec.env or os.name != "nt"
    # A scrubbed env: nothing outside the allowlist leaks.
    assert all(k in terminal.policy.SECRET_ENV_ALLOWLIST for k in spec.env)


def test_build_run_spec_rejects_a_denied_command(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        terminal.build_run_spec("rm -rf /", cwd=tmp_path)


def test_timeout_is_clamped(tmp_path):
    spec = terminal.build_run_spec("python x.py", cwd=tmp_path, timeout_s=99999)
    assert spec.timeout_s == terminal.MAX_TIMEOUT_S
