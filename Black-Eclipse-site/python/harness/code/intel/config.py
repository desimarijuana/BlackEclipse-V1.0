"""CIUE configuration — env-overridable knobs with sensible defaults.

Uses the repository's existing configuration convention (environment variables
with documented overrides, resolved once at read time so a change takes effect
without a restart where practical). Nothing here is a secret; every value is a
plain bound.

  * ``HARNESS_CODE_INTEL``            — "0"/"false" disables CIUE entirely.
  * ``HARNESS_CODE_INTEL_LSP``        — "0"/"false" disables language servers
                                        (structural/index understanding still works).
  * ``HARNESS_CODE_INTEL_INDEX_DIR``  — override the dedicated index directory.
  * ``HARNESS_CODE_INTEL_LSP_TIMEOUT``— per-request LSP timeout, seconds.
  * ``HARNESS_CODE_INTEL_MAX_FILES``  — the per-pass indexing file bound.
  * ``HARNESS_CODE_INTEL_REFRESH_S``  — how stale an index may be before a query
                                        refreshes it incrementally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TRUE = ("1", "true", "yes", "on")


def _flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _int(name: str, default: int, *, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


def _float(name: str, default: float, *, low: float, high: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return max(low, min(value, high))


@dataclass(frozen=True)
class IntelConfig:
    enabled: bool
    lsp_enabled: bool
    index_dir: str
    lsp_timeout_s: float
    max_index_files: int
    refresh_after_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "lspEnabled": self.lsp_enabled,
            "indexDir": self.index_dir,
            "lspTimeoutSeconds": self.lsp_timeout_s,
            "maxIndexFiles": self.max_index_files,
            "refreshAfterSeconds": self.refresh_after_s,
        }


def load_config() -> IntelConfig:
    from .persistence.index import code_index_dir

    override = os.environ.get("HARNESS_CODE_INTEL_INDEX_DIR")
    try:
        index_dir = str(Path(override)) if override else str(code_index_dir())
    except Exception:  # noqa: BLE001
        index_dir = override or ""
    return IntelConfig(
        enabled=_flag("HARNESS_CODE_INTEL", True),
        lsp_enabled=_flag("HARNESS_CODE_INTEL_LSP", True),
        index_dir=index_dir,
        lsp_timeout_s=_float("HARNESS_CODE_INTEL_LSP_TIMEOUT", 15.0, low=2.0, high=120.0),
        max_index_files=_int("HARNESS_CODE_INTEL_MAX_FILES", 60_000, low=100, high=500_000),
        refresh_after_s=_float("HARNESS_CODE_INTEL_REFRESH_S", 30.0, low=0.0, high=3_600.0),
    )


__all__ = ["IntelConfig", "load_config"]
