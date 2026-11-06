"""A project's own write denylist — narrow-only (Phase 24 / P6).

A project may protect paths Eclipse must never write, even at `edit_verify`:
generated code, migrations, lockfiles, a vendored directory. The file lives where
the other project overrides do:

    <project>/.black-eclipse/policy.json
    { "denyPaths": ["src/generated/", "**/*.lock", "prisma/migrations/"] }

Rules:

  * **Narrow-only.** This can only ADD protected paths. It can never widen the
    autonomy profile, the command vocabulary or the global protected set.
  * **A pattern is data, never a shell.** A trailing `/` is a prefix; `*`, `?`,
    `[` use `fnmatch`; anything else is an exact relative path. An absolute path
    or a `..` component is ignored.
  * **Unreadable is empty.** A broken file protects nothing and is reported as a
    warning by `load_patterns`, so writes are never blocked by surprise.
"""

from __future__ import annotations

import fnmatch
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

POLICY_RELPATH = Path(".black-eclipse") / "policy.json"
MAX_PATTERNS = 50
MAX_PATTERN_CHARS = 200


def _normalize(value: Any) -> Optional[str]:
    text = str(value or "").strip().replace("\\", "/")
    if not text or len(text) > MAX_PATTERN_CHARS:
        return None
    if text.startswith("/") or ":" in text.split("/")[0]:
        return None
    if any(part == ".." for part in text.split("/")):
        return None
    return text.lstrip("./")


@lru_cache(maxsize=32)
def _patterns_for(root: str, mtime_ns: int) -> tuple[str, ...]:
    del mtime_ns  # part of the cache key only
    try:
        raw = json.loads((Path(root) / POLICY_RELPATH).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ()
    if not isinstance(raw, dict):
        return ()
    items = raw.get("denyPaths")
    if not isinstance(items, list):
        return ()
    parsed: list[str] = []
    for item in items[:MAX_PATTERNS]:
        pattern = _normalize(item)
        if pattern and pattern not in parsed:
            parsed.append(pattern)
    return tuple(parsed)


def load_patterns(root: Path | str | None) -> tuple[str, ...]:
    """The project's deny patterns (empty when absent, invalid or unreadable)."""
    if root is None:
        return ()
    path = Path(root) / POLICY_RELPATH
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return ()
    return _patterns_for(str(root), mtime)


def matches(pattern: str, rel: str) -> bool:
    """One pattern against one normalized relative path."""
    if pattern.endswith("/"):
        prefix = pattern.rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(rel, pattern)
    return rel == pattern


def is_denied(root: Path | str | None, rel: str) -> bool:
    """True when this project protects `rel` from writes."""
    if root is None:
        return False
    normalized = os.path.normpath(str(rel)).replace("\\", "/")
    if normalized.startswith("../") or normalized == "..":
        return True  # an escape is always refused, policy or not
    return any(matches(pattern, normalized) for pattern in load_patterns(root))


def reset_cache() -> None:
    """Test seam: forget cached patterns (a test rewrites the same file)."""
    _patterns_for.cache_clear()


__all__ = [
    "POLICY_RELPATH",
    "is_denied",
    "load_patterns",
    "matches",
    "reset_cache",
]
