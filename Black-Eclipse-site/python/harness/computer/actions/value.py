"""The semantic `set_value` action.

Instead of "click dropdown → wait → find option → click option", the agent says
`set_value(element=5, value="Market")`. The setter tries, in order:

  1. the driver's native set_value (e.g. WM_SETTEXT on a real control),
  2. a keyboard-driven set (focus the field, select-all, type, Enter) — the
     universal fallback.

For a dropdown it also detects a combo/list role and drives the selection by
typing the first characters + Enter, which is how native combo boxes behave.
The caller verifies the effect afterwards.
"""

from __future__ import annotations

from typing import Any, Optional

from ..errors import ActionFailed, UnsupportedAction
from ..models import Bounds, SnapshotElement


class ValueSetter:
    def __init__(self, *, driver: Any, keyboard: Any, mouse: Any) -> None:
        self._driver = driver
        self._keyboard = keyboard
        self._mouse = mouse

    async def set_value(
        self,
        *,
        bounds: Optional[Bounds],
        value: str,
        role: str = "",
        window_id: Optional[str] = None,
        delivery_mode: str = "background",
    ) -> dict[str, Any]:
        methods_tried: list[str] = []

        # 1. Native control set.
        if bounds is not None:
            try:
                native = await self._driver.set_value(bounds, str(value), window_id=window_id)
                methods_tried.append("driver.set_value")
                if native.get("set"):
                    return {"set": True, "method": "native", "value": str(value), "methodsTried": methods_tried}
            except UnsupportedAction:
                pass
            except Exception:  # noqa: BLE001
                pass

        # 2. Keyboard-driven set. Click to focus, clear, type, commit.
        if bounds is None:
            raise ActionFailed("Eclipse needs a target to set a value.")
        x, y = bounds.center
        await self._mouse.click(x, y, delivery_mode=delivery_mode, window_id=window_id)
        methods_tried.append("click+type")
        await self._keyboard.select_all(delivery_mode=delivery_mode, window_id=window_id)
        await self._keyboard.type_text(str(value), delivery_mode=delivery_mode, window_id=window_id)
        # Combo/list controls commit with Enter; a plain text field ignores it.
        lowered_role = (role or "").lower()
        if lowered_role in ("combobox", "combo box", "listbox", "list", "dropdown"):
            await self._keyboard.press("enter", delivery_mode=delivery_mode, window_id=window_id)
            methods_tried.append("enter")
        return {"set": True, "method": "keyboard", "value": str(value), "methodsTried": methods_tried}


__all__ = ["ValueSetter"]
