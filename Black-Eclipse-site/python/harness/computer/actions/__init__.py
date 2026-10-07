"""Action engines — mouse, keyboard and the semantic value setter.

    keymap.py    semantic shortcut + virtual-key normalization (pure)
    mouse.py     mouse_move/click/double/right/middle/down/up/drag/scroll
    keyboard.py  type/press/hotkey/copy/paste/cut/select_all/escape/clear
    value.py     set_value (dropdown/select/slider/native value controls)

Every engine takes the resolved `Bounds`/point and a `delivery_mode`, delegates
to the driver, and returns a structured result. The foreground/background
escalation and the verification live in the session/core, not here.
"""

from __future__ import annotations

from .keyboard import KeyboardEngine
from .mouse import MouseEngine
from .value import ValueSetter

__all__ = ["KeyboardEngine", "MouseEngine", "ValueSetter"]
