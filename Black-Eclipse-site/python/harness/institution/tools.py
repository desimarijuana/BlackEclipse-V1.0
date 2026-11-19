"""The Institution preset's view of the team hand-off tool.

`read_run_output` now lives with the team layer (`team/tools.py`) because a desk
uses it with or without the Institution preset installed. This module keeps the
old import path working for the preset bootstrap and its tests; it adds nothing.
"""

from __future__ import annotations

from ..team.tools import read_run_output, register_run_output_tool
from ..tools import ToolRegistry

TOOL_NAMES: tuple[str, ...] = ("read_run_output",)


def register_institution_tools(registry: ToolRegistry) -> list[str]:
    """Register `read_run_output` (idempotent; owned by the team layer)."""
    return register_run_output_tool(registry)


__all__ = ["TOOL_NAMES", "read_run_output", "register_institution_tools"]
