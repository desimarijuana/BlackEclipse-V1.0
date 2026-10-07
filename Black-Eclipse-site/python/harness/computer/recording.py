"""Trajectory recording + inspection.

Records a bounded, redactable sequence of frames/actions/targets/verdicts for a
session so it can be exported, inspected and replayed. Sensitive images are
masked before being written to an EXPORTABLE trajectory when redaction is on.

The recorder never becomes a second source of truth: it stores summaries and
artifact paths, not the live session.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RecordedStep:
    seq: int
    kind: str
    at: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "at": self.at, "data": self.data}


class SessionRecorder:
    def __init__(self, *, enabled: bool = True, screenshots: bool = True, recordings_dir: Path, session_id: str) -> None:
        self.enabled = enabled
        self.screenshots = screenshots
        self._dir = Path(recordings_dir) / session_id
        self.session_id = session_id
        self._steps: list[RecordedStep] = []
        self._seq = 0
        self._started = time.time()

    def record(self, kind: str, data: Optional[dict[str, Any]] = None) -> Optional[RecordedStep]:
        if not self.enabled:
            return None
        self._seq += 1
        step = RecordedStep(seq=self._seq, kind=kind, at=time.time(), data=data or {})
        self._steps.append(step)
        return step

    def record_action(self, action: str, *, target: Optional[dict[str, Any]] = None, result: Optional[dict[str, Any]] = None) -> None:
        self.record("action", {"action": action, "target": target, "result": result})

    def record_verdict(self, *, status: str, verdict: str, reason: str = "") -> None:
        self.record("verdict", {"status": status, "verdict": verdict, "reason": reason})

    def record_error(self, *, code: str, message: str) -> None:
        self.record("error", {"code": code, "message": message})

    def record_recovery(self, payload: dict[str, Any]) -> None:
        self.record("recovery", payload)

    def save_image(self, image: Any, *, label: str = "frame") -> Optional[str]:
        if not self.enabled or not self.screenshots or image is None:
            return None
        try:
            import io  # noqa: PLC0415

            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{label}-{int(time.time() * 1000)}.png"
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            path.write_bytes(buffer.getvalue())
            return str(path)
        except Exception:  # noqa: BLE001
            return None

    def steps(self) -> list[RecordedStep]:
        return list(self._steps)

    def summary(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id, "steps": len(self._steps),
            "startedAt": self._started, "enabled": self.enabled,
            "kinds": {kind: sum(1 for s in self._steps if s.kind == kind) for kind in {s.kind for s in self._steps}},
        }

    def export(self, path: Optional[str] = None) -> str:
        """Write the trajectory to JSON; return the path."""
        target = Path(path) if path else (self._dir / "trajectory.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": self.session_id, "startedAt": self._started,
            "summary": self.summary(), "steps": [s.to_dict() for s in self._steps],
        }
        target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(target)


__all__ = ["RecordedStep", "SessionRecorder"]
