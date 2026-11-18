"""Order ownership: the magic tag that makes a bot's orders findable.

Every Eclipse order carries a positive `magic`; the kill switch matches ONLY that
magic, so acting on one bot never touches a human's trade or another
connection's. A missing magic used to mean "un-killable" - and the kill switch
correctly refused rather than guessing.
"""

from __future__ import annotations

import zlib
from typing import Any, Optional

__all__ = ["default_magic", "with_ownership_magic"]


def default_magic(label: str) -> int:
    """A stable non-zero magic derived from the connection's label."""
    return 100_000 + (zlib.crc32(str(label or "").encode("utf-8")) % 800_000)


def with_ownership_magic(
    config: Optional[dict[str, Any]], label: str,
) -> tuple[dict[str, Any], int]:
    """Return the config and the magic, adding a default only when absent.

    An explicit positive magic is never overridden: the operator may need it to
    match an existing EA or an earlier Eclipse session.
    """
    out = dict(config or {})
    magic = int(float(out.get("magic") or 0) or 0)
    if magic <= 0:
        magic = default_magic(label)
        out["magic"] = magic
    return out, magic
