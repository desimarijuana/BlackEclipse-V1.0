"""Decision layer boot wiring.

Constructs the ONE decision service (registry + policy + audit store) and
registers its tools on the SAME registry, reusing the ONE agent-memory
connection. Imported and called once from `AgenticService.__init__`, mirroring
the advisory layer.

Best-effort: a failure leaves typed decisions unavailable rather than blocking
boot. It NEVER registers a remote provider implicitly; Phase 1 adds the TypeSafe
adapter behind explicit operator configuration.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.decisions")


def install_decision_layer(service: Any) -> None:
    try:
        from .service import DecisionService
        from .tools import register_decision_tools

        decisions = DecisionService(service.store)
        service.decision = decisions
        register_decision_tools(service.registry)
    except Exception:  # noqa: BLE001 - decisions must never block boot
        service.decision = None
        log.warning("decision layer unavailable", exc_info=True)


__all__ = ["install_decision_layer"]
