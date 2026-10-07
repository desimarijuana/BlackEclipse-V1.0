"""JSON input schemas for the `computer_*` toolset.

Kept separate from `tools.py` so the registration module stays readable. The
model-facing surface is deliberately COMPACT and token-efficient: one consolidated
`computer_use(action=...)` workhorse plus a handful of small read/support tools.
Descriptions are written for an LLM: how references work and what happens after a
call.
"""

from __future__ import annotations

from typing import Any

_ACTIONS = (
    "capture", "click", "double_click", "right_click", "middle_click",
    "mouse_move", "mouse_position", "scroll", "drag", "type", "key", "hotkey",
    "set_value", "wait", "list_apps", "list_windows", "list_displays",
    "focus_app",
)


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_SESSION = {"type": "string", "description": "Which desktop session to use. Omit to use the most recently active one."}
_ELEMENT = {"type": "integer", "description": "An element number from a `capture` snapshot (#1, #2, …). Prefer this over coordinates."}
_SNAPSHOT = {"type": "string", "description": "The snapshot_id the element number came from. Required with `element` so a stale handle is refused."}

INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    # ── The consolidated action workhorse ───────────────────────────────────
    "computer_use": _schema({
        "action": {"type": "string", "enum": list(_ACTIONS),
                   "description": "The action to perform. `capture` observes the desktop; the rest act on it."},
        "element": _ELEMENT,
        "snapshot_id": _SNAPSHOT,
        "identity": {"type": "string", "description": "Optional element identity from the snapshot, for strict stale detection."},
        "target": {"type": "string", "description": "A description of the target when no element number is available (grounded accessibility → OCR → vision)."},
        "name": {"type": "string", "description": "Exact accessible name to match."},
        "role": {"type": "string", "description": "Accessible role to match (button, textbox, combobox, …)."},
        "coordinates": {"type": "array", "items": {"type": "number"},
                        "description": "Fallback [x, y] or [left, top, right, bottom]. Coordinates are a last resort."},
        "value": {"type": "string", "description": "Value for `set_value`."},
        "text": {"type": "string", "description": "Text to type. Never echoed back."},
        "key": {"type": "string", "description": "A key or shortcut, e.g. 'enter' or 'ctrl+s' or a semantic name like 'SAVE'."},
        "combo": {"type": "string", "description": "Alias for `key` for the hotkey action."},
        "x": {"type": "integer", "description": "X coordinate for pointer/scroll."},
        "y": {"type": "integer", "description": "Y coordinate for pointer/scroll."},
        "dx": {"type": "integer", "description": "Horizontal scroll delta."},
        "dy": {"type": "integer", "description": "Vertical scroll delta."},
        "button": {"type": "string", "enum": ["left", "right", "middle"]},
        "count": {"type": "integer", "description": "Click count (2 = double click)."},
        "window_id": {"type": "string", "description": "Target a specific window (from list_windows)."},
        "app": {"type": "string", "description": "Application name for focus_app/list filtering."},
        "mode": {"type": "string", "enum": ["som", "vision", "ax", "ocr"],
                 "description": "Observation mode for `capture`. `som` (default) is a screen-of-marks with numbered elements."},
        "capture_after": {"type": "boolean", "description": "Observe again after the action and return the new state (for state-changing actions)."},
        "foreground": {"type": "boolean", "description": "Force foreground delivery (moves the real cursor / raises focus). Use only when background fails."},
        "dry_run": {"type": "boolean", "description": "Describe the action without executing it."},
        "ms": {"type": "integer", "description": "Milliseconds for `wait`."},
        "session_id": _SESSION,
    }, ["action"]),

    # ── Read-only support tools ──────────────────────────────────────────────
    "computer_capabilities": _schema({}),
    "computer_status": _schema({"session_id": _SESSION}),
    "computer_doctor": _schema({}),
    "computer_windows": _schema({"app": {"type": "string", "description": "Filter by application name."}}),
    "computer_apps": _schema({}),
    "computer_displays": _schema({}),
    "computer_read_screen": _schema({
        "window_id": {"type": "string"},
        "mode": {"type": "string", "enum": ["som", "vision", "ax", "ocr"]},
        "session_id": _SESSION,
    }),

    # ── Sessions ─────────────────────────────────────────────────────────────
    "computer_session_start": _schema({
        "risk_mode": {"type": "string", "enum": ["read_only", "assisted", "autonomous", "simulation"],
                      "description": "The financial risk mode for this session."},
    }),
    "computer_session_list": _schema({}),
    "computer_session_close": _schema({"session_id": _SESSION}),

    # ── Takeover ─────────────────────────────────────────────────────────────
    "computer_takeover": _schema({"reason": {"type": "string"}, "session_id": _SESSION}),
    "computer_pause": _schema({"reason": {"type": "string"}, "session_id": _SESSION}),
    "computer_resume": _schema({"reason": {"type": "string"}, "session_id": _SESSION}),
    "computer_release": _schema({"reason": {"type": "string"}, "session_id": _SESSION}),

    # ── Recording ────────────────────────────────────────────────────────────
    "computer_record_export": _schema({"session_id": _SESSION}),

    # ── Finance ──────────────────────────────────────────────────────────────
    "computer_finance_read": _schema({
        "window_id": {"type": "string"},
        "session_id": _SESSION,
    }),
    # ── Learned desktop knowledge (Eclipse-Memory) ───────────────────────────
    "computer_remember": _schema({
        "kind": {"type": "string", "enum": ["layout", "workflow", "recovery", "pattern"],
                 "description": "What is being learned about the desktop."},
        "content": {"type": "string", "description": "The knowledge, in one or two sentences."},
        "application": {"type": "string", "description": "The application it concerns."},
        "subject": {"type": "string", "description": "Optional subject key."},
    }, ["kind", "content"]),
    "computer_recall": _schema({
        "query": {"type": "string", "description": "What to remember about the desktop."},
        "application": {"type": "string"},
    }, ["query"]),

    "computer_finance_prepare": _schema({
        "application": {"type": "string", "description": "The trading application."},
        "action": {"type": "string", "enum": ["prepare_order", "buy", "sell", "short", "cover", "submit_order", "cancel_order", "modify_order", "transfer", "withdraw"],
                   "description": "The financial intent to classify and gate."},
        "instrument": {"type": "string", "description": "The symbol/instrument."},
        "side": {"type": "string", "enum": ["buy", "sell"]},
        "quantity": {"type": "number"},
        "price": {"type": "number"},
        "order_type": {"type": "string", "description": "e.g. market, limit."},
        "account": {"type": "string"},
        "session_id": _SESSION,
    }, ["action"]),
}

