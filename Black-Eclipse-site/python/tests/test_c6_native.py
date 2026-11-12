"""C6: native isolation backends are truthful about what the host can enforce."""

from __future__ import annotations

import sys

from harness.security.native import (
    NativeSandbox,
    bwrap_argv,
    seatbelt_argv,
    seatbelt_policy,
)
from harness.security.sandbox import SandboxSpec


def _spec(**overrides) -> SandboxSpec:
    defaults = dict(
        argv=["python", "-c", "print(1)"],
        allow_network=False,
        mounts=[("C:/work", "/workspace", False)],
        env={"A": "1"},
    )
    defaults.update(overrides)
    return SandboxSpec(**defaults)


def test_bubblewrap_denies_network_and_mounts_only_the_workspace():
    argv = bwrap_argv(_spec())
    joined = " ".join(argv)
    assert "--unshare-net" in argv
    assert "--die-with-parent" in argv
    assert "--ro-bind / /" in joined
    assert "--bind C:/work /workspace" in joined
    assert "--clearenv" in argv
    assert argv[-3:] == ["python", "-c", "print(1)"] or argv[-4:] == ["-c", "print(1)"]


def test_bubblewrap_read_only_mount_and_network_permission():
    argv = bwrap_argv(_spec(
        allow_network=True, mounts=[("/data", "/workspace", True)],
    ))
    joined = " ".join(argv)
    assert "--unshare-net" not in argv
    assert "--ro-bind /data /workspace" in joined


def test_seatbelt_policy_denies_writes_and_network_by_default():
    policy = seatbelt_policy(_spec(mounts=[("/work", "/workspace", False)]))
    assert "(deny network*)" in policy
    assert "(deny file-write*)" in policy
    assert '(allow file-write* (subpath "/work"))' in policy
    assert "sandbox-exec" in seatbelt_argv(_spec())[0]


def test_seatbelt_read_only_mount_gets_no_write_exception():
    policy = seatbelt_policy(_spec(mounts=[("/work", "/workspace", True)]))
    assert 'subpath "/work"' not in policy
    assert "(deny network*)" in policy


def test_the_native_backend_is_honest_about_this_host():
    caps = NativeSandbox().capabilities()
    assert caps["processIsolation"] is True
    assert caps["secretIsolation"] is True
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        # Capability follows the actual tool; do not assert it is installed.
        assert isinstance(caps["filesystemIsolation"], bool)
    else:
        assert caps["filesystemIsolation"] is False
        assert caps["networkIsolation"] is False
        assert "Windows" in caps["note"]


def test_an_unavailable_native_backend_refuses_execution():
    sandbox = NativeSandbox()
    if sandbox.available():
        return  # a real primitive is installed; covered by the argv tests
    result = sandbox.execute(None, _spec())
    assert result.refused
    assert "unavailable" in result.reason


def test_windows_appcontainer_is_opt_in_and_honest(monkeypatch):
    from harness.security.appcontainer import WindowsAppContainerSandbox

    monkeypatch.delenv("BLACK_ECLIPSE_WINDOWS_APPCONTAINER", raising=False)
    box = WindowsAppContainerSandbox()
    caps = box.capabilities()
    assert box.available() is False
    assert caps["filesystemIsolation"] is False
    assert caps["networkIsolation"] is False
    result = box.execute(None, _spec())
    assert result.refused
    assert "BLACK_ECLIPSE_WINDOWS_APPCONTAINER" in caps["note"]


def test_enabling_the_appcontainer_elsewhere_does_not_pretend_on_another_os(monkeypatch):
    import sys as _sys

    from harness.security.appcontainer import WindowsAppContainerSandbox

    if _sys.platform == "win32":
        return
    monkeypatch.setenv("BLACK_ECLIPSE_WINDOWS_APPCONTAINER", "1")
    assert WindowsAppContainerSandbox().available() is False
