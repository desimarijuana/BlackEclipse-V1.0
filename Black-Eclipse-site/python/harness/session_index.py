"""Session history indexing — bounded, searchable run messages (M2).

The full run trace already lives in `HarnessRun`/`HarnessEvent`. This module
maintains a SEPARATE, bounded *search index* (`SessionMessage`) of the meaningful
messages from a run, so the agent can answer "what did we decide last week?".

Indexing rules (deliberate):

  * index the user turn, the assistant's final answer, bounded tool/retrieval
    summaries, explicit corrections, memory actions and skill-learning outcomes;
  * NEVER index secrets/credentials/tokens, raw dumps, or unrestricted provider
    payloads — content is redacted and length-capped before it is stored;
  * historical content is CONTEXT, never current financial evidence. It is
    returned through the read-only `session_search`/`session_open` tools and the
    prompt instructs the model to re-retrieve current facts.

Retention and enablement are policy-driven; indexing is best-effort and never
breaks a run.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Reuse the ONE privacy pattern set rather than inventing a second one.
from .eclipse_memory.decision import looks_like_secret

_MAX_MESSAGE_CHARS = 4000
_MAX_SUMMARY_CHARS = 1200

# Raw role markers / dumps are not indexed as-is (they are transcripts).
_DUMP_RE = re.compile(r"(?im)^\s*(system|assistant|user|human)\s*:")


def redact(text: str) -> str:
    """Remove secret-looking spans before anything is indexed.

    This is intentionally conservative: a token/secret/key-shaped run is
    replaced with `[redacted]`, and an obvious tool/provider dump marker line is
    dropped. It never claims to be a complete DLP system — the authoritative
    guard is `session_indexing_enabled` + the redaction here.
    """
    if not text:
        return ""
    cleaned = text
    # Secret-shaped tokens.
    cleaned = re.sub(r"\bsk-[A-Za-z0-9]{12,}\b", "[redacted]", cleaned)
    cleaned = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b", "[redacted]", cleaned)
    cleaned = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[redacted]", cleaned)
    cleaned = re.sub(
        r"(?i)\b(api[ _-]?key|secret|password|passphrase|token|bearer|private[ _-]?key)\b\s*[:=]\s*\S+",
        r"\1=[redacted]",
        cleaned,
    )
    return cleaned.strip()


def _bounded(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def index_run(store: Any, run_id: str, *, user_id: Optional[str] = None) -> dict[str, Any]:
    """Index the meaningful messages of a completed run into `SessionMessage`.

    Idempotent per (runId, ordinal). Returns counts for observability. Never
    raises: an indexing failure is a diagnostic, not a run failure.
    """
    try:
        run = store.get_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "indexed": 0}
    if not run:
        return {"ok": False, "error": "run not found", "indexed": 0}

    indexed = 0
    ordinal = 0

    def _add(role: str, content: str, kind: str) -> None:
        nonlocal indexed, ordinal
        cleaned = redact(content)
        if not cleaned or len(cleaned.strip()) < 2:
            return
        cleaned = _bounded(cleaned, _MAX_MESSAGE_CHARS if kind == "message" else _MAX_SUMMARY_CHARS)
        result = store.index_session_message(
            run_id=run_id, role=role, content=cleaned, user_id=user_id,
            kind=kind, ordinal=ordinal,
        )
        if result:
            indexed += 1
        ordinal += 1

    query = ""
    try:
        query = ((run.get("input") or {}).get("query") or "")
    except Exception:  # noqa: BLE001
        query = ""
    _add("user", query, "message")

    output = run.get("output") or ""
    if output:
        _add("assistant", output, "message")

    # Bounded tool/retrieval summaries (already length-capped on write; we cap
    # again and redact). Exclude the user query text from these.
    try:
        for execution in store.list_tool_executions(run_id):
            text = execution.get("text") or ""
            if text:
                _add("tool", f"{execution.get('name')}: {text}", "tool_summary")
    except Exception:  # noqa: BLE001
        pass

    # Memory actions / learning outcomes from the run's `memory` blob.
    try:
        memory_blob = run.get("memory") or {}
        if isinstance(memory_blob, dict):
            action = memory_blob.get("action")
            if action and memory_blob.get("contentPreview"):
                _add("assistant", f"[memory {action}] {memory_blob.get('contentPreview')}", "memory_action")
            learning = memory_blob.get("learningAnalysis") or {}
            if learning.get("candidatesCreated"):
                _add("assistant", f"[learning] {learning.get('candidatesCreated')} candidate(s) created", "learning_outcome")
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "indexed": indexed, "runId": run_id}
