"""A controlled native Win32 window used by the Computer Use stress tests.

Run as a script: `python computer_stress_target.py <pidfile> [title]`.

It creates a REAL Win32 window with standard child controls (buttons, an edit
box, a combobox, a checkbox, a static label) so the Win32 accessibility baseline
and the input driver can be exercised against known identities and bounds. It
writes its own pid + hwnd to the pidfile and exits when the window closes.

This is a TEST FIXTURE, never imported by the runtime.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Prototypes for the two calls whose marshalling matters for the caption.
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
ES_LEFT = 0x0000
BS_PUSHBUTTON = 0x00000000
BS_CHECKBOX = 0x00000002
CBS_DROPDOWNLIST = 0x0003
SS_LEFT = 0x00000000
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

# Control ids.
ID_SAVE = 101
ID_SAVEAS = 102
ID_CANCEL = 103
ID_EDIT = 104
ID_COMBO = 105
ID_CHECK = 106
ID_LABEL = 107


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


_LOG = os.environ.get("CUA_TARGET_LOG", "")
_LOG_SEQ = [0]


def _append_log(line: str) -> None:
    if not _LOG:
        return
    _LOG_SEQ[0] += 1
    try:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(f"{_LOG_SEQ[0]} {time.time():.3f} {line}\n")
    except OSError:
        pass


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_COMMAND:
        cid = wparam & 0xFFFF
        if cid in (ID_SAVE, ID_SAVEAS, ID_CANCEL):
            name = {ID_SAVE: "SAVE", ID_SAVEAS: "SAVEAS", ID_CANCEL: "CANCEL"}[cid]
            _append_log(name)
            title = {ID_SAVE: "[SAVED]", ID_SAVEAS: "[SAVED AS]", ID_CANCEL: "[CANCELLED]"}[cid]
            user32.SetWindowTextW(hwnd, title)
            # Also change a CHILD static's text, which the Win32 accessibility
            # baseline CAN read cross-process — so verification has a real,
            # AX-visible semantic signal for the click.
            status = user32.FindWindowExW(hwnd, None, "Static", None)
            if status:
                user32.SetWindowTextW(status, f"STATUS={name}")
    elif msg == WM_CLOSE:
        _append_log("CLOSE")
        user32.DestroyWindow(hwnd)
        return 0
    elif msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def main() -> int:
    pidfile = sys.argv[1] if len(sys.argv) > 1 else "target.pid"
    title = sys.argv[2] if len(sys.argv) > 2 else "CUA Stress Target"
    hinstance = kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(_wndproc)
    wc.hInstance = hinstance
    wc.lpszClassName = "CuaStressTarget"
    wc.hbrBackground = gdi32.GetStockObject(5)  # CTLCOLOR_BTN-ish grey
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0, "CuaStressTarget", title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        120, 120, 640, 420, None, None, hinstance, None,
    )
    # Child controls with fixed geometry.
    def _mk(cls, text, style, x, y, w, h, cid):
        return user32.CreateWindowExW(
            0, cls, text, WS_CHILD | WS_VISIBLE | style, x, y, w, h,
            hwnd, ctypes.c_void_p(cid), hinstance, None,
        )

    _mk("Button", "Save", BS_PUSHBUTTON | WS_TABSTOP, 20, 20, 110, 32, ID_SAVE)
    _mk("Button", "Save As", BS_PUSHBUTTON | WS_TABSTOP, 140, 20, 110, 32, ID_SAVEAS)
    _mk("Button", "Cancel", BS_PUSHBUTTON | WS_TABSTOP, 260, 20, 110, 32, ID_CANCEL)
    _mk("Static", "Ticker:", SS_LEFT, 20, 70, 80, 24, ID_LABEL)
    _mk("Edit", "", WS_BORDER | ES_LEFT | WS_TABSTOP, 100, 68, 160, 26, ID_EDIT)
    _mk("ComboBox", "", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, 280, 68, 160, 200, ID_COMBO)
    _mk("Button", "Enable trading", BS_CHECKBOX | WS_TABSTOP, 20, 110, 200, 28, ID_CHECK)
    _mk("Static", "NVDA  Bid 185.21  Ask 185.24", SS_LEFT, 20, 150, 400, 24, ID_LABEL + 10)

    combo = user32.FindWindowExW(hwnd, None, "ComboBox", None)
    if combo:
        for item in ("Market", "Limit", "Stop"):
            user32.SendMessageW(combo, 0x0143, 0, ctypes.c_wchar_p(item))  # CB_ADDSTRING

    # Write our pid + hwnd, then pump messages.
    with open(pidfile, "w", encoding="utf-8") as handle:
        handle.write(f"{kernel32.GetCurrentProcessId()} {int(hwnd)}")

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
