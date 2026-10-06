"""The filesystem operation context — workspace + actor + permission config.

Every operation in `code/fs/operations.py` takes one of these. It bundles the
resolved workspace, the policy binding, the actor (whose autonomy profile is the
base grant), the operator's narrowing config and the dry-run flag. Nothing else
is threaded through the operations, so permission checks stay centralized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..workspace import ResolvedWorkspace
from . import permissions


@dataclass
class FsContext:
    ws: ResolvedWorkspace
    binding: Any                    # policy.WorkspaceBinding
    actor: Any                      # skills.permissions.Actor (workspace-bound)
    config: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False

    def require(self, capability: str, rel_path: str = "") -> None:
        permissions.require(
            self.actor, self.binding, capability, rel_path, config=self.config,
        )


__all__ = ["FsContext"]
