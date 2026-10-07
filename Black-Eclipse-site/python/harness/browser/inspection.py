"""Non-interacting inspection operations for a BrowserSession.

`find` describes the elements a locator matches (with their snapshot references)
without acting on them, so the agent can disambiguate before clicking. `highlight`
briefly outlines an element. Both are extracted here so `session.py` stays under
its size ceiling; the session methods delegate to these functions.
"""

from __future__ import annotations

from typing import Any

from .errors import BrowserSessionError
from .resolver import Target


def _snapshot_ref_for(session: Any, role: str, name: str) -> str:
    """The snapshot ref whose role+name match a live element, or ""."""
    snapshot = session.snapshots.latest
    if snapshot is None or not name:
        return ""
    wanted_role = (role or "").lower()
    wanted_name = name.strip().lower()
    for element in snapshot.elements.values():
        if element.name.strip().lower() != wanted_name:
            continue
        if wanted_role in (element.role, "", "generic") or element.role == wanted_role:
            return element.ref
    return ""


async def find(session: Any, raw_target: Any, *, max_results: int = 20) -> list[dict[str, Any]]:
    """Find elements matching a locator and describe them (no interaction)."""
    target = Target.parse(raw_target)
    page = session.page()
    found = session.resolver._locator_for(page, target)  # noqa: SLF001 - shared resolution
    if found is None:
        return []
    locator = found[0]
    try:
        count = await locator.count()
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    for index in range(min(count, max(1, max_results))):
        item = locator.nth(index)
        entry: dict[str, Any] = {"index": index}
        try:
            entry["text"] = ((await item.inner_text()) or "").strip()[:200]
        except Exception:  # noqa: BLE001
            entry["text"] = ""
        try:
            entry["role"] = await item.evaluate(
                "el => el.getAttribute('role') || el.tagName.toLowerCase()"
            )
        except Exception:  # noqa: BLE001
            entry["role"] = ""
        try:
            entry["name"] = await item.evaluate(
                "el => el.getAttribute('aria-label') || el.getAttribute('name') || "
                "(el.labels && el.labels[0] && el.labels[0].innerText) || "
                "(el.tagName === 'INPUT' ? el.placeholder : '') || (el.innerText || '').trim()"
            )
        except Exception:  # noqa: BLE001
            entry["name"] = entry.get("text", "")
        entry["ref"] = _snapshot_ref_for(session, entry.get("role"), entry.get("name") or entry.get("text"))
        out.append(entry)
    return out


async def highlight(session: Any, raw_target: Any) -> dict[str, Any]:
    """Briefly outline an element (a transient visual aid), without clicking."""
    resolution = await session.resolve(raw_target)
    locator = resolution.locator.first
    await session._scroll_into_view(locator)  # noqa: SLF001 - shared helper
    try:
        await locator.evaluate(
            "el => { const p = el.style.outline; el.style.outline = '3px solid #ff2d55'; "
            "setTimeout(() => { el.style.outline = p; }, 2500); }"
        )
    except Exception as exc:  # noqa: BLE001
        raise BrowserSessionError(
            "Eclipse couldn't highlight that element.", session_id=session.id,
            action="highlight", metadata={"error": str(exc)[:200]},
        ) from exc
    return {"highlighted": True, "resolution": resolution.to_dict()}


__all__ = ["find", "highlight"]
