"""The Windows desktop driver.

Implemented with `ctypes` against the native Win32 APIs — no third-party package
is required, so zero-config keeps working. It provides:

  * display enumeration (multi-monitor, DPI-aware),
  * window + application enumeration (titles, pids, bounds, z-order),
  * screen capture via GDI BitBlt (PIL encodes the PNG when available),
  * input delivery in two modes: `foreground` via SendInput (moves the real
    cursor / raises focus) and `background` via PostMessage to the target window
    (does NOT disturb the user) — with the honest caveat that some modern
    toolkits ignore posted input, which the verifier detects.

Accessibility (UIA/MSAA) lives in `computer/accessibility/windows.py` and is
optional; this driver reports `accessibility` capability from that provider.

It never fabricates: a call it cannot service raises `UnsupportedAction`.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
from ctypes import wintypes
from typing import Any, Optional

from ..actions.keymap import normalize_combo, virtual_key
from ..errors import UnsupportedAction
from ..models import (
    ApplicationInfo,
    Bounds,
    Capabilities,
    DisplayInfo,
    DriverContract,
    WindowInfo,
)
from .base import ComputerDriver, InputResult, ScreenFrame

_IS_WINDOWS = sys.platform == "win32"

# ── Win32 bindings ───────────────────────────────────────────────────────────

if _IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # pragma: no cover - imported for typing/tests on non-Windows
    user32 = gdi32 = kernel32 = None  # type: ignore[assignment]

    class _Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_HWHEEL = 0x1000
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_CHAR, WM_KEYDOWN, WM_KEYUP = 0x0102, 0x0100, 0x0101
WM_SETTEXT = 0x000C
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE, SW_SHOW = 6, 3, 9, 5
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080


def _rect_to_bounds(rect: RECT) -> Bounds:
    return Bounds.from_ltrb(rect.left, rect.top, rect.right, rect.bottom)


def _primary_modifier() -> str:
    return "meta" if sys.platform == "darwin" else "ctrl"


class WindowsDriver(ComputerDriver):
    id = "windows"
    platform = "windows"
    label = "Windows (Win32 / UI Automation)"

    def __init__(self) -> None:
        self._dpi_aware = False
        self._ax: Any = None
        self._started = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not _IS_WINDOWS:
            return
        self._make_dpi_aware()
        from ..accessibility.windows import build_ax_provider  # noqa: PLC0415

        self._ax = build_ax_provider()
        self._started = True

    async def stop(self) -> None:
        self._started = False

    def _make_dpi_aware(self) -> None:
        if self._dpi_aware or not _IS_WINDOWS:
            return
        try:
            # Per-monitor-v2 awareness (Win10 1703+); fall back to system-aware.
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:  # noqa: BLE001
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001 - DPI awareness is best-effort
            pass
        self._dpi_aware = True

    def contract(self) -> DriverContract:
        return DriverContract(
            platform="windows", name=self.id,
            capabilities=("displays", "windows", "applications", "screen_capture",
                          "foreground_input", "background_input", "window_management",
                          "application_management", "set_value"),
        )

    def capabilities(self) -> Capabilities:
        ax_ok = bool(getattr(self._ax, "available", False))
        notes: list[str] = []
        if not ax_ok:
            notes.append("accessibility tree is limited (UI Automation client not installed); OCR/vision fallback in use")
        return Capabilities(
            platform="windows",
            background_input=True,
            foreground_input=True,
            accessibility=ax_ok,
            screen_capture=True,
            multi_monitor=True,
            window_management=True,
            application_management=True,
            set_value=True,
            headless_desktop=False,
            notes=notes,
        )

    def health(self) -> dict[str, Any]:
        return {
            "driver": self.id, "healthy": bool(_IS_WINDOWS), "platform": "windows",
            "dpiAware": self._dpi_aware, "accessibility": bool(getattr(self._ax, "available", False)),
        }

    def set_ax_provider(self, provider: Any) -> None:
        self._ax = provider

    # ── displays ─────────────────────────────────────────────────────────────

    def list_displays(self) -> list[DisplayInfo]:
        if not _IS_WINDOWS:
            return super().list_displays()
        displays: list[DisplayInfo] = []

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM,
        )

        def _cb(monitor: Any, _hdc: Any, _rect: Any, _data: Any) -> int:
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                primary = bool(info.dwFlags & 1)
                bounds = _rect_to_bounds(info.rcMonitor)
                work = _rect_to_bounds(info.rcWork)
                displays.append(DisplayInfo(
                    id=f"display{len(displays)}", bounds=bounds, working_area=work,
                    primary=primary, name="primary" if primary else f"monitor{len(displays)}",
                ))
            return 1

        try:
            user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        except Exception:  # noqa: BLE001
            pass
        if not displays:
            displays.append(DisplayInfo(id="display0", bounds=Bounds(), working_area=Bounds(), primary=True))
        # Sort primary first for deterministic ids.
        displays.sort(key=lambda d: (not d.primary, d.bounds.x))
        for i, d in enumerate(displays):
            d.id = "primary" if d.primary else f"display{i}"
        return displays

    def display_of_point(self, x: int, y: int) -> Optional[DisplayInfo]:
        displays = self.list_displays()
        for display in displays:
            if display.bounds.contains(x, y):
                return display
        return displays[0] if displays else None

    # ── windows ──────────────────────────────────────────────────────────────

    def list_windows(self) -> list[WindowInfo]:
        if not _IS_WINDOWS:
            return []
        foreground = user32.GetForegroundWindow()
        windows: list[WindowInfo] = []

        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd: Any, _lparam: Any) -> int:
            try:
                if not user32.IsWindowVisible(hwnd):
                    return 1
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if ex & WS_EX_TOOLWINDOW:
                    return 1
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return 1
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                rect = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                windows.append(WindowInfo(
                    id=str(int(hwnd)), title=buf.value, pid=pid.value,
                    bounds=_rect_to_bounds(rect),
                    minimized=bool(user32.IsIconic(hwnd)),
                    maximized=bool(user32.IsZoomed(hwnd)),
                    visible=True, focused=(hwnd == foreground),
                ))
            except Exception:  # noqa: BLE001 - skip a window that misbehaves
                pass
            return 1

        try:
            user32.EnumWindows(EnumProc(_cb), 0)
        except Exception:  # noqa: BLE001
            pass
        # Z-order: EnumWindows yields top-to-bottom, so the list order IS z-order.
        apps = {a.pid: a.name for a in self._applications_by_pid()}
        for i, window in enumerate(windows):
            window.z_order = i
            window.app = apps.get(window.pid, "")
            display = self.display_of_point(*window.bounds.center)
            window.display_id = display.id if display else ""
        return windows

    def get_window(self, window_id: str) -> Optional[WindowInfo]:
        for window in self.list_windows():
            if window.id == str(window_id):
                return window
        return None

    async def focus_window(self, window_id: str, *, foreground: bool = False) -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Focusing windows requires Windows.")
        hwnd = int(window_id)
        if not user32.IsWindow(hwnd):
            from ..errors import WindowNotFound  # noqa: PLC0415

            raise WindowNotFound(f"Window {window_id} is gone.", window=window_id)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if foreground:
            try:
                user32.SetForegroundWindow(hwnd)
            except Exception:  # noqa: BLE001
                pass
        return InputResult(delivered=True, delivery_mode="foreground" if foreground else "background")

    async def window_control(self, window_id: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Window control requires Windows.")
        hwnd = int(window_id)
        if not user32.IsWindow(hwnd):
            from ..errors import WindowNotFound  # noqa: PLC0415

            raise WindowNotFound(f"Window {window_id} is gone.", window=window_id)
        if operation == "minimize":
            user32.ShowWindow(hwnd, SW_MINIMIZE)
        elif operation == "maximize":
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
        elif operation == "restore":
            user32.ShowWindow(hwnd, SW_RESTORE)
        elif operation == "show":
            user32.ShowWindow(hwnd, SW_SHOW)
        elif operation == "move":
            x = int(kwargs.get("x", 0)); y = int(kwargs.get("y", 0))
            w = int(kwargs.get("width", 0)); h = int(kwargs.get("height", 0))
            if not w or not h:
                current = self.get_window(window_id)
                w = w or (current.bounds.width if current else 800)
                h = h or (current.bounds.height if current else 600)
            user32.MoveWindow(hwnd, x, y, w, h, True)
        elif operation == "close":
            WM_CLOSE = 0x0010
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        else:
            raise UnsupportedAction(f"Unknown window operation {operation!r}.")
        return {"windowId": window_id, "operation": operation, "done": True}

    # ── applications ─────────────────────────────────────────────────────────

    def _applications_by_pid(self) -> list[ApplicationInfo]:
        """Best-effort application list from the windows' owning processes."""
        if not _IS_WINDOWS:
            return []
        seen: dict[int, ApplicationInfo] = {}
        try:
            for window in self._iter_windows_basic():
                pid = window["pid"]
                if pid in seen:
                    seen[pid].window_ids.append(window["id"])
                    continue
                name, exe = self._process_name(pid)
                seen[pid] = ApplicationInfo(
                    id=str(pid), name=name, pid=pid, executable=exe,
                    running=True, window_ids=[window["id"]],
                )
        except Exception:  # noqa: BLE001
            pass
        return sorted(seen.values(), key=lambda a: a.name.lower())

    def _iter_windows_basic(self) -> list[dict[str, Any]]:
        foreground = user32.GetForegroundWindow()
        out: list[dict[str, Any]] = []

        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd: Any, _lparam: Any) -> int:
            try:
                if not user32.IsWindowVisible(hwnd):
                    return 1
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if ex & WS_EX_TOOLWINDOW:
                    return 1
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return 1
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append({"id": str(int(hwnd)), "pid": pid.value, "focused": hwnd == foreground})
            except Exception:  # noqa: BLE001
                pass
            return 1

        user32.EnumWindows(EnumProc(_cb), 0)
        return out

    def _process_name(self, pid: int) -> tuple[str, str]:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return (f"pid {pid}", "")
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe = buf.value
                name = os.path.basename(exe)
                return (name[:-4] if name.lower().endswith(".exe") else name, exe)
        finally:
            kernel32.CloseHandle(handle)
        return (f"pid {pid}", "")

    def list_applications(self) -> list[ApplicationInfo]:
        return self._applications_by_pid()

    async def launch_application(self, target: str, *, args: list[str] | None = None) -> ApplicationInfo:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Launching applications requires Windows.")
        import subprocess  # noqa: PLC0415

        argv = [target, *(args or [])]
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as exc:  # noqa: BLE001
            from ..errors import ApplicationNotFound  # noqa: PLC0415

            raise ApplicationNotFound(f"Eclipse couldn't start {target!r}.", metadata={"error": str(exc)[:200]}) from exc
        await asyncio.sleep(0.6)
        return ApplicationInfo(
            id=str(proc.pid), name=os.path.basename(target), pid=proc.pid,
            executable=target, running=True,
        )

    async def close_application(self, app_id: str) -> dict[str, Any]:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Closing applications requires Windows.")
        try:
            pid = int(app_id)
        except ValueError as exc:
            raise UnsupportedAction(f"{app_id!r} is not an application id.") from exc
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            return {"applicationId": app_id, "closed": False, "reason": "process is not accessible"}
        try:
            ok = kernel32.TerminateProcess(handle, 0)
        finally:
            kernel32.CloseHandle(handle)
        return {"applicationId": app_id, "closed": bool(ok)}

    # ── capture ──────────────────────────────────────────────────────────────

    async def capture(
        self,
        *,
        window_id: Optional[str] = None,
        region: Optional[Bounds] = None,
        display_id: Optional[str] = None,
    ) -> ScreenFrame:
        if not _IS_WINDOWS:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable("Screen capture requires Windows.")
        bounds = region
        if bounds is None and window_id:
            window = self.get_window(window_id)
            if window is None:
                from ..errors import WindowNotFound  # noqa: PLC0415

                raise WindowNotFound(f"Window {window_id} is gone.", window=window_id)
            bounds = window.bounds
        if bounds is None and display_id:
            for display in self.list_displays():
                if display.id == display_id:
                    bounds = display.bounds
                    break
        if bounds is None:
            display = next((d for d in self.list_displays() if d.primary), None)
            bounds = display.bounds if display else Bounds(0, 0, 1920, 1080)
        if bounds.width <= 0 or bounds.height <= 0:
            raise UnsupportedAction("Cannot capture a zero-sized region.")

        img = self._grab(bounds)
        png = None
        try:
            if img is not None:
                import io  # noqa: PLC0415

                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                png = buffer.getvalue()
        except Exception:  # noqa: BLE001
            png = None
        return ScreenFrame(
            data=img, width=bounds.width, height=bounds.height, bounds=bounds, png_bytes=png,
            scale=(self.display_of_point(*bounds.center).scale if self.display_of_point(*bounds.center) else 1.0),
        )

    def _grab(self, bounds: Bounds) -> Any:
        """Grab a region as a PIL image (ImageGrab), else a GDI bitmap."""
        try:
            from PIL import ImageGrab  # noqa: PLC0415

            return ImageGrab.grab(
                bbox=(bounds.x, bounds.y, bounds.right, bounds.bottom),
                all_screens=True,
            ).convert("RGB")
        except Exception:  # noqa: BLE001
            return self._grab_gdi(bounds)

    def _grab_gdi(self, bounds: Bounds) -> Any:
        hdc_screen = user32.GetDC(0)
        if not hdc_screen:
            return None
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, bounds.width, bounds.height)
        gdi32.SelectObject(hdc_mem, hbitmap)
        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, bounds.width, bounds.height, hdc_screen, bounds.x, bounds.y, SRCCOPY)

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = bounds.width
        header.biHeight = -bounds.height  # top-down
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        buffer_len = bounds.width * bounds.height * 4
        buffer = ctypes.create_string_buffer(buffer_len)
        gdi32.GetDIBits(hdc_mem, hbitmap, 0, bounds.height, buffer, ctypes.byref(header), 0)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        try:
            from PIL import Image  # noqa: PLC0415

            return Image.frombuffer("RGBA", (bounds.width, bounds.height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
        except Exception:  # noqa: BLE001
            return None

    def accessibility_tree(self, window_id: Optional[str] = None) -> Any:
        if self._ax is None or not getattr(self._ax, "available", False):
            return None
        try:
            return self._ax.tree(window_id)
        except Exception:  # noqa: BLE001 - an AX failure is a fallback, not a crash
            return None

    # ── input: foreground (SendInput) ────────────────────────────────────────

    def _send_inputs(self, inputs: list[INPUT]) -> None:
        n = len(inputs)
        array = (INPUT * n)(*inputs)
        user32.SendInput(n, array, ctypes.sizeof(INPUT))

    def _abs_coords(self, x: int, y: int) -> tuple[int, int]:
        vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78) or 1  # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79) or 1  # SM_CYVIRTUALSCREEN
        nx = int((x - vx) * 65535 / vw)
        ny = int((y - vy) * 65535 / vh)
        return nx, ny

    def _fg_mouse(self, x: int, y: int, flags: int, data: int = 0) -> None:
        nx, ny = self._abs_coords(x, y)
        inputs = []
        if flags & MOUSEEVENTF_MOVE:
            inputs.append(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(
                nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None))))
        if flags & (MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_MIDDLEDOWN):
            inputs.append(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(
                nx, ny, 0, flags | MOUSEEVENTF_ABSOLUTE, 0, None))))
        if flags & (MOUSEEVENTF_LEFTUP | MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_MIDDLEUP):
            inputs.append(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(
                nx, ny, 0, flags | MOUSEEVENTF_ABSOLUTE, 0, None))))
        if flags & MOUSEEVENTF_WHEEL:
            inputs.append(INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(
                0, 0, data & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None))))
        self._send_inputs(inputs)

    def _fg_click(self, x: int, y: int, button: str, count: int) -> None:
        down = {"left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN, "middle": MOUSEEVENTF_MIDDLEDOWN}[button]
        up = {"left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP, "middle": MOUSEEVENTF_MIDDLEUP}[button]
        self._fg_mouse(x, y, MOUSEEVENTF_MOVE)
        for _ in range(max(1, count)):
            self._send_inputs([
                INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(*self._abs_coords(x, y), 0, down | MOUSEEVENTF_ABSOLUTE, 0, None))),
                INPUT(type=INPUT_MOUSE, union=_INPUTunion(mi=MOUSEINPUT(*self._abs_coords(x, y), 0, up | MOUSEEVENTF_ABSOLUTE, 0, None))),
            ])

    def _fg_key(self, keys: list[str]) -> None:
        inputs: list[INPUT] = []
        vks: list[tuple[int, bool]] = []
        for name in keys:
            vk = virtual_key(name)
            if vk is None:
                continue
            if name.lower() in ("shift", "ctrl", "control", "alt", "meta", "win"):
                vks.append((vk, False))
            else:
                vks.append((vk, True))
        for vk, _is_target in vks:
            inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(vk, 0, 0, 0, None))))
        for vk, _is_target in reversed(vks):
            inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None))))
        self._send_inputs(inputs)

    def _fg_type(self, text: str) -> None:
        inputs: list[INPUT] = []
        for ch in text:
            code = ord(ch)
            inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None))))
            inputs.append(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))))
        self._send_inputs(inputs)

    # ── input: background (PostMessage) ──────────────────────────────────────

    def _client_point(self, hwnd: int, x: int, y: int) -> tuple[int, int]:
        pt = POINT(x, y)
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    def _lparam(self, x: int, y: int) -> int:
        return ((y & 0xFFFF) << 16) | (x & 0xFFFF)

    def _deepest_child_at(self, top: int, x: int, y: int) -> int:
        """The deepest descendant of `top` whose rectangle contains the screen
        point (x, y). Z-ORDER INDEPENDENT: it walks the target window's OWN child
        hierarchy with `RealChildWindowFromPoint`, so a covering window never
        changes which control we address. This is the correct primitive for a
        background click — a message posted to the top-level window alone never
        activates a child control.
        """
        hwnd = top
        for _ in range(8):
            pt = POINT(x, y)
            if not user32.ScreenToClient(hwnd, ctypes.byref(pt)):
                break
            child = user32.RealChildWindowFromPoint(hwnd, pt)
            child = int(child) if child else 0
            if not child or child == hwnd:
                break
            hwnd = child
        return hwnd

    def _focused_control(self, hwnd: int) -> int:
        """The control that owns keyboard focus within `hwnd`'s thread, even when
        the window is NOT foreground (GetGUIThreadInfo). This lets background
        typing target the right control without activating the window."""
        if not hasattr(self, "_GUITHREADINFO"):
            class GUITHREADINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                    ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                    ("rcCaret", RECT),
                ]

            self._GUITHREADINFO = GUITHREADINFO  # type: ignore[attr-defined]
        gti = self._GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(gti)
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        if not tid or not user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
            return 0
        return int(gti.hwndFocus or 0)

    def _bg_click(self, top: int, x: int, y: int, button: str, count: int) -> bool:
        target = self._deepest_child_at(top, x, y)
        cx, cy = self._client_point(target, x, y)
        lp = self._lparam(cx, cy)
        down, up = {
            "left": (WM_LBUTTONDOWN, WM_LBUTTONUP),
            "right": (WM_RBUTTONDOWN, WM_RBUTTONUP),
            "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP),
        }[button]
        ok = True
        for _ in range(max(1, count)):
            user32.PostMessageW(target, WM_MOUSEMOVE, 0, lp)
            ok = ok and bool(user32.PostMessageW(target, down, 1, lp))
            ok = ok and bool(user32.PostMessageW(target, up, 0, lp))
        return ok

    def _bg_type(self, hwnd: int, text: str) -> bool:
        # Target the focused control of the window's thread when there is one,
        # else the window itself (some apps route WM_CHAR themselves).
        target = self._focused_control(hwnd) or hwnd
        ok = True
        for ch in text:
            ok = ok and bool(user32.PostMessageW(target, WM_CHAR, ord(ch), 0))
        return ok

    def _bg_key(self, hwnd: int, keys: list[str]) -> bool:
        target = self._focused_control(hwnd) or hwnd
        vks = [(virtual_key(k), k.lower() in ("shift", "ctrl", "control", "alt", "meta", "win")) for k in keys]
        vks = [(vk, t) for vk, t in vks if vk is not None]
        ok = True
        for vk, _t in vks:
            ok = ok and bool(user32.PostMessageW(target, WM_KEYDOWN, vk, 0))
        for vk, _t in reversed(vks):
            ok = ok and bool(user32.PostMessageW(target, WM_KEYUP, vk, 0))
        return ok

    def _target_hwnd(self, window_id: Optional[str]) -> Optional[int]:
        if window_id:
            try:
                return int(window_id)
            except ValueError:
                return None
        hwnd = user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None

    def is_point_on_window(self, window_id: str, x: int, y: int) -> Optional[bool]:
        """Whether the TOP-LEVEL window (or one of its controls) is the window
        physically at (x, y). A background click does not need this (PostMessage
        is z-order independent), but a FOREGROUND SendInput at absolute
        coordinates MUST be refused when another window covers the target — else
        the click lands on the wrong application.
        """
        if not _IS_WINDOWS:
            return None
        try:
            target = int(window_id)
        except (TypeError, ValueError):
            return None
        under = user32.WindowFromPoint(POINT(int(x), int(y)))
        if not under:
            return False
        GA_ROOT = 2
        root_under = int(user32.GetAncestor(under, GA_ROOT) or under)
        root_target = int(user32.GetAncestor(target, GA_ROOT) or target)
        return root_under == root_target

    # ── input: the driver methods ────────────────────────────────────────────

    async def click(
        self, x: int, y: int, *, button: str = "left", count: int = 1,
        delivery_mode: str = "background", window_id: Optional[str] = None,
    ) -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Clicking requires Windows.")
        if delivery_mode == "background":
            hwnd = self._target_hwnd(window_id)
            if hwnd:
                ok = self._bg_click(hwnd, x, y, button, count)
                return InputResult(delivered=ok, delivery_mode="background", detail=f"posted to window {hwnd}")
        # A foreground absolute-coordinate click must be refused when another
        # window covers the target — otherwise it lands on the wrong application.
        if window_id is not None:
            on_target = self.is_point_on_window(window_id, x, y)
            if on_target is False:
                from ..errors import TargetObscured  # noqa: PLC0415

                raise TargetObscured(
                    "The target is covered by another window; Eclipse won't click blind.",
                    window=window_id,
                )
        self._make_dpi_aware()
        self._fg_click(x, y, button, count)
        return InputResult(delivered=True, delivery_mode="foreground", detail="SendInput absolute")

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background") -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Mouse press requires Windows.")
        flags = {"left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN, "middle": MOUSEEVENTF_MIDDLEDOWN}[button]
        self._fg_mouse(x, y, MOUSEEVENTF_MOVE)
        self._fg_mouse(x, y, flags)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background") -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Mouse release requires Windows.")
        flags = {"left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP, "middle": MOUSEEVENTF_MIDDLEUP}[button]
        self._fg_mouse(x, y, flags)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def move(self, x: int, y: int, *, delivery_mode: str = "background") -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Pointer movement requires Windows.")
        self._fg_mouse(x, y, MOUSEEVENTF_MOVE)
        return InputResult(delivered=True, delivery_mode="foreground", detail="moved the real cursor")

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None, delivery_mode: str = "background") -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Scrolling requires Windows.")
        if at:
            self._fg_mouse(at[0], at[1], MOUSEEVENTF_MOVE)
        if dy:
            self._fg_mouse(0, 0, MOUSEEVENTF_WHEEL, data=-dy * 120 if dy else 0)
        if dx:
            self._fg_mouse(0, 0, MOUSEEVENTF_HWHEEL, data=-dx * 120 if dx else 0)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left", delivery_mode: str = "background") -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Dragging requires Windows.")
        down = {"left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN, "middle": MOUSEEVENTF_MIDDLEDOWN}[button]
        up = {"left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP, "middle": MOUSEEVENTF_MIDDLEUP}[button]
        self._fg_mouse(x1, y1, MOUSEEVENTF_MOVE)
        self._fg_mouse(x1, y1, down)
        steps = 12
        for i in range(1, steps + 1):
            self._fg_mouse(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps, MOUSEEVENTF_MOVE)
        self._fg_mouse(x2, y2, up)
        return InputResult(delivered=True, delivery_mode="foreground")

    def _require_foreground_owner(self, window_id: Optional[str]) -> None:
        """A foreground keystroke goes to the FOREGROUND window. If the caller
        named a different target window, refuse rather than type into the wrong
        application (the classic focus-steal bug)."""
        if window_id is None or not _IS_WINDOWS:
            return
        try:
            target = int(window_id)
        except (TypeError, ValueError):
            return
        fg = int(user32.GetForegroundWindow() or 0)
        GA_ROOT = 2
        if int(user32.GetAncestor(fg, GA_ROOT) or fg) != int(user32.GetAncestor(target, GA_ROOT) or target):
            from ..errors import TargetObscured  # noqa: PLC0415

            raise TargetObscured(
                "Eclipse won't send foreground keystrokes to a window that isn't focused.",
                window=window_id,
            )

    async def type_text(self, text: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Typing requires Windows.")
        if delivery_mode == "background":
            hwnd = self._target_hwnd(window_id)
            if hwnd:
                ok = self._bg_type(hwnd, text)
                return InputResult(delivered=ok, delivery_mode="background", detail=f"posted to window {hwnd}")
        self._require_foreground_owner(window_id)
        self._fg_type(text)
        return InputResult(delivered=True, delivery_mode="foreground", detail="SendInput unicode")

    async def key(self, keys: list[str], *, delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not _IS_WINDOWS:
            raise UnsupportedAction("Sending keys requires Windows.")
        if delivery_mode == "background":
            hwnd = self._target_hwnd(window_id)
            if hwnd:
                ok = self._bg_key(hwnd, keys)
                return InputResult(delivered=ok, delivery_mode="background", detail=f"posted to window {hwnd}")
        self._require_foreground_owner(window_id)
        self._fg_key(keys)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def press_combo(self, combo: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        normalized = normalize_combo(combo)
        keys = normalized.split("+") if normalized else []
        if not keys:
            raise UnsupportedAction(f"Eclipse doesn't recognise the key {combo!r}.")
        return await self.key(keys, delivery_mode=delivery_mode, window_id=window_id)

    async def set_value(self, bounds: Bounds, value: str, *, window_id: Optional[str] = None) -> dict[str, Any]:
        """Best-effort semantic set: send WM_SETTEXT to the control at the point.

        Falls back to an honest failure when the control is not a window that
        accepts text (a canvas, a custom-drawn grid). The core then uses the
        click → select-all → type sequence instead.
        """
        if not _IS_WINDOWS:
            raise UnsupportedAction("set_value requires Windows.")
        x, y = bounds.center
        hwnd = user32.WindowFromPoint(POINT(x, y))
        if not hwnd:
            return {"set": False, "reason": "no control at that point"}
        # SendMessageTimeout (NOT SendMessage): a plain SendMessage BLOCKS the
        # calling thread until the target's message pump returns, so an
        # unresponsive control would hang the whole async loop. A bounded timeout
        # turns that into an honest failure the core can recover from.
        result = ctypes.c_ulonglong(0)
        SMTO_ABORTIFHUNG = 0x0002
        ok = user32.SendMessageTimeoutW(
            hwnd, WM_SETTEXT, 0, ctypes.c_wchar_p(str(value)),
            SMTO_ABORTIFHUNG, 1500, ctypes.byref(result),
        )
        if not ok:
            return {"set": False, "reason": "the control did not respond to set_value within 1.5s"}
        return {"set": True, "method": "wm_settext", "control": str(int(hwnd)), "result": int(result.value)}

    def pointer_position(self) -> Optional[tuple[int, int]]:
        if not _IS_WINDOWS:
            return None
        pt = POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return (pt.x, pt.y)
        return None


__all__ = ["WindowsDriver"]
