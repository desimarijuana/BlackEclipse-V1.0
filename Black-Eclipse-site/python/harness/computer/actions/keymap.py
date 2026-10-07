"""Semantic key normalization.

The agent should be able to say `SAVE` or `press("ctrl+s")` without knowing the
platform. `normalize_combo` resolves a semantic shortcut to the modifier+key
combo for the CURRENT platform, and `virtual_key` maps a key name to a Windows
virtual-key code (the driver's concern). Both are pure and tested without an OS.
"""

from __future__ import annotations

import sys
from typing import Optional

# Canonical modifier names.
MODIFIERS = ("ctrl", "control", "alt", "shift", "win", "meta", "cmd", "command", "super")

_ALIASES: dict[str, str] = {
    "control": "ctrl",
    "cmd": "meta",
    "command": "meta",
    "super": "meta",
    "win": "meta",
    "windows": "meta",
    "escape": "esc",
    "return": "enter",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "spacebar": "space",
}

# A small semantic-shortcut table. Each entry names the action and the key; the
# modifier is resolved per platform. This is deliberately a CLOSED vocabulary so
# a misspelled shortcut is an honest error, not a silent wrong key.
SEMANTIC_SHORTCUTS: dict[str, dict[str, str]] = {
    "SAVE": {"key": "s"},
    "SAVE_AS": {"key": "s", "shift": "1"},
    "OPEN": {"key": "o"},
    "NEW": {"key": "n"},
    "FIND": {"key": "f"},
    "REPLACE": {"key": "h"},
    "PRINT": {"key": "p"},
    "UNDO": {"key": "z"},
    "REDO": {"key": "y"},
    "REDO_ALT": {"key": "z", "shift": "1"},
    "CUT": {"key": "x"},
    "COPY": {"key": "c"},
    "PASTE": {"key": "v"},
    "SELECT_ALL": {"key": "a"},
    "CLOSE": {"key": "w"},
    "QUIT": {"key": "q"},
    "REFRESH": {"key": "r"},
    "SETTINGS": {"key": ","},
    "FIND_NEXT": {"key": "g"},
    "RUN": {"key": "F5"},
    "SWITCH_APP": {"key": "tab"},
    "CLOSE_WINDOW": {"key": "F4"},
    "LOCK": {"key": "l"},
}


def _canonical_key(name: str) -> str:
    text = (name or "").strip()
    lowered = text.lower()
    return _ALIASES.get(lowered, lowered)


def normalize_combo(combo: str) -> str:
    """Normalize a combo string to `mod+mod+key` form (platform modifiers resolved).

    Accepts `ctrl+s`, `Control+S`, `cmd+shift+p`, `alt+F4`. A semantic shortcut
    name (`SAVE`) resolves through `SEMANTIC_SHORTCUTS` first. The primary
    modifier is `ctrl` on Windows/Linux and `meta` on macOS.
    """
    text = (combo or "").strip()
    if not text:
        return ""
    upper = text.upper().replace(" ", "_")
    if upper in SEMANTIC_SHORTCUTS:
        spec = SEMANTIC_SHORTCUTS[upper]
        primary = "meta" if sys.platform == "darwin" else "ctrl"
        parts = [primary]
        if spec.get("shift"):
            parts.append("shift")
        if spec.get("alt"):
            parts.append("alt")
        parts.append(_canonical_key(spec["key"]))
        # De-dup modifiers, preserve order.
        seen: list[str] = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        return "+".join(seen)
    parts = [_canonical_key(p) for p in text.replace(" ", "").split("+") if p]
    return "+".join(parts)


_PRIMARY = "meta" if sys.platform == "darwin" else "ctrl"


def resolve_modifier_token(token: str) -> str:
    """Map the platform-primary modifier token to `ctrl`/`meta` as appropriate."""
    if token == "primary":
        return _PRIMARY
    return token


# Windows virtual-key codes for the keys the engine can press. Kept here so the
# keymap is one place; the driver imports it.
WIN_VK: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "insert": 0x2D, "delete": 0x2E,
    "meta": 0x5B, "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "numlock": 0x90, "scrolllock": 0x91,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    WIN_VK[_c] = ord(_c.upper())
for _d in "0123456789":
    WIN_VK[_d] = ord(_d)


def virtual_key(name: str) -> Optional[int]:
    """The Windows virtual-key code for a key name, or None if unknown."""
    key = _canonical_key(name)
    if len(key) == 1 and key.isupper():
        key = key.lower()
    return WIN_VK.get(key)


__all__ = [
    "MODIFIERS",
    "SEMANTIC_SHORTCUTS",
    "WIN_VK",
    "normalize_combo",
    "resolve_modifier_token",
    "virtual_key",
]
