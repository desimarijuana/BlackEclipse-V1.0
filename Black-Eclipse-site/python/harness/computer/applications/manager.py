"""Application management.

List, launch, close, restart, is_running and get_info. Launching an application
is a real local mutation (it opens a program), so the tool layer gates it; this
manager only performs the mechanic and avoids launching duplicate instances when
the caller asks for `if_not_running`.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..errors import ApplicationNotFound
from ..models import ApplicationInfo


class ApplicationManager:
    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def list(self) -> list[ApplicationInfo]:
        return self._driver.list_applications()

    def find(self, query: str, *, exact: bool = False) -> list[ApplicationInfo]:
        needle = query if exact else query.lower()
        out: list[ApplicationInfo] = []
        for app in self.list():
            name = app.name if exact else app.name.lower()
            exe = app.executable if exact else app.executable.lower()
            if needle == name or (not exact and needle in name) or (needle in exe):
                out.append(app)
        return out

    def require(self, query: str) -> ApplicationInfo:
        matches = self.find(query)
        if not matches:
            raise ApplicationNotFound(f"{query!r} isn't running.", metadata={"query": query})
        return matches[0]

    def is_running(self, query: str) -> bool:
        return bool(self.find(query))

    async def launch(self, target: str, *, args: Optional[list[str]] = None, if_not_running: bool = False) -> ApplicationInfo:
        if if_not_running:
            existing = self.find(os.path.basename(target))
            if existing:
                return existing[0]
        return await self._driver.launch_application(target, args=args)

    async def close(self, app_id: str) -> dict[str, Any]:
        return await self._driver.close_application(app_id)

    async def restart(self, target: str, *, args: Optional[list[str]] = None, close_first: bool = False) -> ApplicationInfo:
        if close_first:
            matches = self.find(os.path.basename(target))
            for app in matches:
                try:
                    await self.close(app.id)
                except Exception:  # noqa: BLE001 - best-effort close
                    pass
        return await self.launch(target, args=args)

    def get_info(self, query: str) -> ApplicationInfo:
        return self.require(query)


__all__ = ["ApplicationManager"]
