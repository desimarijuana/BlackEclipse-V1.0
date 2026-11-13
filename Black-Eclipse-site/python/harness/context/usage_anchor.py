"""Session usage anchor (W2).

The provider's reported prompt/completion token counts are the only reliable
measure of how full a context is. This store keeps the last successful response
per session, plus a fingerprint of the conversation at that moment, so the next
turn can estimate only the *appended* history instead of the whole request.

The anchor is intentionally small, additive and overwrite-only. It stores no
prompt text, no response text and no provider payload.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS SessionUsageAnchor (
  sessionId          TEXT PRIMARY KEY,
  modelKey           TEXT NOT NULL,
  promptTokens       INTEGER NOT NULL,
  completionTokens   INTEGER NOT NULL,
  anchorFingerprint  TEXT NOT NULL,
  anchorHistoryChars INTEGER NOT NULL DEFAULT 0,
  contextLength      INTEGER,
  anchored           INTEGER NOT NULL DEFAULT 1,
  updatedAt          TEXT NOT NULL
);
"""


def _fingerprint(messages: list[Any]) -> str:
    """A stable fingerprint of the request tail (no prompt text persisted)."""
    last = messages[-1] if messages else None
    content = str(getattr(last, "content", "") or "")
    ident = str(getattr(last, "id", "") or "")
    return "sha256:" + hashlib.sha256((ident + "\x1f" + content).encode("utf-8")).hexdigest()[:24]


def _history_chars(history: Any) -> int:
    try:
        return sum(len(str(getattr(turn, "content", "") or "")) for turn in (history or []))
    except Exception:  # noqa: BLE001
        return 0


@dataclass(frozen=True)
class UsageAnchor:
    session_id: str
    model_key: str
    prompt_tokens: int
    completion_tokens: int
    anchor_fingerprint: str
    anchor_history_chars: int
    context_length: Optional[int]
    anchored: bool
    updated_at: str

    def estimated_used(self, *, history_chars: int, chars_per_token: int = 4) -> int:
        """Provider prompt tokens plus an estimate of appended history only."""
        appended = max(0, int(history_chars) - int(self.anchor_history_chars))
        return int(self.prompt_tokens) + (appended + chars_per_token - 1) // chars_per_token


class UsageAnchorStore:
    """One anchor per session over the harness's existing SQLite connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db = getattr(store, "_db", None)
        if self._db is not None:
            try:
                self._db.executescript(SCHEMA)
                self._db.commit()
            except Exception:  # noqa: BLE001 - the anchor must never break a run
                pass

    def get(self, session_id: str) -> Optional[UsageAnchor]:
        if self._db is None or not session_id:
            return None
        try:
            row = self._db.execute(
                "SELECT * FROM SessionUsageAnchor WHERE sessionId=?", (session_id,)
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        if row is None:
            return None
        return UsageAnchor(
            session_id=str(row["sessionId"]),
            model_key=str(row["modelKey"]),
            prompt_tokens=int(row["promptTokens"] or 0),
            completion_tokens=int(row["completionTokens"] or 0),
            anchor_fingerprint=str(row["anchorFingerprint"] or ""),
            anchor_history_chars=int(row["anchorHistoryChars"] or 0),
            context_length=int(row["contextLength"]) if row["contextLength"] is not None else None,
            anchored=bool(row["anchored"]),
            updated_at=str(row["updatedAt"] or ""),
        )

    def record(
        self,
        session_id: str,
        *,
        model_key: str,
        prompt_tokens: int,
        completion_tokens: int,
        messages: list[Any],
        history_chars: int,
        context_length: Optional[int],
        anchored: bool = True,
    ) -> Optional[UsageAnchor]:
        if self._db is None or not session_id:
            return None
        from ..persistence import now_iso  # noqa: PLC0415

        now = now_iso()
        fingerprint = _fingerprint(messages)
        try:
            self._db.execute(
                """INSERT INTO SessionUsageAnchor
                   (sessionId, modelKey, promptTokens, completionTokens,
                    anchorFingerprint, anchorHistoryChars, contextLength, anchored, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sessionId) DO UPDATE SET
                     modelKey=excluded.modelKey,
                     promptTokens=excluded.promptTokens,
                     completionTokens=excluded.completionTokens,
                     anchorFingerprint=excluded.anchorFingerprint,
                     anchorHistoryChars=excluded.anchorHistoryChars,
                     contextLength=excluded.contextLength,
                     anchored=excluded.anchored,
                     updatedAt=excluded.updatedAt""",
                (
                    session_id, model_key, int(prompt_tokens), int(completion_tokens),
                    fingerprint, int(history_chars), context_length,
                    1 if anchored else 0, now,
                ),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            return None
        return self.get(session_id)

    def clear(self, session_id: str) -> None:
        if self._db is None or not session_id:
            return
        try:
            self._db.execute("DELETE FROM SessionUsageAnchor WHERE sessionId=?", (session_id,))
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass

    def snapshot(self, session_id: str) -> dict[str, Any]:
        anchor = self.get(session_id)
        return {} if anchor is None else {
            "sessionId": anchor.session_id,
            "modelKey": anchor.model_key,
            "promptTokens": anchor.prompt_tokens,
            "completionTokens": anchor.completion_tokens,
            "historyChars": anchor.anchor_history_chars,
            "contextLength": anchor.context_length,
            "anchored": anchor.anchored,
            "updatedAt": anchor.updated_at,
        }


def prepare_anchor(
    store: Any, request: Any, *, enabled: Optional[bool] = None,
) -> tuple[Optional[UsageAnchorStore], str, Optional[UsageAnchor], int]:
    """Return `(store, anchor_id, anchor, history_chars)`.

    `HARNESS_USAGE_ANCHOR=off` is the kill switch: no anchor is loaded and no
    store is handed to the gateway, so the legacy character estimate stands.
    """
    if enabled is None:
        try:
            from ..config import flags  # noqa: PLC0415

            enabled = bool(flags.get_flag("HARNESS_USAGE_ANCHOR"))
        except Exception:  # noqa: BLE001 - a flag read must not break a run
            enabled = True
    anchor_id = str(
        getattr(request, "sessionId", None) or getattr(request, "runId", "") or ""
    )
    history = getattr(getattr(request, "input", None), "history", None) or []
    history_chars = sum(len(str(getattr(turn, "content", "") or "")) for turn in history)
    if not enabled:
        return None, anchor_id, None, history_chars
    anchors = UsageAnchorStore(store)
    return anchors, anchor_id, anchors.get(anchor_id), history_chars


__all__ = ["SCHEMA", "UsageAnchor", "UsageAnchorStore", "prepare_anchor"]
