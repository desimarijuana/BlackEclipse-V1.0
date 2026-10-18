"""Bounded disk hygiene for the video workspace (Phase 8).

The video workspace grows by design: every render/preview job keeps its exact
spec, its MP4(s), its preview PNGs and its report under
``<video-root>/jobs/<jobId>/``. That material is safe to prune — the FINAL MP4
is COPIED into the Artifact Center at registration, so a job workspace is an
audit aid, not the deliverable itself. This module keeps the growth bounded
with two budgets (the same shape as the code-workspace TTL sweep and the
artifact reconciler):

- the newest ``gc_keep_jobs`` job directories are kept;
- directories beyond that count, or the oldest ones while the total size is
  over ``gc_max_total_mb``, are removed oldest-first;
- the single NEWEST directory is never removed (it may be a render in flight);
- ``projects/`` is never touched — it is the durable user-facing data;
- a pass is best-effort and never raises; it never blocks boot.

Runs at boot (``boot.py`` lifespan, like the code-workspace sweep) and on
demand through ``VideoService.prune_workspace()``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from .config import VideoConfig, get_video_config

log = logging.getLogger("harness.video")


def prune_video_workspace(config: Optional[VideoConfig] = None) -> dict[str, Any]:
    """Enforce the job-workspace budgets; best-effort, never raises.

    Returns ``{removed: [jobId], kept: n, freedBytes, totalBytes, skipped}``.
    """
    cfg = config or get_video_config()
    result: dict[str, Any] = {
        "removed": [], "kept": 0, "freedBytes": 0, "totalBytes": 0, "skipped": None,
    }
    if not cfg.gc_enabled:
        result["skipped"] = "disabled"
        return result
    try:
        jobs_root = cfg.resolve_video_root() / "jobs"
        if not jobs_root.is_dir():
            return result
        entries = [entry for entry in jobs_root.iterdir() if entry.is_dir()]
        if not entries:
            return result
        sizes = {entry: _dir_size(entry) for entry in entries}
        total = sum(sizes.values())
        ordered = sorted(entries, key=_mtime)  # oldest first
        keep_count = max(1, int(cfg.gc_keep_jobs))
        max_bytes = max(1, int(cfg.gc_max_total_mb)) * 1024 * 1024

        while ordered and len(ordered) > 1:
            over_count = len(ordered) > keep_count
            over_bytes = total > max_bytes
            if not (over_count or over_bytes):
                break
            candidate = ordered.pop(0)  # the oldest remaining
            try:
                shutil.rmtree(candidate)
            except OSError:
                # A locked file (antivirus, a just-finished child) must not
                # break the pass; the next pass tries again.
                continue
            total -= sizes[candidate]
            result["removed"].append(candidate.name)
            result["freedBytes"] += sizes[candidate]

        result["kept"] = len(ordered)
        result["totalBytes"] = total
        return result
    except Exception:  # noqa: BLE001 - hygiene must never break boot or a job
        log.warning("video workspace prune failed", exc_info=True)
        result["skipped"] = "error"
        return result


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for file in path.rglob("*"):
            try:
                if file.is_file():
                    total += file.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


__all__ = ["prune_video_workspace"]
