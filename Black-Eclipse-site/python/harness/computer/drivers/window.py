"""A driver that drives ONE contained desktop window.

Remote/isolated desktops (a Windows Sandbox, an RDP session, a VM console) render
their desktop inside a host window. This driver wraps a base platform driver and
scopes every operation to that window:

  * capture grabs the window's rectangle (the guest desktop as the client draws it);
  * input translates window-local coordinates to absolute screen coordinates and
    sends foreground events, which the client forwards to the guest;
  * the single contained window is the only enumerable "window".

It is the honest attach mechanism for `WindowsSandboxProvisioner` and
`RdpDesktopProvisioner`: best-effort by nature (a client may not forward every
event), and explicit about its limits — accessibility into the guest is not
available, so the tree is None and the AX capability is False.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from ..errors import TargetNotFound, UnsupportedAction
from ..models import (
    AXNode,
    ApplicationInfo,
    Bounds,
    Capabilities,
    DisplayInfo,
    DriverContract,
    WindowInfo,
)
from .base import ComputerDriver, InputResult, ScreenFrame


class WindowDriver(ComputerDriver):
    id = "window"
    platform = "window"
    label = "Contained window (remote/isolated desktop)"

    def __init__(
        self,
        base: ComputerDriver,
        *,
        window_id: Optional[str] = None,
        title_hint: str = "",
        app_hint: str = "",
        input: str = "foreground",
        isolated: bool = True,
        headless: bool = False,
        ocr: Any = None,
        accessibility_bridge: bool = True,
    ) -> None:
        self._base = base
        self._window_id = str(window_id) if window_id is not None else None
        self._title_hint = title_hint.lower()
        self._app_hint = app_hint.lower()
        self._input = input
        self._isolated = isolated
        self._headless = headless
        # The guest accessibility tree is not reachable from the host, so the
        # bridge derives a real element tree from OCR of the contained window —
        # honest (labelled `source="ocr"`) and enough for grounding.
        self._ocr = ocr
        self._bridge = accessibility_bridge
        self.platform = getattr(base, "platform", "window")
        self._ax_cache: dict[str, tuple[str, AXNode]] = {}
        self._ax_lock = asyncio.Lock()

    # ── attach ───────────────────────────────────────────────────────────────

    def _find_window(self) -> Optional[WindowInfo]:
        if self._window_id is not None:
            try:
                return self._base.get_window(self._window_id)
            except Exception:  # noqa: BLE001
                return None
        try:
            windows = self._base.list_windows()
        except Exception:  # noqa: BLE001
            return None
        for window in windows:
            haystack = f"{window.title} {window.app}".lower()
            if self._title_hint and self._title_hint in haystack:
                return window
            if self._app_hint and self._app_hint in haystack:
                return window
        return None

    def attached(self) -> bool:
        return self._find_window() is not None

    def window_id(self) -> Optional[str]:
        window = self._find_window()
        return window.id if window else self._window_id

    async def start(self) -> None:
        window = self._find_window()
        if window is not None:
            self._window_id = window.id

    async def stop(self) -> None:
        return None

    # ── contract / capabilities ──────────────────────────────────────────────

    def contract(self) -> DriverContract:
        return DriverContract(
            platform=self.platform, name=self.id,
            capabilities=("displays", "windows", "screen_capture", "foreground_input",
                          "window_management"),
        )

    def capabilities(self) -> Capabilities:
        bridge = bool(self._bridge and self._ocr is not None and getattr(self._ocr, "available", False))
        notes = ["input is forwarded to a contained window; the guest's native accessibility tree isn't reachable"]
        if bridge:
            notes.append("element tree is derived from OCR of the contained window (source=ocr)")
        else:
            notes.append("no OCR bridge is available for the contained window")
        return Capabilities(
            platform=self.platform,
            background_input=False,
            foreground_input=True,
            accessibility=bridge,
            screen_capture=True,
            multi_monitor=False,
            window_management=True,
            application_management=False,
            set_value=False,
            headless_desktop=self._headless,
            notes=notes,
        )

    def health(self) -> dict[str, Any]:
        return {
            "driver": self.id, "healthy": self.attached(), "platform": self.platform,
            "window": self.window_id(), "isolated": self._isolated, "headless": self._headless,
        }

    @property
    def isolated(self) -> bool:
        return self._isolated

    @property
    def headless(self) -> bool:
        return self._headless

    # ── geometry (scoped to the window) ──────────────────────────────────────

    def list_displays(self) -> list[DisplayInfo]:
        window = self._find_window()
        bounds = window.bounds if window else Bounds(0, 0, 1024, 768)
        return [DisplayInfo(id="contained", bounds=bounds, working_area=bounds,
                            primary=True, scale=1.0)]

    def list_windows(self) -> list[WindowInfo]:
        window = self._find_window()
        if window is None:
            return []
        contained = WindowInfo(id=window.id, title=window.title, pid=window.pid,
                               bounds=window.bounds, app=window.app, visible=True, focused=True)
        return [contained]

    def get_window(self, window_id: str) -> Optional[WindowInfo]:
        return next((w for w in self.list_windows() if w.id == str(window_id)), None)

    async def focus_window(self, window_id: str, *, foreground: bool = False) -> InputResult:
        return await self._base.focus_window(self._window_id or window_id, foreground=True)

    def _origin(self) -> tuple[int, int, int, int]:
        window = self._find_window()
        if window is None:
            raise TargetNotFound("The contained desktop window is gone.", window=self._window_id or "")
        b = window.bounds
        return b.x, b.y, b.width, b.height

    def _absolute(self, x: int, y: int) -> tuple[int, int]:
        ox, oy, _w, _h = self._origin()
        return ox + int(x), oy + int(y)

    # ── capture ──────────────────────────────────────────────────────────────

    async def capture(self, *, window_id: Optional[str] = None, region: Optional[Bounds] = None,
                      display_id: Optional[str] = None) -> ScreenFrame:
        window = self._find_window()
        if window is None:
            from ..errors import ScreenCaptureUnavailable  # noqa: PLC0415

            raise ScreenCaptureUnavailable("The contained desktop window is gone.")
        if region is not None:
            abs_region = Bounds(window.bounds.x + region.x, window.bounds.y + region.y,
                                region.width, region.height)
            frame = await self._base.capture(region=abs_region)
            frame.bounds = region
            return frame
        frame = await self._base.capture(window_id=window.id)
        return frame

    def accessibility_tree(self, window_id: Optional[str] = None) -> Any:
        """A real element tree for the guest, derived from OCR of its window.

        The guest's native accessibility tree is not reachable from the host, so
        the bridge reads the contained window's pixels and turns OCR words into an
        `AXNode` tree (roles/text/bounds). It is cached briefly so a snapshot +
        its verification don't each pay for a fresh OCR pass. Returns None when the
        bridge is disabled or no OCR/сapture is available — never an invented tree.
        """
        if not self._bridge or self._ocr is None or not getattr(self._ocr, "available", False):
            return None
        cache_key = self._window_id or "_contained"
        cached = self._ax_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < 0.5:
            return cached[1]
        image = self._sync_grab()
        if image is None:
            return cached[1] if cached else None
        try:
            bounds = self._contained_bounds()
            result = self._ocr.read(image, bounds=None)
        except Exception:  # noqa: BLE001
            return cached[1] if cached else None
        if not getattr(result, "available", False):
            return cached[1] if cached else None
        tree = self._tree_from_ocr(result, bounds)
        self._ax_cache[cache_key] = (now, tree)
        return tree

    def _contained_bounds(self) -> Optional[Bounds]:
        window = self._find_window()
        return window.bounds if window else None

    def _sync_grab(self) -> Any:
        """A synchronous grab of the contained window (host screen APIs)."""
        try:
            window = self._find_window()
            if window is None:
                return None
            from PIL import ImageGrab  # noqa: PLC0415

            b = window.bounds
            return ImageGrab.grab(bbox=(b.x, b.y, b.right, b.bottom)).convert("RGB")
        except Exception:  # noqa: BLE001 - a missing grab backend is an honest None
            return None

    def _tree_from_ocr(self, result: Any, origin: Optional[Bounds]) -> AXNode:
        """Build an AXNode tree from OCR lines (words → leaves; line → container)."""
        ox = origin.x if origin else 0
        oy = origin.y if origin else 0
        root = AXNode(role="window", name="", bounds=origin or Bounds())
        for index, line in enumerate(getattr(result, "lines", [])[:200], start=1):
            line_bounds = Bounds(line.bounds.x + ox, line.bounds.y + oy, line.bounds.width, line.bounds.height)
            line_node = AXNode(role="line", name=str(line.text), bounds=line_bounds,
                               interactive=False)
            for word in getattr(line, "words", []):
                word_bounds = Bounds(word.bounds.x + ox, word.bounds.y + oy, word.bounds.width, word.bounds.height)
                line_node.children.append(AXNode(
                    role="text", name=str(word.text), bounds=word_bounds,
                    interactive=False, native_handle={"ocrWord": index},
                ))
            root.children.append(line_node)
        return root

    # ── input (window-local → absolute foreground) ───────────────────────────

    async def _ensure_foreground(self) -> None:
        try:
            await self._base.focus_window(self._window_id, foreground=True)
        except Exception:  # noqa: BLE001
            pass

    def _wants_background(self, delivery_mode: str) -> bool:
        """Best-effort background delivery, when the base driver supports it.

        The base platform driver may post input to the contained window without
        raising it; the core then escalates to foreground if no change is seen.
        """
        return delivery_mode == "background" and getattr(
            self._base.capabilities(), "background_input", False
        )

    async def click(self, x: int, y: int, *, button: str = "left", count: int = 1,
                    delivery_mode: str = "foreground", window_id: Optional[str] = None) -> InputResult:
        ax, ay = self._absolute(x, y)
        if self._wants_background(delivery_mode):
            try:
                return await self._base.click(ax, ay, button=button, count=count,
                                              delivery_mode="background", window_id=self._window_id)
            except Exception:  # noqa: BLE001 - fall back to foreground
                pass
        await self._ensure_foreground()
        return await self._base.click(ax, ay, button=button, count=count,
                                      delivery_mode="foreground", window_id=self._window_id)

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "foreground",
                         window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        ax, ay = self._absolute(x, y)
        return await self._base.mouse_down(ax, ay, button=button, delivery_mode="foreground",
                                           window_id=self._window_id)

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "foreground",
                       window_id: Optional[str] = None) -> InputResult:
        ax, ay = self._absolute(x, y)
        return await self._base.mouse_up(ax, ay, button=button, delivery_mode="foreground",
                                         window_id=self._window_id)

    async def move(self, x: int, y: int, *, delivery_mode: str = "foreground",
                   window_id: Optional[str] = None) -> InputResult:
        ax, ay = self._absolute(x, y)
        return await self._base.move(ax, ay, delivery_mode="foreground", window_id=self._window_id)

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None,
                     delivery_mode: str = "foreground", window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        absolute_at = self._absolute(*at) if at else None
        return await self._base.scroll(dx=dx, dy=dy, at=absolute_at, delivery_mode="foreground",
                                       window_id=self._window_id)

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left",
                   delivery_mode: str = "foreground", window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        return await self._base.drag(*self._absolute(x1, y1), *self._absolute(x2, y2),
                                     button=button, delivery_mode="foreground", window_id=self._window_id)

    async def type_text(self, text: str, *, delivery_mode: str = "foreground",
                        window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        return await self._base.type_text(text, delivery_mode="foreground", window_id=self._window_id)

    async def key(self, keys: list[str], *, delivery_mode: str = "foreground",
                  window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        return await self._base.key(keys, delivery_mode="foreground", window_id=self._window_id)

    async def press_combo(self, combo: str, *, delivery_mode: str = "foreground",
                          window_id: Optional[str] = None) -> InputResult:
        await self._ensure_foreground()
        return await self._base.press_combo(combo, delivery_mode="foreground", window_id=self._window_id)

    def pointer_position(self) -> Optional[tuple[int, int]]:
        position = self._base.pointer_position()
        if position is None:
            return None
        ox, oy, _w, _h = self._origin()
        return (position[0] - ox, position[1] - oy)


__all__ = ["WindowDriver"]
