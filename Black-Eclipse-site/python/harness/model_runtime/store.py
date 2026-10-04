"""Model Runtime persistence — its OWN domain, separate from the financial JDdS.

This module owns the `ModelRequest` and `ModelHealth` tables on the harness's
`agent-memory.db` connection. It is standalone (not mixed into
`persistence.py`) so that ratcheted module needs no edit and the model layer's
storage is discoverable in one place.

Nothing here stores prompts, tool output or credentials. Pricing that was
unknown is stored as NULL, never 0, so the UI renders the honest "unknown" state.
"""

from __future__ import annotations

import json
from typing import Any, Optional

MODEL_RUNTIME_SCHEMA = """
-- Model Runtime persistence (provider-agnostic model layer). This is the model
-- runtime's OWN domain, deliberately separate from the financial JDdS vault. One
-- bounded row per model request: routing decision, normalized usage and cost.
-- Pricing that was unknown is stored as NULL (never 0), so the UI renders the
-- honest "cost unknown" state. `decision` is a bounded, already-redacted JSON
-- trace: no credentials, no prompts, no provider payloads.
CREATE TABLE IF NOT EXISTS ModelRequest (
  id            TEXT PRIMARY KEY,
  runId         TEXT,
  provider      TEXT NOT NULL,
  model         TEXT NOT NULL,
  task          TEXT,
  fallback      INTEGER NOT NULL DEFAULT 0,
  success       INTEGER NOT NULL,
  errorClass    TEXT,
  retries       INTEGER NOT NULL DEFAULT 0,
  inputTokens   INTEGER NOT NULL DEFAULT 0,
  outputTokens  INTEGER NOT NULL DEFAULT 0,
  cachedTokens  INTEGER NOT NULL DEFAULT 0,
  totalTokens   INTEGER NOT NULL DEFAULT 0,
  tokensEstimated INTEGER NOT NULL DEFAULT 0,
  latencyMs     REAL NOT NULL DEFAULT 0,
  ttftMs        REAL,
  costTotal     REAL,
  costCurrency  TEXT,
  costKind      TEXT,
  costEstimated INTEGER NOT NULL DEFAULT 0,
  decision      TEXT,
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_request_run   ON ModelRequest(runId);
CREATE INDEX IF NOT EXISTS idx_model_request_model ON ModelRequest(provider, model);
CREATE INDEX IF NOT EXISTS idx_model_request_created ON ModelRequest(createdAt);

-- Rolling per-provider/model health aggregate, upserted from usage records. A
-- bounded counter (not a time series) so the store never grows without limit:
-- sample count + success/failure counts + last-known latency.
CREATE TABLE IF NOT EXISTS ModelHealth (
  key          TEXT PRIMARY KEY,
  samples      INTEGER NOT NULL DEFAULT 0,
  successes    INTEGER NOT NULL DEFAULT 0,
  failures     INTEGER NOT NULL DEFAULT 0,
  lastLatencyMs REAL,
  lastSeenAt   TEXT NOT NULL
);
"""


class ModelRuntimeStore:
    """Owns the model-runtime tables on the harness's `agent-memory.db`.

    A thin adapter over an existing `AgentMemoryStore`'s connection: it applies
    its own idempotent DDL on construction (so the ratcheted `persistence.py`
    needs no edit) and exposes the two write seams the runtime's `UsageStore`
    sink needs. Kept duck-typed — only `_db` is required from the host store.
    """

    def __init__(self, store: Any) -> None:
        self._host = store
        self._db = getattr(store, "_db", None)
        if self._db is None:  # pragma: no cover - defensive
            raise TypeError("ModelRuntimeStore requires a store exposing `_db`")
        self._db.executescript(MODEL_RUNTIME_SCHEMA)
        self._db.commit()

    def record_model_request(self, record: dict[str, Any]) -> None:
        """Persist one model request row (usage/cost/routing decision)."""
        from ..persistence import now_iso, new_id

        cost = record.get("cost") or {}
        decision = record.get("decision")
        self._db.execute(
            """INSERT INTO ModelRequest
               (id, runId, provider, model, task, fallback, success, errorClass, retries,
                inputTokens, outputTokens, cachedTokens, totalTokens, tokensEstimated,
                latencyMs, ttftMs, costTotal, costCurrency, costKind, costEstimated,
                decision, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("requestId") or new_id("mreq"),
                record.get("runId"),
                record.get("provider") or "unknown",
                record.get("model") or "unknown",
                record.get("task"),
                1 if record.get("fallback") else 0,
                1 if record.get("success") else 0,
                record.get("errorClass"),
                int(record.get("retries") or 0),
                int(record.get("inputTokens") or 0),
                int(record.get("outputTokens") or 0),
                int(record.get("cachedTokens") or 0),
                int(record.get("totalTokens") or 0),
                1 if record.get("tokensEstimated") else 0,
                float(record.get("latencyMs") or 0.0),
                record.get("ttftMs"),
                cost.get("totalCost"),
                cost.get("currency"),
                cost.get("kind"),
                1 if cost.get("estimated") else 0,
                json.dumps(decision) if decision else None,
                now_iso(),
            ),
        )
        self._db.commit()

    def upsert_model_health(self, record: dict[str, Any]) -> None:
        """Upsert the rolling health counter for a provider/model key."""
        from ..persistence import now_iso

        key = f"{record.get('provider') or 'unknown'}/{record.get('model') or 'unknown'}"
        success = 1 if record.get("success") else 0
        self._db.execute(
            """INSERT INTO ModelHealth
               (key, samples, successes, failures, lastLatencyMs, lastSeenAt)
               VALUES (?, 1, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 samples = samples + 1,
                 successes = successes + ?,
                 failures = failures + ?,
                 lastLatencyMs = excluded.lastLatencyMs,
                 lastSeenAt = excluded.lastSeenAt""",
            (
                key, success, 0 if success else 1, record.get("latencyMs"), now_iso(),
                success, 0 if success else 1,
            ),
        )
        self._db.commit()

    def list_model_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            "SELECT * FROM ModelRequest ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("decision"):
                try:
                    item["decision"] = json.loads(item["decision"])
                except (TypeError, ValueError):
                    item["decision"] = None
            out.append(item)
        return out

    def model_health_summary(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM ModelHealth ORDER BY samples DESC"
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["MODEL_RUNTIME_SCHEMA", "ModelRuntimeStore"]


