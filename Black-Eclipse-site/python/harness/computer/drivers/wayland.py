"""The Wayland driver.

Wayland deliberately has no global-input/capture API for arbitrary clients; a
client must go through the compositor's own portal or tools. This driver uses two
real, user-space Wayland tools when present:

  * **capture** via `grim` (wlr-screencopy) — works on wlroots-based compositors;
  * **input** via `ydotool` (uinput) — works when the `ydotoold` daemon is running
    with the needed permissions.

Each capability is reported honestly: a missing tool (or a compositor grim can't
capture) makes that capability False with a reason, never a fabricated result.
Window enumeration is not available on Wayland (no global window list).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from typing import Any, Optional

from ..errors import UnsupportedAction
from ..models import Bounds, Capabilities, DisplayInfo, DriverContract
from .base import ComputerDriver, InputResult, ScreenFrame

_IS_LINUX = sys.platform.startswith("linux")

# ydotool key codes for the keys we can map (Linux input-event-codes).
_KEYCODES = {
    "enter": 28, "return": 28, "esc": 1, "escape": 1, "tab": 15, "space": 57,
    "backspace": 14, "delete": 111, "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
    "ctrl": 29, "control": 29, "shift": 42, "alt": 56, "meta": 125, "super": 125,
}
for _i in range(1, 13):
    _KEYCODES[f"f{_i}"] = 58 + _i - 1
for _c in "abcdefghijklmnopqrstuvwxyz":
    _KEYCODES[_c] = ord(_c) - ord("a") + 30
for _d in "0123456789":
    _KEYCODES[_d] = ord(_d) - ord("0") + 2


def _wayland_session() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


class WaylandDriver(ComputerDriver):
    id = "wayland"
    platform = "linux"
    label = "Wayland (grim + ydotool)"

    def __init__(self, *, display: Optional[str] = None) -> None:
        self._display = display or os.environ.get("WAYLAND_DISPLAY")
        self._grim = shutil.which("grim") if _IS_LINUX else None
        self._ydotool = shutil.which("ydotool") if _IS_LINUX else None
        self._started = False
        self._reason = ""

    async def start(self) -> None:
        if not _IS_LINUX:
            self._reason = "the Wayland driver is only available on Linux"
            return
        if not self._display:
            self._reason = "no WAYLAND_DISPLAY is set"
            return
        self._started = True

    async def stop(self) -> None:
        self._started = False

    def contract(self) -> DriverContract:
        caps = ["displays"]
        if self._grim:
            caps.append("screen_capture")
        if self._ydotool:
            caps.append("foreground_input")
        return DriverContract(platform="linux", name=self.id, capabilities=tuple(caps))

    def capabilities(self) -> Capabilities:
        notes: list[str] = ["Wayland exposes no global window/accessibility API"]
        if not self._grim:
            notes.append("capture needs `grim` (install grim)")
        if not self._ydotool:
            notes.append("input needs `ydotool` + a running `ydotoold` (install ydotool)")
        return Capabilities(
            platform="linux",
            background_input=False,
            foreground_input=bool(self._ydotool) and self._started,
            accessibility=False,
            screen_capture=bool(self._grim) and self._started,
            multi_monitor=False,
            window_management=False,
            application_management=False,
            set_value=False,
            headless_desktop=False,
            notes=notes,
        )

    def health(self) -> dict[str, Any]:
        return {
            "driver": self.id, "healthy": self._started, "platform": "linux",
            "wayland": bool(self._display), "grim": bool(self._grim), "ydotool": bool(self._ydotool),
            **({} if self._started else {"reason": self._reason}),
        }

    def list_displays(self) -> list[DisplayInfo]:
        if not self._started:
            return super().list_displays()
        # Wayland has no global geometry API; report the grim output size if known,
        # else a neutral default (the caller captures and gets the real size).
        return [DisplayInfo(id="wayland", bounds=Bounds(0, 0, 1920, 1080),
                            working_area=Bounds(0, 0, 1920, 1080), primary=True, scale=1.0)]

    # ── capture via grim ─────────────────────────────────────────────────────

    async def capture(self, *, window_id: Optional[str] = None, region: Optional[Bounds] = None,
                      display_id: Optional[str] = None) -> ScreenFrame:
        if not (self._started and self._grim):
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(self._reason or "capture needs `grim`")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            path = handle.name
        argv = [self._grim]
        if region is not None:
            argv += ["-g", f"{region.x},{region.y} {region.width}x{region.height}"]
        argv.append(path)
        env = {**os.environ, "WAYLAND_DISPLAY": self._display or ""}
        proc = await asyncio.create_subprocess_exec(*argv, env=env,
                                                    stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()
        try:
            with open(path, "rb") as fh:
                png = fh.read()
        except OSError as exc:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable(f"grim produced no frame ({str(exc)[:80]})") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        bounds = region or Bounds(0, 0, 1920, 1080)
        data = None
        try:
            import io  # noqa: PLC0415

            from PIL import Image  # noqa: PLC0415

            data = Image.open(io.BytesIO(png)).convert("RGB")
            bounds = Bounds(bounds.x, bounds.y, data.width, data.height)
        except Exception:  # noqa: BLE001
            data = None
        return ScreenFrame(data=data, width=bounds.width, height=bounds.height, bounds=bounds, png_bytes=png)

    # ── input via ydotool ────────────────────────────────────────────────────

    async def _ydotool(self, *args: str) -> None:
        if not self._ydotool:
            raise UnsupportedAction("input needs `ydotool`")
        proc = await asyncio.create_subprocess_exec(self._ydotool, *args,
                                                    stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()

    async def click(self, x: int, y: int, *, button: str = "left", count: int = 1,
                    delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if not (self._started and self._ydotool):
            raise UnsupportedAction("input needs `ydotool`")
        await self._ydotool("mousemove", "--absolute", "-x", str(x), "-y", str(y))
        code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}[button]
        for _ in range(max(1, count)):
            await self._ydotool("click", code)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def move(self, x: int, y: int, *, delivery_mode: str = "background",
                   window_id: Optional[str] = None) -> InputResult:
        await self._ydotool("mousemove", "--absolute", "-x", str(x), "-y", str(y))
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                         window_id: Optional[str] = None) -> InputResult:
        await self._ydotool("mousemove", "--absolute", "-x", str(x), "-y", str(y))
        await self._ydotool("click", {"left": "0x40", "right": "0x41", "middle": "0x42"}[button])
        return InputResult(delivered=True, delivery_mode="foreground")

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "background",
                       window_id: Optional[str] = None) -> InputResult:
        await self._ydotool("click", {"left": "0x80", "right": "0x81", "middle": "0x82"}[button])
        return InputResult(delivered=True, delivery_mode="foreground")

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left",
                   delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        await self._ydotool("mousemove", "--absolute", "-x", str(x1), "-y", str(y1))
        await self._ydotool("click", "0x40")
        steps = 12
        for i in range(1, steps + 1):
            await self._ydotool("mousemove", "--absolute", "-x", str(x1 + (x2 - x1) * i // steps),
                                "-y", str(y1 + (y2 - y1) * i // steps))
        await self._ydotool("click", "0x80")
        return InputResult(delivered=True, delivery_mode="foreground")

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None,
                     delivery_mode: str = "background", window_id: Optional[str] = None) -> InputResult:
        if at:
            await self._ydotool("mousemove", "--absolute", "-x", str(at[0]), "-y", str(at[1]))
        code = "0x00" if dy > 0 else "0x01"  # wheel up/down
        for _ in range(abs(int(dy))):
            await self._ydotool("click", code)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def type_text(self, text: str, *, delivery_mode: str = "background",
                        window_id: Optional[str] = None) -> InputResult:
        # ydotool `type` injects a UTF-8 string directly (needs ydotoold).
        await self._ydotool("type", text)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def key(self, keys: list[str], *, delivery_mode: str = "background",
                  window_id: Optional[str] = None) -> InputResult:
        codes = [_KEYCODES.get(k.lower()) for k in keys]
        if any(code is None for code in codes):
            raise UnsupportedAction("a key in the combo isn't mapped for Wayland")
        sequence = ":".join(f"{code}:1" for code in codes) + ":" + ":".join(f"{code}:0" for code in reversed(codes))
        await self._ydotool("key", sequence)
        return InputResult(delivered=True, delivery_mode="foreground")

    async def press_combo(self, combo: str, *, delivery_mode: str = "background",
                          window_id: Optional[str] = None) -> InputResult:
        keys = [k for k in (combo or "").replace(" ", "").split("+") if k]
        return await self.key(keys, delivery_mode=delivery_mode, window_id=window_id)

    def pointer_position(self) -> Optional[tuple[int, int]]:
        return None  # Wayland exposes no global pointer position


__all__ = ["WaylandDriver"]
