"""Document format adapters.

Each adapter turns raw bytes into a `DocumentIR`. `registry.get_adapter(kind)`
selects one; the orchestrator never switches on a format directly.
"""

from __future__ import annotations

from ..base import Capabilities, DocumentAdapter, ParseContext
from .registry import all_adapters, get_adapter, known_kinds

__all__ = [
    "Capabilities", "DocumentAdapter", "ParseContext",
    "get_adapter", "known_kinds", "all_adapters",
]
