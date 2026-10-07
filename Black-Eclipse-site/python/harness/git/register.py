"""One registration seam for the whole Git / Version-Control subsystem.

`register_code_tools` calls `register_git_subsystem` so `code/tools.py` stays
under its size ratchet. Local Git tools (`git.tools`) and the remote provider
tools (`git.vcs_tools`) both register on the SAME `ToolRegistry`; the ONE policy
authority (`code.policy.allowed_tools`) narrows them by autonomy, and the Git
effect authorizer gates every dangerous and remote action.
"""

from __future__ import annotations

from ..tools import ToolRegistry


def register_git_subsystem(registry: ToolRegistry) -> list[str]:
    """Register local Git tools + remote VCS provider tools. Returns the names."""
    from .tools import register_git_tools
    from .tools_extra import register_extra_git_tools
    from .vcs_tools import register_vcs_tools

    return [
        *register_git_tools(registry),
        *register_extra_git_tools(registry),
        *register_vcs_tools(registry),
    ]


__all__ = ["register_git_subsystem"]
