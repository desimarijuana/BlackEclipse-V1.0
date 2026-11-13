"""Small bridge for subsystems that own no `RunEmitter`.

Some W5/W7 seams persist their own durable event record but do not publish on
`service.bus` (skill evaluation, curator runs, the shadow-git checkpoint store).
They still owe W8 a telemetry signal. `publish()` hands the event to the SAME
`RunEventProjector` the bus uses — it is not a second bus, and it never raises.

The durable record remains the subsystem's own store; this bridge only feeds the
observability projection.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional


def publish(
    event_type: str,
    data: Optional[dict[str, Any]] = None,
    *,
    run_id: str = "",
    transient: bool = True,
) -> bool:
    """Project one telemetry event. Returns True when a projector accepted it."""
    try:
        from . import get_hub  # noqa: PLC0415 - lazy: avoids importing the runtime

        hub = get_hub()
        projector = getattr(hub, "_projector", None)
        if projector is None:
            return False
        payload = {
            "id": f"evt_{event_type.replace('.', '_')}_{uuid.uuid4().hex[:10]}",
            "type": event_type,
            "at": time.time(),
            "transient": bool(transient),
            "data": dict(data or {}),
        }
        if run_id:
            payload["runId"] = run_id
        projector.handle(payload)
        return True
    except Exception:  # noqa: BLE001 - telemetry must never break the caller
        return False


__all__ = ["publish"]
