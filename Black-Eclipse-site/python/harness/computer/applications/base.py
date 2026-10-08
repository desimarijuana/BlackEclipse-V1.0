"""The ApplicationAdapter contract.

An adapter is a KNOWLEDGE record about one application (or a class of them): how
to recognise it, its known controls, its keyboard shortcuts, how to detect its
state, how to verify an action's effect, which actions are safe vs risky, and its
known failure modes. It is data + tiny pure helpers — never a second execution
engine. The core consults an adapter to raise grounding/verification quality; if
no adapter matches, the generic adapter is used and everything still works.
"""

from __future__ import annotations

from typing import Any, Optional

from ..grounding.matching import GroundingQuery


class ApplicationAdapter:
    """Base adapter. Subclasses fill in the knowledge."""

    id = "generic"
    name = "Generic application"
    # Lowercased substrings matched against a window's process/executable name.
    executables: tuple[str, ...] = ()
    # Lowercased substrings matched against a window title.
    title_patterns: tuple[str, ...] = ()
    # Known semantic controls → how to find them. Keys are intents, values are
    # {name, role, shortcut}.
    controls: dict[str, dict[str, str]] = {}
    shortcuts: dict[str, str] = {}
    # Text/state markers that indicate the app is busy/loading/ready.
    busy_markers: tuple[str, ...] = ()
    ready_markers: tuple[str, ...] = ()
    # Actions this adapter considers safe vs risky (risk → higher approval).
    safe_actions: tuple[str, ...] = ("observe", "navigate", "copy", "select")
    risky_actions: tuple[str, ...] = ()
    # Known failure modes to watch for.
    failure_modes: tuple[str, ...] = ()
    # Whether a real structured integration exists (prefer it over CUA).
    has_native_api: bool = False
    # Verification against a real application. The shipped adapters are KNOWLEDGE
    # records (unverified); the live rig marks one verified only after driving the
    # real app, with a note naming the build. Never set true by hand.
    verified: bool = False
    verified_note: str = ""

    def matches(self, *, app_name: str = "", executable: str = "", title: str = "") -> bool:
        app_l = (app_name or "").lower()
        exe_l = (executable or "").lower()
        title_l = (title or "").lower()
        for needle in self.executables:
            if needle and (needle in app_l or needle in exe_l):
                return True
        for pattern in self.title_patterns:
            if pattern and pattern in title_l:
                return True
        return False

    def semantic_selector(self, query: GroundingQuery) -> Optional[dict[str, str]]:
        """A known control for an intent, or None. Used by the grounder rung 2."""
        intent = (query.intent or query.name or "").strip().lower()
        if intent in self.controls:
            return dict(self.controls[intent])
        for key, control in self.controls.items():
            if key in intent or intent in control.get("name", "").lower():
                return dict(control)
        return None

    def shortcut_for(self, action: str) -> Optional[str]:
        return self.shortcuts.get(action)

    def is_risky(self, action: str) -> bool:
        return action in self.risky_actions

    def looks_busy(self, text: str) -> bool:
        """Whether a screen/title reading matches a known busy marker."""
        haystack = (text or "").lower()
        return any(marker in haystack for marker in self.busy_markers)

    def looks_ready(self, text: str) -> bool:
        """Whether a screen/title reading matches a known ready marker."""
        haystack = (text or "").lower()
        return any(marker in haystack for marker in self.ready_markers)

    def mark_verified(self, note: str) -> None:
        """Record that a live rig drove this adapter against the real app.

        Only a rig (or an operator decision) should call this; it is never set by
        construction, so `verified` stays an honest claim.
        """
        self.verified = True
        self.verified_note = note

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "executables": list(self.executables), "titlePatterns": list(self.title_patterns),
            "controls": list(self.controls), "shortcuts": self.shortcuts,
            "hasNativeApi": self.has_native_api,
            "verified": self.verified, "verifiedNote": self.verified_note,
            "riskyActions": list(self.risky_actions), "failureModes": list(self.failure_modes),
        }


class GenericAdapter(ApplicationAdapter):
    id = "generic"
    name = "Generic application"
    has_native_api = False


__all__ = ["ApplicationAdapter", "GenericAdapter"]
