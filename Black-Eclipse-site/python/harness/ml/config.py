"""Runtime configuration and resource guardrails for the ML Research Lab.

Limits are read from the environment (``HARNESS_ML_*``) with conservative
defaults so a single experiment can never exhaust the host: bounded rows, folds,
wall-clock seconds, concurrency and artifact size. Everything is validated; a
bad value falls back to its default rather than crashing boot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass(frozen=True)
class MLConfig:
    """Hard limits enforced by the engine and the Fabric worker."""

    enabled: bool = True
    # Maximum rows in a flattened dataset (dates x symbols).
    max_rows: int = 2_000_000
    # Maximum folds any split design may produce.
    max_folds: int = 50
    # Wall-clock budget for one training job (also the worker timeout source).
    max_seconds: int = 1800
    # Concurrent ML training jobs.
    max_concurrent: int = 1
    # Maximum serialized artifact size (megabytes) before a build is refused.
    max_artifact_mb: int = 512
    # Extra slack on the worker timeout beyond max_seconds (process overhead).
    timeout_slack_seconds: int = 60

    @classmethod
    def from_env(cls) -> "MLConfig":
        return cls(
            enabled=_bool_env("HARNESS_ML_ENABLED", True),
            max_rows=_int_env("HARNESS_ML_MAX_ROWS", 2_000_000, minimum=100),
            max_folds=_int_env("HARNESS_ML_MAX_FOLDS", 50, minimum=1),
            max_seconds=_int_env("HARNESS_ML_MAX_SECONDS", 1800, minimum=5),
            max_concurrent=_int_env("HARNESS_ML_MAX_CONCURRENT", 1, minimum=1),
            max_artifact_mb=_int_env("HARNESS_ML_MAX_ARTIFACT_MB", 512, minimum=1),
        )

    @property
    def worker_timeout_ms(self) -> int:
        return (self.max_seconds + self.timeout_slack_seconds) * 1000

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled, "maxRows": self.max_rows, "maxFolds": self.max_folds,
            "maxSeconds": self.max_seconds, "maxConcurrent": self.max_concurrent,
            "maxArtifactMb": self.max_artifact_mb,
        }


_default: Optional[MLConfig] = None


def get_ml_config() -> MLConfig:
    global _default
    if _default is None:
        _default = MLConfig.from_env()
    return _default


__all__ = ["MLConfig", "get_ml_config"]
