"""Boot wiring for the bot-team orchestration layer.

Called from the runtime lifespan, after the A2A and Task layers are installed, so
the team layer composes them rather than re-creating them. Best-effort: a team
layer that cannot be constructed never blocks boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.team.bootstrap")


def install_team_layer(service: Any) -> bool:
    """Construct + register the team layer on the service. Idempotent."""
    if getattr(service, "team", None) is not None:
        return True
    try:
        a2a = getattr(service, "a2a", None)
        if a2a is None:
            from ..a2a.bootstrap import install_a2a_layer  # noqa: PLC0415

            install_a2a_layer(service)
            a2a = getattr(service, "a2a", None)
        from .service import TeamService  # noqa: PLC0415

        service.team = TeamService(service, a2a=a2a)
        from .tools import register_team_tools  # noqa: PLC0415

        register_team_tools(service.registry)
        # The read-only prerequisite-memo tool belongs to the team layer (a desk
        # uses it with or without the Institution preset installed).
        from .tools import register_run_output_tool  # noqa: PLC0415

        register_run_output_tool(service.registry)
        return True
    except Exception:  # noqa: BLE001 - the team layer must never block boot
        log.warning("team layer unavailable", exc_info=True)
        service.team = None
        return False


__all__ = ["install_team_layer"]
