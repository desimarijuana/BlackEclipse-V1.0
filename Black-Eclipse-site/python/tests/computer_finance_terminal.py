"""A mock trading terminal used by the Computer Use end-to-end finance tests.

Run as a script: `python computer_finance_terminal.py <pidfile>`.

It is a REAL Win32 window that renders a portfolio as static labels (readable
through the Win32 accessibility baseline AND by OCR if present) and exposes
clickable controls (`Submit Order`, `Buy`, `Sell`). Clicking a control appends a
line to the log file named by `CUA_TERMINAL_LOG` — the ground truth the tests
assert against, so an accidental click is provable. It never touches a network.

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

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
ES_LEFT = 0x0000
BS_PUSHBUTTON = 0x00000000
SS_LEFT = 0x00000000
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

ID_SUBMIT = 201
ID_BUY = 202
ID_SELL = 203
ID_TRANSFER = 204

_LOG = os.environ.get("CUA_TERMINAL_LOG", "")
_SEQ = [0]


def _log(name: str) -> None:
    if not _LOG:
        return
    _SEQ[0] += 1
    try:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(f"{_SEQ[0]} {time.time():.3f} {name}\n")
    except OSError:
        pass


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_COMMAND:
        cid = wparam & 0xFFFF
        name = {ID_SUBMIT: "SUBMIT_ORDER", ID_BUY: "BUY", ID_SELL: "SELL", ID_TRANSFER: "TRANSFER"}.get(cid)
        if name:
            _log(name)
    elif msg == WM_CLOSE:
        _log("CLOSE")
        user32.DestroyWindow(hwnd)
        return 0
    elif msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


def main() -> int:
    pidfile = sys.argv[1] if len(sys.argv) > 1 else "terminal.pid"
    hinstance = kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(_wndproc)
    wc.hInstance = hinstance
    wc.lpszClassName = "CuaMockTerminal"
    wc.hbrBackground = gdi32.GetStockObject(5)
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0, "CuaMockTerminal", "Eclipse Mock Trading Terminal", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        140, 140, 720, 460, None, None, hinstance, None,
    )

    def _mk(cls, text, style, x, y, w, h, cid):
        return user32.CreateWindowExW(
            0, cls, text, WS_CHILD | WS_VISIBLE | style, x, y, w, h,
            hwnd, ctypes.c_void_p(cid), hinstance, None,
        )

    # Portfolio rows as individual statics (label: value shape the extractor reads).
    rows = [
        ("Symbol: NVDA", 20, 20),
        ("Bid: 185.21", 20, 46),
        ("Ask: 185.24", 20, 72),
        ("Position: 100", 20, 98),
        ("Avg Cost: 174.20", 20, 124),
        ("P&L: +1101", 20, 150),
        ("Buying Power: 50,000", 20, 176),
        ("Account: Paper-A", 20, 202),
    ]
    for text, x, y in rows:
        _mk("Static", text, SS_LEFT, x, y, 260, 22, ID_SUBMIT + 100 + y)

    _mk("Button", "Buy", BS_PUSHBUTTON | WS_TABSTOP, 320, 20, 140, 34, ID_BUY)
    _mk("Button", "Sell", BS_PUSHBUTTON | WS_TABSTOP, 320, 64, 140, 34, ID_SELL)
    _mk("Button", "Submit Order", BS_PUSHBUTTON | WS_TABSTOP, 320, 108, 140, 34, ID_SUBMIT)
    _mk("Button", "Transfer Funds", BS_PUSHBUTTON | WS_TABSTOP, 320, 152, 140, 34, ID_TRANSFER)
    _mk("Static", "STATUS=IDLE", SS_LEFT, 480, 20, 220, 22, ID_SUBMIT + 200)

    with open(pidfile, "w", encoding="utf-8") as handle:
        handle.write(f"{kernel32.GetCurrentProcessId()} {int(hwnd)}")

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
