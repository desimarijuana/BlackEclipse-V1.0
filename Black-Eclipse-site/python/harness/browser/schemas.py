"""JSON input schemas for the `browser_*` toolset.

Kept separate from `tools.py` so the registration module stays readable. Each
schema is the model-facing contract the registry advertises; the registry's
generic arg model validates against it before the handler runs. Descriptions are
written for an LLM: what the tool does, how references work, and what happens
after the call.
"""

from __future__ import annotations

from typing import Any

_SESSION = {
    "type": "string",
    "description": "Which open browser session to use. Omit to use the most recently active one.",
}
_TARGET = {
    "type": ["string", "object"],
    "description": (
        "The element to act on. Prefer a snapshot reference like \"@e4\" from "
        "browser_snapshot. You may also pass an object: {ref}, {role, name}, "
        "{label}, {text}, {placeholder}, {testid}, {css}, {xpath}, {alt}, {title}, "
        "or {coordinates:{x,y}}."
    ),
}
_WAIT_TIMEOUT = {"type": "number", "description": "Maximum seconds to wait (default 30)."}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    # ── Lifecycle / navigation ─────────────────────────────────────────────
    "browser_launch": _schema({
        "url": {"type": "string", "description": "Optional page to open once the browser starts."},
        "provider": {"type": "string", "description": "Backend to use (default: auto-selected). 'local_chromium', 'cdp', 'lightpanda', etc."},
        "headless": {"type": "boolean", "description": "Run without a visible window (default from config)."},
        "profile": {"type": "string", "description": "Persistent profile name to reuse a signed-in session."},
        "persistent": {"type": "boolean", "description": "Keep cookies/storage on disk for this profile."},
        "viewport": {"type": "object", "description": "{width, height} for the initial window."},
        "permissions": {"type": "object", "description": "Per-permission overrides, e.g. {\"upload\":\"allow\"}."},
        "domains": {"type": "object", "description": "Domain policy: {allowed, blocked, approval}."},
    }),
    "browser_close": _schema({"session_id": _SESSION}),
    "browser_status": _schema({"session_id": _SESSION}),
    "browser_navigate": _schema({
        "url": {"type": "string", "description": "The web address to open (http/https)."},
        "session_id": _SESSION,
        "wait_until": {"type": "string", "enum": ["commit", "domcontentloaded", "load", "networkidle"], "description": "When to consider the page loaded."},
        "timeout": {"type": "number", "description": "Navigation timeout in seconds."},
    }, ["url"]),
    "browser_back": _schema({"session_id": _SESSION, "timeout": {"type": "number"}}),
    "browser_forward": _schema({"session_id": _SESSION, "timeout": {"type": "number"}}),
    "browser_refresh": _schema({"session_id": _SESSION, "timeout": {"type": "number"}}),
    "browser_stop": _schema({"session_id": _SESSION}),

    # ── Observation ────────────────────────────────────────────────────────
    "browser_snapshot": _schema({
        "session_id": _SESSION,
        "persist": {"type": "boolean", "description": "Save the full snapshot to a file when it is large (default true)."},
    }),
    "browser_extract": _schema({"session_id": _SESSION}),
    "browser_screenshot": _schema({"session_id": _SESSION, "full_page": {"type": "boolean", "description": "Capture the whole scrollable page."}}),
    "browser_vision": _schema({
        "session_id": _SESSION,
        "query": {"type": "string", "description": "What to look for on screen (optional)."},
        "screenshot": {"type": "boolean", "description": "Capture a screenshot too (default true)."},
    }),
    "browser_visual_find": _schema({
        "session_id": _SESSION,
        "text": {"type": "string", "description": "Visible text or label to locate visually."},
        "screenshot": {"type": "boolean"},
    }, ["text"]),
    "browser_visual_click": _schema({
        "session_id": _SESSION,
        "text": {"type": "string", "description": "Visible text or label to locate and click."},
    }, ["text"]),
    "browser_get_images": _schema({"session_id": _SESSION}),
    "browser_get_text": _schema({"session_id": _SESSION}),
    "browser_get_links": _schema({"session_id": _SESSION}),
    "browser_get_forms": _schema({"session_id": _SESSION}),
    "browser_get_accessibility_tree": _schema({"session_id": _SESSION}),
    "browser_get_dom": _schema({"session_id": _SESSION, "selector": {"type": "string", "description": "Optional CSS selector to scope the HTML."}}),

    # ── Interaction ────────────────────────────────────────────────────────
    "browser_click": _schema({
        "target": _TARGET, "session_id": _SESSION,
        "button": {"type": "string", "enum": ["left", "right", "middle"]},
        "double": {"type": "boolean"},
        "expect": {"type": "object", "description": "Optional expectations to verify, e.g. {urlChanged:true} or {elementAppears:'@e9'}."},
        "timeout": {"type": "number"},
    }, ["target"]),
    "browser_type": _schema({
        "target": _TARGET, "text": {"type": "string", "description": "Text to type. To fill a saved credential, pass its vault:// reference."},
        "session_id": _SESSION, "submit": {"type": "boolean", "description": "Press Enter after typing."},
        "clear": {"type": "boolean", "description": "Clear the field first (default true)."},
        "expect": {"type": "object"}, "timeout": {"type": "number"},
    }, ["target", "text"]),
    "browser_fill": _schema({
        "target": _TARGET, "text": {"type": "string"}, "session_id": _SESSION,
        "submit": {"type": "boolean"}, "clear": {"type": "boolean"},
    }, ["target", "text"]),
    "browser_select": _schema({
        "target": _TARGET, "value": {"description": "Option value(s) or label(s) to choose."},
        "session_id": _SESSION, "timeout": {"type": "number"},
    }, ["target", "value"]),
    "browser_check": _schema({"target": _TARGET, "session_id": _SESSION, "timeout": {"type": "number"}}, ["target"]),
    "browser_uncheck": _schema({"target": _TARGET, "session_id": _SESSION, "timeout": {"type": "number"}}, ["target"]),
    "browser_press": _schema({
        "key": {"type": "string", "description": "Key to press, e.g. 'Enter', 'Escape', 'Control+A'."},
        "target": _TARGET, "session_id": _SESSION, "timeout": {"type": "number"},
    }, ["key"]),
    "browser_hover": _schema({"target": _TARGET, "session_id": _SESSION, "timeout": {"type": "number"}}, ["target"]),
    "browser_scroll": _schema({
        "session_id": _SESSION, "dy": {"type": "integer", "description": "Vertical pixels to scroll (default 600)."},
        "dx": {"type": "integer", "description": "Horizontal pixels."},
        "selector": {"type": "string", "description": "Scroll a specific element into view instead."},
    }),
    "browser_drag": _schema({"source": _TARGET, "target": _TARGET, "session_id": _SESSION, "timeout": {"type": "number"}}, ["source", "target"]),

    # ── Waiting ────────────────────────────────────────────────────────────
    "browser_wait": _schema({"ms": {"type": "integer", "description": "Milliseconds to wait (max 60000)."}, "session_id": _SESSION}),
    "browser_wait_for_element": _schema({"target": _TARGET, "session_id": _SESSION, "state": {"type": "string", "enum": ["attached", "detached", "visible", "hidden"]}, "timeout": _WAIT_TIMEOUT}, ["target"]),
    "browser_wait_for_navigation": _schema({"session_id": _SESSION, "timeout": _WAIT_TIMEOUT}),
    "browser_wait_for_url": _schema({"pattern": {"type": "string", "description": "URL or glob pattern to wait for."}, "session_id": _SESSION, "timeout": _WAIT_TIMEOUT}, ["pattern"]),
    "browser_wait_for_network": _schema({"session_id": _SESSION, "timeout": _WAIT_TIMEOUT}),
    "browser_wait_for_download": _schema({"session_id": _SESSION, "timeout": _WAIT_TIMEOUT}),
    "browser_wait_for_popup": _schema({"session_id": _SESSION, "timeout": _WAIT_TIMEOUT}),
    "browser_wait_for_load_state": _schema({"state": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"]}, "session_id": _SESSION, "timeout": _WAIT_TIMEOUT}),
    "browser_wait_for_text": _schema({"text": {"type": "string", "description": "Text that should appear on the page."}, "session_id": _SESSION, "timeout": _WAIT_TIMEOUT}, ["text"]),

    # ── Tabs / windows ─────────────────────────────────────────────────────
    "browser_tabs": _schema({"session_id": _SESSION}),
    "browser_new_tab": _schema({"url": {"type": "string"}, "session_id": _SESSION}),
    "browser_switch_tab": _schema({"tab_id": {"type": "string", "description": "Tab id from browser_tabs."}, "session_id": _SESSION}, ["tab_id"]),
    "browser_close_tab": _schema({"tab_id": {"type": "string"}, "session_id": _SESSION}),
    "browser_new_window": _schema({"url": {"type": "string"}, "session_id": _SESSION}),
    "browser_switch_window": _schema({"tab_id": {"type": "string"}, "session_id": _SESSION}, ["tab_id"]),

    # ── Files ──────────────────────────────────────────────────────────────
    "browser_download": _schema({"target": _TARGET, "session_id": _SESSION, "timeout": _WAIT_TIMEOUT}, ["target"]),
    "browser_upload": _schema({
        "target": _TARGET, "files": {"type": "array", "items": {"type": "string"}, "description": "Workspace-relative file paths to upload."},
        "session_id": _SESSION, "timeout": {"type": "number"},
    }, ["target", "files"]),

    # ── Debugging ──────────────────────────────────────────────────────────
    "browser_console": _schema({"session_id": _SESSION, "level": {"type": "string"}, "limit": {"type": "integer"}}),
    "browser_network": _schema({"session_id": _SESSION, "kind": {"type": "string", "enum": ["request", "response", "failed"]}, "limit": {"type": "integer"}}),
    "browser_errors": _schema({"session_id": _SESSION, "limit": {"type": "integer"}}),
    "browser_evaluate": _schema({"expression": {"type": "string", "description": "JavaScript to run in the page (permission-gated)."}, "arg": {"description": "Optional JSON argument passed as the second evaluate argument."}, "session_id": _SESSION}, ["expression"]),
    "browser_cdp": _schema({"method": {"type": "string", "description": "A CDP command, e.g. 'Page.captureScreenshot'. Only Browser/Page/Runtime/Network/Target/DOM domains are allowed."}, "params": {"type": "object"}, "session_id": _SESSION}, ["method"]),
    "browser_exec": _schema({
        "program": {"type": ["string", "array"], "description": "A JSON list of steps, or a short Python-subset source string of browser.<op>(...) calls."},
        "session_id": _SESSION, "max_steps": {"type": "integer"}, "timeout": {"type": "number"},
    }, ["program"]),
    "browser_dialog": _schema({"action": {"type": "string", "enum": ["accept", "dismiss"]}, "text": {"type": "string", "description": "Text for a prompt dialog."}, "session_id": _SESSION}, ["action"]),

    # ── Storage / permissions ─────────────────────────────────────────────
    "browser_cookies": _schema({"session_id": _SESSION, "action": {"type": "string", "enum": ["list", "set", "clear"]}, "cookie": {"type": "object"}, "urls": {"type": "array", "items": {"type": "string"}}}),
    "browser_storage": _schema({"session_id": _SESSION}),
    "browser_permissions": _schema({"session_id": _SESSION, "grant": {"type": "array", "items": {"type": "string"}}, "revoke": {"type": "boolean"}}),

    # ── Sessions ──────────────────────────────────────────────────────────
    "browser_session_create": _schema({
        "url": {"type": "string"}, "provider": {"type": "string"}, "headless": {"type": "boolean"},
        "profile": {"type": "string"}, "persistent": {"type": "boolean"},
        "permissions": {"type": "object"}, "domains": {"type": "object"}, "viewport": {"type": "object"},
        "name": {"type": "string", "description": "A label for this session."},
    }),
    "browser_session_list": _schema({}),
    "browser_session_pause": _schema({"session_id": _SESSION}),
    "browser_session_resume": _schema({"session_id": _SESSION}),
    "browser_session_destroy": _schema({"session_id": _SESSION}),

    # ── Profiles ──────────────────────────────────────────────────────────
    "browser_profile_create": _schema({"name": {"type": "string"}}, ["name"]),
    "browser_profile_list": _schema({}),
    "browser_profile_use": _schema({"name": {"type": "string"}, "url": {"type": "string"}}, ["name"]),
    "browser_profile_delete": _schema({"name": {"type": "string"}}, ["name"]),

    # ── Vault ─────────────────────────────────────────────────────────────
    "browser_vault_list": _schema({"profile": {"type": "string"}}),
    "browser_vault_unlock": _schema({"reference": {"type": "string", "description": "A vault:// reference to verify is resolvable."}}),
    "browser_vault_fill": _schema({"target": _TARGET, "reference": {"type": "string", "description": "A vault:// reference, never a raw secret."}, "session_id": _SESSION, "submit": {"type": "boolean"}}, ["target", "reference"]),
    "browser_vault_enter_code": _schema({"target": _TARGET, "reference": {"type": "string"}, "session_id": _SESSION, "submit": {"type": "boolean"}}, ["target", "reference"]),
    "browser_vault_save_login": _schema({"reference": {"type": "string"}, "origin": {"type": "string"}, "username": {"type": "string"}, "kind": {"type": "string"}, "profile": {"type": "string"}}, ["reference"]),

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    "browser_request_human": _schema({"reason": {"type": "string", "description": "Why a person is needed (CAPTCHA, sign-in approval, etc.)."}, "session_id": _SESSION}, ["reason"]),
    "browser_pause": _schema({"session_id": _SESSION}),
    "browser_resume": _schema({"session_id": _SESSION}),

    # ── Device emulation ──────────────────────────────────────────────────
    "browser_emulate_device": _schema({"device": {"type": "string", "description": "A Playwright device name, e.g. 'iPhone 13'."}, "session_id": _SESSION}, ["device"]),
    "browser_set_viewport": _schema({"width": {"type": "integer"}, "height": {"type": "integer"}, "session_id": _SESSION}, ["width", "height"]),
    "browser_set_user_agent": _schema({"user_agent": {"type": "string"}, "session_id": _SESSION}, ["user_agent"]),
    "browser_set_locale": _schema({"locale": {"type": "string"}, "session_id": _SESSION}, ["locale"]),
    "browser_set_timezone": _schema({"timezone": {"type": "string"}, "session_id": _SESSION}, ["timezone"]),
    "browser_set_geolocation": _schema({"latitude": {"type": "number"}, "longitude": {"type": "number"}, "session_id": _SESSION}, ["latitude", "longitude"]),

    # ── Network interception (elevated) ───────────────────────────────────
    "browser_intercept": _schema({
        "action": {"type": "string", "enum": ["block", "headers", "throttle", "offline", "clear"]},
        "url_pattern": {"type": "string"}, "headers": {"type": "object"},
        "latency_ms": {"type": "integer"}, "throughput_kbps": {"type": "integer"},
        "session_id": _SESSION,
    }, ["action"]),
}

# Tool metadata: permission (registry-level), risk, effect, timeout, description.
# `permission="read"` tools still pass the browser POLICY ENGINE in the handler;
# the registry-level value only reflects whether the tool reaches the network or
# changes durable state on the machine.
TOOL_META: dict[str, dict[str, Any]] = {
    "browser_launch": {"risk": "medium", "timeout": 60_000, "effect": None, "desc":
        "Start an isolated Eclipse-managed browser. Returns a session id used by every other browser tool. "
        "Uses local Chromium by default; a private/local address always runs locally. Pass a vault profile to reuse a signed-in session."},
    "browser_close": {"risk": "low", "timeout": 20_000, "desc":
        "Close a browser session and release its resources. Never leaks a process."},
    "browser_status": {"risk": "low", "timeout": 15_000, "desc":
        "Report a session's state, current page, tabs, pending dialog and policy."},
    "browser_navigate": {"risk": "low", "timeout": 45_000, "desc":
        "Open a web address. The domain policy is checked first; a blocked address is refused, an approval domain asks a person."},
    "browser_back": {"risk": "low", "timeout": 30_000, "desc": "Go back one page in the session's history."},
    "browser_forward": {"risk": "low", "timeout": 30_000, "desc": "Go forward one page in the session's history."},
    "browser_refresh": {"risk": "low", "timeout": 30_000, "desc": "Reload the current page."},
    "browser_stop": {"risk": "low", "timeout": 15_000, "desc": "Stop loading the current page."},

    "browser_snapshot": {"risk": "low", "timeout": 30_000, "desc":
        "Read the page as an accessibility snapshot with stable references (@e1, @e2, …). This is the PRIMARY way to see a page; use it before acting. "
        "Large pages are truncated in the reply and saved in full to a file whose path is returned."},
    "browser_extract": {"risk": "low", "timeout": 30_000, "desc": "Extract structured page data: title, headings, and the main text."},
    "browser_screenshot": {"risk": "low", "timeout": 30_000, "desc": "Save a PNG screenshot of the page and return its path."},
    "browser_vision": {"risk": "low", "timeout": 45_000, "desc":
        "Visual fallback for canvas/graphical pages: capture a screenshot and map on-screen interactive elements with their positions."},
    "browser_visual_find": {"risk": "low", "timeout": 30_000, "desc": "Locate an element by its visible text/label and report its on-screen position."},
    "browser_visual_click": {"risk": "medium", "timeout": 30_000, "desc": "Click an element found by visible text/label (visual fallback)."},
    "browser_get_images": {"risk": "low", "timeout": 20_000, "desc": "List images on the page with their sources and alt text."},
    "browser_get_text": {"risk": "low", "timeout": 20_000, "desc": "Return the page's visible text."},
    "browser_get_links": {"risk": "low", "timeout": 20_000, "desc": "List the page's links with their text and targets."},
    "browser_get_forms": {"risk": "low", "timeout": 20_000, "desc": "Describe the page's forms and their fields (names, types, labels)."},
    "browser_get_accessibility_tree": {"risk": "low", "timeout": 20_000, "desc": "Return the raw accessibility tree of the page."},
    "browser_get_dom": {"risk": "low", "timeout": 20_000, "desc": "Return the page's HTML (optionally scoped by a selector). Prefer browser_snapshot unless raw HTML is genuinely needed."},

    "browser_click": {"risk": "medium", "timeout": 30_000, "desc":
        "Click an element by snapshot reference (@e4) or another locator. After the click the page is observed again and the result describes what changed. "
        "A control labelled like a payment, deletion or send is treated as destructive and may need approval."},
    "browser_type": {"risk": "low", "timeout": 30_000, "desc":
        "Type text into an element. Pass `submit` to press Enter afterwards. To fill a saved credential, pass its vault:// reference instead of the secret."},
    "browser_fill": {"risk": "low", "timeout": 30_000, "desc": "Fill an input with text (clears it first)."},
    "browser_select": {"risk": "low", "timeout": 30_000, "desc": "Choose an option in a dropdown."},
    "browser_check": {"risk": "low", "timeout": 30_000, "desc": "Tick a checkbox or radio button."},
    "browser_uncheck": {"risk": "low", "timeout": 30_000, "desc": "Untick a checkbox."},
    "browser_press": {"risk": "low", "timeout": 30_000, "desc": "Press a keyboard key, optionally on a specific element."},
    "browser_hover": {"risk": "low", "timeout": 30_000, "desc": "Move the pointer over an element (reveals menus/tooltips)."},
    "browser_scroll": {"risk": "low", "timeout": 20_000, "desc": "Scroll the page, or an element into view."},
    "browser_drag": {"risk": "low", "timeout": 30_000, "desc": "Drag one element onto another."},

    "browser_wait": {"risk": "low", "timeout": 65_000, "desc": "Pause for a fixed time (use sparingly; prefer a specific wait)."},
    "browser_wait_for_element": {"risk": "low", "timeout": 65_000, "desc": "Wait until an element appears, disappears or is visible."},
    "browser_wait_for_navigation": {"risk": "low", "timeout": 65_000, "desc": "Wait for the current navigation to complete."},
    "browser_wait_for_url": {"risk": "low", "timeout": 65_000, "desc": "Wait until the page reaches a URL pattern."},
    "browser_wait_for_network": {"risk": "low", "timeout": 65_000, "desc": "Wait until network activity settles."},
    "browser_wait_for_download": {"risk": "low", "timeout": 65_000, "desc": "Wait for a download to start and save it."},
    "browser_wait_for_popup": {"risk": "low", "timeout": 65_000, "desc": "Wait for a new window/tab to open."},
    "browser_wait_for_load_state": {"risk": "low", "timeout": 65_000, "desc": "Wait for a load state (load/domcontentloaded/networkidle)."},
    "browser_wait_for_text": {"risk": "low", "timeout": 65_000, "desc": "Wait until specific text appears on the page."},

    "browser_tabs": {"risk": "low", "timeout": 15_000, "desc": "List the session's open tabs and which is active."},
    "browser_new_tab": {"risk": "low", "timeout": 30_000, "desc": "Open a new tab, optionally at a URL."},
    "browser_switch_tab": {"risk": "low", "timeout": 15_000, "desc": "Make a tab the active one."},
    "browser_close_tab": {"risk": "low", "timeout": 20_000, "desc": "Close a tab (defaults to the active tab)."},
    "browser_new_window": {"risk": "low", "timeout": 30_000, "desc": "Open a new window (a new tab in this runtime)."},
    "browser_switch_window": {"risk": "low", "timeout": 15_000, "desc": "Switch to another window/tab."},

    "browser_download": {"risk": "low", "timeout": 60_000, "desc": "Download the file behind an element and save it; returns its path and checksum."},
    "browser_upload": {"risk": "medium", "effect": "write", "timeout": 45_000, "desc": "Upload one or more workspace files into a file input. Needs approval by default."},

    "browser_console": {"risk": "low", "timeout": 15_000, "desc": "Read the page's console messages (log/info/warning/error)."},
    "browser_network": {"risk": "low", "timeout": 15_000, "desc": "Inspect network requests, responses and failures."},
    "browser_errors": {"risk": "low", "timeout": 15_000, "desc": "Read uncaught page errors."},
    "browser_evaluate": {"risk": "medium", "effect": "external_action", "timeout": 30_000, "desc": "Run JavaScript in the page. Permission-gated; never host access."},
    "browser_cdp": {"risk": "medium", "effect": "external_action", "timeout": 30_000, "desc": "Send a controlled Chrome DevTools Protocol command (Browser/Page/Runtime/Network/Target/DOM only)."},
    "browser_exec": {"risk": "medium", "effect": "external_action", "timeout": 120_000, "desc":
        "Run a bounded, sandboxed program of browser steps in one call. Accepts a JSON step list or a short browser.<op>(...) script; no host access."},
    "browser_dialog": {"risk": "low", "timeout": 15_000, "desc": "Accept or dismiss a pending page dialog (alert/confirm/prompt)."},

    "browser_cookies": {"risk": "low", "timeout": 15_000, "desc": "List, set or clear cookies. Values are filtered from the model's view by default."},
    "browser_storage": {"risk": "low", "timeout": 15_000, "desc": "Read local/session storage for the current page."},
    "browser_permissions": {"risk": "low", "timeout": 15_000, "desc": "Grant or revoke browser permissions (camera, geolocation, notifications) for the session."},

    "browser_session_create": {"risk": "medium", "timeout": 60_000, "desc": "Create a new named, isolated browser session. Sessions never share cookies unless a profile is named."},
    "browser_session_list": {"risk": "low", "timeout": 15_000, "desc": "List open browser sessions and their state."},
    "browser_session_pause": {"risk": "low", "timeout": 15_000, "desc": "Pause a session (keeps it open, stops idle cleanup)."},
    "browser_session_resume": {"risk": "low", "timeout": 15_000, "desc": "Resume a paused or human-required session."},
    "browser_session_destroy": {"risk": "low", "timeout": 20_000, "desc": "Destroy a session and release its browser."},

    "browser_profile_create": {"risk": "low", "timeout": 20_000, "desc": "Create a persistent profile (saved cookies/storage) for signed-in reuse."},
    "browser_profile_list": {"risk": "low", "timeout": 15_000, "desc": "List saved browser profiles."},
    "browser_profile_use": {"risk": "low", "timeout": 60_000, "desc": "Open a session using a saved profile."},
    "browser_profile_delete": {"risk": "low", "timeout": 20_000, "desc": "Delete a saved profile and its stored session data."},

    "browser_vault_list": {"risk": "low", "timeout": 15_000, "desc": "List saved credential references (never the secrets themselves)."},
    "browser_vault_unlock": {"risk": "low", "timeout": 15_000, "desc": "Check that a credential reference can be resolved (does not reveal it)."},
    "browser_vault_fill": {"risk": "medium", "effect": "external_action", "timeout": 30_000, "desc": "Fill a field using a saved credential reference. The secret is never shown to the model."},
    "browser_vault_enter_code": {"risk": "medium", "effect": "external_action", "timeout": 30_000, "desc": "Enter a one-time code from a saved reference into a field."},
    "browser_vault_save_login": {"risk": "medium", "effect": "write", "timeout": 20_000, "desc": "Record a credential REFERENCE (never a plaintext secret) for a site."},

    "browser_request_human": {"risk": "low", "timeout": 15_000, "desc": "Pause and ask a person to complete a CAPTCHA/MFA/security check. Automation never bypasses these."},
    "browser_pause": {"risk": "low", "timeout": 15_000, "desc": "Pause a session."},
    "browser_resume": {"risk": "low", "timeout": 15_000, "desc": "Resume a paused or human-required session."},

    "browser_emulate_device": {"risk": "low", "timeout": 20_000, "desc": "Emulate a mobile device profile."},
    "browser_set_viewport": {"risk": "low", "timeout": 15_000, "desc": "Resize the browser viewport."},
    "browser_set_user_agent": {"risk": "low", "timeout": 15_000, "desc": "Set the session's user-agent for new pages."},
    "browser_set_locale": {"risk": "low", "timeout": 15_000, "desc": "Set the session's locale."},
    "browser_set_timezone": {"risk": "low", "timeout": 15_000, "desc": "Set the session's timezone."},
    "browser_set_geolocation": {"risk": "low", "timeout": 15_000, "desc": "Set the session's geolocation (needs the geolocation permission)."},

    "browser_intercept": {"risk": "high", "effect": "external_action", "timeout": 30_000, "desc": "Advanced network control: block requests, modify headers, throttle, or go offline. Elevated and approval-gated."},
}

# Tools that require an explicit browser session to already exist. Everything
# else falls back to the most recently active session when none is named.
REQUIRES_SESSION: frozenset[str] = frozenset(
    name for name in INPUT_SCHEMAS
    if name
    not in {
        "browser_launch", "browser_session_create", "browser_session_list",
        "browser_profile_create", "browser_profile_list", "browser_profile_use",
        "browser_profile_delete", "browser_vault_list", "browser_vault_unlock",
        "browser_vault_save_login",
    }
)

ALL_TOOL_NAMES: tuple[str, ...] = tuple(INPUT_SCHEMAS.keys())

# Tools whose effect is a durable write or an external action (the browser
# authorizer admits them; the handler still runs the policy engine).
EFFECTFUL_TOOLS: tuple[str, ...] = tuple(
    name for name, meta in TOOL_META.items() if meta.get("effect")
)

__all__ = ["ALL_TOOL_NAMES", "EFFECTFUL_TOOLS", "INPUT_SCHEMAS", "REQUIRES_SESSION", "TOOL_META"]

# A couple of pydantic models used by handlers for stricter local validation.
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402


class LaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    url: str | None = None
    provider: str | None = None
    headless: bool | None = None
    profile: str | None = None
    persistent: bool | None = None
    viewport: dict[str, int] | None = None
    permissions: dict[str, str] | None = None
    domains: dict[str, list[str]] | None = None


class ExecInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: Any
    session_id: str | None = Field(default=None, alias="session_id")
    max_steps: int | None = Field(default=None, alias="max_steps")
    timeout: float | None = None
