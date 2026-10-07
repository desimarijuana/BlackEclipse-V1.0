"""Browser trace replay and inspection (Phase 8.1).

A stored `BrowserTrace` is enough to answer, WITHOUT a live browser: what the
agent SAW, what it DID and why, what CHANGED, and why it FAILED. This module is a
pure read path over the trace's bounded step record — it never launches or
touches a browser, and it never re-executes anything.

The output is a bounded `timeline` (one row per step) plus a `failureAnalysis`
that names the first failing step, its stable code, a coarse category and a plain
sentence. `render_text` turns the same view into a short human-readable timeline
(“open page → search → find filing → download → extract”), which the operator UI
displays and the `browser_replay` tool returns to the model.

Nothing here fabricates: a step with no verification is reported as unverified,
not as a success; a trace with no error yields `failureAnalysis: null`.
"""

from __future__ import annotations

from typing import Any, Optional

from .telemetry import classify_error

# A replay is bounded: the timeline keeps the most recent steps of a very long
# trace (the same tail-first bias the trace itself uses).
MAX_REPLAY_STEPS = 500
_MAX_STR = 300

# Plain sentences for the codes an operator/model is most likely to hit. The
# category fallback guarantees a sentence even for an unrecognised code.
_PLAIN_REASONS: tuple[tuple[str, str], ...] = (
    ("TIMEOUT", "the page or the action didn't finish in time"),
    ("CAPABILITY_UNSUPPORTED", "the chosen browser backend can't do that action"),
    ("PROVIDER_UNAVAILABLE", "the browser backend couldn't start or was unavailable"),
    ("PROVIDER_ERROR", "the browser backend reported an error"),
    ("LAUNCH_FAILED", "the browser couldn't be started"),
    ("ELEMENT_NOT_FOUND", "the element the agent targeted wasn't on the page"),
    ("STALE_ELEMENT", "the page changed and the element reference went stale"),
    ("NAVIGATION_FAILED", "the page couldn't be opened"),
    ("AUTHENTICATION_FAILED", "sign-in didn't succeed"),
    ("CREDENTIAL_UNAVAILABLE", "a saved credential couldn't be resolved"),
    ("DOWNLOAD_FAILED", "the download couldn't be saved"),
    ("UPLOAD_FAILED", "the upload couldn't be delivered"),
    ("PERMISSION_DENIED", "the browser policy denied the action"),
    ("APPROVAL_REQUIRED", "the action needed a person's approval"),
    ("HUMAN_REQUIRED", "a person had to complete a CAPTCHA/MFA/security check"),
    ("UNAVAILABLE", "the browser capability was unavailable"),
)

_CATEGORY_SENTENCES = {
    "timeout": "the action timed out",
    "capability": "the backend doesn't support that action",
    "provider": "the browser backend failed",
    "crash": "the browser crashed or disconnected",
    "element": "the target element couldn't be found",
    "navigation": "navigation failed",
    "auth": "authentication failed",
    "download": "the download failed",
    "upload": "the upload failed",
    "dialog": "the page dialog couldn't be handled",
    "cdp": "the CDP command failed",
    "execution": "the browser program stopped",
    "permission": "the action was refused by policy",
    "human": "a person's intervention was required",
    "limit": "a browser session limit was hit",
    "unavailable": "the browser capability was unavailable",
    "error": "the action failed",
    "unknown": "the action failed",
}


def plain_reason(code: Optional[str]) -> str:
    """A short plain sentence for a stable error code (or its category)."""
    if not code:
        return _CATEGORY_SENTENCES["unknown"]
    upper = str(code).upper()
    for needle, sentence in _PLAIN_REASONS:
        if needle in upper:
            return sentence
    return _CATEGORY_SENTENCES.get(classify_error(code), _CATEGORY_SENTENCES["error"])


def _clip(value: Any, limit: int = _MAX_STR) -> str:
    try:
        return str(value)[:limit]
    except Exception:  # noqa: BLE001
        return ""


def _step_status(step: dict[str, Any]) -> str:
    if step.get("error"):
        return "failed"
    if step.get("humanIntervention"):
        return "human"
    verification = step.get("verification") or {}
    if verification and verification.get("success") is False:
        return "unverified"
    return "ok"


