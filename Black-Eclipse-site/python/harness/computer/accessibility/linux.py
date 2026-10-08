"""The Linux accessibility provider.

Tier 1 is **AT-SPI** (the GNOME accessibility bus) via the optional `pyatspi`
package (part of `python3-pyatspi`). It yields a real semantic tree for GTK/Qt
applications. There is no always-available baseline analogous to the Win32 child
enumeration on Linux, so when AT-SPI is absent the provider is the honest null —
never a fabricated tree.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from ..models import AXNode, Bounds
from .base import AXProvider, looks_interactive
from .null import NullAXProvider

_IS_LINUX = sys.platform.startswith("linux")


class ATSPIAXProvider(AXProvider):
    id = "atspi"
    available = False

    def __init__(self) -> None:
        self.reason = ""
        if not _IS_LINUX:
            self.reason = "AT-SPI is only available on Linux"
            return
        try:
            import pyatspi  # noqa: F401, PLC0415

            self._pyatspi = pyatspi
            self.available = True
        except Exception:  # noqa: BLE001
            self.reason = "AT-SPI isn't installed (install python3-pyatspi)"

    def tree(self, window_id: Optional[str] = None) -> Optional[AXNode]:
        if not self.available:
            return None
        try:
            desktop = self._pyatspi.Registry.getDesktop(0)
        except Exception:  # noqa: BLE001
            return None
        target = None
        try:
            for app in desktop:
                for frame in app:
                    if window_id and str(getattr(frame, "name", "")) == str(window_id):
                        target = frame
                        break
                if target is not None:
                    break
            if target is None and len(desktop) and len(desktop[0]):
                target = desktop[0][0]
        except Exception:  # noqa: BLE001
            return None
        if target is None:
            return None
        root = AXNode(role="window", name=str(getattr(target, "name", "")), bounds=Bounds())
        self._walk(target, root, depth=0)
        return root

    def _walk(self, node: Any, parent: AXNode, *, depth: int) -> None:
        if depth > 12:
            return
        try:
            children = list(node)
        except Exception:  # noqa: BLE001 - a leaf has no children
            return
        for child in children:
            role = str(getattr(child, "getRoleName", lambda: "")()).lower()
            name = str(getattr(child, "name", "") or "")
            if not name and role not in ("push button", "text", "entry"):
                # Keep walking; a container may still hold named controls.
                wrapper = AXNode(role=role, name="", bounds=Bounds())
                self._walk(child, wrapper, depth=depth + 1)
                if wrapper.children:
                    parent.children.append(wrapper)
                continue
            bounds = Bounds()
            try:
                extents = child.queryComponent().getExtents(0)  # CoordType.SCREEN
                bounds = Bounds(extents.x, extents.y, extents.width, extents.height)
            except Exception:  # noqa: BLE001
                bounds = Bounds()
            role_name = {"push button": "button", "entry": "textbox", "text": "text"}.get(role, role or "element")
            ax = AXNode(role=role_name, name=name, bounds=bounds,
                        interactive=looks_interactive(role_name))
            parent.children.append(ax)
            self._walk(child, ax, depth=depth + 1)

    def describe(self) -> dict[str, Any]:
        return {"provider": "atspi", "available": self.available,
                **({} if self.available else {"reason": self.reason})}


def build_ax_provider() -> AXProvider:
    provider = ATSPIAXProvider()
    if provider.available:
        return provider
    return NullAXProvider(provider.reason)


__all__ = ["ATSPIAXProvider", "build_ax_provider"]
