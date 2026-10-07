"""Computer Use telemetry.

Bounded, in-process counters for the metrics the design calls for: actions,
success/failure/recovery rate, grounding confidence, verification confidence,
latency (driver/vision/OCR), vision calls, foreground escalations, approval
requests. Exposed to the harness bus as events and readable as a snapshot.

Counter-only and bounded; it is observability, never a second state store.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _LatencyStat:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "avgMs": round(self.total_ms / self.count, 1) if self.count else 0.0,
            "maxMs": round(self.max_ms, 1),
        }


class ComputerTelemetry:
    def __init__(self, *, bus: Any = None) -> None:
        self.bus = bus
        self.started_at = time.time()
        self.actions = 0
        self.successes = 0
        self.failures = 0
        self.recoveries = 0
        self.recovery_attempts = 0
        self.foreground_escalations = 0
        self.approval_requests = 0
        self.vision_calls = 0
        self.ocr_calls = 0
        self.grounding_scores: list[float] = []
        self.verification_scores: list[float] = []
        self.driver_latency = _LatencyStat()
        self.vision_latency = _LatencyStat()
        self.ocr_latency = _LatencyStat()
        self.tokens_by_action: dict[str, int] = {}

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.bus is None:
            return
        try:
            from ..persistence import now_iso  # noqa: PLC0415

            self.bus.publish({
                "id": f"computer_{event_type}_{now_iso()}", "runId": None,
                "type": event_type, "seq": 0, "at": now_iso(), "data": data,
            })
        except Exception:  # noqa: BLE001 - observability must never break a run
            pass

    def record_action(self, *, action: str, success: bool, duration_ms: float, verdict: str = "") -> None:
        self.actions += 1
        self.driver_latency.add(duration_ms)
        if success:
            self.successes += 1
        else:
            self.failures += 1
        self._emit("computer.action", {"action": action, "success": success, "verdict": verdict, "durationMs": int(duration_ms)})

    def record_grounding(self, score: float) -> None:
        self.grounding_scores.append(score)
        if len(self.grounding_scores) > 500:
            del self.grounding_scores[0]

    def record_verification(self, score: float) -> None:
        self.verification_scores.append(score)
        if len(self.verification_scores) > 500:
            del self.verification_scores[0]

    def record_recovery(self, *, attempts: int, recovered: bool) -> None:
        self.recovery_attempts += attempts
        if recovered:
            self.recoveries += 1
        self._emit("computer.recovery", {"attempts": attempts, "recovered": recovered})

    def record_foreground(self) -> None:
        self.foreground_escalations += 1
        self._emit("computer.foreground", {"escalated": True})

    def record_approval_request(self) -> None:
        self.approval_requests += 1

    def record_vision(self, *, duration_ms: float, tokens: int = 0) -> None:
        self.vision_calls += 1
        self.vision_latency.add(duration_ms)
        self.tokens_by_action["vision"] = self.tokens_by_action.get("vision", 0) + tokens

    def record_ocr(self, *, duration_ms: float) -> None:
        self.ocr_calls += 1
        self.ocr_latency.add(duration_ms)

    def snapshot(self) -> dict[str, Any]:
        denom = self.actions or 1
        recov_denom = self.recovery_attempts or 1
        return {
            "uptimeS": round(time.time() - self.started_at, 1),
            "actions": self.actions,
            "successes": self.successes,
            "failures": self.failures,
            "successRate": round(self.successes / denom, 3),
            "failureRate": round(self.failures / denom, 3),
            "recoveries": self.recoveries,
            "recoveryRate": round(self.recoveries / recov_denom, 3),
            "foregroundEscalations": self.foreground_escalations,
            "approvalRequests": self.approval_requests,
            "visionCalls": self.vision_calls,
            "ocrCalls": self.ocr_calls,
            "avgGroundingConfidence": round(sum(self.grounding_scores) / len(self.grounding_scores), 3) if self.grounding_scores else 0.0,
            "avgVerificationConfidence": round(sum(self.verification_scores) / len(self.verification_scores), 3) if self.verification_scores else 0.0,
            "driverLatency": self.driver_latency.to_dict(),
            "visionLatency": self.vision_latency.to_dict(),
            "ocrLatency": self.ocr_latency.to_dict(),
            "tokensByAction": dict(self.tokens_by_action),
        }


__all__ = ["ComputerTelemetry"]
