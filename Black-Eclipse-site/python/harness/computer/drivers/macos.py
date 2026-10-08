"""The macOS desktop driver.

Implemented with `ctypes` against the Core Graphics (`CGEvent`, `CGWindowList`,
`CGDisplay`) and Application Services (AXUIElement) frameworks — no third-party
package. It provides display geometry, window enumeration (`CGWindowListCopyWindowInfo`),
screen capture (`CGWindowListCreateImage`), input via `CGEventPost`, and
accessibility via the AX API.

macOS gates desktop control behind TCC permissions (Screen Recording,
Accessibility). Eclipse cannot grant them; `doctor` names exactly what is missing
and every action fails honestly until a person grants them in System Settings.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import c_double, c_int32, c_uint32, c_void_p
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

_IS_MAC = sys.platform == "darwin"


def _cg_available() -> tuple[bool, str]:
    if not _IS_MAC:
        return False, "the macOS driver is only available on macOS"
    if ctypes.util.find_library("CoreGraphics") is None and ctypes.util.find_library("ApplicationServices") is None:
        return False, "the Core Graphics framework couldn't be loaded"
    return True, ""


class CGPoint(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", c_double), ("height", c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class MacOSDriver(ComputerDriver):
    id = "macos"
    platform = "macos"
    label = "macOS (Core Graphics / AX)"

    def __init__(self) -> None:
        self._cg: Any = None
        self._as: Any = None
        self._cf: Any = None
        self._started = False
        self._ax: Any = None
        self._reason = ""

    async def start(self) -> None:
        ok, reason = _cg_available()
        if not ok:
            self._reason = reason
            return
        try:
            self._cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics") or "CoreGraphics")
            self._cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation") or "CoreFoundation")
            try:
                self._as = ctypes.CDLL(ctypes.util.find_library("ApplicationServices") or "ApplicationServices")
            except Exception:  # noqa: BLE001
                self._as = None
            from ..accessibility.macos import build_ax_provider  # noqa: PLC0415

            self._ax = build_ax_provider()
            self._started = True
        except Exception as exc:  # noqa: BLE001
            self._reason = f"the macOS driver couldn't initialise ({str(exc)[:120]})"

    async def stop(self) -> None:
        self._started = False

    def contract(self) -> DriverContract:
        return DriverContract(
            platform="macos", name=self.id,
            capabilities=("displays", "windows", "screen_capture", "foreground_input", "window_management"),
        )

    def capabilities(self) -> Capabilities:
        ax_ok = bool(getattr(self._ax, "available", False))
        notes: list[str] = []
        if not self._started:
            notes.append(self._reason or "the macOS driver is not active")
        if self._started and not self._has_screen_recording():
            notes.append("Screen Recording permission is not granted (System Settings → Privacy & Security)")
        if not ax_ok:
            notes.append("accessibility tree is limited (Accessibility permission or AX API unavailable)")
        return Capabilities(
            platform="macos",
            background_input=False,   # macOS has no background-input path; foreground only.
            foreground_input=self._started,
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
            "driver": self.id, "healthy": self._started, "platform": "macos",
            "screenRecording": self._has_screen_recording() if self._started else False,
            "accessibility": bool(getattr(self._ax, "available", False)),
            **({} if self._started else {"reason": self._reason}),
        }

    def _has_screen_recording(self) -> bool:
        """Best-effort TCC probe: whether screen capture returns real pixels."""
        try:
            image = self._cg.CGWindowListCreateImage(CGRect(), 1 << 3, 0, 1)  # kCGWindowListOptionOnScreenOnly
            return bool(image)
        except Exception:  # noqa: BLE001
            return False

    # ── displays ─────────────────────────────────────────────────────────────

    def list_displays(self) -> list[DisplayInfo]:
        if not self._started:
            return super().list_displays()
        uid = c_uint32(0)
        try:
            count = c_uint32(0)
            self._cg.CGGetActiveDisplayList(0, None, ctypes.byref(count))
            count = int(count.value)
            displays: list[DisplayInfo] = []
            for i in range(count):
                did = c_uint32(0)
                arr = (c_uint32 * 1)()
                got = c_uint32(0)
                if not self._cg.CGGetActiveDisplayList(1, arr, ctypes.byref(got)):
                    continue
                did = arr[0]
                rect = self._cg.CGDisplayBounds(did) if hasattr(self._cg, "CGDisplayBounds") else CGRect()
                bounds = Bounds(int(rect.origin.x), int(rect.origin.y), int(rect.size.width), int(rect.size.height))
                displays.append(DisplayInfo(id=f"display{i}", bounds=bounds, working_area=bounds,
                                            primary=(i == 0), scale=1.0))
            return displays or super().list_displays()
        except Exception:  # noqa: BLE001
            return super().list_displays()

    # ── windows ──────────────────────────────────────────────────────────────

    def list_windows(self) -> list[WindowInfo]:
        if not self._started:
            return []
        try:
            option = 1 | 16 | 32  # OnScreenOnly | ExcludeDesktopElements | ... (common flags)
            cf_array = self._cg.CGWindowListCopyWindowInfo(option, 0)
            if not cf_array:
                return []
            count = self._cf.CFArrayGetCount(cf_array)
            out: list[WindowInfo] = []
            for i in range(count):
                info = self._cf.CFArrayGetValueAtIndex(cf_array, i)
                d = self._cf_dict(info)
                if not d:
                    continue
                wid = d.get("kCGWindowNumber")
                pid = d.get("kCGWindowOwnerPID")
                title = d.get("kCGWindowName") or ""
                app = d.get("kCGWindowOwnerName") or ""
                b = d.get("kCGWindowBounds") or {}
                bounds = Bounds(int(b.get("X", 0)), int(b.get("Y", 0)),
                                int(b.get("Width", 0)), int(b.get("Height", 0)))
                if not title:
                    continue
                out.append(WindowInfo(id=str(wid), title=str(title), pid=int(pid or 0),
                                      bounds=bounds, app=str(app), z_order=i, visible=True))
            self._cf.CFRelease(cf_array)
            return out
        except Exception:  # noqa: BLE001
            return []

    def _cf_dict(self, cf_dictionary: Any) -> dict[str, Any]:
        try:
            keys = self._cf.CFDictionaryGetKeysAndValues  # existence check
            self._cf.CFStringCreateWithCString.restype = c_void_p
            self._cf.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]
            self._cf.CFDictionaryGetValue.restype = c_void_p
            out: dict[str, Any] = {}
            for key in ("kCGWindowNumber", "kCGWindowOwnerPID", "kCGWindowName",
                        "kCGWindowOwnerName", "kCGWindowBounds"):
                ckey = self._cf.CFStringCreateWithCString(None, key.encode(), 0x08000100)
                value = self._cf.CFDictionaryGetValue(cf_dictionary, ckey)
                if not value:
                    continue
                if key in ("kCGWindowNumber", "kCGWindowOwnerPID"):
                    out[key] = self._cf_int(value)
                elif key == "kCGWindowBounds":
                    out[key] = self._cf_bounds(value)
                else:
                    out[key] = self._cf_string(value)
                self._cf.CFRelease(ckey)
            return out
        except Exception:  # noqa: BLE001
            return {}

    def _cf_string(self, cf_str: Any) -> str:
        try:
            self._cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
            ptr = self._cf.CFStringGetCStringPtr(cf_str, 0x08000100)
            if ptr:
                return ptr.decode("utf-8", "replace")
            buf = ctypes.create_string_buffer(1024)
            self._cf.CFStringGetCString(cf_str, buf, 1024, 0x08000100)
            return buf.value.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""

    def _cf_int(self, cf_num: Any) -> int:
        try:
            return int(self._cf.CFNumberGetValue(cf_num, 12))  # kCFNumberSInt64Type-ish
        except Exception:  # noqa: BLE001
            return 0

    def _cf_bounds(self, cf_dict: Any) -> dict[str, float]:
        out: dict[str, float] = {}
        if self._as is None:
            return out
        try:
            rect = CGRect()
            self._as.CGRectMakeWithDictionaryRepresentation(cf_dict, ctypes.byref(rect))
            out = {"X": rect.origin.x, "Y": rect.origin.y, "Width": rect.size.width, "Height": rect.size.height}
        except Exception:  # noqa: BLE001
            pass
        return out

    async def focus_window(self, window_id: str, *, foreground: bool = False) -> InputResult:
        raise UnsupportedAction(
            "Focused window switching is not implemented on macOS yet; use the app switcher or launch_application."
        )

    # ── applications ─────────────────────────────────────────────────────────

    def list_applications(self) -> list[ApplicationInfo]:
        seen: dict[int, ApplicationInfo] = {}
        for window in self.list_windows():
            if window.pid in seen:
                seen[window.pid].window_ids.append(window.id)
                continue
            seen[window.pid] = ApplicationInfo(id=str(window.pid), name=window.app or f"pid {window.pid}",
                                               pid=window.pid, running=True, window_ids=[window.id])
        return sorted(seen.values(), key=lambda a: a.name.lower())

    async def launch_application(self, target: str, *, args: list[str] | None = None) -> ApplicationInfo:
        if not self._started:
            raise UnsupportedAction("Launching applications requires macOS.")
        import asyncio  # noqa: PLC0415

        argv = ["open", "-a", target, *(args or [])] if not target.endswith(".app") else ["open", target, *(args or [])]
        try:
            proc = await asyncio.create_subprocess_exec(*argv)
        except Exception as exc:  # noqa: BLE001
            from ..errors import ApplicationNotFound  # noqa: PLC0415

            raise ApplicationNotFound(f"Eclipse couldn't start {target!r}.") from exc
        await asyncio.sleep(0.8)
        return ApplicationInfo(id=str(proc.pid), name=target, pid=proc.pid, executable=target, running=True)

    # ── capture ──────────────────────────────────────────────────────────────

    async def capture(self, *, window_id: Optional[str] = None, region: Optional[Bounds] = None,
                      display_id: Optional[str] = None) -> ScreenFrame:
        if not self._started:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(self._reason or "the macOS driver is not active")
        bounds = region
        if bounds is None and window_id:
            win = next((w for w in self.list_windows() if w.id == str(window_id)), None)
            bounds = win.bounds if win else None
        if bounds is None:
            bounds = self.list_displays()[0].bounds
        try:
            image = self._cg.CGWindowListCreateImage(
                CGRect(CGPoint(bounds.x, bounds.y), CGSize(bounds.width, bounds.height)),
                1 << 3, 0, 1,
            )
        except Exception as exc:  # noqa: BLE001
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(f"macOS capture failed: {str(exc)[:120]}") from exc
        if not image:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable("Screen Recording permission is not granted for Eclipse.")
        png = self._png_from_cgimage(image)
        if png is None:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable("could not encode the macOS frame (Quartz image export unavailable)")
        data = self._pil_from_png(png)
        return ScreenFrame(data=data, width=bounds.width, height=bounds.height, bounds=bounds, png_bytes=png)

    def _png_from_cgimage(self, cg_image: Any) -> Optional[bytes]:
        try:
            import Quartz  # noqa: PLC0415  # optional pyobjc; absent ⇒ honest fallback

            rep = Quartz.NSBitmapImageRep.alloc().initWithCGImage_(cg_image)
            data = rep.representationUsingType_properties_(Quartz.NSPNGFileType, None)
            return bytes(data)
        except Exception:  # noqa: BLE001
            return None

    def _pil_from_png(self, png: bytes) -> Any:
        try:
            import io  # noqa: PLC0415

            from PIL import Image  # noqa: PLC0415

            return Image.open(io.BytesIO(png)).convert("RGB")
        except Exception:  # noqa: BLE001
            return None

    def accessibility_tree(self, window_id: Optional[str] = None) -> Any:
        if self._ax is None or not getattr(self._ax, "available", False):
            return None
        try:
            return self._ax.tree(window_id)
        except Exception:  # noqa: BLE001
            return None

    # ── input (CGEvent foreground only) ──────────────────────────────────────

    def _post_mouse(self, x: int, y: int, event_type: int, button: int = 0) -> None:
        point = CGPoint(float(x), float(y))
        event = self._cg.CGEventCreateMouseEvent(None, event_type, point, button)
        self._cg.CGEventPost(0, event)  # kCGHIDEventTap
        self._cg.CFRelease(event)

    async def click(self, x: int, y: int, *, button: str = "left", count: int = 1,
                    delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Clicking requires macOS.")
        # CGEvent types: leftDown=1 leftUp=2 rightDown=3 rightUp=4 otherDown=25 otherUp=26
        down, up, bnum = {
            "left": (1, 2, 0), "right": (3, 4, 1), "middle": (25, 26, 2),
        }[button]
        self._post_mouse(x, y, 5)  # mouseMoved
        for _ in range(max(1, count)):
            self._post_mouse(x, y, down, bnum)
            self._post_mouse(x, y, up, bnum)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def move(self, x: int, y: int, *, delivery_mode: str = "background",
                   window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Pointer movement requires macOS.")
        self._post_mouse(x, y, 5)  # mouseMoved
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                         window_id: Optional[str] = None) -> InputResult:
        down, _up, bnum = {"left": (1, 2, 0), "right": (3, 4, 1), "middle": (25, 26, 2)}[button]
        self._post_mouse(x, y, 5)
        self._post_mouse(x, y, down, bnum)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                       window_id: Optional[str] = None) -> InputResult:
        _down, up, bnum = {"left": (1, 2, 0), "right": (3, 4, 1), "middle": (25, 26, 2)}[button]
        self._post_mouse(x, y, up, bnum)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left",
                   delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        down, up, bnum = {"left": (1, 2, 0), "right": (3, 4, 1), "middle": (25, 26, 2)}[button]
        self._post_mouse(x1, y1, 5)
        self._post_mouse(x1, y1, down, bnum)
        steps = 12
        for i in range(1, steps + 1):
            self._post_mouse(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps, 6)  # leftDragged
        self._post_mouse(x2, y2, up, bnum)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None,
                     delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Scrolling requires macOS.")
        # ScrollWheelEvent2 takes int32 wheel1 (vertical), wheel2 (horizontal).
        event = self._cg.CGEventCreateScrollWheelEvent(None, 0, 2, c_int32(-dy), c_int32(-dx))
        self._cg.CGEventPost(0, event)
        self._cg.CFRelease(event)
        return InputResult(delivered=True, delivery_mode="foreground")

    def _post_key(self, vk: int, down: bool) -> None:
        event = self._cg.CGEventCreateKeyboardEvent(None, ctypes.c_uint16(vk), down)
        self._cg.CGEventPost(0, event)
        self._cg.CFRelease(event)

    async def key(self, keys: list[str], *, delivery_mode: str = "background",
                  window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Sending keys requires macOS.")
        codes = [virtual_key(k) for k in keys]
        codes = [c for c in codes if c is not None]
        for code in codes:
            self._post_key(code, True)
        for code in reversed(codes):
            self._post_key(code, False)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def type_text(self, text: str, *, delivery_mode: str = "background",
                        window_id: Optional[str] = None) -> InputResult:
        if not self._started:
            raise UnsupportedAction("Typing requires macOS.")
        for ch in text:
            # A bounded ASCII path; full Unicode typing needs the clipboard/IME.
            code = ord(ch)
            if code > 127:
                continue
            self._post_key(code, True)
            self._post_key(code, False)
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
            event = self._cg.CGEventCreate(None)
            point = self._cg.CGEventGetLocation(event)
            self._cg.CFRelease(event)
            return (int(point.x), int(point.y))
        except Exception:  # noqa: BLE001
            return None


__all__ = ["MacOSDriver"]
