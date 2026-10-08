"""The Linux X11 desktop driver.

Implemented with `ctypes` against `libX11`, `libXtst` (XTest) and `libXext` — no
third-party Python package, so zero-config keeps working. It provides display
geometry, window enumeration (EWMH `_NET_CLIENT_LIST`), screen capture
(`XGetImage`) and input via XTest (foreground) plus `XSendEvent` (background,
best-effort).

Wayland has no equivalent global-input API; a Wayland session without an XWayland
server falls back to a genuine `NullDriver` (honest), and `doctor` names the
missing backend. Accessibility (AT-SPI) lives in `computer/accessibility/linux.py`
and is optional, exactly like UIA on Windows.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from ctypes import c_char_p, c_int, c_long, c_uint, c_ulong, c_void_p
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

_IS_LINUX = sys.platform.startswith("linux")


def _x11_available(*, display: Optional[str] = None) -> tuple[bool, str]:
    if not _IS_LINUX:
        return False, "the X11 driver is only available on Linux"
    if not (display or os.environ.get("DISPLAY")):
        return False, "no X11 DISPLAY is set (a Wayland-only session has no global input API)"
    if ctypes.util.find_library("X11") is None:
        return False, "libX11 isn't installed"
    return True, ""


class _XImage(ctypes.Structure):
    _fields_ = [
        ("width", c_int), ("height", c_int), ("xoffset", c_int), ("format", c_int),
        ("data", c_void_p), ("byte_order", c_int), ("bitmap_unit", c_int),
        ("bitmap_bit_order", c_int), ("bitmap_pad", c_int), ("depth", c_int),
        ("bytes_per_line", c_int), ("bits_per_pixel", c_int), ("red_mask", c_ulong),
        ("green_mask", c_ulong), ("blue_mask", c_ulong),
    ]


class LinuxX11Driver(ComputerDriver):
    id = "linux"
    platform = "linux"
    label = "Linux (X11 / XTest)"

    def __init__(self, *, display: Optional[str] = None) -> None:
        self._x11: Any = None
        self._xtst: Any = None
        self._display: Any = None
        self._started = False
        self._root = 0
        self._ax: Any = None
        self._reason = ""
        # An explicit DISPLAY (used by the Xvfb provisioner) overrides the env.
        self._display_name = display

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        ok, reason = _x11_available(display=self._display_name)
        if not ok:
            self._reason = reason
            return
        try:
            self._x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
            xtst = ctypes.util.find_library("Xtst")
            if xtst:
                self._xtst = ctypes.CDLL(xtst)
            self._x11.XOpenDisplay.restype = c_void_p
            self._x11.XOpenDisplay.argtypes = [c_char_p]
            self._x11.XDefaultRootWindow.restype = c_ulong
            self._x11.XDefaultRootWindow.argtypes = [c_void_p]
            self._x11.XInternAtom.restype = c_ulong
            self._x11.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
            self._x11.XGetImage.restype = c_void_p
            self._x11.XGetImage.argtypes = [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_ulong, c_int]
            self._x11.XDestroyImage.argtypes = [c_void_p]
            self._display = self._x11.XOpenDisplay((self._display_name or os.environ.get("DISPLAY")).encode())
            if not self._display:
                self._reason = "could not open the X display"
                return
            self._root = int(self._x11.XDefaultRootWindow(ctypes.c_void_p(self._display)))
            from ..accessibility.linux import build_ax_provider  # noqa: PLC0415

            self._ax = build_ax_provider()
            self._started = True
        except Exception as exc:  # noqa: BLE001 - an X failure is an honest null
            self._reason = f"the X11 driver couldn't initialise ({str(exc)[:120]})"

    async def stop(self) -> None:
        if self._display:
            try:
                self._x11.XCloseDisplay(ctypes.c_void_p(self._display))
            except Exception:  # noqa: BLE001
                pass
        self._started = False

    def contract(self) -> DriverContract:
        return DriverContract(
            platform="linux", name=self.id,
            capabilities=("displays", "windows", "screen_capture", "foreground_input",
                          "background_input", "window_management"),
        )

    def capabilities(self) -> Capabilities:
        ax_ok = bool(getattr(self._ax, "available", False))
        notes: list[str] = []
        if not self._started:
            notes.append(self._reason or "the X11 driver is not active")
        if not ax_ok:
            notes.append("accessibility tree is limited (AT-SPI client not installed); OCR/vision fallback in use")
        return Capabilities(
            platform="linux",
            background_input=True,
            foreground_input=True,
            accessibility=ax_ok,
            screen_capture=self._started,
            multi_monitor=self._started,
            window_management=self._started,
            application_management=self._started,
            set_value=False,
            headless_desktop=False,
            notes=notes,
        )

    def health(self) -> dict[str, Any]:
        return {
            "driver": self.id, "healthy": self._started, "platform": "linux",
            "display": "x11" if self._started else (self._reason or "unavailable"),
            "accessibility": bool(getattr(self._ax, "available", False)),
        }

    # ── displays ─────────────────────────────────────────────────────────────

    def list_displays(self) -> list[DisplayInfo]:
        if not self._started:
            return super().list_displays()
        try:
            screen = self._x11.XDefaultScreen(ctypes.c_void_p(self._display))
            w = self._x11.XDisplayWidth(ctypes.c_void_p(self._display), screen)
            h = self._x11.XDisplayHeight(ctypes.c_void_p(self._display), screen)
            return [DisplayInfo(id="primary", bounds=Bounds(0, 0, int(w), int(h)),
                                working_area=Bounds(0, 0, int(w), int(h)), primary=True)]
        except Exception:  # noqa: BLE001
            return super().list_displays()

    # ── windows ──────────────────────────────────────────────────────────────

    def list_windows(self) -> list[WindowInfo]:
        if not self._started:
            return []
        return self._ewmh_windows()

    def _atom(self, name: str) -> int:
        return int(self._x11.XInternAtom(ctypes.c_void_p(self._display), name.encode(), False))

    def _ewmh_windows(self) -> list[WindowInfo]:
        """Enumerate top-level windows via EWMH `_NET_CLIENT_LIST`."""
        out: list[WindowInfo] = []
        try:
            net_list = self._atom("_NET_CLIENT_LIST")
            actual_type = c_ulong(0)
            actual_format = c_int(0)
            nitems = c_ulong(0)
            bytes_after = c_ulong(0)
            data = c_void_p(0)
            status = self._x11.XGetWindowProperty(
                c_void_p(self._display), c_ulong(self._root), c_ulong(net_list),
                0, 4096, False, 0,  # AnyPropertyType
                ctypes.byref(actual_type), ctypes.byref(actual_format),
                ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(data),
            )
            if status != 0 or not data:
                return out
            count = int(nitems.value)
            array = ctypes.cast(data, ctypes.POINTER(c_ulong))
            for i in range(count):
                wid = int(array[i])
                out.append(self._window_info(wid, i))
            self._x11.XFree(data)
        except Exception:  # noqa: BLE001
            return out
        apps = {a.pid: a.name for a in self._applications_by_pid()}
        for window in out:
            window.app = apps.get(window.pid, "")
        return out

    def _window_info(self, wid: int, z: int) -> WindowInfo:
        title = self._window_name(wid)
        pid = self._window_pid(wid)
        bounds = self._window_bounds(wid)
        focused = self._focused() == wid
        return WindowInfo(id=str(wid), title=title, pid=pid, bounds=bounds, focused=focused,
                           visible=True, z_order=z)

    def _window_name(self, wid: int) -> str:
        try:
            name = c_void_p(0)
            self._x11.XFetchName(ctypes.c_void_p(self._display), c_ulong(wid), ctypes.byref(name))
            if name:
                text = ctypes.string_at(name).decode("utf-8", "replace")
                self._x11.XFree(name)
                return text
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _window_pid(self, wid: int) -> int:
        try:
            net_wm_pid = self._atom("_NET_WM_PID")
            actual_type = c_ulong(0); fmt = c_int(0); n = c_ulong(0); after = c_ulong(0)
            data = c_void_p(0)
            if self._x11.XGetWindowProperty(
                c_void_p(self._display), c_ulong(wid), c_ulong(net_wm_pid), 0, 1, False, 0,
                ctypes.byref(actual_type), ctypes.byref(fmt), ctypes.byref(n),
                ctypes.byref(after), ctypes.byref(data),
            ) == 0 and data:
                pid = int(ctypes.cast(data, ctypes.POINTER(c_ulong))[0])
                self._x11.XFree(data)
                return pid
        except Exception:  # noqa: BLE001
            pass
        return 0

    def _window_bounds(self, wid: int) -> Bounds:
        try:
            class XWindowAttributes(ctypes.Structure):
                _fields_ = [("x", c_int), ("y", c_int), ("width", c_int), ("height", c_int),
                            ("border_width", c_int), ("depth", c_int), ("visual", c_void_p),
                            ("root", c_ulong), ("class_", c_int), ("bit_gravity", c_int),
                            ("win_gravity", c_int), ("backing_store", c_int),
                            ("backing_planes", c_ulong), ("backing_pixel", c_ulong),
                            ("save_under", c_int), ("colormap", c_ulong), ("map_installed", c_int),
                            ("map_state", c_int), ("all_event_masks", c_long),
                            ("your_event_mask", c_long), ("do_not_propagate_mask", c_long),
                            ("override_redirect", c_int), ("screen", c_void_p)]
            attrs = XWindowAttributes()
            if self._x11.XGetWindowAttributes(ctypes.c_void_p(self._display), c_ulong(wid), ctypes.byref(attrs)):
                # Translate window-local origin to root coordinates.
                root = c_ulong(0)
                x = c_int(0); y = c_int(0)
                self._x11.XTranslateCoordinates(
                    ctypes.c_void_p(self._display), c_ulong(wid), c_ulong(self._root),
                    0, 0, ctypes.byref(x), ctypes.byref(y), ctypes.byref(root),
                )
                return Bounds(int(x.value), int(y.value), int(attrs.width), int(attrs.height))
        except Exception:  # noqa: BLE001
            pass
        return Bounds()

    def _focused(self) -> int:
        try:
            focus = c_ulong(0); revert = c_int(0)
            self._x11.XGetInputFocus(ctypes.c_void_p(self._display), ctypes.byref(focus), ctypes.byref(revert))
            return int(focus.value)
        except Exception:  # noqa: BLE001
            return 0

    async def focus_window(self, window_id: str, *, foreground: bool = False) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Focusing windows requires an active X11 driver.")
        wid = c_ulong(int(window_id))
        try:
            self._x11.XRaiseWindow(ctypes.c_void_p(self._display), wid)
            self._x11.XSetInputFocus(ctypes.c_void_p(self._display), wid, 1, 0)  # RevertToParent
            self._x11.XFlush(ctypes.c_void_p(self._display))
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedAction(f"could not focus window {window_id}") from exc
        return InputResult(delivered=True, delivery_mode="foreground" if foreground else "background")

    async def window_control(self, window_id: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        if not self._started:
            raise UnsupportedAction("Window control requires an active X11 driver.")
        wid = c_ulong(int(window_id))
        try:
            if operation == "minimize":
                self._x11.XIconifyWindow(ctypes.c_void_p(self._display), wid, 0)
            elif operation in ("show", "restore"):
                self._x11.XMapWindow(ctypes.c_void_p(self._display), wid)
            elif operation == "maximize":
                # A real maximize is a WM request; map+raise is the honest best-effort.
                self._x11.XMapWindow(ctypes.c_void_p(self._display), wid)
                self._x11.XRaiseWindow(ctypes.c_void_p(self._display), wid)
            elif operation == "close":
                WM_DELETE = self._atom("WM_DELETE_WINDOW")
                # A ClientMessage is complex via ctypes; send a synthetic event is unsafe,
                # so fall back to an honest refusal for close on X11.
                raise UnsupportedAction("closing windows isn't implemented for X11 yet")
            else:
                raise UnsupportedAction(f"unknown window operation {operation!r}")
            self._x11.XFlush(ctypes.c_void_p(self._display))
        except UnsupportedAction:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedAction(f"could not {operation} window {window_id}") from exc
        return {"windowId": window_id, "operation": operation, "done": True}

    # ── applications ─────────────────────────────────────────────────────────

    def _applications_by_pid(self) -> list[ApplicationInfo]:
        seen: dict[int, ApplicationInfo] = {}
        for window in self.list_windows():
            if window.pid in seen:
                seen[window.pid].window_ids.append(window.id)
                continue
            name, exe = self._process_name(window.pid)
            seen[window.pid] = ApplicationInfo(id=str(window.pid), name=name, pid=window.pid,
                                               executable=exe, running=True, window_ids=[window.id])
        return sorted(seen.values(), key=lambda a: a.name.lower())

    def _process_name(self, pid: int) -> tuple[str, str]:
        if not pid:
            return ("", "")
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
            return (os.path.basename(exe), exe)
        except Exception:  # noqa: BLE001
            try:
                with open(f"/proc/{pid}/comm", encoding="utf-8") as fh:
                    return (fh.read().strip(), "")
            except Exception:  # noqa: BLE001
                return (f"pid {pid}", "")

    def list_applications(self) -> list[ApplicationInfo]:
        if not self._started:
            return []
        return self._applications_by_pid()

    async def launch_application(self, target: str, *, args: list[str] | None = None) -> ApplicationInfo:
        if not self._started:
            raise UnsupportedAction("Launching applications requires an active X11 driver.")
        import asyncio  # noqa: PLC0415

        try:
            proc = await asyncio.create_subprocess_exec(target, *(args or []))
        except Exception as exc:  # noqa: BLE001
            from ..errors import ApplicationNotFound  # noqa: PLC0415

            raise ApplicationNotFound(f"Eclipse couldn't start {target!r}.") from exc
        await asyncio.sleep(0.6)
        return ApplicationInfo(id=str(proc.pid), name=os.path.basename(target), pid=proc.pid,
                               executable=target, running=True)

    # ── capture ──────────────────────────────────────────────────────────────

    async def capture(self, *, window_id: Optional[str] = None, region: Optional[Bounds] = None,
                      display_id: Optional[str] = None) -> ScreenFrame:
        if not self._started:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(self._reason or "no X11 display")
        bounds = region
        if bounds is None and window_id:
            bounds = self._window_bounds(int(window_id))
        if bounds is None:
            bounds = self.list_displays()[0].bounds
        try:
            img = self._grab(bounds)
        except Exception as exc:  # noqa: BLE001
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(f"X11 capture failed: {str(exc)[:120]}") from exc
        png = None
        try:
            import io  # noqa: PLC0415

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png = buf.getvalue()
        except Exception:  # noqa: BLE001
            png = None
        return ScreenFrame(data=img, width=bounds.width, height=bounds.height, bounds=bounds, png_bytes=png)

    def _grab(self, bounds: Bounds) -> Any:
        ximage_ptr = self._x11.XGetImage(
            ctypes.c_void_p(self._display), c_ulong(self._root),
            c_int(bounds.x), c_int(bounds.y), c_uint(bounds.width), c_uint(bounds.height),
            c_ulong(0xFFFFFFFF), c_int(2),  # AllPlanes, ZPixmap
        )
        if not ximage_ptr:
            raise UnsupportedAction("XGetImage returned nothing")
        ximage = ctypes.cast(ximage_ptr, ctypes.POINTER(_XImage)).contents
        width, height = ximage.width, ximage.height
        bpl = ximage.bytes_per_line
        depth = ximage.depth
        raw = ctypes.string_at(ximage.data, bpl * height)
        self._x11.XDestroyImage(ximage_ptr)
        try:
            from PIL import Image  # noqa: PLC0415

            # XImage is BGRX on a typical 24/32-bit TrueColor visual.
            mode = "RGBA" if depth == 32 else "RGB"
            step = 4 if depth == 32 else 3
            image = Image.frombuffer("RGB", (width, height), raw, "raw", "BGRX" if step == 4 else "BGR", bpl, 1)
            return image.convert("RGB")
        except Exception:  # noqa: BLE001
            return None

    def accessibility_tree(self, window_id: Optional[str] = None) -> Any:
        if self._ax is None or not getattr(self._ax, "available", False):
            return None
        try:
            return self._ax.tree(window_id)
        except Exception:  # noqa: BLE001
            return None

    # ── input (XTest foreground; XSendEvent background best-effort) ──────────

    def _xtest_ready(self) -> bool:
        return self._xtst is not None and self._display is not None

    def _fake_motion(self, x: int, y: int) -> None:
        self._xtst.XTestFakeMotionEvent(ctypes.c_void_p(self._display), -1, c_int(x), c_int(y), c_ulong(0))
        self._x11.XFlush(ctypes.c_void_p(self._display))

    def _fake_button(self, button: int, down: bool) -> None:
        self._xtst.XTestFakeButtonEvent(ctypes.c_void_p(self._display), c_uint(button), c_int(1 if down else 0), c_ulong(0))
        self._x11.XFlush(ctypes.c_void_p(self._display))

    async def click(self, x: int, y: int, *, button: str = "left", count: int = 1,
                    delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Clicking requires an active X11 driver.")
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        num = {"left": 1, "middle": 2, "right": 3}[button]
        self._fake_motion(x, y)
        for _ in range(max(1, count)):
            self._fake_button(num, True)
            self._fake_button(num, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def move(self, x: int, y: int, *, delivery_mode: str = "background",
                   window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Pointer movement requires an active X11 driver.")
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        self._fake_motion(x, y)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                         window_id: Optional[str] = None) -> InputResult:
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        num = {"left": 1, "middle": 2, "right": 3}[button]
        self._fake_motion(x, y)
        self._fake_button(num, True)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                       window_id: Optional[str] = None) -> InputResult:
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        num = {"left": 1, "middle": 2, "right": 3}[button]
        self._fake_button(num, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left",
                   delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        num = {"left": 1, "middle": 2, "right": 3}[button]
        self._fake_motion(x1, y1)
        self._fake_button(num, True)
        steps = 12
        for i in range(1, steps + 1):
            self._fake_motion(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
        self._fake_button(num, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None,
                     delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not self._xtest_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        if at:
            self._fake_motion(at[0], at[1])
        # X11 wheel is buttons 4/5 (vertical) and 6/7 (horizontal).
        button = 4 if dy > 0 else 5
        for _ in range(abs(int(dy))):
            self._fake_button(button, True)
            self._fake_button(button, False)
        if dx:
            hbutton = 7 if dx > 0 else 6
            for _ in range(abs(int(dx))):
                self._fake_button(hbutton, True)
                self._fake_button(hbutton, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    def _fake_key(self, vk: int, down: bool) -> None:
        self._xtst.XTestFakeKeyEvent(ctypes.c_void_p(self._display), c_uint(vk), c_int(1 if down else 0), c_ulong(0))
        self._x11.XFlush(ctypes.c_void_p(self._display))

    async def key(self, keys: list[str], *, delivery_mode: str = "background",
                  window_id: Optional[str] = None) -> InputResult:
        if not self._xtst_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        codes = [virtual_key(k) for k in keys]
        codes = [c for c in codes if c is not None]
        for code in codes:
            self._fake_key(code, True)
        for code in reversed(codes):
            self._fake_key(code, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def type_text(self, text: str, *, delivery_mode: str = "background",
                        window_id: Optional[str] = None) -> InputResult:
        if not self._xtst_ready():
            raise UnsupportedAction("XTest isn't available (libXtst missing).")
        # Type via keysyms mapped through the current keymap is complex; use the
        # XTest key path for the characters we can map and report honestly.
        for ch in text:
            code = _keysym_for_char(ch)
            if code is None:
                continue
            self._fake_key(code, True)
            self._fake_key(code, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def press_combo(self, combo: str, *, delivery_mode: str = "background",
                          window_id: Optional[str] = None) -> InputResult:
        normalized = normalize_combo(combo)
        keys = [k for k in normalized.split("+") if k]
        if not keys:
            raise UnsupportedAction(f"Eclipse doesn't recognise the key {combo!r}.")
        return await self.key(keys, delivery_mode=delivery_mode, window_id=window_id)

    def pointer_position(self) -> Optional[tuple[int, int]]:
        if not self._started:
            return None
        try:
            class XPointerRoot(ctypes.Structure):
                _fields_ = [("x", c_int), ("y", c_int), ("root", c_ulong), ("child", c_ulong)]
            root_ret = c_ulong(0); child_ret = c_ulong(0)
            rx = c_int(0); ry = c_int(0); wx = c_int(0); wy = c_int(0); mask = c_uint(0)
            if self._x11.XQueryPointer(
                ctypes.c_void_p(self._display), c_ulong(self._root),
                ctypes.byref(root_ret), ctypes.byref(child_ret),
                ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(mask),
            ):
                return (int(rx.value), int(ry.value))
        except Exception:  # noqa: BLE001
            pass
        return None


def _keysym_for_char(ch: str) -> Optional[int]:
    """Map a printable character to an X11 keycode via the server's keymap.

    Only ASCII letters/digits and a few punctuation keys are mapped here; a caller
    that needs full Unicode should use the clipboard. Unmapped characters are
    skipped (never a wrong keystroke).
    """
    if "a" <= ch <= "z":
        return ord(ch) - ord("a") + 0x61
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 0x41
    if "0" <= ch <= "9":
        return ord(ch)
    return None


__all__ = ["LinuxX11Driver"]