# Tool metadata: registry permission, risk, effect, timeout, description.
#
# Like the browser's click/type tools, the computer action tools are registered
# as `read` at the REGISTRY level: the real gate is the handler's COMPUTER POLICY
# engine (plus the finance firewall), which routes an ASK through the same
# single-use approval store the rest of the harness uses. Registering them as
# effectful would refuse even a harmless `capture` before the handler could
# decide. The autonomy boundary is still structural: `COMPUTER_EFFECTFUL_TOOLS`
# (in `code/policy.py`) removes the action tools at `plan_only`.
TOOL_META: dict[str, dict[str, Any]] = {
    "computer_use": {"risk": "medium", "timeout": 60_000, "desc":
        "Operate the real desktop: observe it and act on native applications (Excel, VS Code, terminals, "
        "PDF apps, trading terminals). Start with action='capture' to get numbered elements (#1, #2, …), then act "
        "with element=<number> and the returned snapshot_id. Background delivery is the default and does NOT steal "
        "your focus; a foreground escalation is explicit. A financial mutation is routed through the finance firewall."},
    "computer_capabilities": {"risk": "low", "timeout": 15_000, "desc": "Report what this machine's Computer Use runtime can do (driver, accessibility, capture, OCR, vision)."},
    "computer_status": {"risk": "low", "timeout": 15_000, "desc": "Report a desktop session's state, active app and current snapshot."},
    "computer_doctor": {"risk": "low", "timeout": 15_000, "desc": "Diagnose the Computer Use runtime: platform, driver, permissions and capability readiness."},
    "computer_windows": {"risk": "low", "timeout": 15_000, "desc": "List open windows (id, title, application, bounds, focused)."},
    "computer_apps": {"risk": "low", "timeout": 15_000, "desc": "List running applications with their windows."},
    "computer_displays": {"risk": "low", "timeout": 15_000, "desc": "List displays: resolution, scale, DPI, primary, bounds."},
    "computer_read_screen": {"risk": "low", "timeout": 30_000, "desc": "Observe the screen (or a window) as numbered elements without acting."},
    "computer_session_start": {"risk": "medium", "timeout": 30_000, "desc": "Start a desktop-control session and return its id. Other computer tools reuse the most recent one."},
    "computer_session_list": {"risk": "low", "timeout": 15_000, "desc": "List desktop sessions."},
    "computer_session_close": {"risk": "low", "timeout": 20_000, "desc": "Close a desktop session."},
    "computer_takeover": {"risk": "low", "timeout": 15_000, "desc": "Hand control to a person: the agent stops acting, session state is preserved, and it can resume later."},
    "computer_pause": {"risk": "low", "timeout": 15_000, "desc": "Pause a session."},
    "computer_resume": {"risk": "low", "timeout": 15_000, "desc": "Resume a paused/human-held session."},
    "computer_release": {"risk": "low", "timeout": 15_000, "desc": "Release the control lease back to the agent."},
    "computer_record_export": {"risk": "low", "timeout": 20_000, "desc": "Export the session's recorded trajectory to a JSON file for inspection/replay."},
    "computer_remember": {"risk": "low", "timeout": 20_000, "desc":
        "Store a learned desktop fact (application layout, a successful workflow, a recovery path) in Eclipse-Memory. "
        "Explicit and inspectable — never screenshots, never automatic."},
    "computer_recall": {"risk": "low", "timeout": 15_000, "desc": "Recall previously learned desktop knowledge."},
    "computer_finance_read": {"risk": "low", "timeout": 30_000, "desc":
        "Read financial state from the screen (ticker, bid, ask, position, P&L, …). The result is SCREEN-DERIVED, "
        "carries an explicit source, and is never treated as authoritative market data."},
    "computer_finance_prepare": {"risk": "critical", "timeout": 30_000, "desc":
        "Classify a financial intent and run it through the finance firewall BEFORE touching the UI. Returns "
        "allowed / approval_required / blocked. Eclipse never performs an unrestricted financial mutation."},
}

# The computer ELEVATED tools the computer authorizer admits. `computer_use`
# itself is registered as `read` (like `browser_click`) and gated per-call by the
# computer policy engine; the finance firewall + takeover are the elevated set.
# Mirrored by `code/policy.py` `COMPUTER_EFFECTFUL_TOOLS` (the ONE authority for
# the autonomy boundary).
EFFECTFUL_TOOLS: tuple[str, ...] = (
    "computer_finance_prepare",
    "computer_takeover",
)

ALL_TOOL_NAMES: tuple[str, ...] = tuple(INPUT_SCHEMAS.keys())

__all__ = ["ALL_TOOL_NAMES", "EFFECTFUL_TOOLS", "INPUT_SCHEMAS", "TOOL_META"]
