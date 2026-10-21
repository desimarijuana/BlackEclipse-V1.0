"""Persisted RSL runtime settings.

The loop is still env-first: `RSLConfig.from_env()` supplies the base, then the
last operator-applied override is overlaid. Only the bounded, non-secret fields
in `RSLConfig` are stored; mode is never enabled implicitly.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso
from .config import RSLConfig

RSL_CONFIG_KEY = "rsl.config"


class RuntimeSettingsStore:
    """Small key/value table on the ONE agent-memory database."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS HarnessRuntimeSetting (
      key       TEXT PRIMARY KEY,
      value     TEXT NOT NULL,
      updatedAt TEXT NOT NULL
    );
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(self._SCHEMA)

    @property
    def _db(self):
        return self._store._db

    def get(self, key: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT value FROM HarnessRuntimeSetting WHERE key = ?", (key,),
        ).fetchone()
        if row is None:
            return None
        try:
            parsed = json.loads(row["value"])
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, sort_keys=True)
        self._db.execute(
            """INSERT INTO HarnessRuntimeSetting (key, value, updatedAt)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                            updatedAt = excluded.updatedAt""",
            (key, payload, now_iso()),
        )

    def delete(self, key: str) -> None:
        self._db.execute(
            "DELETE FROM HarnessRuntimeSetting WHERE key = ?", (key,),
        )

    def load_rsl_config(self, base: RSLConfig) -> RSLConfig:
        payload = self.get(RSL_CONFIG_KEY)
        if not payload:
            return base
        try:
            return RSLConfig.from_dict(payload, base=base)
        except ValueError:
            # A corrupt/obsolete row must never stop the runtime from booting.
            return base

    def save_rsl_config(self, config: RSLConfig) -> None:
        self.put(RSL_CONFIG_KEY, config.to_dict())


__all__ = ["RSL_CONFIG_KEY", "RuntimeSettingsStore"]
