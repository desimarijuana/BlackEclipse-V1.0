"""Shell detection, redaction, runtimes and port parsing."""

from __future__ import annotations

import os

import pytest

from harness.terminal import redaction, runtimes, shell_detect
from harness.terminal import port_manager
from harness.terminal.runtimes import RuntimeUnavailable


# ── ShellDetector ────────────────────────────────────────────────────────────


def test_detects_at_least_one_shell_on_this_host():
    shells = shell_detect.detect_shells()
    assert shells, "no shell detected on a host that clearly has one"
    assert all(s.path for s in shells if s.name != "wsl")


def test_default_shell_is_a_detected_shell():
    default = shell_detect.default_shell()
    assert default is not None
    assert default.name in {s.name for s in shell_detect.detect_shells()}


def test_resolve_shell_by_name_and_unknown():
    default = shell_detect.default_shell()
    assert default is not None
    assert shell_detect.resolve_shell(default.name) is default
    assert shell_detect.resolve_shell("definitely-not-a-shell") is None


def test_capabilities_are_honest_shape():
    caps = shell_detect.capabilities().to_dict()
    assert caps["platform"] in ("windows", "linux", "darwin")
    assert isinstance(caps["shells"], list)
    assert isinstance(caps["runtimes"], list)
    assert "local" in caps["runtimes"]
    assert isinstance(caps["pty"], bool)
    # The `docker` flag tracks the IMPLEMENTATION, which does not exist yet, so it
    # is always False. `ssh` reflects whether the ssh client is installed, which
    # is a host fact; the SSH RUNTIME itself still refuses (asserted elsewhere).
    assert caps["docker"] is False
    assert isinstance(caps["ssh"], bool)


def test_wsl_probe_never_raises_and_is_structured():
    info = shell_detect.detect_wsl().to_dict()
    assert isinstance(info["available"], bool)
    if not info["available"]:
        assert info["reason"]


# ── SecretRedactor ───────────────────────────────────────────────────────────


def test_redacts_assignment_values_but_keeps_the_key():
    out = redaction.redact("DATABASE_URL=postgres://user:hunter2@host/db")
    assert "hunter2" not in out
    assert "DATABASE_URL" in out
    assert redaction.REDACT_MARKER in out


def test_redacts_url_credentials():
    out = redaction.redact("connecting to postgres://admin:s3cret@db.internal:5432/app")
    assert "s3cret" not in out
    assert "admin" in out


def test_redacts_a_known_secret_token():
    token = "sk-abcdef0123456789abcdef0123456789"
    out = redaction.redact(f"OPENAI_API_KEY={token}")
    assert token not in out


def test_redact_env_masks_sensitive_names_only():
    masked = redaction.redact_env({"API_KEY": "abc", "PATH": "/usr/bin", "MY_SECRET": "x"})
    assert masked["API_KEY"] == redaction.REDACT_MARKER
    assert masked["MY_SECRET"] == redaction.REDACT_MARKER
    assert masked["PATH"] == "/usr/bin"


def test_redaction_is_idempotent_and_empty_safe():
    assert redaction.redact("") == ""
    once = redaction.redact("TOKEN=abc123")
    assert redaction.redact(once) == once


# ── Runtimes ──────────────────────────────────────────────────────────────────


def test_local_runtime_is_available_and_wraps_the_shell():
    runtime = runtimes.select_runtime("local")
    assert runtime.available
    argv = runtime.build_argv("echo hi", shell=None, cwd=os.getcwd())
    assert argv[-1] == "echo hi"
    assert len(argv) > 1


def test_docker_and_ssh_refuse_honestly_not_fall_back():
    for name in ("docker", "ssh"):
        runtime = runtimes.select_runtime(name)
        assert runtime.available is False
        with pytest.raises(RuntimeUnavailable) as info:
            runtime.build_argv("x", shell=None, cwd=".")
        assert info.value.code == "NOT_IMPLEMENTED"


def test_wsl_runtime_refuses_when_not_installed():
    runtime = runtimes.WSLruntime()
    if runtime.available:
        pytest.skip("WSL is installed on this host")
    with pytest.raises(RuntimeUnavailable) as info:
        runtimes.select_runtime("wsl")
    assert info.value.code == "RUNTIME_UNAVAILABLE"


def test_windows_path_maps_to_wsl_mount():
    assert runtimes._windows_to_wsl(r"C:\Users\me\project") == "/mnt/c/Users/me/project"
    assert runtimes._windows_to_wsl("C:\\") == "/mnt/c"
    assert runtimes._windows_to_wsl("/already/posix") == "/already/posix"


def test_unknown_runtime_refuses():
    with pytest.raises(RuntimeUnavailable) as info:
        runtimes.select_runtime("quantum-shell")
    assert info.value.code == "INVALID_ARGUMENT"


def test_describe_runtimes_reports_docker_and_ssh_unimplemented():
    described = runtimes.describe_runtimes()
    assert described["local"]["available"] is True
    assert described["docker"]["implemented"] is False
    assert described["ssh"]["implemented"] is False


# ── PortManager parsing ────────────────────────────────────────────────────────


_WINDOWS_NETSTAT = """
  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING       18432
  TCP    127.0.0.1:5432         0.0.0.0:0              LISTENING       9123
  TCP    0.0.0.0:3000           0.0.0.0:0              ESTABLISHED     18432
"""

_POSIX_SS = """State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
LISTEN 0      128    0.0.0.0:8080      0.0.0.0:*     users:(("node",pid=555,fd=20))
LISTEN 0      128    127.0.0.1:6379    0.0.0.0:*     users:(("redis",pid=777,fd=6))
"""


def test_parse_windows_netstat_keeps_only_listening():
    ports = port_manager._parse_netstat_windows(_WINDOWS_NETSTAT)
    got = {(p.port, p.pid) for p in ports}
    assert (3000, 18432) in got
    assert (5432, 9123) in got
    # The ESTABLISHED row is not a listener.
    assert len(ports) == 2


def test_parse_posix_ss_reads_pid():
    ports = port_manager._parse_ss_posix(_POSIX_SS)
    got = {(p.port, p.pid) for p in ports}
    assert (8080, 555) in got
    assert (6379, 777) in got


def test_summarize_partitions_development_ports():
    info = port_manager.PortInfo(port=3000, pid=1, process_id=None, address="0.0.0.0", protocol="tcp", status="listening")
    other = port_manager.PortInfo(port=44444, pid=2, process_id=None, address="0.0.0.0", protocol="tcp", status="listening")
    summary = port_manager.summarize([info, other])
    assert summary["count"] == 2
    assert summary["development"][0]["port"] == 3000
    assert summary["other"][0]["port"] == 44444
