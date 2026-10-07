"""Adapter selection."""

from __future__ import annotations

from typing import Optional

from .adapters import ADAPTERS
from .base import ApplicationAdapter, GenericAdapter


class AdapterRegistry:
    def __init__(self, adapters: tuple[ApplicationAdapter, ...] = ADAPTERS) -> None:
        self._adapters = adapters
        self._generic = next((a for a in adapters if isinstance(a, GenericAdapter)), GenericAdapter())

    def select(self, *, app_name: str = "", executable: str = "", title: str = "") -> ApplicationAdapter:
        for adapter in self._adapters:
            if isinstance(adapter, GenericAdapter):
                continue
            if adapter.matches(app_name=app_name, executable=executable, title=title):
                return adapter
        return self._generic

    def for_app(self, app: dict) -> ApplicationAdapter:
        return self.select(
            app_name=str(app.get("name") or ""),
            executable=str(app.get("executable") or ""),
            title=str(app.get("title") or ""),
        )

    def by_id(self, adapter_id: str) -> Optional[ApplicationAdapter]:
        for adapter in self._adapters:
            if adapter.id == adapter_id:
                return adapter
        return None

    def describe(self) -> list[dict]:
        return [a.describe() for a in self._adapters]


def build_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry()


__all__ = ["AdapterRegistry", "build_adapter_registry"]
