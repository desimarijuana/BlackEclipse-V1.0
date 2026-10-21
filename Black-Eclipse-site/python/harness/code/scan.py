"""Walk a workspace's text files - ignore-aware and bounded.

Round 3 / W5 (ADR-H284). This was `code/tools.py::_iter_scan_files`, and it
lived in the ratcheted core file because it happened to be written there first.
It is a SCAN, not a policy, so it has its own module now.

**What it guarantees.**

- The base may name a FOLDER or a SINGLE FILE. A model often points at the one
  file it means, and refusing that (`NOT_A_DIRECTORY`/`NOT_FOUND`) was a real
  incident - so a file is accepted and yielded on its own.
- IGNORED and PROTECTED paths are skipped, and binary files are never yielded.
- The walk is BOUNDED three ways: a file count, a total byte count, and (in the
  caller) a wall-clock deadline. A walk that cannot finish is stopped, not
  left running.

**Why it is not merged with `code/fs/search.py::_iter_files`.** That walker has
a different contract: it requires a DIRECTORY, it is hidden-file aware, and it
carries no byte budget. Merging them would change the fs search's behaviour
(one of them would silently start skipping hidden files, or start refusing a
single-file root the search deliberately accepts). Two walkers with two
contracts is honest; one walker with the union of both contracts is a
behaviour change disguised as a cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional, Tuple

from . import policy
from .workspace import (
    MAX_SCAN_BYTES,
    MAX_SCAN_FILES,
    ResolvedWorkspace,
    confine,
    is_binary,
)


def iter_scan_files(ws: ResolvedWorkspace, base: str) -> Iterator[Tuple[str, Path]]:
    """Yield `(rel, Path)` for text files under `base`, ignore-aware and bounded.

    `base` may name a single file too: the model often points at the one file it
    means, and refusing that (`NOT_A_DIRECTORY`/`NOT_FOUND`) was a real incident.
    """
    start = confine(ws, base or ".")
    if start.is_file():
        rel = start.relative_to(ws.root).as_posix()
        if not policy.is_ignored(rel) and not is_binary(start):
            yield rel, start
        return
    if not start.is_dir():
        from .workspace import WorkspaceDenial  # noqa: PLC0415

        raise WorkspaceDenial("NOT_FOUND", "That isn't a folder Eclipse can search.", path=base)
    scanned = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
        for name in filenames:
            full = current / name
            rel = full.relative_to(ws.root).as_posix()
            if policy.is_ignored(rel):
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if total_bytes + size > MAX_SCAN_BYTES:
                return
            if is_binary(full):
                continue
            total_bytes += size
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                return
            yield rel, full


__all__ = ["iter_scan_files"]
