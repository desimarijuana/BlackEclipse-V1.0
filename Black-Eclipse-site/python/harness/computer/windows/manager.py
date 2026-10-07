"""The window manager.

List/get/focus/activate/minimize/maximize/restore/move/resize/close and the
visibility predicates. Window targeting is EXACT: a title match is explicit
about whether it is a substring or exact, and an ambiguous title match is
reported (so the agent can disambiguate) rather than silently choosing one.
"""

from __future__ import annotations

from typing import Any, Optional

from ..errors import WindowNotFound
from ..models import WindowInfo


class WindowManager:
    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def list(self) -> list[WindowInfo]:
        return self._driver.list_windows()

    def find(
        self,
        *,
        window_id: Optional[str] = None,
        title: Optional[str] = None,
        app: Optional[str] = None,
        pid: Optional[int] = None,
        exact: bool = False,
        focused: Optional[bool] = None,
    ) -> list[WindowInfo]:
        windows = self.list()
        if window_id:
            windows = [w for w in windows if w.id == str(window_id)]
        if title:
            needle = title if exact else title.lower()
            windows = [w for w in windows if (w.title == needle if exact else needle in w.title.lower())]
        if app:
            needle = app.lower()
            windows = [w for w in windows if needle in (w.app or "").lower()]
        if pid is not None:
            windows = [w for w in windows if w.pid == int(pid)]
        if focused is not None:
            windows = [w for w in windows if w.focused == focused]
        return windows

    def require(self, window_id: str) -> WindowInfo:
        window = self._driver.get_window(window_id)
        if window is None:
            raise WindowNotFound(f"Window {window_id!r} is not open.", window=window_id)
        return window

    def resolve_target(
        self,
        *,
        window_id: Optional[str] = None,
        title: Optional[str] = None,
        app: Optional[str] = None,
        focused_first: bool = True,
    ) -> WindowInfo:
        """Resolve exactly one window or raise (not found / ambiguous)."""
        matches = self.find(window_id=window_id, title=title, app=app)
        if not matches:
            raise WindowNotFound(
                "Eclipse couldn't find a window matching that description.",
                window=window_id or title or app,
            )
        if len(matches) > 1:
            focused = [w for w in matches if w.focused]
            if focused_first and len(focused) == 1:
                return focused[0]
            if focused_first and len(focused) > 1:
                matches = focused
            if len(matches) > 1:
                from ..errors import AmbiguousTarget  # noqa: PLC0415

                raise AmbiguousTarget(
                    "More than one window matches; specify the window id.",
                    metadata={"candidates": [{"id": w.id, "title": w.title, "app": w.app} for w in matches[:8]]},
                )
        return matches[0]

    async def focus(self, window_id: str, *, foreground: bool = False) -> dict[str, Any]:
        result = await self._driver.focus_window(window_id, foreground=foreground)
        return {"windowId": window_id, **result.to_dict()}

    async def activate(self, window_id: str, *, foreground: bool = True) -> dict[str, Any]:
        return await self.focus(window_id, foreground=foreground)

    async def minimize(self, window_id: str) -> dict[str, Any]:
        return await self._driver.window_control(window_id, "minimize")

    async def maximize(self, window_id: str) -> dict[str, Any]:
        return await self._driver.window_control(window_id, "maximize")

    async def restore(self, window_id: str) -> dict[str, Any]:
        return await self._driver.window_control(window_id, "restore")

    async def move(self, window_id: str, *, x: int, y: int, width: Optional[int] = None, height: Optional[int] = None) -> dict[str, Any]:
        return await self._driver.window_control(window_id, "move", x=x, y=y, width=width or 0, height=height or 0)

    async def resize(self, window_id: str, *, width: int, height: int) -> dict[str, Any]:
        window = self.require(window_id)
        return await self._driver.window_control(window_id, "move", x=window.bounds.x, y=window.bounds.y, width=width, height=height)

    async def close(self, window_id: str) -> dict[str, Any]:
        return await self._driver.window_control(window_id, "close")

    def is_visible(self, window_id: str) -> bool:
        window = self._driver.get_window(window_id)
        return bool(window and window.visible)

    def is_minimized(self, window_id: str) -> bool:
        window = self._driver.get_window(window_id)
        return bool(window and window.minimized)

    def is_maximized(self, window_id: str) -> bool:
        window = self._driver.get_window(window_id)
        return bool(window and window.maximized)


__all__ = ["WindowManager"]
