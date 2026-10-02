"""The chat capability view (Phase 14 §6.4).

Derives, from a run's persisted verification blob, the small view the chat
surface renders for a coding turn: the profile it was bound to, an i18n headline
KEY (never a category, never a mechanism word) and the Phase-4 verification blob
it composes. Pure and side-effect free; no new persisted column — the profile
rides INSIDE the existing `codeVerification` blob (`autonomy`/`workspaceId`).

`headline` is an i18n key; the front door resolves it. The two profiles are the
only ones a chat turn can carry (`plan_only` | `edit_verify`); anything else
yields no capability view.
"""

from __future__ import annotations

from typing import Any, Optional

_HEADLINE = {
    "edit_verify": "code.chat.headline.editVerify",
    "plan_only": "code.chat.headline.planOnly",
}


def capability_from_verification(blob: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The chat capability view for a run, or None for an ordinary turn.

    None when the blob is absent, or when it carries no chat code profile (an
    ordinary finance run). The `verification` sub-object is the Phase-4 blob with
    the profile keys removed, so the panel composes exactly what it did before.
    """
    if not isinstance(blob, dict):
        return None
    autonomy = blob.get("autonomy")
    if autonomy not in _HEADLINE:
        return None
    verification = {k: v for k, v in blob.items() if k not in ("autonomy", "workspaceId")}
    return {
        "kind": "code",
        "profile": autonomy,
        "headline": _HEADLINE[autonomy],
        "verification": verification or None,
    }


__all__ = ["capability_from_verification"]
