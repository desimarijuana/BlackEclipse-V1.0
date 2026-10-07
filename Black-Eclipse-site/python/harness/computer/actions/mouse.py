"""The mouse toolset.

Wraps a driver's mouse methods with the full agent-facing verb set: move, click,
double-click, right/middle click, press/release, drag/drag-to, vertical and
horizontal scroll, relative move/click, and pointer position. Element targeting
is resolved to a point BEFORE this engine is called; this engine only knows how
to deliver a mouse event at a coordinate in a given delivery mode.
"""

from __future__ import annotations

from typing import Any, Optional

from ..errors import ActionFailed
from ..models import Bounds, Point


class MouseEngine:
    def __init__(self, driver: Any) -> None:
        self._driver = driver

    async def move(self, x: int, y: int, *, delivery_mode: str = "background") -> Any:
        return await self._driver.move(int(x), int(y), delivery_mode=delivery_mode)

    async def click(
        self, x: int, y: int, *, button: str = "left", count: int = 1,
        delivery_mode: str = "background", window_id: Optional[str] = None,
    ) -> Any:
        return await self._driver.click(int(x), int(y), button=button, count=count,
                                        delivery_mode=delivery_mode, window_id=window_id)

    async def double_click(self, x: int, y: int, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.click(x, y, count=2, delivery_mode=delivery_mode, window_id=window_id)

    async def right_click(self, x: int, y: int, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.click(x, y, button="right", delivery_mode=delivery_mode, window_id=window_id)

    async def middle_click(self, x: int, y: int, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.click(x, y, button="middle", delivery_mode=delivery_mode, window_id=window_id)

    async def mouse_down(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "foreground") -> Any:
        return await self._driver.mouse_down(int(x), int(y), button=button, delivery_mode=delivery_mode)

    async def mouse_up(self, x: int, y: int, *, button: str = "left", delivery_mode: str = "foreground") -> Any:
        return await self._driver.mouse_up(int(x), int(y), button=button, delivery_mode=delivery_mode)

    async def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left", delivery_mode: str = "foreground") -> Any:
        return await self._driver.drag(int(x1), int(y1), int(x2), int(y2), button=button, delivery_mode=delivery_mode)

    async def scroll(self, *, dx: int = 0, dy: int = 0, at: Optional[tuple[int, int]] = None, delivery_mode: str = "foreground") -> Any:
        return await self._driver.scroll(dx=int(dx), dy=int(dy), at=at, delivery_mode=delivery_mode)

    async def scroll_horizontal(self, dx: int, *, at: Optional[tuple[int, int]] = None, delivery_mode: str = "foreground") -> Any:
        return await self.scroll(dx=dx, dy=0, at=at, delivery_mode=delivery_mode)

    async def move_relative(self, dx: int, dy: int, *, delivery_mode: str = "background") -> Any:
        current = self._driver.pointer_position()
        if current is None:
            raise ActionFailed("Eclipse couldn't read the current pointer position.")
        return await self.move(current[0] + int(dx), current[1] + int(dy), delivery_mode=delivery_mode)

    async def click_relative(self, dx: int, dy: int, *, button: str = "left", delivery_mode: str = "background") -> Any:
        current = self._driver.pointer_position()
        if current is None:
            raise ActionFailed("Eclipse couldn't read the current pointer position.")
        return await self.click(current[0] + int(dx), current[1] + int(dy), button=button, delivery_mode=delivery_mode)

    def position(self) -> Optional[Point]:
        pos = self._driver.pointer_position()
        return Point(*pos) if pos else None


def point_of(bounds: Optional[Bounds]) -> Optional[tuple[int, int]]:
    return bounds.center if bounds else None


__all__ = ["MouseEngine", "point_of"]