def _step_row(step: dict[str, Any]) -> dict[str, Any]:
    """One bounded timeline row: what happened, why, what changed."""
    observation = step.get("observation") or {}
    verification = step.get("verification") or {}
    error = step.get("error") or None
    refs = _snapshot_refs(observation)
    row: dict[str, Any] = {
        "index": step.get("index"),
        "action": step.get("action"),
        "providedBy": step.get("provider") or None,
        "durationMs": step.get("durationMs") or 0,
        "status": _step_status(step),
        "params": step.get("params") or {},
        "observationSummary": _summarize(observation),
        "verification": {
            "success": verification.get("success"),
            "stateChanged": bool(verification.get("state_changed")),
            "summary": _clip(verification.get("summary"), 240) if verification.get("summary") else None,
        } if verification else None,
        "refs": refs or None,
        "humanIntervention": step.get("humanIntervention") or None,
        "error": None,
    }
    if error:
        code = error.get("code")
        row["error"] = {
            "code": code,
            "category": classify_error(code),
            "reason": plain_reason(code),
            "message": _clip(error.get("message"), 240),
        }
    return row


def _snapshot_refs(observation: dict[str, Any]) -> list[str]:
    """Pull the stable `@eN` references out of an observation, if any."""
    if not isinstance(observation, dict):
        return []
    refs: list[str] = []
    for key in ("interactive", "elements", "matches"):
        value = observation.get(key)
        if isinstance(value, list):
            for item in value[:40]:
                if isinstance(item, dict) and item.get("ref"):
                    refs.append(str(item["ref"]))
    return refs[:40]


def _summarize(observation: dict[str, Any]) -> Optional[str]:
    """A one-line, content-safe summary of what the agent saw."""
    if not isinstance(observation, dict) or not observation:
        return None
    if observation.get("summary"):
        return _clip(observation["summary"], 240)
    bits: list[str] = []
    for key in ("url", "title", "generation", "elementCount", "interactiveCount", "chars", "count"):
        if observation.get(key) is not None:
            bits.append(f"{key}={_clip(observation[key], 120)}")
    return "; ".join(bits) if bits else None


def build_timeline(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """A bounded, ordered timeline of a stored trace's steps."""
    steps = trace.get("steps") or []
    if not isinstance(steps, list):
        return []
    return [_step_row(step if isinstance(step, dict) else {}) for step in steps[-MAX_REPLAY_STEPS:]]


def failure_analysis(timeline: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The first failing step and why, or None when the trace has no failure."""
    for row in timeline:
        if row.get("error"):
            return {
                "stepIndex": row.get("index"),
                "action": row.get("action"),
                "code": row["error"]["code"],
                "category": row["error"]["category"],
                "reason": row["error"]["reason"],
            }
    return None


def replay_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a stored trace into a bounded, browser-free replay view.

    Accepts the dict `BrowserStore.get_trace` returns (or the `trace` object a
    live session holds via `to_dict`). Never raises on a sparse trace.
    """
    summary = trace.get("summary") or {}
    timeline = build_timeline(trace)
    changed = [row["index"] for row in timeline if (row.get("verification") or {}).get("stateChanged")]
    failure = failure_analysis(timeline)
    return {
        "traceId": trace.get("id"),
        "sessionId": trace.get("sessionId"),
        "runId": trace.get("runId"),
        "taskId": trace.get("taskId"),
        "provider": trace.get("provider"),
        "status": trace.get("status"),
        "createdAt": trace.get("createdAt"),
        "finishedAt": trace.get("finishedAt"),
        "stepCount": len(trace.get("steps") or []),
        "shownSteps": len(timeline),
        "bounded": len(trace.get("steps") or []) > MAX_REPLAY_STEPS,
        "summary": summary,
        "timeline": timeline,
        "changedStepIndices": changed,
        "failureAnalysis": failure,
    }


def render_text(view: dict[str, Any]) -> str:
    """A short human-readable timeline of the replay view."""
    lines: list[str] = []
    header = (
        f"Trace {view.get('traceId')} — {view.get('status') or 'unknown'}, "
        f"{view.get('shownSteps', 0)} of {view.get('stepCount', 0)} step(s), "
        f"provider {view.get('provider') or '?'}."
    )
    lines.append(header)
    for row in view.get("timeline") or []:
        marker = {"ok": "✓", "failed": "✗", "human": "⏸", "unverified": "?"}.get(row.get("status"), "·")
        line = f"  {marker} {row.get('index')}. {row.get('action')} ({row.get('durationMs')}ms)"
        if (row.get("verification") or {}).get("stateChanged"):
            line += " [page changed]"
        if row.get("observationSummary"):
            line += f" — saw {row['observationSummary']}"
        if row.get("error"):
            line += f" — failed: {row['error']['reason']} ({row['error']['code']})"
        lines.append(line)
    failure = view.get("failureAnalysis")
    if failure:
        lines.append(
            f"The run first failed at step {failure['stepIndex']} ({failure['action']}): "
            f"{failure['reason']} [{failure['code']}]."
        )
    else:
        lines.append("No failures were recorded in this trace.")
    return "\n".join(lines)


__all__ = [
    "MAX_REPLAY_STEPS",
    "build_timeline",
    "failure_analysis",
    "plain_reason",
    "render_text",
    "replay_trace",
]
