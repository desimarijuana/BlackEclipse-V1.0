"""C6.9 opt-in live smoke: the Windows AppContainer actually isolates a child.

Run only when the operator enables the backend:
    BLACK_ECLIPSE_WINDOWS_APPCONTAINER=1 node scripts/test-python.js \
        python/tests/test_c6_appcontainer_live.py
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.skipif(
    not (sys.platform == "win32" and os.environ.get("BLACK_ECLIPSE_WINDOWS_APPCONTAINER") == "1"),
    reason="opt-in Windows AppContainer smoke: set BLACK_ECLIPSE_WINDOWS_APPCONTAINER=1",
)


def test_appcontainer_runs_a_command_with_no_network_capability():
    from harness.security.appcontainer import WindowsAppContainerSandbox
    from harness.security.sandbox import SandboxSpec

    box = WindowsAppContainerSandbox()
    assert box.available()
    caps = box.capabilities()
    assert caps["filesystemIsolation"] is True
    assert caps["networkIsolation"] is True

    work = tempfile.mkdtemp(prefix="be-ac-live-")
    spec = SandboxSpec(
        argv=[r"C:\Windows\System32\cmd.exe", "/c", "echo ac-ok"],
        cwd=work,
        timeout_s=30,
    )
    result = box.execute(box.create(spec), spec)
    assert not result.refused, result.reason
    assert result.exit_code == 0, (result.stdout, result.stderr)
    assert "ac-ok" in result.stdout


def test_appcontainer_cannot_read_outside_its_granted_workspace():
    from harness.security.appcontainer import WindowsAppContainerSandbox
    from harness.security.sandbox import SandboxSpec

    box = WindowsAppContainerSandbox()
    work = tempfile.mkdtemp(prefix="be-ac-work-")
    outside = tempfile.mkdtemp(prefix="be-ac-outside-")
    inside_file = os.path.join(work, "inside.txt")
    outside_file = os.path.join(outside, "secret.txt")
    with open(inside_file, "w", encoding="utf-8") as handle:
        handle.write("inside-visible")
    with open(outside_file, "w", encoding="utf-8") as handle:
        handle.write("outside-secret")

    def run(target: str):
        spec = SandboxSpec(
            argv=[r"C:\Windows\System32\cmd.exe", "/c", "type", target],
            cwd=work, timeout_s=30,
        )
        return box.execute(box.create(spec), spec)

    visible = run(inside_file)
    assert not visible.refused, visible.reason
    assert "inside-visible" in visible.stdout

    blocked = run(outside_file)
    assert "outside-secret" not in blocked.stdout
    assert not blocked.ok
