"""Process-wide execution service singleton (mirrors `terminal/runtime.py`).

The service is built once in `service.AgenticService.__init__` and installed here
so the tool handlers resolve the SAME orchestrator/scheduler/store the HTTP
surface uses. No second registry, no second execution path.
"""

from __future__ import annotations

from typing import Optional

_SERVICE: Optional[object] = None


def set_execution_service(service: Optional[object]) -> None:
    global _SERVICE
    _SERVICE = service


def get_execution_service() -> Optional[object]:
    return _SERVICE


__all__ = ["get_execution_service", "set_execution_service"]
