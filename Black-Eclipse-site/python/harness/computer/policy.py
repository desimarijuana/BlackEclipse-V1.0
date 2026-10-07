"""The Computer Use policy engine — the ONE authority for permissions/risk.

Nothing here captures a screen or moves a pointer. It answers, deterministically:
may this run perform this action, against this application, in this session?

Design (mirrors `browser/policy.py` and `code/policy.py`):

  * ``PERMISSIONS``       — the closed permission vocabulary.
  * ``LEVELS``            — ALLOW / DENY / ASK.
  * ``RISK_LEVELS``       — READ / LOW / MEDIUM / HIGH / CRITICAL.
  * ``DEFAULT_PERMISSIONS`` — fail-closed defaults (screenshot allow; type ask;
                              submit/financial deny).
  * ``AppPolicy``         — allowed / denied application lists.
  * ``classify_action``   — the risk band for an action name.

A decision is DATA plus small pure functions. Every later phase calls this; none
re-implements it. Financial mutations are escalated to CRITICAL and are handled by
``finance/firewall.py`` on top of this — never bypassed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Permission vocabulary ────────────────────────────────────────────────────

ALLOW = "allow"
DENY = "deny"
ASK = "ask"
LEVELS = (ALLOW, DENY, ASK)

PERMISSIONS: tuple[str, ...] = (
    "observe",          # screenshot / accessibility read
    "list",             # windows / applications / displays
    "click",
    "type",
    "key",
    "set_value",
    "scroll",
    "drag",
    "launch_app",       # open a program
    "close_app",        # close a program
    "window_control",   # minimize/maximize/move/close a window
    "clipboard_read",
    "clipboard_write",
    "foreground",       # escalate to foreground input (steals focus)
    "finance_read",
    "finance_mutate",   # buy/sell/order/transfer/withdraw
    "take_screenshot_sensitive",
)

# Fail-closed defaults. Observations are permissive (they change nothing);
# anything that moves input, focuses the user's screen or touches money is gated.
DEFAULT_PERMISSIONS: dict[str, str] = {
    "observe": ALLOW,
    "list": ALLOW,
    "click": ASK,
    "type": ASK,
    "key": ASK,
    "set_value": ASK,
    "scroll": ASK,
    "drag": ASK,
    "launch_app": ASK,
    "close_app": ASK,
    "window_control": ASK,
    "clipboard_read": ASK,
    "clipboard_write": ASK,
    "foreground": ASK,
    "finance_read": ALLOW,
    "finance_mutate": DENY,
    "take_screenshot_sensitive": ASK,
}

# ── Risk classification ──────────────────────────────────────────────────────

READ = "READ"
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
RISK_LEVELS = (READ, LOW, MEDIUM, HIGH, CRITICAL)

# Action name → risk band. The names are the agent-facing action verbs plus the
# financial mutation vocabulary. Unknown actions default to MEDIUM (fail-safe).
ACTION_RISK: dict[str, str] = {
    # Read
    "capture": READ, "screenshot": READ, "list_apps": READ, "list_windows": READ,
    "list_displays": READ, "status": READ, "capabilities": READ, "observe": READ,
    "window_list": READ, "window_get": READ, "application_list": READ,
    "application_get_info": READ, "mouse_position": READ, "clipboard_read": READ,
    # Low — non-destructive input
    "mouse_move": LOW, "mouse_move_relative": LOW, "scroll": LOW,
    "mouse_scroll": LOW, "mouse_scroll_horizontal": LOW, "window_focus": LOW,
    "window_activate": LOW, "window_minimize": LOW, "window_maximize": LOW,
    "window_restore": LOW, "window_move": LOW, "window_resize": LOW, "wait": LOW,
    # Medium — input that changes state / opens things
    "click": MEDIUM, "double_click": MEDIUM, "right_click": MEDIUM,
    "middle_click": MEDIUM, "mouse_click": MEDIUM, "mouse_double_click": MEDIUM,
    "mouse_right_click": MEDIUM, "mouse_middle_click": MEDIUM,
    "mouse_down": MEDIUM, "mouse_up": MEDIUM, "drag": MEDIUM, "mouse_drag": MEDIUM,
    "type": MEDIUM, "key": MEDIUM, "set_value": MEDIUM, "keyboard_type": MEDIUM,
    "keyboard_press": MEDIUM, "keyboard_hotkey": MEDIUM, "launch_app": MEDIUM,
    "application_launch": MEDIUM, "clipboard_write": MEDIUM,
    # High
    "close_app": HIGH, "application_close": HIGH, "window_close": HIGH,
    "delete_file": HIGH, "foreground": HIGH, "application_restart": HIGH,
    # Critical — financial mutation
    "buy": CRITICAL, "sell": CRITICAL, "short": CRITICAL, "cover": CRITICAL,
    "submit_order": CRITICAL, "cancel_order": CRITICAL, "modify_order": CRITICAL,
    "transfer": CRITICAL, "withdraw": CRITICAL, "deposit": CRITICAL,
    "payment": CRITICAL, "account_change": CRITICAL, "finance_mutate": CRITICAL,
}

# Action names that are financial mutations. Owned here so the firewall and the
# risk classifier agree.
FINANCIAL_MUTATIONS: frozenset[str] = frozenset({
    "buy", "sell", "short", "cover", "submit_order", "cancel_order",
    "modify_order", "transfer", "withdraw", "deposit", "payment", "account_change",
})


def classify_action(action: str) -> str:
    """The risk band for an action name. Unknown ⇒ MEDIUM (fail-safe)."""
    return ACTION_RISK.get((action or "").strip().lower(), MEDIUM)


def is_financial_mutation(action: str) -> bool:
    return (action or "").strip().lower() in FINANCIAL_MUTATIONS


@dataclass
class PermissionDecision:
    permission: str
    level: str
    reason: str
    allowed: bool
    requires_approval: bool
    risk: str = MEDIUM
    code: str = "OK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission": self.permission, "level": self.level, "reason": self.reason,
            "allowed": self.allowed, "requiresApproval": self.requires_approval,
            "risk": self.risk, "code": self.code,
        }


# ── Application policy ───────────────────────────────────────────────────────


def _app_matches(name: str, pattern: str) -> bool:
    name_l = (name or "").lower()
    pattern_l = (pattern or "").strip().lower().lstrip("*.")
    if not pattern_l:
        return False
    return name_l == pattern_l or pattern_l in name_l


@dataclass
class AppPolicy:
    """Allowed / denied application lists.

    Empty `allowed` means "any application not explicitly denied". A denied app is
    never driven; an app not on a non-empty allow list is refused.
    """

    allowed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)

    def check_app(self, name: str) -> PermissionDecision:
        for pattern in self.denied:
            if _app_matches(name, pattern):
                return PermissionDecision(
                    "observe", DENY, f"Eclipse isn't allowed to operate {name}.",
                    allowed=False, requires_approval=False, code="COMPUTER_APP_DENIED", risk=HIGH,
                )
        if self.allowed and not any(_app_matches(name, p) for p in self.allowed):
            return PermissionDecision(
                "observe", DENY, f"{name} isn't on Eclipse's approved application list.",
                allowed=False, requires_approval=False, code="COMPUTER_APP_NOT_ALLOWED", risk=HIGH,
            )
        return PermissionDecision("observe", ALLOW, "allowed", allowed=True, requires_approval=False)

    def check_action(self, action: str) -> Optional[PermissionDecision]:
        """A hard block on a prohibited action, or an action absent from a
        non-empty allowlist. Returns None only when the action is permitted."""
        lowered = (action or "").strip().lower()
        if lowered in {a.lower() for a in self.prohibited_actions}:
            return PermissionDecision(
                lowered, DENY, f"Eclipse isn't permitted to {lowered.replace('_', ' ')}.",
                allowed=False, requires_approval=False, code="COMPUTER_ACTION_PROHIBITED",
                risk=classify_action(lowered),
            )
        if self.allowed_actions:
            allowed = {a.lower() for a in self.allowed_actions}
            if lowered not in allowed:
                return PermissionDecision(
                    lowered, DENY, f"Eclipse isn't permitted to {lowered.replace('_', ' ')} in this task.",
                    allowed=False, requires_approval=False, code="COMPUTER_ACTION_NOT_ALLOWED",
                    risk=classify_action(lowered),
                )
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowedApps": list(self.allowed), "deniedApps": list(self.denied),
            "allowedActions": list(self.allowed_actions),
            "prohibitedActions": list(self.prohibited_actions),
        }


@dataclass
class ComputerPolicy:
    permissions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PERMISSIONS))
    apps: AppPolicy = field(default_factory=AppPolicy)
    mode: str = "background"
    allow_foreground: bool = True
    finance_mode: str = "read_only"

    def permission_level(self, permission: str) -> str:
        if permission not in PERMISSIONS:
            return DENY
        if permission == "finance_mutate" and self.finance_mode == "read_only":
            return DENY
        return self.permissions.get(permission, DENY)

    def evaluate(self, permission: str, *, action: str = "", app: str = "") -> PermissionDecision:
        if permission not in PERMISSIONS:
            return PermissionDecision(
                permission, DENY, "Eclipse doesn't recognise that kind of desktop action.",
                allowed=False, requires_approval=False, code="COMPUTER_PERMISSION_DENIED",
            )
        if permission == "foreground" and not self.allow_foreground:
            return PermissionDecision(
                permission, DENY, "Foreground control isn't available in this task.",
                allowed=False, requires_approval=False, code="COMPUTER_PERMISSION_DENIED", risk=HIGH,
            )
        if app:
            app_decision = self.apps.check_app(app)
            if not app_decision.allowed:
                return app_decision
        if action:
            blocked = self.apps.check_action(action)
            if blocked is not None:
                return blocked
        level = self.permission_level(permission)
        risk = classify_action(action) if action else MEDIUM
        if level == ALLOW:
            return PermissionDecision(permission, ALLOW, "allowed", allowed=True, requires_approval=False, risk=risk)
        if level == ASK:
            return PermissionDecision(
                permission, ASK, f"{_plain(permission)} needs your approval.",
                allowed=False, requires_approval=True, code="COMPUTER_APPROVAL_REQUIRED", risk=risk,
            )
        return PermissionDecision(
            permission, DENY, f"{_plain(permission)} isn't available in this task.",
            allowed=False, requires_approval=False, code="COMPUTER_PERMISSION_DENIED", risk=risk,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "permissions": {p: self.permission_level(p) for p in PERMISSIONS},
            "apps": self.apps.to_dict(), "mode": self.mode,
            "allowForeground": self.allow_foreground, "financeMode": self.finance_mode,
        }


_PLAIN = {
    "observe": "Reading the screen",
    "list": "Listing windows and applications",
    "click": "Clicking on the desktop",
    "type": "Typing on the desktop",
    "key": "Sending a key",
    "set_value": "Changing a control's value",
    "scroll": "Scrolling",
    "drag": "Dragging",
    "launch_app": "Opening an application",
    "close_app": "Closing an application",
    "window_control": "Changing a window",
    "clipboard_read": "Reading the clipboard",
    "clipboard_write": "Writing the clipboard",
    "foreground": "Taking over the foreground",
    "finance_read": "Reading financial data on screen",
    "finance_mutate": "Placing a financial action",
    "take_screenshot_sensitive": "Capturing a sensitive screen",
}


def _plain(permission: str) -> str:
    return _PLAIN.get(permission, "That desktop action")


def default_policy() -> ComputerPolicy:
    from .config import computer_config  # noqa: PLC0415

    cfg = computer_config()
    return ComputerPolicy(
        apps=AppPolicy(
            allowed=list(cfg.allowed_apps), denied=list(cfg.denied_apps),
            allowed_actions=list(cfg.allowed_actions), prohibited_actions=list(cfg.prohibited_actions),
        ),
        mode=cfg.mode, finance_mode=cfg.finance_mode,
    )


__all__ = [
    "ACTION_RISK", "ALLOW", "ASK", "AppPolicy", "CRITICAL", "ComputerPolicy",
    "DEFAULT_PERMISSIONS", "DENY", "FINANCIAL_MUTATIONS", "HIGH", "LEVELS", "LOW",
    "MEDIUM", "PERMISSIONS", "PermissionDecision", "READ", "RISK_LEVELS",
    "classify_action", "default_policy", "is_financial_mutation",
]
