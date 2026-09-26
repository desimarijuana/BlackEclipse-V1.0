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


def index_run(
    store: Any,
    run_id: str,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
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

    # Prefer the run's own persisted scope; fall back to the caller's.
    session_id = session_id or run.get("sessionId")
    profile_id = profile_id or run.get("profileId")
    project_id = project_id or run.get("projectId")

    indexed = 0
    ordinal = 0

    def _add(role: str, content: str, kind: str, **extra: Any) -> None:
        nonlocal indexed, ordinal
        cleaned = redact(content)
        if not cleaned or len(cleaned.strip()) < 2:
            return
        cleaned = _bounded(cleaned, _MAX_MESSAGE_CHARS if kind == "message" else _MAX_SUMMARY_CHARS)
        result = store.index_session_message(
            run_id=run_id, role=role, content=cleaned, user_id=user_id,
            kind=kind, ordinal=ordinal, session_id=session_id, profile_id=profile_id,
            project_id=project_id, **extra,
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
                _add("assistant", f"[memory {action}] {memory_blob.get('contentPreview')}",
                     "memory_action", memory_action=str(action))
            learning = memory_blob.get("learningAnalysis") or {}
            if learning.get("candidatesCreated"):
                _add("assistant", f"[learning] {learning.get('candidatesCreated')} candidate(s) created", "learning_outcome")
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "indexed": indexed, "runId": run_id}


def build_summary(store: Any, session_id: str, *, limit: int = 40) -> dict[str, Any]:
    """Build a bounded, deterministic session summary from its indexed messages.

    Contains objective / decisions / unresolved / corrections / skills used /
    memories changed / files or instruments / next actions. It is SEARCHABLE but
    is never injected into every prompt automatically; a caller opts in. Never
    raises — a summary is a projection, not truth.
    """
    try:
        messages: list[dict[str, Any]] = []
        for run_id in store.session_runs(session_id):
            messages.extend(store.open_session(run_id).get("messages", []))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    objective = None
    decisions: list[str] = []
    corrections: list[str] = []
    skills: set[str] = set()
    memories: list[str] = []
    instruments: set[str] = set()
    unresolved: list[str] = []

    for message in messages[: max(1, int(limit))]:
        role = message.get("role")
        kind = message.get("kind")
        content = (message.get("content") or message.get("snippet") or "").strip()
        if not content:
            continue
        if role == "user" and objective is None:
            objective = content[:400]
        if kind == "memory_action":
            memories.append(content[:200])
        if kind in ("decision", "correction"):
            corrections.append(content[:200])
        text = content.lower()
        if "decid" in text:
            decisions.append(content[:200])
        if "unresolved" in text or "todo" in text or "next step" in text:
            unresolved.append(content[:200])
        if kind == "tool_summary" and "skill" in text:
            skills.add(content[:120])
        import re as _re  # noqa: PLC0415

        for ticker in _re.findall(r"\b[A-Z]{1,5}\b", message.get("content") or "")[:5]:
            instruments.add(ticker)

    summary = {
        "objective": objective,
        "decisions": decisions[:5],
        "unresolved": unresolved[:5],
        "corrections": corrections[:5],
        "skillsUsed": sorted(skills)[:10],
        "memoriesChanged": memories[:5],
        "instruments": sorted(instruments)[:20],
        "nextActions": unresolved[:5],
        "messageCount": len(messages),
    }
    try:
        store.update_chat_session(session_id, summary=summary)
    except Exception:  # noqa: BLE001 - persisting a summary must not fail the caller
        pass
    return {"ok": True, "sessionId": session_id, "summary": summary}


def summary_prompt_block(session: dict[str, Any]) -> str:
    """A bounded prompt block for an ACTIVE session, or "" when there is none.

    Deliberately small: a session summary is context, never financial evidence,
    and is only injected when a caller asks for an active-workflow block.
    """
    summary = (session or {}).get("summary")
    if not isinstance(summary, dict):
        return ""
    lines = ["## Active workflow (session context — not financial evidence)"]
    if summary.get("objective"):
        lines.append(f"Objective: {summary['objective']}")
    if summary.get("nextActions"):
        lines.append("Next actions: " + "; ".join(str(a) for a in summary["nextActions"][:3]))
    return "\n".join(lines) if len(lines) > 1 else ""
