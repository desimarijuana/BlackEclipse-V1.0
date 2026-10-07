"""The keyboard toolset.

Type, press a single key, send a hotkey combo, key down/up, and the semantic
editing verbs (copy/paste/cut/select-all/escape/clear). Shortcut combos are
normalized to the current platform via `keymap.normalize_combo`, so the agent can
say `SAVE` or `ctrl+s` and Eclipse resolves `Cmd+S` on macOS.
"""

from __future__ import annotations

from typing import Any, Optional

from ..errors import ActionFailed
from .keymap import normalize_combo


class KeyboardEngine:
    def __init__(self, driver: Any) -> None:
        self._driver = driver

    async def type_text(self, text: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self._driver.type_text(str(text), delivery_mode=delivery_mode, window_id=window_id)

    async def press(self, key: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        keys = [k for k in normalize_combo(key).split("+") if k]
        if not keys:
            raise ActionFailed(f"Eclipse doesn't recognise the key {key!r}.")
        return await self._driver.key(keys, delivery_mode=delivery_mode, window_id=window_id)

    async def hotkey(self, combo: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        normalized = normalize_combo(combo)
        keys = [k for k in normalized.split("+") if k]
        if not keys:
            raise ActionFailed(f"Eclipse doesn't recognise the shortcut {combo!r}.")
        return await self._driver.key(keys, delivery_mode=delivery_mode, window_id=window_id)

    async def key_down(self, key: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        key = normalize_combo(key).split("+")[0]
        # A held key is best-effort: most toolkits only observe a press+release.
        return await self._driver.key([key], delivery_mode=delivery_mode, window_id=window_id)

    async def key_up(self, key: str, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        key = normalize_combo(key).split("+")[0]
        return await self._driver.key([key], delivery_mode=delivery_mode, window_id=window_id)

    async def copy(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.hotkey("COPY", delivery_mode=delivery_mode, window_id=window_id)

    async def paste(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.hotkey("PASTE", delivery_mode=delivery_mode, window_id=window_id)

    async def cut(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.hotkey("CUT", delivery_mode=delivery_mode, window_id=window_id)

    async def select_all(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.hotkey("SELECT_ALL", delivery_mode=delivery_mode, window_id=window_id)

    async def escape(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        return await self.press("esc", delivery_mode=delivery_mode, window_id=window_id)

    async def clear(self, *, delivery_mode: str = "background", window_id: Optional[str] = None) -> Any:
        await self.select_all(delivery_mode=delivery_mode, window_id=window_id)
        return await self.press("delete", delivery_mode=delivery_mode, window_id=window_id)


__all__ = ["KeyboardEngine"]
