"""Event System configuration (env-driven, matching the harness conventions).

Every value has a safe default so zero-config keeps working. Non-numeric or
out-of-range values fall back to the default rather than crashing boot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "enable", "enabled")


def _int(name: str, default: int, *, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(low, min(high, value))


@dataclass(frozen=True)
class EventConfig:
    bus_enabled: bool = True
    store_enabled: bool = True
    deduplication_enabled: bool = True
    replay_enabled: bool = True
    max_concurrency: int = 16
    max_retries: int = 5
    retention_days: int = 30
    max_queue: int = 1000
    echo_legacy: bool = True

    @classmethod
    def from_env(cls) -> "EventConfig":
        return cls(
            bus_enabled=_flag("EVENT_BUS_ENABLED", True),
            store_enabled=_flag("EVENT_STORE_ENABLED", True),
            deduplication_enabled=_flag("EVENT_DEDUPLICATION_ENABLED", True),
            replay_enabled=_flag("EVENT_REPLAY_ENABLED", True),
            max_concurrency=_int("EVENT_MAX_CONCURRENCY", 16, low=1, high=256),
            max_retries=_int("EVENT_MAX_RETRIES", 5, low=0, high=20),
            retention_days=_int("EVENT_RETENTION", 30, low=1, high=3650),
            max_queue=_int("EVENT_MAX_QUEUE", 1000, low=1, high=100_000),
            echo_legacy=_flag("EVENT_ECHO_LEGACY", True),
        )


__all__ = ["EventConfig"]
