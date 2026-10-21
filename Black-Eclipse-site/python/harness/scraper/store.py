"""Where a collected scraper goes: the rows into the vault, the program on disk.

Two homes, one rule each:

  * the ROWS go to the front door (`POST /api/scraper/datasets`), which writes
    them into `CustomDatasetRecord` — the same store the dataset wizard uses.
    They are labelled `SCRAPER`: collected page data, never a verified source,
    and never a canonical market table;
  * the PROGRAM is saved beside them under `.black-eclipse/scrapers/`, so the
    same collection can be run again without writing it a second time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso

MAX_SCRAPERS = 100
_NAME_RE = re.compile(r"[^a-z0-9_]+")

#: The rows a single collection may store (the vault's own cap).
MAX_ROWS = 5_000


def slug(value: str) -> str:
    """A lower_snake_case name that is safe as a file name and a dataset name."""
    text = _NAME_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return text[:64] or "scraper"


async def persist_rows(
    bridge: Any,
    *,
    name: str,
    description: str,
    source_url: str,
    purpose: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Store the collected rows in the vault. Returns the store's own report.

    A bridge that cannot write (no `post_json`) is reported as unavailable —
    never as "stored".
    """
    post = getattr(bridge, "post_json", None)
    if post is None:
        return {"ok": False, "error": "the vault cannot accept collected rows from here"}
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS]
    payload = {
        "name": slug(name),
        "description": description,
        "sourceUrl": source_url,
        "purpose": purpose,
        "columns": list(columns),
        "rows": [
            {str(key): ("" if value is None else str(value)) for key, value in row.items()}
            for row in rows
        ],
    }
    try:
        result = await post("/api/scraper/datasets", payload)
    except Exception as exc:  # noqa: BLE001 - a transport failure is an unavailable store
        return {"ok": False, "error": str(exc)}
    if not isinstance(result, dict):
        return {"ok": False, "error": "the vault returned an unreadable answer"}
    return result


# ── The saved program ────────────────────────────────────────────────────────


def scraper_root(ctx: Any) -> Optional[Path]:
    """`.black-eclipse/scrapers/` for this workspace, or None when there is none."""
    root = getattr(getattr(ctx, "workspace", None), "root", None)
    if not root:
        from ..code.workspace import default_root  # noqa: PLC0415

        root = default_root()
    if not root:
        return None
    return Path(root) / ".black-eclipse" / "scrapers"


def save_scraper(
    ctx: Any,
    *,
    name: str,
    program: str,
    target_url: str,
    columns: list[str],
    purpose: str = "",
    dataset: Optional[str] = None,
) -> Optional[str]:
    """Save the scraper program so it can be run again. Returns its id."""
    root = scraper_root(ctx)
    if root is None:
        return None
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    scraper_id = slug(name)
    record = {
        "id": scraper_id,
        "name": scraper_id,
        "purpose": purpose,
        "targetUrl": target_url,
        "columns": list(columns),
        "dataset": dataset,
        "program": program,
        "savedAt": now_iso(),
    }
    try:
        (root / f"{scraper_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError:
        return None
    _prune(root)
    return scraper_id


def load_scraper(ctx: Any, scraper_id: str) -> Optional[dict[str, Any]]:
    """The saved scraper with this id, or None."""
    root = scraper_root(ctx)
    if root is None:
        return None
    path = root / f"{slug(scraper_id)}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def list_scrapers(ctx: Any) -> list[dict[str, Any]]:
    """Every saved scraper, newest first."""
    root = scraper_root(ctx)
    if root is None or not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        out.append({
            "id": raw.get("id") or path.stem,
            "name": raw.get("name") or path.stem,
            "purpose": raw.get("purpose") or "",
            "targetUrl": raw.get("targetUrl") or "",
            "columns": raw.get("columns") or [],
            "dataset": raw.get("dataset"),
            "savedAt": raw.get("savedAt"),
        })
    out.sort(key=lambda item: str(item.get("savedAt") or ""), reverse=True)
    return out[:MAX_SCRAPERS]


def _prune(root: Path) -> None:
    """Keep the folder bounded: the newest MAX_SCRAPERS programs survive."""
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return
    for path in paths[:-MAX_SCRAPERS]:
        try:
            path.unlink()
        except OSError:
            pass


__all__ = [
    "MAX_ROWS",
    "list_scrapers",
    "load_scraper",
    "persist_rows",
    "save_scraper",
    "scraper_root",
    "slug",
]
