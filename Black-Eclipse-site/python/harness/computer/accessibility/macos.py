"""The macOS accessibility provider.

Uses the Application Services AX API (`AXUIElement`) via `ctypes`. macOS gates it
behind the Accessibility TCC permission; without it `AXIsProcessTrusted` is false
and the provider is the honest null. No third-party package is required.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import c_void_p
from typing import Any, Optional

from ..models import AXNode, Bounds
from .base import AXProvider, looks_interactive
from .null import NullAXProvider

_IS_MAC = sys.platform == "darwin"

# AX role → the portable role vocabulary used across platforms.
_ROLE_MAP = {
    "AXButton": "button", "AXTextField": "textbox", "AXTextArea": "textbox",
    "AXStaticText": "text", "AXCheckBox": "checkbox", "AXRadioButton": "radio",
    "AXComboBox": "combobox", "AXPopUpButton": "combobox", "AXMenuButton": "button",
    "AXMenuItem": "menuitem", "AXMenuBar": "menubar", "AXList": "list",
    "AXOutline": "tree", "AXRow": "listitem", "AXCell": "cell", "AXTable": "datagrid",
    "AXSlider": "slider", "AXTabGroup": "tab", "AXRadioGroup": "radiogroup",
    "AXWindow": "window", "AXSheet": "dialog", "AXScrollArea": "pane",
    "AXGroup": "group", "AXLink": "link", "AXImage": "image", "AXWebArea": "document",
}


class MacAXProvider(AXProvider):
    id = "mac_ax"
    available = False

    def __init__(self) -> None:
        self.reason = ""
        if not _IS_MAC:
            self.reason = "the AX API is only available on macOS"
            return
        try:
            self._as = ctypes.CDLL(ctypes.util.find_library("ApplicationServices") or "ApplicationServices")
            self._cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation") or "CoreFoundation")
        except Exception:  # noqa: BLE001
            self.reason = "the Application Services framework couldn't be loaded"
            return
        try:
            if not self._as.AXIsProcessTrusted():
                self.reason = "Accessibility permission is not granted (System Settings → Privacy & Security → Accessibility)"
                return
            self.available = True
        except Exception as exc:  # noqa: BLE001
            self.reason = f"the AX API couldn't be queried ({str(exc)[:100]})"

    def tree(self, window_id: Optional[str] = None) -> Optional[AXNode]:
        if not self.available:
            return None
        try:
            app = self._as.AXUIElementCreateApplication(int(window_id) if window_id else _current_pid(self._as))
            if not app:
                return None
            root = AXNode(role="window", name="", bounds=Bounds())
            self._copy_attributes(app, root)
            self._walk(app, root, depth=0)
            return root
        except Exception:  # noqa: BLE001
            return None

    def _attr(self, element: Any, name: str) -> Any:
        cf_name = self._cf.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        value = c_void_p(0)
        try:
            if self._as.AXUIElementCopyAttributeValue(element, cf_name, ctypes.byref(value)) == 0:
                return value
        finally:
            self._cf.CFRelease(cf_name)
        return None

    def _string(self, element: Any, name: str) -> str:
        value = self._attr(element, name)
        if not value:
            return ""
        try:
            self._cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
            ptr = self._cf.CFStringGetCStringPtr(value, 0x08000100)
            if ptr:
                return ptr.decode("utf-8", "replace")
            buf = ctypes.create_string_buffer(2048)
            if self._cf.CFStringGetCString(value, buf, 2048, 0x08000100):
                return buf.value.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._cf.CFRelease(value)
        return ""

    def _children(self, element: Any) -> list[Any]:
        value = self._attr(element, "AXChildren")
        if not value:
            return []
        out: list[Any] = []
        try:
            count = self._cf.CFArrayGetCount(value)
            for i in range(count):
                child = self._cf.CFArrayGetValueAtIndex(value, i)
                if child:
                    self._cf.CFRetain(child)
                    out.append(child)
        except Exception:  # noqa: BLE001
            out = []
        finally:
            self._cf.CFRelease(value)
        return out

    def _copy_attributes(self, element: Any, node: AXNode) -> None:
        role_raw = self._string(element, "AXRole")
        node.role = _ROLE_MAP.get(role_raw, (role_raw.replace("AX", "").lower() or "element"))
        node.name = self._string(element, "AXTitle") or self._string(element, "AXDescription") or self._string(element, "AXValue")
        node.interactive = looks_interactive(node.role)

    def _walk(self, element: Any, parent: AXNode, *, depth: int) -> None:
        if depth > 12:
            return
        for child in self._children(element):
            node = AXNode(role="element", name="", bounds=Bounds())
            self._copy_attributes(child, node)
            if node.name or node.interactive:
                parent.children.append(node)
            self._walk(child, node, depth=depth + 1)
            self._cf.CFRelease(child)

    def describe(self) -> dict[str, Any]:
        return {"provider": "mac_ax", "available": self.available,
                **({} if self.available else {"reason": self.reason})}


def _current_pid(ax: Any) -> int:
    import os  # noqa: PLC0415

    return os.getpid()


def build_ax_provider() -> AXProvider:
    provider = MacAXProvider()
    if provider.available:
        return provider
    return NullAXProvider(provider.reason)


__all__ = ["MacAXProvider", "build_ax_provider"]
