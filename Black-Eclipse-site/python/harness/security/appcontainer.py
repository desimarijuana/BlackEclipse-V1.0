"""Windows AppContainer backend (C6.9).

An AppContainer is the Windows-native isolation primitive: a process with a
unique package SID, no network capabilities, and filesystem access only to paths
whose ACL explicitly grants that SID. This backend launches the child with
`PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` and a scrubbed environment.

Honesty rules:
  * it is **opt-in** (`BLACK_ECLIPSE_WINDOWS_APPCONTAINER=1`). Without the flag
    the backend reports unavailable and Windows keeps the Job Object backend;
  * if profile creation or the launch fails, `execute()` returns a refusal, never
    an unrestricted run;
  * `capabilities()` only claims filesystem/network isolation when the backend is
    enabled.

The profile is created once per process and reused. The workspace is granted to
the AppContainer SID with `icacls`; the child's environment is built by
`code/sandbox.build_env`, so host secrets are absent.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .models import new_id
from .sandbox import ExecutionSandbox, SandboxHandle, SandboxResult, SandboxSpec

ENABLE_ENV = "BLACK_ECLIPSE_WINDOWS_APPCONTAINER"
PROFILE_NAME = "EclipseHarnessSandbox"
_DEFAULT_TIMEOUT_S = 120
_READ_CHUNK = 64 * 1024

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True) if sys.platform == "win32" else None
_userenv = ctypes.WinDLL("userenv", use_last_error=True) if sys.platform == "win32" else None

_HANDLE_FLAG_INHERIT = 0x1
_STARTF_USESTDHANDLES = 0x00000100
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_NO_WINDOW = 0x08000000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
_WAIT_OBJECT_0 = 0x0
_WAIT_TIMEOUT = 0x102
_ERROR_ALREADY_EXISTS = 0x800700B7


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", _STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


def _flag(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _flag(os.environ.get(ENABLE_ENV))


def exports_available() -> bool:
    return bool(
        _kernel32 is not None and _advapi32 is not None and _userenv is not None
        and hasattr(_userenv, "CreateAppContainerProfile")
        and hasattr(_userenv, "DeriveAppContainerSidFromAppContainerName")
        and hasattr(_kernel32, "UpdateProcThreadAttribute")
    )


def _sid_to_string(sid: Any) -> Optional[str]:
    out = wintypes.LPWSTR()
    if not _advapi32.ConvertSidToStringSidW(sid, ctypes.byref(out)):
        return None
    try:
        return out.value
    finally:
        _kernel32.LocalFree(out)


class WindowsAppContainerSandbox(ExecutionSandbox):
    name = "appcontainer"

    _sid: Any = None
    _sid_string: Optional[str] = None
    _granted: set[str] = set()
    _lock = threading.RLock()

    def _tool(self) -> Optional[str]:
        return "appcontainer" if (sys.platform == "win32" and enabled() and exports_available()) else None

    def available(self) -> bool:
        return self._tool() is not None

    def capabilities(self) -> dict[str, Any]:
        active = self.available()
        return {
            "backend": self.name,
            "platform": sys.platform,
            "tool": self._tool(),
            "processIsolation": True,
            "filesystemIsolation": active,
            "networkIsolation": active,
            "secretIsolation": True,
            "egressProxy": False,
            "note": (
                "Windows AppContainer (opt-in): workspace-only ACL, no network capability"
                if active else
                "enable with BLACK_ECLIPSE_WINDOWS_APPCONTAINER=1; otherwise Windows uses the Job Object backend"
            ),
        }

    # ── profile / ACL ────────────────────────────────────────────────────────
    def _ensure_profile(self) -> Any:
        with self._lock:
            if self._sid is not None:
                return self._sid
            sid = ctypes.c_void_p()
            _userenv.CreateAppContainerProfile.restype = ctypes.c_long
            _userenv.CreateAppContainerProfile.argtypes = [
                wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
            ]
            hr = _userenv.CreateAppContainerProfile(
                PROFILE_NAME, "Eclipse sandbox", "Eclipse harness isolation",
                None, 0, ctypes.byref(sid),
            )
            if (hr & 0xFFFFFFFF) == _ERROR_ALREADY_EXISTS:
                _userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
                _userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
                    wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                ]
                hr = _userenv.DeriveAppContainerSidFromAppContainerName(
                    PROFILE_NAME, ctypes.byref(sid),
                )
            if hr != 0 or not sid.value:
                raise OSError(f"CreateAppContainerProfile failed (HRESULT 0x{hr & 0xFFFFFFFF:08x})")
            self._sid = sid
            self._sid_string = _sid_to_string(sid)
            if not self._sid_string:
                raise OSError("could not serialize the AppContainer SID")
            return sid

    def _grant(self, path: Optional[str]) -> None:
        if not path:
            return
        target = str(Path(path))
        if target in self._granted:
            return
        sid = self._sid_string or ""
        if not sid:
            raise OSError("the AppContainer SID is unavailable")
        # (OI)(CI)M: inherit object+container, modify. No full control, no owner.
        result = subprocess.run(
            ["icacls", target, "/grant", f"*{sid}:(OI)(CI)M", "/C", "/Q"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise OSError(f"could not grant the workspace to the AppContainer: {result.stderr.strip()[:300]}")
        self._granted.add(target)

    # ── execute ──────────────────────────────────────────────────────────────
    def create(self, spec: SandboxSpec) -> SandboxHandle:
        return SandboxHandle(id=new_id("sbx"), backend=self.name)

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:
        if not self.available():
            return SandboxResult(
                None, "", self.capabilities()["note"], self.name, 0.0,
                refused=True, reason="sandbox unavailable",
            )
        if not spec.argv:
            return SandboxResult(None, "", "empty command", self.name, 0.0,
                                 refused=True, reason="empty command")
        started = time.time()
        try:
            sid = self._ensure_profile()
            cwd = spec.cwd or (spec.mounts[0][0] if spec.mounts else os.getcwd())
            for host, _container, _ro in spec.mounts:
                self._grant(host)
            self._grant(cwd)
            code, out, err, timed_out = self._launch(sid, spec, cwd)
        except Exception as exc:  # noqa: BLE001 - every failure is a refusal, never unbounded
            return SandboxResult(None, "", str(exc)[:2_000], self.name,
                                 time.time() - started, refused=True,
                                 reason="appcontainer launch failed")
        return SandboxResult(
            code, out, err, self.name, time.time() - started,
            limited=timed_out, reason="timeout" if timed_out else "",
        )

    def _launch(self, sid: Any, spec: SandboxSpec, cwd: str) -> tuple[Optional[int], str, str, bool]:
        from ..code.sandbox import build_env  # noqa: PLC0415

        read_end = wintypes.HANDLE()
        write_end = wintypes.HANDLE()
        sa = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
        if not _kernel32.CreatePipe(ctypes.byref(read_end), ctypes.byref(write_end), ctypes.byref(sa), 0):
            raise OSError(f"CreatePipe failed ({ctypes.get_last_error()})")
        _kernel32.SetHandleInformation(read_end, _HANDLE_FLAG_INHERIT, 0)

        size = ctypes.c_size_t(0)
        _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        attribute_list = ctypes.cast(buffer, ctypes.c_void_p)
        if not _kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(size)):
            raise OSError(f"InitializeProcThreadAttributeList failed ({ctypes.get_last_error()})")

        capabilities = _SECURITY_CAPABILITIES(sid.value, None, 0, 0)
        if not _kernel32.UpdateProcThreadAttribute(
            attribute_list, 0, _PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            ctypes.byref(capabilities), ctypes.sizeof(capabilities), None, None,
        ):
            raise OSError(f"UpdateProcThreadAttribute failed ({ctypes.get_last_error()})")

        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = _kernel32.GetStdHandle(-10)
        startup.StartupInfo.hStdOutput = write_end
        startup.StartupInfo.hStdError = write_end
        startup.lpAttributeList = attribute_list

        env = build_env({**dict(spec.env or {}), **dict(spec.secret_env or {})})
        # AppContainer process creation resolves its local app-data path and
        # fails with ERROR_ENVVAR_NOT_FOUND (203) if LOCALAPPDATA is absent, even
        # though the block is otherwise valid. These are paths, not secrets; the
        # rest of the secret-scrubbing policy is unchanged.
        for key in ("APPDATA", "LOCALAPPDATA"):
            value = os.environ.get(key)
            if value and key not in env:
                env[key] = value
        block = "\0".join(f"{key}={value}" for key, value in env.items()) + "\0\0"
        env_buffer = ctypes.create_unicode_buffer(block)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(spec.argv)))
        process_info = _PROCESS_INFORMATION()
        flags = (
            _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW
            | _CREATE_UNICODE_ENVIRONMENT
        )
        _kernel32.CreateProcessW.restype = wintypes.BOOL
        _kernel32.CreateProcessW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOEXW), ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        created = _kernel32.CreateProcessW(
            None, command, None, None, True, flags,
            env_buffer, cwd,
            ctypes.byref(startup), ctypes.byref(process_info),
        )
        _kernel32.DeleteProcThreadAttributeList(attribute_list)
        _kernel32.CloseHandle(write_end)
        if not created:
            _kernel32.CloseHandle(read_end)
            raise OSError(f"CreateProcessW failed ({ctypes.get_last_error()})")

        chunks: list[bytes] = []

        def _drain() -> None:
            buf = ctypes.create_string_buffer(_READ_CHUNK)
            read = wintypes.DWORD(0)
            while _kernel32.ReadFile(read_end, buf, _READ_CHUNK, ctypes.byref(read), None):
                if read.value == 0:
                    break
                chunks.append(buf.raw[: read.value])

        reader = threading.Thread(target=_drain, daemon=True)
        reader.start()
        timeout_ms = max(1, int(spec.timeout_s or _DEFAULT_TIMEOUT_S)) * 1000
        wait = _kernel32.WaitForSingleObject(process_info.hProcess, timeout_ms)
        timed_out = wait == _WAIT_TIMEOUT
        if timed_out:
            _kernel32.TerminateProcess(process_info.hProcess, 1)
            _kernel32.WaitForSingleObject(process_info.hProcess, 5_000)
        code = wintypes.DWORD(0)
        _kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(code))
        reader.join(timeout=5)
        _kernel32.CloseHandle(read_end)
        _kernel32.CloseHandle(process_info.hThread)
        _kernel32.CloseHandle(process_info.hProcess)
        output = b"".join(chunks).decode("utf-8", errors="replace")
        return (None if timed_out else int(code.value)), output, "", timed_out


__all__ = [
    "ENABLE_ENV",
    "PROFILE_NAME",
    "WindowsAppContainerSandbox",
    "enabled",
    "exports_available",
]
